"""
Normalization and Deduplication Engine for 30% Industry Branch CSVs.
Implements M1 cleanup:
- ID migration to clean INDUSTRY_TOPIC_NN pattern
- Exports data/seeds/id_migration_map.csv
- Scans named rules and deadlines, marking affected rows DRAFT
- Exports data/seeds/date_sensitive_rows.csv
- Updates child question depends_on references
- Produces normalized_branch_questions.json & .csv, seed_merge_report.csv
"""
import os
import csv
import json
import re
from typing import Dict, Any, List, Tuple
from packages.schema.models import (
    QuestionSchema,
    ScopeEnum,
    ReviewStatusEnum,
    DIMENSION_MAPPINGS,
    RiskWeightEnum,
    InputTypeEnum,
    EvidenceTypeEnum
)
from apps.api.core.dependencies import parse_legacy_depends_on
from apps.api.core.pass_rules import infer_pass_rule


# Mapping industry folders to canonical industry names
FOLDER_TO_INDUSTRY = {
    "Energy & CleanTech": "ENERGY",
    "FinTech": "FINTECH",
    "HealthCare": "HEALTHCARE",
    "Manufacturing & Industrial": "MANUFACTURING",
    "Software (SaaS)": "SOFTWARE",
}

# Clean ID Migration Map: replaces truncated and _ALT IDs with clean INDUSTRY_TOPIC_NN
ID_CLEAN_MAP: Dict[str, Tuple[str, str, str, str]] = {
    # (new_id, industry, topic, reason/description)
    # HealthCare / Medical Device Collisions & Truncations
    "MED_DEV_02_ESTABLISHMEN": ("HLTH_ESTREG_01", "HEALTHCARE", "ESTREG", "FDA Establishment Registration under 21 CFR Part 807"),
    "MED_DEV_03_QMSR_COMPLIA": ("HLTH_QMSR_01", "HEALTHCARE", "QMSR", "FDA Quality Management System Regulation (QMSR) & ISO 13485"),
    "MED_DEV_04_DESIGN_CONTR": ("HLTH_DSGNCTRL_01", "HEALTHCARE", "DSGNCTRL", "Design Controls 21 CFR 820.30"),
    "MED_DEV_05_RISK_MANAGEM": ("HLTH_RISKMGMT_01", "HEALTHCARE", "RISKMGMT", "ISO 14971 Risk Management for Medical Devices"),
    "MED_DEV_06_510K_CLEARAN": ("HLTH_510K_01", "HEALTHCARE", "510K", "FDA 510(k) Premarket Notification Equivalence"),
    "MED_DEV_07_PMA_APPROVAL": ("HLTH_PMA_01", "HEALTHCARE", "PMA", "FDA Premarket Approval (PMA) for Class III Devices"),
    "MED_DEV_08_CLINICAL_TRI": ("HLTH_CLINTRIAL_01", "HEALTHCARE", "CLINTRIAL", "21 CFR Part 812 Investigational Device Exemption (IDE)"),
    "MED_DEV_CYBER_01": ("HLTH_CYBER_01", "HEALTHCARE", "CYBER", "Premarket Cybersecurity SPDF & Threat Modeling"),
    "MED_DEV_CYBER_02": ("HLTH_CYBER_02", "HEALTHCARE", "CYBER", "Software Bill of Materials (SBOM) Machine-Readable Inventory"),
    "MED_DEV_CYBER_03": ("HLTH_CYBER_03", "HEALTHCARE", "CYBER", "FDA-Recognized Consensus Standards Testing (AAMI TIR57/UL 2900)"),
    "MED_DEV_CYBER_04": ("HLTH_CYBER_04", "HEALTHCARE", "CYBER", "Coordinated Vulnerability Disclosure (CVD) Program"),
    "MED_DEV_CYBER_05": ("HLTH_CYBER_05", "HEALTHCARE", "CYBER", "Postmarket Vulnerability Management & Patch Deployment SLAs"),

    # Manufacturing Collisions & Truncations
    "MFG_01_MANUFACTURIN": ("MFG_MODEL_01", "MANUFACTURING", "MODEL", "Primary Manufacturing Operational Model"),
    "MFG_02_SUPPLY_CHAIN": ("MFG_SUPPLY_01", "MANUFACTURING", "SUPPLY", "Bill of Materials Single-Sourced Critical Components"),
    "MFG_04_OSHA_COMPLIA": ("MFG_OSHA_01", "MANUFACTURING", "OSHA", "OSHA Citations & Total Recordable Incident Rate (TRIR)"),
    "MFG_05_ENVIRONMENTA": ("MFG_ENVPERM_01", "MANUFACTURING", "ENVPERM", "EPA Environmental Permits & RCRA Hazardous Waste"),
    "MFG_06_EPA_PFAS": ("MFG_PFAS_01", "MANUFACTURING", "PFAS", "EPA PFAS Reporting under TSCA Section 8(a)(7)"),
    "MFG_07_ITAR_EAR": ("MFG_EXPORT_01", "MANUFACTURING", "EXPORT", "ITAR & EAR Dual-Use Export Compliance"),

    # SaaS Collisions & Truncations
    "SAAS_03_OPEN_SOURCE": ("SAAS_COPYLEFT_01", "SOFTWARE", "COPYLEFT", "Viral Open Source Copyleft Licenses (GPL/AGPL)"),
    "SAAS_04_DATA_PRIVACY": ("SAAS_PRIVACY_01", "SOFTWARE", "PRIVACY", "CPRA / GDPR Consumer Deletion DSAR Workflows"),
    "SAAS_05_SLA_LIABILIT": ("SAAS_SLA_01", "SOFTWARE", "SLA", "Enterprise SLA Unlimited Liability Caps"),
    "SAAS_06_API_DEPENDEN": ("SAAS_API_01", "SOFTWARE", "API", "Critical Third-Party API Architecture & Fallback Grace"),
    "SAAS_07_AI_DATA_RIGH": ("SAAS_AIDATA_01", "SOFTWARE", "AIDATA", "Proprietary ML Model Training Rights on Customer Data"),
    "SAAS_08_DISASTER_REC": ("SAAS_BCPDR_01", "SOFTWARE", "BCPDR", "Disaster Recovery & Business Continuity Plans (RTO/RPO)"),

    # FinTech _ALT Collisions
    "FIN_TECH_01_ALT": ("FIN_SECTOR_01", "FINTECH", "SECTOR", "FinTech Sub-Sector Classification"),
    "FIN_TECH_02_ALT": ("FIN_MTL_01", "FINTECH", "MTL", "FinCEN MSB Registration & State Money Transmitter Licenses"),
    "FIN_TECH_03_ALT": ("FIN_USURY_01", "FINTECH", "USURY", "TILA, ECOA, & State Usury Rate Caps"),
    "FIN_TECH_04_ALT": ("FIN_CRYPTO_01", "FINTECH", "CRYPTO", "NY BitLicense & Digital Asset Cold-Storage Custody"),
    "FIN_TECH_05_ALT": ("FIN_AML_01", "FINTECH", "AML", "Bank Secrecy Act AML / CIP / KYC Onboarding Program"),
    "FIN_TECH_06_ALT": ("FIN_PCIDSS_01", "FINTECH", "PCIDSS", "PCI-DSS v4.0 Compliance & Report on Compliance (ROC)"),
    "FIN_TECH_07_ALT": ("FIN_CFPB_01", "FINTECH", "CFPB", "CFPB Section 1033 Personal Financial Data Rights Rule"),
    "FIN_TECH_08_ALT": ("FIN_FBO_01", "FINTECH", "FBO", "FDIC-Insured FBO Account Daily Reconciliation"),

    # Energy _ALT Collisions
    "ENERGY_02_ALT": ("ENG_FERC_01", "ENERGY", "FERC", "FERC Order 2023 Interconnection Queue Reform"),
    "ENERGY_03_ALT": ("ENG_PPA_01", "ENERGY", "PPA", "Power Purchase Agreements (PPAs) & Revenue Floor Off-take"),
    "ENERGY_04_ALT": ("ENG_PHASE1_01", "ENERGY", "PHASE1", "ASTM E1527 Phase I Environmental Site Assessment (ESA)"),
    "ENERGY_05_ALT": ("ENG_IRASRC_01", "ENERGY", "IRASRC", "IRA Critical Battery Minerals Domestic Sourcing (Sec 45X/30D)"),
    "ENERGY_06_ALT": ("ENG_WARRANTY_01", "ENERGY", "WARRANTY", "Performance Warranty Reserve for Degradation & O&M"),
    "ENERGY_07_ALT": ("ENG_NERCCIP_01", "ENERGY", "NERCCIP", "NERC CIP Operational Technology (OT) Network Segmentation"),
}


def clean_text(s: str) -> str:
    """Normalize whitespace and quotes for comparison."""
    if not s:
        return ""
    t = s.strip().replace("\r", " ").replace("\n", " ")
    t = re.sub(r"\s+", " ", t)
    return t


def text_similarity(t1: str, t2: str) -> float:
    """Compute basic token-set Jaccard similarity."""
    w1 = set(re.findall(r"\w+", t1.lower()))
    w2 = set(re.findall(r"\w+", t2.lower()))
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


def infer_evidence_type(question_text: str, sub_category: str) -> Tuple[EvidenceTypeEnum, Dict[str, Any]]:
    """Infers evidence type and extraction hint based on PRD 7.4 design constraints."""
    txt = (question_text + " " + sub_category).lower()
    hint: Dict[str, Any] = {}

    # 1. Contract clauses (CUAD extractable)
    if "governing law" in txt:
        return EvidenceTypeEnum.CONTRACT_CLAUSE, {"cuad_category": "Governing Law", "doc_types": ["customer_contract", "msa"]}
    if "copyleft" in txt or "open-source" in txt or "gpl" in txt or "agpl" in txt:
        return EvidenceTypeEnum.CONTRACT_CLAUSE, {"cuad_category": "License Grant", "doc_types": ["code_audit", "ip_agreement"]}
    if "unlimited financial liability" in txt or "liability cap" in txt or "cap on liability" in txt:
        return EvidenceTypeEnum.CONTRACT_CLAUSE, {"cuad_category": "Cap on Liability", "doc_types": ["customer_contract", "msa"]}
    if "sla" in txt or "termination for convenience" in txt or "uptime failures" in txt:
        return EvidenceTypeEnum.CONTRACT_CLAUSE, {"cuad_category": "Termination for Convenience", "doc_types": ["customer_contract", "sla"]}
    if "terms of service" in txt or "model training" in txt or "user data" in txt:
        return EvidenceTypeEnum.CONTRACT_CLAUSE, {"cuad_category": "IP Ownership Assignment", "doc_types": ["terms_of_service"]}
    if "power purchase agreement" in txt or "ppa" in txt or "off-take" in txt:
        return EvidenceTypeEnum.CONTRACT_CLAUSE, {"cuad_category": "Revenue/Profit Sharing", "doc_types": ["ppa_agreement"]}
    if "escrow" in txt or "source code escrow" in txt:
        return EvidenceTypeEnum.CONTRACT_CLAUSE, {"cuad_category": "Source Code Escrow", "doc_types": ["escrow_agreement"]}

    # 2. Certificates & Regulatory reports
    if "soc 2" in txt or "soc2" in txt:
        return EvidenceTypeEnum.CERTIFICATE_OR_REPORT, {"standard": "SOC 2 Type II", "doc_types": ["audit_report"]}
    if "510(k)" in txt:
        return EvidenceTypeEnum.CERTIFICATE_OR_REPORT, {"standard": "FDA 510(k)", "doc_types": ["fda_clearance_letter"]}
    if "pma" in txt or "premarket approval" in txt:
        return EvidenceTypeEnum.CERTIFICATE_OR_REPORT, {"standard": "FDA PMA", "doc_types": ["fda_approval_letter"]}
    if "iso 9001" in txt or "iso 13485" in txt or "iso 14971" in txt:
        return EvidenceTypeEnum.CERTIFICATE_OR_REPORT, {"standard": "ISO Certification", "doc_types": ["iso_certificate"]}
    if "bitlicense" in txt:
        return EvidenceTypeEnum.CERTIFICATE_OR_REPORT, {"standard": "NY BitLicense", "doc_types": ["license_document"]}
    if "hitrust" in txt:
        return EvidenceTypeEnum.CERTIFICATE_OR_REPORT, {"standard": "HITRUST CSF", "doc_types": ["hitrust_report"]}
    if "phase i" in txt or "environmental site assessment" in txt:
        return EvidenceTypeEnum.CERTIFICATE_OR_REPORT, {"standard": "ASTM E1527", "doc_types": ["environmental_audit"]}

    # 3. Policy documents
    if "policy" in txt or "disaster recovery" in txt or "bcp" in txt or "incident response" in txt:
        return EvidenceTypeEnum.POLICY_DOC, {"doc_types": ["dr_bcp_policy", "security_policy", "privacy_policy"]}
    if "threat modeling" in txt or "spdf" in txt or "sbom" in txt:
        return EvidenceTypeEnum.POLICY_DOC, {"doc_types": ["cybersecurity_framework", "sbom_document"]}

    # 4. Financial tables
    if "fbo" in txt or "bank reconciliation" in txt:
        return EvidenceTypeEnum.FINANCIAL_TABLE, {"table_type": "reconciliation_schedule"}
    if "percentage of raw materials" in txt or "single-sourced" in txt:
        return EvidenceTypeEnum.FINANCIAL_TABLE, {"table_type": "supplier_spend_table"}
    if "clean claims" in txt or "denial rate" in txt:
        return EvidenceTypeEnum.FINANCIAL_TABLE, {"table_type": "billing_aging_report"}

    return EvidenceTypeEnum.SELF_ATTESTED, {}


def check_date_sensitive_rules(text: str) -> Tuple[bool, List[str], str]:
    """
    Detects effective dates, deadlines, and named rules (PRD Section 6.2 & M1 cleanup).
    Returns (is_sensitive, matched_rules, claim_to_verify).
    """
    txt_lower = text.lower()
    matched = []
    claims = []

    # 1. FERC Order 2023
    if "ferc" in txt_lower:
        matched.append("FERC Order 2023")
        claims.append("Verify interconnection cluster study timelines, penalty structure for transmission providers, and commercial readiness deposit requirements under FERC Order 2023.")

    # 2. IRA (Inflation Reduction Act) - exclude 'Investors' Rights Agreement' (IRA)
    if "inflation reduction" in txt_lower or re.search(r"\bira\b", txt_lower) and "investors' rights" not in txt_lower and "investor rights" not in txt_lower:
        matched.append("IRA")
        claims.append("Verify prevailing wage and apprenticeship audit records, domestic content bonus thresholds, and critical mineral sourcing requirements under the Inflation Reduction Act.")

    # 3. SEC Item 1.05
    if "sec item 1.05" in txt_lower or ("8-k" in txt_lower and "cyber" in txt_lower):
        matched.append("SEC Item 1.05")
        claims.append("Verify 4-business-day reporting deadline for material cybersecurity incidents and documented materiality determination framework per SEC Release No. 33-11216.")

    # 4. CFPB Section 1033
    if "cfpb" in txt_lower or "1033" in txt_lower:
        matched.append("CFPB 1033")
        claims.append("Verify consumer financial data rights compliance schedule, transition away from screen-scraping to developer APIs, and phased compliance tier dates (starting 2026).")

    # 5. FDA QMSR
    if "qmsr" in txt_lower:
        matched.append("QMSR")
        claims.append("Verify Quality Management System alignment with ISO 13485:2016 and FDA QMSR final rule transition deadline (effective February 2, 2026).")

    # 6. PFAS / TSCA 8(a)(7)
    if "pfas" in txt_lower or "tsca" in txt_lower:
        matched.append("PFAS")
        claims.append("Verify chemical reporting scope, supply chain inquiry records, and EPA TSCA Section 8(a)(7) submission window.")

    # 7. PCI-DSS v4.0
    if "pci-dss v4" in txt_lower or "pci dss 4" in txt_lower or "pci-dss 4" in txt_lower:
        matched.append("PCI-DSS v4.0")
        claims.append("Verify full enforcement transition to PCI-DSS v4.0 (mandatory after March 31, 2025), customized approach documentation, and targeted risk analyses.")

    # 8. Future years / effective dates
    year_matches = re.findall(r"\b202[5-9]\b", text)
    if year_matches:
        matched.extend(list(set(year_matches)))
        claims.append(f"Verify statutory milestones and regulatory effective dates scheduled for {', '.join(sorted(set(year_matches)))}.")

    if matched:
        return True, matched, " | ".join(claims)
    return False, [], ""


def normalize_seed_files(
    seed_root: str = "data/ASP/30% questions",
    output_dir: str = "data/seeds"
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Normalizes all CSV files in data/ASP/30% questions/, resolves collisions,
    merges duplicates, applies clean INDUSTRY_TOPIC_NN IDs, tracks migrations,
    marks date-sensitive rules as DRAFT, and produces seed files.
    """
    os.makedirs(output_dir, exist_ok=True)
    raw_files = []
    for root, _, files in os.walk(seed_root):
        for f in sorted(files):
            if f.endswith(".csv"):
                raw_files.append(os.path.join(root, f))

    print(f"Reading {len(raw_files)} CSV files from {seed_root}...")

    # Load all raw records
    raw_records = []
    for fp in raw_files:
        rel = os.path.relpath(fp, seed_root).replace("\\", "/")
        folder = rel.split("/")[0]
        ind_default = FOLDER_TO_INDUSTRY.get(folder, "UNIVERSAL")

        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_records.append({
                    "file": rel,
                    "folder": folder,
                    "industry_default": ind_default,
                    "data": row
                })

    print(f"Loaded {len(raw_records)} raw records.")

    # Deduplication and collision resolution
    merged_questions: Dict[str, Dict[str, Any]] = {}
    merge_reports: List[Dict[str, Any]] = []

    # Map of ID renames for dependency tracking and migration map
    id_migration_records: List[Dict[str, str]] = []
    # Key: old_id, Value: new_id
    id_renames: Dict[str, str] = {}

    date_sensitive_list: List[Dict[str, Any]] = []

    for item in raw_records:
        r = item["data"]
        raw_id = r["question_id"].strip()
        q_text = clean_text(r["question_text"])
        rel_file = item["file"]
        folder = item["folder"]

        # Determine true industry and subsector
        sub_sector = r.get("sub_sector", "").strip() or "ALL"
        sub_category = r.get("sub_category", "").strip()
        stage_raw = r.get("stage", "ALL").strip() or "ALL"
        stage_list = [s.strip() for s in stage_raw.split(",") if s.strip()] or ["ALL"]
        geo_raw = r.get("geography", "USA").strip() or "USA"
        geo_list = [g.strip() for g in geo_raw.split(",") if g.strip()] or ["USA"]

        # Handle the multi-industry file inside HealthCare/
        if "gemini-code-1789523871318.csv" in rel_file:
            if raw_id.startswith("FIN_TECH"):
                industry = "FINTECH"
                sub_sector = "ALL"
            elif raw_id.startswith("SAAS"):
                industry = "SOFTWARE"
                sub_sector = "ALL"
            elif raw_id.startswith("MFG"):
                industry = "MANUFACTURING"
                sub_sector = "ALL"
            elif raw_id.startswith("ENERGY"):
                industry = "ENERGY"
                sub_sector = "ALL"
            else:
                industry = "HEALTHCARE"
        else:
            industry = item["industry_default"]

        # Check for existing questions with same ID or similar text
        existing_with_id = merged_questions.get(raw_id)

        target_id = raw_id
        action = "RETAINED"
        merge_notes = ""

        if existing_with_id:
            existing_text = clean_text(existing_with_id["question_text"])
            sim = text_similarity(q_text, existing_text)

            if sim >= 0.70 or q_text.lower() == existing_text.lower():
                # TRUE DUPLICATE: Merge into existing, keeping the richer record
                action = "MERGED_DUPLICATE"
                merge_notes = f"Merged with {existing_with_id['source_doc']} (similarity: {sim:.2f})"

                if len(r.get("remediation_action", "")) > len(existing_with_id.get("remediation_action", "")):
                    existing_with_id["remediation_action"] = r.get("remediation_action", "")
                if sub_sector != "ALL" and existing_with_id["sub_sector"] == "ALL":
                    existing_with_id["sub_sector"] = sub_sector
                if sub_category and not existing_with_id["sub_category"]:
                    existing_with_id["sub_category"] = sub_category
                if stage_list != ["ALL"] and existing_with_id["stage"] == ["ALL"]:
                    existing_with_id["stage"] = stage_list

                merge_reports.append({
                    "original_id": raw_id,
                    "normalized_id": raw_id,
                    "action": action,
                    "source_file": rel_file,
                    "question_text": q_text,
                    "notes": merge_notes
                })
                continue
            else:
                # ID COLLISION: Different question sharing the same ID!
                action = "RESOLVED_ID_COLLISION"

                # Check if this raw_id + subcategory/folder maps cleanly
                # Determine legacy truncated/disambiguated ID
                disambig_suffix = sub_category.upper() if sub_category else "ALT"
                disambig_suffix = re.sub(r"[^A-Z0-9_]", "_", disambig_suffix)[:12]
                legacy_id = f"{raw_id}_{disambig_suffix}"
                legacy_alt_id = f"{raw_id}_ALT"

                # Look up clean ID in migration map
                matched_legacy = None
                if legacy_id in ID_CLEAN_MAP:
                    matched_legacy = legacy_id
                elif legacy_alt_id in ID_CLEAN_MAP:
                    matched_legacy = legacy_alt_id

                if matched_legacy:
                    new_clean_id, clean_ind, clean_top, reason = ID_CLEAN_MAP[matched_legacy]
                    target_id = new_clean_id
                    id_renames[matched_legacy] = target_id
                    id_renames[raw_id] = target_id
                    id_renames[f"{rel_file}::{raw_id}"] = target_id
                    id_migration_records.append({
                        "old_id": matched_legacy,
                        "new_id": target_id,
                        "industry": clean_ind,
                        "topic": clean_top,
                        "reason": reason
                    })
                    merge_notes = f"Collided on {raw_id}. Migrated from {matched_legacy} to clean ID {target_id} ({reason})."
                else:
                    # Fallback clean naming if unmapped
                    clean_suffix = re.sub(r"[^A-Z0-9]", "", disambig_suffix)[:6] or "ALT"
                    target_id = f"{industry[:4]}_{clean_suffix}_01"
                    counter = 1
                    base = target_id
                    while target_id in merged_questions:
                        target_id = f"{base}_{counter:02d}"
                        counter += 1
                    id_renames[f"{rel_file}::{raw_id}"] = target_id
                    merge_notes = f"Collided on {raw_id}. Renamed to {target_id}."

        else:
            # Check if this non-collided question has a clean ID mapping (e.g. MED_DEV_CYBER_01)
            if raw_id in ID_CLEAN_MAP:
                new_clean_id, clean_ind, clean_top, reason = ID_CLEAN_MAP[raw_id]
                target_id = new_clean_id
                id_renames[raw_id] = target_id
                id_renames[f"{rel_file}::{raw_id}"] = target_id
                id_migration_records.append({
                    "old_id": raw_id,
                    "new_id": target_id,
                    "industry": clean_ind,
                    "topic": clean_top,
                    "reason": reason
                })
                merge_notes = f"Standardized {raw_id} to clean pattern {target_id}."

        # Map dimension to canonical code
        raw_dim = r.get("dimension", "Operations_Tech").strip()
        canonical_dim = DIMENSION_MAPPINGS.get(raw_dim, DIMENSION_MAPPINGS.get("Operations_Tech")).value

        # Normalize risk weight
        raw_rw = r.get("risk_weight", "MEDIUM").strip().upper()
        if "CRITICAL" in raw_rw:
            risk_weight = RiskWeightEnum.CRITICAL.value
        elif "HIGH" in raw_rw:
            risk_weight = RiskWeightEnum.HIGH.value
        elif "LOW" in raw_rw:
            risk_weight = RiskWeightEnum.LOW.value
        else:
            risk_weight = RiskWeightEnum.MEDIUM.value

        # Normalize input type
        raw_inp = r.get("input_type", "BOOLEAN").strip().upper()
        if "CHOICE" in raw_inp or "MULTIPLE" in raw_inp:
            input_type = InputTypeEnum.MULTIPLE_CHOICE.value
        elif "PERCENT" in raw_inp:
            input_type = InputTypeEnum.PERCENTAGE.value
        elif "CURRENCY" in raw_inp:
            input_type = InputTypeEnum.CURRENCY.value
        elif "NUMBER" in raw_inp or "INTEGER" in raw_inp:
            input_type = InputTypeEnum.NUMBER.value
        elif "TEXT" in raw_inp:
            input_type = InputTypeEnum.TEXT.value
        else:
            input_type = InputTypeEnum.BOOLEAN.value

        # Remediation horizon
        raw_h = r.get("remediation_horizon_days", 90)
        try:
            raw_h = int(raw_h)
            if raw_h in (30, 60, 90, 180):
                horizon = raw_h
            elif raw_h <= 30:
                horizon = 30
            elif raw_h <= 60:
                horizon = 60
            elif raw_h <= 90:
                horizon = 90
            else:
                horizon = 180
        except (ValueError, TypeError):
            horizon = 90

        # Infer pass rule
        pass_rule = infer_pass_rule(q_text, input_type)

        # Infer evidence type & hint
        evidence_type, hint = infer_evidence_type(q_text, sub_category)

        # Date-sensitive & named rules check (PRD Section 6.2 & M1 cleanup)
        full_text_to_scan = f"{q_text} {r.get('remediation_action', '')} {r.get('source_ref', '')}"
        is_date_sensitive, matched_rules, claim_to_verify = check_date_sensitive_rules(full_text_to_scan)

        if is_date_sensitive:
            review_status = ReviewStatusEnum.DRAFT.value
            last_verified = None
            date_sensitive_list.append({
                "question_id": target_id,
                "question_text": q_text,
                "matched_rules": ", ".join(matched_rules),
                "review_status": "DRAFT",
                "claim_to_verify": claim_to_verify
            })
        else:
            review_status = ReviewStatusEnum.UNREVIEWED_SEED.value
            last_verified = None

        # Construct unified question dictionary
        q_dict = {
            "question_id": target_id,
            "scope": ScopeEnum.BRANCH.value,
            "industry": industry,
            "sub_sector": sub_sector,
            "geography": geo_list,
            "stage": stage_list,
            "dimension": canonical_dim,
            "sub_category": sub_category or raw_dim,
            "question_text": q_text,
            "input_type": input_type,
            "options": ["Yes", "No"] if input_type == InputTypeEnum.BOOLEAN.value else None,
            "depends_on": parse_legacy_depends_on(r.get("depends_on")),
            "risk_weight": risk_weight,
            "pass_rule": pass_rule,
            "evidence_type": evidence_type.value,
            "extraction_hint": hint or None,
            "remediation_action": clean_text(r.get("remediation_action", "")),
            "remediation_horizon_days": horizon,
            "source_doc": f"30% questions/{folder}",
            "source_ref": r.get("sub_category", "") or r.get("dimension", ""),
            "last_verified_on": last_verified,
            "review_status": review_status,
        }

        merged_questions[target_id] = q_dict

        merge_reports.append({
            "original_id": raw_id,
            "normalized_id": target_id,
            "action": action,
            "source_file": rel_file,
            "question_text": q_text,
            "notes": merge_notes
        })

    # Fix any dependency references where target_id changed
    for qid, q in merged_questions.items():
        dep = q.get("depends_on")
        if dep and isinstance(dep, dict) and "all" in dep:
            for cond in dep["all"]:
                cond_qid = cond.get("question_id")
                # Look up direct rename
                if cond_qid in id_renames:
                    cond["question_id"] = id_renames[cond_qid]
                else:
                    for k, renamed in id_renames.items():
                        if k.endswith(f"::{cond_qid}"):
                            cond["question_id"] = renamed

    # Export normalized branch questions
    branch_list = list(merged_questions.values())

    json_path = os.path.join(output_dir, "normalized_branch_questions.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(branch_list, f, indent=2)
    print(f"Wrote {len(branch_list)} normalized branch questions to {json_path}")

    csv_path = os.path.join(output_dir, "normalized_branch_questions.csv")
    if branch_list:
        fieldnames = list(branch_list[0].keys())
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in branch_list:
                row_copy = dict(row)
                for k in ["geography", "stage", "options", "depends_on", "pass_rule", "extraction_hint"]:
                    if isinstance(row_copy[k], (list, dict)):
                        row_copy[k] = json.dumps(row_copy[k])
                writer.writerow(row_copy)
        print(f"Wrote {len(branch_list)} normalized branch questions to {csv_path}")

    # Export seed merge report
    report_csv = os.path.join(output_dir, "seed_merge_report.csv")
    if merge_reports:
        with open(report_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(merge_reports[0].keys()))
            writer.writeheader()
            writer.writerows(merge_reports)
        print(f"Wrote {len(merge_reports)} merge report rows to {report_csv}")

    # Export ID Migration Map
    map_csv = os.path.join(output_dir, "id_migration_map.csv")
    # Deduplicate migration records by old_id
    seen_map = set()
    dedup_map_records = []
    for m in id_migration_records:
        if m["old_id"] not in seen_map:
            seen_map.add(m["old_id"])
            dedup_map_records.append(m)

    with open(map_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["old_id", "new_id", "industry", "topic", "reason"])
        writer.writeheader()
        writer.writerows(dedup_map_records)
    print(f"Wrote {len(dedup_map_records)} migration mappings to {map_csv}")

    # Export Date-Sensitive Rows
    dates_csv = os.path.join(output_dir, "date_sensitive_rows.csv")
    with open(dates_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["question_id", "question_text", "matched_rules", "review_status", "claim_to_verify"])
        writer.writeheader()
        writer.writerows(date_sensitive_list)
    print(f"Wrote {len(date_sensitive_list)} date-sensitive rows to {dates_csv}")

    return branch_list, merge_reports


if __name__ == "__main__":
    normalize_seed_files()
