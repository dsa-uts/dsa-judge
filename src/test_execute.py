# テストプログラム実行方法
# $ cd src
# $ pytest --log-cli-level=INFO test_execute.py
import pytest
import sandbox
from sandbox.execute import TaskInfo
from sandbox.execute import Volume
from sandbox.execute import VolumeMountInfo
import logging
from datetime import timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
import time

from db.crud import *
from db.database import SessionLocal

# ロガーの設定
logging.basicConfig(level=logging.INFO)
test_logger = logging.getLogger(__name__)


# Dockerコンテナを起動して、Hello, World!を出力するテスト
def test_RunHelloWorld():
    task = TaskInfo(
        name="ubuntu",
        arguments=["echo", "Hello, World!"],
        timeoutSec=5.0,
        memoryLimitMB=256,
        cpus=1,
    )

    result, err = task.run()

    test_logger.info(result)
    test_logger.info(err)

    assert err.message == ""

    assert result.exitCode == 0

    assert result.stdout == "Hello, World!\n"

    assert result.stderr == ""


# sandboxの戻り値をきちんとチェックできているか確かめるテスト
def test_ExitCode():
    task = TaskInfo(
        name="ubuntu",
        arguments=["sh", "-c", "exit 123"],
        timeoutSec=5.0,
        memoryLimitMB=256,
        cpus=1,
    )

    result, err = task.run()

    test_logger.info(result)
    test_logger.info(err)

    assert err.message == ""
    assert result.exitCode == 123
    assert result.stdout == ""
    assert result.stderr == ""


# 標準入力をきちんと受け取れているか確かめるテスト
def test_Stdin():
    task = TaskInfo(
        name="ubuntu",
        arguments=["sh", "-c", "read input; test $input = dummy"],
        Stdin="dummy",
    )

    result, err = task.run()

    test_logger.info(result)
    test_logger.info(err)

    assert err.message == ""
    assert result.exitCode == 0
    assert result.stdout == ""
    assert result.stderr == ""


# 標準出力をきちんとキャプチャできているか確かめるテスト
def test_Stdout():
    task = TaskInfo(name="ubuntu", arguments=["echo", "dummy"])

    result, err = task.run()

    test_logger.info(result)
    test_logger.info(err)

    assert err.message == ""
    assert result.exitCode == 0
    assert result.stdout == "dummy\n"
    assert result.stderr == ""


# 標準エラー出力をちゃんとキャプチャできているか確かめるテスト
def test_Stderr():
    task = TaskInfo(name="ubuntu", arguments=["sh", "-c", "echo dummy >&2"])

    result, err = task.run()

    test_logger.info(result)
    test_logger.info(err)

    assert err.message == ""
    assert result.exitCode == 0
    assert result.stdout == ""
    assert result.stderr == "dummy\n"


# sleepした分ちゃんと実行時間が計測されているか確かめるテスト
def test_SleepTime():
    task = TaskInfo(name="ubuntu", arguments=["sleep", "3"], timeoutSec=5.0)

    result, err = task.run()

    test_logger.info(result)
    test_logger.info(err)

    assert err.message == ""
    assert result.exitCode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.timeMS >= 2000 and result.timeMS <= 5000


# タイムアウトをきちんと検出できているか確かめるテスト
def test_Timeout():
    task = TaskInfo(name="ubuntu", arguments=["sleep", "100"], timeoutSec=3.0)

    result, err = task.run()

    test_logger.info(result)
    test_logger.info(err)

    assert err.message == ""
    assert result.TLE == True


# ファイルをDockerボリュームにコピーするテスト
def test_CopyFileFromClientToVolume():
    # ファイル転送先のボリュームの作成
    volume, err = Volume.create()

    assert err.message == ""

    # tempdir にファイルを作成
    with TemporaryDirectory() as tempdir:
        with open(Path(tempdir) / "test.txt", "w") as f:
            f.write("Hello, World!")

        # ファイルをボリュームにコピー
        volume.copyFile(Path(tempdir) / "test.txt", Path("test.txt"))

    # ファイルがコピーされたことを確認
    task = TaskInfo(
        name="ubuntu",
        arguments=["cat", "test.txt"],
        workDir="/workdir/",
        volumeMountInfo=[VolumeMountInfo(path="/workdir/", volume=volume)],
    )

    result, err = task.run()

    test_logger.info(result)

    assert err.message == ""

    assert result.exitCode == 0

    assert result.stdout == "Hello, World!"

    assert result.stderr == ""

    err = volume.remove()

    assert err.message == ""


# 複数のファイルをDockerボリュームにコピーするテスト
def test_CopyFilesFromClientToVolume():
    # ファイル転送先のボリュームの作成
    volume, err = Volume.create()

    assert err.message == ""

    # tempdir にファイルを作成
    with TemporaryDirectory() as tempdir:
        with open(Path(tempdir) / "test1.txt", "w") as f:
            f.write("Hello, World!")

        with open(Path(tempdir) / "test2.txt", "w") as f:
            f.write("Goodbye, World!")

        # ファイルをボリュームにコピー
        volume.copyFiles(
            filePathsFromClient=[
                Path(tempdir) / "test1.txt",
                Path(tempdir) / "test2.txt",
            ],
            DirPathInVolume=Path("./"),
        )

    # ファイルがコピーされたことを確認
    task = TaskInfo(
        name="ubuntu",
        arguments=["cat", "test1.txt", "test2.txt"],
        workDir="/workdir/",
        volumeMountInfo=[VolumeMountInfo(path="/workdir/", volume=volume)],
    )

    result, err = task.run()

    test_logger.info(result)

    assert err.message == ""

    assert result.exitCode == 0

    assert result.stdout == "Hello, World!Goodbye, World!"

    assert result.stderr == ""

    err = volume.remove()

    assert err.message == ""


# Dockerボリュームにある複数のファイルを削除するテスト
def test_RemoveFilesInVolume():
    # ファイル転送先のボリュームの作成
    volume, err = Volume.create()

    assert err.message == ""

    # tempdir にファイルを作成
    with TemporaryDirectory() as tempdir:
        with open(Path(tempdir) / "test1.txt", "w") as f:
            f.write("Hello, World!")

        with open(Path(tempdir) / "test2.txt", "w") as f:
            f.write("Goodbye, World!")

        # ファイルをボリュームにコピー
        volume.copyFiles(
            filePathsFromClient=[
                Path(tempdir) / "test1.txt",
                Path(tempdir) / "test2.txt",
            ],
            DirPathInVolume=Path("./"),
        )

    # ファイルがコピーされたことを確認
    task = TaskInfo(
        name="ubuntu",
        arguments=["ls"],
        workDir="/workdir/",
        volumeMountInfo=[VolumeMountInfo(path="/workdir/", volume=volume)],
    )

    result, err = task.run()

    test_logger.info(result)

    assert err.message == ""

    assert result.exitCode == 0

    assert result.stdout == "test1.txt\ntest2.txt\n"

    assert result.stderr == ""

    # ファイルを削除
    volume.removeFiles([Path("test1.txt"), Path("test2.txt")])

    # ファイルが削除されたことを確認
    task = TaskInfo(
        name="ubuntu",
        arguments=["ls"],
        workDir="/workdir/",
        volumeMountInfo=[VolumeMountInfo(path="/workdir/", volume=volume)],
    )

    result, err = task.run()

    test_logger.info(result)

    assert err.message == ""

    assert result.exitCode == 0

    assert result.stdout == ""

    assert result.stderr == ""

    err = volume.remove()

    test_logger.info(err)

    assert err.message == ""


# ボリュームのクローンができているかチェック
def test_CloneVolume():
    # 一時ディレクトリを作成
    with TemporaryDirectory() as temp_dir:
        # テストファイルを作成
        file1_path = Path(temp_dir) / "file1.txt"
        file2_path = Path(temp_dir) / "file2.txt"
        with open(file1_path, "w") as f1, open(file2_path, "w") as f2:
            f1.write("Content of file1")
            f2.write("Content of file2")

        # 元のボリュームを作成
        original_volume, err = Volume.create()
        assert err.message == ""

        # テストファイルを元のボリュームにコピー
        err = original_volume.copyFile(Path(file1_path), Path("file1.txt"))
        assert err.message == ""
        err = original_volume.copyFile(Path(file2_path), Path("file2.txt"))
        assert err.message == ""

        # ボリュームをクローン
        cloned_volume, err = original_volume.clone()
        assert err.message == ""

        # クローンされたボリュームの内容を確認
        task = TaskInfo(
            name="ubuntu",
            arguments=["ls"],
            workDir="/workdir/",
            volumeMountInfo=[VolumeMountInfo(path="/workdir/", volume=cloned_volume)],
        )

        result, err = task.run()
        assert err.message == ""
        assert result.exitCode == 0
        assert "file1.txt" in result.stdout
        assert "file2.txt" in result.stdout

        # クリーンアップ
        err = original_volume.remove()
        assert err.message == ""
        err = cloned_volume.remove()
        assert err.message == ""

# メモリ制限を検出できるかチェック
def test_MemoryLimit():
    task = TaskInfo(
        name="ubuntu",
        arguments=["dd", "if=/dev/zero", "of=/dev/null", "bs=800M"],
        timeoutSec=3.0,
        memoryLimitMB=500,
    )

    result, err = task.run()

    assert err.message == ""

    test_logger.info(result)

    assert result.exitCode != 0
    # assert result.TLE == False
    assert abs(result.memoryByte - 500 * 1024 * 1024) < 1024 * 1024


# ネットワーク制限をできているかチェック
def test_NetworkDisable():
    task = TaskInfo(
        name="ibmcom/ping",
        arguments=["ping", "-c", "5", "google.com"],
        enableNetwork=None,
    )

    result, err = task.run()

    assert err.message == ""

    test_logger.info(result)

    assert result.exitCode != 0
    assert result.TLE == False
    assert result.stdout == ""


# フォークボムなどの攻撃に対処できるように、プロセス数制限ができているかチェック
def test_ForkBomb():
    volume, err = Volume.create()

    assert err.message == ""

    err = volume.copyFile(Path("sources/fork_bomb.sh"), Path("fork_bomb.sh"))

    assert err.message == ""

    task = TaskInfo(
        name="ubuntu",
        arguments=["./fork_bomb.sh"],
        workDir="/workdir/",
        volumeMountInfo=[VolumeMountInfo(path="/workdir/", volume=volume)],
        timeoutSec=3.0,
        pidsLimit=10,
    )

    result, err = task.run()

    test_logger.info(result)
    test_logger.info(err)

    err = volume.remove()

    assert err.message == ""


# スタックメモリの制限ができているかチェック
def test_UseManyStack():
    volume, err = Volume.create()

    assert err.message == ""

    err = volume.copyFile(Path("sources/use_many_stack.cpp"), Path("use_many_stack.cpp"))

    assert err.message == ""

    task = TaskInfo(
        name="gcc:13.3",
        arguments=["g++", "use_many_stack.cpp"],
        workDir="/workdir/",
        volumeMountInfo=[VolumeMountInfo(path="/workdir/", volume=volume)],
    )

    result, err = task.run()

    test_logger.info(result)
    test_logger.info(err)

    assert err.message == ""
    assert result.exitCode == 0

    task = TaskInfo(
        name="gcc:13.3",
        arguments=["./a.out"],
        workDir="/workdir/",
        volumeMountInfo=[VolumeMountInfo(path="/workdir/", volume=volume)],
        stackLimitKB=10240,
        memoryLimitMB=256,
    )

    result, err = task.run()

    test_logger.info(result)
    test_logger.info(err)

    assert result.exitCode != 0

    err = volume.remove()

    assert err.message == ""


# 試しにジャッジリクエストを投じてみて、どのような結果になるか見てみる。
def test_submit_judge():
    with SessionLocal() as db:
        # ジャッジリクエストを登録
        submission = register_judge_request(
            db=db,
            batch_id=None,
            student_id="sxxxxxxx",
            lecture_id=1,
            assignment_id=1,
            for_evaluation=False,
        )

        # 提出されたファイルを登録
        register_uploaded_files(
            db=db,
            submission_id=submission.id,
            path=Path("sample_submission/ex1-1/gcd_euclid.c"),
        )
        register_uploaded_files(
            db=db,
            submission_id=submission.id,
            path=Path("sample_submission/ex1-1/main_euclid.c"),
        )
        register_uploaded_files(
            db=db,
            submission_id=submission.id,
            path=Path("sample_submission/ex1-1/Makefile"),
        )

        # ジャッジリクエストをキューに並べる
        enqueue_judge_request(db=db, submission_id=submission.id)
    
    
    while True:
        with SessionLocal() as db:
            # ジャッジが完了するまでsubmissionのステータスを見張る
            progress = fetch_judge_status(db=db, submission_id=submission.id)
            if progress == SubmissionProgressStatus.DONE:
                break
        time.sleep(1.0)
    
    # 結果を取得する
    with SessionLocal() as db:
        judge_results = fetch_judge_results(db=db, submission_id=submission.id)
    
    for judge_result in judge_results:
        test_logger.info(judge_result)
