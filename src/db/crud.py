# Create, Read, Update and Delete (CRUD)
from sqlalchemy.orm import Session
from pathlib import Path
from pprint import pp
from sqlalchemy import inspect
from datetime import datetime, timedelta

from db import models, records

import logging

CRUD_LOGGER = logging.getLogger("crud")


def define_crud_logger(logger: logging.Logger):
    global CRUD_LOGGER
    CRUD_LOGGER = logger


# ----------------------- for judge server --------------------------------------


# Submissionテーブルから、statusが"queued"のジャッジリクエストを数件取得し、statusを"running"
# に変え、変更したリクエスト(複数)を返す
def fetch_queued_judge_and_change_status_to_running(
    db: Session, n: int
) -> list[records.Submission]:
    CRUD_LOGGER.debug("fetch_queued_judgeが呼び出されました")
    try:
        # FOR UPDATE NOWAITを使用して排他的にロックを取得
        # CRUD_LOGGER.debug("FOR UPDATE NOWAITを使用して排他的にロックを取得")
        submission_list = (
            db.query(models.Submission)
            .filter(models.Submission.progress == "queued")
            .with_for_update(nowait=True)
            .limit(n)
            .all()
        )
        # CRUD_LOGGER.debug(f"取得したSubmissionの数: {len(submission_list)}")

        for submission in submission_list:
            submission.progress = "running"
            # total_task（実行しなければならないTestCaseの数）を求める
            # CRUD_LOGGER.debug(f"total_taskを求めるためにTestCasesテーブルをクエリ")
            submission_total_task = (
                db.query(models.TestCases)
                .filter(models.TestCases.lecture_id == submission.lecture_id, 
                        models.TestCases.assignment_id == submission.assignment_id,
                        # 非評価用の課題は必ず含めるものとする
                        (models.TestCases.eval == submission.eval) | (models.TestCases.eval == False))
                .count()
            )
            # CRUD_LOGGER.debug(f"total_task: {submission_total_task}")
            submission.total_task = submission_total_task
            submission.completed_task = 0

        db.commit()
        return [
            # sqlalchemyのrelationshipのlazy loadingにより
            # uploaded_filesが埋まる
            records.Submission.model_validate(submission)
            for submission in submission_list
        ]
    except Exception as e:
        db.rollback()
        CRUD_LOGGER.error(f"fetch_queued_judgeでエラーが発生しました: {str(e)}")
        return []


# lecture_id, assignment_idのデータから、それに対応するProblemデータを全て取得する
# eval=Trueの場合は、評価用のデータも取得する
def fetch_problem(
    db: Session, lecture_id: int, assignment_id: int, eval: bool
) -> records.Problem | None:
    CRUD_LOGGER.debug("fetch_problemが呼び出されました")
    try:
        problem = (
            db.query(models.Problem)
            .filter(
                models.Problem.lecture_id == lecture_id,
                models.Problem.assignment_id == assignment_id,
            )
            .first()
        )

        # ここで、lazy loadingにより、executables, arranged_files, required_files, test_casesが埋まる
        problem_record = records.Problem.model_validate(problem)
        
        if eval is False:
            # eval == Falseの場合は、評価用のテストケースを除く
            problem_record.test_cases = [
                testcase for testcase in problem_record.test_cases if testcase.eval == False
            ]
        
        return problem_record
    except Exception as e:
        CRUD_LOGGER.error(f"fetch_problemでエラーが発生しました: {str(e)}")
        return None


# 特定のSubmissionに対応するジャッジリクエストの属性値を変更する
# 注) SubmissionRecord.idが同じレコードがテーブル内にあること
def update_submission_record(db: Session, submission_record: records.Submission) -> None:
    CRUD_LOGGER.debug("call update_submission_status")
    raw_submission_record = (
        db.query(models.Submission)
        .filter(models.Submission.id == submission_record.id)
        .first()
    )
    if raw_submission_record is None:
        raise ValueError(f"Submission with id {submission_record.id} not found")

    # assert raw_submission_record.batch_id == submission_record.batch_id
    # assert raw_submission_record.user_id == submission_record.user_id
    # assert raw_submission_record.lecture_id == submission_record.lecture_id
    # assert raw_submission_record.assignment_id == submission_record.assignment_id
    # assert raw_submission_record.eval == submission_record.eval
    raw_submission_record.progress = submission_record.progress.value
    raw_submission_record.total_task = submission_record.total_task
    raw_submission_record.completed_task = submission_record.completed_task
    db.commit()


def register_submission_summary_recursive(
    db: Session, submission_summary: records.SubmissionSummary
) -> None:
    CRUD_LOGGER.debug("register_submission_summary_recursiveが呼び出されました")
    raw_submission_summary = models.SubmissionSummary(
        **submission_summary.model_dump(exclude={"judge_results"})
    )
    
    db.add(raw_submission_summary)
    # ここでコミットしないと、judge_resultsのsubmission_id(SubmissionSummary.submission_idを指すFK)
    # の参照先が定まらないため、以降の処理でエラーが発生する
    db.commit()
    
    for judge_result in submission_summary.judge_results:
        raw_judge_result = models.JudgeResult(
            **judge_result.model_dump(exclude={"id", "ts"})
        )
        db.add(raw_judge_result)
    
    db.commit()

# Undo処理: judge-serverをシャットダウンするときに実行する
# 1. その時点でstatusが"running"になっているジャッジリクエスト(from Submissionテーブル)を
#    全て"queued"に変更する
# 2. 変更したジャッジリクエストについて、それに紐づいたJudgeResult, EvaluationSummary, SubmissionSummaryを全て削除する
def undo_running_submissions(db: Session) -> None:
    CRUD_LOGGER.debug("call undo_running_submissions")
    # 1. "running"状態のSubmissionを全て取得
    running_submissions = (
        db.query(models.Submission)
        .filter(models.Submission.progress == "running")
        .all()
    )

    submission_id_list = [submission.id for submission in running_submissions]

    # すべてのrunning submissionのstatusを"queued"に変更
    for submission in running_submissions:
        submission.progress = "queued"

    db.commit()

    # 関連するJudgeResultを一括で削除
    db.query(models.JudgeResult).filter(
        models.JudgeResult.submission_id.in_(submission_id_list)
    ).delete(synchronize_session=False)

    # 関連するSubmissionSummaryを一括で削除
    db.query(models.SubmissionSummary).filter(
        models.SubmissionSummary.submission_id.in_(submission_id_list)
    ).delete(synchronize_session=False)

    # 変更をコミット
    db.commit()


def fetch_uploaded_files(db: Session, submission_id: int) -> list[records.UploadedFiles]:
    raw_uploaded_files = db.query(models.UploadedFiles).filter(models.UploadedFiles.submission_id == submission_id).all()
    return [records.UploadedFiles.model_validate(uploaded_file) for uploaded_file in raw_uploaded_files]


# ----------------------- end --------------------------------------------------

# ---------------- for client server -------------------------------------------


# Submissionテーブルにジャッジリクエストを追加する
def register_judge_request(
    db: Session,
    batch_id: int | None,
    user_id: str,
    lecture_id: int,
    assignment_id: int,
    eval: bool,
) -> records.Submission:
    CRUD_LOGGER.debug("call register_judge_request")
    new_submission = models.Submission(
        batch_id=batch_id,
        user_id=user_id,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        eval=eval,
    )
    db.add(new_submission)
    db.commit()
    db.refresh(new_submission)
    return records.Submission.model_validate(new_submission)


# アップロードされたファイルをUploadedFilesに登録する
def register_uploaded_files(db: Session, submission_id: int, path: Path) -> None:
    CRUD_LOGGER.debug("call register_uploaded_files")
    new_uploadedfiles = models.UploadedFiles(
        submission_id=submission_id, path=str(path)
    )
    db.add(new_uploadedfiles)
    db.commit()


# Submissionテーブルのジャッジリクエストをキューに追加する
# 具体的にはSubmissionレコードのstatusをqueuedに変更する
def enqueue_judge_request(db: Session, submission_id: int) -> None:
    CRUD_LOGGER.debug("call enqueue_judge_request")
    pending_submission = (
        db.query(models.Submission)
        .filter(models.Submission.id == submission_id)
        .first()
    )

    if pending_submission is not None:
        pending_submission.progress = "queued"
        db.commit()
    else:
        raise ValueError(f"Submission with id {submission_id} not found")


# Submissionテーブルのジャッジリクエストのstatusを確認する
def fetch_submission_record(db: Session, submission_id: int) -> records.Submission:
    CRUD_LOGGER.debug("call fetch_judge_status")
    submission = (
        db.query(models.Submission)
        .filter(models.Submission.id == submission_id)
        .first()
    )
    if submission is None:
        raise ValueError(f"Submission with {submission_id} not found")
    return records.Submission.model_validate(submission)


# 特定のジャッジリクエストに紐づいたジャッジ結果を取得する
def fetch_submission_summary(
    db: Session, submission_id: int, detail: bool = False
) -> records.SubmissionSummary | None:
    CRUD_LOGGER.debug("call fetch_submission_summary")
    raw_submission_summary = (
        db.query(models.SubmissionSummary)
        .filter(models.SubmissionSummary.submission_id == submission_id)
        .first()
    )
    if raw_submission_summary is None:
        return None
    submission_summary = records.SubmissionSummary.model_validate(raw_submission_summary)
    if detail is True:
        judge_results = (
            db.query(models.JudgeResult)
            .filter(models.JudgeResult.submission_id == submission_id)
            .all()
        )
        submission_summary.judge_results = [records.JudgeResult.model_validate(judge_result) for judge_result in judge_results]
    return submission_summary


def create_user(db: Session, user_id: str) -> None:
    '''
    テストコードのためだけのメソッド
    '''
    new_user = models.Users(
        user_id=user_id,
        username="test",
        email="test@test.com",
        hashed_password="test",
        role="student",
        disabled=False,
        active_start_date=datetime.now(),
        active_end_date=datetime.now() + timedelta(days=365),
    )
    db.add(new_user)
    db.commit()

def delete_user(db: Session, user_id: str) -> None:
    '''
    テストコードのためだけのメソッド
    '''
    db.query(models.Users).filter(models.Users.user_id == user_id).delete()
    db.commit()

def user_exists(db: Session, user_id: str) -> bool:
    return db.query(models.Users).filter(models.Users.user_id == user_id).first() is not None
