from pathlib import Path
from dataclasses import dataclass, field
from sandbox.execute import Volume
from sandbox.my_error import Error
from sandbox.execute import TaskInfo
from sandbox.execute import VolumeMountInfo
from sqlalchemy.orm import Session
from sandbox.execute import TaskResult
from dotenv import load_dotenv
from db.models import TestCases, Problem
import logging
from db.crud import *
from db.database import SessionLocal
from checker import StandardChecker
import os
from enum import Enum

# ロガーの設定
logging.basicConfig(level=logging.INFO)
test_logger = logging.getLogger("uvicorn")

load_dotenv()

RESOURCE_DIR = Path(os.getenv("RESOURCE_PATH"))

StatusOrder = {
    JudgeSummaryStatus.UNPROCESSED: 0,
    JudgeSummaryStatus.AC: 1,
    JudgeSummaryStatus.WA: 2,
    JudgeSummaryStatus.TLE: 3,
    JudgeSummaryStatus.MLE: 4,
    JudgeSummaryStatus.RE: 5,
    JudgeSummaryStatus.CE: 6,
    JudgeSummaryStatus.OLE: 7,
    JudgeSummaryStatus.IE: 8,
}


class JudgeSummaryStatusAggregator:
    flag: JudgeSummaryStatus

    def __init__(self, flag: JudgeSummaryStatus):
        self.flag = flag

    def update(self, flag: JudgeSummaryStatus) -> None:
        if StatusOrder[self.flag] < StatusOrder[flag]:
            self.flag = flag

class JudgeInfo:
    submission_record: SubmissionRecord # Submissionテーブル内のジャッジリクエストレコード
    
    problem_record: ProblemRecord  # Problemテーブル内のテーブルレコード

    required_files: list[str]  # ユーザに提出を求められているソースコードの名前リスト
    arranged_filepaths: list[
        Path
    ]  # こちらが用意しているソースコードのファイルパスのリスト
    uploaded_filepaths: list[Path]  # ユーザが提出したソースコードのファイルパスのリスト

    entire_status: JudgeSummaryStatusAggregator  # テストケース全体のジャッジ結果

    prebuilt_testcases: list[TestCaseRecord]

    postbuilt_testcases: list[TestCaseRecord]

    judge_testcases: list[TestCaseRecord]

    def __init__(
        self,
        submission: SubmissionRecord
    ):
        self.submission_record = submission

        db = SessionLocal()
        
        problem_record = fetch_problem(
            db=db,
            lecture_id=self.submission_record.lecture_id,
            assignment_id=self.submission_record.assignment_id,
            for_evaluation=self.submission_record.for_evaluation,
        )
        
        if problem_record is None:
            # Submissionテーブルのstatusをdoneに変更
            self.submission_record.progress = SubmissionProgressStatus.DONE
            # Submissionテーブルのmessageにエラー文を追加
            self.submission_record.message = f"Error on Problem {self.lecture_id}-{self.assignment_id}:{self.for_evaluation}: Not found"
            update_submission_record(db=db, submission_record=self.submission_record)
            db.close()
            raise ValueError(self.submission_record.message)
        else:
            self.problem_record = problem_record
        
        test_logger.info(f"JudgeInfo.__init__: problem_record: {self.problem_record}")

        # Get required file names
        self.required_files = fetch_required_files(
            db=db,
            lecture_id=self.submission_record.lecture_id,
            assignment_id=self.submission_record.assignment_id,
            for_evaluation=self.submission_record.for_evaluation,
        )
        
        test_logger.info(f"JudgeInfo.__init__: required_files: {self.required_files}")

        # Get arranged filepaths
        self.arranged_filepaths = [
            RESOURCE_DIR / filepath
            for filepath in fetch_arranged_filepaths(
                db=db,
                lecture_id=self.submission_record.lecture_id,
                assignment_id=self.submission_record.assignment_id,
                for_evaluation=self.submission_record.for_evaluation,
            )
        ]
        
        test_logger.info(f"JudgeInfo.__init__: required_files: {self.required_files}")

        # Get uploaded filepaths
        self.uploaded_filepaths = [
            RESOURCE_DIR / filepath
            for filepath in fetch_uploaded_filepaths(db=db, submission_id=self.submission_record.id)
        ]
        
        test_logger.info(f"JudgeInfo.__init__: uploaded_filepaths: {self.uploaded_filepaths}")

        # Get testcases info
        testcases = fetch_testcases(
            db=db,
            lecture_id=self.submission_record.lecture_id,
            assignment_id=self.submission_record.assignment_id,
            for_evaluation=self.submission_record.for_evaluation,
        )

        self.prebuilt_testcases = []
        self.postbuilt_testcases = []
        self.judge_testcases = []

        # prebuilt, postbuilt, judgeの種類ごとにtestcasesを分ける
        for testcase in testcases:
            if testcase.type == TestCaseType.preBuilt:
                self.prebuilt_testcases.append(testcase)
            elif testcase.type == TestCaseType.postBuilt:
                self.postbuilt_testcases.append(testcase)
            else: # testcase.type == TestCaseType.Judge
                self.judge_testcases.append(testcase)

        self.entire_status = JudgeSummaryStatusAggregator(JudgeSummaryStatus.AC)
        db.close()

    def _create_complete_volume(self) -> tuple[Volume, Error]:
        docker_volume, err = Volume.create()
        if not err.silence():
            return (Volume(""), Error(f"cannot create volume: {docker_volume.name}"))

        # copy uploaded files and arranged files to volume
        err = docker_volume.copyFiles(self.uploaded_filepaths + self.arranged_filepaths)
        if not err.silence():
            return (
                Volume(""),
                Error(f"failed to copy uploaded files to volume: {docker_volume.name}"),
            )

        return (docker_volume, Error.Nothing())

    def _result_check_and_register(
        self,
        db: Session,
        testcase: TestCaseRecord,
        result: TaskResult,
        expected_stdout: str,
        expected_stderr: str,
    ) -> JudgeSummaryStatus:
        judge_result_record = JudgeResultRecord(
            submission_id=self.submission_record.id,
            testcase_id=testcase.id,
            timeMS=result.timeMS,
            memoryKB=result.memoryByte / 1024,
            exit_code=result.exitCode,
            stdout=result.stdout,
            stderr=result.stderr,
            result=SingleJudgeStatus.AC
        )
        # TLEチェック
        if result.TLE:
            judge_result_record.result=SingleJudgeStatus.TLE
        # MLEチェック
        elif result.memoryByte + 1024 * 1024 > 512 * 1024 * 1024:
            judge_result_record.result=SingleJudgeStatus.MLE
        # RE(Runtime Errorチェック)
        elif result.exitCode != testcase.exit_code:
            judge_result_record.result=SingleJudgeStatus.RE
        # Wrong Answerチェック
        elif not StandardChecker.match(
            expected_stdout, result.stdout
        ) or not StandardChecker.match(expected_stderr, result.stderr):
            judge_result_record.result=SingleJudgeStatus.WA
        else:
        # AC(正解)として登録
            judge_result_record.result=SingleJudgeStatus.AC
        register_judge_result(
            db=db,
            result=judge_result_record
        )
        return JudgeSummaryStatus(judge_result_record.result.value)
            
    def _exec_checker(self, testcase_list: list[TestCaseRecord], initial_volume: Volume, container_name: str, timeoutSec: float, memoryLimitMB: int) -> JudgeSummaryStatus:
        db = SessionLocal()
        status_aggregator: JudgeSummaryStatusAggregator = JudgeSummaryStatusAggregator(JudgeSummaryStatus.AC)
        for testcase in testcase_list:
            # ボリューム作成
            volume, err = initial_volume.clone()
            if not err.silence():
                register_judge_result(
                    db=db,
                    result=JudgeResultRecord(
                        submission_id=self.submission_record.id,
                        testcase_id=testcase.id,
                        timeMS=0,
                        memoryKB=0,
                        exit_code=-1,
                        stdout='',
                        stderr=err.message,
                        result=SingleJudgeStatus.IE
                    )
                )
                status_aggregator.update(JudgeSummaryStatus.IE)
                continue
            
            args = []
            
            # スクリプトが要求されるならそれをボリュームにコピー
            if testcase.script_path is not None:
                err = volume.copyFile(
                    RESOURCE_DIR / testcase.script_path,
                    Path("./") / Path(testcase.script_path).name
                )
                if not err.silence():
                    test_logger.info(f"err occured when copying script file: {err}")
                    register_judge_result(
                        db=db,
                        result=JudgeResultRecord(
                            submission_id=self.submission_record.id,
                            testcase_id=testcase.id,
                            timeMS=0,
                            memoryKB=0,
                            exit_code=-1,
                            stdout='',
                            stderr=err.message,
                            result=SingleJudgeStatus.IE
                        )
                    )
                    status_aggregator.update(JudgeSummaryStatus.IE)
                    continue
                args = [f"./{Path(testcase.script_path).name}"]
            else:
                # そうでないなら通常のexecutableをargsに追加
                args = [f"./{self.problem_record.executable}"]
            
            stdin: str = ""
            expected_stdout: str = ""
            expected_stderr: str = ""
            
            try:
                # 引数をargに追加する
                if testcase.argument_path is not None:
                    with open(RESOURCE_DIR / testcase.argument_path, "r", encoding='utf-8') as f:
                        arguments = f.read().strip().split()
                        args.extend(arguments)
                    
                # stdin, expected_stdout, expected_stderrを読み込む
                if testcase.stdin_path is not None:
                    with open(
                        RESOURCE_DIR / testcase.stdin_path, "r", encoding="utf-8"
                    ) as f:
                        stdin = f.read()
                else:
                    stdin = ""

                with open(
                    RESOURCE_DIR / testcase.stdout_path, "r", encoding="utf-8"
                ) as f:
                    expected_stdout = f.read()

                with open(
                    RESOURCE_DIR / testcase.stderr_path, "r", encoding="utf-8"
                ) as f:
                    expected_stderr = f.read()
        
            except FileNotFoundError as e:
                register_judge_result(
                    db=db,
                    result=JudgeResultRecord(
                        submission_id=self.submission_record.id,
                        testcase_id=testcase.id,
                        timeMS=0,
                        memoryKB=0,
                        exit_code=-1,
                        stdout='',
                        stderr=err.message,
                        result=SingleJudgeStatus.IE
                    )
                )
                status_aggregator.update(JudgeSummaryStatus.IE)
                # ボリュームを削除
                err = volume.remove()
                if not err.silence():
                    test_logger.info(f"failed to remove volume: {volume.name}")
                continue
            
            # sandbox環境のセットアップ
            task = TaskInfo(
                name=container_name,
                arguments=args,
                workDir="/workdir/",
                volumeMountInfo=[VolumeMountInfo(path="/workdir/", volume=volume)],
                timeoutSec=timeoutSec,
                memoryLimitMB=memoryLimitMB,
                Stdin=stdin,
            )

            # sandbox環境で実行
            result, err = task.run()

            status = self._result_check_and_register(
                db=db,
                testcase=testcase,
                result=result,
                expected_stdout=expected_stdout,
                expected_stderr=expected_stderr,
            )
            
            # ボリュームを削除
            err = volume.remove()
            if not err.silence():
                test_logger.info(f"failed to remove volume: {volume.name}")
            
            status_aggregator.update(status)
        
        db.close()
        return status_aggregator.flag

    def _compile(self, working_volume: Volume, container_name: str) -> Error:
        # コンパイルコマンドの取得
        args = []
        try:
            with open(RESOURCE_DIR / self.problem_record.build_script_path, mode='r', encoding='utf-8') as f:
                compile_command = f.read().strip().split()
                args.extend(compile_command)
        except FileNotFoundError:
            return Error(f"script for compile commands not found: {self.problem_record.build_script_path}")
    
        # sandbox環境のセットアップ
        task = TaskInfo(
            name=container_name,
            arguments=args,
            workDir="/workdir/",
            volumeMountInfo=[VolumeMountInfo(path="/workdir/", volume=working_volume)],
            timeoutSec=2.0,
            memoryLimitMB=512
        )
        
        # sandbox環境で実行
        result, err = task.run()
        
        if not err.silence():
            return Error(f"compile failed: {result.stderr}")
        
        return Error.Nothing()

    def judge(self) -> Error:

        # 1. コンパイル前のチェックを行う
        # required_files, arranged_filesが入ったボリュームを作る
        working_volume, err = self._create_complete_volume()
        if not err.silence():
            return err
        # チェッカーを走らせる
        prebuilt_result = self._exec_checker(testcase_list=self.prebuilt_testcases, initial_volume=working_volume, container_name="binary-runner", timeoutSec=2.0, memoryLimitMB=512)
        if prebuilt_result is not JudgeSummaryStatus.AC:
            # 早期終了
            db = SessionLocal()
            self.submission_record.progress = SubmissionProgressStatus.DONE
            self.submission_record.prebuilt_result = prebuilt_result
            update_submission_record(db=db, submission_record=self.submission_record)
            db.close()
            return Error.Nothing()
        else:
            self.submission_record.prebuilt_result = JudgeSummaryStatus.AC
        
        # 2. コンパイルを行う
        err = self._compile(working_volume=working_volume, container_name="checker-lang-gcc")
        
        if not err.silence():
            # 早期終了
            db = SessionLocal()
            self.submission_record.progress = SubmissionProgressStatus.DONE
            self.submission_record.postbuilt_result = JudgeSummaryStatus.CE
            update_submission_record(db=db, submission_record=self.submission_record)
            db.close()
            return Error.Nothing()
        
        # 3. コンパイル後のチェックを行う
        # チェッカーを走らせる
        postbuilt_result = self._exec_checker(testcase_list=self.postbuilt_testcases, initial_volume=working_volume, container_name="checker-lang-gcc", timeoutSec=2.0, memoryLimitMB=512)
        if postbuilt_result is not JudgeSummaryStatus.AC:
            # 早期終了
            db = SessionLocal()
            self.submission_record.progress = SubmissionProgressStatus.DONE
            self.submission_record.postbuilt_result = postbuilt_result
            update_submission_record(db=db, submission_record=self.submission_record)
            db.close()
            return Error.Nothing()
        else:
            self.submission_record.postbuilt_result = JudgeSummaryStatus.AC
        
        # 4. ジャッジを行う
        # チェッカーを走らせる
        judge_result = self._exec_checker(testcase_list=self.judge_testcases, initial_volume=working_volume, container_name="binary-runner", timeoutSec=self.problem_record.timeMS / 1000.0, memoryLimitMB=self.problem_record.memoryMB)
        
        # ボリュームを削除
        err = working_volume.remove()
        if not err.silence():
            test_logger.info(f"failed to remove volume: {working_volume.name}")
        
        # ジャッジ結果を登録
        db = SessionLocal()
        self.submission_record.progress = SubmissionProgressStatus.DONE
        self.submission_record.judge_result = judge_result
        update_submission_record(db=db, submission_record=self.submission_record)
        db.close()
        return Error.Nothing()
