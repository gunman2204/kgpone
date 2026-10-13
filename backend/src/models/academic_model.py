import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Enum, Text, ForeignKey, DateTime, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base
from src.models.system_model import DeletionStatus
from src.models.common import utcnow

class SemesterType(str, enum.Enum):
    AUTUMN = "AUTUMN"
    SPRING = "SPRING"
    SUMMER = "SUMMER"

class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationship
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="department", cascade="all, delete-orphan")

class CoursePrerequisite(Base):
    __tablename__ = "course_prerequisites"
    __table_args__ = (UniqueConstraint('course_id', 'prerequisite_id'),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    prerequisite_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deletion_status: Mapped[str] = mapped_column(String(50), default=DeletionStatus.NONE)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    department: Mapped["Department"] = relationship("Department", back_populates="courses")
    offerings: Mapped[list["CourseOffering"]] = relationship("CourseOffering", back_populates="course", cascade="all, delete-orphan")
    prerequisites: Mapped[list["Course"]] = relationship(
        "Course",
        secondary="course_prerequisites",
        primaryjoin="Course.id==CoursePrerequisite.course_id",
        secondaryjoin="Course.id==CoursePrerequisite.prerequisite_id",
        backref="prerequisite_for"
    )

class CourseOffering(Base):
    __tablename__ = "course_offerings"
    __table_args__ = (UniqueConstraint('course_id', 'year', 'semester'),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    semester: Mapped[SemesterType] = mapped_column(Enum(SemesterType), nullable=False)

    # Relationships
    course: Mapped["Course"] = relationship("Course", back_populates="offerings")
    faculty: Mapped[list["FacultyInfo"]] = relationship("FacultyInfo", back_populates="course_offering", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(
        "Document", 
        back_populates="course_offering", 
        cascade="all, delete-orphan",
        primaryjoin="CourseOffering.id == Document.course_offering_id"
    )

class FacultyInfo(Base):
    __tablename__ = "faculty_info"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_offering_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("course_offerings.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False) # 'Professor', 'TA', 'Coordinator'
    office_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationship
    course_offering: Mapped["CourseOffering"] = relationship("CourseOffering", back_populates="faculty")
