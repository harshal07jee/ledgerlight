"""
M6 Test Suite: CUAD Contract Clause Extraction and Confidence Gating (PRD 7.4, 7.5, 12.1).

Verifies:
1. Model metadata (exact repo id, license, download size, CPU execution).
2. All CONTRACT_CLAUSE questions mapped to official 41 CUAD categories.
3. Sliding window tokenization & handling for long documents (length 384, stride 128).
4. No-answer detection (negative contracts).
5. Exact boundary cases at 0.85 and 0.50.
6. Status assignment: pure presence auto-fills above 0.85; compliance clauses propose "Clause found" with NEEDS_CONFIRMATION.
7. PRD 12.1 Structured Audit Logging: strictly ZERO document text in logs.
8. Air-gap guarantee: runs locally on CPU, no document text leaves the machine.
9. Score labeled "model score", never "probability".
10. Calibration hook (temperature scaling).
"""
import os
import pytest
from apps.api.core.cuad import (
    verify_model_metadata,
    extract_best_clause_span,
    gate_cuad_extraction,
    calibrate_score,
    create_extraction_audit_log_entry,
    CUAD_41_CATEGORIES,
    CUAD_CATEGORIES_SET,
    CONTRACT_QUESTION_TO_CUAD,
    PURE_PRESENCE_QUESTIONS,
    T_HIGH_DEFAULT,
    T_LOW_DEFAULT,
    CUAD_MODEL_REPO,
    CUAD_MODEL_VERSION,
    CUAD_DOWNLOAD_SIZE_BYTES,
    CUAD_LICENSE,
)
from apps.api.models.data_room import ExtractionAuditLog


def test_cuad_model_metadata_and_license():
    """
    PRD 7.4 Requirement:
    Verify exact repo id, license, download size, and CPU local execution.
    """
    meta = verify_model_metadata()
    assert meta["repo_id"] == "Mjolnirslams/roberta-base-squad2-cuad"
    assert meta["license"] == "cc-by-4.0"
    assert meta["size_bytes"] == 496250208
    assert meta["size_mb"] == 473.26
    assert meta["parameters"] == 124056578
    assert meta["air_gap_compliant"] is True
    assert meta["device"] == "cpu"


def test_all_contract_clause_questions_mapped_to_41_official_cuad_categories():
    """
    PRD 7.4 Requirement:
    - Every mapped category must be in the official 41 CUAD categories (exact match).
    - Every mapped question ID must exist in the database with evidence_type='CONTRACT_CLAUSE'.
    - Ambiguous or non-matching questions (litigation, royalties, side letters) must NOT be mapped.
    """
    from apps.api.database import SessionLocal
    from apps.api.models.question import Question

    assert len(CUAD_41_CATEGORIES) == 41, "Must contain exactly 41 official CUAD categories"
    
    # Verify every mapped question maps to a valid category in the 41 official set
    for qid, cat in CONTRACT_QUESTION_TO_CUAD.items():
        assert cat in CUAD_41_CATEGORIES, f"Question {qid} mapped to invalid CUAD category '{cat}'"

    # Verify every mapped question ID exists in the database
    db = SessionLocal()
    try:
        db_questions = {
            q.question_id: q for q in db.query(Question).filter(Question.evidence_type == "CONTRACT_CLAUSE").all()
        }
        assert len(db_questions) == 35, f"Expected 35 CONTRACT_CLAUSE questions in DB, got {len(db_questions)}"
        
        for qid in CONTRACT_QUESTION_TO_CUAD.keys():
            assert qid in db_questions, f"Mapped question {qid} does not exist in the database!"

        # Specific safety exclusions: non-matching questions must NOT be mapped (must be NONE - manual)
        # Litigation
        assert "CORE_LEGAL_01" not in CONTRACT_QUESTION_TO_CUAD
        # Royalties / earn-outs
        assert "CORE_CASH_FLOW_08" not in CONTRACT_QUESTION_TO_CUAD
        # Side letters
        assert "CORE_TXN_01" not in CONTRACT_QUESTION_TO_CUAD
        # Breach / default
        assert "CORE_LEGAL_02" not in CONTRACT_QUESTION_TO_CUAD
        # PPAs
        assert "ENERGY_06" not in CONTRACT_QUESTION_TO_CUAD
        assert "ENG_PHASE1_01" not in CONTRACT_QUESTION_TO_CUAD
        # BaaS
        assert "FIN_TECH_10" not in CONTRACT_QUESTION_TO_CUAD
    finally:
        db.close()


def test_window_handling_long_documents():
    """
    PRD 7.4 Requirement:
    Long documents: sliding windows (max length 384, stride 128).
    Extracts the best span across overlapping windows.
    """
    # Create a long synthetic contract with ~800 words, placing the target clause in the middle
    preamble = "General commercial preamble text and definitions. " * 60
    target_clause = (
        "Section 14.2 Most Favored Nation: Provider represents and warrants that "
        "the pricing, discount terms, and service credits offered to Customer hereunder "
        "shall be no less favorable than those offered to any other commercial customer."
    )
    postamble = "Additional boilerplate terms, governing law, and notices. " * 60
    long_contract = f"{preamble}\n\n{target_clause}\n\n{postamble}"

    res = extract_best_clause_span(long_contract, "Most Favored Nation", max_length=384, stride=128)
    assert res is not None
    assert res["clause_found"] is True
    assert res["model_score"] > 0.60
    assert "Most Favored Nation" in res["span_text"] or "pricing" in res["span_text"]
    assert res["char_start"] > 0


def test_no_answer_detection_on_negative_contracts():
    """
    PRD 7.4 Requirement:
    Negative control: When the contract does NOT contain the target clause,
    comparing span score with no-answer score results in clause_found=False.
    """
    nda_text = (
        "This Non-Disclosure Agreement is entered into by and between the parties solely "
        "for the purpose of evaluating a potential commercial transaction. Both parties agree "
        "to maintain confidentiality. Governing law shall be the State of Delaware."
    )
    # Query for a clause that is completely absent
    res = extract_best_clause_span(nda_text, "Revenue/Profit Sharing")
    assert res["clause_found"] is False
    assert res["model_score"] < T_LOW_DEFAULT


def test_boundary_cases_at_exactly_85_and_50():
    """
    PRD 7.5 Requirement:
    Boundary cases at exactly 0.85 and 0.50:
    - At 0.85: pure presence is AUTO_FILLED; compliance is NEEDS_CONFIRMATION.
    - At 0.8499: strictly NEEDS_CONFIRMATION (never AUTO_FILLED).
    - At 0.50: NEEDS_CONFIRMATION.
    - At 0.4999: MANUAL_REQUIRED.
    """
    # 1. Pure presence question at exactly 0.85 -> AUTO_FILLED
    q_presence = "CORE_CUST_02"  # MFN customer agreements (pure presence)
    gated_85_presence = gate_cuad_extraction(q_presence, {
        "model_score": 0.85,
        "cuad_category": "Most Favored Nation",
        "span_text": "Sample MFN Clause"
    })
    assert gated_85_presence["status"] == "AUTO_FILLED"
    assert gated_85_presence["confidence"] == 0.85

    # 2. Compliance question at exactly 0.85 -> NEEDS_CONFIRMATION (evidence, not verdict)
    q_compliance = "CORE_TXN_02"  # Change of control consent requirements (compliance/qualitative)
    gated_85_compliance = gate_cuad_extraction(q_compliance, {
        "model_score": 0.85,
        "cuad_category": "Change Of Control",
        "span_text": "Consent required for change of control"
    })
    assert gated_85_compliance["status"] == "NEEDS_CONFIRMATION"

    # 3. Just below 0.85 (0.8499) on pure presence -> strictly NEEDS_CONFIRMATION
    gated_sub_85 = gate_cuad_extraction(q_presence, {
        "model_score": 0.8499,
        "cuad_category": "Most Favored Nation",
        "span_text": "Sample MFN Clause"
    })
    assert gated_sub_85["status"] == "NEEDS_CONFIRMATION"
    assert gated_sub_85["status"] != "AUTO_FILLED"

    # 4. At exactly 0.50 (T_low) -> NEEDS_CONFIRMATION
    gated_50 = gate_cuad_extraction(q_presence, {
        "model_score": 0.50,
        "cuad_category": "Most Favored Nation",
        "span_text": "Sample MFN Clause"
    })
    assert gated_50["status"] == "NEEDS_CONFIRMATION"

    # 5. Just below 0.50 (0.4999) -> MANUAL_REQUIRED
    gated_sub_50 = gate_cuad_extraction(q_presence, {
        "model_score": 0.4999,
        "cuad_category": "Most Favored Nation",
        "span_text": "Sample MFN Clause"
    })
    assert gated_sub_50["status"] == "MANUAL_REQUIRED"


def test_clause_span_is_evidence_not_verdict():
    """
    PRD 7.5 Requirement:
    A clause span is evidence, not a verdict. 'Clause found' proposes an answer
    and highlights the passage; the user decides compliance.
    Only pure presence questions may AUTO_FILL (and only above T_high); everything else is NEEDS_CONFIRMATION.
    """
    # Compliance question with high model score (0.96)
    res = gate_cuad_extraction("CORE_TXN_02", {
        "model_score": 0.96,
        "cuad_category": "Change Of Control",
        "span_text": "Counterparty consent required upon change of control transaction."
    })
    assert res["status"] == "NEEDS_CONFIRMATION", "Compliance clause must NEVER auto-fill"
    assert res["answer_value"] == "Clause found: Change Of Control"
    assert "Counterparty consent" in res["snippet"]


def test_score_labeling_is_model_score_not_probability():
    """
    PRD 7.5 Requirement:
    Label scores 'model score', not 'probability'.
    """
    res = extract_best_clause_span("Sample text with non-compete clause for 12 months", "Non-Compete")
    assert "model_score" in res
    assert "probability" not in res


def test_prd_12_1_structured_logging_has_zero_document_text():
    """
    PRD 12.1 Requirement:
    Logging per PRD 12.1: assessment_id, question_id, method, model name and version,
    raw score, calibrated score (nullable), status, user_action, final_value, time_to_confirm_ms.
    CRITICAL INVARIANT: No document text in logs!
    """
    gated = {
        "model_score": 0.92,
        "calibrated_score": 0.90,
        "status": "AUTO_FILLED",
        "answer_value": True,
        "span_text": "CONFIDENTIAL HIGHLY SENSITIVE CONTRACT PARAGRAPH"
    }
    log_entry = create_extraction_audit_log_entry(
        assessment_id="asmt-12345",
        question_id="CORE_CUST_02",
        gated_result=gated,
        user_action="accepted",
        final_value=True,
        time_to_confirm_ms=1450
    )

    # Required PRD 12.1 fields
    assert log_entry["assessment_id"] == "asmt-12345"
    assert log_entry["question_id"] == "CORE_CUST_02"
    assert log_entry["method"] == "CUAD_EXTRACTIVE_QA"
    assert log_entry["model_name"] == CUAD_MODEL_REPO
    assert log_entry["model_version"] == CUAD_MODEL_VERSION
    assert log_entry["raw_score"] == 0.92
    assert log_entry["calibrated_score"] == 0.90
    assert log_entry["status"] == "AUTO_FILLED"
    assert log_entry["user_action"] == "accepted"
    assert log_entry["final_value"] is True
    assert log_entry["time_to_confirm_ms"] == 1450

    # STRICT SAFETY INVARIANT: No document text in log!
    log_str = str(log_entry).lower()
    assert "confidential highly sensitive" not in log_str
    assert "span_text" not in log_entry
    assert "snippet" not in log_entry
    assert "passage" not in log_entry
    assert "text" not in log_entry

    # Verify SQLAlchemy model schema conforms to zero-text invariant
    columns = [col.name for col in ExtractionAuditLog.__table__.columns]
    assert "snippet" not in columns
    assert "passage" not in columns
    assert "text" not in columns
    assert "contract_text" not in columns


def test_calibration_hook():
    """
    PRD 7.5 Requirement:
    Calibration hook (temperature scaling or isotonic regression) that is off until a labeled set exists.
    """
    # Default: calibration is off -> returns None
    from apps.api.core import cuad
    cuad.CALIBRATION_ENABLED = False
    assert calibrate_score(0.85, "Non-Compete") is None

    # When calibration is enabled
    cuad.CALIBRATION_ENABLED = True
    cal = calibrate_score(0.85, "Non-Compete")
    assert cal is not None
    assert 0.0 < cal < 1.0
    # Reset to default
    cuad.CALIBRATION_ENABLED = False
