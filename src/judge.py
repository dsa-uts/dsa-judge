from pathlib import Path
from sandbox.execute import Volume
from sandbox.my_error import Error
from sandbox.execute import TaskInfo
from sandbox.execute import VolumeMountInfo
from dotenv import load_dotenv
from db import records, crud
from db.database import SessionLocal
from checker import StandardChecker
import os

# ロガーの設定
from log.config import judge_logger

load_dotenv()

RESOURCE_DIR = Path(os.getenv("RESOURCE_PATH"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR_PATH"))

class JudgeInfo:
    submission_record: records.Submission # Submissionテーブル内のジャッジリクエストレコード

    problem_record: records.Problem # Problemテーブル内のテーブルレコード

    def __init__(
        self,
        submission: records.Submission
    ):
        self.submission_record = submission

        with SessionLocal() as db:
            
            # self.submission_record.uploaded_filesは自動で取得しないので、
            # ここで取得する    
            self.submission_record.uploaded_files = crud.fetch_uploaded_files(db=db, submission_id=self.submission_record.id)

            problem_record = crud.fetch_problem(
                db=db,
                lecture_id=self.submission_record.lecture_id,
                assignment_id=self.submission_record.assignment_id,
                eval=self.submission_record.eval
            )

            if problem_record is None:
                # Submissionテーブルのstatusをdoneに変更
                self.submission_record.progress = records.SubmissionProgressStatus.DONE
                message = f"Error on Problem {self.submission_record.lecture_id}-{self.submission_record.assignment_id}:{self.submission_record.for_evaluation}: Not found"
                detail = ""
                # SubmissionSummaryレコードを作成
                submission_summary = records.SubmissionSummary(
                    submission_id=self.submission_record.id,
                    batch_id=self.submission_record.batch_id,
                    user_id=self.submission_record.user_id,
                    result=records.SubmissionSummaryStatus.IE,
                    message=message,
                    detail=detail,
                    score=0
                )

                crud.register_submission_summary_recursive(db=db, submission_summary=submission_summary)
                crud.update_submission_record(db=db, submission_record=self.submission_record)
                raise ValueError(message)
            else:
                self.problem_record = problem_record

            judge_logger.debug(f"JudgeInfo.__init__: problem_record: {self.problem_record}")

    def _create_complete_volume(self) -> tuple[Volume, Error]:
        docker_volume, err = Volume.create()
        if not err.silence():
            return (Volume(""), Error(f"cannot create volume: {docker_volume.name}"))

        uploaded_filepaths = [UPLOAD_DIR / file.path for file in self.submission_record.uploaded_files]

        arranged_filepaths = [RESOURCE_DIR / file.path for file in self.problem_record.arranged_files]

        # copy uploaded files and arranged files to volume
        err = docker_volume.copyFiles(uploaded_filepaths + arranged_filepaths)
        if not err.silence():
            return (
                Volume(""),
                Error(f"failed to copy uploaded files to volume: {docker_volume.name}"),
            )

        return (docker_volume, Error.Nothing())

    def _update_progress_of_submission(self, completed_task: int) -> None:
        self.submission_record.completed_task = completed_task
        with SessionLocal() as db:
            crud.update_submission_record(db=db, submission_record=self.submission_record)

    def _exec_built_task(
        self,
        working_volume: Volume,
        testcase_list: list[records.TestCases],
        container_name: str,
    ) -> list[records.JudgeResult]:
        judge_result_list: list[records.JudgeResult] = []
        for testcase in testcase_list:
            # 実行コマンド + 引数
            args = []

            # コマンドを追加
            args += testcase.command.strip().split()

            if testcase.args is not None:
                args += testcase.args.strip().split()

            # NOTE) コンパイル時は、標準入力は受け付けないものとする。

            # sandbox環境のセットアップ
            sandbox_task = TaskInfo(
                name=container_name,
                arguments=args,
                workDir="/workdir/",
                volumeMountInfoList=[VolumeMountInfo(path="/workdir/", volume=working_volume, read_only=False)],
                timeoutSec=2.0,
                memoryLimitMB=512
            )

            # sandbox環境で実行
            result, err = sandbox_task.run()

            judge_result = records.JudgeResult(
                        submission_id=self.submission_record.id,
                        testcase_id=testcase.id,
                        result=records.SingleJudgeStatus.AC,
                        timeMS=result.timeMS,
                        memoryKB=result.memoryByte / 1024,
                        exit_code=result.exitCode,
                        stdout=result.stdout,
                        stderr=result.stderr
                    )

            # 進捗状況を更新
            self._update_progress_of_submission(
                completed_task=self.submission_record.completed_task + 1
            )

            if not err.silence():
                # 内部エラーにより失敗
                judge_result.result = records.SingleJudgeStatus.IE
                judge_result_list.append(judge_result)
                return judge_result_list

            # NOTE: ビルドの際は、標準出力、標準エラー出力の確認はせず、戻り値のみの確認とする。
            # それは、Makefileによるビルドログの出力まで一致確認するのは厳格すぎるから。

            # コンパイルエラーかチェック
            if result.exitCode != 0:
                judge_result.result = records.SingleJudgeStatus.CE

            # TestCaseで設定されていたコンパイルジョブが正常に実行完了した
            # judge_result_listに追加
            judge_result_list.append(judge_result)

        # 全部のビルドが終了した
        return judge_result_list

    def _exec_judge_task(self, working_volume: Volume, testcase_list: list[records.TestCases], container_name: str) -> list[records.JudgeResult]:
        judge_result_list: list[records.JudgeResultRecord] = []
        for testcase in testcase_list:
            # 実行コマンド + 引数
            args = []

            # コマンド、引数追加
            args += testcase.command.strip().split()

            if testcase.args is not None:
                args += testcase.args.strip().split()

            # 標準入力、想定される標準出力・標準エラー出力の取得
            stdin = None
            expected_stdout = None
            expected_stderr = None
            expected_exit_code = testcase.exit_code

            if testcase.stdin_path is not None:
                with open(RESOURCE_DIR / Path(testcase.stdin_path), mode='r', encoding='utf-8') as f:
                    stdin = f.read()

            if testcase.stdout_path is not None:
                with open(RESOURCE_DIR / Path(testcase.stdout_path), mode='r', encoding='utf-8') as f:
                    expected_stdout = f.read()

            if testcase.stderr_path is not None:
                with open(RESOURCE_DIR / Path(testcase.stderr_path), mode='r', encoding='utf-8') as f:
                    expected_stderr = f.read()

            # sandbox環境のセットアップ
            sandbox_task = TaskInfo(
                name=container_name,
                arguments=args,
                workDir="/workdir/",
                volumeMountInfoList=[VolumeMountInfo(path="/workdir/", volume=working_volume, read_only=True)],
                timeoutSec=self.problem_record.timeMS / 1000,
                memoryLimitMB=self.problem_record.memoryMB
            )

            # 標準入力をセット
            if stdin is not None:
                sandbox_task.Stdin = stdin

            # sandbox環境で実行
            result, err = sandbox_task.run()

            judge_result = records.JudgeResult(
                        submission_id=self.submission_record.id,
                        testcase_id=testcase.id,
                        result=records.SingleJudgeStatus.AC,
                        timeMS=result.timeMS,
                        memoryKB=result.memoryByte / 1024,
                        exit_code=result.exitCode,
                        stdout=result.stdout,
                        stderr=result.stderr
                    )

            # 進捗状況を更新
            self._update_progress_of_submission(
                completed_task=self.submission_record.completed_task + 1
            )

            if not err.silence():
                judge_logger.critical(f"Internal error while executing sandbox: {err.message}")
                # 内部エラーにより失敗
                # 内部エラーの場合は、即座に終了する
                judge_result.result = records.SingleJudgeStatus.IE
                judge_result_list.append(judge_result)
                return judge_result_list

            # TLEチェック
            if result.TLE:
                judge_result.result = records.SingleJudgeStatus.TLE
            # MLEチェック
            elif result.memoryByte + 1024 * 1024 > self.problem_record.memoryMB * 1024 * 1024:
                judge_result.result = records.SingleJudgeStatus.MLE
            # RE(Runtime Errorチェック)
            elif result.exitCode != expected_exit_code:
                judge_result.result = records.SingleJudgeStatus.RE
            # Wrong Answerチェック
            elif not (
                expected_stdout is not None
                and StandardChecker.match(expected_stdout, result.stdout)
            ) or not (
                expected_stderr is not None
                and StandardChecker.match(expected_stderr, result.stderr)
            ):
                judge_result.result = records.SingleJudgeStatus.WA
            else:
                # AC(正解)
                judge_result.result= records.SingleJudgeStatus.AC

            # TestCaseで設定されていたジョブが正常に実行完了した
            # judge_result_listに追加
            judge_result_list.append(judge_result)

        return judge_result_list

    def _closing_procedure(self, submission_summary: records.SubmissionSummary, working_volume: Volume | None) -> Error:
        # SubmissionSummaryレコードを登録し、submission.progress = 'Done'にする。
        with SessionLocal() as db:
            crud.register_submission_summary_recursive(
                db=db,
                submission_summary=submission_summary
            )
            self.submission_record.progress = records.SubmissionProgressStatus.DONE
            crud.update_submission_record(
                db=db,
                submission_record=self.submission_record
            )
        if working_volume is not None:
            # ボリュームの削除
            err = working_volume.remove()
            if not err.silence():
                judge_logger.error(f"failed to remove volume: {working_volume.name}")
                return err

        return Error.Nothing()

    def judge(self) -> Error:
        # testcase_id(key) -> TestCaseのdict
        testcase_dict: dict[int, records.TestCases] = {}
        for testcase in self.problem_record.test_cases:
            testcase_dict[testcase.id] = testcase
        
        
        submission_summary_record = records.SubmissionSummary(
            submission_id=self.submission_record.id,
            batch_id=self.submission_record.batch_id,
            user_id=self.submission_record.user_id,
            result=records.SubmissionSummaryStatus.AC, # 仮
            message="", # 仮
            detail="", # 仮
            score=0, # 仮
            timeMS=0, # 仮
            memoryKB=0, # 仮
        )

        # 1. ビルド前チェックを行う
        # アップロードされたファイルの中に、要求されているファイルが含まれているかチェックする。
        # 注)このとき、他のファイルが含まれていても良しとする(現状の判断では)
        uploaded_filename = [Path(file_path.path).name for file_path in self.submission_record.uploaded_files]
        required_filename = [required_file.name for required_file in self.problem_record.required_files]

        # self.problem_record.required_filesの内容がuploaded_filenameに完全に含まれているか調べる
        missing_files = set(required_filename) - set(uploaded_filename)
        if missing_files:
            # ファイルが見つからなかったことをDBに登録して、早期終了
            submission_summary_record.result = records.SubmissionSummaryStatus.FN
            submission_summary_record.message = "ファイルが存在しません"
            submission_summary_record.detail = f"{' '.join(missing_files)}"
            submission_summary_record.score = 0
            return self._closing_procedure(
                submission_summary=submission_summary_record,
                working_volume=None
            )

        # 2. 準備
        # required_files, arranged_filesが入ったボリュームを作る
        working_volume, err = self._create_complete_volume()
        if not err.silence():
            submission_summary_record.result = records.SubmissionSummaryStatus.IE
            submission_summary_record.message = "error when executing sandbox"
            submission_summary_record.detail = err.message
            submission_summary_record.score = 0
            return self._closing_procedure(
                submission_summary=submission_summary_record,
                working_volume=working_volume
            )

        submission_summary_record.judge_results = []

        # 3. Builtテストケース(コンパイル)を実行する
        built_task_list = [task for task in self.problem_record.test_cases if task.type == records.EvaluationType.Built]
        build_exec_result_list = self._exec_built_task(
            working_volume=working_volume,
            testcase_list=built_task_list,
            container_name="checker-lang-gcc"
        )
        submission_summary_record.judge_results += build_exec_result_list
        
        # ジャッジ結果の集約
        for exec_result in build_exec_result_list:
            submission_summary_record.timeMS = max(submission_summary_record.timeMS, exec_result.timeMS)
            submission_summary_record.memoryKB = max(submission_summary_record.memoryKB, exec_result.memoryKB)
            submission_summary_record.score += testcase_dict[exec_result.testcase_id].score if exec_result.result == records.SingleJudgeStatus.AC else 0
            submission_summary_record.result = max(submission_summary_record.result, records.SubmissionSummaryStatus[exec_result.result.value])
            
            if exec_result.result != records.SingleJudgeStatus.AC:
                corresponding_testcase = testcase_dict[exec_result.testcase_id]
                submission_summary_record.detail += f"{corresponding_testcase.message_on_fail}: {exec_result.result.value} (-{corresponding_testcase.score})\n"
            
        if submission_summary_record.result != records.SubmissionSummaryStatus.AC:
            submission_summary_record.message += "ビルドに失敗しました\n"
            return self._closing_procedure(
                submission_summary=submission_summary_record,
                working_volume=working_volume
            )

        # 4. 必要な実行ファイルが生成されているか調べる
        executable_list = [executable.name for executable in self.problem_record.executables]

        # Volume内でどのようなファイルが生成されたか調べる
        sandbox_env = TaskInfo(
            name="binary-runner", 
            arguments=["ls", "-p"],
            workDir="/workdir/",
            volumeMountInfoList=[VolumeMountInfo(path="/workdir/", volume=working_volume, read_only=True)]
        )
        result, err = sandbox_env.run()

        if not err.silence():
            submission_summary_record.result = records.SubmissionSummaryStatus.IE
            submission_summary_record.message += "error when executing sandbox: ls -lp\n"
            submission_summary_record.detail += f"{err.message}\n"
            return self._closing_procedure(
                submission_summary=submission_summary_record,
                working_volume=working_volume
            )

        all_files_in_sandbox = [file for file in result.stdout.strip().split()]

        # all_files_in_sandboxの中に、executable_listの要素が全部含まれているか調べる。
        # 含まれていないものがあれば、それをnot_found_listで表す。
        not_found_executable_set = set(executable_list) - set(all_files_in_sandbox)
        if not_found_executable_set:
            # 必要な実行バイナリが見つからなかったことをDBに登録して、早期終了
            submission_summary_record.result = records.SubmissionSummaryStatus.CE
            submission_summary_record.message += "実行ファイルが出力されていません\n"
            submission_summary_record.detail += f"{' '.join(not_found_executable_set)}\n"
            # submission_summary_record.score = (total sum)
            return self._closing_procedure(
                submission_summary=submission_summary_record,
                working_volume=working_volume
            )

        # Judgeテストケース(実行・チェック)を実行する
        judge_task_list = [task for task in self.problem_record.test_cases if task.type == records.EvaluationType.Judge]
        judge_exec_result_list = self._exec_judge_task(
            working_volume=working_volume,
            testcase_list=judge_task_list,
            container_name="binary-runner"
        )
        submission_summary_record.judge_results += judge_exec_result_list
        
        for exec_result in judge_exec_result_list:
            submission_summary_record.timeMS = max(submission_summary_record.timeMS, exec_result.timeMS)
            submission_summary_record.memoryKB = max(submission_summary_record.memoryKB, exec_result.memoryKB)
            submission_summary_record.score += testcase_dict[exec_result.testcase_id].score if exec_result.result == records.SingleJudgeStatus.AC else 0
            
            if exec_result.result != records.SingleJudgeStatus.AC:
                corresponding_testcase = testcase_dict[exec_result.testcase_id]
                submission_summary_record.detail += f"{corresponding_testcase.message_on_fail}: {exec_result.result.value} (-{corresponding_testcase.score})\n"

        # 全体の結果を登録
        return self._closing_procedure(
            submission_summary=submission_summary_record,
            working_volume=working_volume
        )
