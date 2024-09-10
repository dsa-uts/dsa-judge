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

# ロガーの設定
from log.config import judge_logger

load_dotenv()

RESOURCE_DIR = Path(os.getenv("RESOURCE_PATH"))

class JudgeInfo:
    submission_record: SubmissionRecord # Submissionテーブル内のジャッジリクエストレコード

    problem_record: ProblemRecord  # Problemテーブル内のテーブルレコード

    # ユーザに提出を求められているソースコードの名前リスト
    required_files: list[str]
    # こちらが用意しているソースコードのファイルパスの辞書
    arranged_filepath_dict: dict[str, Path]
    uploaded_filepaths: list[Path]  # ユーザが提出したソースコードのファイルパスのリスト

    executable_list: list[str] # ビルド・実行される実行ファイル名リスト

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

        judge_logger.debug(f"JudgeInfo.__init__: problem_record: {self.problem_record}")

        # Get required file names
        self.required_files = fetch_required_files(
            db=db,
            lecture_id=self.submission_record.lecture_id,
            assignment_id=self.submission_record.assignment_id,
            for_evaluation=self.submission_record.for_evaluation,
        )

        judge_logger.debug(f"JudgeInfo.__init__: required_files: {self.required_files}")

        # Get arranged filepaths (The dictionary from str_id -> Path)
        self.arranged_filepath_dict = {
            str_id: RESOURCE_DIR / filepath
            for str_id, filepath in fetch_arranged_filepaths(
                db=db,
                lecture_id=self.submission_record.lecture_id,
                assignment_id=self.submission_record.assignment_id,
                for_evaluation=self.submission_record.for_evaluation,
            )
        }

        judge_logger.debug(f"JudgeInfo.__init__: required_files: {self.required_files}")

        # Get uploaded filepaths
        self.uploaded_filepaths = [
            RESOURCE_DIR / filepath
            for filepath in fetch_uploaded_filepaths(db=db, submission_id=self.submission_record.id)
        ]

        judge_logger.debug(f"JudgeInfo.__init__: uploaded_filepaths: {self.uploaded_filepaths}")

        # Get executable names
        self.executable_list = fetch_executables(
            db=db,
            lecture_id=self.submission_record.lecture_id,
            assignment_id=self.submission_record.assignment_id,
            for_evaluation=self.submission_record.for_evaluation,
        )
        
        judge_logger.debug(f"JudgeInfo.__init__: executables: {self.executable_list}")

        db.close()

    def _create_complete_volume(self) -> tuple[Volume, Error]:
        docker_volume, err = Volume.create()
        if not err.silence():
            return (Volume(""), Error(f"cannot create volume: {docker_volume.name}"))

        # copy uploaded files and arranged files to volume
        err = docker_volume.copyFiles(self.uploaded_filepaths + list(self.arranged_filepath_dict.values()))
        if not err.silence():
            return (
                Volume(""),
                Error(f"failed to copy uploaded files to volume: {docker_volume.name}"),
            )

        return (docker_volume, Error.Nothing())

    def _evaluation_summary(self, task: EvaluationItemRecord, result: EvaluationSummaryStatus, message: str, detail: str, score: int, arranged_file_path: str | None,  judge_result_list: list[JudgeResultRecord] = []) -> EvaluationSummaryRecord:
        return EvaluationSummaryRecord(
            submission_id=self.submission_record.id,
            batch_id=self.submission_record.batch_id,
            user_id=self.submission_record.user_id,
            lecture_id=self.submission_record.lecture_id,
            assignment_id=self.submission_record.assignment_id,
            for_evaluation=self.submission_record.for_evaluation,
            eval_id=task.str_id,
            arranged_file_id=task.arranged_file_id,
            result=result,
            message=message,
            detail=detail,
            score=score,
            eval_title=task.title,
            eval_description=task.description,
            eval_type=task.type,
            arranged_file_path=arranged_file_path,
            # id=(テーブル挿入時に自動で割り当てられる),
            judge_result_list=judge_result_list
        )
    
    def _exec_built_task(self, working_volume: Volume, built_task: EvaluationItemRecord, container_name: str) -> EvaluationSummaryRecord:
        # 紐づいているソースコードのpathを取得
        arranged_file_path = None
        if built_task.arranged_file_id is not None:
            arranged_file_path = self.arranged_filepath_dict[built_task.arranged_file_id]
            
        judge_result_list: list[JudgeResultRecord] = []
        for testcase in built_task.testcase_list:
            # 実行コマンド + 引数
            args = []
            
            # コマンドを追加
            args += testcase.command.strip().split()
            
            if testcase.argument_path is not None:
                try:
                    # 引数ファイルの内容をargsに追加
                    with open(RESOURCE_DIR / Path(testcase.argument_path), mode='r', encoding='utf-8') as f:
                        argument_list = f.read().strip().split()
                        args += argument_list
                except FileNotFoundError:
                    return self._evaluation_summary(task=built_task,
                                result=EvaluationSummaryStatus.IE,
                                message="argument file not found",
                                detail=f"{testcase.argument_path}",
                                score=0,
                                arranged_file_path=arranged_file_path)
            
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
            
            if not err.silence():
                # 内部エラーにより失敗
                return self._evaluation_summary(task=built_task,
                                result=EvaluationSummaryStatus.IE,
                                message="Internal error while executing sandbox",
                                detail=err,
                                score=0,
                                arranged_file_path=arranged_file_path,
                                judge_result_list=judge_result_list)
            
            # NOTE: ビルドの際は、標準出力、標準エラー出力の確認はせず、戻り値のみの確認とする。
            # それは、Makefileによるビルドログの出力まで一致確認するのは厳格すぎるから。
            
            judge_result = JudgeResultRecord(
                        submission_id=self.submission_record.id,
                        testcase_id=testcase.id,
                        result=SingleJudgeStatus.AC,
                        timeMS=result.timeMS,
                        memoryKB=result.memoryByte / 1024,
                        exit_code=result.exitCode,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        description=testcase.description,
                        command=" ".join(args),
                        stdin=None,
                        expected_stdout=None,
                        expected_stderr=None,
                        expected_exit_code=testcase.exit_code
                    )
            
            # コンパイルエラーかチェック
            if result.exitCode != testcase.exit_code:
                # コンパイルエラー
                judge_result.result = SingleJudgeStatus.WA
                judge_result_list.append(judge_result)
                return self._evaluation_summary(task=built_task,
                                result=EvaluationSummaryStatus.CE,
                                message=f"Compile error when executing {" ".join(args)}",
                                detail=result.stderr,
                                score=0,
                                arranged_file_path=arranged_file_path)
                
            # TestCaseで設定されていたコンパイルジョブが正常に実行完了した
            # judge_result_listに追加
            judge_result.result = SingleJudgeStatus.AC
            judge_result_list.append(judge_result)
            
        # 全部のビルドが正常終了した
        return self._evaluation_summary(
            task=built_task,
            result=EvaluationSummaryStatus.AC,
            message=f"Compile Success",
            detail="",
            score=built_task.score,
            arranged_file_path=arranged_file_path,
            judge_result_list=judge_result_list
        )
                
    def _exec_judge_task(self, working_volume: Volume, judge_task: EvaluationItemRecord, container_name: str) -> EvaluationSummaryRecord:
        # 紐づいているソースコードのpathを取得
        arranged_file_path = None
        if judge_task.arranged_file_id is not None:
            arranged_file_path = self.arranged_filepath_dict[judge_task.arranged_file_id]
            
        judge_result_list: list[JudgeResultRecord] = []
        for testcase in judge_task.testcase_list:
            # 実行コマンド + 引数
            args = []
            
            # コマンド、引数追加
            args += testcase.command.strip().split()

            if testcase.argument_path is not None:
                try:
                    # 引数ファイルの内容をargsに追加
                    with open(RESOURCE_DIR / Path(testcase.argument_path), mode='r', encoding='utf-8') as f:
                        argument_list = f.read().strip().split()
                        args += argument_list
                except FileNotFoundError:
                    return self._evaluation_summary(
                                task=judge_task,
                                result=EvaluationSummaryStatus.IE,
                                message="argument file not found",
                                detail=f"{testcase.argument_path}",
                                score=0,
                                arranged_file_path=arranged_file_path
                            )
            
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
            
            if not err.silence():
                # 内部エラーにより失敗
                return self._evaluation_summary(task=judge_task,
                                result=EvaluationSummaryStatus.IE,
                                message="Internal error while executing sandbox",
                                detail=err,
                                score=0,
                                arranged_file_path=arranged_file_path,
                                judge_result_list=judge_result_list)

            judge_result = JudgeResultRecord(
                        submission_id=self.submission_record.id,
                        testcase_id=testcase.id,
                        result=SingleJudgeStatus.AC,
                        timeMS=result.timeMS,
                        memoryKB=result.memoryByte / 1024,
                        exit_code=result.exitCode,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        description=testcase.description,
                        command=" ".join(args),
                        stdin=stdin,
                        expected_stdout=expected_stdout,
                        expected_stderr=expected_stderr,
                        expected_exit_code=testcase.exit_code
                    )
            
            # TLEチェック
            if result.TLE:
                judge_result.result = SingleJudgeStatus.TLE
            # MLEチェック
            elif result.memoryByte + 1024 * 1024 > self.problem_record.memoryMB * 1024 * 1024:
                judge_result.result = SingleJudgeStatus.MLE
            # RE(Runtime Errorチェック)
            elif result.exitCode != expected_exit_code:
                judge_result.result = SingleJudgeStatus.RE
            # Wrong Answerチェック
            elif not StandardChecker.match(
                expected_stdout, result.stdout
            ) or not StandardChecker.match(expected_stderr, result.stderr):
                judge_result.result = SingleJudgeStatus.WA
            else:
            # AC(正解)
                judge_result.result= SingleJudgeStatus.AC
            
            # TestCaseで設定されていたジョブが正常の実行完了した
            # judge_result_listに追加
            judge_result_list.append(judge_result)
        
        # 全部のジャッジが正常に終了した
        # judge_result_listの中の結果を集計
        # judge_result_listの中で最も厳しい結果を取得
        worst_result = max(judge_result.result for judge_result in judge_result_list)
        
        # SingleJudgeStatus -> EvaluationSummaryStatusに変換
        worst_result = EvaluationSummaryStatus[worst_result.name]
        
        # スコア計算
        score = judge_task.score if worst_result == EvaluationSummaryStatus.AC else 0

        # 結果メッセージを生成
        message = f"Judge completed. Result: {worst_result.name}"
        
        detail = ""

        return self._evaluation_summary(
            task=judge_task,
            result=worst_result,
            message=message,
            detail=detail,
            score=score,
            arranged_file_path=arranged_file_path,
            judge_result_list=judge_result_list
        )
    
    def _closing_procedure(self, submission_summary: SubmissionSummaryRecord, working_volume: Volume) -> Error:
        # SubmissionSummaryレコードを登録し、submission.progress = 'Done'にする。
        with SessionLocal() as db:
            register_submission_summary_recursive(
                db=db,
                submission_summary=submission_summary
            )
            self.submission_record.progress = SubmissionProgressStatus.DONE
            update_submission_record(
                db=db,
                submission_record=self.submission_record
            )
        # ボリュームの削除
        err = working_volume.remove()
        if not err.silence():
            judge_logger.error(f"failed to remove volume: {working_volume.name}")
        
        return err
    

    def judge(self) -> Error:
        submission_summary_record = SubmissionSummaryRecord(
            submission_id=self.submission_record.id,
            batch_id=self.submission_record.batch_id,
            user_id=self.submission_record.user_id,
            lecture_id=self.submission_record.lecture_id,
            assignment_id=self.submission_record.assignment_id,
            for_evaluation=self.submission_record.for_evaluation,
            result=SubmissionSummaryStatus.AC, # 仮
            message="", # 仮
            detail="", # 仮
            score=0, # 仮
            evaluation_summary_list=[] #仮
        )
        

        # 1. ビルド前チェックを行う
        # アップロードされたファイルの中に、要求されているファイルが含まれているかチェックする。
        # 注)このとき、他のファイルが含まれていても良しとする(現状の判断では)
        uploaded_filename = [file_path.name for file_path in self.uploaded_filepaths]
        
        # self.required_filesの内容がuploaded_filenameに完全に含まれているか調べる
        missing_files = set(self.required_files) - set(uploaded_filename)
        if missing_files:
            # ファイルが見つからなかったことをDBに登録して、早期終了
            submission_summary_record.result = SubmissionSummaryStatus.FN
            submission_summary_record.message = "ファイルが存在しません"
            submission_summary_record.detail = f"{' '.join(missing_files)}"
            submission_summary_record.score = 0
            submission_summary_record.evaluation_summary_list = []
            return self._closing_procedure(
                submission_summary=submission_summary_record,
                working_volume=working_volume
            )
        
        # 2. 準備
        # required_files, arranged_filesが入ったボリュームを作る
        working_volume, err = self._create_complete_volume()
        if not err.silence():
            submission_summary_record.result = SubmissionSummaryStatus.IE
            submission_summary_record.message = "error when executing sandbox"
            submission_summary_record.detail = err.message
            # submission_summary_record.score = (total sum)
            submission_summary_record.evaluation_summary_list = evaluation_summary_list
            return self._closing_procedure(
                submission_summary=submission_summary_record,
                working_volume=working_volume
            )
        
        evaluation_summary_list = []
        
        # 3. Builtテストケース(コンパイル)を実行する
        built_task_list = [task for task in self.problem_record.evaluation_item_list if task.type == EvaluationType.Built]
        for built_task in built_task_list:
            evaluation_summary = self._exec_built_task(
                working_volume=working_volume,
                built_task=built_task,
                container_name="checker-lang-gcc"
            )
            evaluation_summary_list.append(evaluation_summary)
            submission_summary_record.score += built_task.score
            
            if evaluation_summary.result != EvaluationSummaryStatus.AC:
                # コンパイル失敗した場合は早期終了する
                submission_summary_record.result = SubmissionSummaryStatus.CE
                submission_summary_record.message = evaluation_summary.message
                submission_summary_record.detail = evaluation_summary.detail
                # submission_summary_record.score = (total sum)
                submission_summary_record.evaluation_summary_list = evaluation_summary_list
                return self._closing_procedure(
                    submission_summary=submission_summary_record,
                    working_volume=working_volume
                )
        
        # 4. 必要な実行ファイルが生成されているか調べる
        
        # Executablesテーブルから、必要な実行バイナリのファイル名リストを取得
        executable_list = []
        with SessionLocal() as db:
            executable_list = fetch_executables(
                db=db,
                lecture_id=self.problem_record.lecture_id,
                assignment_id=self.problem_record.assignment_id,
                for_evaluation=self.problem_record.for_evaluation
            )
        
        # Volume内でどのようなファイルが生成されたか調べる
        sandbox_env = TaskInfo(
            name="binary-runner", 
            arguments=["ls", "-p"],
            workDir="/workdir/",
            volumeMountInfoList=[VolumeMountInfo(path="/workdir/", volume=working_volume, read_only=True)])
        result, err = sandbox_env.run()
        
        if not err.silence():
            submission_summary_record.result = SubmissionSummaryStatus.IE
            submission_summary_record.message = "error when executing sandbox"
            submission_summary_record.detail = err.message
            # submission_summary_record.score = (total sum)
            submission_summary_record.evaluation_summary_list = evaluation_summary_list
            return self._closing_procedure(
                submission_summary=submission_summary_record,
                working_volume=working_volume
            )

        all_files_in_sandbox = [file for file in result.stdout.strip().split() if not file.endswith('/')]
        
        # all_files_in_sandboxの中に、executable_listの要素が全部含まれているか調べる。
        # 含まれていないものがあれば、それをnot_found_listで表す。
        not_found_executable_set = set(executable_list) - set(all_files_in_sandbox)
        if not_found_executable_set:
            # 必要な実行バイナリが見つからなかったことをDBに登録して、早期終了
            submission_summary_record.result = SubmissionSummaryStatus.CE
            submission_summary_record.message = "実行ファイルが出力されていません"
            submission_summary_record.detail = f"{' '.join(not_found_executable_set)}"
            # submission_summary_record.score = (total sum)
            submission_summary_record.evaluation_summary_list = evaluation_summary_list
            return self._closing_procedure(
                submission_summary=submission_summary_record,
                working_volume=working_volume
            )
        
        # Judgeテストケース(実行・チェック)を実行する
        judge_task_list = [task for task in self.problem_record.evaluation_item_list if task.type == EvaluationType.Judge]
        for judge_task in judge_task_list:
            evaluation_summary = self._exec_judge_task(
                working_volume=working_volume,
                judge_task=judge_task,
                container_name="binary-runner"
            )
            evaluation_summary_list.append(evaluation_summary)
            submission_summary_record.score += judge_task.score
            submission_summary_record.result = max(submission_summary_record.result, SubmissionSummaryStatus[evaluation_summary.result.name])
            
        submission_summary_record.evaluation_summary_list = evaluation_summary_list
    
        # 全体の結果を登録
        return self._closing_procedure(
            submission_summary=submission_summary_record,
            working_volume=working_volume
        )
