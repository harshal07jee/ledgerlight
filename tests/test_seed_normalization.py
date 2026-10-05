"""
Unit tests for Seed Normalization, Schema Integrity, ID Migration, Core Bank, and Date Sensitivity (PRD Section 6.2 & M1 Cleanup).
"""
import os
import json
import csv
import re
import pytest
from apps.api.database import SessionLocal
from apps.api.models import Question
from packages.schema.models import QuestionSchema, DimensionEnum


def test_seed_normalization_output_exists():
    assert os.path.exists("data/seeds/normalized_branch_questions.json")
    assert os.path.exists("data/seeds/normalized_branch_questions.csv")
    assert os.path.exists("data/seeds/seed_merge_report.csv")
    assert os.path.exists("data/seeds/id_migration_map.csv")
    assert os.path.exists("data/seeds/date_sensitive_rows.csv")
    assert os.path.exists("data/seeds/draft_universal_core.json")
    assert os.path.exists("data/seeds/draft_universal_core.csv")
    assert os.path.exists("data/seeds/coverage_report.md")
    assert os.path.exists("data/seeds/possible_duplicates.csv")


def test_id_migration_map_conforms_to_pattern():
    with open("data/seeds/id_migration_map.csv", "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) >= 30, f"Expected >= 30 migrated IDs, found {len(reader)}"

        pattern = re.compile(r"^[A-Z]{3,4}(_[A-Z0-9]+)*_\d{2}$")
        for row in reader:
            old_id = row["old_id"]
            new_id = row["new_id"]
            assert pattern.match(new_id), f"New ID {new_id} does not follow valid question bank pattern (migrated from {old_id})"
            # Assert no truncated suffixes remain in new_id
            assert not new_id.endswith("_ALT"), f"New ID {new_id} still contains _ALT"
            assert len(new_id.split("_")) in (2, 3), f"New ID {new_id} must have 2 or 3 underscore-delimited components"


def test_universal_core_dimensions_have_at_least_8_questions():
    with open("data/seeds/draft_universal_core.json", "r", encoding="utf-8") as f:
        core_q = json.load(f)

    # 88 total questions (exactly 8 per each of the 11 dimensions)
    assert len(core_q) >= 88

    dim_counts = {}
    for q in core_q:
        d = q["dimension"]
        dim_counts[d] = dim_counts.get(d, 0) + 1
        # Review status must be either DRAFT or AI_PRE_REVIEWED; NEVER APPROVED
        assert q["review_status"] in ("DRAFT", "AI_PRE_REVIEWED"), f"Core row {q['question_id']} must be DRAFT or AI_PRE_REVIEWED"
        assert q["review_status"] != "APPROVED", f"Core row {q['question_id']} must NEVER be APPROVED"
        assert q["source_doc"] != "", f"Core row {q['question_id']} missing source_doc"
        assert q["source_ref"] != "", f"Core row {q['question_id']} missing source_ref section citation"

    # The 11 Universal Core dimensions (excluding the 12th branch dimension INDUSTRY_REG)
    core_dims = [d for d in DimensionEnum if d != DimensionEnum.INDUSTRY_REG]
    assert len(core_dims) == 11

    for dim in core_dims:
        assert dim.value in dim_counts, f"Dimension {dim.value} missing from core bank"
        assert dim_counts[dim.value] >= 8, f"Dimension {dim.value} has only {dim_counts[dim.value]} questions (requires >= 8)"


def test_date_sensitive_rows_are_marked_draft():
    with open("data/seeds/date_sensitive_rows.csv", "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) > 0

    with open("data/seeds/normalized_branch_questions.json", "r", encoding="utf-8") as f:
        branch_q = {q["question_id"]: q for q in json.load(f)}

    for row in reader:
        qid = row["question_id"]
        assert row["review_status"] == "DRAFT"
        assert row["claim_to_verify"] != ""
        if qid in branch_q:
            assert branch_q[qid]["review_status"] == "DRAFT", f"Date-sensitive question {qid} must be marked DRAFT"


def test_seed_merge_report_integrity():
    with open("data/seeds/seed_merge_report.csv", "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) > 0

        # Check required columns
        expected_cols = {"original_id", "normalized_id", "action", "source_file", "question_text", "notes"}
        assert expected_cols.issubset(set(reader[0].keys()))

        actions = [r["action"] for r in reader]
        assert "RETAINED" in actions
        assert "MERGED_DUPLICATE" in actions
        assert "RESOLVED_ID_COLLISION" in actions


def test_normalized_questions_conform_to_schema():
    with open("data/seeds/normalized_branch_questions.json", "r", encoding="utf-8") as f:
        branch_q = json.load(f)
    with open("data/seeds/draft_universal_core.json", "r", encoding="utf-8") as f:
        core_q = json.load(f)

    all_q = branch_q + core_q
    assert len(all_q) >= 200

    qids = set()
    for q in all_q:
        # Validate against strict Pydantic model
        model = QuestionSchema(**q)
        assert model.question_id not in qids, f"Duplicate question_id detected: {model.question_id}"
        qids.add(model.question_id)

        # Dimension validation
        valid_dims = {d.value for d in DimensionEnum}
        assert model.dimension in valid_dims, f"Invalid dimension {model.dimension} in {model.question_id}"

        # M1 Acceptance: Every APPROVED row MUST have a pass_rule, citation, and horizon
        if model.review_status == "APPROVED":
            assert model.pass_rule is not None, f"Approved row {model.question_id} missing pass_rule"
            assert model.source_doc != "", f"Approved row {model.question_id} missing source_doc citation"
            assert model.remediation_horizon_days in (30, 60, 90, 180), f"Approved row {model.question_id} invalid horizon: {model.remediation_horizon_days}"


def test_every_boolean_question_has_explicit_pass_rule():
    with open("data/seeds/normalized_branch_questions.json", "r", encoding="utf-8") as f:
        branch_q = json.load(f)
    with open("data/seeds/draft_universal_core.json", "r", encoding="utf-8") as f:
        core_q = json.load(f)

    for q in (branch_q + core_q):
        if q["input_type"] == "BOOLEAN":
            assert q.get("pass_rule") is not None, f"Boolean question {q['question_id']} missing explicit pass_rule"
            assert q["pass_rule"].get("type") in ("bool", "disclosed"), f"Boolean question {q['question_id']} has unexpected pass_rule type: {q['pass_rule'].get('type')}"
            if q["pass_rule"].get("type") == "bool":
                assert "pass_when" in q["pass_rule"], f"Boolean question {q['question_id']} missing pass_when in pass_rule"


def test_database_loaded_inventory():
    db = SessionLocal()
    try:
        total = db.query(Question).count()
        assert total >= 200
        unreviewed = db.query(Question).filter(Question.review_status == "UNREVIEWED_SEED").count()
        ai_pre = db.query(Question).filter(Question.review_status == "AI_PRE_REVIEWED").count()
        draft = db.query(Question).filter(Question.review_status == "DRAFT").count()
        approved = db.query(Question).filter(Question.review_status == "APPROVED").count()
        assert unreviewed > 0
        assert ai_pre > 0
        assert draft > 0
        assert approved == 0, f"Database must NEVER have APPROVED rows from seed scripts, found {approved}"
    finally:
        db.close()


def test_seed_scripts_unable_to_write_approved():
    """Assert seed scripts are strictly unable to write review_status=APPROVED."""
    from unittest.mock import patch, mock_open
    from apps.api.seeds.db_seed import seed_database

    # 1. Assert JSON seeds have 0 APPROVED questions
    with open("data/seeds/draft_universal_core.json", "r", encoding="utf-8") as f:
        core_q = json.load(f)
    with open("data/seeds/normalized_branch_questions.json", "r", encoding="utf-8") as f:
        branch_q = json.load(f)

    for q in (core_q + branch_q):
        assert q.get("review_status") != "APPROVED", f"Seed question {q['question_id']} has review_status=APPROVED"

    # 2. Assert attempting to seed APPROVED raises ValueError
    bad_question_data = [
        {
            "question_id": "TEST_APPROVED_FORBIDDEN",
            "scope": "CORE",
            "industry": "UNIVERSAL",
            "sub_sector": "ALL",
            "geography": ["USA"],
            "stage": ["ALL"],
            "dimension": "GOVERNANCE",
            "question_text": "Is this seed row approved?",
            "input_type": "BOOLEAN",
            "risk_weight": "MEDIUM",
            "pass_rule": {"type": "bool", "pass_when": True},
            "source_doc": "Test Doc",
            "source_ref": "Sec 1.1",
            "review_status": "APPROVED"
        }
    ]

    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=json.dumps(bad_question_data))):
            with pytest.raises(ValueError, match="must NEVER set review_status=APPROVED"):
                seed_database()
