"""
SQLAlchemy model for Diligence Remediation Roadmap Tasks (PRD Section 9.1 & FR-8).
Tracks remediation horizon buckets (30/60/90/180), task completion, assignments, and comments.
"""
from datetime import datetime
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON, Float, Integer
from sqlalchemy.orm import relationship
from apps.api.database import Base


class RoadmapTask(Base):
    __tablename__ = "roadmap_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(100), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)  # Playbook text from question bank only
    dimension = Column(String(50), nullable=False)
    sub_category = Column(String(100), nullable=False, default="General")
    horizon_days = Column(Integer, nullable=False, default=90)  # 30, 60, 90, 180

    risk_weight = Column(String(20), nullable=False)  # CRITICAL, HIGH, MEDIUM, LOW
    weight_value = Column(Float, nullable=False)
    points_recoverable = Column(Float, nullable=False)
    priority_score = Column(Float, nullable=False)  # weight_value * points_recoverable

    source_doc = Column(String(255), nullable=True)
    source_ref = Column(String(255), nullable=True)

    status = Column(String(50), nullable=False, default="todo")  # todo, in_progress, done
    assignee = Column(String(255), nullable=True)
    comments = Column(JSON, nullable=False, default=list)  # list of {id, author, text, created_at}

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assessment = relationship("Assessment", backref="roadmap_tasks")
