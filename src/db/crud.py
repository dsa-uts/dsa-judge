# Create, Read, Update and Delete (CRUD)
from sqlalchemy.orm import Session
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

from . import models

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

#----------------------- for judge server --------------------------------------
from enum import Enum

class SubmissionProgressStatus(Enum):
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    DONE = 'done'

class JudgeSummaryStatus(Enum):
    UNPROCESSED = 'Unprocessed'
    AC = 'AC'
    WA = 'WA'
    TLE = 'TLE'
    MLE = 'MLE'
    CE = 'CE'
    RE = 'RE'
    OLE = 'OLE'
    IE = 'IE'

@dataclass
class SubmissionRecord:
    id: int
    ts: datetime 
    batch_id: int | None
    student_id: str
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    progress: SubmissionProgressStatus
    prebuilt_result: JudgeSummaryStatus
    postbuilt_result: JudgeSummaryStatus
    judge_result: JudgeSummaryStatus
    message: str

# Submissionテーブルから、statusが"queued"のジャッジリクエストを数件取得し、statusを"running"
# に変え、変更したリクエスト(複数)を返す
def fetch_queued_judge_and_change_status_to_running(db: Session, n: int) -> list[SubmissionRecord]:
    logger.info("fetch_queued_judgeが呼び出されました")
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
                student_id=submission.student_id,
                lecture_id=submission.lecture_id,
                assignment_id=submission.assignment_id,
                for_evaluation=submission.for_evaluation,
                progress=SubmissionProgressStatus(submission.progress),
                prebuilt_result=JudgeSummaryStatus(submission.prebuilt_result),
                postbuilt_result=JudgeSummaryStatus(submission.postbuilt_result),
                judge_result=JudgeSummaryStatus(submission.judge_result),
                message=submission.message)
            for submission in submission_list
        ]
    except Exception as e:
        db.rollback()
        logger.error(f"fetch_queued_judgeでエラーが発生しました: {str(e)}")
        return []

@dataclass
class ProblemRecord:
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    title: str
    description_path: str
    timeMS: int
    memoryMB: int
    build_script_path: str
    executable: str

# lecture_id, assignment_id, for_evaluationのデータから、それに対応するProblemデータ(実行ファイル名、制限リソース量)を取得する
def fetch_problem(db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool) -> ProblemRecord | None:
    logger.info("call fetch_problem")
    problem = db.query(models.Problem).filter(models.Problem.lecture_id == lecture_id,
                                              models.Problem.assignment_id == assignment_id,
                                              models.Problem.for_evaluation == for_evaluation
                                              ).first()
    
    if problem is not None:
        return ProblemRecord(
            lecture_id=problem.lecture_id,
            assignment_id=problem.assignment_id,
            for_evaluation=problem.for_evaluation,
            title=problem.title,
            description_path=problem.description_path,
            timeMS=problem.timeMS,
            memoryMB=problem.memoryMB,
            build_script_path=problem.build_script_path,
            executable=problem.executable
        )

    return None

# ジャッジリクエストに紐づいている、アップロードされたファイルのパスのリストをUploadedFiles
# テーブルから取得して返す
def fetch_uploaded_filepaths(db: Session, submission_id: int) -> list[str]:
    logger.info("call fetch_uploaded_filepaths")
    uploaded_files = db.query(models.UploadedFiles).filter(models.UploadedFiles.submission_id == submission_id).all()
    return [file.path for file in uploaded_files]

# 特定の問題でこちらで用意しているファイルのパス(複数)をArrangedFilesテーブルから取得する
def fetch_arranged_filepaths(db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool) -> list[str]:
    logger.info("call fetch_arranged_filepaths")
    arranged_files = db.query(models.ArrangedFiles).filter(
        models.ArrangedFiles.lecture_id == lecture_id,
        models.ArrangedFiles.assignment_id == assignment_id,
        models.ArrangedFiles.for_evaluation == for_evaluation
    ).all()
    return [file.path for file in arranged_files]

# 特定の問題で必要とされているのファイル名のリストをRequiredFilesテーブルから取得する
def fetch_required_files(db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool) -> list[str]:
    logger.info("call fetch_required_files")
    required_files = db.query(models.RequiredFiles).filter(
        models.RequiredFiles.lecture_id == lecture_id,
        models.RequiredFiles.assignment_id == assignment_id,
        models.RequiredFiles.for_evaluation == for_evaluation
    ).all()
    return [file.name for file in required_files]

class TestCaseType(Enum):
    preBuilt = 'preBuilt'
    postBuilt = 'postBuilt'
    Judge = 'Judge'

@dataclass
class TestCaseRecord:
    id: int
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    type: TestCaseType # ENUM('preBuilt', 'postBuilt', 'Judge') NOT NULL, -- テストケースが実行されるタイミング
    description: str | None
    score: str | None
    script_path: str | None
    argument_path: str | None
    stdin_path: str | None
    stdout_path: str
    stderr_path: str
    exit_code: int # default: 0

# 特定の問題に紐づいたテストケースのリストをTestCasesテーブルから取得する
def fetch_testcases(db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool) -> list[TestCaseRecord]:
    logger.info("call fetch_testcases")
    testcase_list = db.query(models.TestCases).filter(
        models.TestCases.lecture_id == lecture_id,
        models.TestCases.assignment_id == assignment_id,
        models.TestCases.for_evaluation == for_evaluation
    ).all()
    return [
        TestCaseRecord(
            id=testcase.id,
            lecture_id=testcase.lecture_id,
            assignment_id=testcase.assignment_id,
            for_evaluation=testcase.for_evaluation,
            type=TestCaseType(testcase.type), # cast str to Enum
            description=testcase.description,
            score=testcase.score,
            script_path=testcase.script_path,
            argument_path=testcase.argument_path,
            stdin_path=testcase.stdin_path,
            stdout_path=testcase.stdout_path,
            stderr_path=testcase.stderr_path,
            exit_code=testcase.exit_code
        )
        for testcase in testcase_list
    ]
    
class SingleJudgeStatus(Enum):
    AC = 'AC'
    WA = 'WA'
    TLE = 'TLE'
    MLE = 'MLE'
    CE = 'CE'
    RE = 'RE'
    OLE = 'OLE'
    IE = 'IE'
    
@dataclass
class JudgeResultRecord:
    submission_id: int
    testcase_id: int
    timeMS: int
    memoryKB: int
    exit_code: int
    stdout: str
    stderr: str
    result: SingleJudgeStatus
    id: int = 1 # テーブルに挿入する際は自動設定されるので、コンストラクタで指定する必要が無いように適当な値を入れている
    ts: datetime = datetime(1998, 6, 6, 12, 32, 41)

# 特定のテストケースに対するジャッジ結果をJudgeResultテーブルに登録する
def register_judge_result(db: Session, result: JudgeResultRecord) -> None:
    logger.info("call register_judge_result")
    judge_result = models.JudgeResult(
        submission_id=result.submission_id,
        testcase_id=result.testcase_id,
        timeMS=result.timeMS,
        memoryKB=result.memoryKB,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        result=result.result.value
    )
    db.add(judge_result)
    db.commit()
    
# 特定のSubmissionに対応するジャッジリクエストの属性値を変更する
# 注) SubmissionRecord.idが同じレコードがテーブル内にあること
def update_submission_record(db: Session, submission_record: SubmissionRecord) -> None:
    logger.info("call update_submission_status")
    raw_submission_record = db.query(models.Submission).filter(models.Submission.id == submission_record.id).first()
    if raw_submission_record is None:
        raise ValueError(f"Submission with id {submission_record.id} not found")
    
    # assert raw_submission_record.batch_id == submission_record.batch_id
    # assert raw_submission_record.student_id == submission_record.student_id
    # assert raw_submission_record.for_evaluation == submission_record.for_evaluation
    raw_submission_record.progress = submission_record.progress.value
    raw_submission_record.prebuilt_result = submission_record.prebuilt_result.value
    raw_submission_record.postbuilt_result = submission_record.postbuilt_result.value
    raw_submission_record.judge_result = submission_record.judge_result.value
    raw_submission_record.message = submission_record.message
    db.commit()

# Undo処理: judge-serverをシャットダウンするときに実行する
# 1. その時点でstatusが"running"になっているジャッジリクエスト(from Submissionテーブル)を
#    全て"queued"に変更する
# 2. 変更したジャッジリクエストについて、それに紐づいたJudgeResultを全て削除する
def undo_running_submissions(db: Session) -> None:
    logger.info("call undo_running_submissions")
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
    logger.info("call register_judge_request")
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
        student_id=new_submission.student_id,
        lecture_id=new_submission.lecture_id,
        assignment_id=new_submission.assignment_id,
        for_evaluation=new_submission.for_evaluation,
        progress=SubmissionProgressStatus(new_submission.progress),
        prebuilt_result=JudgeSummaryStatus(new_submission.prebuilt_result),
        postbuilt_result=JudgeSummaryStatus(new_submission.postbuilt_result),
        judge_result=JudgeSummaryStatus(new_submission.postbuilt_result),
        message=new_submission.message
    )

# アップロードされたファイルをUploadedFilesに登録する
def register_uploaded_files(db: Session, submission_id: int, path: Path) -> None:
    logger.info("call register_uploaded_files")
    new_uploadedfiles = models.UploadedFiles(
        submission_id=submission_id,
        path=str(path)
    )
    db.add(new_uploadedfiles)
    db.commit()
    
# Submissionテーブルのジャッジリクエストをキューに追加する
# 具体的にはSubmissionレコードのstatusをqueuedに変更する
def enqueue_judge_request(db: Session, submission_id: int) -> None:
    logger.info("call enqueue_judge_request")
    pending_submission = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    
    if pending_submission is not None:
        pending_submission.progress = 'queued'
        db.commit()
    else:
        raise ValueError(f"Submission with id {submission_id} not found")

# Submissionテーブルのジャッジリクエストのstatusを確認する
def fetch_judge_status(db: Session, submission_id: int) -> SubmissionProgressStatus:
    logger.info("call fetch_judge_status")
    submission = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    if submission is None:
        raise ValueError(f"Submission with {submission_id} not found")
    return SubmissionProgressStatus(submission.progress)

# 特定のジャッジリクエストに紐づいたジャッジ結果を取得する
def fetch_judge_results(db: Session, submission_id: int) -> list[JudgeResultRecord]:
    logger.info("call fetch_judge_result")
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
