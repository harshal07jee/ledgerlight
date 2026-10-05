"""
Golden Tests for Diligence Readiness Scoring & Trace Engine (Milestone M3).
Covers PRD Section 8 requirements:
1. All pass = 100.0
2. Single CRITICAL fail caps at 60.0 (with banner list)
3. Unanswered/UNVERIFIED questions excluded from score, counted in completeness, never treated as PASS, provisional badge < 60%
4. Determinism: same inputs + same config = identical output (run twice, compare)
5. Changing transaction type alters overall score weighting as expected
6. Partial thresholds (runway 6 to 9 months yields PARTIAL, >= 9 PASS, < 6 FAIL)
7. API endpoints: POST /assessments/{id}/score and GET /assessments/{id}/trace
"""
import pytest
from typing import Dict, Any, List
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api.database import SessionLocal, Base, engine
from apps.api.models import Organization, User, Membership, Assessment, Answer, ScoreRun, ScoreTraceRow
from apps.api.core.auth import hash_password
from apps.api.core.scoring import compute_readiness_score, load_scoring_config

client = TestClient(app)


@pytest.fixture(scope="module")
def scoring_config():
    """Loads default scoring config."""
    return load_scoring_config()


# --- Unit Golden Tests: Pure Scoring Function ---

def test_golden_all_pass_yields_100(scoring_config):
    """Golden Test 1: When all applicable questions pass, score is exactly 100.0."""
    applicable_questions = [
        {
            "question_id": "GOV_01",
            "dimension": "GOVERNANCE",
            "risk_weight": "CRITICAL",
            "question_text": "Is the corporate capitalization table fully reconciled?",
            "pass_rule": {"type": "bool", "pass_when": True},
            "source_doc": "NVCA_SPA_2025",
            "source_ref": "Section 2.2"
        },
        {
            "question_id": "FIN_01",
            "dimension": "FIN_CONTROLS",
            "risk_weight": "HIGH",
            "question_text": "Are annual financial statements audited by an independent CPA?",
            "pass_rule": {"type": "bool", "pass_when": True},
            "source_doc": "ILPA_DDQ_2.0",
            "source_ref": "Fin_3.1"
        },
        {
            "question_id": "LEGAL_01",
            "dimension": "LEGAL_IP_REG",
            "risk_weight": "CRITICAL",
            "question_text": "Have all founders and technical contractors executed proprietary information agreements?",
            "pass_rule": {"type": "bool", "pass_when": True},
            "source_doc": "NVCA_CIIAA_2025",
            "source_ref": "Section 1"
        }
    ]

    answers = {
        "GOV_01": True,
        "FIN_01": True,
        "LEGAL_01": True
    }

    profile = {"transaction_type": "VC_GROWTH_FINANCING"}

    result = compute_readiness_score(applicable_questions, answers, profile, scoring_config)

    assert result["overall_score"] == 100.0
    assert result["unconstrained_score"] == 100.0
    assert result["critical_cap_applied"] is False
    assert len(result["failed_critical_items"]) == 0
    assert result["completeness"]["completeness_pct"] == 100.0
    assert result["completeness"]["is_provisional"] is False
    assert len(result["trace_rows"]) == 0
    assert result["total_deductions"] == 0
    assert result["total_points_lost"] == 0.0

    # Every answered dimension must be 100.0
    for dim_code in ["GOVERNANCE", "FIN_CONTROLS", "LEGAL_IP_REG"]:
        assert result["dimension_scores"][dim_code]["score"] == 100.0


def test_golden_single_critical_fail_caps_at_60(scoring_config):
    """Golden Test 2: Single CRITICAL fail caps the overall score at 60.0."""
    applicable_questions = [
        # Dimension 1: GOVERNANCE (CRITICAL passes, weight 8)
        {
            "question_id": "GOV_01",
            "dimension": "GOVERNANCE",
            "risk_weight": "CRITICAL",
            "question_text": "Is the corporate capitalization table fully reconciled?",
            "pass_rule": {"type": "bool", "pass_when": True}
        },
        # Dimension 2: FIN_CONTROLS (HIGH passes, weight 5)
        {
            "question_id": "FIN_01",
            "dimension": "FIN_CONTROLS",
            "risk_weight": "HIGH",
            "question_text": "Are annual financial statements audited?",
            "pass_rule": {"type": "bool", "pass_when": True}
        },
        # Dimension 3: OPS_TECH_CYBER (MEDIUM passes, weight 3)
        {
            "question_id": "OPS_01",
            "dimension": "OPS_TECH_CYBER",
            "risk_weight": "MEDIUM",
            "question_text": "Is multi-factor authentication enforced?",
            "pass_rule": {"type": "bool", "pass_when": True}
        },
        # Dimension 4: FIN_PERFORMANCE (HIGH passes, weight 5)
        {
            "question_id": "PERF_01",
            "dimension": "FIN_PERFORMANCE",
            "risk_weight": "HIGH",
            "question_text": "Is annual recurring revenue growth > 50%?",
            "pass_rule": {"type": "bool", "pass_when": True}
        },
        # Dimension 5: LEGAL_IP_REG (CRITICAL FAILS! weight 8)
        {
            "question_id": "LEGAL_CRIT_01",
            "dimension": "LEGAL_IP_REG",
            "risk_weight": "CRITICAL",
            "question_text": "Do all founders have executed IP assignment agreements?",
            "pass_rule": {"type": "bool", "pass_when": True},
            "source_doc": "NVCA_CIIAA_2025",
            "source_ref": "Section 2"
        }
    ]

    # Answers: 4 pass, 1 critical fails
    answers = {
        "GOV_01": True,
        "FIN_01": True,
        "OPS_01": True,
        "PERF_01": True,
        "LEGAL_CRIT_01": False  # FAILS
    }

    profile = {"transaction_type": "VC_GROWTH_FINANCING"}

    result = compute_readiness_score(applicable_questions, answers, profile, scoring_config)

    # In VC_GROWTH_FINANCING:
    # GOVERNANCE: 100 (wt 10)
    # FIN_CONTROLS: 100 (wt 10)
    # OPS_TECH_CYBER: 100 (wt 10)
    # FIN_PERFORMANCE: 100 (wt 15)
    # LEGAL_IP_REG: 0 (wt 15)
    # Total txn weight = 10+10+10+15+15 = 60
    # Weighted sum = 10*100 + 10*100 + 10*100 + 15*100 + 15*0 = 4500
    # Unconstrained score = 4500 / 60 = 75.0
    assert result["unconstrained_score"] == 75.0

    # But single CRITICAL fail caps at 60.0
    assert result["overall_score"] == 60.0
    assert result["critical_cap_applied"] is True
    assert len(result["failed_critical_items"]) == 1
    assert result["failed_critical_items"][0]["question_id"] == "LEGAL_CRIT_01"

    # Deduction trace must include LEGAL_CRIT_01
    assert len(result["trace_rows"]) == 1
    trace = result["trace_rows"][0]
    assert trace["question_id"] == "LEGAL_CRIT_01"
    assert trace["is_critical_fail"] is True
    assert trace["points_lost"] == 8.0  # Weight of CRITICAL is 8


def test_golden_unanswered_excluded_from_score_lowers_completeness(scoring_config):
    """
    Golden Test 3: UNVERIFIED / unanswered questions:
    - Excluded from score calculation (do not deduct points from answered questions)
    - Counted in evidence completeness denominator
    - Never treated as PASS
    - Flags provisional when completeness < 60%
    """
    applicable_questions = [
        {
            "question_id": f"Q_{i}",
            "dimension": "GOVERNANCE",
            "risk_weight": "MEDIUM",
            "question_text": f"Question {i}",
            "pass_rule": {"type": "bool", "pass_when": True}
        }
        for i in range(1, 11)  # 10 questions
    ]

    # Only 3 questions answered (all PASS), 7 unanswered
    answers = {
        "Q_1": True,
        "Q_2": True,
        "Q_3": True
    }

    profile = {"transaction_type": "VC_GROWTH_FINANCING"}

    result = compute_readiness_score(applicable_questions, answers, profile, scoring_config)

    # Answered questions passed -> dimension score is 100.0, NOT 30.0!
    assert result["dimension_scores"]["GOVERNANCE"]["score"] == 100.0
    assert result["overall_score"] == 100.0

    # Completeness is 3 / 10 = 30.0%
    assert result["completeness"]["total_applicable"] == 10
    assert result["completeness"]["answered_count"] == 3
    assert result["completeness"]["completeness_pct"] == 30.0

    # Provisional flag must be True because 30.0% < 60.0%
    assert result["completeness"]["is_provisional"] is True


def test_golden_determinism_identical_runs(scoring_config):
    """Golden Test 4: Running twice with exact same inputs and config yields identical output."""
    applicable_questions = [
        {
            "question_id": "TXN_01",
            "dimension": "TXN_READINESS",
            "risk_weight": "HIGH",
            "question_text": "Is the corporate data room fully indexed?",
            "pass_rule": {"type": "bool", "pass_when": True}
        },
        {
            "question_id": "FIN_02",
            "dimension": "FIN_CONTROLS",
            "risk_weight": "MEDIUM",
            "question_text": "Are monthly closes completed within 15 days?",
            "pass_rule": {"type": "bool", "pass_when": True}
        },
        {
            "question_id": "CYBER_01",
            "dimension": "OPS_TECH_CYBER",
            "risk_weight": "HIGH",
            "question_text": "Have penetration tests been completed in the past 12 months?",
            "pass_rule": {"type": "bool", "pass_when": True}
        }
    ]

    answers = {
        "TXN_01": True,
        "FIN_02": False,
        "CYBER_01": True
    }

    profile = {"transaction_type": "M&A_SELL_SIDE"}

    run_1 = compute_readiness_score(applicable_questions, answers, profile, scoring_config)
    run_2 = compute_readiness_score(applicable_questions, answers, profile, scoring_config)

    assert run_1 == run_2
    assert run_1["overall_score"] == run_2["overall_score"]
    assert run_1["trace_rows"] == run_2["trace_rows"]
    assert run_1["dimension_scores"] == run_2["dimension_scores"]


def test_golden_transaction_type_weighting_shifts_score(scoring_config):
    """
    Golden Test 5: Changing transaction type changes the weighting of dimensions as expected.
    In DEBT_FINANCING, PROFIT_CASHFLOW has weight 25, OPS_TECH_CYBER has weight 5.
    In VC_GROWTH_FINANCING, PROFIT_CASHFLOW has weight 10, OPS_TECH_CYBER has weight 10.
    A company with strong cyber but weak cashflow should score higher in VC than in Debt.
    """
    applicable_questions = [
        {
            "question_id": "OPS_HIGH_01",
            "dimension": "OPS_TECH_CYBER",
            "risk_weight": "HIGH",
            "question_text": "Is technical architecture fully automated?",
            "pass_rule": {"type": "bool", "pass_when": True}
        },
        {
            "question_id": "CASH_FAIL_01",
            "dimension": "PROFIT_CASHFLOW",
            "risk_weight": "HIGH",
            "question_text": "Is operating cashflow positive?",
            "pass_rule": {"type": "bool", "pass_when": True}
        }
    ]

    answers = {
        "OPS_HIGH_01": True,   # PASS (OPS score = 100)
        "CASH_FAIL_01": False  # FAIL (CASH score = 0)
    }

    vc_result = compute_readiness_score(
        applicable_questions, answers, {"transaction_type": "VC_GROWTH_FINANCING"}, scoring_config
    )
    debt_result = compute_readiness_score(
        applicable_questions, answers, {"transaction_type": "DEBT_FINANCING"}, scoring_config
    )

    # In VC: weights are OPS=10, CASH=10. Score = (10*100 + 10*0)/20 = 50.0
    assert vc_result["overall_score"] == 50.0

    # In Debt: weights are OPS=5, CASH=25. Score = (5*100 + 25*0)/30 = 500/30 = 16.67
    assert debt_result["overall_score"] == 16.67

    # Debt score must be significantly lower than VC score due to cashflow penalty
    assert vc_result["overall_score"] > debt_result["overall_score"]


def test_golden_partial_thresholds_runway(scoring_config):
    """
    Golden Test 6: Partial thresholds:
    Runway months rule:
    - >= 9 months: PASS (s_q = 1.0, 0 points lost)
    - 6 to 9 months: PARTIAL (s_q = 0.5, 0.5 * weight points lost)
    - < 6 months: FAIL (s_q = 0.0, full weight points lost)
    """
    runway_question = {
        "question_id": "CASH_RUNWAY_01",
        "dimension": "PROFIT_CASHFLOW",
        "risk_weight": "HIGH",  # Weight 5
        "question_text": "What is the company's current cash runway in months?",
        "pass_rule": {
            "type": "threshold",
            "field": "runway_months",
            "op": "gte",
            "value": 9,
            "partial": {"op": "gte", "value": 6}
        }
    }

    # Case A: Runway = 12 months (>= 9) -> PASS
    res_pass = compute_readiness_score([runway_question], {"CASH_RUNWAY_01": 12}, {"transaction_type": "VC_GROWTH_FINANCING"}, scoring_config)
    assert res_pass["overall_score"] == 100.0
    assert len(res_pass["trace_rows"]) == 0

    # Case B: Runway = 7.5 months (6 to 9) -> PARTIAL
    res_partial = compute_readiness_score([runway_question], {"CASH_RUNWAY_01": 7.5}, {"transaction_type": "VC_GROWTH_FINANCING"}, scoring_config)
    assert res_partial["overall_score"] == 50.0
    assert len(res_partial["trace_rows"]) == 1
    assert res_partial["trace_rows"][0]["answer_state"] == "PARTIAL"
    assert res_partial["trace_rows"][0]["points_lost"] == 2.5  # 5 * 0.5

    # Case C: Runway = 4 months (< 6) -> FAIL
    res_fail = compute_readiness_score([runway_question], {"CASH_RUNWAY_01": 4}, {"transaction_type": "VC_GROWTH_FINANCING"}, scoring_config)
    assert res_fail["overall_score"] == 0.0
    assert len(res_fail["trace_rows"]) == 1
    assert res_fail["trace_rows"][0]["answer_state"] == "FAIL"
    assert res_fail["trace_rows"][0]["points_lost"] == 5.0  # 5 * 1.0


def test_golden_best_case_and_worst_case_bounds(scoring_config):
    """
    Golden Test 7: Best-case and Worst-case score bounds:
    - Best: unverified questions counted as PASS (s_q = 1.0)
    - Worst: unverified questions counted as FAIL (s_q = 0.0)
    - When 100% complete: best == overall == worst
    - When partially complete: worst <= overall <= best
    - If unverified question is CRITICAL, worst-case score caps at 60.0
    """
    q1 = {
        "question_id": "GOV_Q1",
        "dimension": "GOVERNANCE",
        "risk_weight": "HIGH",
        "pass_rule": {"type": "bool", "pass_when": True}
    }
    q2 = {
        "question_id": "GOV_Q2",
        "dimension": "GOVERNANCE",
        "risk_weight": "HIGH",
        "pass_rule": {"type": "bool", "pass_when": True}
    }

    # Case A: 100% complete (both pass) -> best == overall == worst == 100.0
    res_complete = compute_readiness_score([q1, q2], {"GOV_Q1": True, "GOV_Q2": True}, {"transaction_type": "VC_GROWTH_FINANCING"}, scoring_config)
    assert res_complete["overall_score"] == 100.0
    assert res_complete["best_case_score"] == 100.0
    assert res_complete["worst_case_score"] == 100.0

    # Case B: Partially complete: q1 passes, q2 is unverified
    # Answered score is 100.0 (over q1)
    # Best-case: q2 passes -> 100.0
    # Worst-case: q2 fails -> 50.0
    res_partial = compute_readiness_score([q1, q2], {"GOV_Q1": True}, {"transaction_type": "VC_GROWTH_FINANCING"}, scoring_config)
    assert res_partial["overall_score"] == 100.0
    assert res_partial["best_case_score"] == 100.0
    assert res_partial["worst_case_score"] == 50.0
    assert res_partial["worst_case_score"] <= res_partial["overall_score"] <= res_partial["best_case_score"]

    # Case C: Unverified question is CRITICAL
    # An unverified CRITICAL question in worst case counts as FAIL, capping worst case at 60.0
    q_crit = {
        "question_id": "LEGAL_CRIT",
        "dimension": "LEGAL_IP_REG",
        "risk_weight": "CRITICAL",
        "pass_rule": {"type": "bool", "pass_when": True}
    }
    # q1 passed (governance = 100), q_crit is unverified (legal)
    res_crit = compute_readiness_score([q1, q_crit], {"GOV_Q1": True}, {"transaction_type": "VC_GROWTH_FINANCING"}, scoring_config)
    # Overall is 100.0 (over answered q1)
    assert res_crit["overall_score"] == 100.0
    # Best case: q_crit passes -> 100.0
    assert res_crit["best_case_score"] == 100.0
    # Worst case: q_crit fails -> capped at 60.0
    assert res_crit["worst_case_score"] <= 60.0


# --- End-to-End API Golden Tests ---

@pytest.fixture(scope="module")
def api_test_setup():
    """Sets up an isolated test organization, user, assessment, and answers."""
    import uuid
    db = SessionLocal()
    try:
        # Create Org
        org = Organization(name=f"Golden Test Org {uuid.uuid4().hex[:6]}")
        db.add(org)
        db.flush()

        # Create User with unique email
        test_email = f"goldentest_{uuid.uuid4().hex[:8]}@ledgerlight.io"
        user = User(
            email=test_email,
            hashed_password=hash_password("Pass123!"),
            full_name="Golden Tester",
            is_active=True,
            is_admin=False
        )
        db.add(user)
        db.flush()

        # Membership
        membership = Membership(org_id=org.id, user_id=user.id, role="Owner")
        db.add(membership)
        db.flush()

        # Assessment
        assessment = Assessment(
            org_id=org.id,
            name="Golden Test Assessment",
            industry="SOFTWARE",
            sub_sector="ALL",
            stage="Growth",
            transaction_type="VC_GROWTH_FINANCING",
            geography=["USA"],
            status="in_progress"
        )
        db.add(assessment)
        db.commit()
        db.refresh(assessment)

        token = f"demo-session-{user.id}"

        yield {
            "org_id": org.id,
            "user_id": user.id,
            "assessment_id": assessment.id,
            "token": token
        }
    finally:
        db.close()


def test_api_score_and_trace_endpoints(api_test_setup):
    """
    Tests POST /assessments/{id}/score and GET /assessments/{id}/trace:
    - Verifies response schema
    - Verifies config_version and question_bank_version are persisted
    - Verifies trace row structure
    """
    aid = api_test_setup["assessment_id"]
    token = api_test_setup["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Answer a question via existing autosave endpoint
    res_ans = client.put(
        f"/assessments/{aid}/answers/CORE_IP_01",
        json={"value": True, "notes": "CIIAA fully executed by all founders"},
        headers=headers
    )
    assert res_ans.status_code == 200

    # 2. Trigger score run via POST /assessments/{id}/score
    res_score = client.post(f"/assessments/{aid}/score", headers=headers)
    assert res_score.status_code == 200
    score_data = res_score.json()

    assert "overall_score" in score_data
    assert "unconstrained_score" in score_data
    assert "dimension_scores" in score_data
    assert "completeness" in score_data
    assert "trace_rows" in score_data
    assert "config_version" in score_data
    assert "question_bank_version" in score_data
    assert score_data["config_version"] in ("1.0.0", "v1.0.0")

    # 3. Retrieve trace via GET /assessments/{id}/trace
    res_trace = client.get(f"/assessments/{aid}/trace", headers=headers)
    assert res_trace.status_code == 200
    trace_data = res_trace.json()

    assert trace_data["assessment_id"] == aid
    assert trace_data["score_run_id"] == score_data["id"]
    assert trace_data["overall_score"] == score_data["overall_score"]
    assert "trace_rows" in trace_data
    assert "weight_origin_share" in trace_data
    assert trace_data["config_version"] in ("1.0.0", "v1.0.0")


def test_golden_weight_origin_share_and_disclosures():
    """
    PRD Section 8 & Pre-M5 Requirement:
    - Scored answers must carry origin ('self-attested' vs 'evidence-backed').
    - Output must report share of scored weight (self-attested vs evidence-backed).
    - Routing questions never score and never fail/pass, but count toward completeness.
    - Disclosed questions are listed in unscored_disclosures, excluded from score.
    """
    from apps.api.core.scoring import compute_readiness_score

    applicable_questions = [
        # Evidence-backed scorable question (CRITICAL = 8 pts)
        {
            "question_id": "Q_EVID_1",
            "dimension": "GOVERNANCE",
            "risk_weight": "CRITICAL",
            "evidence_type": "CONTRACT_CLAUSE",
            "pass_rule": {"type": "bool", "pass_when": True},
            "question_text": "Binding PIIA agreement executed?"
        },
        # Self-attested scorable question (HIGH = 5 pts)
        {
            "question_id": "Q_SELF_1",
            "dimension": "GOVERNANCE",
            "risk_weight": "HIGH",
            "evidence_type": "SELF_ATTESTED",
            "pass_rule": {"type": "bool", "pass_when": True},
            "question_text": "Code of conduct in place?"
        },
        # Routing question (never scored, counts in completeness)
        {
            "question_id": "Q_ROUTE_1",
            "dimension": "OPS_TECH_CYBER",
            "risk_weight": "CRITICAL",
            "input_type": "MULTIPLE_CHOICE",
            "pass_rule": {"type": "routing", "description": "Routing question"},
            "question_text": "Software delivery model?"
        },
        # Unscored disclosure (never scored, counts in completeness)
        {
            "question_id": "Q_DISC_1",
            "dimension": "PROFIT_CASHFLOW",
            "risk_weight": "MEDIUM",
            "input_type": "CURRENCY",
            "pass_rule": {"type": "disclosed", "description": "Unscored disclosure"},
            "question_text": "Working capital peg target?"
        }
    ]

    answers = {
        "Q_EVID_1": {"value": True, "user_action": "manual"},
        "Q_SELF_1": {"value": False, "user_action": "manual"},  # Deducted
        "Q_ROUTE_1": {"value": "B2B Enterprise SaaS"},
        "Q_DISC_1": {"value": "$1,500,000", "notes": "Historical average"}
    }

    company_profile = {"transaction_type": "VC_GROWTH_FINANCING"}

    res = compute_readiness_score(applicable_questions, answers, company_profile)

    # 1. Completeness: all 4 are answered
    assert res["completeness"]["total_applicable"] == 4
    assert res["completeness"]["answered_count"] == 4
    assert res["completeness"]["completeness_pct"] == 100.0

    # 2. Weight origin breakdown:
    # Q_EVID_1: 8.0 pts evidence-backed
    # Q_SELF_1: 5.0 pts self-attested
    # Total scored weight = 13.0 pts
    origin_share = res["weight_origin_share"]
    assert origin_share["evidence_backed_weight"] == 8.0
    assert origin_share["self_attested_weight"] == 5.0
    assert origin_share["total_scored_weight"] == 13.0
    assert origin_share["evidence_backed_share_pct"] == 61.5  # 8 / 13 * 100
    assert origin_share["self_attested_share_pct"] == 38.5    # 5 / 13 * 100

    # 3. Disclosures: Q_DISC_1 is collected in unscored_disclosures
    assert len(res["unscored_disclosures"]) == 1
    assert res["unscored_disclosures"][0]["question_id"] == "Q_DISC_1"
    assert res["unscored_disclosures"][0]["value"] == "$1,500,000"

    # 4. Deduction trace carries origin
    assert len(res["trace_rows"]) == 1
    assert res["trace_rows"][0]["question_id"] == "Q_SELF_1"
    assert res["trace_rows"][0]["origin"] == "self-attested"


def test_golden_scored_question_review_status_counts():
    """Assert scored questions review status breakdown is tracked accurately."""
    applicable_questions = [
        {
            "question_id": "Q_AI_1",
            "dimension": "GOVERNANCE",
            "risk_weight": "MEDIUM",
            "input_type": "BOOLEAN",
            "pass_rule": {"type": "bool", "pass_when": True},
            "review_status": "AI_PRE_REVIEWED"
        },
        {
            "question_id": "Q_AI_2",
            "dimension": "GOVERNANCE",
            "risk_weight": "HIGH",
            "input_type": "BOOLEAN",
            "pass_rule": {"type": "bool", "pass_when": True},
            "review_status": "AI_PRE_REVIEWED"
        },
        {
            "question_id": "Q_SEED_1",
            "dimension": "FIN_CONTROLS",
            "risk_weight": "CRITICAL",
            "input_type": "BOOLEAN",
            "pass_rule": {"type": "bool", "pass_when": True},
            "review_status": "UNREVIEWED_SEED"
        },
        {
            "question_id": "Q_DISC_1",
            "dimension": "FIN_CONTROLS",
            "risk_weight": "MEDIUM",
            "input_type": "TEXT",
            "pass_rule": {"type": "disclosed"},
            "review_status": "AI_PRE_REVIEWED"
        },
        {
            "question_id": "Q_UNANS_1",
            "dimension": "GOVERNANCE",
            "risk_weight": "LOW",
            "input_type": "BOOLEAN",
            "pass_rule": {"type": "bool", "pass_when": True},
            "review_status": "AI_PRE_REVIEWED"
        }
    ]

    answers = {
        "Q_AI_1": True,
        "Q_AI_2": False,
        "Q_SEED_1": True,
        "Q_DISC_1": "Qualitative disclosure notes"
        # Q_UNANS_1 is unanswered
    }

    profile = {"transaction_type": "VC_GROWTH_FINANCING"}
    res = compute_readiness_score(applicable_questions, answers, profile)

    st_counts = res["scored_question_review_status"]
    assert st_counts["AI_PRE_REVIEWED"] == 2
    assert st_counts["UNREVIEWED_SEED"] == 1
    assert st_counts["APPROVED"] == 0
    assert st_counts["total_scored"] == 3

