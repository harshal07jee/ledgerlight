"""
Unit and integration tests for Milestone M2:
- Sign-up & Onboarding flow
- Applicable-question engine using company profile + depends_on
- Dynamic dependency gating & hiding non-applicable questions
- Autosave & completeness progress calculation
- Industry switch warning & answer discard logic
"""
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def approve_test_core_questions():
    """
    Test fixture: Temporarily marks CORE_CASH_FLOW_01 and CORE_CASH_FLOW_02 as APPROVED
    for the duration of questionnaire tests, and strictly restores them to DRAFT on teardown.
    Guarantees zero persistent modification of seed or production databases.
    """
    from apps.api.database import SessionLocal
    from apps.api.models import Question

    db = SessionLocal()
    target_qids = ["CORE_CASH_FLOW_01", "CORE_CASH_FLOW_02"]
    try:
        for qid in target_qids:
            q = db.query(Question).filter_by(question_id=qid).first()
            if q:
                q.review_status = "APPROVED"
        db.commit()
        yield
    finally:
        for qid in target_qids:
            q = db.query(Question).filter_by(question_id=qid).first()
            if q:
                q.review_status = "DRAFT"
        db.commit()
        db.close()


def test_signup_and_onboarding_flow():
    # 1. Sign up
    signup_payload = {
        "full_name": "Alexander Hamilton",
        "email": "alexander@treasury-tech.com",
        "password": "SecurePassword123!",
        "company_name": "Treasury Tech Inc."
    }
    signup_res = client.post("/auth/signup", json=signup_payload)
    assert signup_res.status_code == 200
    user_data = signup_res.json()["user"]
    org_data = signup_res.json()["organization"]
    token = signup_res.json()["access_token"]
    assert user_data["email"] == "alexander@treasury-tech.com"
    assert org_data["name"] == "Treasury Tech Inc."
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Assessment
    assessment_payload = {
        "name": "Treasury Tech Series A Diligence",
        "industry": "FINTECH",
        "sub_sector": "Payments/MSB",
        "stage": "Growth",
        "transaction_type": "VC_GROWTH_FINANCING",
        "geography": ["USA"]
    }
    create_res = client.post(
        f"/orgs/{org_data['id']}/assessments",
        json=assessment_payload,
        headers=headers
    )
    assert create_res.status_code == 200
    res_json = create_res.json()
    assert res_json["status"] == "created"
    assert res_json["assessment"]["industry"] == "FINTECH"
    assert res_json["progress"]["total_applicable"] > 0
    assert res_json["progress"]["answered_count"] == 0
    assert res_json["progress"]["completeness_pct"] == 0.0
    assert res_json["progress"]["is_provisional"] is True


def test_applicable_question_engine_profile_filtering():
    # 1. Create a Software company assessment
    org_res = client.post("/auth/signup", json={
        "full_name": "Ada Lovelace",
        "email": "ada@analytical-engine.io",
        "password": "Password123!",
        "company_name": "Analytical Cloud"
    })
    token = org_res.json()["access_token"]
    org_id = org_res.json()["organization"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        f"/orgs/{org_id}/assessments",
        json={
            "industry": "SOFTWARE",
            "sub_sector": "B2B Enterprise SaaS",
            "stage": "Growth",
            "transaction_type": "VC_GROWTH_FINANCING"
        },
        headers=headers
    )
    assessment_id = create_res.json()["assessment"]["id"]

    # 2. Fetch questions
    q_res = client.get(f"/assessments/{assessment_id}/questions", headers=headers)
    assert q_res.status_code == 200
    data = q_res.json()

    applicable_qids = [q["question_id"] for q in data["questions"]]

    # Universal Core questions MUST be present (via approved fixture)
    assert any(qid.startswith("CORE_") for qid in applicable_qids)

    # Software questions MUST be present
    assert any(qid.startswith("SAAS_") for qid in applicable_qids)

    # HealthCare, FinTech, Energy branch questions MUST NOT be present
    assert not any(qid.startswith("MED_DEV_") for qid in applicable_qids)
    assert not any(qid.startswith("HLTH_") for qid in applicable_qids)
    assert not any(qid.startswith("FIN_TECH_") for qid in applicable_qids)
    assert not any(qid.startswith("ENG_") for qid in applicable_qids)

    # Hidden questions count must be tracked
    assert data["progress"]["hidden_not_applicable_count"] > 0


def test_dynamic_branching_and_dependency_hiding():
    # Setup Healthcare assessment
    org_res = client.post("/auth/signup", json={
        "full_name": "Dr. Jonas Salk",
        "email": "jonas@polio-cure.org",
        "password": "Password123!",
        "company_name": "BioHealth Therapeutics"
    })
    token = org_res.json()["access_token"]
    org_id = org_res.json()["organization"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        f"/orgs/{org_id}/assessments",
        json={
            "industry": "HEALTHCARE",
            "sub_sector": "Medical_Devices",
            "stage": "Growth"
        },
        headers=headers
    )
    assessment_id = create_res.json()["assessment"]["id"]

    # Initially, MED_DEV_01 is unanswered
    q_res1 = client.get(f"/assessments/{assessment_id}/questions", headers=headers)
    qids1 = [q["question_id"] for q in q_res1.json()["questions"]]

    assert "MED_DEV_01" in qids1
    # Both Class II and Class III specific questions must be hidden
    assert "MED_DEV_03" not in qids1
    assert "MED_DEV_04" not in qids1

    # 1. Answer MED_DEV_01 with 'Class II'
    ans_res1 = client.put(
        f"/assessments/{assessment_id}/answers/MED_DEV_01",
        json={"value": "Class II"},
        headers=headers
    )
    assert ans_res1.status_code == 200

    # Re-fetch: MED_DEV_03 (Class II) should now be APPLICABLE; MED_DEV_04 (Class III) remains HIDDEN
    q_res2 = client.get(f"/assessments/{assessment_id}/questions", headers=headers)
    qids2 = [q["question_id"] for q in q_res2.json()["questions"]]
    assert "MED_DEV_03" in qids2
    assert "MED_DEV_04" not in qids2

    # 2. Change MED_DEV_01 to 'Class III'
    ans_res2 = client.put(
        f"/assessments/{assessment_id}/answers/MED_DEV_01",
        json={"value": "Class III"},
        headers=headers
    )
    assert ans_res2.status_code == 200

    # Re-fetch: MED_DEV_04 (Class III) should now be APPLICABLE; MED_DEV_03 (Class II) is now HIDDEN
    q_res3 = client.get(f"/assessments/{assessment_id}/questions", headers=headers)
    qids3 = [q["question_id"] for q in q_res3.json()["questions"]]
    assert "MED_DEV_04" in qids3
    assert "MED_DEV_03" not in qids3


def test_autosave_and_progress_calculation():
    org_res = client.post("/auth/signup", json={
        "full_name": "Grace Hopper",
        "email": "grace@navy-comp.mil",
        "password": "Password123!",
        "company_name": "Compiler Systems"
    })
    token = org_res.json()["access_token"]
    org_id = org_res.json()["organization"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        f"/orgs/{org_id}/assessments",
        json={
            "industry": "SOFTWARE",
            "sub_sector": "B2B Enterprise SaaS"
        },
        headers=headers
    )
    assessment_id = create_res.json()["assessment"]["id"]

    # Initial state
    q_res = client.get(f"/assessments/{assessment_id}/questions", headers=headers)
    assert q_res.json()["progress"]["answered_count"] == 0

    # Autosave question 1 (Universal Core)
    save1 = client.put(
        f"/assessments/{assessment_id}/answers/CORE_CASH_FLOW_01",
        json={"value": 18, "notes": "Audited cash runway calculation."},
        headers=headers
    )
    assert save1.status_code == 200
    p1 = save1.json()["progress"]
    assert p1["answered_count"] == 1
    assert p1["completeness_pct"] > 0.0

    # Autosave question 2 (SaaS Branch)
    save2 = client.put(
        f"/assessments/{assessment_id}/answers/SAAS_02",
        json={"value": True, "notes": "SOC 2 Type II audit report on file."},
        headers=headers
    )
    assert save2.status_code == 200
    p2 = save2.json()["progress"]
    assert p2["answered_count"] == 2

    # Verify reload retains saved values
    q_reload = client.get(f"/assessments/{assessment_id}/questions", headers=headers)
    questions = {q["question_id"]: q for q in q_reload.json()["questions"]}
    assert questions["CORE_CASH_FLOW_01"]["current_answer"] == 18
    assert questions["CORE_CASH_FLOW_01"]["notes"] == "Audited cash runway calculation."
    assert questions["SAAS_02"]["current_answer"] is True


def test_industry_switch_warning_and_discard():
    # Setup assessment in SOFTWARE industry
    org_res = client.post("/auth/signup", json={
        "full_name": "Katherine Johnson",
        "email": "katherine@orbital-math.gov",
        "password": "Password123!",
        "company_name": "Orbital Dynamics"
    })
    token = org_res.json()["access_token"]
    org_id = org_res.json()["organization"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        f"/orgs/{org_id}/assessments",
        json={
            "industry": "SOFTWARE",
            "sub_sector": "B2B Enterprise SaaS"
        },
        headers=headers
    )
    assessment_id = create_res.json()["assessment"]["id"]

    # Answer 1 Universal Core question + 1 Software branch question
    client.put(
        f"/assessments/{assessment_id}/answers/CORE_CASH_FLOW_01",
        json={"value": 12},
        headers=headers
    )
    client.put(
        f"/assessments/{assessment_id}/answers/SAAS_01",
        json={"value": "B2B Enterprise SaaS"},
        headers=headers
    )

    # 1. Attempt to change industry to ENERGY without confirmation
    switch_res1 = client.patch(
        f"/assessments/{assessment_id}/profile",
        json={"industry": "ENERGY", "confirm_discard_answers": False},
        headers=headers
    )
    assert switch_res1.status_code == 409
    err = switch_res1.json()["detail"]
    assert "discard 1 answers specific to SOFTWARE" in err["warning"]
    assert err["discard_count"] == 1

    # Verify industry did NOT change
    assess_check = client.get(f"/assessments/{assessment_id}", headers=headers).json()["assessment"]
    assert assess_check["industry"] == "SOFTWARE"

    # 2. Change industry with confirm_discard_answers=True
    switch_res2 = client.patch(
        f"/assessments/{assessment_id}/profile",
        json={"industry": "ENERGY", "confirm_discard_answers": True},
        headers=headers
    )
    assert switch_res2.status_code == 200
    assert switch_res2.json()["assessment"]["industry"] == "ENERGY"

    # Verify that SAAS_01 answer is gone, but CORE_CASH_FLOW_01 is retained!
    q_after = client.get(f"/assessments/{assessment_id}/questions", headers=headers).json()
    questions_after = {q["question_id"]: q for q in q_after["questions"]}

    # Core answer retained
    assert "CORE_CASH_FLOW_01" in questions_after
    assert questions_after["CORE_CASH_FLOW_01"]["current_answer"] == 12

    # Software question no longer applicable
    assert "SAAS_01" not in questions_after

    # Energy questions now applicable
    assert "ENERGY_01" in questions_after
