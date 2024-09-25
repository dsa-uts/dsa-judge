# Create, Read, Update and Delete (CRUD)
from sqlalchemy.orm import Session
from pathlib import Path
from pprint import pp

from . import models
from .records import *

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
) -> list[SubmissionRecord]:
    CRUD_LOGGER.debug("fetch_queued_judgeが呼び出されました")
    try:
        # FOR UPDATE NOWAITを使用して排他的にロックを取得
        submission_list = (
            db.query(models.Submission)
            .filter(models.Submission.progress == "queued")
            .with_for_update(nowait=True)
            .limit(n)
            .all()
        )

        for submission in submission_list:
            submission.progress = "running"
            # total_task（実行しなければならないTestCaseの数）を求める
            submission_total_task = (
                db.query(models.TestCases)
                .join(
                    models.EvaluationItems,
                    models.TestCases.eval_id == models.EvaluationItems.str_id,
                )
                .filter(
                    models.EvaluationItems.lecture_id == submission.lecture_id,
                    models.EvaluationItems.assignment_id == submission.assignment_id,
                    models.EvaluationItems.for_evaluation == submission.for_evaluation,
                )
                .count()
            )
            submission.total_task = submission_total_task
            submission.completed_task = 0

        db.commit()
        return [
            SubmissionRecord.model_validate(submission)
            for submission in submission_list
        ]
    except Exception as e:
        db.rollback()
        CRUD_LOGGER.error(f"fetch_queued_judgeでエラーが発生しました: {str(e)}")
        return []


# lecture_id, assignment_id, for_evaluationのデータから、それに対応するProblemデータ(実行ファイル名、制限リソース量)
# およびそれに紐づいている評価項目(EvaluationItems)のリストやさらにそのEvaluationItemsに紐づいているTestCasesのリスト
# を取得
def fetch_problem(
    db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool
) -> ProblemRecord | None:
    CRUD_LOGGER.debug("fetch_problemが呼び出されました")
    try:
        problem = (
            db.query(models.Problem)
            .filter(
                models.Problem.lecture_id == lecture_id,
                models.Problem.assignment_id == assignment_id,
                models.Problem.for_evaluation == for_evaluation,
            )
            .first()
        )

        if problem is None:
            return None

        evaluation_items = (
            db.query(models.EvaluationItems)
            .filter(
                models.EvaluationItems.lecture_id == lecture_id,
                models.EvaluationItems.assignment_id == assignment_id,
                models.EvaluationItems.for_evaluation == for_evaluation,
            )
            .all()
        )

        evaluation_item_list = []
        for item in evaluation_items:
            testcases = (
                db.query(models.TestCases)
                .filter(models.TestCases.eval_id == item.str_id)
                .all()
            )

            testcase_list = [
                TestCaseRecord.model_validate(testcase) for testcase in testcases
            ]

            evaluation_item_record = EvaluationItemRecord.model_validate(item)
            evaluation_item_record.testcase_list = testcase_list

            evaluation_item_list.append(evaluation_item_record)

        # evaluation_item.type == Builtのレコードが先に来るようにソートする。
        evaluation_item_list.sort(key=lambda x: x.type != EvaluationType.Built)

        problem_record = ProblemRecord.model_validate(problem)
        problem_record.evaluation_item_list = evaluation_item_list

        return problem_record
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
    uploaded_files = (
        db.query(models.UploadedFiles)
        .filter(models.UploadedFiles.submission_id == submission_id)
        .all()
    )
    return [file.path for file in uploaded_files]


# 特定の問題でこちらで用意しているファイルのIDとパス(複数)をArrangedFilesテーブルから取得する
def fetch_arranged_filepaths(
    db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool
) -> list[tuple[str, str]]:
    CRUD_LOGGER.debug("fetch_arranged_filepathsが呼び出されました")
    arranged_files = (
        db.query(models.ArrangedFiles)
        .filter(
            models.ArrangedFiles.lecture_id == lecture_id,
            models.ArrangedFiles.assignment_id == assignment_id,
            models.ArrangedFiles.for_evaluation == for_evaluation,
        )
        .all()
    )
    return [(file.str_id, file.path) for file in arranged_files]


# 特定の問題で必要とされているのファイル名のリストをRequiredFilesテーブルから取得する
def fetch_required_files(
    db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool
) -> list[ArrangedFileRecord]:
    CRUD_LOGGER.debug("call fetch_required_files")
    required_files = (
        db.query(models.RequiredFiles)
        .filter(
            models.RequiredFiles.lecture_id == lecture_id,
            models.RequiredFiles.assignment_id == assignment_id,
            models.RequiredFiles.for_evaluation == for_evaluation,
        )
        .all()
    )
    return [ArrangedFileRecord.model_validate(file) for file in required_files]


# 特定のSubmissionに対応するジャッジリクエストの属性値を変更する
# 注) SubmissionRecord.idが同じレコードがテーブル内にあること
def update_submission_record(db: Session, submission_record: SubmissionRecord) -> None:
    CRUD_LOGGER.debug("call update_submission_status")
    raw_submission_record = (
        db.query(models.Submission)
        .filter(models.Submission.id == submission_record.id)
        .first()
    )
    if raw_submission_record is None:
        raise ValueError(f"Submission with id {submission_record.id} not found")

    # assert raw_submission_record.batch_id == submission_record.batch_id
    # assert raw_submission_record.student_id == submission_record.student_id
    # assert raw_submission_record.for_evaluation == submission_record.for_evaluation
    raw_submission_record.progress = submission_record.progress.value
    raw_submission_record.total_task = submission_record.total_task
    raw_submission_record.completed_task = submission_record.completed_task
    db.commit()


def register_submission_summary_recursive(
    db: Session, submission_summary: SubmissionSummaryRecord
) -> None:
    CRUD_LOGGER.debug("register_submission_summary_recursiveが呼び出されました")
    db_submission_summary = models.SubmissionSummary()
    # sqlalchemyのモデルのフィールドに対応するもののみSubmissionSummaryレコードからコピーする
    for var, value in vars(models.SubmissionSummary).items():
        if var in submission_summary.model_fields:
            setattr(db_submission_summary, var, getattr(submission_summary, var))
    db.add(db_submission_summary)
    db.commit()
    db.refresh(db_submission_summary)

    submission_summary_id = db_submission_summary.assignment_id

    for evaluation_summary in submission_summary.evaluation_summary_list:
        evaluation_summary.parent_id = submission_summary_id
        db_evaluation_summary = models.EvaluationSummary()
        for var, value in vars(models.EvaluationSummary).items():
            if var in evaluation_summary.model_fields:
                setattr(db_evaluation_summary, var, getattr(evaluation_summary, var))
        db.add(db_evaluation_summary)
        db.commit()
        db.refresh(db_evaluation_summary)
        evaluation_summary_id = db_evaluation_summary.assignment_id

        for judge_result in evaluation_summary.judge_result_list:
            judge_result.parent_id = evaluation_summary_id
            db_judge_result = models.JudgeResult()
            for var, value in vars(models.JudgeResult).items():
                if var in judge_result.model_fields:
                    setattr(db_judge_result, var, getattr(judge_result, var))
            db.add(db_judge_result)
            db.commit()

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

    # 関連するEvaluationSummaryを一括で削除
    db.query(models.EvaluationSummary).filter(
        models.EvaluationSummary.submission_id.in_(submission_id_list)
    ).delete(synchronize_session=False)

    # 関連するSubmissionSummaryを一括で削除
    db.query(models.SubmissionSummary).filter(
        models.SubmissionSummary.submission_id.in_(submission_id_list)
    ).delete(synchronize_session=False)

    # 変更をコミット
    db.commit()


# ----------------------- end --------------------------------------------------

# ---------------- for client server -------------------------------------------


# Submissionテーブルにジャッジリクエストを追加する
def register_judge_request(
    db: Session,
    batch_id: int | None,
    user_id: str,
    lecture_id: int,
    assignment_id: int,
    for_evaluation: bool,
) -> SubmissionRecord:
    CRUD_LOGGER.debug("call register_judge_request")
    new_submission = models.Submission(
        batch_id=batch_id,
        user_id=user_id,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=for_evaluation,
    )
    db.add(new_submission)
    db.commit()
    db.refresh(new_submission)
    return SubmissionRecord.model_validate(new_submission)


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
def fetch_submission_record(db: Session, submission_id: int) -> SubmissionRecord:
    CRUD_LOGGER.debug("call fetch_judge_status")
    submission = (
        db.query(models.Submission)
        .filter(models.Submission.id == submission_id)
        .first()
    )
    if submission is None:
        raise ValueError(f"Submission with {submission_id} not found")
    return SubmissionRecord.model_validate(submission)


# 特定のジャッジリクエストに紐づいたジャッジ結果を取得する
def fetch_judge_results(db: Session, submission_id: int) -> list[JudgeResultRecord]:
    CRUD_LOGGER.debug("call fetch_judge_result")
    raw_judge_results = (
        db.query(models.JudgeResult)
        .filter(models.JudgeResult.submission_id == submission_id)
        .all()
    )
    return [
        JudgeResultRecord.model_validate(raw_result)
        for raw_result in raw_judge_results
    ]


def fetch_arranged_file_dict(
    db: Session, arranged_file_id_list: list[str]
) -> dict[str, str]:
    arranged_file_records = (
        db.query(models.ArrangedFiles)
        .filter(models.ArrangedFiles.str_id.in_(arranged_file_id_list))
        .all()
    )
    return {record.str_id: record.path for record in arranged_file_records}


def fetch_submission_summary(
    db: Session, submission_id: int
) -> SubmissionSummaryRecord:
    CRUD_LOGGER.debug("fetch_submission_summaryが呼び出されました")
    raw_submission_summary = (
        db.query(models.SubmissionSummary)
        .filter(models.SubmissionSummary.submission_id == submission_id)
        .first()
    )
    if raw_submission_summary is None:
        raise ValueError(f"提出 {submission_id} は完了していません")
    submission_summary = SubmissionSummaryRecord.model_validate(raw_submission_summary)

    # Goal: submission_summary.evaluation_summary_listを埋める

    raw_evaluation_summary_list = (
        db.query(models.EvaluationSummary)
        .filter(models.EvaluationSummary.parent_id == submission_summary.submission_id)
        .all()
    )
    
    evaluation_summary_list = [
        EvaluationSummaryRecord.model_validate(raw_evaluation_summary)
        for raw_evaluation_summary in raw_evaluation_summary_list
    ]

    for evaluation_summary in evaluation_summary_list:
        raw_judge_result_list = (
            db.query(models.JudgeResult)
            .filter(models.JudgeResult.parent_id == evaluation_summary.id)
            .all()
        )
        judge_result_list = [
            JudgeResultRecord.model_validate(raw_judge_result)
            for raw_judge_result in raw_judge_result_list
        ]
        evaluation_summary.judge_result_list = judge_result_list
        submission_summary.evaluation_summary_list.append(evaluation_summary)

    return submission_summary
