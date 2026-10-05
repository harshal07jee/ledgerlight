"""
Deterministic Document Extraction and Detection Engine (PRD Section 7.4 & FR-3, FR-4).

Implements:
1. Deterministic extractors for FINANCIAL_TABLE questions:
   - runway, burn, customer concentration, NRR, budget variance, EBITDA add-backs, gross margin.
   - Shows formula and inputs to user.
   - Confidence 1.0 only if all required cells found; otherwise NEEDS_CONFIRMATION.
2. Deterministic detectors for CERTIFICATE_OR_REPORT and POLICY_DOC:
   - Keyword and section detection.
   - Label is strictly "document found", never "compliant".
3. Per-question output:
   answer_value, confidence, source_file, page, char_start, char_end, snippet (<= 500 chars), method, status.
4. Privacy & logging:
   Logs contain no document text or answer values, IDs only.
"""
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from apps.api.core.ingest import ParsedDocument, ParsedPage

# Dedicated logger for extraction engine
logger = logging.getLogger("ledgerlight.extractors")

CONFIDENCE_T_HIGH = 0.85
CONFIDENCE_T_LOW = 0.50


def sanitize_snippet(text: str, max_chars: int = 500) -> str:
    """Sanitizes snippet to max 500 chars per PRD 11.2."""
    if not text:
        return ""
    clean = " ".join(text.split())
    if len(clean) > max_chars:
        return clean[:max_chars - 3] + "..."
    return clean


def extract_financial_number(text: str) -> Optional[float]:
    """Helper to extract positive or negative float from currency/percentage string."""
    if not text:
        return None
    cleaned = str(text).replace("$", "").replace(",", "").replace("%", "").strip()
    # Check for accounting parentheses e.g. (150,000) -> -150000
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1].strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


# =========================================================================
# 1. Deterministic Financial Table Extractors
# =========================================================================

def extract_cash_runway(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts cash balance and net monthly burn to compute runway:
    Formula: runway_months = cash_balance / net_monthly_burn
    Confidence: 1.0 only if both cash_balance and net_monthly_burn found.
    """
    cash_balance: Optional[float] = None
    cash_source: Optional[Tuple[str, int, str]] = None
    monthly_burn: Optional[float] = None
    burn_source: Optional[Tuple[str, int, str]] = None

    for doc in docs:
        for p in doc.pages:
            # Check tables in XLSX / CSV
            for tbl in p.tables:
                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)
                    
                    # Cash balance check
                    if any(k in row_str for k in ["cash and cash equivalents", "ending cash balance", "total cash", "cash balance", "certified cash balance"]):
                        for cell in row:
                            val = extract_financial_number(str(cell))
                            if val is not None and val > 1000:
                                cash_balance = val
                                cash_source = (doc.filename, p.page_number, f"Cash line item: {' | '.join(str(c) for c in row[:4])}")
                                break

                    # Monthly burn check
                    if any(k in row_str for k in ["net burn", "monthly burn", "average monthly burn", "burn rate", "net monthly burn"]):
                        for cell in row:
                            val = extract_financial_number(str(cell))
                            if val is not None and val > 100:
                                monthly_burn = abs(val)
                                burn_source = (doc.filename, p.page_number, f"Burn line item: {' | '.join(str(c) for c in row[:4])}")
                                break

            # Check text lines in PDF / TXT
            for line in p.text.splitlines():
                l_lower = line.lower()
                if cash_balance is None and any(k in l_lower for k in ["cash and cash equivalents", "ending cash balance", "certified cash balance", "cash balance"]):
                    nums = re.findall(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]{5,}(?:\.[0-9]+)?)", line)
                    if nums:
                        cash_balance = extract_financial_number(nums[-1])
                        cash_source = (doc.filename, p.page_number, line.strip())

                if monthly_burn is None and any(k in l_lower for k in ["net monthly burn", "monthly burn", "burn rate", "net burn"]):
                    nums = re.findall(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]{4,}(?:\.[0-9]+)?)", line)
                    if nums:
                        monthly_burn = extract_financial_number(nums[-1])
                        burn_source = (doc.filename, p.page_number, line.strip())

    if cash_balance is not None and monthly_burn is not None and monthly_burn > 0:
        runway = round(cash_balance / monthly_burn, 1)
        src_file = cash_source[0] if cash_source else docs[0].filename
        src_page = cash_source[1] if cash_source else 1
        snippet = sanitize_snippet(f"Cash Balance: ${cash_balance:,.2f} ({cash_source[2] if cash_source else ''}) | Net Monthly Burn: ${monthly_burn:,.2f} ({burn_source[2] if burn_source else ''})")
        return {
            "answer_value": runway,
            "confidence": 1.0,  # All required input cells found
            "status": "AUTO_FILLED",
            "method": "FINANCIAL_TABLE",
            "formula": "runway_months = cash_balance / net_monthly_burn",
            "formula_inputs": {
                "cash_balance": cash_balance,
                "net_monthly_burn": monthly_burn
            },
            "source_file": src_file,
            "page": src_page,
            "snippet": snippet
        }
    elif cash_balance is not None:
        # Partial extraction
        src_file = cash_source[0] if cash_source else docs[0].filename
        src_page = cash_source[1] if cash_source else 1
        snippet = sanitize_snippet(f"Cash Balance identified: ${cash_balance:,.2f}, but net monthly burn not located in data room.")
        return {
            "answer_value": None,
            "confidence": 0.50,
            "status": "NEEDS_CONFIRMATION",
            "method": "FINANCIAL_TABLE",
            "formula": "runway_months = cash_balance / net_monthly_burn",
            "formula_inputs": {"cash_balance": cash_balance, "net_monthly_burn": None},
            "source_file": src_file,
            "page": src_page,
            "snippet": snippet
        }
    
    return None


def extract_gross_margin(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts revenue and COGS / gross margin percentage from financial statements:
    Formula: gross_margin_pct = ((revenue - cogs) / revenue) * 100
    """
    revenue: Optional[float] = None
    cogs: Optional[float] = None
    direct_margin: Optional[float] = None
    best_source: Optional[Tuple[str, int, str]] = None

    for doc in docs:
        for p in doc.pages:
            for tbl in p.tables:
                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)
                    if any(k in row_str for k in ["total revenue", "net revenue", "gross revenue"]) and revenue is None:
                        for cell in row:
                            val = extract_financial_number(str(cell))
                            if val is not None and val > 1000:
                                revenue = val
                                best_source = (doc.filename, p.page_number, f"Revenue: {' | '.join(str(c) for c in row[:4])}")
                                break

                    if any(k in row_str for k in ["cost of goods sold", "cost of revenue", "total cogs", "cogs"]) and cogs is None:
                        for cell in row:
                            val = extract_financial_number(str(cell))
                            if val is not None and val > 100:
                                cogs = abs(val)
                                break

                    if any(k in row_str for k in ["gross margin %", "gross margin percentage", "gross margin"]) and direct_margin is None:
                        for cell in row:
                            val = extract_financial_number(str(cell))
                            if val is not None and 0 <= val <= 100:
                                direct_margin = val
                                best_source = (doc.filename, p.page_number, f"Direct Margin: {' | '.join(str(c) for c in row[:4])}")
                                break

            # Text lines check
            for line in p.text.splitlines():
                l_lower = line.lower()
                if "gross margin" in l_lower and ("%" in line or "percent" in l_lower) and direct_margin is None:
                    nums = re.findall(r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%", line)
                    if nums:
                        direct_margin = float(nums[0])
                        best_source = (doc.filename, p.page_number, line.strip())

    if revenue is not None and cogs is not None and revenue > 0:
        gm = round(((revenue - cogs) / revenue) * 100.0, 1)
        src_file = best_source[0] if best_source else docs[0].filename
        src_page = best_source[1] if best_source else 1
        snippet = sanitize_snippet(f"Revenue: ${revenue:,.2f} | COGS: ${cogs:,.2f} | Calculated Gross Margin: {gm}%")
        return {
            "answer_value": gm,
            "confidence": 1.0,
            "status": "AUTO_FILLED",
            "method": "FINANCIAL_TABLE",
            "formula": "gross_margin_pct = ((revenue - cogs) / revenue) * 100",
            "formula_inputs": {"revenue": revenue, "cogs": cogs, "gross_profit": round(revenue - cogs, 2)},
            "source_file": src_file,
            "page": src_page,
            "snippet": snippet
        }
    elif direct_margin is not None:
        src_file = best_source[0] if best_source else docs[0].filename
        src_page = best_source[1] if best_source else 1
        snippet = sanitize_snippet(f"Reported Gross Margin: {direct_margin}% ({best_source[2] if best_source else ''})")
        return {
            "answer_value": direct_margin,
            "confidence": 1.0,
            "status": "AUTO_FILLED",
            "method": "FINANCIAL_TABLE",
            "formula": "gross_margin_pct = direct_reported_margin",
            "formula_inputs": {"gross_margin_pct": direct_margin},
            "source_file": src_file,
            "page": src_page,
            "snippet": snippet
        }
    return None


def extract_customer_concentration(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts largest customer revenue share:
    Formula: top1_pct = (top_customer_revenue / total_revenue) * 100
    """
    top_customer_rev: Optional[float] = None
    total_rev: Optional[float] = None
    direct_top1_pct: Optional[float] = None
    best_source: Optional[Tuple[str, int, str]] = None

    for doc in docs:
        for p in doc.pages:
            for tbl in p.tables:
                customer_amounts: List[float] = []
                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)
                    if any(k in row_str for k in ["total revenue", "total arr", "total"]):
                        for c in row:
                            val = extract_financial_number(str(c))
                            if val is not None and val > 1000:
                                total_rev = val
                                break
                    elif any(c for c in row if any(k in str(c).lower() for k in ["customer", "client", "account", "corp", "inc"])):
                        for c in row:
                            val = extract_financial_number(str(c))
                            if val is not None and val > 0:
                                customer_amounts.append(val)

                if customer_amounts and total_rev:
                    customer_amounts.sort(reverse=True)
                    top_customer_rev = customer_amounts[0]
                    best_source = (doc.filename, p.page_number, f"Customer Revenue Schedule: Top customer amount ${top_customer_rev:,.2f}")

            # Text check
            for line in p.text.splitlines():
                l_lower = line.lower()
                if ("largest customer" in l_lower or "top customer" in l_lower) and ("%" in line or "percent" in l_lower):
                    nums = re.findall(r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%", line)
                    if nums:
                        direct_top1_pct = float(nums[0])
                        best_source = (doc.filename, p.page_number, line.strip())

    if top_customer_rev is not None and total_rev is not None and total_rev > 0:
        top1_pct = round((top_customer_rev / total_rev) * 100.0, 1)
        src_file = best_source[0] if best_source else docs[0].filename
        src_page = best_source[1] if best_source else 1
        snippet = sanitize_snippet(f"Top Customer Revenue: ${top_customer_rev:,.2f} | Total Revenue: ${total_rev:,.2f} | Concentration: {top1_pct}%")
        return {
            "answer_value": top1_pct,
            "confidence": 1.0,
            "status": "AUTO_FILLED",
            "method": "FINANCIAL_TABLE",
            "formula": "top1_pct = (top_customer_revenue / total_revenue) * 100",
            "formula_inputs": {"top_customer_revenue": top_customer_rev, "total_revenue": total_rev},
            "source_file": src_file,
            "page": src_page,
            "snippet": snippet
        }
    elif direct_top1_pct is not None:
        src_file = best_source[0] if best_source else docs[0].filename
        src_page = best_source[1] if best_source else 1
        snippet = sanitize_snippet(f"Reported Top Customer Share: {direct_top1_pct}% ({best_source[2] if best_source else ''})")
        return {
            "answer_value": direct_top1_pct,
            "confidence": 1.0,
            "status": "AUTO_FILLED",
            "method": "FINANCIAL_TABLE",
            "formula": "top1_pct = direct_reported_percentage",
            "formula_inputs": {"top1_pct": direct_top1_pct},
            "source_file": src_file,
            "page": src_page,
            "snippet": snippet
        }

    return None


def extract_net_revenue_retention(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts Net Revenue Retention (NRR):
    Formula: nrr_pct = (ending_arr / beginning_arr) * 100
    """
    beg_arr: Optional[float] = None
    end_arr: Optional[float] = None
    direct_nrr: Optional[float] = None
    best_source: Optional[Tuple[str, int, str]] = None

    for doc in docs:
        for p in doc.pages:
            for tbl in p.tables:
                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)
                    if "beginning arr" in row_str or "starting arr" in row_str:
                        for c in row:
                            val = extract_financial_number(str(c))
                            if val and val > 1000:
                                beg_arr = val
                                best_source = (doc.filename, p.page_number, f"Beginning ARR: ${val:,.2f}")
                                break
                    if "ending arr" in row_str:
                        for c in row:
                            val = extract_financial_number(str(c))
                            if val and val > 1000:
                                end_arr = val
                                best_source = (doc.filename, p.page_number, f"Ending ARR: ${val:,.2f}")
                                break
                    if any(k in row_str for k in ["net revenue retention", "net dollar retention", "nrr", "ndr"]):
                        for c in row:
                            val = extract_financial_number(str(c))
                            if val and 50 <= val <= 250:
                                direct_nrr = val
                                best_source = (doc.filename, p.page_number, f"Reported NRR: {val}%")
                                break

            # Text lines check
            for line in p.text.splitlines():
                l_lower = line.lower()
                if any(k in l_lower for k in ["net revenue retention", "net retention", "nrr", "ndr"]) and ("%" in line or "percent" in l_lower):
                    nums = re.findall(r"([0-9]{2,3}(?:\.[0-9]+)?)\s*%", line)
                    if nums:
                        direct_nrr = float(nums[0])
                        best_source = (doc.filename, p.page_number, line.strip())

    if beg_arr and end_arr and beg_arr > 0:
        nrr = round((end_arr / beg_arr) * 100.0, 1)
        src_file = best_source[0] if best_source else docs[0].filename
        src_page = best_source[1] if best_source else 1
        snippet = sanitize_snippet(f"Beginning ARR: ${beg_arr:,.2f} | Ending ARR: ${end_arr:,.2f} | Calculated NRR: {nrr}%")
        return {
            "answer_value": nrr,
            "confidence": 1.0,
            "status": "AUTO_FILLED",
            "method": "FINANCIAL_TABLE",
            "formula": "nrr_pct = (ending_arr / beginning_arr) * 100",
            "formula_inputs": {"beginning_arr": beg_arr, "ending_arr": end_arr},
            "source_file": src_file,
            "page": src_page,
            "snippet": snippet
        }
    elif direct_nrr is not None:
        src_file = best_source[0] if best_source else docs[0].filename
        src_page = best_source[1] if best_source else 1
        snippet = sanitize_snippet(f"Reported NRR: {direct_nrr}% ({best_source[2] if best_source else ''})")
        return {
            "answer_value": direct_nrr,
            "confidence": 1.0,
            "status": "AUTO_FILLED",
            "method": "FINANCIAL_TABLE",
            "formula": "nrr_pct = direct_reported_nrr",
            "formula_inputs": {"nrr_pct": direct_nrr},
            "source_file": src_file,
            "page": src_page,
            "snippet": snippet
        }

    return None


def extract_budget_variance(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts budget vs actual revenue variance shortfall:
    Formula: shortfall_pct = max(0, ((budget_revenue - actual_revenue) / budget_revenue) * 100)
    """
    budget_rev: Optional[float] = None
    actual_rev: Optional[float] = None
    best_source: Optional[Tuple[str, int, str]] = None

    for doc in docs:
        for p in doc.pages:
            for tbl in p.tables:
                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)
                    if any(k in row_str for k in ["budget revenue", "budgeted revenue", "plan revenue", "board budget"]) and budget_rev is None:
                        for c in row:
                            val = extract_financial_number(str(c))
                            if val and val > 1000:
                                budget_rev = val
                                best_source = (doc.filename, p.page_number, f"Budget Revenue: ${val:,.2f}")
                                break
                    if any(k in row_str for k in ["actual revenue", "actuals revenue", "actual total revenue"]) and actual_rev is None:
                        for c in row:
                            val = extract_financial_number(str(c))
                            if val and val > 1000:
                                actual_rev = val
                                best_source = (doc.filename, p.page_number, f"Actual Revenue: ${val:,.2f}")
                                break

    if budget_rev and actual_rev and budget_rev > 0:
        shortfall = round(max(0.0, ((budget_rev - actual_rev) / budget_rev) * 100.0), 1)
        src_file = best_source[0] if best_source else docs[0].filename
        src_page = best_source[1] if best_source else 1
        snippet = sanitize_snippet(f"Budget Revenue: ${budget_rev:,.2f} | Actual Revenue: ${actual_rev:,.2f} | Revenue Shortfall: {shortfall}%")
        return {
            "answer_value": shortfall,
            "confidence": 1.0,
            "status": "AUTO_FILLED",
            "method": "FINANCIAL_TABLE",
            "formula": "shortfall_pct = max(0, ((budget_revenue - actual_revenue) / budget_revenue) * 100)",
            "formula_inputs": {"budget_revenue": budget_rev, "actual_revenue": actual_rev},
            "source_file": src_file,
            "page": src_page,
            "snippet": snippet
        }

    return None


def extract_ebitda_addbacks(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts EBITDA add-backs percentage:
    Formula: ebitda_addbacks_pct = (management_addbacks / ebitda) * 100
    """
    addbacks: Optional[float] = None
    ebitda: Optional[float] = None
    best_source: Optional[Tuple[str, int, str]] = None

    for doc in docs:
        for p in doc.pages:
            for tbl in p.tables:
                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)
                    if any(k in row_str for k in ["total add-backs", "management add-backs", "ebitda adjustments", "addbacks"]) and addbacks is None:
                        for c in row:
                            val = extract_financial_number(str(c))
                            if val and val > 0:
                                addbacks = val
                                best_source = (doc.filename, p.page_number, f"Management Add-backs: ${val:,.2f}")
                                break
                    if any(k in row_str for k in ["reported ebitda", "unadjusted ebitda", "ebitda"]) and ebitda is None:
                        for c in row:
                            val = extract_financial_number(str(c))
                            if val and abs(val) > 1000:
                                ebitda = abs(val)
                                best_source = (doc.filename, p.page_number, f"EBITDA: ${val:,.2f}")
                                break

    if addbacks is not None and ebitda is not None and ebitda > 0:
        addback_pct = round((addbacks / ebitda) * 100.0, 1)
        src_file = best_source[0] if best_source else docs[0].filename
        src_page = best_source[1] if best_source else 1
        snippet = sanitize_snippet(f"Management Add-backs: ${addbacks:,.2f} | EBITDA: ${ebitda:,.2f} | Add-backs Percentage: {addback_pct}%")
        return {
            "answer_value": addback_pct,
            "confidence": 1.0,
            "status": "AUTO_FILLED",
            "method": "FINANCIAL_TABLE",
            "formula": "ebitda_addbacks_pct = (management_addbacks / ebitda) * 100",
            "formula_inputs": {"management_addbacks": addbacks, "ebitda": ebitda},
            "source_file": src_file,
            "page": src_page,
            "snippet": snippet
        }

    return None


# =========================================================================
# 2. Deterministic Certificate / Audit Report Detectors
# =========================================================================

def detect_certificate_or_report(
    question_id: str,
    question_text: str,
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Detects official audit reports or registrations.
    STRICT REQUIREMENT: Result is labeled "document found", NEVER "compliant".
    """
    qt = question_text.lower()
    
    # Determine target criteria
    target_terms: List[str] = []
    if "soc 2" in qt or "soc2" in qt:
        target_terms = ["soc 2", "type ii", "type 2", "service organization control", "trust services criteria"]
    elif "iso 9001" in qt:
        target_terms = ["iso 9001", "quality management systems", "iso 9001:2015"]
    elif "iso 27001" in qt:
        target_terms = ["iso 27001", "information security management system", "iso/iec 27001"]
    elif "fda" in qt and ("registration" in qt or "807" in qt or "510(k)" in qt):
        target_terms = ["fda establishment registration", "21 cfr part 807", "device listing", "fei number", "510(k)"]
    elif "pci-dss" in qt or "pci dss" in qt:
        target_terms = ["pci-dss", "report on compliance", "roc", "qualified security assessor", "qsa"]
    else:
        # Generic extract from question text keywords
        words = [w for w in re.findall(r"\b[A-Za-z0-9\-]{3,}\b", qt) if w not in ["the", "does", "company", "have", "are", "and", "for", "with", "audit", "report"]]
        target_terms = words[:3]

    if not target_terms:
        return None

    for doc in docs:
        for p in doc.pages:
            p_text = p.text
            p_lower = p_text.lower()
            
            matched_terms = [t for t in target_terms if t in p_lower]
            if len(matched_terms) >= 1:
                # Find match index for snippet
                first_term = matched_terms[0]
                idx = p_lower.find(first_term)
                start = max(0, idx - 100)
                end = min(len(p_text), idx + 250)
                raw_snip = p_text[start:end]
                
                # Confidence determination
                confidence = 0.90 if len(matched_terms) >= 2 or doc.file_type == "certificate_or_report" else 0.65
                status = "AUTO_FILLED" if confidence >= CONFIDENCE_T_HIGH else "NEEDS_CONFIRMATION"

                snippet = sanitize_snippet(
                    f"Document found: '{doc.filename}' (Page {p.page_number}). Matched: {', '.join(matched_terms)}. Excerpt: ...{raw_snip}..."
                )

                return {
                    "answer_value": True,
                    "confidence": confidence,
                    "status": status,
                    "method": "CERTIFICATE_OR_REPORT",
                    "source_file": doc.filename,
                    "page": p.page_number,
                    "char_start": start,
                    "char_end": end,
                    "snippet": snippet,
                    "formula": None,
                    "formula_inputs": None
                }

    return None


# =========================================================================
# 3. Deterministic Policy Document Detectors
# =========================================================================

def detect_policy_document(
    question_id: str,
    question_text: str,
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Detects presence of formal operational / governance policy documents.
    STRICT REQUIREMENT: Result is labeled "document found", NEVER "compliant".
    """
    qt = question_text.lower()
    
    # Identify policy domain
    domain_terms: List[str] = []
    if any(k in qt for k in ["bcp", "disaster recovery", "business continuity"]):
        domain_terms = ["business continuity", "disaster recovery", "bcp", "dr plan", "rto", "rpo", "failover"]
    elif any(k in qt for k in ["incident response", "security incident"]):
        domain_terms = ["incident response plan", "incident response", "security incident", "breach notification"]
    elif any(k in qt for k in ["privacy", "data privacy", "gdpr", "ccpa"]):
        domain_terms = ["data privacy policy", "privacy policy", "data subject rights", "gdpr", "ccpa"]
    elif any(k in qt for k in ["information security", "security policy"]):
        domain_terms = ["information security policy", "access control policy", "acceptable use policy", "infosec"]
    elif any(k in qt for k in ["whistleblower", "ethics"]):
        domain_terms = ["whistleblower policy", "code of ethics", "ethics hotline"]
    elif any(k in qt for k in ["revenue recognition"]):
        domain_terms = ["revenue recognition policy", "asc 606", "performance obligations"]
    elif any(k in qt for k in ["retention plan", "vesting"]):
        domain_terms = ["retention agreement", "vesting schedule", "retention plan"]
    else:
        words = [w for w in re.findall(r"\b[A-Za-z0-9\-]{4,}\b", qt) if w not in ["company", "does", "maintain", "written", "policy", "policies", "have"]]
        domain_terms = words[:3]

    if not domain_terms:
        return None

    for doc in docs:
        for p in doc.pages:
            p_text = p.text
            p_lower = p_text.lower()
            
            matches = [t for t in domain_terms if t in p_lower]
            if matches:
                first_term = matches[0]
                idx = p_lower.find(first_term)
                start = max(0, idx - 100)
                end = min(len(p_text), idx + 250)
                raw_snip = p_text[start:end]

                confidence = 0.90 if len(matches) >= 2 or doc.file_type == "policy" else 0.60
                status = "AUTO_FILLED" if confidence >= CONFIDENCE_T_HIGH else "NEEDS_CONFIRMATION"

                snippet = sanitize_snippet(
                    f"Document found: '{doc.filename}' (Page {p.page_number}). Matched: {', '.join(matches)}. Excerpt: ...{raw_snip}..."
                )

                return {
                    "answer_value": True,
                    "confidence": confidence,
                    "status": status,
                    "method": "POLICY_DOC",
                    "source_file": doc.filename,
                    "page": p.page_number,
                    "char_start": start,
                    "char_end": end,
                    "snippet": snippet,
                    "formula": None,
                    "formula_inputs": None
                }

    return None


# =========================================================================
# 4. Master Extraction Router (PRD 7.4)
# =========================================================================

def extract_answer_for_question(
    question: Dict[str, Any],
    docs: List[ParsedDocument],
    assessment_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Routes question by evidence_type and extracts answer proposal.
    Guarantees privacy: logs contain NO document text or answer values.
    """
    qid = question.get("question_id", "")
    qtext = question.get("question_text", "")
    ev_type = str(question.get("evidence_type", "SELF_ATTESTED")).upper()
    doc_count = len(docs)

    result: Optional[Dict[str, Any]] = None

    if doc_count > 0:
        if ev_type == "FINANCIAL_TABLE":
            q_lower = qtext.lower()
            if "runway" in q_lower:
                result = extract_cash_runway(docs)
            elif "gross margin" in q_lower:
                result = extract_gross_margin(docs)
            elif "largest customer" in q_lower or "concentration" in q_lower:
                result = extract_customer_concentration(docs)
            elif "net revenue retention" in q_lower or "nrr" in q_lower:
                result = extract_net_revenue_retention(docs)
            elif "budget" in q_lower and ("fall short" in q_lower or "variance" in q_lower):
                result = extract_budget_variance(docs)
            elif "ebitda" in q_lower and "add-backs" in q_lower:
                result = extract_ebitda_addbacks(docs)

        elif ev_type == "CERTIFICATE_OR_REPORT":
            result = detect_certificate_or_report(qid, qtext, docs)

        elif ev_type == "POLICY_DOC":
            result = detect_policy_document(qid, qtext, docs)

        elif ev_type == "CONTRACT_CLAUSE":
            # Per prompt: Do not integrate CUAD model yet
            result = None

    if result is None:
        # Fallback to MANUAL_REQUIRED
        method = ev_type if ev_type in ("FINANCIAL_TABLE", "CERTIFICATE_OR_REPORT", "POLICY_DOC") else "MANUAL"
        result = {
            "answer_value": None,
            "confidence": 0.0,
            "status": "MANUAL_REQUIRED",
            "method": method,
            "source_file": None,
            "page": None,
            "char_start": None,
            "char_end": None,
            "snippet": "We couldn't find this in your documents. Manual user input required.",
            "formula": None,
            "formula_inputs": None
        }

    # Strict privacy logging: IDs and status only, never document text or values
    logger.info(
        "Extraction executed: assessment_id=%s, question_id=%s, method=%s, status=%s, confidence=%.2f",
        assessment_id or "NONE",
        qid,
        result["method"],
        result["status"],
        result["confidence"]
    )

    result["question_id"] = qid
    return result


def compute_extraction_coverage_report(
    applicable_questions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Generates honest coverage report:
    Counts how many scored questions are auto-extractable vs manual.
    Never rounds up!
    """
    # Only scored applicable questions (exclude disclosed and routing)
    scored_questions = [
        q for q in applicable_questions
        if q.get("review_status") != "DRAFT"
        and q.get("pass_rule", {}).get("type") not in ("disclosed", "routing")
    ]
    total_scored = len(scored_questions)

    by_method: Dict[str, int] = {
        "FINANCIAL_TABLE": 0,
        "CERTIFICATE_OR_REPORT": 0,
        "POLICY_DOC": 0,
        "CONTRACT_CLAUSE": 0,
        "SELF_ATTESTED": 0
    }

    auto_extractable = 0
    manual_required = 0

    for q in scored_questions:
        ev = str(q.get("evidence_type", "SELF_ATTESTED")).upper()
        if ev in by_method:
            by_method[ev] += 1
        else:
            by_method["SELF_ATTESTED"] += 1

        # In M5 without CUAD, auto-extractable methods are FINANCIAL_TABLE, CERTIFICATE_OR_REPORT, POLICY_DOC
        if ev in ("FINANCIAL_TABLE", "CERTIFICATE_OR_REPORT", "POLICY_DOC"):
            auto_extractable += 1
        else:
            manual_required += 1

    auto_pct = (auto_extractable / total_scored * 100.0) if total_scored > 0 else 0.0
    manual_pct = (manual_required / total_scored * 100.0) if total_scored > 0 else 0.0

    return {
        "total_applicable_questions": len(applicable_questions),
        "total_scored_questions": total_scored,
        "auto_extractable_count": auto_extractable,
        "auto_extractable_pct": auto_pct,
        "manual_required_count": manual_required,
        "manual_required_pct": manual_pct,
        "breakdown_by_method": by_method,
        "cuad_model_status": "PENDING_INTEGRATION (CONTRACT_CLAUSE routed to manual in M5)"
    }
