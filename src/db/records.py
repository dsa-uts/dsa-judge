from dataclasses import dataclass, field
from datetime import datetime
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
    expected_stdout: str | None
    expected_stderr: str | None
    expected_exit_code: int = 0
    # テーブル挿入時に自動で決まる値
    id: int = 1 # テーブルに挿入する際は自動設定されるので、コンストラクタで指定する必要が無いように適当な値を入れている
    ts: datetime = datetime(1998, 6, 6, 12, 32, 41)

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
    judge_result_list: list[JudgeResultRecord] = field(default_factory=list)

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
    evaluation_summary_list: list[EvaluationSummaryRecord] = field(default_factory=list)
