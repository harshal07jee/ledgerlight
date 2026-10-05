"""
SQLAlchemy models for Score Runs and Trace Rows (PRD Section 8 & 14).
Stores deterministic score outputs, versioning tags, and per-deduction trace lines.
"""
from datetime import datetime
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON, Boolean, Float, Integer
from sqlalchemy.orm import relationship
from apps.api.database import Base


class ScoreRun(Base):
    __tablename__ = "score_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Scores
    overall_score = Column(Float, nullable=False)
    unconstrained_score = Column(Float, nullable=False)
    best_case_score = Column(Float, nullable=True)
    worst_case_score = Column(Float, nullable=True)
    completeness_pct = Column(Float, nullable=False)
    is_provisional = Column(Boolean, nullable=False, default=False)
    critical_cap_applied = Column(Boolean, nullable=False, default=False)
    failed_critical_count = Column(Integer, nullable=False, default=0)
    
    # Dimension Breakdown & Critical items snapshot
    dimension_scores = Column(JSON, nullable=False)
    failed_critical_items = Column(JSON, nullable=False, default=list)
    weight_origin_share = Column(JSON, nullable=True)
    unscored_disclosures = Column(JSON, nullable=True)
    scored_question_review_status = Column(JSON, nullable=True)
    
    # Audit & Versioning (PRD 8.7)
    config_version = Column(String(50), nullable=False, default="1.0.0")
    question_bank_version = Column(String(50), nullable=False, default="1.0.0")
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    assessment = relationship("Assessment", backref="score_runs")
    trace_rows = relationship("ScoreTraceRow", back_populates="score_run", cascade="all, delete-orphan", order_by="ScoreTraceRow.points_lost.desc()")


class ScoreTraceRow(Base):
    __tablename__ = "score_trace_rows"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    score_run_id = Column(String(36), ForeignKey("score_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(100), nullable=False, index=True)
    
    question_text = Column(Text, nullable=False)
    dimension = Column(String(50), nullable=False)
    risk_weight = Column(String(20), nullable=False)  # CRITICAL, HIGH, MEDIUM, LOW
    weight_value = Column(Float, nullable=False)       # 8, 5, 3, 1
    
    answer_state = Column(String(20), nullable=False)  # PASS, PARTIAL, FAIL, UNVERIFIED
    user_answer = Column(JSON, nullable=True)
    expected_rule = Column(Text, nullable=False)
    points_lost = Column(Float, nullable=False)        # weight * (1 - score)
    
    # Source Citations
    source_doc = Column(String(255), nullable=True)
    source_ref = Column(String(255), nullable=True)
    evidence_snippet = Column(Text, nullable=True)
    answer_origin = Column(String(50), nullable=False, default="manual")  # manual, auto_filled, confirmed
    origin = Column(String(50), nullable=True)                            # self-attested, evidence-backed
    
    notes = Column(Text, nullable=True)
    is_critical_fail = Column(Boolean, nullable=False, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    score_run = relationship("ScoreRun", back_populates="trace_rows")

