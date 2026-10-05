"""
Unified Question Schema for Diligence Readiness Platform (PRD Section 6.2)
"""
from enum import Enum
from typing import List, Optional, Any, Dict, Union
from pydantic import BaseModel, Field


class ScopeEnum(str, Enum):
    CORE = "CORE"
    BRANCH = "BRANCH"


class IndustryEnum(str, Enum):
    UNIVERSAL = "UNIVERSAL"
    HEALTHCARE = "HEALTHCARE"
    FINTECH = "FINTECH"
    SOFTWARE = "SOFTWARE"
    MANUFACTURING = "MANUFACTURING"
    ENERGY = "ENERGY"


class InputTypeEnum(str, Enum):
    BOOLEAN = "BOOLEAN"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    TEXT = "TEXT"
    PERCENTAGE = "PERCENTAGE"
    NUMBER = "NUMBER"
    CURRENCY = "CURRENCY"
    FILE = "FILE"


class RiskWeightEnum(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceTypeEnum(str, Enum):
    CONTRACT_CLAUSE = "CONTRACT_CLAUSE"
    FINANCIAL_TABLE = "FINANCIAL_TABLE"
    CERTIFICATE_OR_REPORT = "CERTIFICATE_OR_REPORT"
    POLICY_DOC = "POLICY_DOC"
    SELF_ATTESTED = "SELF_ATTESTED"


class ReviewStatusEnum(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    UNREVIEWED_SEED = "UNREVIEWED_SEED"
    AI_PRE_REVIEWED = "AI_PRE_REVIEWED"
    DEPRECATED = "DEPRECATED"


class DimensionEnum(str, Enum):
    GOVERNANCE = "GOVERNANCE"
    FIN_CONTROLS = "FIN_CONTROLS"
    LEGAL_IP_REG = "LEGAL_IP_REG"
    OPS_TECH_CYBER = "OPS_TECH_CYBER"
    HUMAN_CAPITAL = "HUMAN_CAPITAL"
    TXN_READINESS = "TXN_READINESS"
    FIN_PERFORMANCE = "FIN_PERFORMANCE"
    PROFIT_CASHFLOW = "PROFIT_CASHFLOW"
    REVENUE_QUALITY = "REVENUE_QUALITY"
    MGMT_DEPTH = "MGMT_DEPTH"
    CUSTOMER_MARKET = "CUSTOMER_MARKET"
    INDUSTRY_REG = "INDUSTRY_REG"


# Canonical mapping from legacy/raw strings to standard DimensionEnum
DIMENSION_MAPPINGS: Dict[str, DimensionEnum] = {
    "Governance": DimensionEnum.GOVERNANCE,
    "GOVERNANCE": DimensionEnum.GOVERNANCE,
    "Financial_Controls": DimensionEnum.FIN_CONTROLS,
    "FIN_CONTROLS": DimensionEnum.FIN_CONTROLS,
    "Financial Controls & Reporting": DimensionEnum.FIN_CONTROLS,
    "Legal_IP_Regulatory": DimensionEnum.LEGAL_IP_REG,
    "LEGAL_IP_REG": DimensionEnum.LEGAL_IP_REG,
    "Legal, IP & Regulatory": DimensionEnum.LEGAL_IP_REG,
    "Operations_Tech": DimensionEnum.OPS_TECH_CYBER,
    "OPS_TECH_CYBER": DimensionEnum.OPS_TECH_CYBER,
    "Operations, Technology & Cyber": DimensionEnum.OPS_TECH_CYBER,
    "Human_Capital": DimensionEnum.HUMAN_CAPITAL,
    "HUMAN_CAPITAL": DimensionEnum.HUMAN_CAPITAL,
    "Human Capital / HR": DimensionEnum.HUMAN_CAPITAL,
    "Transaction_Readiness": DimensionEnum.TXN_READINESS,
    "TXN_READINESS": DimensionEnum.TXN_READINESS,
    "Transaction & Investor Readiness": DimensionEnum.TXN_READINESS,
    "Financial_Performance": DimensionEnum.FIN_PERFORMANCE,
    "FIN_PERFORMANCE": DimensionEnum.FIN_PERFORMANCE,
    "Financial Performance & Growth": DimensionEnum.FIN_PERFORMANCE,
    "Commercial_Financial": DimensionEnum.FIN_PERFORMANCE,
    "Profitability_Cashflow": DimensionEnum.PROFIT_CASHFLOW,
    "PROFIT_CASHFLOW": DimensionEnum.PROFIT_CASHFLOW,
    "Profitability & Cash Flow": DimensionEnum.PROFIT_CASHFLOW,
    "Revenue_Quality": DimensionEnum.REVENUE_QUALITY,
    "REVENUE_QUALITY": DimensionEnum.REVENUE_QUALITY,
    "Revenue Quality & Concentration": DimensionEnum.REVENUE_QUALITY,
    "Mgmt_Depth": DimensionEnum.MGMT_DEPTH,
    "MGMT_DEPTH": DimensionEnum.MGMT_DEPTH,
    "Management Team Depth": DimensionEnum.MGMT_DEPTH,
    "Customer_Market": DimensionEnum.CUSTOMER_MARKET,
    "CUSTOMER_MARKET": DimensionEnum.CUSTOMER_MARKET,
    "Customer & Market Position": DimensionEnum.CUSTOMER_MARKET,
    "Healthcare_Regulatory": DimensionEnum.INDUSTRY_REG,
    "Manufacturing_Industrial": DimensionEnum.OPS_TECH_CYBER,
    "INDUSTRY_REG": DimensionEnum.INDUSTRY_REG,
}


class QuestionSchema(BaseModel):
    """Unified Question Schema matching PRD Section 6.2 exactly."""
    question_id: str = Field(..., description="Unique question identifier, e.g. CORE_IP_01, MED_DEV_03")
    scope: ScopeEnum = Field(..., description="CORE or BRANCH")
    industry: str = Field("UNIVERSAL", description="UNIVERSAL, HEALTHCARE, FINTECH, SOFTWARE, MANUFACTURING, ENERGY")
    sub_sector: str = Field("ALL", description="Specific sub-sector or ALL")
    geography: List[str] = Field(default_factory=lambda: ["USA"], description="Geographies where applicable")
    stage: List[str] = Field(default_factory=lambda: ["ALL"], description="Stages where applicable")
    dimension: str = Field(..., description="Canonical dimension code from PRD 6.3")
    sub_category: str = Field("", description="Subcategory / grouping tag")
    question_text: str = Field(..., description="Plain English question text")
    input_type: InputTypeEnum = Field(InputTypeEnum.BOOLEAN, description="Input data type")
    options: Optional[List[str]] = Field(default=None, description="Options for MULTIPLE_CHOICE questions")
    depends_on: Optional[Dict[str, Any]] = Field(default=None, description="Structured conditional logic (PRD 6.4)")
    risk_weight: RiskWeightEnum = Field(RiskWeightEnum.MEDIUM, description="CRITICAL, HIGH, MEDIUM, LOW")
    pass_rule: Optional[Dict[str, Any]] = Field(default=None, description="Machine-readable pass/fail rule (PRD 6.5)")
    evidence_type: EvidenceTypeEnum = Field(EvidenceTypeEnum.SELF_ATTESTED, description="Extraction evidence routing")
    extraction_hint: Optional[Dict[str, Any]] = Field(default=None, description="Doc types, keywords, cuad_category")
    remediation_action: str = Field("", description="Remediation playbook action text")
    remediation_horizon_days: int = Field(90, description="Remediation bucket: 30, 60, 90, or 180 days")
    source_doc: str = Field("", description="Primary source citation, e.g. NVCA_SPA_2025")
    source_ref: str = Field("", description="Specific section/rule, e.g. Section 2.8(h) or 21 CFR 820")
    last_verified_on: Optional[str] = Field(default=None, description="ISO date when citation was verified by a human")
    review_status: ReviewStatusEnum = Field(ReviewStatusEnum.DRAFT, description="DRAFT, APPROVED, DEPRECATED")
