from pydantic import BaseModel, Field, field_serializer
from datetime import datetime
from enum import Enum


class SubmissionProgressStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"


# 実行結果の集約をするための、順序定義
# 各テストケースの実行結果が、["AC", "WA", "AC", "TLE"]の場合、
# 全体の結果はmaxを取って"TLE"となる。
JudgeStatusOrder: dict[str, int] = {
    # (value) : (order)
    "AC": 0,  # Accepted
    "WA": 1,  # Wrong Answer
    "TLE": 2,  # Time Limit Exceed
    "MLE": 3,  # Memory Limit Exceed
    "RE": 4,  # Runtime Error
    "CE": 5,  # Compile Error
    "OLE": 6,  # Output Limit Exceed (8000 bytes)
    "IE": 7,  # Internal Error (e.g., docker sandbox management)
    "FN": 8,  # File Not found
}


class BaseJudgeStatusWithOrder(Enum):
    def __str__(self):
        return self.name

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return JudgeStatusOrder[self.value] < JudgeStatusOrder[other.value]
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return JudgeStatusOrder[self.value] > JudgeStatusOrder[other.value]
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return JudgeStatusOrder[self.value] <= JudgeStatusOrder[other.value]
        return NotImplemented

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return JudgeStatusOrder[self.value] >= JudgeStatusOrder[other.value]
        return NotImplemented


class SingleJudgeStatus(BaseJudgeStatusWithOrder):
    AC = "AC"  # Accepted
    WA = "WA"  # Wrong Answer
    TLE = "TLE"  # Time Limit Exceed
    MLE = "MLE"  # Memory Limit Exceed
    RE = "RE"  # Runtime Error
    CE = "CE"  # Compile Error
    OLE = "OLE"  # Output Limit Exceed (8000 bytes)
    IE = "IE"  # Internal Error (e.g., docker sandbox management)


class EvaluationSummaryStatus(BaseJudgeStatusWithOrder):
    AC = "AC"  # Accepted
    WA = "WA"  # Wrong Answer
    TLE = "TLE"  # Time Limit Exceed
    MLE = "MLE"  # Memory Limit Exceed
    RE = "RE"  # Runtime Error
    CE = "CE"  # Compile Error
    OLE = "OLE"  # Output Limit Exceed (8000 bytes)
    IE = "IE"  # Internal Error (e.g., docker sandbox management)


class SubmissionSummaryStatus(BaseJudgeStatusWithOrder):
    AC = "AC"  # Accepted
    WA = "WA"  # Wrong Answer
    TLE = "TLE"  # Time Limit Exceed
    MLE = "MLE"  # Memory Limit Exceed
    RE = "RE"  # Runtime Error
    CE = "CE"  # Compile Error
    OLE = "OLE"  # Output Limit Exceed (8000 bytes)
    IE = "IE"  # Internal Error (e.g., docker sandbox management)
    FN = "FN"  # File Not found


class SubmissionRecord(BaseModel):
    id: int
    ts: datetime
    batch_id: int | None
    user_id: str
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    progress: SubmissionProgressStatus
    total_task: int = Field(default=0)
    completed_task: int = Field(default=0)

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }

    @field_serializer("progress")
    def serialize_progress(self, progress: SubmissionProgressStatus, _info):
        return progress.value


class ArrangedFileRecord(BaseModel):
    str_id: str
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    path: str

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }


class TestCaseRecord(BaseModel):
    id: int
    eval_id: str
    description: str | None
    command: str  # nullable=False
    argument_path: str | None
    stdin_path: str | None
    stdout_path: str | None
    stderr_path: str | None
    exit_code: int  # default: 0

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }


class EvaluationType(Enum):
    Built = "Built"
    Judge = "Judge"


class EvaluationItemRecord(BaseModel):
    str_id: str
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    title: str
    description: str | None
    score: int
    type: EvaluationType
    arranged_file_id: str | None
    message_on_fail: str | None
    # 紐づいているTestCaseRecordのリスト
    testcase_list: list[TestCaseRecord] = Field(default_factory=list)

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }

    @field_serializer("type")
    def serialize_type(self, type: EvaluationType, _info):
        return type.value


class ProblemRecord(BaseModel):
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    title: str
    description_path: str
    timeMS: int
    memoryMB: int
    # 紐づいているEvaluationItemRecordのリスト
    evaluation_item_list: list[EvaluationItemRecord] = Field(default_factory=list)

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }


class JudgeResultRecord(BaseModel):
    parent_id: int = Field(default=0)
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
    expected_exit_code: int = Field(default=0)
    # テーブル挿入時に自動で決まる値
    id: int = Field(default=0)
    ts: datetime = Field(default_factory=lambda: datetime(1998, 6, 6, 12, 32, 41))

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }

    @field_serializer("result")
    def serialize_result(self, result: SingleJudgeStatus, _info):
        return result.value


class EvaluationSummaryRecord(BaseModel):
    parent_id: int = Field(default=0)
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
    eval_title: str  # EvaluationItems.title
    eval_description: str | None  # EvaluationItems.description
    eval_type: EvaluationType  # EvaluationItems.type
    arranged_file_path: str | None  # Arrangedfiles.path
    # テーブルに挿入時に自動で値が決まるフィールド
    id: int = Field(default=0)  # auto increment PK
    # 以降、クライアントで必要になるフィールド
    judge_result_list: list[JudgeResultRecord] = Field(default_factory=list)

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }

    @field_serializer("result")
    def serialize_result(self, result: EvaluationSummaryStatus, _info):
        return result.value


class SubmissionSummaryRecord(BaseModel):
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
    evaluation_summary_list: list[EvaluationSummaryRecord] = Field(default_factory=list)

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }

    @field_serializer("result")
    def serialize_result(self, result: SubmissionSummaryStatus, _info):
        return result.value


class EvaluationResultRecord(BaseModel):
    user_id: str
    lecture_id: int
    score: int | None
    report_path: str | None
    comment: str | None

    model_config = {"from_attributes": True}
