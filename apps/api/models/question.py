"""
SQLAlchemy Question and QuestionVersion models matching PRD Section 6.2.
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from apps.api.database import Base


class Question(Base):
    __tablename__ = "questions"

    question_id = Column(String(100), primary_key=True)
    scope = Column(String(20), nullable=False, default="BRANCH")  # CORE, BRANCH
    industry = Column(String(100), nullable=False, default="UNIVERSAL")
    sub_sector = Column(String(100), nullable=False, default="ALL")
    geography = Column(JSON, nullable=False, default=lambda: ["USA"])
    stage = Column(JSON, nullable=False, default=lambda: ["ALL"])
    dimension = Column(String(50), nullable=False)
    sub_category = Column(String(100), nullable=True, default="")
    question_text = Column(Text, nullable=False)
    input_type = Column(String(50), nullable=False, default="BOOLEAN")
    options = Column(JSON, nullable=True)
    depends_on = Column(JSON, nullable=True)
    risk_weight = Column(String(20), nullable=False, default="MEDIUM")
    pass_rule = Column(JSON, nullable=True)
    evidence_type = Column(String(50), nullable=False, default="SELF_ATTESTED")
    extraction_hint = Column(JSON, nullable=True)
    remediation_action = Column(Text, nullable=True, default="")
    remediation_horizon_days = Column(Integer, nullable=False, default=90)
    source_doc = Column(String(255), nullable=True, default="")
    source_ref = Column(String(255), nullable=True, default="")
    last_verified_on = Column(String(50), nullable=True)
    reviewer_name = Column(String(100), nullable=True)
    review_status = Column(String(20), nullable=False, default="DRAFT")  # DRAFT, APPROVED, UNREVIEWED_SEED, DEPRECATED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    versions = relationship("QuestionVersion", back_populates="question", cascade="all, delete-orphan")


class QuestionVersion(Base):
    __tablename__ = "question_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(String(100), ForeignKey("questions.question_id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False)
    changed_by = Column(String(100), nullable=True)
    change_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    question = relationship("Question", back_populates="versions")
