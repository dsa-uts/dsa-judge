from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Enum,
    text,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from .database import Base


class Lecture(Base):
    __tablename__ = "Lecture"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    
    # Lectureレコードと1-N関係にあるProblemレコードへの参照
    problems: list["Problem"] = relationship("Problem", back_populates="lecture")


class Problem(Base):
    __tablename__ = "Problem"
    lecture_id = Column(
        Integer, ForeignKey("Lecture.id"), primary_key=True, nullable=False
    )
    assignment_id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String(255), nullable=False)
    description_path = Column(String(255), nullable=False)
    timeMS = Column(Integer, nullable=False)
    memoryMB = Column(Integer, nullable=False)
    
    # Problemレコードと1-NまたはN-1関係にあるレコードへの参照
    lecture: Lecture = relationship("Lecture", back_populates="problems")
    executables: list["Executables"] = relationship("Executables", back_populates="problem")
    arranged_files: list["ArrangedFiles"] = relationship("ArrangedFiles", back_populates="problem")
    required_files: list["RequiredFiles"] = relationship("RequiredFiles", back_populates="problem")
    test_cases: list["TestCases"] = relationship("TestCases", back_populates="problem")


class Executables(Base):
    __tablename__ = "Executables"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"))
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"))
    eval = Column(Boolean, default=False)
    name = Column(String(255), nullable=False)
    problem: Problem = relationship("Problem", back_populates="executables")


class ArrangedFiles(Base):
    __tablename__ = "ArrangedFiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"))
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"))
    eval = Column(Boolean, default=False)
    path = Column(String(255), nullable=False)
    problem: Problem = relationship("Problem", back_populates="arranged_files")


class RequiredFiles(Base):
    __tablename__ = "RequiredFiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"))
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"))
    name = Column(String(255), nullable=False)
    problem: Problem = relationship("Problem", back_populates="required_files")


class TestCases(Base):
    __tablename__ = "TestCases"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"))
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"))
    eval = Column(Boolean, default=False)
    type = Column(Enum("Built", "Judge"), nullable=False)
    score = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(String)
    message_on_fail = Column(String(255))
    command = Column(String(255), nullable=False)
    argument_path = Column(String(255))
    stdin_path = Column(String(255))
    stdout_path = Column(String(255))
    stderr_path = Column(String(255))
    exit_code = Column(Integer, nullable=False, default=0)
    problem: Problem = relationship("Problem", back_populates="test_cases")


class Users(Base):
    __tablename__ = "Users"
    user_id = Column(String(255), primary_key=True)
    username = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum("admin", "manager", "student"), nullable=False)
    disabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )
    active_start_date = Column(DateTime, nullable=False)
    active_end_date = Column(DateTime, nullable=False)


class LoginHistory(Base):
    __tablename__ = "LoginHistory"
    user_id = Column(
        String(255), ForeignKey("Users.user_id"), primary_key=True, nullable=False
    )
    login_at = Column(DateTime, nullable=False, primary_key=True)
    logout_at = Column(DateTime, nullable=False)
    refresh_count = Column(Integer, default=0, nullable=False)
    
    user_info: Users = relationship("Users")


class BatchSubmission(Base):
    __tablename__ = "BatchSubmission"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    user_id = Column(String(255), ForeignKey("Users.user_id"))
    lecture_id = Column(Integer, ForeignKey("Lecture.id"), nullable=False)
    message = Column(String(255), nullable=True)
    complete_judge = Column(Integer, nullable=True)
    total_judge = Column(Integer, nullable=True)


class BatchSubmissionSummary(Base):
    __tablename__ = "BatchSubmissionSummary"
    batch_id = Column(Integer, ForeignKey("BatchSubmission.id"), primary_key=True)
    user_id = Column(String(255), ForeignKey("Users.user_id"), primary_key=True)
    status = Column(Enum("submitted", "delay", "non-submitted"), nullable=False)
    result = Column(Enum("AC", "WA", "TLE", "MLE", "RE", "CE", "OLE", "IE", "FN"), nullable=True, default=None)
    upload_dir = Column(String(255), nullable=True, default=None)
    report_path = Column(String(255), nullable=True, default=None)
    submit_date = Column(DateTime, nullable=True, default=None)


class Submission(Base):
    __tablename__ = "Submission"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    batch_id = Column(Integer, ForeignKey("BatchSubmission.id"), default=None)
    user_id = Column(String(255), ForeignKey("Users.user_id"), nullable=False)
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"), nullable=False)
    eval = Column(Boolean, nullable=False)
    progress = Column(Enum("pending", "queued", "running", "done"), default="pending")
    total_task = Column(Integer, nullable=False, default=0)
    completed_task = Column(Integer, nullable=False, default=0)

    uploaded_files: list["UploadedFiles"] = relationship("UploadedFiles")


class UploadedFiles(Base):
    __tablename__ = "UploadedFiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    submission_id = Column(Integer, ForeignKey("Submission.id"))
    path = Column(String(255), nullable=False)


class SubmissionSummary(Base):
    __tablename__ = "SubmissionSummary"
    submission_id = Column(Integer, ForeignKey("Submission.id"), primary_key=True)
    batch_id = Column(Integer, ForeignKey("BatchSubmission.id"), default=None)
    user_id = Column(String(255), ForeignKey("Users.user_id"), nullable=False)
    result = Column(
        Enum("AC", "WA", "TLE", "MLE", "RE", "CE", "OLE", "IE", "FN"), nullable=False
    )
    message = Column(String(255))
    detail = Column(String(255))
    score = Column(Integer, nullable=False)
    timeMS = Column(Integer, nullable=False, default=0)
    memoryKB = Column(Integer, nullable=False, default=0)
    
    judge_results: list["JudgeResult"] = relationship("JudgeResult")


class JudgeResult(Base):
    __tablename__ = "JudgeResult"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    submission_id = Column(Integer, ForeignKey("Submission.id"), nullable=False)
    testcase_id = Column(Integer, ForeignKey("TestCases.id"), nullable=False)
    result = Column(
        Enum("AC", "WA", "TLE", "MLE", "RE", "CE", "OLE", "IE"), nullable=False
    )
    timeMS = Column(Integer, nullable=False)
    memoryKB = Column(Integer, nullable=False)
    exit_code = Column(Integer, nullable=False)
    stdout = Column(String, nullable=False)
    stderr = Column(String, nullable=False)

