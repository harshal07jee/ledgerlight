"""
Creates a rich test assessment with documents, extractions, score run, and roadmap tasks
specifically for browser verification of all frontend routes.
"""
from apps.api.database import SessionLocal
from apps.api.models import (
    User, Organization, Membership, Assessment, Answer, Question,
    ScoreRun, RoadmapTask, DataRoomDocument, ProposedExtraction
)
from apps.api.core.auth import create_session_token, hash_password
from apps.api.core.scoring import compute_readiness_score
from apps.api.core.roadmap import generate_roadmap_tasks_data
import uuid
from datetime import datetime

db = SessionLocal()
try:
    user = db.query(User).filter(User.email == "founder@company.com").first()
    if not user:
        user = User(
            email="founder@company.com",
            hashed_password=hash_password("Password123!"),
            full_name="Jane Founder",
            is_active=True,
            is_admin=False
        )
        db.add(user)
        db.flush()

    membership = db.query(Membership).filter(Membership.user_id == user.id).first()
    if not membership:
        org = Organization(name="Acme Technology Holdings")
        db.add(org)
        db.flush()
        membership = Membership(org_id=org.id, user_id=user.id, role="Owner")
        db.add(membership)
        db.flush()
    else:
        org = db.query(Organization).filter(Organization.id == membership.org_id).first()

    # Create test assessment
    asmt_id = "test-browser-asmt-001"
    asmt = db.query(Assessment).filter(Assessment.id == asmt_id).first()
    if asmt:
        db.delete(asmt)
        db.commit()

    asmt = Assessment(
        id=asmt_id,
        org_id=org.id,
        name="Browser Verification SaaS Assessment",
        industry="SOFTWARE",
        sub_sector="B2B_ENTERPRISE",
        stage="Series B",
        transaction_type="VC_GROWTH_FINANCING",
        geography=["USA"],
        status="in_progress"
    )
    db.add(asmt)
    db.flush()

    # Add documents
    doc1 = DataRoomDocument(
        assessment_id=asmt.id,
        org_id=org.id,
        filename="Q4_2025_Financial_Statements.xlsx",
        file_type="financial_statement",
        file_size=512000,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        page_count=4,
        status="processed",
        stage="classified"
    )
    doc2 = DataRoomDocument(
        assessment_id=asmt.id,
        org_id=org.id,
        filename="December_2025_Bank_Statement.pdf",
        file_type="bank_statement",
        file_size=204800,
        sha256="ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
        mime_type="application/pdf",
        page_count=2,
        status="processed",
        stage="classified"
    )
    db.add_all([doc1, doc2])
    db.flush()

    # Add proposed extractions
    ext1 = ProposedExtraction(
        assessment_id=asmt.id,
        document_id=doc1.id,
        question_id="CORE_PERF_01",
        answer_value=75.0,
        confidence=1.0,
        status="AUTO_FILLED",
        method="FINANCIAL_TABLE",
        source_file=doc1.filename,
        page=1,
        snippet="Revenue: $10,500,000.00 | COGS: $2,625,000.00 | Gross Margin: 75.0%",
        formula="gross_margin_pct = ((revenue - cogs) / revenue) * 100",
        formula_inputs={"revenue": 10500000.0, "cogs": 2625000.0}
    )
    ext2 = ProposedExtraction(
        assessment_id=asmt.id,
        document_id=doc2.id,
        question_id="CORE_FIN_02",
        answer_value=15.0,
        confidence=0.70,
        status="NEEDS_CONFIRMATION",
        method="FINANCIAL_TABLE",
        source_file=doc2.filename,
        page=1,
        snippet="Cash Balance: $2,250,000.00 | Net Burn: $150,000.00 | Runway: 15.0m",
        formula="runway_months = cash_balance / net_monthly_burn",
        formula_inputs={"cash_balance": 2250000.0, "net_monthly_burn": 150000.0}
    )
    db.add_all([ext1, ext2])
    db.flush()

    # Add some answers
    ans1 = Answer(
        assessment_id=asmt.id,
        question_id="CORE_PERF_01",
        value=75.0,
        user_action="accepted"
    )
    ans2 = Answer(
        assessment_id=asmt.id,
        question_id="CORE_GOV_01",
        value=True,
        user_action="manual"
    )
    ans3 = Answer(
        assessment_id=asmt.id,
        question_id="CORE_LEGAL_01",
        value=False,
        user_action="manual"
    )
    db.add_all([ans1, ans2, ans3])
    db.flush()

    # Compute a score run
    questions = db.query(Question).filter(Question.review_status != "DRAFT").all()
    q_dicts = [
        {
            "question_id": q.question_id,
            "dimension": q.dimension,
            "sub_category": q.sub_category,
            "risk_weight": q.risk_weight,
            "pass_rule": q.pass_rule,
            "input_type": q.input_type,
            "evidence_type": q.evidence_type,
            "review_status": q.review_status,
            "remediation_action": q.remediation_action,
            "remediation_horizon_days": q.remediation_horizon_days
        }
        for q in questions
    ]
    answers_dict = {
        "CORE_PERF_01": {"value": 75.0, "origin": "evidence-backed"},
        "CORE_GOV_01": {"value": True, "origin": "evidence-backed"},
        "CORE_LEGAL_01": {"value": False, "origin": "self-attested"}
    }
    score_out = compute_readiness_score(q_dicts, answers_dict, company_profile={"transaction_type": "VC_GROWTH_FINANCING"})

    score_run = ScoreRun(
        assessment_id=asmt.id,
        overall_score=score_out["overall_score"],
        unconstrained_score=score_out.get("unconstrained_score", score_out["overall_score"]),
        best_case_score=score_out.get("best_case_score", score_out["overall_score"]),
        worst_case_score=score_out.get("worst_case_score", score_out["overall_score"]),
        completeness_pct=score_out["completeness"]["completeness_pct"],
        is_provisional=score_out["completeness"]["is_provisional"],
        critical_cap_applied=score_out.get("critical_cap_applied", False),
        failed_critical_count=score_out.get("failed_critical_count", 0),
        dimension_scores=score_out["dimension_scores"],
        failed_critical_items=score_out.get("failed_critical_items", []),
        weight_origin_share=score_out.get("weight_origin_share", {}),
        unscored_disclosures=score_out.get("unscored_disclosures", []),
        scored_question_review_status=score_out.get("scored_question_review_status", {}),
        config_version=score_out["config_version"],
        question_bank_version=score_out["question_bank_version"]
    )
    db.add(score_run)
    db.flush()

    # Generate roadmap tasks
    roadmap_data = generate_roadmap_tasks_data(q_dicts, answers_dict)
    all_tasks = [t for bucket in roadmap_data["buckets"].values() for t in bucket]
    for td in all_tasks:
        task = RoadmapTask(
            assessment_id=asmt.id,
            question_id=td["question_id"],
            title=td["title"],
            description=td["description"],
            dimension=td["dimension"],
            sub_category=td["sub_category"],
            horizon_days=td["horizon_days"],
            risk_weight=td["risk_weight"],
            weight_value=td["weight_value"],
            points_recoverable=td["points_recoverable"],
            priority_score=td["priority_score"],
            source_doc=td["source_doc"],
            source_ref=td["source_ref"],
            status="todo"
        )
        db.add(task)

    db.commit()

    # Create session token
    token = create_session_token(user.id, db)
    print("Test assessment created:", asmt.id)
    print("Session token:", token)
    print("User ID:", user.id)
finally:
    db.close()
