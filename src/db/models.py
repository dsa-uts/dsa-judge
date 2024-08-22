from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, Enum, text, ForeignKey, ForeignKeyConstraint
from sqlalchemy.orm import relationship

from .database import Base

class Lecture(Base):
    __tablename__ = 'Lecture'
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    start_date = Column(TIMESTAMP, nullable=False)
    end_date = Column(TIMESTAMP, nullable=False)
    problems = relationship("Problem", back_populates="lecture")

class Problem(Base):
    __tablename__ = 'Problem'
    lecture_id = Column(Integer, ForeignKey('Lecture.id'), primary_key=True, nullable=False)
    assignment_id = Column(Integer, primary_key=True, nullable=False)
    for_evaluation = Column(Boolean, primary_key=True, nullable=False)
    title = Column(String(255), nullable=False)
    description_path = Column(String(255), nullable=False)
    timeMS = Column(Integer, nullable=False)
    memoryMB = Column(Integer, nullable=False)
    build_script_path = Column(String(255), nullable=False)
    executable = Column(String(255), nullable=False)
    lecture = relationship("Lecture", back_populates="problems")

class ArrangedFiles(Base):
    __tablename__ = 'ArrangedFiles'
    id = Column(Integer, primary_key=True, autoincrement=True)
    lecture_id = Column(Integer, ForeignKey('Problem.lecture_id'))
    assignment_id = Column(Integer, ForeignKey('Problem.assignment_id'))
    for_evaluation = Column(Boolean, ForeignKey('Problem.for_evaluation'))
    path = Column(String(255), nullable=False)

class RequiredFiles(Base):
    __tablename__ = 'RequiredFiles'
    id = Column(Integer, primary_key=True, autoincrement=True)
    lecture_id = Column(Integer, ForeignKey('Problem.lecture_id'))
    assignment_id = Column(Integer, ForeignKey('Problem.assignment_id'))
    for_evaluation = Column(Boolean, ForeignKey('Problem.for_evaluation'))
    name = Column(String(255), nullable=False)

class TestCases(Base):
    __tablename__ = 'TestCases'
    id = Column(Integer, primary_key=True, autoincrement=True)
    lecture_id = Column(Integer, ForeignKey('Problem.lecture_id'), nullable=False)
    assignment_id = Column(Integer, ForeignKey('Problem.assignment_id'), nullable=False)
    for_evaluation = Column(Boolean, ForeignKey('Problem.for_evaluation'), nullable=False)
    type = Column(Enum('preBuilt', 'postBuilt', 'Judge'), nullable=False)
    description = Column(String)
    score = Column(Integer)
    script_path = Column(String(255))
    argument_path = Column(String(255))
    stdin_path = Column(String(255))
    stdout_path = Column(String(255), nullable=False)
    stderr_path = Column(String(255), nullable=False)
    exit_code = Column(Integer, nullable=False, default=0)

class AdminUser(Base):
    __tablename__ = 'AdminUser'
    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)

class Student(Base):
    __tablename__ = 'Student'
    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)

class BatchSubmission(Base):
    __tablename__ = 'BatchSubmission'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    user_id = Column(String(255), ForeignKey('AdminUser.id'))

class Submission(Base):
    __tablename__ = 'Submission'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    batch_id = Column(Integer, ForeignKey('BatchSubmission.id'))
    student_id = Column(String(255), ForeignKey('Student.id'), nullable=False)
    lecture_id = Column(Integer, ForeignKey('Problem.lecture_id'), nullable=False)
    assignment_id = Column(Integer, ForeignKey('Problem.assignment_id'), nullable=False)
    for_evaluation = Column(Boolean, ForeignKey('Problem.for_evaluation'), nullable=False)
    progress = Column(Enum('pending', 'queued', 'running', 'done'), default='pending')
    prebuilt_result = Column(Enum('Unprocessed', 'AC', 'WA', 'TLE', 'MLE', 'CE', 'RE', 'OLE', 'IE'), default='Unprocessed')
    postbuilt_result = Column(Enum('Unprocessed', 'AC', 'WA', 'TLE', 'MLE', 'CE', 'RE', 'OLE', 'IE'), default='Unprocessed')
    judge_result = Column(Enum('Unprocessed', 'AC', 'WA', 'TLE', 'MLE', 'CE', 'RE', 'OLE', 'IE'), default='Unprocessed')
    message = Column(String(255), default='')

class UploadedFiles(Base):
    __tablename__ = 'UploadedFiles'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    submission_id = Column(Integer, ForeignKey('Submission.id'))
    path = Column(String(255), nullable=False)

class JudgeResult(Base):
    __tablename__ = 'JudgeResult'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    submission_id = Column(Integer, ForeignKey('Submission.id'))
    testcase_id = Column(Integer, ForeignKey('TestCases.id'))
    timeMS = Column(Integer, nullable=False)
    memoryKB = Column(Integer, nullable=False)
    exit_code = Column(Integer, nullable=False)
    stdout = Column(String, nullable=False)
    stderr = Column(String, nullable=False)
    result = Column(Enum('AC', 'WA', 'TLE', 'MLE', 'CE', 'RE', 'OLE', 'IE'), nullable=False)

