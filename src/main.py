from fastapi import FastAPI, HTTPException, UploadFile, File
from contextlib import asynccontextmanager
import logging
from concurrent.futures import ThreadPoolExecutor, Future
import asyncio
from db.crud import *
from db.models import *
from db.database import SessionLocal
from sandbox.my_error import Error
from judge import JudgeInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")


class WorkerPool:
    max_workers: int
    executor: ThreadPoolExecutor
    active_jobs: dict

    def __init__(self, max_workers: int):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.active_jobs = {}

    def available_workers(self) -> int:
        return self.max_workers - len(self.active_jobs)

    def collect_completed_jobs(self) -> list:
        now_completed = [job for job, future in self.active_jobs.items() if future.done()]
        completed_jobrecord = [(job[0], job[1], future.result()) for job, future in self.active_jobs.items() if future.done()]
        for job in now_completed:
            self.active_jobs.pop(job)
        return completed_jobrecord

    def submit_job(self, job: str, func, *args, **kwargs):
        if self.available_workers() > 0:
            future = self.executor.submit(func, *args, **kwargs)
            self.active_jobs[(job, datetime.now())] = future
            return True
        return False
    
worker_pool = WorkerPool(max_workers=50)

def process_one_judge_request(submission: SubmissionRecord) -> Error:
    logger.info(f"JudgeInfo(submission_id={submission.id}, lecture_id={submission.lecture_id}, assignment_id={submission.assignment_id}, for_evaluation={submission.for_evaluation}) will be created...")
    judge_info = JudgeInfo(submission)
    logger.info("START JUDGE...")
    err = judge_info.judge()
    logger.info("END JUDGE")
    
    return err

async def process_judge_requests():
    while True:
        try:
            completed_jobrecord_list = worker_pool.collect_completed_jobs()
            for completed_jobrecord in completed_jobrecord_list:
                logger.info(f"job: \"{completed_jobrecord[0]}\", date: {completed_jobrecord[1]}, result: {completed_jobrecord[2]}")
            with SessionLocal() as db:
                num_available_workers = worker_pool.available_workers()
                queued_submissions = fetch_queued_judge_and_change_status_to_running(db, num_available_workers)
            if queued_submissions:
                logger.info(
                    f"{len(queued_submissions)}件のジャッジリクエストを取得しました。"
                )
                # スレッドプールを使用して各ジャッジリクエストを処理
                for submission in queued_submissions:
                    logger.info(f"submission: {submission}")
                    logger.info("throw judge request to thread pool...")
                    worker_pool.submit_job(f"submission-{submission.id}", process_one_judge_request, submission)
            else:
                logger.info("キューにジャッジリクエストはありません。")
        except Exception as e:
            import traceback
            logger.error(f"例外が発生しました: {type(e).__name__}: {str(e)}")
            logger.error(f"スタックトレース:\n{traceback.format_exc()}")
            logger.info("データベースに接続できない可能性があります。準備ができていない可能性があります。")

        await asyncio.sleep(5)  # 5秒待機


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("LIFESPAN LOGIC INITIALIZED...")
    task = asyncio.create_task(process_judge_requests())
    yield
    task.cancel()
    logger.info("LIFESPAN LOGIC DEACTIVATED...")
    # 現在実行しているジャッジリクエストを最後まで実行し、保留状態のものは破棄する
    worker_pool.executor.shutdown(wait=True, cancel_futures=True)
    completed_jobrecord_list = worker_pool.collect_completed_jobs()
    for completed_jobrecord in completed_jobrecord_list:
        logger.info(f"job: \"{completed_jobrecord[0]}\", date: {completed_jobrecord[1]}, result: {completed_jobrecord[2]}")
    # statusをrunningにしてしまっているタスクをqueuedに戻す
    # そして途中結果を削除する
    with SessionLocal() as db:
        undo_running_submissions(db)

app = FastAPI(lifespan=lifespan)
