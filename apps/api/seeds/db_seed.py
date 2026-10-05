"""
Database Seeder for Diligence Readiness Platform.
Seeds:
- Demo Organization & Users (Founder, Advisor, Admin)
- Active Config Version (v1.0.0) with PRD Section 8 weights & thresholds
- All 153 normalized questions (Universal Core + 5 Industry Branches)
"""
import os
import json
import hashlib
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from apps.api.database import SessionLocal, engine, Base
from apps.api.models import Organization, User, Membership, ConfigVersion, Question, QuestionVersion
from apps.api.core.auth import hash_password


DEFAULT_WEIGHTS = {
    "severity": {
        "CRITICAL": 8,
        "HIGH": 5,
        "MEDIUM": 3,
        "LOW": 1
    },
    "transaction_matrices": {
        "VC_GROWTH_FINANCING": {
            "GOVERNANCE": 10,
            "FIN_CONTROLS": 10,
            "LEGAL_IP_REG": 15,
            "OPS_TECH_CYBER": 10,
            "HUMAN_CAPITAL": 5,
            "TXN_READINESS": 10,
            "FIN_PERFORMANCE": 15,
            "PROFIT_CASHFLOW": 10,
            "REVENUE_QUALITY": 10,
            "MGMT_DEPTH": 5,
            "CUSTOMER_MARKET": 5,
            "INDUSTRY_REG": 10
        },
        "M&A_SELL_SIDE": {
            "GOVERNANCE": 15,
            "FIN_CONTROLS": 15,
            "LEGAL_IP_REG": 20,
            "OPS_TECH_CYBER": 10,
            "HUMAN_CAPITAL": 10,
            "TXN_READINESS": 15,
            "FIN_PERFORMANCE": 10,
            "PROFIT_CASHFLOW": 10,
            "REVENUE_QUALITY": 10,
            "MGMT_DEPTH": 5,
            "CUSTOMER_MARKET": 5,
            "INDUSTRY_REG": 15
        },
        "IPO_PREP": {
            "GOVERNANCE": 20,
            "FIN_CONTROLS": 20,
            "LEGAL_IP_REG": 15,
            "OPS_TECH_CYBER": 10,
            "HUMAN_CAPITAL": 10,
            "TXN_READINESS": 15,
            "FIN_PERFORMANCE": 15,
            "PROFIT_CASHFLOW": 10,
            "REVENUE_QUALITY": 10,
            "MGMT_DEPTH": 10,
            "CUSTOMER_MARKET": 5,
            "INDUSTRY_REG": 15
        },
        "DEBT_FINANCING": {
            "GOVERNANCE": 10,
            "FIN_CONTROLS": 20,
            "LEGAL_IP_REG": 10,
            "OPS_TECH_CYBER": 5,
            "HUMAN_CAPITAL": 5,
            "TXN_READINESS": 10,
            "FIN_PERFORMANCE": 15,
            "PROFIT_CASHFLOW": 25,
            "REVENUE_QUALITY": 15,
            "MGMT_DEPTH": 5,
            "CUSTOMER_MARKET": 5,
            "INDUSTRY_REG": 10
        }
    }
}

DEFAULT_THRESHOLDS = {
    "critical_fail_cap": 60.0,
    "provisional_completeness_threshold": 60.0,
    "confidence_t_high": 0.85,
    "confidence_t_low": 0.50,
    "runway_months_critical": 6.0,
    "runway_months_partial": 9.0,
    "top1_customer_max_pct": 20.0,
    "nrr_min_pct": 100.0,
    "budget_variance_max_pct": 15.0,
    "ebitda_addbacks_max_pct": 10.0
}


def seed_database(db: Session = None) -> Dict[str, Any]:
    """Populates database with initial models, demo accounts, and all questions."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        # 1. Config Version
        active_config = db.query(ConfigVersion).filter_by(version_tag="v1.0.0").first()
        if not active_config:
            active_config = ConfigVersion(
                version_tag="v1.0.0",
                weights=DEFAULT_WEIGHTS,
                thresholds=DEFAULT_THRESHOLDS,
                is_active=True
            )
            db.add(active_config)
            db.commit()
            print("Seeded active ConfigVersion v1.0.0")

        # 2. Demo Org & Users
        org = db.query(Organization).filter_by(name="Acme Technology Holdings").first()
        if not org:
            org = Organization(name="Acme Technology Holdings")
            db.add(org)
            db.flush()

            demo_users = [
                ("founder@company.com", "Jane Founder", "Owner", False),
                ("admin@ledgerlight.io", "System Admin", "Owner", True),
                ("advisor@firm.com", "Sarah Counsel", "Advisor-guest", False),
            ]

            for email, name, role, is_admin in demo_users:
                user = db.query(User).filter_by(email=email).first()
                if not user:
                    user = User(
                        email=email,
                        hashed_password=hash_password("Password123!"),
                        full_name=name,
                        is_active=True,
                        is_admin=is_admin
                    )
                    db.add(user)
                    db.flush()

                    membership = Membership(
                        org_id=org.id,
                        user_id=user.id,
                        role=role
                    )
                    db.add(membership)

            db.commit()
            print("Seeded demo organization and users.")

        # 3. Seed Questions
        branch_path = "data/seeds/normalized_branch_questions.json"
        core_path = "data/seeds/draft_universal_core.json"

        all_q_data = []
        if os.path.exists(branch_path):
            with open(branch_path, "r", encoding="utf-8") as f:
                all_q_data.extend(json.load(f))
        if os.path.exists(core_path):
            with open(core_path, "r", encoding="utf-8") as f:
                all_q_data.extend(json.load(f))

        inserted_count = 0
        updated_count = 0

        for q_dict in all_q_data:
            qid = q_dict["question_id"]
            if q_dict.get("review_status") == "APPROVED":
                raise ValueError(
                    f"Seed scripts must NEVER set review_status=APPROVED. "
                    f"Question {qid} has review_status='APPROVED'. Human verification is required."
                )
            existing = db.query(Question).filter_by(question_id=qid).first()
            if existing:
                for k, v in q_dict.items():
                    setattr(existing, k, v)
                updated_count += 1
            else:
                new_q = Question(**q_dict)
                db.add(new_q)
                inserted_count += 1

        current_qids = {q_dict["question_id"] for q_dict in all_q_data}
        # Clean up any obsolete/migrated question IDs from earlier seed runs
        obsolete_count = 0
        obsolete_records = db.query(Question).filter(~Question.question_id.in_(current_qids)).all()
        for ob in obsolete_records:
            # Delete related question versions first
            db.query(QuestionVersion).filter_by(question_id=ob.question_id).delete()
            db.delete(ob)
            obsolete_count += 1

        db.commit()
        print(f"Seeded questions: {inserted_count} inserted, {updated_count} updated, {obsolete_count} obsolete removed. Total in DB: {db.query(Question).count()}")

        return {
            "questions_total": db.query(Question).count(),
            "inserted": inserted_count,
            "updated": updated_count
        }

    finally:
        if own_session:
            db.close()


if __name__ == "__main__":
    seed_database()
