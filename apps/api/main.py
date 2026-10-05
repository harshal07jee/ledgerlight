"""
FastAPI Application for Diligence Readiness Platform (Ledgerlight).
Implements M0 foundations, M1 Question Bank Admin APIs, and M2 Questionnaire without AI.
"""
import os
import uuid
import hashlib
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query, Response, Request, status, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from enum import Enum
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

logger = logging.getLogger("ledgerlight.main")

from apps.api.database import get_db, engine, Base
from apps.api.core.auth import (
    require_admin,
    get_current_user,
    hash_password,
    verify_password,
    check_login_rate_limit,
    record_failed_login,
    reset_failed_login,
    verify_assessment_access,
    verify_org_access,
    create_session_token,
    revoke_session_token
)
from apps.api.core.dependencies import is_question_applicable
from apps.api.models import (
    Organization,
    User,
    Membership,
    AuditLog,
    ConfigVersion,
    Question,
    QuestionVersion,
    Assessment,
    Answer,
    ScoreRun,
    ScoreTraceRow,
    RoadmapTask,
    DataRoomDocument,
    ProposedExtraction,
    ExtractionAuditLog
)
from apps.api.core.scoring import compute_readiness_score, load_scoring_config
from apps.api.core.roadmap import generate_roadmap_tasks_data, compute_reassessment_delta
from apps.api.core.pdf_export import generate_assessment_pdf
from apps.api.core.ingest import (
    validate_file_security,
    validate_and_extract_zip,
    parse_document,
    sweep_temp_files,
    IngestSecurityError
)
from apps.api.core.extractors import (
    extract_answer_for_question,
    compute_extraction_coverage_report
)
from packages.schema.models import QuestionSchema, ReviewStatusEnum

# Initialize tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Ledgerlight Diligence Readiness API",
    description="Explainable, rules-based diligence readiness platform API.",
    version="1.0.0"
)

# CORS configuration
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    os.getenv("FRONTEND_URL", "http://localhost:3000")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CSRF protection middleware for cookie-authenticated state-changing requests (Requirement 8)
ALLOWED_CSRF_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://testserver",
    os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/"),
}

@app.middleware("http")
async def csrf_protect_middleware(request: Request, call_next):
    # Only state-changing methods are subject to CSRF protection
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        has_cookie = "ledgerlight_session" in request.cookies
        auth_header = request.headers.get("authorization", "")
        has_bearer = auth_header.lower().startswith("bearer ")

        # When relying on ambient cookie authentication without an explicit Bearer header
        if has_cookie and not has_bearer:
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")

            request_origin = None
            if origin:
                request_origin = origin.rstrip("/")
            elif referer:
                from urllib.parse import urlparse
                parsed_ref = urlparse(referer)
                if parsed_ref.scheme and parsed_ref.netloc:
                    request_origin = f"{parsed_ref.scheme}://{parsed_ref.netloc}"

            host_header = request.headers.get("host", "")
            valid_origins = set(ALLOWED_CSRF_ORIGINS)
            if host_header:
                valid_origins.add(f"http://{host_header}")
                valid_origins.add(f"https://{host_header}")

            if not request_origin or request_origin not in valid_origins:
                # Disallow cross-origin requests for cookie-authenticated mutations
                if request.url.path not in ("/auth/login", "/auth/signup", "/auth/logout"):
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "CSRF verification failed: cross-origin request rejected"}
                    )

    response = await call_next(request)
    return response




DIMENSION_DISPLAY_NAMES = {
    "GOVERNANCE": "Governance & Corporate Structure",
    "FIN_CONTROLS": "Financial Controls & Reporting",
    "LEGAL_IP_REG": "Legal, IP & Regulatory",
    "OPS_TECH_CYBER": "Operations, Technology & Cyber",
    "HUMAN_CAPITAL": "Human Capital / HR",
    "TXN_READINESS": "Transaction & Investor Readiness",
    "FIN_PERFORMANCE": "Financial Performance & Growth",
    "PROFIT_CASHFLOW": "Profitability & Cash Flow",
    "REVENUE_QUALITY": "Revenue Quality & Concentration",
    "MGMT_DEPTH": "Management Team Depth",
    "CUSTOMER_MARKET": "Customer & Market Position",
    "INDUSTRY_REG": "Industry Regulatory & Technical Branch"
}

STANDARD_DIMENSION_ORDER = [
    "GOVERNANCE",
    "FIN_CONTROLS",
    "LEGAL_IP_REG",
    "OPS_TECH_CYBER",
    "HUMAN_CAPITAL",
    "TXN_READINESS",
    "FIN_PERFORMANCE",
    "PROFIT_CASHFLOW",
    "REVENUE_QUALITY",
    "MGMT_DEPTH",
    "CUSTOMER_MARKET",
    "INDUSTRY_REG"
]


# --- Pydantic Schemas ---

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    database: str
    total_questions: int
    approved_questions: int
    unreviewed_seed_questions: int = 0
    ai_pre_reviewed_questions: int = 0
    draft_questions: int


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    full_name: str
    email: str
    password: str
    company_name: str


class TransactionTypeEnum(str, Enum):
    VC_GROWTH_FINANCING = "VC_GROWTH_FINANCING"
    M_AND_A_SELL_SIDE = "M&A_SELL_SIDE"
    IPO_PREP = "IPO_PREP"
    DEBT_FINANCING = "DEBT_FINANCING"


class IndustryEnum(str, Enum):
    UNIVERSAL = "UNIVERSAL"
    HEALTHCARE = "HEALTHCARE"
    FINTECH = "FINTECH"
    SOFTWARE = "SOFTWARE"
    MANUFACTURING = "MANUFACTURING"
    ENERGY = "ENERGY"


VALID_TRANSACTION_TYPES = {
    "VC_GROWTH_FINANCING",
    "M&A_SELL_SIDE",
    "IPO_PREP",
    "DEBT_FINANCING",
}

VALID_INDUSTRIES = {
    "UNIVERSAL",
    "HEALTHCARE",
    "FINTECH",
    "SOFTWARE",
    "MANUFACTURING",
    "ENERGY",
}

VALID_STAGES = {
    "STARTUP",
    "GROWTH",
    "ESTABLISHED",
    "MATURE",
    "ALL",
}

VALID_SUB_SECTORS_NORMALIZED = {
    "ALL",
    "MEDICAL_DEVICES",
    "DIGITAL_HEALTH",
    "BIOTECHNOLOGY",
    "PHARMACEUTICALS",
    "PAYMENTS/MSB",
    "LENDING",
    "DIGITAL ASSETS",
    "WEALTHTECH/RIA",
    "B2B ENTERPRISE SAAS",
    "AI INFRASTRUCTURE",
    "CONTRACT MANUFACTURER",
    "HEAVY INDUSTRIAL EQUIPMENT",
    "CHEMICALS AND MATERIALS",
    "SOLAR & WIND GENERATION",
    "BATTERY & ENERGY STORAGE",
    "GRID INFRASTRUCTURE / OT",
}


def _validate_industry(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v_norm = v.strip().upper()
    if v_norm not in VALID_INDUSTRIES:
        raise ValueError(f"Unknown industry '{v}'. Valid industries: {sorted(list(VALID_INDUSTRIES))}")
    return v_norm


def _validate_sub_sector(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v_norm = v.strip().upper()
    if v_norm not in VALID_SUB_SECTORS_NORMALIZED:
        raise ValueError(f"Unknown sub_sector '{v}'. Valid sub_sectors include: 'ALL' or specific industry sub_sectors.")
    return v.strip()


def _validate_stage(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v_norm = v.strip().upper()
    if v_norm not in VALID_STAGES:
        raise ValueError(f"Unknown stage '{v}'. Valid stages: Startup, Growth, Established, Mature, ALL")
    return v.strip().capitalize() if v_norm != "ALL" else "ALL"


def _validate_transaction_type(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v_clean = v.strip()
    if v_clean == "M_AND_A_SELL_SIDE":
        v_clean = "M&A_SELL_SIDE"
    if v_clean not in VALID_TRANSACTION_TYPES:
        raise ValueError(
            f"Unknown transaction_type '{v}'. Valid transaction types: {sorted(list(VALID_TRANSACTION_TYPES))}"
        )
    return v_clean


class CreateAssessmentRequest(BaseModel):
    name: Optional[str] = "Diligence Readiness Assessment"
    industry: str
    sub_sector: Optional[str] = "ALL"
    stage: Optional[str] = "Growth"
    transaction_type: Optional[str] = "VC_GROWTH_FINANCING"
    geography: Optional[List[str]] = ["USA"]

    @field_validator("industry")
    @classmethod
    def check_industry(cls, v: str) -> str:
        return _validate_industry(v)

    @field_validator("sub_sector")
    @classmethod
    def check_sub_sector(cls, v: Optional[str]) -> Optional[str]:
        return _validate_sub_sector(v)

    @field_validator("stage")
    @classmethod
    def check_stage(cls, v: Optional[str]) -> Optional[str]:
        return _validate_stage(v)

    @field_validator("transaction_type")
    @classmethod
    def check_transaction_type(cls, v: Optional[str]) -> Optional[str]:
        return _validate_transaction_type(v)


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    sub_sector: Optional[str] = None
    stage: Optional[str] = None
    transaction_type: Optional[str] = None
    confirm_discard_answers: bool = False

    @field_validator("industry")
    @classmethod
    def check_industry(cls, v: Optional[str]) -> Optional[str]:
        return _validate_industry(v)

    @field_validator("sub_sector")
    @classmethod
    def check_sub_sector(cls, v: Optional[str]) -> Optional[str]:
        return _validate_sub_sector(v)

    @field_validator("stage")
    @classmethod
    def check_stage(cls, v: Optional[str]) -> Optional[str]:
        return _validate_stage(v)

    @field_validator("transaction_type")
    @classmethod
    def check_transaction_type(cls, v: Optional[str]) -> Optional[str]:
        return _validate_transaction_type(v)


class AnswerRequest(BaseModel):
    value: Any
    notes: Optional[str] = None
    user_action: Optional[str] = "manual"


class ApproveQuestionRequest(BaseModel):
    reviewer_name: str
    last_verified_on: str
    verification_notes: Optional[str] = None


# --- Helper Functions ---

def q_to_dict(q: Question) -> Dict[str, Any]:
    """Converts a Question SQLAlchemy model to dict for applicability engine."""
    return {
        "question_id": q.question_id,
        "scope": q.scope,
        "industry": q.industry,
        "sub_sector": q.sub_sector,
        "geography": q.geography,
        "stage": q.stage,
        "dimension": q.dimension,
        "sub_category": q.sub_category,
        "question_text": q.question_text,
        "input_type": q.input_type,
        "options": q.options,
        "depends_on": q.depends_on,
        "risk_weight": q.risk_weight,
        "pass_rule": q.pass_rule,
        "evidence_type": q.evidence_type,
        "extraction_hint": q.extraction_hint,
        "remediation_action": q.remediation_action,
        "remediation_horizon_days": q.remediation_horizon_days,
        "source_doc": q.source_doc,
        "source_ref": q.source_ref,
        "last_verified_on": q.last_verified_on,
        "reviewer_name": getattr(q, "reviewer_name", None),
        "review_status": q.review_status,
    }


def compute_assessment_questions(
    assessment: Assessment,
    db: Session,
    include_drafts: bool = False
) -> Dict[str, Any]:
    """
    Evaluates which questions are applicable using company profile and depends_on rules.
    Prunes non-applicable questions and returns grouped questionnaire data with progress.
    """
    # 1. Fetch questions from DB
    q_query = db.query(Question)
    if not include_drafts:
        # Show APPROVED, UNREVIEWED_SEED, and AI_PRE_REVIEWED to users; exclude DRAFT
        q_query = q_query.filter(
            Question.review_status.in_([
                ReviewStatusEnum.APPROVED.value,
                ReviewStatusEnum.UNREVIEWED_SEED.value,
                ReviewStatusEnum.AI_PRE_REVIEWED.value
            ])
        )
    all_q_models = q_query.order_by(Question.question_id).all()

    # 2. Fetch existing answers and proposed extractions for assessment
    existing_answers = db.query(Answer).filter(Answer.assessment_id == assessment.id).all()
    answers_dict = {a.question_id: a.value for a in existing_answers if a.value is not None}
    answers_by_qid = {a.question_id: a for a in existing_answers}

    extractions = db.query(ProposedExtraction).filter(ProposedExtraction.assessment_id == assessment.id).all()
    extractions_by_qid = {e.question_id: e for e in extractions}

    # Auto-filled or confirmed extractions supply answers for dependencies if not manually answered
    for ext in extractions:
        if ext.question_id not in answers_dict:
            if ext.user_action == "confirmed" and ext.confirmed_value is not None:
                answers_dict[ext.question_id] = ext.confirmed_value
            elif ext.status == "AUTO_FILLED" and ext.user_action != "rejected" and ext.answer_value is not None:
                answers_dict[ext.question_id] = ext.answer_value

    # 3. Build lookup maps
    all_questions_by_id = {q.question_id: q_to_dict(q) for q in all_q_models}

    company_profile = {
        "industry": assessment.industry,
        "sub_sector": assessment.sub_sector,
        "stage": assessment.stage,
        "transaction_type": assessment.transaction_type,
        "geography": assessment.geography or ["USA"]
    }

    # 4. Evaluate applicability
    applicable_questions = []
    for q in all_q_models:
        q_dict = dict(all_questions_by_id[q.question_id])
        if is_question_applicable(q_dict, company_profile, answers_dict, all_questions_by_id):
            ans = answers_by_qid.get(q.question_id)
            ext = extractions_by_qid.get(q.question_id)

            if ans and ans.value is not None:
                q_dict["current_answer"] = ans.value
                q_dict["notes"] = ans.notes
                q_dict["user_action"] = ans.user_action or "manual"
                q_dict["updated_at"] = ans.updated_at.isoformat()
            elif ext and ext.user_action == "confirmed":
                q_dict["current_answer"] = ext.confirmed_value if ext.confirmed_value is not None else ext.answer_value
                q_dict["notes"] = f"Confirmed extraction ({ext.source_file}, p. {ext.page})"
                q_dict["user_action"] = "confirmed"
                q_dict["updated_at"] = ext.updated_at.isoformat()
            elif ext and ext.status == "AUTO_FILLED" and ext.user_action != "rejected":
                q_dict["current_answer"] = ext.answer_value
                q_dict["notes"] = f"Auto-filled from {ext.source_file} (p. {ext.page})"
                q_dict["user_action"] = "auto"
                q_dict["updated_at"] = ext.updated_at.isoformat()
            else:
                q_dict["current_answer"] = None
                q_dict["notes"] = None
                q_dict["user_action"] = None
                q_dict["updated_at"] = None

            if ext:
                q_dict["extraction"] = {
                    "id": ext.id,
                    "answer_value": ext.answer_value,
                    "confidence": ext.confidence,
                    "status": ext.status,
                    "method": ext.method,
                    "source_file": ext.source_file,
                    "page": ext.page,
                    "snippet": ext.snippet,
                    "formula": ext.formula,
                    "formula_inputs": ext.formula_inputs,
                    "user_action": ext.user_action,
                    "confirmed_value": ext.confirmed_value
                }
            applicable_questions.append(q_dict)

    # 5. Group by dimension
    dim_buckets = {d: [] for d in STANDARD_DIMENSION_ORDER}
    for q in applicable_questions:
        d = q.get("dimension", "OTHER")
        if d not in dim_buckets:
            dim_buckets[d] = []
        dim_buckets[d].append(q)

    by_dimension = []
    for d in STANDARD_DIMENSION_ORDER:
        qs = dim_buckets.get(d, [])
        if qs:  # Only include dimensions that have applicable questions
            answered = sum(1 for q in qs if q["current_answer"] is not None)
            by_dimension.append({
                "dimension": d,
                "dimension_name": DIMENSION_DISPLAY_NAMES.get(d, d),
                "total": len(qs),
                "answered": answered,
                "questions": qs
            })

    # Add any dimensions outside the standard list if any
    for d, qs in dim_buckets.items():
        if d not in STANDARD_DIMENSION_ORDER and qs:
            answered = sum(1 for q in qs if q["current_answer"] is not None)
            by_dimension.append({
                "dimension": d,
                "dimension_name": DIMENSION_DISPLAY_NAMES.get(d, d),
                "total": len(qs),
                "answered": answered,
                "questions": qs
            })

    total_applicable = len(applicable_questions)
    answered_count = sum(1 for q in applicable_questions if q["current_answer"] is not None)
    completeness_pct = round((answered_count / total_applicable * 100), 1) if total_applicable > 0 else 0.0
    hidden_count = len(all_q_models) - total_applicable

    return {
        "assessment": {
            "id": assessment.id,
            "org_id": assessment.org_id,
            "name": assessment.name,
            "industry": assessment.industry,
            "sub_sector": assessment.sub_sector,
            "stage": assessment.stage,
            "transaction_type": assessment.transaction_type,
            "geography": assessment.geography,
            "status": assessment.status
        },
        "progress": {
            "total_applicable": total_applicable,
            "answered_count": answered_count,
            "completeness_pct": completeness_pct,
            "is_provisional": completeness_pct < 60.0,
            "hidden_not_applicable_count": hidden_count
        },
        "by_dimension": by_dimension,
        "questions": applicable_questions
    }


# --- Core System Endpoints ---

@app.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """System health check and question inventory count."""
    try:
        total_q = db.query(Question).count()
        approved_q = db.query(Question).filter(Question.review_status == ReviewStatusEnum.APPROVED.value).count()
        unreviewed_seed_q = db.query(Question).filter(Question.review_status == ReviewStatusEnum.UNREVIEWED_SEED.value).count()
        ai_pre_reviewed_q = db.query(Question).filter(Question.review_status == ReviewStatusEnum.AI_PRE_REVIEWED.value).count()
        draft_q = db.query(Question).filter(Question.review_status == ReviewStatusEnum.DRAFT.value).count()
        return HealthResponse(
            status="ok",
            timestamp=datetime.utcnow().isoformat(),
            database="connected",
            total_questions=total_q,
            approved_questions=approved_q,
            unreviewed_seed_questions=unreviewed_seed_q,
            ai_pre_reviewed_questions=ai_pre_reviewed_q,
            draft_questions=draft_q
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database check failed: {str(e)}")


@app.get("/config/active")
def get_active_config(db: Session = Depends(get_db)):
    """Retrieves active weights matrix and thresholds."""
    cfg = db.query(ConfigVersion).filter(ConfigVersion.is_active == True).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="No active config version found.")
    return {
        "version_tag": cfg.version_tag,
        "weights": cfg.weights,
        "thresholds": cfg.thresholds,
        "created_at": cfg.created_at.isoformat()
    }


# --- Auth & Onboarding Endpoints (M2 & PRD Section 11) ---

@app.post("/auth/signup")
def signup(
    req: SignupRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """Creates user, organization, and membership for new accounts; sets HttpOnly cookie."""
    existing_user = db.query(User).filter(User.email == req.email.strip().lower()).first()
    if existing_user:
        membership = db.query(Membership).filter(Membership.user_id == existing_user.id).first()
        org = db.query(Organization).filter(Organization.id == membership.org_id).first() if membership else None
        token = create_session_token(existing_user.id, db)
        response.set_cookie(
            key="ledgerlight_session",
            value=token,
            httponly=True,
            samesite="strict",
            secure=os.getenv("SECURE_COOKIES", "false").lower() == "true",
            path="/"
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": existing_user.id,
                "email": existing_user.email,
                "full_name": existing_user.full_name,
                "is_admin": existing_user.is_admin,
                "org_id": org.id if org else None,
                "role": membership.role if membership else "Owner"
            },
            "organization": {
                "id": org.id if org else "",
                "name": org.name if org else req.company_name
            }
        }

    org = Organization(name=req.company_name.strip() or "My Company")
    db.add(org)
    db.flush()

    user = User(
        email=req.email.strip().lower(),
        hashed_password=hash_password(req.password),
        full_name=req.full_name.strip(),
        is_active=True,
        is_admin=False
    )
    db.add(user)
    db.flush()

    membership = Membership(
        org_id=org.id,
        user_id=user.id,
        role="Owner"
    )
    db.add(membership)
    db.commit()

    token = create_session_token(user.id, db)
    response.set_cookie(
        key="ledgerlight_session",
        value=token,
        httponly=True,
        samesite="strict",
        secure=os.getenv("SECURE_COOKIES", "false").lower() == "true",
        path="/"
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_admin": user.is_admin,
            "org_id": org.id,
            "role": "Owner"
        },
        "organization": {
            "id": org.id,
            "name": org.name
        }
    }


@app.post("/auth/login")
def login(
    creds: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Authenticates user, verifies password against hash, applies sliding-window
    rate limiting and account lockout, and issues both access_token and HttpOnly cookie.
    Generates a cryptographically random 256-bit token stored hashed in user_sessions.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    client_key = f"{client_ip}:{creds.email.strip().lower()}"

    check_login_rate_limit(client_key)

    user = db.query(User).filter(User.email == creds.email.strip().lower()).first()
    if not user or not verify_password(creds.password, user.hashed_password):
        record_failed_login(client_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    # Login successful: clear failure history
    reset_failed_login(client_key)

    membership = db.query(Membership).filter(Membership.user_id == user.id).first()
    token = create_session_token(user.id, db)

    response.set_cookie(
        key="ledgerlight_session",
        value=token,
        httponly=True,
        samesite="strict",
        secure=os.getenv("SECURE_COOKIES", "false").lower() == "true",
        path="/"
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_admin": user.is_admin,
            "org_id": membership.org_id if membership else None,
            "role": membership.role if membership else None
        }
    }


@app.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Clears the HttpOnly session cookie and revokes session token in database."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    elif "ledgerlight_session" in request.cookies:
        token = request.cookies.get("ledgerlight_session", "").strip()

    if token:
        revoke_session_token(token, db)

    response.delete_cookie(key="ledgerlight_session", path="/" )
    return {"status": "logged_out"}



@app.get("/me")
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns authenticated user profile."""
    membership = db.query(Membership).filter(Membership.user_id == current_user.id).first()
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_admin": current_user.is_admin,
        "org_id": membership.org_id if membership else None,
        "role": membership.role if membership else None
    }


# --- Organization & Tenant Isolation Endpoints (PRD Section 11.3) ---

@app.get("/orgs/{org_id}")
def get_organization(
    org_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieves organization details if current user belongs to the org."""
    org = verify_org_access(org_id, current_user, db)
    return {
        "id": org.id,
        "name": org.name,
        "created_at": org.created_at.isoformat()
    }


@app.get("/orgs/{org_id}/assessments")
def list_org_assessments(
    org_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists assessments belonging exclusively to the authorized organization."""
    org = verify_org_access(org_id, current_user, db)
    assessments = db.query(Assessment).filter(Assessment.org_id == org.id).all()
    return {
        "organization_id": org.id,
        "assessments": [
            {
                "id": a.id,
                "name": a.name,
                "industry": a.industry,
                "sub_sector": a.sub_sector,
                "stage": a.stage,
                "transaction_type": a.transaction_type,
                "status": a.status,
                "created_at": a.created_at.isoformat()
            }
            for a in assessments
        ]
    }


# --- Assessment & Questionnaire Endpoints (M2 & Tenant-Isolated) ---

@app.post("/orgs/{org_id}/assessments")
def create_assessment(
    org_id: str,
    req: CreateAssessmentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Creates a new assessment within the caller's authorized organization."""
    org = verify_org_access(org_id, current_user, db, require_edit=True)

    assessment = Assessment(
        org_id=org.id,
        name=req.name.strip() or f"{org.name} Diligence Assessment",
        industry=req.industry.strip().upper(),
        sub_sector=req.sub_sector.strip() if req.sub_sector else "ALL",
        stage=req.stage.strip() if req.stage else "Growth",
        transaction_type=req.transaction_type.strip() if req.transaction_type else "VC_GROWTH_FINANCING",
        geography=req.geography or ["USA"],
        status="in_progress"
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    # Initial assessment data with applicable questions
    data = compute_assessment_questions(assessment, db)
    return {
        "status": "created",
        "assessment": data["assessment"],
        "progress": data["progress"],
        "by_dimension": data["by_dimension"]
    }


@app.get("/assessments/{assessment_id}")
def get_assessment(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieves assessment metadata and current progress for authorized tenant."""
    assessment = verify_assessment_access(assessment_id, current_user, db)

    data = compute_assessment_questions(assessment, db)
    return {
        "assessment": data["assessment"],
        "progress": data["progress"]
    }


@app.patch("/assessments/{assessment_id}/profile")
def update_assessment_profile(
    assessment_id: str,
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates company profile attributes.
    If industry changes, detects whether branch answers exist and raises 409 Conflict
    unless confirm_discard_answers is True.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db, require_edit=True)

    # Check for industry change
    new_industry = req.industry.strip().upper() if req.industry else None
    if new_industry and new_industry != assessment.industry:
        # Count branch answers specific to current industry
        current_branch_answers = (
            db.query(Answer)
            .join(Question, Answer.question_id == Question.question_id)
            .filter(
                Answer.assessment_id == assessment.id,
                Question.scope == "BRANCH",
                Question.industry == assessment.industry
            )
            .all()
        )
        discard_count = len(current_branch_answers)

        if discard_count > 0 and not req.confirm_discard_answers:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "warning": (
                        f"Changing industry from {assessment.industry} to {new_industry} "
                        f"will discard {discard_count} answers specific to {assessment.industry}. "
                        "Universal Core answers will be preserved."
                    ),
                    "discard_count": discard_count,
                    "current_industry": assessment.industry,
                    "new_industry": new_industry
                }
            )

        # User confirmed discard: prune old branch answers
        if discard_count > 0:
            for ans in current_branch_answers:
                db.delete(ans)

        assessment.industry = new_industry

    if req.name is not None:
        assessment.name = req.name.strip()
    if req.sub_sector is not None:
        assessment.sub_sector = req.sub_sector.strip()
    if req.stage is not None:
        assessment.stage = req.stage.strip()
    if req.transaction_type is not None:
        assessment.transaction_type = req.transaction_type.strip()

    db.commit()
    db.refresh(assessment)

    data = compute_assessment_questions(assessment, db)
    return {
        "status": "updated",
        "assessment": data["assessment"],
        "progress": data["progress"],
        "by_dimension": data["by_dimension"]
    }


@app.get("/assessments/{assessment_id}/questions")
def get_assessment_questions(
    assessment_id: str,
    include_drafts: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns applicable questions grouped by dimension for authorized tenant.
    Prunes non-applicable questions whose depends_on rules or profile requirements are not met.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db)

    return compute_assessment_questions(assessment, db, include_drafts=include_drafts)


@app.put("/assessments/{assessment_id}/answers/{question_id}")
def autosave_answer(
    assessment_id: str,
    question_id: str,
    req: AnswerRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Autosaves or updates an answer for a question in an assessment (authorized tenant).
    Re-evaluates applicability and returns fresh completeness metrics.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db, require_edit=True)

    q = db.query(Question).filter(Question.question_id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail=f"Question {question_id} not found.")

    answer = db.query(Answer).filter(
        Answer.assessment_id == assessment_id,
        Answer.question_id == question_id
    ).first()

    if answer:
        answer.value = req.value
        if req.notes is not None:
            answer.notes = req.notes
        if req.user_action:
            answer.user_action = req.user_action
        answer.updated_at = datetime.utcnow()
    else:
        answer = Answer(
            assessment_id=assessment_id,
            question_id=question_id,
            value=req.value,
            notes=req.notes,
            user_action=req.user_action or "manual"
        )
        db.add(answer)

    db.commit()
    db.refresh(answer)

    # Re-evaluate progress
    progress_data = compute_assessment_questions(assessment, db)["progress"]

    return {
        "status": "saved",
        "assessment_id": assessment_id,
        "question_id": question_id,
        "value": answer.value,
        "updated_at": answer.updated_at.isoformat(),
        "progress": progress_data
    }


# --- Scoring & Explainability Trace Endpoints (M3 & PRD Section 8) ---

@app.post("/assessments/{assessment_id}/score")
def calculate_assessment_score(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Computes deterministic diligence readiness score and trace for an assessment.
    Stores ScoreRun and ScoreTraceRow records for auditable versioning.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db, require_edit=True)

    # 1. Fetch active config
    active_cfg = db.query(ConfigVersion).filter(ConfigVersion.is_active == True).first()
    config_dict = None
    if active_cfg:
        config_dict = {
            "config_version": active_cfg.version_tag,
            "severity_weights": active_cfg.weights.get("severity", {}),
            "partial_score_multiplier": active_cfg.thresholds.get("partial_score_multiplier", 0.5),
            "critical_fail_cap": active_cfg.thresholds.get("critical_fail_cap", 60.0),
            "provisional_threshold_pct": active_cfg.thresholds.get("provisional_completeness_threshold", 60.0),
            "transaction_matrices": active_cfg.weights.get("transaction_matrices", {})
        }
    if not config_dict or not config_dict.get("transaction_matrices"):
        config_dict = load_scoring_config()

    # 2. Get applicable questions
    q_data = compute_assessment_questions(assessment, db)
    applicable_questions = q_data["questions"]

    # 3. Get answers map
    existing_answers = db.query(Answer).filter(Answer.assessment_id == assessment_id).all()
    answers_map = {
        a.question_id: {
            "value": a.value,
            "notes": a.notes,
            "user_action": a.user_action or "manual",
            "evidence_file_id": a.evidence_file_id
        }
        for a in existing_answers
    }

    # Integrate extractions: confirmed or AUTO_FILLED
    extractions = db.query(ProposedExtraction).filter(ProposedExtraction.assessment_id == assessment_id).all()
    for ext in extractions:
        qid = ext.question_id
        if qid not in answers_map or answers_map[qid]["value"] is None:
            if ext.user_action == "confirmed":
                val = ext.confirmed_value if ext.confirmed_value is not None else ext.answer_value
                answers_map[qid] = {
                    "value": val,
                    "notes": f"Confirmed extraction from {ext.source_file or 'data room'} (p. {ext.page or 1})",
                    "user_action": "confirmed",
                    "evidence_snippet": ext.snippet
                }
            elif ext.status == "AUTO_FILLED" and ext.user_action != "rejected":
                answers_map[qid] = {
                    "value": ext.answer_value,
                    "notes": f"Auto-filled from {ext.source_file or 'data room'} (p. {ext.page or 1})",
                    "user_action": "auto",
                    "evidence_snippet": ext.snippet
                }

    # 4. Assessment profile
    company_profile = {
        "industry": assessment.industry,
        "sub_sector": assessment.sub_sector,
        "stage": assessment.stage,
        "transaction_type": assessment.transaction_type,
        "geography": assessment.geography or ["USA"]
    }

    # 5. Call pure deterministic scoring function
    score_result = compute_readiness_score(
        applicable_questions=applicable_questions,
        answers=answers_map,
        company_profile=company_profile,
        config=config_dict
    )

    # 6. Save ScoreRun record
    score_run = ScoreRun(
        assessment_id=assessment.id,
        overall_score=score_result["overall_score"],
        unconstrained_score=score_result["unconstrained_score"],
        best_case_score=score_result.get("best_case_score"),
        worst_case_score=score_result.get("worst_case_score"),
        completeness_pct=score_result["completeness"]["completeness_pct"],
        is_provisional=score_result["completeness"]["is_provisional"],
        critical_cap_applied=score_result["critical_cap_applied"],
        failed_critical_count=score_result["failed_critical_count"],
        dimension_scores=score_result["dimension_scores"],
        failed_critical_items=score_result["failed_critical_items"],
        weight_origin_share=score_result.get("weight_origin_share"),
        unscored_disclosures=score_result.get("unscored_disclosures"),
        scored_question_review_status=score_result.get("scored_question_review_status"),
        config_version=score_result["config_version"],
        question_bank_version=score_result["question_bank_version"]
    )
    db.add(score_run)
    db.flush()

    # 7. Save ScoreTraceRow records
    for row in score_result["trace_rows"]:
        trace_record = ScoreTraceRow(
            score_run_id=score_run.id,
            question_id=row["question_id"],
            question_text=row["question_text"],
            dimension=row["dimension"],
            risk_weight=row["risk_weight"],
            weight_value=row["weight_value"],
            answer_state=row["answer_state"],
            user_answer=row["user_answer"],
            expected_rule=row["expected_rule"],
            points_lost=row["points_lost"],
            source_doc=row["source_doc"],
            source_ref=row["source_ref"],
            evidence_snippet=row["evidence_snippet"],
            answer_origin=row["answer_origin"],
            origin=row.get("origin", "self-attested"),
            notes=row["notes"],
            is_critical_fail=row["is_critical_fail"]
        )
        db.add(trace_record)

    db.commit()
    db.refresh(score_run)

    score_result["id"] = score_run.id
    score_result["assessment_id"] = assessment.id
    score_result["created_at"] = score_run.created_at.isoformat()
    return score_result


@app.get("/assessments/{assessment_id}/trace")
def get_assessment_trace(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns the latest score trace and deduction breakdown for an assessment.
    If no score has been computed yet, computes one.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db)

    latest_run = (
        db.query(ScoreRun)
        .filter(ScoreRun.assessment_id == assessment_id)
        .order_by(ScoreRun.created_at.desc())
        .first()
    )

    if not latest_run:
        return calculate_assessment_score(assessment_id, current_user, db)

    trace_records = (
        db.query(ScoreTraceRow)
        .filter(ScoreTraceRow.score_run_id == latest_run.id)
        .order_by(ScoreTraceRow.points_lost.desc())
        .all()
    )

    trace_rows = [
        {
            "id": r.id,
            "question_id": r.question_id,
            "question_text": r.question_text,
            "dimension": r.dimension,
            "risk_weight": r.risk_weight,
            "weight_value": r.weight_value,
            "answer_state": r.answer_state,
            "user_answer": r.user_answer,
            "expected_rule": r.expected_rule,
            "points_lost": r.points_lost,
            "source_doc": r.source_doc,
            "source_ref": r.source_ref,
            "evidence_snippet": r.evidence_snippet,
            "answer_origin": r.answer_origin,
            "origin": r.origin or "self-attested",
            "notes": r.notes,
            "is_critical_fail": r.is_critical_fail
        }
        for r in trace_records
    ]

    return {
        "assessment_id": assessment_id,
        "score_run_id": latest_run.id,
        "overall_score": latest_run.overall_score,
        "unconstrained_score": latest_run.unconstrained_score,
        "best_case_score": latest_run.best_case_score if latest_run.best_case_score is not None else latest_run.overall_score,
        "worst_case_score": latest_run.worst_case_score if latest_run.worst_case_score is not None else latest_run.overall_score,
        "critical_cap_applied": latest_run.critical_cap_applied,
        "failed_critical_count": latest_run.failed_critical_count,
        "failed_critical_items": latest_run.failed_critical_items,
        "completeness": {
            "completeness_pct": latest_run.completeness_pct,
            "is_provisional": latest_run.is_provisional,
        },
        "dimension_scores": latest_run.dimension_scores,
        "weight_origin_share": latest_run.weight_origin_share or {},
        "unscored_disclosures": latest_run.unscored_disclosures or [],
        "scored_question_review_status": latest_run.scored_question_review_status or {},
        "trace_rows": trace_rows,
        "total_deductions": len(trace_rows),
        "total_points_lost": round(sum(r["points_lost"] for r in trace_rows), 2),
        "transaction_type": assessment.transaction_type,
        "config_version": latest_run.config_version,
        "question_bank_version": latest_run.question_bank_version,
        "created_at": latest_run.created_at.isoformat()
    }


# --- Remediation Roadmap & Reporting Endpoints (M4 & PRD Sections 9.1, 9.3, 9.4) ---

class UpdateRoadmapTaskRequest(BaseModel):
    status: Optional[str] = None  # todo, in_progress, done
    assignee: Optional[str] = None
    comment: Optional[str] = None


@app.get("/assessments/{assessment_id}/roadmap")
def get_assessment_roadmap(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generates and returns remediation roadmap for an assessment (PRD Section 9.1 & FR-8).
    - 4 horizon lanes: 30, 60, 90, 180 days.
    - Tasks sorted by priority_score = weight * points_lost descending.
    - Root-cause clustering by dimension + sub_category.
    - Strict question bank playbook text only (NO LLM generation).
    - Synchronizes tasks with DB to preserve assignments, status, and comments.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db)

    # 1. Fetch active config
    active_cfg = db.query(ConfigVersion).filter(ConfigVersion.is_active == True).first()
    config_dict = None
    if active_cfg:
        config_dict = {
            "config_version": active_cfg.version_tag,
            "severity_weights": active_cfg.weights.get("severity", {}),
            "partial_score_multiplier": active_cfg.thresholds.get("partial_score_multiplier", 0.5),
            "critical_fail_cap": active_cfg.thresholds.get("critical_fail_cap", 60.0),
            "provisional_threshold_pct": active_cfg.thresholds.get("provisional_completeness_threshold", 60.0),
            "transaction_matrices": active_cfg.weights.get("transaction_matrices", {})
        }
    if not config_dict or not config_dict.get("transaction_matrices"):
        config_dict = load_scoring_config()

    # 2. Get applicable questions
    q_data = compute_assessment_questions(assessment, db)
    applicable_questions = q_data["questions"]

    # 3. Get answers map
    existing_answers = db.query(Answer).filter(Answer.assessment_id == assessment_id).all()
    answers_map = {
        a.question_id: {
            "value": a.value,
            "notes": a.notes,
            "user_action": a.user_action,
            "evidence_file_id": a.evidence_file_id
        }
        for a in existing_answers
    }

    # 4. Generate pure deterministic roadmap tasks
    roadmap_data = generate_roadmap_tasks_data(
        applicable_questions=applicable_questions,
        answers=answers_map,
        config=config_dict
    )

    # 5. Synchronize with database roadmap_tasks to preserve user state
    db_tasks = db.query(RoadmapTask).filter(RoadmapTask.assessment_id == assessment_id).all()
    db_task_map = {t.question_id: t for t in db_tasks}

    for h in [30, 60, 90, 180]:
        for t in roadmap_data["buckets"][h]:
            qid = t["question_id"]
            if qid in db_task_map:
                existing = db_task_map[qid]
                t["id"] = existing.id
                t["status"] = existing.status
                t["assignee"] = existing.assignee
                t["comments"] = existing.comments or []
                existing.points_recoverable = t["points_recoverable"]
                existing.priority_score = t["priority_score"]
                existing.weight_value = t["weight_value"]
                existing.horizon_days = t["horizon_days"]
            else:
                new_t = RoadmapTask(
                    assessment_id=assessment_id,
                    question_id=qid,
                    title=t["title"],
                    description=t["description"],
                    dimension=t["dimension"],
                    sub_category=t["sub_category"],
                    horizon_days=t["horizon_days"],
                    risk_weight=t["risk_weight"],
                    weight_value=t["weight_value"],
                    points_recoverable=t["points_recoverable"],
                    priority_score=t["priority_score"],
                    source_doc=t.get("source_doc"),
                    source_ref=t.get("source_ref"),
                    status="todo",
                    assignee=None,
                    comments=[]
                )
                db.add(new_t)
                db.flush()
                t["id"] = new_t.id

    db.commit()

    return {
        "assessment_id": assessment_id,
        "buckets": roadmap_data["buckets"],
        "groups": roadmap_data["groups"],
        "summary": roadmap_data["summary"]
    }


@app.patch("/assessments/{assessment_id}/roadmap/tasks/{task_id}")
def update_roadmap_task(
    assessment_id: str,
    task_id: str,
    body: UpdateRoadmapTaskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates roadmap task status (todo/done), assignee, or appends a comment.
    CRITICAL: Marking done must NOT alter the readiness score.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db, require_edit=True)
    task = (
        db.query(RoadmapTask)
        .filter(RoadmapTask.id == task_id, RoadmapTask.assessment_id == assessment_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Roadmap task not found")

    if body.status is not None:
        if body.status not in ["todo", "in_progress", "done"]:
            raise HTTPException(status_code=400, detail="Invalid status. Must be todo, in_progress, or done")
        task.status = body.status

    if body.assignee is not None:
        task.assignee = body.assignee.strip() if body.assignee.strip() else None

    if body.comment is not None and body.comment.strip():
        existing_comments = list(task.comments or [])
        new_comment = {
            "id": str(uuid.uuid4()),
            "author": current_user.full_name or current_user.email,
            "text": body.comment.strip(),
            "created_at": datetime.utcnow().isoformat()
        }
        existing_comments.append(new_comment)
        task.comments = existing_comments

    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)

    return {
        "id": task.id,
        "assessment_id": task.assessment_id,
        "question_id": task.question_id,
        "title": task.title,
        "description": task.description,
        "dimension": task.dimension,
        "sub_category": task.sub_category,
        "horizon_days": task.horizon_days,
        "risk_weight": task.risk_weight,
        "weight_value": task.weight_value,
        "points_recoverable": task.points_recoverable,
        "priority_score": task.priority_score,
        "source_doc": task.source_doc,
        "source_ref": task.source_ref,
        "status": task.status,
        "assignee": task.assignee,
        "comments": task.comments or [],
        "updated_at": task.updated_at.isoformat()
    }


@app.get("/assessments/{assessment_id}/delta")
def get_assessment_delta(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Computes delta between the latest two score runs (PRD Section 9.3).
    Returns overall delta, unconstrained delta, completeness delta,
    per-dimension changes, and items that flipped from FAIL/PARTIAL to PASS.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db)

    runs = (
        db.query(ScoreRun)
        .filter(ScoreRun.assessment_id == assessment_id)
        .order_by(ScoreRun.created_at.desc())
        .limit(2)
        .all()
    )

    if len(runs) == 0:
        return {
            "is_initial_assessment": True,
            "overall_score_delta": 0.0,
            "unconstrained_score_delta": 0.0,
            "completeness_delta": 0.0,
            "critical_cap_status": {
                "previous_capped": False,
                "current_capped": False,
                "cap_lifted": False,
                "cap_imposed": False
            },
            "dimension_deltas": [],
            "flipped_items": [],
            "total_flipped_to_pass": 0,
            "current_run_id": None,
            "previous_run_id": None
        }

    current_run = runs[0]
    previous_run = runs[1] if len(runs) > 1 else None

    # Load trace rows for runs
    curr_traces = (
        db.query(ScoreTraceRow)
        .filter(ScoreTraceRow.score_run_id == current_run.id)
        .all()
    )
    curr_trace_dicts = [
        {
            "question_id": t.question_id,
            "question_text": t.question_text,
            "dimension": t.dimension,
            "answer_state": t.answer_state,
            "points_lost": t.points_lost,
            "source_doc": t.source_doc,
            "source_ref": t.source_ref
        }
        for t in curr_traces
    ]

    prev_trace_dicts = None
    if previous_run:
        prev_traces = (
            db.query(ScoreTraceRow)
            .filter(ScoreTraceRow.score_run_id == previous_run.id)
            .all()
        )
        prev_trace_dicts = [
            {
                "question_id": t.question_id,
                "question_text": t.question_text,
                "dimension": t.dimension,
                "answer_state": t.answer_state,
                "points_lost": t.points_lost,
                "source_doc": t.source_doc,
                "source_ref": t.source_ref
            }
            for t in prev_traces
        ]

    curr_dict = {
        "id": current_run.id,
        "overall_score": current_run.overall_score,
        "unconstrained_score": current_run.unconstrained_score,
        "completeness_pct": current_run.completeness_pct,
        "critical_cap_applied": current_run.critical_cap_applied,
        "dimension_scores": current_run.dimension_scores or {},
        "created_at": current_run.created_at.isoformat()
    }
    prev_dict = None
    if previous_run:
        prev_dict = {
            "id": previous_run.id,
            "overall_score": previous_run.overall_score,
            "unconstrained_score": previous_run.unconstrained_score,
            "completeness_pct": previous_run.completeness_pct,
            "critical_cap_applied": previous_run.critical_cap_applied,
            "dimension_scores": previous_run.dimension_scores or {},
            "created_at": previous_run.created_at.isoformat()
        }

    return compute_reassessment_delta(
        current_run=curr_dict,
        previous_run=prev_dict,
        current_trace_rows=curr_trace_dicts,
        previous_trace_rows=prev_trace_dicts
    )


@app.get("/assessments/{assessment_id}/report.pdf")
def get_assessment_pdf_report(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generates and returns an audit-grade branded PDF report (PRD Section 9.4).
    Contains: cover, executive summary, dimension scores, critical items,
    trace table, roadmap, methodology governance page, and PRD Section 1 disclaimer.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db)

    # 1. Fetch latest score run, or calculate if none
    latest_run = (
        db.query(ScoreRun)
        .filter(ScoreRun.assessment_id == assessment_id)
        .order_by(ScoreRun.created_at.desc())
        .first()
    )
    if not latest_run:
        calculate_assessment_score(assessment_id, current_user, db)
        latest_run = (
            db.query(ScoreRun)
            .filter(ScoreRun.assessment_id == assessment_id)
            .order_by(ScoreRun.created_at.desc())
            .first()
        )

    # 2. Trace rows
    trace_records = (
        db.query(ScoreTraceRow)
        .filter(ScoreTraceRow.score_run_id == latest_run.id)
        .order_by(ScoreTraceRow.points_lost.desc())
        .all()
    )
    trace_rows = [
        {
            "question_id": r.question_id,
            "question_text": r.question_text,
            "dimension": r.dimension,
            "risk_weight": r.risk_weight,
            "weight_value": r.weight_value,
            "answer_state": r.answer_state,
            "user_answer": r.user_answer,
            "expected_rule": r.expected_rule,
            "points_lost": r.points_lost,
            "source_doc": r.source_doc,
            "source_ref": r.source_ref,
            "is_critical_fail": r.is_critical_fail
        }
        for r in trace_records
    ]

    # 3. Roadmap data
    roadmap_resp = get_assessment_roadmap(assessment_id, current_user, db)

    # 4. Prepare data packets
    assessment_data = {
        "id": assessment.id,
        "name": assessment.name,
        "industry": assessment.industry,
        "sub_sector": assessment.sub_sector,
        "stage": assessment.stage,
        "transaction_type": assessment.transaction_type,
        "geography": assessment.geography or ["USA"]
    }

    score_data = {
        "overall_score": latest_run.overall_score,
        "unconstrained_score": latest_run.unconstrained_score,
        "best_case_score": latest_run.best_case_score if latest_run.best_case_score is not None else latest_run.overall_score,
        "worst_case_score": latest_run.worst_case_score if latest_run.worst_case_score is not None else latest_run.overall_score,
        "completeness": {
            "completeness_pct": latest_run.completeness_pct,
            "is_provisional": latest_run.is_provisional
        },
        "critical_cap_applied": latest_run.critical_cap_applied,
        "failed_critical_items": latest_run.failed_critical_items or [],
        "dimension_scores": latest_run.dimension_scores or {},
        "weight_origin_share": latest_run.weight_origin_share or {},
        "unscored_disclosures": latest_run.unscored_disclosures or [],
        "scored_question_review_status": latest_run.scored_question_review_status or {},
        "config_version": latest_run.config_version,
        "question_bank_version": latest_run.question_bank_version
    }

    pdf_bytes = generate_assessment_pdf(
        assessment_data=assessment_data,
        score_data=score_data,
        trace_rows=trace_rows,
        roadmap_data=roadmap_resp
    )

    clean_filename = f"ledgerlight_report_{assessment_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{clean_filename}"'
        }
    )


# --- Public & Admin Question Bank Endpoints (M1) ---

@app.get("/questions")
def get_public_questions(
    industry: Optional[str] = None,
    dimension: Optional[str] = None,
    include_drafts: bool = False,
    db: Session = Depends(get_db)
):
    """
    Returns questions for standard assessments.
    Per PRD 6.2 rule: Rows with review_status != APPROVED MUST NOT be shown
    to normal users unless include_drafts=true (admin testing toggle).
    """
    query = db.query(Question)

    if not include_drafts:
        query = query.filter(
            Question.review_status.in_([
                ReviewStatusEnum.APPROVED.value,
                ReviewStatusEnum.UNREVIEWED_SEED.value,
                ReviewStatusEnum.AI_PRE_REVIEWED.value
            ])
        )

    if industry and industry.upper() != "ALL":
        query = query.filter(Question.industry.in_(["UNIVERSAL", industry.upper()]))

    if dimension:
        query = query.filter(Question.dimension == dimension.upper())

    results = query.all()
    return [q_to_dict(q) for q in results]


@app.get("/admin/questions")
def list_admin_questions(
    industry: Optional[str] = None,
    dimension: Optional[str] = None,
    review_status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin console question bank list with full review status filtering."""
    query = db.query(Question)

    if industry and industry.upper() != "ALL":
        query = query.filter(Question.industry == industry.upper())

    if dimension:
        query = query.filter(Question.dimension == dimension.upper())

    if review_status:
        query = query.filter(Question.review_status == review_status.upper())

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (Question.question_text.ilike(search_pattern)) |
            (Question.question_id.ilike(search_pattern)) |
            (Question.source_doc.ilike(search_pattern))
        )

    total_count = query.count()
    items = query.order_by(Question.question_id).offset(offset).limit(limit).all()

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "question_id": q.question_id,
                "scope": q.scope,
                "industry": q.industry,
                "sub_sector": q.sub_sector,
                "dimension": q.dimension,
                "question_text": q.question_text,
                "input_type": q.input_type,
                "risk_weight": q.risk_weight,
                "evidence_type": q.evidence_type,
                "review_status": q.review_status,
                "source_doc": q.source_doc,
                "source_ref": q.source_ref,
                "remediation_horizon_days": q.remediation_horizon_days,
                "last_verified_on": q.last_verified_on
            }
            for q in items
        ]
    }


@app.get("/admin/questions/{question_id}")
def get_question_detail(
    question_id: str,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Retrieves full details and version history of a question."""
    q = db.query(Question).filter(Question.question_id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    versions = db.query(QuestionVersion).filter(QuestionVersion.question_id == question_id).order_by(QuestionVersion.version_number.desc()).all()

    return {
        "question": q_to_dict(q),
        "versions": [
            {
                "version_number": v.version_number,
                "changed_by": v.changed_by,
                "change_reason": v.change_reason,
                "created_at": v.created_at.isoformat()
            }
            for v in versions
        ]
    }


@app.post("/admin/questions/{question_id}/approve")
def approve_question(
    question_id: str,
    req: ApproveQuestionRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Approve a draft question for live usage.
    Requires reviewer_name and last_verified_on (YYYY-MM-DD).
    Verifies that pass_rule, citation, and horizon are valid per M1 acceptance.
    """
    import re
    if not req.reviewer_name or not req.reviewer_name.strip():
        raise HTTPException(status_code=400, detail="reviewer_name is required to approve.")
    if not req.last_verified_on or not req.last_verified_on.strip():
        raise HTTPException(status_code=400, detail="last_verified_on is required to approve.")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", req.last_verified_on.strip()):
        raise HTTPException(status_code=400, detail="last_verified_on must be formatted as YYYY-MM-DD.")

    q = db.query(Question).filter(Question.question_id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    if not q.pass_rule:
        raise HTTPException(status_code=400, detail="Cannot approve: missing pass_rule.")
    if not q.source_doc:
        raise HTTPException(status_code=400, detail="Cannot approve: missing source_doc citation.")
    if not q.remediation_horizon_days:
        raise HTTPException(status_code=400, detail="Cannot approve: missing remediation horizon.")

    # Snapshot previous version
    existing_versions = db.query(QuestionVersion).filter(QuestionVersion.question_id == question_id).count()
    version_record = QuestionVersion(
        question_id=question_id,
        version_number=existing_versions + 1,
        snapshot={
            "review_status": q.review_status,
            "question_text": q.question_text,
            "pass_rule": q.pass_rule,
            "last_verified_on": q.last_verified_on
        },
        changed_by=req.reviewer_name.strip(),
        change_reason=f"Approved: {req.verification_notes or 'Human review complete'}"
    )
    db.add(version_record)

    q.review_status = ReviewStatusEnum.APPROVED.value
    q.last_verified_on = req.last_verified_on.strip()
    q.reviewer_name = req.reviewer_name.strip()
    db.commit()

    return {
        "status": "success",
        "question_id": question_id,
        "review_status": q.review_status,
        "last_verified_on": q.last_verified_on,
        "reviewer_name": req.reviewer_name.strip()
    }


@app.get("/admin/metrics/coverage")
def get_admin_coverage_metrics(
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Returns real-time question bank coverage and routing statistics."""
    total = db.query(Question).count()
    approved = db.query(Question).filter(Question.review_status == "APPROVED").count()
    draft = db.query(Question).filter(Question.review_status == "DRAFT").count()

    by_evidence = {}
    for ev in ["CONTRACT_CLAUSE", "FINANCIAL_TABLE", "CERTIFICATE_OR_REPORT", "POLICY_DOC", "SELF_ATTESTED"]:
        by_evidence[ev] = db.query(Question).filter(Question.evidence_type == ev).count()

    auto_extractable = sum(by_evidence[k] for k in ["CONTRACT_CLAUSE", "FINANCIAL_TABLE", "CERTIFICATE_OR_REPORT", "POLICY_DOC"])
    manual = by_evidence["SELF_ATTESTED"]

    return {
        "total_questions": total,
        "approved": approved,
        "draft": draft,
        "auto_extractable": auto_extractable,
        "auto_extractable_pct": round((auto_extractable / total * 100), 1) if total else 0,
        "manual_required": manual,
        "manual_required_pct": round((manual / total * 100), 1) if total else 0,
        "by_evidence_type": by_evidence
    }


# --- M5 Data Room & Extraction Endpoints (PRD Section 7 & FR-3, FR-4) ---

class UpdateDocTypeRequest(BaseModel):
    file_type: str


class ConfirmExtractionRequest(BaseModel):
    confirmed_value: Optional[Any] = None


class BulkConfirmRequest(BaseModel):
    extraction_ids: Optional[List[str]] = None
    min_confidence: Optional[float] = 0.85


@app.post("/assessments/{assessment_id}/documents/upload")
async def upload_documents(
    assessment_id: str,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Uploads and processes documents for an assessment data room (M5).
    - Validates MIME and magic bytes, size limits, rejects executables.
    - Blocks zip bombs and path traversal.
    - Processes in-memory, deletes temp files immediately, keeps only metadata & snippets <= 500 chars.
    - Deterministic extraction on applicable questions.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db, require_edit=True)

    uploaded_docs: List[DataRoomDocument] = []
    parsed_docs: List[ParsedDocument] = []

    for file in files:
        try:
            content = await file.read()
            filename = file.filename or "unknown"

            # 1. Detect if it is a ZIP archive bundle
            is_zip = filename.lower().endswith(".zip")

            if is_zip:
                # Security validation on zip wrapper
                validate_file_security(filename, content)
                extracted_items = validate_and_extract_zip(content)
                del content  # In-memory discard of archive

                for rel_name, item_bytes in extracted_items:
                    validate_file_security(rel_name, item_bytes)
                    item_sha = hashlib.sha256(item_bytes).hexdigest()

                    parsed = parse_document(rel_name, item_bytes)
                    del item_bytes  # Immediate in-memory discard of raw bytes

                    parsed_docs.append(parsed)

                    parsed_warns = "; ".join(parsed.warnings) if getattr(parsed, "warnings", None) else None
                    doc = DataRoomDocument(
                        assessment_id=assessment.id,
                        org_id=assessment.org_id,
                        filename=rel_name,
                        file_type=parsed.file_type or "unclassified",
                        file_size=parsed.file_size or 0,
                        sha256=item_sha,
                        mime_type=parsed.mime_type or "application/octet-stream",
                        page_count=parsed.page_count or len(parsed.pages),
                        status="processed",
                        stage="classified",
                        error_message=parsed_warns
                    )
                    db.add(doc)
                    db.flush()
                    uploaded_docs.append(doc)
            else:
                # Single document
                validate_file_security(filename, content)
                file_sha = hashlib.sha256(content).hexdigest()

                parsed = parse_document(filename, content)
                del content  # Immediate in-memory discard of raw file

                parsed_docs.append(parsed)

                parsed_warns = "; ".join(parsed.warnings) if getattr(parsed, "warnings", None) else None
                doc = DataRoomDocument(
                    assessment_id=assessment.id,
                    org_id=assessment.org_id,
                    filename=filename,
                    file_type=parsed.file_type or "unclassified",
                    file_size=parsed.file_size or 0,
                    sha256=file_sha,
                    mime_type=parsed.mime_type or "application/octet-stream",
                    page_count=parsed.page_count or len(parsed.pages),
                    status="processed",
                    stage="classified",
                    error_message=parsed_warns
                )
                db.add(doc)
                db.flush()
                uploaded_docs.append(doc)

        except IngestSecurityError as se:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(se))
        except ValueError as ve:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
        except Exception as e:
            logger.error("Upload processing error for assessment %s: %s", assessment_id, str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Processing error: {str(e)}")

    # Run deterministic extractions on all applicable questions for this assessment
    q_data = compute_assessment_questions(assessment, db)
    applicable_questions = q_data["questions"]

    # Map filename to doc_id for referencing
    doc_id_map = {d.filename: d.id for d in uploaded_docs}

    created_extractions_count = 0
    for q in applicable_questions:
        ext = extract_answer_for_question(q, parsed_docs, assessment_id=assessment.id)
        if ext and ext["status"] in ("AUTO_FILLED", "NEEDS_CONFIRMATION"):
            qid = q["question_id"]
            matched_doc_id = doc_id_map.get(ext.get("source_file"))

            existing = (
                db.query(ProposedExtraction)
                .filter(
                    ProposedExtraction.assessment_id == assessment.id,
                    ProposedExtraction.question_id == qid
                )
                .first()
            )

            if existing:
                if existing.user_action != "confirmed":
                    existing.answer_value = ext["answer_value"]
                    existing.confidence = ext["confidence"]
                    existing.status = ext["status"]
                    existing.method = ext["method"]
                    existing.source_file = ext.get("source_file")
                    existing.page = ext.get("page")
                    existing.char_start = ext.get("char_start")
                    existing.char_end = ext.get("char_end")
                    existing.snippet = ext.get("snippet")
                    existing.formula = ext.get("formula")
                    existing.formula_inputs = ext.get("formula_inputs")
                    existing.document_id = matched_doc_id
                    existing.updated_at = datetime.utcnow()
            else:
                new_ext = ProposedExtraction(
                    assessment_id=assessment.id,
                    document_id=matched_doc_id,
                    question_id=qid,
                    answer_value=ext["answer_value"],
                    confidence=ext["confidence"],
                    status=ext["status"],
                    method=ext["method"],
                    source_file=ext.get("source_file"),
                    page=ext.get("page"),
                    char_start=ext.get("char_start"),
                    char_end=ext.get("char_end"),
                    snippet=ext.get("snippet"),
                    formula=ext.get("formula"),
                    formula_inputs=ext.get("formula_inputs"),
                    user_action="pending"
                )
                db.add(new_ext)
                created_extractions_count += 1

    # Cleanup temp sweeper
    sweep_temp_files()

    db.commit()

    return {
        "status": "success",
        "documents_uploaded": len(uploaded_docs),
        "extractions_found": created_extractions_count,
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "file_type": d.file_type,
                "file_size": d.file_size,
                "sha256": d.sha256,
                "page_count": d.page_count,
                "status": d.status,
                "stage": d.stage
            }
            for d in uploaded_docs
        ]
    }


@app.get("/assessments/{assessment_id}/documents")
def list_documents(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists data room documents for an assessment."""
    assessment = verify_assessment_access(assessment_id, current_user, db)
    docs = db.query(DataRoomDocument).filter(DataRoomDocument.assessment_id == assessment.id).all()
    return {
        "assessment_id": assessment.id,
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "file_type": d.file_type,
                "file_size": d.file_size,
                "sha256": d.sha256,
                "mime_type": d.mime_type,
                "page_count": d.page_count,
                "status": d.status,
                "stage": d.stage,
                "error_message": d.error_message,
                "created_at": d.created_at.isoformat()
            }
            for d in docs
        ]
    }


@app.patch("/assessments/{assessment_id}/documents/{document_id}")
def update_document_classification(
    assessment_id: str,
    document_id: str,
    req: UpdateDocTypeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Corrects heuristic document classification type."""
    assessment = verify_assessment_access(assessment_id, current_user, db, require_edit=True)
    doc = db.query(DataRoomDocument).filter(
        DataRoomDocument.id == document_id,
        DataRoomDocument.assessment_id == assessment.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.file_type = req.file_type.strip().lower()
    doc.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(doc)
    return {
        "status": "updated",
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type
    }


@app.delete("/assessments/{assessment_id}/documents/{document_id}")
def delete_document(
    assessment_id: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deletes document and its associated proposed extractions."""
    assessment = verify_assessment_access(assessment_id, current_user, db, require_edit=True)
    doc = db.query(DataRoomDocument).filter(
        DataRoomDocument.id == document_id,
        DataRoomDocument.assessment_id == assessment.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove extractions tied to this document
    db.query(ProposedExtraction).filter(
        ProposedExtraction.assessment_id == assessment.id,
        ProposedExtraction.document_id == document_id
    ).delete()

    db.delete(doc)
    db.commit()
    return {"status": "deleted", "id": document_id}


@app.get("/assessments/{assessment_id}/extractions")
def list_extractions(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists all proposed extractions with confidence, source snippet, and formula."""
    assessment = verify_assessment_access(assessment_id, current_user, db)
    extractions = (
        db.query(ProposedExtraction)
        .filter(ProposedExtraction.assessment_id == assessment.id)
        .all()
    )
    return {
        "assessment_id": assessment.id,
        "extractions": [
            {
                "id": e.id,
                "question_id": e.question_id,
                "document_id": e.document_id,
                "answer_value": e.answer_value,
                "confidence": e.confidence,
                "status": e.status,
                "method": e.method,
                "source_file": e.source_file,
                "page": e.page,
                "char_start": e.char_start,
                "char_end": e.char_end,
                "snippet": e.snippet,
                "formula": e.formula,
                "formula_inputs": e.formula_inputs,
                "user_action": e.user_action,
                "confirmed_value": e.confirmed_value,
                "created_at": e.created_at.isoformat(),
                "updated_at": e.updated_at.isoformat()
            }
            for e in extractions
        ]
    }


@app.post("/assessments/{assessment_id}/extractions/{extraction_id}/confirm")
def confirm_extraction(
    assessment_id: str,
    extraction_id: str,
    body: Optional[ConfirmExtractionRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Confirms an extraction proposal.
    Optionally accepts a corrected confirmed_value.
    Synchronizes into assessment answers map for scoring.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db, require_edit=True)
    ext = (
        db.query(ProposedExtraction)
        .filter(
            ProposedExtraction.id == extraction_id,
            ProposedExtraction.assessment_id == assessment.id
        )
        .first()
    )
    if not ext:
        raise HTTPException(status_code=404, detail="Extraction not found")

    ext.user_action = "confirmed"
    if body and body.confirmed_value is not None:
        ext.confirmed_value = body.confirmed_value
    else:
        ext.confirmed_value = ext.answer_value
    ext.updated_at = datetime.utcnow()

    # Also update Answer table
    ans = db.query(Answer).filter(
        Answer.assessment_id == assessment.id,
        Answer.question_id == ext.question_id
    ).first()
    if ans:
        ans.value = ext.confirmed_value
        ans.user_action = "confirmed"
        ans.notes = f"Confirmed extraction from {ext.source_file or 'data room'} (p. {ext.page or 1})"
        ans.updated_at = datetime.utcnow()
    else:
        ans = Answer(
            assessment_id=assessment.id,
            question_id=ext.question_id,
            value=ext.confirmed_value,
            user_action="confirmed",
            notes=f"Confirmed extraction from {ext.source_file or 'data room'} (p. {ext.page or 1})"
        )
        db.add(ans)

    # PRD 12.1 Logging: Zero document text stored
    audit_entry = ExtractionAuditLog(
        assessment_id=assessment.id,
        question_id=ext.question_id,
        method=ext.method,
        model_name=ext.model_name or "roberta-base-squad2-cuad",
        model_version=ext.model_version or "v1.0",
        raw_score=ext.confidence,
        calibrated_score=ext.calibrated_score,
        status=ext.status,
        user_action="confirmed",
        final_value=ext.confirmed_value,
        time_to_confirm_ms=ext.time_to_confirm_ms
    )
    db.add(audit_entry)

    db.commit()
    db.refresh(ext)

    return {
        "status": "confirmed",
        "id": ext.id,
        "question_id": ext.question_id,
        "confirmed_value": ext.confirmed_value,
        "user_action": ext.user_action
    }


@app.post("/assessments/{assessment_id}/extractions/{extraction_id}/reject")
def reject_extraction(
    assessment_id: str,
    extraction_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Rejects an extraction proposal; marks it rejected so it does not auto-score."""
    assessment = verify_assessment_access(assessment_id, current_user, db, require_edit=True)
    ext = (
        db.query(ProposedExtraction)
        .filter(
            ProposedExtraction.id == extraction_id,
            ProposedExtraction.assessment_id == assessment.id
        )
        .first()
    )
    if not ext:
        raise HTTPException(status_code=404, detail="Extraction not found")

    ext.user_action = "rejected"
    ext.updated_at = datetime.utcnow()

    # If Answer table was populated automatically from this, reset value to None
    ans = db.query(Answer).filter(
        Answer.assessment_id == assessment.id,
        Answer.question_id == ext.question_id
    ).first()
    if ans and ans.user_action in ("auto", "confirmed"):
        ans.value = None
        ans.user_action = "manual"
        ans.notes = "Extraction rejected by user"
        ans.updated_at = datetime.utcnow()

    # PRD 12.1 Logging: Zero document text stored
    audit_entry = ExtractionAuditLog(
        assessment_id=assessment.id,
        question_id=ext.question_id,
        method=ext.method,
        model_name=ext.model_name or "roberta-base-squad2-cuad",
        model_version=ext.model_version or "v1.0",
        raw_score=ext.confidence,
        calibrated_score=ext.calibrated_score,
        status=ext.status,
        user_action="rejected",
        final_value=None,
        time_to_confirm_ms=ext.time_to_confirm_ms
    )
    db.add(audit_entry)

    db.commit()
    return {"status": "rejected", "id": ext.id}


@app.post("/assessments/{assessment_id}/extractions/bulk-confirm")
def bulk_confirm_extractions(
    assessment_id: str,
    req: BulkConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Bulk confirms proposed extractions.
    Strict PRD 7.5 / M6 Invariant: Bulk confirm is allowed ONLY above T_high (>= 0.85).
    """
    assessment = verify_assessment_access(assessment_id, current_user, db, require_edit=True)
    query = db.query(ProposedExtraction).filter(
        ProposedExtraction.assessment_id == assessment.id,
        ProposedExtraction.user_action == "pending",
        ProposedExtraction.confidence >= 0.85  # Gated strictly to T_high
    )

    if req.extraction_ids:
        query = query.filter(ProposedExtraction.id.in_(req.extraction_ids))

    pending_items = query.all()
    confirmed_count = 0

    for ext in pending_items:
        ext.user_action = "confirmed"
        ext.confirmed_value = ext.answer_value
        ext.updated_at = datetime.utcnow()

        ans = db.query(Answer).filter(
            Answer.assessment_id == assessment.id,
            Answer.question_id == ext.question_id
        ).first()
        if ans:
            ans.value = ext.confirmed_value
            ans.user_action = "confirmed"
            ans.notes = f"Bulk-confirmed extraction from {ext.source_file or 'data room'}"
            ans.updated_at = datetime.utcnow()
        else:
            ans = Answer(
                assessment_id=assessment.id,
                question_id=ext.question_id,
                value=ext.confirmed_value,
                user_action="confirmed",
                notes=f"Bulk-confirmed extraction from {ext.source_file or 'data room'}"
            )
            db.add(ans)

        # PRD 12.1 Logging: Zero document text stored
        audit_entry = ExtractionAuditLog(
            assessment_id=assessment.id,
            question_id=ext.question_id,
            method=ext.method,
            model_name=ext.model_name or "roberta-base-squad2-cuad",
            model_version=ext.model_version or "v1.0",
            raw_score=ext.confidence,
            calibrated_score=ext.calibrated_score,
            status=ext.status,
            user_action="accepted",
            final_value=ext.confirmed_value,
            time_to_confirm_ms=0
        )
        db.add(audit_entry)
        confirmed_count += 1

    db.commit()
    return {
        "status": "success",
        "confirmed_count": confirmed_count
    }


@app.get("/assessments/{assessment_id}/extraction-coverage")
def get_assessment_extraction_coverage(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns honest coverage report:
    How many scored questions are auto-extractable vs manual.
    Never rounded up.
    """
    assessment = verify_assessment_access(assessment_id, current_user, db)
    q_data = compute_assessment_questions(assessment, db)
    coverage = compute_extraction_coverage_report(q_data["questions"])
    return {
        "assessment_id": assessment.id,
        "coverage": coverage
    }
