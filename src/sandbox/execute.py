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
import re
from pathlib import Path
from typing import Callable
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


        args = ["volume", "create"]
        args += ["--name", volumeName]

        # Dockerボリュームの作成
        cmd = ["docker"] + args
        err = ""

        
        args = ["volume", "create"]
        args += ["--name", volumeName]

        # Dockerボリュームの作成
        cmd = ["docker"] + args
        err = ""

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

    def copyFile(self, client: docker.DockerClient, srcPathOnClient: Path, dstDirOnVolume: Path = Path("./")) -> Error:
        try:
            container: Container = client.containers.create(
                image="binary-runner",
                command=["echo", "Hello, World!"],
                working_dir="/home/guest",
                user=f"{GUEST_UID}:{GUEST_GID}",
                volumes={self._volume.name: {'bind': '/home/guest', 'mode': 'rw'}}
            )
        
            # filePathInVolumeが絶対パスの場合、相対パスに変換
            if dstDirOnVolume.is_absolute():
                dstDirOnVolume = Path(".") / dstDirOnVolume.relative_to("/")

            dstInContainer = Path("/home/guest") / dstDirOnVolume / srcPathOnClient.name
            # docker sdkのput_archiveは停止しているコンテナには使えない
            # そのため、docker cpコマンドを使ってファイルをコピーする
            cmd = ["docker", "cp", str(srcPathOnClient), f"{container.id}:{str(dstInContainer)}"]
            SANDBOX_LOGGER.debug(f"cmd: {cmd}")
            if subprocess.run(cmd, check=False).returncode != 0:
                return Error(f"Failed to copy file")
    
            container.remove()
        except APIError as e:
            return Error(f"Failed to copy file: {e}")
        except ImageNotFound as e:
            return Error(f"Failed to copy file: {e}")
        except Exception as e:
            return Error(f"Failed to copy file: {e}")
        return Error("")

    def copyFiles(
        self, client: docker.DockerClient, srcPathsOnClient: list[Path], dstDirOnVolume: Path = Path("./")
    ) -> Error:
        try:
            container: Container = client.containers.create(
                image="binary-runner",
                command=["echo", "Hello, World!"],
                working_dir="/home/guest",
                user=f"{GUEST_UID}:{GUEST_GID}",
                volumes={self._volume.name: {'bind': '/home/guest', 'mode': 'rw'}}
            )
            
            # DirPathInVolumeが絶対パスの場合、相対パスに変換
            if dstDirOnVolume.is_absolute():
                dstDirOnVolume = Path(".") / dstDirOnVolume.relative_to("/")

            for srcPathOnClient in srcPathsOnClient:
                dstPathInContainer = Path("/home/guest") / dstDirOnVolume / srcPathOnClient.name
                cmd = ["docker", "cp", str(srcPathOnClient), f"{container.id}:{str(dstPathInContainer)}"]
                SANDBOX_LOGGER.debug(f"cmd: {cmd}")
                if subprocess.run(cmd, check=False).returncode != 0:
                    return Error(f"Failed to copy file")
            
            container.remove(force=True)
        except APIError as e:
            return Error(f"Failed to copy file: {e}")
        except ImageNotFound as e:
            return Error(f"Failed to copy file: {e}")
        except Exception as e:
            return Error(f"Failed to copy file: {e}")

        return Error("")

    def removeFiles(self, client: docker.DockerClient, filePathsInVolume: list[Path]) -> Error:
        arguments = ["rm"]

        for filePath in filePathsInVolume:
            if filePath.is_absolute():
                filePath = Path(".") / filePath.relative_to("/")
            filePathInContainer = Path("/home/guest") / filePath
            arguments += [str(filePathInContainer.resolve())]
            
        try:
            container: Container = client.containers.create(
                image="binary-runner",
                command=arguments,
                working_dir="/home/guest",
                user=f"{GUEST_UID}:{GUEST_GID}",
                volumes={self._volume.name: {'bind': '/home/guest', 'mode': 'rw'}}
            )
            
            container.start()
            container.wait()
            container.remove(force=True)
        except APIError as e:
            return Error(f"Failed to remove file: {e}")
        except ImageNotFound as e:
            return Error(f"Failed to remove file: {e}")
        except Exception as e:
            return Error(f"Failed to remove file: {e}")

        return Error("")
    
    def clone(self, client: docker.DockerClient) -> tuple["DockerVolume", Error]:
        # 新しいDockerボリュームを作成
        new_volume, err = DockerVolume.create(client)
        if err.message != "":
            return DockerVolume("", None), Error(f"新しいボリュームの作成に失敗しました: {err.message}")

        # 元のボリュームの内容を新しいボリュームにコピー
        try:
            container: Container = client.containers.create(
                image="binary-runner",
                command=["cp", "-r", "/workdir/src/.", "/workdir/dst"],
                working_dir="/workdir",
                user="root",
                volumes={self._volume.name: {'bind': '/workdir/src', 'mode': 'rw'}, new_volume.name: {'bind': '/workdir/dst', 'mode': 'rw'}}
            )
            
            container.start()
            result = container.wait()

            if result["StatusCode"] != 0:
                new_volume.remove()
                return DockerVolume("", None), Error(f"Failed to clone volume")
            
            container.remove(force=True)
        except APIError as e:
            return DockerVolume("", None), Error(f"Failed to clone volume: {e}")
        except ImageNotFound as e:
            return DockerVolume("", None), Error(f"Failed to clone volume: {e}")
        except Exception as e:
            return DockerVolume("", None), Error(f"Failed to clone volume: {e}")

        return new_volume, Error("")


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
    
    def __init__(self):
        self._container = None
        self.containerID = ""
        self.cgroup_parent = ""

    # Dockerコンテナの作成
    def _create(
        self,
        client: docker.DockerClient,
        ImageName: str,
        arguments: list[str],
        cgroupParent: str | None = CGROUP_PARENT,
        user: str | None = f"{GUEST_UID}",
        groups: list[str] | None = [f"{GUEST_GID}"],
        cpuset: list[int] | None = None,
        memoryLimitMB: int = -1,
        stackLimitKB: int = -1,
        pidsLimit: int = -1,
        enableNetwork: bool = False,
        enableLoggingDriver: bool = True,
        workDir: str = "/home/guest",
        volumeMountInfoList: list[VolumeMountInfo] = None,
    ) -> Error:
        
        SANDBOX_LOGGER.info(f"cgroupParent: {cgroupParent}")
        
        ulimit_list: list[Ulimit] = []
        
        if stackLimitKB > 0:
            ulimit_list += [Ulimit(name="stack", soft=stackLimitKB, hard=stackLimitKB)]
        
        try:
            container: Container = client.containers.create(
                image=ImageName,
                command=arguments,
                cgroup_parent = cgroupParent if cgroupParent is not None else "system.slice",
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
                },
                stdin_open=True, # Keep STDIN open even if not attached (-iオプションに相当)
            )
            
            self._container = container
            self.containerID = container.id
            self.cgroup_parent = cgroupParent if cgroupParent is not None else "system.slice"
        except APIError as e:
            return Error(f"Failed to create container: {e}")
        except ImageNotFound as e:
            return Error(f"Failed to create container: {e}")
        except Exception as e:
            return Error(f"Failed to create container: {e}")
        
        SANDBOX_LOGGER.debug(f'containerID: {self.containerID}, err: ""')

        return Error("")

    def remove(self) -> Error:
        try:
            self._container.remove(force=True)
        except APIError as e:
            return Error(f"Failed to remove container: {e}")
        except ImageNotFound as e:
            return Error(f"Failed to remove container: {e}")
        except Exception as e:
            return Error(f"Failed to remove container: {e}")
        
        SANDBOX_LOGGER.debug(f"remove container: {self.containerID}")

        return Error("")

    # ファイルのコピー
    def copyFile(self, srcInHost: Path, dstInContainer: Path) -> Error:
        try:
            with tempfile.TemporaryFile() as tmp:
                tar = tarfile.open(fileobj=tmp, mode="w")
                tar.add(srcInHost)
                tar.close()
                
                tmp.seek(0)
                self._container.put_archive(path=str(dstInContainer), data=tmp.read())
        except APIError as e:
            return Error(f"Failed to copy file: {e}")
        except ImageNotFound as e:
            return Error(f"Failed to copy file: {e}")
        except Exception as e:
            return Error(f"Failed to copy file: {e}")

        SANDBOX_LOGGER.debug(f"copy file: {srcInHost} -> {dstInContainer}")

        return Error("")


__MEM_USAGE_PATTERN = re.compile(r"^(\d+(\.\d+)?)([KMG]i?)B")


# 時間・メモリ計測用のモニター
class TaskMonitor:
    cgroup_parent: str
    _cgroup_path: Path
    startTime: int
    endTime: int
    maxUsedMemory: int  # 最大使用メモリ量[Byte]
    containerInfo: ContainerInfo  # モニタリング対象のコンテナ情報
    _monitoring: bool  # モニタリング中かどうか
    _monitor_thread: threading.Thread  # モニタリングスレッド

    def __init__(self, containerInfo: ContainerInfo):
        self.cgroup_parent = containerInfo.cgroup_parent
        self.startTime = 0
        self.endTime = 0
        self.maxUsedMemory = 0
        self.containerInfo = containerInfo
        self._monitoring = False
        self._cgroup_path = Path("/sys-host/fs/cgroup/") / self.cgroup_parent / f"docker-{containerInfo.containerID}.scope" / "memory.current"

    def start(self):
        self.startTime = time.time_ns()
        # containerInfo.containerIDを使ってコンテナのメモリ使用量を取得する
        # 取得はdocker statsコマンドを使い、1msごとに取得する
        # 取得したメモリ使用量からmaxUsedMemoryを更新する
        self._monitoring = True
        # TODO: docker statsは遅いので、/sys/fs/cgroupからメモリ使用量を取得する方法を検討する
        self._monitor_thread = threading.Thread(
            target=self.__monitor_memory_usage_by_cgroup
        )
        self._monitor_thread.start()

    def end(self):
        self.endTime = time.time_ns()
        self._monitoring = False
        self._monitor_thread.join()

    def get_elapsed_time_ms(self) -> float:
        return (self.endTime - self.startTime) / 1e6

    def get_used_memory_byte(self) -> int:
        return self.maxUsedMemory

    '''
    Dockerコンテナのメモリの取得方法は3つある
    1. docker statsコマンドを使って取得する
    2. /sys/fs/cgroup/system.slice/docker-xxxxxx.scope/memory.currentから取得する
    3. psコマんドで取得する
         * docker inspect -f '{{.State.Pid}}' <container id> でコンテナIDに対応するPIDを取得
         * ps -p <pid> -o pid,comm,rss でRSSを取得
    1の手法は遅い。
    2の手法は早いが、Linuxでしか使えない。
    3の手法の場合、ユーザ空間のプロセスのRSSを取得するため、全体のメモリ使用量を取得できない。
    ref: https://unix.stackexchange.com/questions/686814/cgroup-and-process-memory-statistics-mismatch
    '''

    def __monitor_memory_usage_by_docker_stats(self) -> None:
        while self._monitoring:
            # docker statsコマンドを使ってコンテナのメモリ使用量を取得する
            result = subprocess.run(
                [
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.MemUsage}}",
                    self.containerInfo.containerID,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            SANDBOX_LOGGER.debug(f"docker stats: {result.stdout}")

            # result.stdout = "1.23GiB / 2.00GiB"といった形式でメモリ使用量が取得できる
            # この値をパースしてmaxUsedMemoryを更新する
            if result.returncode == 0:
                mem_usage = result.stdout.strip()
                used_memory = self.__parse_memory_usage_docker_stats(mem_usage)
                if used_memory > self.maxUsedMemory:
                    self.maxUsedMemory = used_memory
                time.sleep(0.001)  # 1ms待つ

    def __parse_memory_usage_docker_stats(self, mem_usage: str) -> int:
        # "1.23 GiB / 2.00 GiB" -> 1.23 -> 1.23 * 1024 * 1024 * 1024
        match = __MEM_USAGE_PATTERN.match(mem_usage)
        if match:
            # __MEM_USAGE_PATTERN.match("1.23 GiB / 2.00 GiB")
            # match.group(1) = "1.23"
            # match.group(2) = ".23"
            # match.group(3) = "Gi"
            value = float(match.group(1))
            unit = match.group(3)
            if unit == "Ki":
                return int(value * 1024)
            elif unit == "Mi":
                return int(value * 1024 * 1024)
            else:
                assert unit == "Gi"
                return int(value * 1024 * 1024 * 1024)
        return 0

    def __monitor_memory_usage_by_cgroup(self) -> None:
        # /sys/fs/cgroup/system.slice/docker-xxxxxx.scope/memory.current
        # からメモリ使用量をバイト単位で取得する
        while self._monitoring:
            try:
                if self._cgroup_path.exists():
                    with self._cgroup_path.open("r") as f:
                        mem_usage = int(f.read())
                        if mem_usage > self.maxUsedMemory:
                            self.maxUsedMemory = mem_usage
            except FileNotFoundError:
                # test_logger.info(f"Cgroup Path not exists: {cgroup_path}")
                pass
            except OSError:
                # test_logger.info(f"Failed to read cgroup file: {cgroup_path}")
                pass
            time.sleep(0.001)


class TaskResult(BaseModel):
    exitCode: int = Field(default=-1)
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    timeMS: int = Field(default=-1)
    memoryByte: int = Field(default=-1)
    TLE: bool = Field(default=True)  # 制限時間を超えたかどうか


# タスクの実行情報
@dataclass
class TaskInfo:
    imageName: str  # コンテナイメージ名
    arguments: list[str] = field(default_factory=list)  # コンテナ内で実行するコマンド
    timeoutSec: float = field(default=0.0)  # タイムアウト時間
    user: str = field(default=f"{GUEST_UID}")
    groups: list[str] = field(default_factory=lambda: [f"{GUEST_GID}"])
    cpuset: list[int] | None = field(default=None)
    memoryLimitMB: int = field(default=0)  # メモリ制限
    stackLimitKB: int = field(default=0)  # リカージョンの深さを制限
    pidsLimit: int = field(default=0)  # プロセス数の制限
    enableNetwork: bool = field(default=False)
    enableLoggingDriver: bool = field(default=True)
    workDir: str = field(default="/home/guest")  # コンテナ内での作業ディレクトリ
    cgroupParent: str = field(default=CGROUP_PARENT) # cgroupの親ディレクトリ
    volumeMountInfoList: list[VolumeMountInfo] = field(
        default_factory=list
    )  # ボリュームのマウント情報
    taskMonitor: TaskMonitor = field(
        default_factory=lambda: TaskMonitor(ContainerInfo())
    )

    Stdin: str = ""  # 標準入力
    Stdout: str = ""  # 標準出力
    Stderr: str = ""  # 標準エラー出力

    # Dockerコンテナの作成
    def __create(self, client: docker.DockerClient) -> tuple[ContainerInfo, Error]:
        # docker create ...
        containerInfo = ContainerInfo()

        # Dockerコンテナの作成
        err = containerInfo._create(
            client=client,
            ImageName=self.imageName,
            arguments=self.arguments,
            cgroupParent=self.cgroupParent,
            user=self.user,
            groups=self.groups,
            cpuset=self.cpuset,
            memoryLimitMB=self.memoryLimitMB,
            stackLimitKB=self.stackLimitKB,
            pidsLimit=self.pidsLimit,
            enableNetwork=self.enableNetwork,
            enableLoggingDriver=self.enableLoggingDriver,
            workDir=self.workDir,
            volumeMountInfoList=self.volumeMountInfoList,
        )

        if err.message != "":
            SANDBOX_LOGGER.debug(
                f'containerID: {containerInfo.containerID}, err: "{err.message}"'
            )
            return ContainerInfo(), err

        # モニターにコンテナ情報を設定
        self.taskMonitor = TaskMonitor(
            containerInfo=containerInfo
        )

        return containerInfo, Error("")

    # docker start ... を実行して、コンテナを起動する。
    # これにより、docker createで指定したコマンド(コンパイル、プログラムの実行等)が実行される。
    def __start(self, containerInfo: ContainerInfo) -> tuple[TaskResult, Error]:
        # self.timeout + 500msの制限時間を設定
        timeout = 30.0  # デフォルトは30秒
        if self.timeoutSec != 0.0:
            timeout = self.timeoutSec + 0.5

        # モニターを開始
        self.taskMonitor.start()

        # Dockerコンテナの起動
        TLE = False
        result = None
        try:
            # docker sdkのstartは、-i(interactive)オプションなどついていない
            # subprocess.runで"docker start"コマンドを直接実行する
            ProcessResult = subprocess.run(
                args=["docker", "start", "-i", containerInfo.containerID],
                capture_output=True,
                text=True,
                timeout=timeout,
                input=self.Stdin,
                check=False,
            )
            # 戻り値を検出
            SANDBOX_LOGGER.debug(f"result: {ProcessResult}")
        except subprocess.TimeoutExpired:
            # タイムアウトした場合
            # モニターを終了(これをしないとtaskMonitorのスレッドが終了しない)
            self.taskMonitor.end()

            # まだ実行中の場合があるので、docker kill...で停止させる。
            try:
                containerInfo._container.kill()
            except APIError as e:
                message = f"failed to stop docker: {e}"
                SANDBOX_LOGGER.error(message)
                SANDBOX_LOGGER.debug(message)
                return TaskResult(
                    TLE=True,
                    timeMS=int(self.taskMonitor.get_elapsed_time_ms()),
                    memoryByte=self.taskMonitor.get_used_memory_byte(),
                ), Error(message)

            result = containerInfo._container.wait()
            exit_code: int = result["StatusCode"]
            err_message: str = "" if "Error" not in result else result["Error"]["Message"]
            if err_message != "":
                return (
                    TaskResult(
                        TLE=True,
                        timeMS=int(self.taskMonitor.get_elapsed_time_ms()),
                        memoryByte=self.taskMonitor.get_used_memory_byte(),
                    ),
                    Error(err_message),
                )
            return TaskResult(
                exitCode=exit_code,
                TLE=True,
                timeMS=int(self.taskMonitor.get_elapsed_time_ms()),
                memoryByte=self.taskMonitor.get_used_memory_byte(),
            ), Error("")

        # モニターを終了
        self.taskMonitor.end()

        # 標準出力、標準エラー出力を取得
        self.Stdout = containerInfo._container.logs(stdout=True, stderr=False).decode("utf-8")
        self.Stderr = containerInfo._container.logs(stdout=False, stderr=True).decode("utf-8")

        # タイムアウトしたかどうか
        if (
            self.timeoutSec != 0.0
            and self.timeoutSec < self.taskMonitor.get_elapsed_time_ms() / 1000
        ):
            TLE = True

        # 終了コードを取得
        result = containerInfo._container.wait()
        SANDBOX_LOGGER.debug(f"result: {result}")
        exit_code = result["StatusCode"]
        err_message = "" if "Error" not in result else result["Error"]["Message"]
        if err_message != "":
            return TaskResult(), Error(err_message)

        return TaskResult(
            exitCode=exit_code,
            stdout=self.Stdout,
            stderr=self.Stderr,
            timeMS=int(self.taskMonitor.get_elapsed_time_ms()),
            memoryByte=self.taskMonitor.get_used_memory_byte(),
            TLE=TLE,
        ), Error("")

    def run(self, client: docker.DockerClient) -> tuple[TaskResult, Error]:
        # コンテナ作成から起動までの処理を行う
        # 途中で失敗したら、作成したコンテナの削除を行い、エラーを返す
        containerInfo, err = self.__create(client=client)
        SANDBOX_LOGGER.debug(
            f'containerID: {containerInfo.containerID}, err: "{err.message}"'
        )
        if err.message != "":
            # コンテナの作成に失敗した場合
            return TaskResult(), err
        SANDBOX_LOGGER.debug(f"containerID: {containerInfo.containerID}")

        SANDBOX_LOGGER.debug("start container")
        result, err = self.__start(containerInfo=containerInfo)

        # コンテナの削除
        err2 = containerInfo.remove()
        if err2.message != "":
            err.message += "\n" + err2.message

        return result, err


def inspectExitCode(containerId: str) -> tuple[int, Error]:
    args = ["inspect", "--format={{.State.ExitCode}}", containerId]

    cmd = ["docker"] + args

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    SANDBOX_LOGGER.debug(f"inspect exit code: {result}")

    err = ""
    if result.returncode != 0:
        err = f"Failed to inspect exit code: {result.stderr}"
        return -1, Error(err)

    return int(result.stdout), Error(err)
