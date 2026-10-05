"""
SQLAlchemy models for Data Room and Deterministic Extraction (PRD Section 7 & FR-3, FR-4).
Tracks uploaded document metadata (raw binary is deleted after processing) and extraction proposals.
"""
from datetime import datetime
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON, Boolean, Float, Integer
from sqlalchemy.orm import relationship
from apps.api.database import Base


class DataRoomDocument(Base):
    __tablename__ = "data_room_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False, default="unclassified")  # financial_statement, cap_table, bank_statement, customer_contract, policy, certificate_or_report, other, unclassified
    file_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    mime_type = Column(String(100), nullable=False)
    page_count = Column(Integer, nullable=False, default=1)
    
    # Ingestion status: pending -> parsing -> classifying -> extracting -> completed / failed
    status = Column(String(50), nullable=False, default="pending")
    stage = Column(String(50), nullable=False, default="uploaded")
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assessment = relationship("Assessment", backref="documents")
    extractions = relationship("ProposedExtraction", back_populates="document", cascade="all, delete-orphan")


class ProposedExtraction(Base):
    __tablename__ = "proposed_extractions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("data_room_documents.id", ondelete="SET NULL"), nullable=True, index=True)
    question_id = Column(String(100), nullable=False, index=True)
    
    # Answer proposal
    answer_value = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)  # 0.0 to 1.0
    status = Column(String(50), nullable=False, default="MANUAL_REQUIRED")  # AUTO_FILLED, NEEDS_CONFIRMATION, MANUAL_REQUIRED
    method = Column(String(50), nullable=False, default="MANUAL")  # FINANCIAL_TABLE, CERTIFICATE_OR_REPORT, POLICY_DOC, MANUAL
    
    # Evidence Citation (Strict PRD 11.2: snippets <= 500 chars)
    source_file = Column(String(255), nullable=True)
    page = Column(Integer, nullable=True, default=1)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    snippet = Column(String(500), nullable=True)
    
    # Financial table transparency
    formula = Column(Text, nullable=True)
    formula_inputs = Column(JSON, nullable=True)
    
    # Model and score gating (PRD 7.4 & 12.1)
    model_name = Column(String(100), nullable=True)
    model_version = Column(String(50), nullable=True)
    raw_score = Column(Float, nullable=True)
    calibrated_score = Column(Float, nullable=True)
    time_to_confirm_ms = Column(Integer, nullable=True)

    # Review & Confirmation (PRD 7.1)
    user_action = Column(String(50), nullable=False, default="pending")  # pending, accepted, edited, rejected
    confirmed_value = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    document = relationship("DataRoomDocument", back_populates="extractions")


class ExtractionAuditLog(Base):
    """
    Structured extraction audit log per PRD Section 12.1.
    Tracks model scores, user actions, and confirmation latencies.
    CRITICAL SAFETY INVARIANT: Strictly NO document text or passage content is stored in this log.
    """
    __tablename__ = "extraction_audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(100), nullable=False, index=True)
    method = Column(String(50), nullable=False)  # CUAD_EXTRACTIVE_QA, FINANCIAL_TABLE, etc.
    model_name = Column(String(100), nullable=True)
    model_version = Column(String(50), nullable=True)
    raw_score = Column(Float, nullable=False)
    calibrated_score = Column(Float, nullable=True)
    status = Column(String(50), nullable=False)  # AUTO_FILLED, NEEDS_CONFIRMATION, MANUAL_REQUIRED
    user_action = Column(String(50), nullable=True)  # accepted, edited, rejected, pending
    final_value = Column(JSON, nullable=True)
    time_to_confirm_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

