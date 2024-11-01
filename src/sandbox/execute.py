"""
このプログラムでは、以下のような機能を実装する。
* Dockerボリュームの作成と削除を行うボリューム管理クラスVolume
* Dockerコンテナの作成と削除を行うコンテナ管理クラスContainerInfo
* タスクの実行を行うタスク管理クラスTaskInfo
* タスクの実行結果を格納するクラスTaskResult
"""

# 外部定義モジュールのインポート
import uuid
import subprocess
import threading
from pydantic import BaseModel, Field
from dataclasses import dataclass, field
import time  # 実行時間の計測に使用
from pathlib import Path
import logging
import docker
from docker.models.containers import Container
from docker.models import volumes
from docker.errors import APIError, ImageNotFound
from docker.types import Ulimit, LogConfig
import requests
import tempfile
import tarfile
from dotenv import load_dotenv
import os
import socket

load_dotenv()

GUEST_UID = os.getenv("GUEST_UID")
GUEST_GID = os.getenv("GUEST_GID")
CGROUP_PARENT = os.getenv("CGROUP_PARENT")

# 内部定義モジュールのインポート
from .my_error import Error

SANDBOX_LOGGER = logging.getLogger("sandbox")

def define_sandbox_logger(logger: logging.Logger):
    global SANDBOX_LOGGER
    SANDBOX_LOGGER = logger

# Dockerボリュームの管理クラス
class DockerVolume:
    name: str  # ボリューム名
    _volume: volumes.Volume | None
    
    def __init__(self, name: str, volume: volumes.Volume | None = None):
        self.name = name
        self._volume = volume

    @classmethod
    def create(cls, client: docker.DockerClient) -> tuple["DockerVolume", Error]:
        volumeName = "volume-" + str(uuid.uuid4())
        try:
            volume = client.volumes.create(name=volumeName)
        except APIError as e:
            return DockerVolume("", None), Error(f"Failed to create volume: {e}")

        SANDBOX_LOGGER.debug(f"volumeName: {volumeName}")
        return DockerVolume(volumeName, volume), Error("")

    def remove(self) -> Error:
        if self._volume is None:
            return Error("Volume is not created")

        try:
            self._volume.remove()
        except APIError as e:
            return Error(f"Failed to remove volume: {e}")

        return Error("")

class VolumeMountInfo:
    path: str # コンテナ内のマウント先のパス
    volume: DockerVolume  # マウントするボリュームの情報
    read_only: bool = False
    
    def __init__(self, path: str, volume: DockerVolume, read_only: bool = False):
        self.path = path
        self.volume = volume
        self.read_only = read_only


# Dockerコンテナの管理クラス
class ContainerInfo:
    containerID: str  # コンテナID
    _container: Container | None
    cgroup_parent: str
    
    def __init__(
        self,
        client: docker.DockerClient,
        imageName: str,
        arguments: list[str],
        interactive: bool = False,
        cgroupParent: str | None = None,
        user: str | None = f"{GUEST_UID}",
        groups: list[str] | None = [f"{GUEST_GID}"],
        cpuset: list[int] | None = None,
        memoryLimitMB: int = -1,
        stackLimitKB: int = -1,
        pidsLimit: int = -1,
        enableNetwork: bool = False,
        enableLoggingDriver: bool = True,
        workDir: str = "/home/guest",
        volumeMountInfoList: list[VolumeMountInfo] | None = None,
    ):
        ulimit_list: list[Ulimit] = []
        
        if stackLimitKB > 0:
            ulimit_list += [Ulimit(name="stack", soft=stackLimitKB, hard=stackLimitKB)]
        
        container: Container = client.containers.create(
            image=imageName,
            command=arguments,
            cgroup_parent=cgroupParent if cgroupParent is not None else None,
            user=user,
            group_add=groups,
            cpuset_cpus=",".join([str(cpu) for cpu in cpuset]) if cpuset is not None else None,
            mem_limit=f"{memoryLimitMB}m" if memoryLimitMB > 0 else None,
            memswap_limit=f"{memoryLimitMB}m" if memoryLimitMB > 0 else None,
            ulimits=ulimit_list,
            pids_limit=pidsLimit if pidsLimit > 0 else None,
            network_disabled=not enableNetwork,
            log_config=LogConfig(type=LogConfig.types.JSON) if enableLoggingDriver else None,
            working_dir=workDir,
            volumes={
                volume_mount_info.volume.name: {
                    "bind": volume_mount_info.path,
                    "mode": "rw" if not volume_mount_info.read_only else "ro"
                } for volume_mount_info in volumeMountInfoList
            } if volumeMountInfoList is not None else None,
            stdin_open=interactive,
        )
        
        self._container = container
        self.containerID = container.id
        self.cgroup_parent = cgroupParent if cgroupParent is not None else "system.slice"
        
        SANDBOX_LOGGER.debug(f'containerID: {self.containerID}, err: ""')

    def remove(self) -> Error:
        try:
            self._container.remove(force=True)
        except APIError as e:
            return Error(f"Failed to remove container: {e}")
        except Exception as e:
            return Error(f"Failed to remove container: {e}")
        
        SANDBOX_LOGGER.debug(f"remove container: {self.containerID}")

        return Error("")

    # ファイルのコピー
    def copyFile(self, srcInHost: Path, dstInContainer: Path) -> Error:
        try:
            with tempfile.TemporaryFile(suffix=".tar") as tmp:
                tar = tarfile.open(fileobj=tmp, mode="w")
                tar.add(srcInHost, arcname=srcInHost.name)
                tar.close()
                
                tmp.seek(0)
                if not self._container.put_archive(path=str(dstInContainer), data=tmp.read()):
                    return Error("Failed to put archive")
        except APIError as e:
            return Error(f"Failed to copy file: {e}")
        except Exception as e:
            return Error(f"Failed to copy file: {e}")

        SANDBOX_LOGGER.debug(f"copy file: {srcInHost} -> {dstInContainer}")

        return Error("")
    
    def downloadFile(self, absPathInContainer: Path, dstInHost: Path) -> Error:
        try:
            stream, stat = self._container.get_archive(path=str(absPathInContainer))
            with tempfile.TemporaryFile(suffix=".tar") as tmp:
                for chunk in stream:
                    tmp.write(chunk)
                
                tmp.seek(0)
                with tarfile.open(fileobj=tmp, mode="r") as tar:
                    tar.extractall(path=str(dstInHost))
        except APIError as e:
            return Error(f"Failed to download file: {e}")
        except Exception as e:
            return Error(f"Failed to download file: {e}")
        
        return Error("")
    
    def start(self) -> Error:
        try:
            self._container.start()
        except APIError as e:
            return Error(f"Failed to start container: {e}")
        except Exception as e:
            return Error(f"Failed to start container: {e}")

        SANDBOX_LOGGER.debug(f"start container: {self.containerID}")

        return Error("")

    def exec_run(
        self,
        command: list[str],
        user: str = "",
        workDir: str = "/home/guest",
        timeoutSec: float = 10.0,
    ) -> tuple["ExecRunResult", Error]:
        pass
        # container.exec_run(...)でコマンドを実行する
        # タイムアウト時刻を過ぎても終了しない場合はコンテナをkillする
        try:
            result = ExecRunResult()
            error = Error("")
            execution_completed = threading.Event()
            
            def run_command():
                start_time = time.monotonic()
                exec_result = self._container.exec_run(
                    cmd=command,
                    user=user,
                    demux=True
                )
                end_time = time.monotonic()
                result.timeMS = int((end_time - start_time) * 1000)
                result.exitCode = exec_result.exit_code
                stdout_data, stderr_data = exec_result.output
                result.stdout = stdout_data.decode() if stdout_data else ""
                result.stderr = stderr_data.decode() if stderr_data else ""
                
                execution_completed.set()
                
            # コマンド実行用スレッドを開始
            thread = threading.Thread(target=run_command)
            thread.start()
            
            # タイムアウトまで待機、完了したら即座に終了
            if not execution_completed.wait(timeout=timeoutSec):
                self._container.kill()
                error = Error(f"Command timed out after {timeoutSec} seconds. Container killed.")
                thread.join()
            
            SANDBOX_LOGGER.debug(f"exec_run: {' '.join(command)}, err: {error}") 
            
            return result, error
        except APIError as e:
            return ExecRunResult(), Error(f"Failed to exec_run: {e}")
        except Exception as e:
            return ExecRunResult(), Error(f"Failed to exec_run: {e}")
        

class ExecRunResult(BaseModel):
    exitCode: int = Field(default=-1)
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    timeMS: int = Field(default=-1)


# watchdogに渡す設定
class TaskInfo(BaseModel):
    command: str
    stdin: str
    timeoutMS: int
    memoryLimitMB: int
    uid: int
    gid: int


class WatchDogResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    timeMS: int
    memoryKB: int
    TLE: bool
    MLE: bool
    
    model_config = {
        "from_attributes": True
    }
