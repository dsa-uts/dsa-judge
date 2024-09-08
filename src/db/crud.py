# Create, Read, Update and Delete (CRUD)
from sqlalchemy.orm import Session
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path="../.env")
RESOURCE_DIR = Path(os.getenv("RESOURCE_PATH"))

from . import models

import logging
CRUD_LOGGER = logging.getLogger("crud")

def define_crud_logger(logger: logging.Logger):
    global CRUD_LOGGER
    CRUD_LOGGER = logger

# ----------------------- for judge server --------------------------------------
from enum import Enum

class EnumWithOrder(Enum):
    def __str__(self):
        return self.name

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self.value >= other.value
        return NotImplemented

class SubmissionProgressStatus(Enum):
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    DONE = 'done'

class SingleJudgeStatus(EnumWithOrder):
    # (value) = (order)
    AC  = 0
    WA  = 1
    TLE = 2
    MLE = 3
    RE  = 4
    CE  = 5
    OLE = 6
    IE  = 7

class EvaluationSummaryStatus(EnumWithOrder):
    # (value) = (order)
    AC  = 0
    WA  = 1
    TLE = 2
    MLE = 3
    RE  = 4
    CE  = 5
    OLE = 6
    IE  = 7

class SubmissionSummaryStatus(EnumWithOrder):
    # (value) = (order)
    AC  = 0 # Accepted
    WA  = 1 # Wrong Answer
    TLE = 2 # Time Limit Exceed
    MLE = 3 # Memory Limit Exceed
    RE  = 4 # Runtime Error
    CE  = 5 # Compile Error
    OLE = 6 # Output Limit Exceed (8000 bytes)
    IE  = 7 # Internal Error (e.g., docker sandbox management)
    FN  = 8 # File Not found

@dataclass
class SubmissionRecord:
    id: int
    ts: datetime 
    batch_id: int | None
    user_id: str
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    progress: SubmissionProgressStatus

# Submissionテーブルから、statusが"queued"のジャッジリクエストを数件取得し、statusを"running"
# に変え、変更したリクエスト(複数)を返す
def fetch_queued_judge_and_change_status_to_running(db: Session, n: int) -> list[SubmissionRecord]:
    CRUD_LOGGER.debug("fetch_queued_judgeが呼び出されました")
    try:
        # FOR UPDATE NOWAITを使用して排他的にロックを取得
        submission_list = db.query(models.Submission).filter(models.Submission.progress == 'queued').with_for_update(nowait=True).limit(n).all()
        
        for submission in submission_list:
            submission.progress = 'running'
        
        db.commit()
        return [
            SubmissionRecord(
                id=submission.id,
                ts=submission.ts,
                batch_id=submission.batch_id,
                user_id=submission.user_id,
                lecture_id=submission.lecture_id,
                assignment_id=submission.assignment_id,
                for_evaluation=submission.for_evaluation,
                progress=SubmissionProgressStatus(submission.progress))
            for submission in submission_list
        ]
    except Exception as e:
        db.rollback()
        CRUD_LOGGER.error(f"fetch_queued_judgeでエラーが発生しました: {str(e)}")
        return []

@dataclass
class TestCaseRecord:
    id: int
    description: str | None
    command: str # nullable=False
    argument_path: str | None
    stdin_path: str | None
    stdout_path: str | None
    stderr_path: str | None
    exit_code: int # default: 0

class EvaluationType(EnumWithOrder):
    Built = 1
    Judge = 2

@dataclass
class EvaluationItemRecord:
    str_id: str
    title: str
    description: str | None
    score: int
    type: EvaluationType
    arranged_file_id: str | None
    message_on_fail: str | None
    testcase_list: list[TestCaseRecord] # 紐づいているTestCaseRecordのリスト

@dataclass
class ProblemRecord:
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    title: str
    description_path: str
    timeMS: int
    memoryMB: int
    evaluation_item_list: list[EvaluationItemRecord] # 紐づいているEvaluationItemRecordのリスト

# lecture_id, assignment_id, for_evaluationのデータから、それに対応するProblemデータ(実行ファイル名、制限リソース量)
# およびそれに紐づいている評価項目(EvaluationItems)のリストやさらにそのEvaluationItemsに紐づいているTestCasesのリスト
# を取得
def fetch_problem(db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool) -> ProblemRecord | None:
    CRUD_LOGGER.debug("fetch_problemが呼び出されました")
    try:
        problem = db.query(models.Problem).filter(
            models.Problem.lecture_id == lecture_id,
            models.Problem.assignment_id == assignment_id,
            models.Problem.for_evaluation == for_evaluation
        ).first()

        if problem is None:
            return None

        evaluation_items = db.query(models.EvaluationItems).filter(
            models.EvaluationItems.lecture_id == lecture_id,
            models.EvaluationItems.assignment_id == assignment_id,
            models.EvaluationItems.for_evaluation == for_evaluation
        ).all()

        evaluation_item_list = []
        for item in evaluation_items:
            testcases = db.query(models.TestCases).filter(
                models.TestCases.eval_id == item.str_id
            ).all()

            testcase_list = [
                TestCaseRecord(
                    id=testcase.id,
                    description=testcase.description,
                    command=testcase.command,
                    argument_path=testcase.argument_path,
                    stdin_path=testcase.stdin_path,
                    stdout_path=testcase.stdout_path,
                    stderr_path=testcase.stderr_path,
                    exit_code=testcase.exit_code
                ) for testcase in testcases
            ]

            evaluation_item_list.append(
                EvaluationItemRecord(
                    str_id=item.str_id,
                    title=item.title,
                    description=item.description,
                    score=item.score,
                    type=EvaluationType[item.type],
                    arranged_file_id=item.arranged_file_id,
                    message_on_fail=item.message_on_fail,
                    testcase_list=testcase_list
                )
            )
        
        # evaluation_item.type == Builtのレコードが先に来るようにソートする。
        evaluation_item_list.sort(key=lambda x: x.type != EvaluationType.Built)

        return ProblemRecord(
            lecture_id=problem.lecture_id,
            assignment_id=problem.assignment_id,
            for_evaluation=problem.for_evaluation,
            title=problem.title,
            description_path=problem.description_path,
            timeMS=problem.timeMS,
            memoryMB=problem.memoryMB,
            evaluation_item_list=evaluation_item_list
        )

    except Exception as e:
        CRUD_LOGGER.error(f"fetch_problemでエラーが発生しました: {str(e)}")
        return None


# 課題のエントリから、そこでビルド・実行される実行ファイル名のリストをExecutablesテーブルから
# 取得する
def fetch_executables(
    db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool
) -> list[str]:
    CRUD_LOGGER.debug("call fetch_executables")
    executable_record_list = (
        db.query(models.Executables)
        .filter(
            models.Executables.lecture_id == lecture_id,
            models.Executables.assignment_id == assignment_id,
            models.Executables.for_evaluation == for_evaluation,
        )
        .all()
    )
    return [executable_record.name for executable_record in executable_record_list]


# ジャッジリクエストに紐づいている、アップロードされたファイルのパスのリストをUploadedFiles
# テーブルから取得して返す
def fetch_uploaded_filepaths(db: Session, submission_id: int) -> list[str]:
    CRUD_LOGGER.debug("call fetch_uploaded_filepaths")
    uploaded_files = db.query(models.UploadedFiles).filter(models.UploadedFiles.submission_id == submission_id).all()
    return [file.path for file in uploaded_files]

# 特定の問題でこちらで用意しているファイルのパス(複数)をArrangedFilesテーブルから取得する
def fetch_arranged_filepaths(db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool) -> list[str]:
    CRUD_LOGGER.debug("call fetch_arranged_filepaths")
    arranged_files = db.query(models.ArrangedFiles).filter(
        models.ArrangedFiles.lecture_id == lecture_id,
        models.ArrangedFiles.assignment_id == assignment_id,
        models.ArrangedFiles.for_evaluation == for_evaluation
    ).all()
    return [file.path for file in arranged_files]

# 特定の問題で必要とされているのファイル名のリストをRequiredFilesテーブルから取得する
def fetch_required_files(db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool) -> list[str]:
    CRUD_LOGGER.debug("call fetch_required_files")
    required_files = db.query(models.RequiredFiles).filter(
        models.RequiredFiles.lecture_id == lecture_id,
        models.RequiredFiles.assignment_id == assignment_id,
        models.RequiredFiles.for_evaluation == for_evaluation
    ).all()
    return [file.name for file in required_files]

@dataclass
class JudgeResultRecord:
    submission_id: int
    testcase_id: int
    result: SingleJudgeStatus
    timeMS: int
    memoryKB: int
    exit_code: int
    stdout: str
    stderr: str
    # TestCasesレコードから取ってくる値
    description: str | None
    command: str
    stdin: str | None
    expected_stdout: str
    expected_stderr: str
    expected_exit_code: int = 0
    # テーブル挿入時に自動で決まる値
    id: int = 1 # テーブルに挿入する際は自動設定されるので、コンストラクタで指定する必要が無いように適当な値を入れている
    ts: datetime = datetime(1998, 6, 6, 12, 32, 41)
    # 以降は、クライアント側で必要になるフィールド(対応するtestcase_idに対応するテストケースの情報)

# 特定のテストケースに対するジャッジ結果をJudgeResultテーブルに登録する
def register_judge_result(db: Session, judge_result: JudgeResultRecord) -> None:
    CRUD_LOGGER.debug("call register_judge_result")
    judge_result = models.JudgeResult(
        submission_id=judge_result.submission_id,
        testcase_id=judge_result.testcase_id,
        result=judge_result.result.name,
        timeMS=judge_result.timeMS,
        memoryKB=judge_result.memoryKB,
        exit_code=judge_result.exit_code,
        stdout=judge_result.stdout,
        stderr=judge_result.stderr,
        description=judge_result.description,
        command=judge_result.command,
        stdin=judge_result.stdin,
        expected_stdout=judge_result.expected_stdout,
        expected_stderr=judge_result.expected_stderr,
        expected_exit_code=judge_result.expected_exit_code
    )
    db.add(judge_result)
    db.commit()

# 特定のSubmissionに対応するジャッジリクエストの属性値を変更する
# 注) SubmissionRecord.idが同じレコードがテーブル内にあること
def update_submission_record(db: Session, submission_record: SubmissionRecord) -> None:
    CRUD_LOGGER.debug("call update_submission_status")
    raw_submission_record = db.query(models.Submission).filter(models.Submission.id == submission_record.id).first()
    if raw_submission_record is None:
        raise ValueError(f"Submission with id {submission_record.id} not found")
    
    # assert raw_submission_record.batch_id == submission_record.batch_id
    # assert raw_submission_record.student_id == submission_record.student_id
    # assert raw_submission_record.for_evaluation == submission_record.for_evaluation
    raw_submission_record.progress = submission_record.progress.value
    db.commit()

@dataclass
class EvaluationSummaryRecord:
    submission_id: int
    batch_id: int | None
    user_id: int
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    eval_id: str
    arranged_file_id: str | None
    result: EvaluationSummaryStatus
    message: str | None
    detail: str | None
    score: int
    # 外部キー関係ではないけどEvaluationItemsやArrangedFilesから取ってくる値
    eval_title: str # EvaluationItems.title
    eval_description: str | None # EvaluationItems.description
    eval_type: EvaluationType # EvaluationItems.type
    arranged_file_path: str | None # Arrangedfiles.path
    # テーブルに挿入時に自動で値が決まるフィールド
    id: int = 0 # auto increment PK
    # 以降、クライアントで必要になるフィールド
    judge_result_list: list[JudgeResultRecord] = []

# 特定のSubmission,さらにその中の評価項目に対応する結果をEvaluationSummaryテーブルに登録する
def register_evaluation_summary(db: Session, eval_summary: EvaluationSummaryRecord) -> None:
    CRUD_LOGGER.debug(f"call register_evaluation_summary")
    new_eval_summary = models.EvaluationSummary(
        submission_id=eval_summary.submission_id,
        batch_id=eval_summary.batch_id,
        user_id=eval_summary.user_id,
        lecture_id=eval_summary.lecture_id,
        assignment_id=eval_summary.assignment_id,
        for_evaluation=eval_summary.for_evaluation,
        eval_id=eval_summary.eval_id,
        arranged_file_id=eval_summary.arranged_file_id,
        result=eval_summary.result.name,
        message=eval_summary.message,
        detail=eval_summary.detail,
        score=eval_summary.score,
        eval_title=eval_summary.eval_title,
        eval_description=eval_summary.eval_description,
        arranged_file_path=eval_summary.arranged_file_path
    )
    db.add(new_eval_summary)
    db.commit()
    db.refresh(new_eval_summary)
    eval_summary.id = new_eval_summary.id

@dataclass
class SubmissionSummaryRecord:
    submission_id: int
    batch_id: int | None
    user_id: str
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    result: SubmissionSummaryStatus
    message: str | None
    detail: str | None
    score: int
    # 以降、クライアントで必要になるフィールド
    evaluation_summary_list: list[EvaluationSummaryRecord] = []


# 特定のSubmissionに対応するジャッジの集計結果をSubmissionSummaryテーブルに登録する
def register_submission_summary(db: Session, submission_summary: SubmissionSummaryRecord) -> None:
    CRUD_LOGGER.debug("register_submission_summaryが呼び出されました")
    new_submission_summary = models.SubmissionSummary(
        submission_id=submission_summary.submission_id,
        batch_id=submission_summary.batch_id,
        user_id=submission_summary.user_id,
        lecture_id=submission_summary.lecture_id,
        assignment_id=submission_summary.assignment_id,
        for_evaluation=submission_summary.for_evaluation,
        result=submission_summary.result.name,
        message=submission_summary.message,
        detail=submission_summary.detail,
        score=submission_summary.score
    )
    db.add(new_submission_summary)
    db.commit()

# Undo処理: judge-serverをシャットダウンするときに実行する
# 1. その時点でstatusが"running"になっているジャッジリクエスト(from Submissionテーブル)を
#    全て"queued"に変更する
# 2. 変更したジャッジリクエストについて、それに紐づいたJudgeResultを全て削除する
def undo_running_submissions(db: Session) -> None:
    CRUD_LOGGER.debug("call undo_running_submissions")
    # 1. "running"状態のSubmissionを全て取得
    running_submissions = db.query(models.Submission).filter(models.Submission.progress == "running").all()
    
    submission_id_list = [submission.id for submission in running_submissions]
    
    # すべてのrunning submissionのstatusを"queued"に変更
    for submission in running_submissions:
        submission.progress = "queued"
    
    db.commit()
    
    # 関連するJudgeResultを一括で削除
    db.query(models.JudgeResult).filter(models.JudgeResult.submission_id.in_(submission_id_list)).delete(synchronize_session=False)
    # 変更をコミット
    db.commit()

# ----------------------- end --------------------------------------------------

# ---------------- for client server -------------------------------------------

# Submissionテーブルにジャッジリクエストを追加する
def register_judge_request(db: Session, batch_id: int | None, student_id: str, lecture_id: int, assignment_id: int, for_evaluation: bool) -> SubmissionRecord:
    CRUD_LOGGER.debug("call register_judge_request")
    new_submission = models.Submission(
        batch_id=batch_id,
        student_id=student_id,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=for_evaluation,
    )
    db.add(new_submission)
    db.commit()
    db.refresh(new_submission)
    return SubmissionRecord(
        id=new_submission.id,
        ts=new_submission.ts,
        batch_id=new_submission.batch_id,
        user_id=new_submission.student_id,
        lecture_id=new_submission.lecture_id,
        assignment_id=new_submission.assignment_id,
        for_evaluation=new_submission.for_evaluation,
        progress=SubmissionProgressStatus(new_submission.progress)
    )

# アップロードされたファイルをUploadedFilesに登録する
def register_uploaded_files(db: Session, submission_id: int, path: Path) -> None:
    CRUD_LOGGER.debug("call register_uploaded_files")
    new_uploadedfiles = models.UploadedFiles(
        submission_id=submission_id,
        path=str(path)
    )
    db.add(new_uploadedfiles)
    db.commit()

# Submissionテーブルのジャッジリクエストをキューに追加する
# 具体的にはSubmissionレコードのstatusをqueuedに変更する
def enqueue_judge_request(db: Session, submission_id: int) -> None:
    CRUD_LOGGER.debug("call enqueue_judge_request")
    pending_submission = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    
    if pending_submission is not None:
        pending_submission.progress = 'queued'
        db.commit()
    else:
        raise ValueError(f"Submission with id {submission_id} not found")

# Submissionテーブルのジャッジリクエストのstatusを確認する
def fetch_judge_status(db: Session, submission_id: int) -> SubmissionProgressStatus:
    CRUD_LOGGER.debug("call fetch_judge_status")
    submission = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    if submission is None:
        raise ValueError(f"Submission with {submission_id} not found")
    return SubmissionProgressStatus(submission.progress)

# 特定のジャッジリクエストに紐づいたジャッジ結果を取得する
def fetch_judge_results(db: Session, submission_id: int) -> list[JudgeResultRecord]:
    CRUD_LOGGER.debug("call fetch_judge_result")
    raw_judge_results = db.query(models.JudgeResult).filter(models.JudgeResult.submission_id == submission_id).all()
    return [
        JudgeResultRecord(
            id=raw_result.id,
            ts=raw_result.ts,
            submission_id=raw_result.submission_id,
            testcase_id=raw_result.testcase_id,
            timeMS=raw_result.timeMS,
            memoryKB=raw_result.memoryKB,
            exit_code=raw_result.exit_code,
            stdout=raw_result.stdout,
            stderr=raw_result.stderr,
            result=SingleJudgeStatus(raw_result.result)
        )
        for raw_result in raw_judge_results
    ]

def fetch_arranged_file_dict(db: Session, arranged_file_id_list: list[str]) -> dict[str, str]:
    arranged_file_records = db.query(models.ArrangedFiles).filter(models.ArrangedFiles.str_id.in_(arranged_file_id_list)).all()
    return {record.str_id: record.path for record in arranged_file_records}

def fetch_submission_summary(db: Session, submission_id: int) -> SubmissionSummaryRecord:
    CRUD_LOGGER.debug("fetch_submission_summaryが呼び出されました")
    raw_submission_summary = db.query(models.SubmissionSummary).filter(
        models.SubmissionSummary.submission_id == submission_id
    ).first()
    if raw_submission_summary is None:
        raise ValueError(f"提出 {submission_id} は完了していません")
    submission_summary = SubmissionSummaryRecord(
        submission_id=raw_submission_summary.submission_id,
        batch_id=raw_submission_summary.batch_id,
        user_id=raw_submission_summary.user_id,
        lecture_id=raw_submission_summary.lecture_id,
        assignment_id=raw_submission_summary.assignment_id,
        for_evaluation=raw_submission_summary.for_evaluation,
        result=SubmissionSummaryStatus[raw_submission_summary.result],
        message=raw_submission_summary.message,
        detail=raw_submission_summary.detail,
        score=raw_submission_summary.score
    )

    # Goal: submission_summary.evaluation_summary_listを埋める

    # 1. fetch_problem()で問題の全情報を取得
    problem_record = fetch_problem(
        db=db,
        lecture_id=submission_summary.lecture_id,
        assignment_id=submission_summary.assignment_id,
        for_evaluation=submission_summary.for_evaluation,
    )

    if problem_record is None:
        raise ValueError(
            f"対応する問題情報がありません: 第{submission_summary.lecture_id}回 課題{submission_summary.assignment_id} - {submission_summary.for_evaluation}"
        )

    # submission_idに対応するJudgeResultを全て取得
    judge_result_list = fetch_judge_results(
        db=db, submission_id=submission_summary.submission_id
    )
    
    # testcase_id -> JudgeResulレコードへアクセスする辞書
    judge_result_dict = {item.testcase_id: item for item in judge_result_list}

    raw_evaluation_summary_list = db.query(models.EvaluationSummary).filter(
        models.EvaluationSummary.submission_id == submission_id
    ).all()

    # eval_id -> 対応するEvaluationItemsレコードの情報へアクセスする辞書
    evaluation_items_dict = {item.str_id: item for item in problem_record.evaluation_item_list}

    for raw_evaluation_summary in raw_evaluation_summary_list:
        evaluation_item = evaluation_items_dict[raw_evaluation_summary.eval_id]
        evaluation_summary = EvaluationSummaryRecord(
            id=raw_evaluation_summary.id,
            submission_id=raw_evaluation_summary.submission_id,
            batch_id=raw_evaluation_summary.batch_id,
            user_id=raw_evaluation_summary.user_id,
            lecture_id=raw_evaluation_summary.lecture_id,
            assignment_id=raw_evaluation_summary.assignment_id,
            for_evaluation=raw_evaluation_summary.for_evaluation,
            eval_id=raw_evaluation_summary.eval_id,
            arranged_file_id=raw_evaluation_summary.arranged_file_id,
            result=EvaluationSummaryStatus[raw_evaluation_summary.result],
            message=raw_evaluation_summary.message,
            detail=raw_evaluation_summary.detail,
            score=raw_evaluation_summary.score,
            eval_title=raw_evaluation_summary.eval_title,
            eval_description=raw_evaluation_summary.eval_description,
            eval_type=EvaluationType[raw_evaluation_summary.eval_type],
            arranged_file_path=raw_evaluation_summary.arranged_file_path,
            judge_result_list=[]
        )
        
        # EvaluationSummaryRecord.judge_result_listに実行結果リストを挿入する
        for testcase in evaluation_item.testcase_list:
            evaluation_summary.judge_result_list.append(
                judge_result_dict[testcase.id]
            )
        
        submission_summary.evaluation_summary_list.append(evaluation_summary)

    return submission_summary
