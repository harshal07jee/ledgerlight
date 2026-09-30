"""
Integration tests for FastAPI endpoints, RBAC, and Question Approval Workflow (PRD Section 11 & 14 & M1 Cleanup).
"""
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app)
ADMIN_HEADERS = {"Authorization": "Bearer demo-token-admin"}
FOUNDER_HEADERS = {"Authorization": "Bearer demo-token-founder"}
ADVISOR_HEADERS = {"Authorization": "Bearer demo-token-advisor"}


def test_health_check_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert data["total_questions"] >= 200
    assert data["unreviewed_seed_questions"] > 0
    assert data["draft_questions"] > 0


def test_get_active_config_endpoint():
    res = client.get("/config/active")
    assert res.status_code == 200
    data = res.json()
    assert data["version_tag"] == "v1.0.0"
    assert "weights" in data
    assert "thresholds" in data
    assert data["thresholds"]["critical_fail_cap"] == 60.0


def test_auth_login_endpoint():
    # Admin login
    res_admin = client.post("/auth/login", json={"email": "admin@ledgerlight.io", "password": "Password123!"})
    assert res_admin.status_code == 200
    assert res_admin.json()["user"]["is_admin"] is True
    assert "access_token" in res_admin.json()

    # Founder login
    res_founder = client.post("/auth/login", json={"email": "founder@company.com", "password": "Password123!"})
    assert res_founder.status_code == 200
    assert res_founder.json()["user"]["is_admin"] is False


def test_rbac_security_admin_endpoints():
    # 1. Unauthenticated request to /admin/questions -> 401
    unauth_client = TestClient(app)
    res_unauth = unauth_client.get("/admin/questions")
    assert res_unauth.status_code == 401, f"Expected 401, got {res_unauth.status_code}"

    # 2. Non-admin founder request to /admin/questions -> 403 Forbidden
    res_founder = client.get("/admin/questions", headers=FOUNDER_HEADERS)
    assert res_founder.status_code == 403, f"Expected 403 for founder, got {res_founder.status_code}"
    assert "Admin privileges required" in res_founder.json()["detail"]

    # 3. Non-admin advisor request to /admin/metrics/coverage -> 403 Forbidden
    res_advisor = client.get("/admin/metrics/coverage", headers=ADVISOR_HEADERS)
    assert res_advisor.status_code == 403, f"Expected 403 for advisor, got {res_advisor.status_code}"

    # 4. Admin request to /admin/questions -> 200 OK
    res_admin = client.get("/admin/questions?limit=10", headers=ADMIN_HEADERS)
    assert res_admin.status_code == 200
    assert res_admin.json()["total"] >= 200


def test_questions_endpoint_filters_drafts():
    # Normal user query: MUST NOT return draft questions (returns APPROVED and UNREVIEWED_SEED)
    res_normal = client.get("/questions")
    assert res_normal.status_code == 200
    normal_q = res_normal.json()
    for q in normal_q:
        assert q["review_status"] in ("APPROVED", "UNREVIEWED_SEED"), f"Draft question leaked to normal user: {q['question_id']}"

    # Admin query with include_drafts=true: returns drafts as well
    res_admin = client.get("/questions?include_drafts=true")
    assert res_admin.status_code == 200
    all_q = res_admin.json()
    assert len(all_q) > len(normal_q)
    statuses = {q["review_status"] for q in all_q}
    assert "DRAFT" in statuses
    assert "UNREVIEWED_SEED" in statuses


def test_admin_metrics_coverage():
    res_cov = client.get("/admin/metrics/coverage", headers=ADMIN_HEADERS)
    assert res_cov.status_code == 200
    cov = res_cov.json()
    assert cov["total_questions"] >= 200
    assert cov["auto_extractable"] > 0
    assert cov["manual_required"] > 0


def test_approval_workflow_requires_reviewer_name_and_date():
    # Fetch a draft question
    res = client.get("/admin/questions?review_status=DRAFT&limit=1", headers=ADMIN_HEADERS)
    assert res.status_code == 200
    draft_item = res.json()["items"][0]
    qid = draft_item["question_id"]

    # 1. Non-admin attempting to approve -> 403
    res_forbidden = client.post(
        f"/admin/questions/{qid}/approve",
        headers=FOUNDER_HEADERS,
        json={"reviewer_name": "Jane Founder", "last_verified_on": "2026-09-30"}
    )
    assert res_forbidden.status_code == 403

    # 2. Admin omitting reviewer_name -> 422 or 400
    res_no_reviewer = client.post(
        f"/admin/questions/{qid}/approve",
        headers=ADMIN_HEADERS,
        json={"reviewer_name": "", "last_verified_on": "2026-09-30"}
    )
    assert res_no_reviewer.status_code == 400
    assert "reviewer_name is required" in res_no_reviewer.json()["detail"]

    # 3. Admin omitting last_verified_on -> 400
    res_no_date = client.post(
        f"/admin/questions/{qid}/approve",
        headers=ADMIN_HEADERS,
        json={"reviewer_name": "Chief Compliance Officer", "last_verified_on": ""}
    )
    assert res_no_date.status_code == 400
    assert "last_verified_on is required" in res_no_date.json()["detail"]

    # 4. Admin passing malformed date -> 400
    res_bad_date = client.post(
        f"/admin/questions/{qid}/approve",
        headers=ADMIN_HEADERS,
        json={"reviewer_name": "Chief Compliance Officer", "last_verified_on": "Sept 30 2026"}
    )
    assert res_bad_date.status_code == 400
    assert "YYYY-MM-DD" in res_bad_date.json()["detail"]

    try:
        # 5. Valid approval with both required fields
        approve_res = client.post(
            f"/admin/questions/{qid}/approve",
            headers=ADMIN_HEADERS,
            json={
                "reviewer_name": "Senior Diligence Counsel",
                "last_verified_on": "2026-09-30",
                "verification_notes": "Statutory citations cross-checked against primary regulatory filings."
            }
        )
        assert approve_res.status_code == 200
        data = approve_res.json()
        assert data["review_status"] == "APPROVED"
        assert data["reviewer_name"] == "Senior Diligence Counsel"
        assert data["last_verified_on"] == "2026-09-30"

        # Verify audit version record was created
        detail_res = client.get(f"/admin/questions/{qid}", headers=ADMIN_HEADERS)
        assert detail_res.status_code == 200
        assert detail_res.json()["question"]["review_status"] == "APPROVED"
        assert len(detail_res.json()["versions"]) >= 1
    finally:
        # Revert question back to DRAFT to prevent test from mutating DB state
        from apps.api.database import SessionLocal
        from apps.api.models import Question
        db_cleanup = SessionLocal()
        q_clean = db_cleanup.query(Question).filter_by(question_id=qid).first()
        if q_clean:
            q_clean.review_status = "DRAFT"
            q_clean.reviewer_name = None
            q_clean.last_verified_on = None
            db_cleanup.commit()
        db_cleanup.close()


def test_assessment_input_validation_returns_422():
    """Verify API strictly returns 422 Unprocessable Entity for unknown industry, sub_sector, stage, or transaction_type."""
    import uuid

    # 1. Setup isolated user and org
    unique_email = f"validator_{uuid.uuid4().hex[:6]}@example.com"
    signup_res = client.post("/auth/signup", json={
        "full_name": "Validation Tester",
        "email": unique_email,
        "password": "Password123!",
        "company_name": "Valid Corp"
    })
    assert signup_res.status_code == 200
    auth_data = signup_res.json()
    token = auth_data["access_token"]
    org_id = auth_data["user"]["org_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Unknown industry -> 422
    res_ind = client.post(f"/orgs/{org_id}/assessments", headers=headers, json={
        "name": "Invalid Industry Test",
        "industry": "UNKNOWN_AEROSPACE",
        "sub_sector": "ALL",
        "stage": "Growth",
        "transaction_type": "VC_GROWTH_FINANCING"
    })
    assert res_ind.status_code == 422

    # 3. Unknown sub_sector -> 422
    res_sub = client.post(f"/orgs/{org_id}/assessments", headers=headers, json={
        "name": "Invalid Sub-sector Test",
        "industry": "SOFTWARE",
        "sub_sector": "NON_EXISTENT_SUB_SECTOR",
        "stage": "Growth",
        "transaction_type": "VC_GROWTH_FINANCING"
    })
    assert res_sub.status_code == 422

    # 4. Unknown stage -> 422
    res_stage = client.post(f"/orgs/{org_id}/assessments", headers=headers, json={
        "name": "Invalid Stage Test",
        "industry": "SOFTWARE",
        "sub_sector": "ALL",
        "stage": "UNKNOWN_PRE_SEED_STAGE",
        "transaction_type": "VC_GROWTH_FINANCING"
    })
    assert res_stage.status_code == 422

    # 5. Unknown transaction_type -> 422
    res_txn = client.post(f"/orgs/{org_id}/assessments", headers=headers, json={
        "name": "Invalid Transaction Type Test",
        "industry": "SOFTWARE",
        "sub_sector": "ALL",
        "stage": "Growth",
        "transaction_type": "UNKNOWN_SPAC_MERGER"
    })
    assert res_txn.status_code == 422

    # 6. Valid payload succeeds with 201
    res_valid = client.post(f"/orgs/{org_id}/assessments", headers=headers, json={
        "name": "Valid Assessment Test",
        "industry": "SOFTWARE",
        "sub_sector": "ALL",
        "stage": "Growth",
        "transaction_type": "VC_GROWTH_FINANCING"
    })
    assert res_valid.status_code == 200


