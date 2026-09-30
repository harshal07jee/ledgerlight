"""
Assessment and Answer models for Milestone M2 (Questionnaire without AI).
Tracks company profile, diligence progress, and question answers.
"""
from datetime import datetime
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON, Boolean, Integer
from sqlalchemy.orm import relationship
from apps.api.database import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, default="Diligence Readiness Assessment")
    
    # Company Profile Gating Attributes (PRD Section 6.2 & 6.4)
    industry = Column(String(50), nullable=False)  # HEALTHCARE, FINTECH, SOFTWARE, MANUFACTURING, ENERGY
    sub_sector = Column(String(100), nullable=False, default="ALL")
    stage = Column(String(50), nullable=False, default="Growth")  # Startup, Growth, Established, Mature
    transaction_type = Column(String(50), nullable=False, default="VC_GROWTH_FINANCING")
    geography = Column(JSON, nullable=False, default=lambda: ["USA"])
    
    status = Column(String(50), nullable=False, default="in_progress")  # in_progress, completed, archived
    target_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    organization = relationship("Organization", backref="assessments")
    answers = relationship("Answer", back_populates="assessment", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(100), nullable=False, index=True)
    
    # Stored answer value (supports bool, int, float, str, list)
    value = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    
    # Action audit per PRD 12.1
    user_action = Column(String(50), nullable=False, default="manual")  # manual, accepted, edited, rejected
    evidence_file_id = Column(String(36), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assessment = relationship("Assessment", back_populates="answers")
