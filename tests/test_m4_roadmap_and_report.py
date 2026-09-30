"""
Milestone M4 Validation Tests (PRD Sections 9.1, 9.3, 9.4 and FR-8).
Validates:
1. Roadmap bucket placement (30/60/90/180) and ordering (weight x points_lost desc).
2. Root-cause clustering (grouping by dimension + sub_category).
3. Playbook text strictly from question bank (no LLM generation).
4. Marking task done does NOT change the score.
5. Re-assessment delta calculation (dimension changes & flipped FAIL->PASS items).
6. PDF export contains PRD Section 1 disclaimer and version strings.
7. Tenant-isolation tests for new M4 endpoints.
"""
import uuid
import pytest
import pymupdf
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api.core.roadmap import generate_roadmap_tasks_data, compute_reassessment_delta
from apps.api.core.pdf_export import DISCLAIMER_TEXT

client = TestClient(app)


def test_roadmap_bucket_placement_and_ordering():
    """
    PRD 9.1 & FR-8:
    - One task per FAIL/PARTIAL question (and CRITICAL UNVERIFIED).
    - Placed in bucket from remediation_horizon_days (30/60/90/180).
    - Ordered within each bucket by weight x points_lost descending.
    - Only remediation_action text from question bank (no LLM).
    """
    mock_questions = [
        {
            "question_id": "Q-30-HIGH",
            "question_text": "Do you have 2FA enabled on all production systems?",
            "dimension": "CYBERSECURITY",
            "sub_category": "Access Control",
            "risk_weight": "HIGH",  # weight 5.0
            "remediation_horizon_days": 30,
            "remediation_action": "Enforce mandatory MFA across all identity providers within 30 days.",
            "pass_rule": {"type": "BOOLEAN", "operator": "EQUALS", "value": True},
            "source_doc": "SOC 2 Type II",
            "source_ref": "CC6.1"
        },
        {
            "question_id": "Q-30-CRIT",
            "question_text": "Are all customer IP assignment agreements fully signed?",
            "dimension": "INTELLECTUAL_PROPERTY",
            "sub_category": "Chain of Title",
            "risk_weight": "CRITICAL",  # weight 8.0
            "remediation_horizon_days": 30,
            "remediation_action": "Execute confirmatory assignment agreements for all historical contractors.",
            "pass_rule": {"type": "BOOLEAN", "operator": "EQUALS", "value": True},
            "source_doc": "PIIA Registry",
            "source_ref": "Exhibit A"
        },
        {
            "question_id": "Q-60-MED",
            "question_text": "Is there a documented disaster recovery testing plan?",
            "dimension": "CYBERSECURITY",
            "sub_category": "Business Continuity",
            "risk_weight": "MEDIUM",  # weight 3.0
            "remediation_horizon_days": 60,
            "remediation_action": "Conduct and document an annual DR tabletop simulation.",
            "pass_rule": {"type": "BOOLEAN", "operator": "EQUALS", "value": True}
        },
        {
            "question_id": "Q-90-LOW",
            "question_text": "Do vendor contracts include standard SLA terms?",
            "dimension": "COMMERCIAL",
            "sub_category": "Vendor Contracts",
            "risk_weight": "LOW",  # weight 1.0
            "remediation_horizon_days": 90,
            "remediation_action": "Update master vendor template with standard SLA clauses.",
            "pass_rule": {"type": "BOOLEAN", "operator": "EQUALS", "value": True}
        },
        {
            "question_id": "Q-180-HIGH",
            "question_text": "Is annual external penetration testing performed?",
            "dimension": "CYBERSECURITY",
            "sub_category": "Penetration Testing",
            "risk_weight": "HIGH",  # weight 5.0
            "remediation_horizon_days": 180,
            "remediation_action": "Engage CREST-accredited third-party firm for annual gray-box pentest.",
            "pass_rule": {"type": "BOOLEAN", "operator": "EQUALS", "value": True}
        },
        {
            "question_id": "Q-PASS-IGNORE",
            "question_text": "Is certificate of incorporation on file?",
            "dimension": "CORPORATE_RECORDS",
            "sub_category": "Formation",
            "risk_weight": "CRITICAL",
            "remediation_horizon_days": 30,
            "remediation_action": "File formation docs.",
            "pass_rule": {"type": "BOOLEAN", "operator": "EQUALS", "value": True}
        },
        {
            "question_id": "Q-CRIT-UNVERIFIED",
            "question_text": "Are all material patent assignments recorded with USPTO?",
            "dimension": "INTELLECTUAL_PROPERTY",
            "sub_category": "Chain of Title",
            "risk_weight": "CRITICAL",  # weight 8.0, points lost 8.0, priority_score 64.0
            "remediation_horizon_days": 60,
            "remediation_action": "Record confirmatory assignments with USPTO patent registry.",
            "pass_rule": {"type": "BOOLEAN", "operator": "EQUALS", "value": True}
        }
    ]

    answers = {
        "Q-30-HIGH": {"value": False},  # FAIL -> weight 5, points_lost 5, priority 25
        "Q-30-CRIT": {"value": False},  # FAIL -> weight 8, points_lost 8, priority 64
        "Q-60-MED": {"value": False},   # FAIL -> weight 3, points_lost 3, priority 9
        "Q-90-LOW": {"value": False},   # FAIL -> weight 1, points_lost 1, priority 1
        "Q-180-HIGH": {"value": False}, # FAIL -> weight 5, points_lost 5, priority 25
        "Q-PASS-IGNORE": {"value": True},  # PASS -> excluded from roadmap
        "Q-CRIT-UNVERIFIED": {"value": None}  # UNVERIFIED + CRITICAL -> included!
    }

    result = generate_roadmap_tasks_data(mock_questions, answers)
    buckets = result["buckets"]

    # 1. Bucket assignments
    assert len(buckets[30]) == 2
    assert len(buckets[60]) == 2  # Q-60-MED and Q-CRIT-UNVERIFIED
    assert len(buckets[90]) == 1
    assert len(buckets[180]) == 1

    # PASS question must be excluded
    all_qids = [t["question_id"] for h in buckets.values() for t in h]
    assert "Q-PASS-IGNORE" not in all_qids

    # 2. Ordering within 30-day bucket: weight x points_lost desc
    # Q-30-CRIT (priority 64) must come before Q-30-HIGH (priority 25)
    b30 = buckets[30]
    assert b30[0]["question_id"] == "Q-30-CRIT"
    assert b30[0]["priority_score"] == 64.0
    assert b30[1]["question_id"] == "Q-30-HIGH"
    assert b30[1]["priority_score"] == 25.0

    # 3. Ordering within 60-day bucket:
    # Q-CRIT-UNVERIFIED (priority 64) before Q-60-MED (priority 9)
    b60 = buckets[60]
    assert b60[0]["question_id"] == "Q-CRIT-UNVERIFIED"
    assert b60[0]["priority_score"] == 64.0
    assert b60[1]["question_id"] == "Q-60-MED"

    # 4. Strictly uses playbook text from question bank (no LLM generation)
    assert b30[0]["description"] == "Execute confirmatory assignment agreements for all historical contractors."
    assert b30[1]["description"] == "Enforce mandatory MFA across all identity providers within 30 days."


def test_roadmap_root_cause_grouping():
    """Validates root-cause clustering by dimension + sub_category."""
    mock_questions = [
        {
            "question_id": "Q-IP-1",
            "question_text": "IP assignment 1",
            "dimension": "INTELLECTUAL_PROPERTY",
            "sub_category": "Chain of Title",
            "risk_weight": "HIGH",
            "remediation_horizon_days": 30,
            "remediation_action": "Fix IP 1",
            "pass_rule": {"type": "BOOLEAN", "operator": "EQUALS", "value": True}
        },
        {
            "question_id": "Q-IP-2",
            "question_text": "IP assignment 2",
            "dimension": "INTELLECTUAL_PROPERTY",
            "sub_category": "Chain of Title",
            "risk_weight": "CRITICAL",
            "remediation_horizon_days": 60,
            "remediation_action": "Fix IP 2",
            "pass_rule": {"type": "BOOLEAN", "operator": "EQUALS", "value": True}
        },
        {
            "question_id": "Q-SEC-1",
            "question_text": "MFA requirement",
            "dimension": "CYBERSECURITY",
            "sub_category": "Access Control",
            "risk_weight": "HIGH",
            "remediation_horizon_days": 30,
            "remediation_action": "Fix SEC 1",
            "pass_rule": {"type": "BOOLEAN", "operator": "EQUALS", "value": True}
        }
    ]

    answers = {
        "Q-IP-1": {"value": False},
        "Q-IP-2": {"value": False},
        "Q-SEC-1": {"value": False}
    }

    result = generate_roadmap_tasks_data(mock_questions, answers)
    groups = result["groups"]

    # Should have 2 groups: IP::Chain of Title (2 tasks) and CYBERSECURITY::Access Control (1 task)
    assert len(groups) == 2
    ip_group = next(g for g in groups if g["sub_category"] == "Chain of Title")
    assert ip_group["dimension"] == "INTELLECTUAL_PROPERTY"
    assert ip_group["task_count"] == 2
    assert ip_group["total_points_recoverable"] == 13.0  # 5 + 8


def test_done_does_not_change_score():
    """
    CRITICAL REQUIREMENT:
    Users can mark tasks done, assign, and comment.
    Marking a task done MUST NOT change the assessment score.
    """
    # 1. Provision user & assessment
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    signup_res = client.post("/auth/signup", json={
        "full_name": "Bob Founder",
        "email": email,
        "password": "Password123!",
        "company_name": "Bob Tech"
    })
    token = signup_res.json()["access_token"]
    org_id = signup_res.json()["organization"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    ass_res = client.post(f"/orgs/{org_id}/assessments", headers=headers, json={
        "name": "Bob Tech Series A",
        "industry": "SOFTWARE",
        "sub_sector": "ALL",
        "transaction_type": "VC_GROWTH_FINANCING"
    })
    ass_id = ass_res.json()["assessment"]["id"]

    # 2. Get applicable questions
    q_res = client.get(f"/assessments/{ass_id}/questions", headers=headers)
    questions = q_res.json()["questions"]
    assert len(questions) > 0

    # 3. Answer half questions as False (FAIL) and compute initial score
    for q in questions[:5]:
        client.put(f"/assessments/{ass_id}/answers/{q['question_id']}", headers=headers, json={"value": False})

    score_res_1 = client.post(f"/assessments/{ass_id}/score", headers=headers)
    initial_score = score_res_1.json()["overall_score"]

    # 4. Get roadmap tasks
    roadmap_res = client.get(f"/assessments/{ass_id}/roadmap", headers=headers)
    assert roadmap_res.status_code == 200
    buckets = roadmap_res.json()["buckets"]
    all_tasks = [t for lane in buckets.values() for t in lane]
    assert len(all_tasks) > 0

    first_task = all_tasks[0]
    task_id = first_task["id"]

    # 5. Mark task as DONE, assign, and comment
    patch_res = client.patch(
        f"/assessments/{ass_id}/roadmap/tasks/{task_id}",
        headers=headers,
        json={
            "status": "done",
            "assignee": "sarah@bobtech.com",
            "comment": "Completed remediation playbook. Evidence attached."
        }
    )
    assert patch_res.status_code == 200
    updated_task = patch_res.json()
    assert updated_task["status"] == "done"
    assert updated_task["assignee"] == "sarah@bobtech.com"
    assert len(updated_task["comments"]) == 1
    assert "remediation playbook" in updated_task["comments"][0]["text"]

    # 6. Verify score is completely UNCHANGED
    trace_res = client.get(f"/assessments/{ass_id}/trace", headers=headers)
    assert trace_res.json()["overall_score"] == initial_score

    score_res_2 = client.post(f"/assessments/{ass_id}/score", headers=headers)
    assert score_res_2.json()["overall_score"] == initial_score


def test_delta_calculation():
    """
    PRD 9.3:
    Re-assessment saves each score run and shows delta view
    (per-dimension change and items that flipped from FAIL to PASS).
    """
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    signup_res = client.post("/auth/signup", json={
        "full_name": "Charlie Founder",
        "email": email,
        "password": "Password123!",
        "company_name": "Charlie Cloud"
    })
    token = signup_res.json()["access_token"]
    org_id = signup_res.json()["organization"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    ass_res = client.post(f"/orgs/{org_id}/assessments", headers=headers, json={
        "name": "Charlie Cloud Due Diligence",
        "industry": "SOFTWARE",
        "sub_sector": "ALL",
        "transaction_type": "VC_GROWTH_FINANCING"
    })
    ass_id = ass_res.json()["assessment"]["id"]

    q_res = client.get(f"/assessments/{ass_id}/questions", headers=headers)
    scorable_questions = [
        q for q in q_res.json()["questions"] 
        if (q.get("pass_rule") or {}).get("type") not in ("routing", "disclosed")
    ]
    q1 = scorable_questions[0]["question_id"]
    q2 = scorable_questions[1]["question_id"]

    # Run 1: q1 and q2 are FAIL
    client.put(f"/assessments/{ass_id}/answers/{q1}", headers=headers, json={"value": False})
    client.put(f"/assessments/{ass_id}/answers/{q2}", headers=headers, json={"value": False})
    run_1_res = client.post(f"/assessments/{ass_id}/score", headers=headers)
    score_1 = run_1_res.json()["overall_score"]

    # Initial delta has is_initial_assessment == True
    delta_initial = client.get(f"/assessments/{ass_id}/delta", headers=headers).json()
    assert delta_initial["is_initial_assessment"] is True

    # Run 2: Flip q1 from FAIL (False) to PASS (True)
    client.put(f"/assessments/{ass_id}/answers/{q1}", headers=headers, json={"value": True})
    run_2_res = client.post(f"/assessments/{ass_id}/score", headers=headers)
    score_2 = run_2_res.json()["overall_score"]
    assert score_2 > score_1

    # Delta view should show improvement and flipped item
    delta_res = client.get(f"/assessments/{ass_id}/delta", headers=headers)
    assert delta_res.status_code == 200
    delta = delta_res.json()

    assert delta["is_initial_assessment"] is False
    assert delta["overall_score_delta"] > 0.0
    assert delta["total_flipped_to_pass"] >= 1

    flipped_q1 = next((item for item in delta["flipped_items"] if item["question_id"] == q1), None)
    assert flipped_q1 is not None
    assert flipped_q1["flipped_to_pass"] is True
    assert flipped_q1["current_state"] == "PASS"


def test_pdf_report_generates_and_contains_disclaimer_and_versions():
    """
    PRD 9.4:
    PDF export: cover, summary, dimension scores, critical items, trace table,
    roadmap, methodology page (weights, config version, question bank version, best/worst case),
    and the statutory disclaimer from PRD section 1.
    """
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    signup_res = client.post("/auth/signup", json={
        "full_name": "Dana Founder",
        "email": email,
        "password": "Password123!",
        "company_name": "Dana Security"
    })
    token = signup_res.json()["access_token"]
    org_id = signup_res.json()["organization"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    ass_res = client.post(f"/orgs/{org_id}/assessments", headers=headers, json={
        "name": "Dana Security Audit",
        "industry": "SOFTWARE",
        "sub_sector": "ALL",
        "transaction_type": "VC_GROWTH_FINANCING"
    })
    ass_id = ass_res.json()["assessment"]["id"]

    # Put a failing answer to populate trace and roadmap
    q_res = client.get(f"/assessments/{ass_id}/questions", headers=headers)
    q0 = q_res.json()["questions"][0]["question_id"]
    client.put(f"/assessments/{ass_id}/answers/{q0}", headers=headers, json={"value": False})

    pdf_res = client.get(f"/assessments/{ass_id}/report.pdf", headers=headers)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF")

    # Read and inspect PDF text content
    doc = pymupdf.open(stream=pdf_res.content, filetype="pdf")
    assert len(doc) >= 4  # Multi-page editorial report

    all_text = " ".join([page.get_text() for page in doc])

    # 1. Statutory disclaimer from PRD Section 1 must be present
    assert DISCLAIMER_TEXT in all_text

    # 2. Config version and Question bank version
    assert "Config Version" in all_text or "Configuration:" in all_text
    assert "Question Bank Version" in all_text

    # 3. Best and Worst case score bounds
    assert "Worst:" in all_text or "worst_case" in all_text.lower()
    assert "Best:" in all_text or "best_case" in all_text.lower()

    # 4. Roadmap and Dimension scores
    assert "Remediation Roadmap" in all_text
    assert "Dimension Readiness Scores" in all_text


def test_tenant_isolation_m4_endpoints():
    """
    Tenant isolation tests for new M4 endpoints:
    - GET /assessments/{id}/roadmap
    - PATCH /assessments/{id}/roadmap/tasks/{task_id}
    - GET /assessments/{id}/delta
    - GET /assessments/{id}/report.pdf
    User from Org B cannot access Org A's roadmap, delta, or PDF report.
    """
    # 1. Setup Org A and Assessment A
    res_a = client.post("/auth/signup", json={
        "full_name": "Org A Lead",
        "email": f"lead_{uuid.uuid4().hex[:8]}@orga.com",
        "password": "Password123!",
        "company_name": "Org A Corp"
    })
    token_a = res_a.json()["access_token"]
    org_a_id = res_a.json()["organization"]["id"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    ass_a = client.post(f"/orgs/{org_a_id}/assessments", headers=headers_a, json={
        "name": "Org A Assessment",
        "industry": "SOFTWARE",
        "sub_sector": "ALL",
        "transaction_type": "VC_GROWTH_FINANCING"
    }).json()
    ass_a_id = ass_a["assessment"]["id"]

    # Org A populates roadmap
    rm_a = client.get(f"/assessments/{ass_a_id}/roadmap", headers=headers_a).json()
    all_tasks = [t for lane in rm_a["buckets"].values() for t in lane]
    task_a_id = all_tasks[0]["id"] if all_tasks else "task-none"

    # 2. Setup Org B
    res_b = client.post("/auth/signup", json={
        "full_name": "Org B Lead",
        "email": f"lead_{uuid.uuid4().hex[:8]}@orgb.com",
        "password": "Password123!",
        "company_name": "Org B Corp"
    })
    token_b = res_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 3. Org B attempts to access Org A's resources
    res_rm = client.get(f"/assessments/{ass_a_id}/roadmap", headers=headers_b)
    assert res_rm.status_code in (403, 404)

    res_patch = client.patch(
        f"/assessments/{ass_a_id}/roadmap/tasks/{task_a_id}",
        headers=headers_b,
        json={"status": "done"}
    )
    assert res_patch.status_code in (403, 404)

    res_delta = client.get(f"/assessments/{ass_a_id}/delta", headers=headers_b)
    assert res_delta.status_code in (403, 404)

    res_pdf = client.get(f"/assessments/{ass_a_id}/report.pdf", headers=headers_b)
    assert res_pdf.status_code in (403, 404)
