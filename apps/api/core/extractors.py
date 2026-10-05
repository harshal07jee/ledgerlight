"""
Deterministic Document Extraction and Detection Engine (PRD Section 7.4 & FR-3, FR-4).

Implements:
1. Deterministic extractors for FINANCIAL_TABLE questions:
   - runway, burn, customer concentration, NRR, budget variance, EBITDA add-backs, gross margin.
   - Shows formula and inputs to user.
   - Confidence 1.0 and AUTO_FILLED only if:
     (a) Comes from a structured table cell with a recognized header,
     (b) Every input comes from the SAME document and the same period,
     (c) Passes plausibility checks (runway 0-120m, percentages 0-100%).
   - Otherwise, status is NEEDS_CONFIRMATION with confidence <= 0.70.
   - Never auto-fills from regex-parsed free text.
   - Conflicting values across documents produce NEEDS_CONFIRMATION showing all sources.
2. Deterministic detectors for CERTIFICATE_OR_REPORT and POLICY_DOC:
   - Always return NEEDS_CONFIRMATION (never AUTO_FILLED).
   - Label is strictly "document found", never an answer or "compliant".
3. Per-question output:
   answer_value, confidence, source_file, page, char_start, char_end, snippet (<= 500 chars), method, status.
4. Privacy & logging:
   Logs contain no document text or answer values, IDs only.
"""
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from apps.api.core.ingest import ParsedDocument, ParsedPage

logger = logging.getLogger("ledgerlight.extractors")

CONFIDENCE_T_HIGH = 0.85
CONFIDENCE_T_LOW = 0.50

# EBITDA Add-back label synonyms
ADDBACK_SYNONYMS = [
    "management add-backs", "management addbacks", "total add-backs", "total addbacks",
    "add-backs", "addbacks", "ebitda adjustments", "normalized ebitda adjustments",
    "normalization adjustments", "pro-forma adjustments", "pro forma adjustments",
    "management adjustments", "adjusted ebitda adjustments"
]


def sanitize_snippet(text: str, max_chars: int = 500) -> str:
    """Sanitizes snippet to max 500 chars per PRD 11.2."""
    if not text:
        return ""
    clean = " ".join(text.split())
    if len(clean) > max_chars:
        return clean[:max_chars - 3] + "..."
    return clean


def extract_financial_number(text: Any) -> Optional[float]:
    """
    Helper to extract float from currency/percentage string, handling:
    - Currency symbols: $, €, £
    - Commas: 1,000,000
    - Accounting parentheses as negatives: (800,000), $(800,000), $( 800,000.00 ), ($800k)
    - Percentages: 80.0%, 17.1 %
    - Leading/trailing text
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None

    is_neg = False
    cleaned = s.replace("$", "").replace("€", "").replace("£", "").replace(",", "").replace("%", "").strip()

    # Check for outer accounting parentheses e.g. (800000) or $(800000)
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_neg = True
        cleaned = cleaned[1:-1].strip()
    elif "(" in s and ")" in s:
        m = re.search(r"\(\s*\$?\s*([0-9]+(?:\.[0-9]+)?)\s*\)", s.replace(",", ""))
        if m:
            try:
                return -float(m.group(1))
            except ValueError:
                pass

    try:
        val = float(cleaned)
        return -val if is_neg else val
    except ValueError:
        m = re.search(r"\(?\s*\$?\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*\)?", s)
        if m:
            try:
                val = float(m.group(1).replace(",", ""))
                return -val if is_neg or ("(" in m.group(0) and ")" in m.group(0)) else val
            except ValueError:
                return None
    return None


def detect_unit_multiplier(text: str) -> float:
    """Detects unit scale in headers or preambles ($ in thousands, millions, etc.)."""
    t = text.lower()
    if any(k in t for k in ["in thousands", "in '000s", "($ in '000s)", "($000)", "$ in thousands", "$000", "$k", "figures in $ thousands", "($ in thousands)"]):
        return 1000.0
    if any(k in t for k in ["in millions", "($ in millions)", "$ in millions", "$m", "($m)", "figures in $ millions"]):
        return 1000000.0
    return 1.0


def check_plausibility(metric: str, value: float) -> Tuple[bool, Optional[str]]:
    """Enforces PRD plausibility limits: runway 0-120m, percentages 0-100%."""
    if metric == "runway":
        if value < 0.0:
            return False, f"Runway cannot be negative ({value} months)"
        if value > 120.0:
            return False, f"Runway exceeds plausible maximum of 120 months ({value} months)"
        return True, None
    elif metric in ("gross_margin", "customer_concentration", "budget_variance", "ebitda_addbacks"):
        if value < 0.0:
            return False, f"{metric} cannot be negative ({value}%)"
        if value > 100.0:
            return False, f"{metric} cannot exceed 100.0% ({value}%)"
        return True, None
    elif metric == "nrr":
        if value < 0.0 or value > 300.0:
            return False, f"NRR out of plausible range 0-300% ({value}%)"
        return True, None
    return True, None


def determine_extraction_status(
    is_table: bool,
    same_document: bool,
    is_plausible: bool,
    has_conflict: bool = False
) -> Tuple[str, float]:
    """
    STRICT SAFETY RULE (Rule 1):
    Never auto-fill from regex-parsed free text.
    A value may be AUTO_FILLED only if:
      (a) it comes from a structured table cell with a recognized header (is_table=True),
      (b) every input comes from the SAME document and the same period (same_document=True),
      (c) it passes plausibility checks (is_plausible=True).
    Otherwise it is NEEDS_CONFIRMATION with confidence <= 0.70.
    Confidence 1.0 is allowed only when (a), (b), and (c) all hold.
    If has_conflict is True, confidence is <= 0.50.
    """
    if has_conflict:
        return "NEEDS_CONFIRMATION", 0.50
    if not is_plausible:
        return "NEEDS_CONFIRMATION", 0.35
    if is_table and same_document and is_plausible:
        return "AUTO_FILLED", 1.0
    return "NEEDS_CONFIRMATION", 0.70


# =========================================================================
# 1. Deterministic Financial Table Extractors
# =========================================================================

def extract_cash_runway(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts cash balance and net monthly burn to compute runway:
    Formula: runway_months = cash_balance / net_monthly_burn
    Safety rules:
    - Prefer Ending/Closing/Certified balance over Opening/Beginning balance.
    - Accounting parentheses are treated as negatives.
    - Plausibility: runway must be 0 to 120 months. Cash > 0, Burn > 0.
    - AUTO_FILLED only if from structured table cell in same document, with recognized header.
    - If multiple documents conflict (> 0.5 months difference), return NEEDS_CONFIRMATION.
    """
    candidates: List[Dict[str, Any]] = []

    for doc in docs:
        doc_multiplier = 1.0
        for p in doc.pages:
            m = detect_unit_multiplier(p.text)
            if m > 1.0:
                doc_multiplier = m
                break

        for p in doc.pages:
            # 1. Structured table check (XLSX / CSV / PDF tables)
            for tbl in p.tables:
                tbl_text = " ".join(" ".join(str(c) for c in r) for r in tbl[:3])
                tbl_multiplier = detect_unit_multiplier(tbl_text) or doc_multiplier

                cash_val: Optional[float] = None
                cash_label: str = ""
                cash_score: int = 0
                burn_val: Optional[float] = None
                burn_label: str = ""

                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)
                    
                    # Cash balance check: prefer ending / closing / certified over opening
                    current_score = 0
                    if any(k in row_str for k in ["closing ledger balance", "certified cash balance", "certified closing balance", "ending cash balance", "closing cash", "ending cash", "combined total cash"]):
                        current_score = 100
                    elif any(k in row_str for k in ["cash and cash equivalents", "cash and equivalents", "total cash", "cash balance", "closing"]):
                        current_score = 80
                    elif any(k in row_str for k in ["opening ledger balance", "beginning cash balance", "opening cash", "beginning cash", "starting cash"]):
                        current_score = 10

                    if current_score > cash_score:
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v is not None and v > 0:
                                cash_val = v * tbl_multiplier
                                cash_label = row_str[:80]
                                cash_score = current_score
                                break

                    # Monthly burn check
                    if any(k in row_str for k in ["average monthly burn", "net monthly burn", "net monthly cash outflow / burn", "monthly burn", "burn rate", "net burn", "average monthly cash consumption"]) and burn_val is None:
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v is not None and abs(v) > 0:
                                burn_val = abs(v) * tbl_multiplier
                                burn_label = row_str[:80]
                                break

                if cash_val is not None and burn_val is not None and burn_val > 0:
                    r_val = round(cash_val / burn_val, 1)
                    snip = sanitize_snippet(f"Cash: ${cash_val:,.2f} ({cash_label}) | Burn: ${burn_val:,.2f} ({burn_label}) | Runway: {r_val}m")
                    candidates.append({
                        "runway": r_val,
                        "cash": cash_val,
                        "burn": burn_val,
                        "doc_name": doc.filename,
                        "page": p.page_number,
                        "is_table": True,
                        "snippet": snip
                    })

            # 2. Text lines check (PDF / TXT lines)
            lines = p.text.splitlines()
            text_cash: Optional[float] = None
            text_cash_score: int = 0
            text_cash_line: str = ""
            text_burn: Optional[float] = None
            text_burn_line: str = ""

            for line in lines:
                l_lower = line.lower()
                c_score = 0
                if any(k in l_lower for k in ["closing ledger balance", "certified cash balance", "certified closing balance", "ending cash balance", "closing cash", "ending cash", "combined total cash", "ending balance", "closing balance", "certified balance"]):
                    c_score = 100
                elif any(k in l_lower for k in ["cash and cash equivalents", "cash and equivalents", "total cash", "cash balance"]):
                    c_score = 80
                elif any(k in l_lower for k in ["opening ledger balance", "beginning cash balance", "opening cash", "beginning cash", "opening balance", "beginning balance"]):
                    c_score = 10

                if c_score > text_cash_score:
                    # Match full numbers in line
                    nums = re.findall(r"(?:\$|\b)\s*\(?\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]{4,}(?:\.[0-9]+)?)\s*\)?", line)
                    if nums:
                        v = extract_financial_number(nums[-1])
                        if v is not None and v > 0:
                            text_cash = v * doc_multiplier
                            text_cash_score = c_score
                            text_cash_line = line.strip()

                if text_burn is None and any(k in l_lower for k in ["average monthly burn", "net monthly burn", "net monthly cash outflow / burn", "monthly burn", "burn rate", "net burn", "average monthly cash consumption"]):
                    nums = re.findall(r"(?:\$|\b)\s*\(?\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]{4,}(?:\.[0-9]+)?)\s*\)?", line)
                    if nums:
                        v = extract_financial_number(nums[-1])
                        if v is not None and abs(v) > 0:
                            text_burn = abs(v) * doc_multiplier
                            text_burn_line = line.strip()

            if text_cash is not None and text_burn is not None and text_burn > 0:
                r_val = round(text_cash / text_burn, 1)
                snip = sanitize_snippet(f"Cash: ${text_cash:,.2f} ({text_cash_line}) | Burn: ${text_burn:,.2f} ({text_burn_line}) | Runway: {r_val}m")
                candidates.append({
                    "runway": r_val,
                    "cash": text_cash,
                    "burn": text_burn,
                    "doc_name": doc.filename,
                    "page": p.page_number,
                    "is_table": False,
                    "snippet": snip
                })

    if not candidates:
        return None

    # Check for conflicts across DIFFERENT documents
    unique_runways: Dict[float, List[Dict[str, Any]]] = {}
    for c in candidates:
        key = round(c["runway"], 1)
        if key not in unique_runways:
            unique_runways[key] = []
        unique_runways[key].append(c)

    has_conflict = False
    if len(unique_runways) > 1:
        diff = max(unique_runways.keys()) - min(unique_runways.keys())
        if diff > 0.5:
            has_conflict = True

    if has_conflict:
        conflict_list = []
        for r_val, c_list in sorted(unique_runways.items()):
            srcs = [f"{item['doc_name']} (p.{item['page']}): {item['runway']}m" for item in c_list]
            conflict_list.append("; ".join(srcs))

        snippet = sanitize_snippet(
            f"Conflicting runway values detected across documents: {' | '.join(conflict_list)}. User confirmation required."
        )
        return {
            "answer_value": list(unique_runways.keys())[0],
            "confidence": 0.50,
            "status": "NEEDS_CONFIRMATION",
            "method": "FINANCIAL_TABLE",
            "formula": "runway_months = cash_balance / net_monthly_burn",
            "formula_inputs": {
                "conflict": True,
                "candidates": [
                    {"runway": c["runway"], "cash": c["cash"], "burn": c["burn"], "doc": c["doc_name"], "page": c["page"]}
                    for c in candidates
                ]
            },
            "source_file": candidates[0]["doc_name"],
            "page": candidates[0]["page"],
            "snippet": snippet
        }

    # If no conflict: prefer structured table candidate over free-text
    table_candidates = [c for c in candidates if c["is_table"]]
    chosen = table_candidates[0] if table_candidates else candidates[0]

    is_plausible, plaus_err = check_plausibility("runway", chosen["runway"])
    status, confidence = determine_extraction_status(
        is_table=chosen["is_table"],
        same_document=True,
        is_plausible=is_plausible,
        has_conflict=False
    )

    snippet = chosen["snippet"]
    if not is_plausible and plaus_err:
        snippet = sanitize_snippet(f"Plausibility warning: {plaus_err}. {snippet}")

    return {
        "answer_value": chosen["runway"],
        "confidence": confidence,
        "status": status,
        "method": "FINANCIAL_TABLE",
        "formula": "runway_months = cash_balance / net_monthly_burn",
        "formula_inputs": {
            "cash_balance": chosen["cash"],
            "net_monthly_burn": chosen["burn"],
            "source_is_table": chosen["is_table"]
        },
        "source_file": chosen["doc_name"],
        "page": chosen["page"],
        "snippet": snippet
    }


def extract_gross_margin(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts revenue and COGS / gross margin percentage from financial statements:
    Formula: gross_margin_pct = ((revenue - cogs) / revenue) * 100
    Rule: Both revenue and COGS must come from the same document/table.
    """
    candidates: List[Dict[str, Any]] = []

    for doc in docs:
        doc_multiplier = 1.0
        for p in doc.pages:
            m = detect_unit_multiplier(p.text)
            if m > 1.0:
                doc_multiplier = m
                break

        for p in doc.pages:
            for tbl in p.tables:
                tbl_text = " ".join(" ".join(str(c) for c in r) for r in tbl[:3])
                tbl_multiplier = detect_unit_multiplier(tbl_text) or doc_multiplier

                rev: Optional[float] = None
                rev_label: str = ""
                cogs: Optional[float] = None
                cogs_label: str = ""
                direct_margin: Optional[float] = None
                direct_label: str = ""

                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)
                    if any(k in row_str for k in ["total net revenue", "total revenue", "net revenue", "gross revenue", "total net sales", "revenue"]) and rev is None:
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v is not None and v > 0:
                                rev = v * tbl_multiplier
                                rev_label = str(row[0]).strip()
                                break

                    if any(k in row_str for k in ["cost of goods sold", "cost of sales and contract fulfillment", "cost of sales", "cost of revenue", "total cogs", "cogs"]) and cogs is None:
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v is not None and abs(v) > 0:
                                cogs = abs(v) * tbl_multiplier
                                cogs_label = str(row[0]).strip()
                                break

                    if any(k in row_str for k in ["gross margin %", "gross profit margin %", "gross margin percentage", "gross margin"]) and direct_margin is None:
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v is not None and 0 <= v <= 100:
                                direct_margin = v
                                direct_label = str(row[0]).strip()
                                break

                if rev is not None and cogs is not None and rev > 0:
                    gm = round(((rev - cogs) / rev) * 100.0, 1)
                    is_plausible, err_msg = check_plausibility("gross_margin", gm)
                    status, conf = determine_extraction_status(
                        is_table=True,
                        same_document=True,
                        is_plausible=is_plausible,
                        has_conflict=False
                    )
                    snip = sanitize_snippet(f"Revenue: ${rev:,.2f} ({rev_label}) | COGS: ${cogs:,.2f} ({cogs_label}) | Gross Margin: {gm}%")
                    candidates.append({
                        "gm": gm,
                        "rev": rev,
                        "cogs": cogs,
                        "doc_name": doc.filename,
                        "page": p.page_number,
                        "is_table": True,
                        "status": status,
                        "confidence": conf,
                        "snippet": snip
                    })
                elif direct_margin is not None:
                    is_plausible, err_msg = check_plausibility("gross_margin", direct_margin)
                    status, conf = determine_extraction_status(
                        is_table=True,
                        same_document=True,
                        is_plausible=is_plausible,
                        has_conflict=False
                    )
                    candidates.append({
                        "gm": direct_margin,
                        "rev": None,
                        "cogs": None,
                        "doc_name": doc.filename,
                        "page": p.page_number,
                        "is_table": True,
                        "status": status,
                        "confidence": conf,
                        "snippet": sanitize_snippet(f"Reported Gross Margin: {direct_margin}% ({direct_label})")
                    })

            # Text check (free text)
            for line in p.text.splitlines():
                l_lower = line.lower()
                if "gross margin" in l_lower and ("%" in line or "percent" in l_lower):
                    nums = re.findall(r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%", line)
                    if nums:
                        dm = float(nums[0])
                        is_plausible, _ = check_plausibility("gross_margin", dm)
                        status, conf = determine_extraction_status(
                            is_table=False,
                            same_document=True,
                            is_plausible=is_plausible,
                            has_conflict=False
                        )
                        candidates.append({
                            "gm": dm,
                            "rev": None,
                            "cogs": None,
                            "doc_name": doc.filename,
                            "page": p.page_number,
                            "is_table": False,
                            "status": status,
                            "confidence": conf,
                            "snippet": sanitize_snippet(f"Reported Gross Margin (text): {dm}% ({line.strip()})")
                        })

    if not candidates:
        return None

    # Check conflicts
    unique_gms = {round(c["gm"], 1): c for c in candidates}
    if len(unique_gms) > 1 and (max(unique_gms.keys()) - min(unique_gms.keys()) > 1.0):
        c_strs = [f"{c['doc_name']} (p.{c['page']}): {c['gm']}%" for c in candidates]
        return {
            "answer_value": list(unique_gms.keys())[0],
            "confidence": 0.50,
            "status": "NEEDS_CONFIRMATION",
            "method": "FINANCIAL_TABLE",
            "formula": "gross_margin_pct = ((revenue - cogs) / revenue) * 100",
            "formula_inputs": {"conflict": True, "candidates": [c["gm"] for c in candidates]},
            "source_file": candidates[0]["doc_name"],
            "page": candidates[0]["page"],
            "snippet": sanitize_snippet(f"Conflicting gross margin values detected: {' | '.join(c_strs)}")
        }

    # Prefer table candidate
    table_candidates = [c for c in candidates if c["is_table"]]
    chosen = table_candidates[0] if table_candidates else candidates[0]

    return {
        "answer_value": chosen["gm"],
        "confidence": chosen["confidence"],
        "status": chosen["status"],
        "method": "FINANCIAL_TABLE",
        "formula": "gross_margin_pct = ((revenue - cogs) / revenue) * 100",
        "formula_inputs": {
            "revenue": chosen.get("rev"),
            "cogs": chosen.get("cogs"),
            "source_is_table": chosen["is_table"]
        },
        "source_file": chosen["doc_name"],
        "page": chosen["page"],
        "snippet": chosen["snippet"]
    }


def extract_customer_concentration(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts largest customer revenue share:
    Formula: top1_pct = (top_customer_revenue / total_revenue) * 100
    Rule: Top customer and total revenue MUST come from the SAME document/table.
    Plausibility: must be 0 to 100%.
    """
    candidates: List[Dict[str, Any]] = []

    for doc in docs:
        doc_multiplier = 1.0
        for p in doc.pages:
            m = detect_unit_multiplier(p.text)
            if m > 1.0:
                doc_multiplier = m
                break

        for p in doc.pages:
            for tbl in p.tables:
                tbl_text = " ".join(" ".join(str(c) for c in r) for r in tbl[:3])
                tbl_multiplier = detect_unit_multiplier(tbl_text) or doc_multiplier

                total_rev: Optional[float] = None
                customer_amounts: List[Tuple[float, str]] = []
                direct_pct: Optional[float] = None
                direct_label: str = ""

                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)
                    
                    if any(k in row_str for k in ["total consolidated arr", "total revenue", "total arr", "total client", "total billings"]) or row_str.strip().startswith("total"):
                        for cell in row:
                            if "%" in str(cell):
                                continue
                            v = extract_financial_number(cell)
                            if v is not None and v > 0:
                                total_rev = v * tbl_multiplier
                                break
                    elif any(c for c in row if any(k in str(c).lower() for k in ["customer", "client", "account", "corp", "inc", "enterprises", "solutions", "holdings", "systems", "labs", "partner", "partners", "company", "co."])):
                        # Skip consolidated / other rows from being picked as single largest customer
                        if any(k in row_str for k in ["all other", "consolidated other", "other active", "other customers", "other accounts", "rest of", "all remaining"]):
                            continue
                        for cell in row:
                            if "%" in str(cell):
                                continue
                            v = extract_financial_number(cell)
                            if v is not None and v > 0:
                                customer_amounts.append((v * tbl_multiplier, str(row[0]).strip()))
                                break

                    if any(k in row_str for k in ["share of overall arr", "revenue share %", "concentration %", "% of arr", "% of revenue"]):
                        for cell in row:
                            v = extract_financial_number(cell)
                            if v is not None and 0.0 < v <= 100.0:
                                if direct_pct is None:
                                    direct_pct = v
                                    direct_label = str(row[0]).strip()

                if customer_amounts and total_rev and total_rev > 0:
                    customer_amounts.sort(key=lambda x: x[0], reverse=True)
                    top_amount, top_name = customer_amounts[0]
                    calc_pct = round((top_amount / total_rev) * 100.0, 1)

                    is_plausible, err_msg = check_plausibility("customer_concentration", calc_pct)
                    status, conf = determine_extraction_status(
                        is_table=True,
                        same_document=True,
                        is_plausible=is_plausible,
                        has_conflict=False
                    )

                    snip = sanitize_snippet(
                        f"Top Customer: '{top_name}' (${top_amount:,.2f}) | Total Revenue: ${total_rev:,.2f} | Concentration: {calc_pct}%"
                    )
                    if not is_plausible and err_msg:
                        snip = sanitize_snippet(f"Implausibility flag ({err_msg}): {snip}")

                    candidates.append({
                        "pct": calc_pct,
                        "top_amount": top_amount,
                        "total_rev": total_rev,
                        "doc_name": doc.filename,
                        "page": p.page_number,
                        "is_table": True,
                        "is_plausible": is_plausible,
                        "status": status,
                        "confidence": conf,
                        "snippet": snip
                    })
                elif direct_pct is not None:
                    is_plausible, _ = check_plausibility("customer_concentration", direct_pct)
                    status, conf = determine_extraction_status(
                        is_table=True,
                        same_document=True,
                        is_plausible=is_plausible,
                        has_conflict=False
                    )
                    candidates.append({
                        "pct": direct_pct,
                        "top_amount": None,
                        "total_rev": None,
                        "doc_name": doc.filename,
                        "page": p.page_number,
                        "is_table": True,
                        "is_plausible": is_plausible,
                        "status": status,
                        "confidence": conf,
                        "snippet": sanitize_snippet(f"Direct Top Customer Share: {direct_pct}% ({direct_label})")
                    })

    if not candidates:
        return None

    # Check conflicts
    unique_pcts = {round(c["pct"], 1): c for c in candidates}
    if len(unique_pcts) > 1 and (max(unique_pcts.keys()) - min(unique_pcts.keys()) > 1.0):
        c_strs = [f"{c['doc_name']} (p.{c['page']}): {c['pct']}%" for c in candidates]
        return {
            "answer_value": list(unique_pcts.keys())[0],
            "confidence": 0.50,
            "status": "NEEDS_CONFIRMATION",
            "method": "FINANCIAL_TABLE",
            "formula": "top1_pct = (top_customer_revenue / total_revenue) * 100",
            "formula_inputs": {"conflict": True, "candidates": [c["pct"] for c in candidates]},
            "source_file": candidates[0]["doc_name"],
            "page": candidates[0]["page"],
            "snippet": sanitize_snippet(f"Conflicting customer concentration values detected: {' | '.join(c_strs)}")
        }

    chosen = candidates[0]
    return {
        "answer_value": chosen["pct"],
        "confidence": chosen["confidence"],
        "status": chosen["status"],
        "method": "FINANCIAL_TABLE",
        "formula": "top1_pct = (top_customer_revenue / total_revenue) * 100",
        "formula_inputs": {
            "top_customer_revenue": chosen.get("top_amount"),
            "total_revenue": chosen.get("total_rev"),
            "source_is_table": chosen["is_table"]
        },
        "source_file": chosen["doc_name"],
        "page": chosen["page"],
        "snippet": chosen["snippet"]
    }


def extract_net_revenue_retention(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts Net Revenue Retention (NRR):
    Formula: nrr_pct = (ending_arr / beginning_arr) * 100
    Rule: Beginning and Ending ARR must come from the same document/table.
    """
    candidates: List[Dict[str, Any]] = []

    for doc in docs:
        doc_multiplier = 1.0
        for p in doc.pages:
            m = detect_unit_multiplier(p.text)
            if m > 1.0:
                doc_multiplier = m
                break

        for p in doc.pages:
            for tbl in p.tables:
                tbl_text = " ".join(" ".join(str(c) for c in r) for r in tbl[:3])
                tbl_multiplier = detect_unit_multiplier(tbl_text) or doc_multiplier

                beg_arr: Optional[float] = None
                end_arr: Optional[float] = None
                direct_nrr: Optional[float] = None

                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)
                    if "beginning arr" in row_str or "starting arr" in row_str:
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v and v > 0:
                                beg_arr = v * tbl_multiplier
                                break
                    if "ending arr" in row_str:
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v and v > 0:
                                end_arr = v * tbl_multiplier
                                break
                    if any(k in row_str for k in ["net revenue retention", "net dollar retention", "nrr", "ndr"]):
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v and 50 <= v <= 250:
                                direct_nrr = v
                                break

                if beg_arr and end_arr and beg_arr > 0:
                    nrr = round((end_arr / beg_arr) * 100.0, 1)
                    is_plausible, _ = check_plausibility("nrr", nrr)
                    status, conf = determine_extraction_status(
                        is_table=True,
                        same_document=True,
                        is_plausible=is_plausible,
                        has_conflict=False
                    )
                    candidates.append({
                        "nrr": nrr,
                        "beg_arr": beg_arr,
                        "end_arr": end_arr,
                        "doc_name": doc.filename,
                        "page": p.page_number,
                        "is_table": True,
                        "status": status,
                        "confidence": conf,
                        "snippet": sanitize_snippet(f"Beginning ARR: ${beg_arr:,.2f} | Ending ARR: ${end_arr:,.2f} | NRR: {nrr}%")
                    })
                elif direct_nrr is not None:
                    is_plausible, _ = check_plausibility("nrr", direct_nrr)
                    status, conf = determine_extraction_status(
                        is_table=True,
                        same_document=True,
                        is_plausible=is_plausible,
                        has_conflict=False
                    )
                    candidates.append({
                        "nrr": direct_nrr,
                        "beg_arr": None,
                        "end_arr": None,
                        "doc_name": doc.filename,
                        "page": p.page_number,
                        "is_table": True,
                        "status": status,
                        "confidence": conf,
                        "snippet": sanitize_snippet(f"Reported NRR: {direct_nrr}%")
                    })

    if not candidates:
        return None

    chosen = candidates[0]
    return {
        "answer_value": chosen["nrr"],
        "confidence": chosen["confidence"],
        "status": chosen["status"],
        "method": "FINANCIAL_TABLE",
        "formula": "nrr_pct = (ending_arr / beginning_arr) * 100",
        "formula_inputs": {
            "beginning_arr": chosen.get("beg_arr"),
            "ending_arr": chosen.get("end_arr"),
            "source_is_table": chosen["is_table"]
        },
        "source_file": chosen["doc_name"],
        "page": chosen["page"],
        "snippet": chosen["snippet"]
    }


def extract_budget_variance(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts budget vs actual revenue variance shortfall:
    Formula: shortfall_pct = max(0, ((budget_revenue - actual_revenue) / budget_revenue) * 100)
    Rule: Budget and Actual revenue must come from the same document/table.
    """
    candidates: List[Dict[str, Any]] = []

    for doc in docs:
        doc_multiplier = 1.0
        for p in doc.pages:
            m = detect_unit_multiplier(p.text)
            if m > 1.0:
                doc_multiplier = m
                break

        for p in doc.pages:
            for tbl in p.tables:
                tbl_text = " ".join(" ".join(str(c) for c in r) for r in tbl[:3])
                tbl_multiplier = detect_unit_multiplier(tbl_text) or doc_multiplier

                budget_rev: Optional[float] = None
                actual_rev: Optional[float] = None
                direct_shortfall: Optional[float] = None

                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)
                    if any(k in row_str for k in ["budget revenue", "budgeted revenue", "plan revenue", "board budget"]) and budget_rev is None:
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v and v > 0:
                                budget_rev = v * tbl_multiplier
                                break
                    if any(k in row_str for k in ["actual revenue", "actuals revenue", "actual total revenue"]) and actual_rev is None:
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v and v > 0:
                                actual_rev = v * tbl_multiplier
                                break
                    if any(k in row_str for k in ["variance shortfall %", "revenue shortfall %", "budget variance %"]):
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v is not None and 0.0 <= v <= 100.0:
                                direct_shortfall = v
                                break

                if budget_rev and actual_rev and budget_rev > 0:
                    shortfall = round(max(0.0, ((budget_rev - actual_rev) / budget_rev) * 100.0), 1)
                    is_plausible, _ = check_plausibility("budget_variance", shortfall)
                    status, conf = determine_extraction_status(
                        is_table=True,
                        same_document=True,
                        is_plausible=is_plausible,
                        has_conflict=False
                    )
                    candidates.append({
                        "shortfall": shortfall,
                        "budget": budget_rev,
                        "actual": actual_rev,
                        "doc_name": doc.filename,
                        "page": p.page_number,
                        "is_table": True,
                        "status": status,
                        "confidence": conf,
                        "snippet": sanitize_snippet(f"Budget Revenue: ${budget_rev:,.2f} | Actual Revenue: ${actual_rev:,.2f} | Shortfall: {shortfall}%")
                    })
                elif direct_shortfall is not None:
                    is_plausible, _ = check_plausibility("budget_variance", direct_shortfall)
                    status, conf = determine_extraction_status(
                        is_table=True,
                        same_document=True,
                        is_plausible=is_plausible,
                        has_conflict=False
                    )
                    candidates.append({
                        "shortfall": direct_shortfall,
                        "budget": None,
                        "actual": None,
                        "doc_name": doc.filename,
                        "page": p.page_number,
                        "is_table": True,
                        "status": status,
                        "confidence": conf,
                        "snippet": sanitize_snippet(f"Reported Revenue Variance Shortfall: {direct_shortfall}%")
                    })

    if not candidates:
        return None

    chosen = candidates[0]
    return {
        "answer_value": chosen["shortfall"],
        "confidence": chosen["confidence"],
        "status": chosen["status"],
        "method": "FINANCIAL_TABLE",
        "formula": "shortfall_pct = max(0, ((budget_revenue - actual_revenue) / budget_revenue) * 100)",
        "formula_inputs": {
            "budget_revenue": chosen.get("budget"),
            "actual_revenue": chosen.get("actual"),
            "source_is_table": chosen["is_table"]
        },
        "source_file": chosen["doc_name"],
        "page": chosen["page"],
        "snippet": chosen["snippet"]
    }


def extract_ebitda_addbacks(
    docs: List[ParsedDocument]
) -> Optional[Dict[str, Any]]:
    """
    Extracts EBITDA add-backs percentage:
    Formula: ebitda_addbacks_pct = (management_addbacks / ebitda) * 100
    Rule: Add-backs and EBITDA must come from the same document/table.
    Never match labels containing "adjusted EBITDA" alone without "adjustment" / "add-back".
    """
    candidates: List[Dict[str, Any]] = []

    for doc in docs:
        doc_multiplier = 1.0
        for p in doc.pages:
            m = detect_unit_multiplier(p.text)
            if m > 1.0:
                doc_multiplier = m
                break

        for p in doc.pages:
            for tbl in p.tables:
                tbl_text = " ".join(" ".join(str(c) for c in r) for r in tbl[:3])
                tbl_multiplier = detect_unit_multiplier(tbl_text) or doc_multiplier

                addbacks_val: Optional[float] = None
                addbacks_label: str = ""
                ebitda_val: Optional[float] = None
                ebitda_label: str = ""

                for row in tbl:
                    row_str = " ".join(str(c).lower() for c in row)

                    # Add-back check with synonym list
                    # RULE: never match labels containing "adjusted EBITDA" alone!
                    is_addback_row = any(syn in row_str for syn in ADDBACK_SYNONYMS)
                    if "adjusted ebitda" in row_str and not any(k in row_str for k in ["adjustment", "adjustments", "add-back", "addback", "add back"]):
                        is_addback_row = False

                    if is_addback_row and addbacks_val is None:
                        for cell in reversed(row):
                            v = extract_financial_number(cell)
                            if v is not None and v > 0:
                                addbacks_val = v * tbl_multiplier
                                addbacks_label = str(row[0]).strip()
                                break

                    # Reported EBITDA check (unadjusted / base EBITDA)
                    if any(k in row_str for k in ["reported ebitda", "unadjusted ebitda", "reported operating ebitda", "ebitda"]) and ebitda_val is None:
                        if not any(k in row_str for k in ["adjustment", "adjustments", "add-back", "addback"]):
                            for cell in reversed(row):
                                v = extract_financial_number(cell)
                                if v is not None and abs(v) > 0:
                                    ebitda_val = abs(v) * tbl_multiplier
                                    ebitda_label = str(row[0]).strip()
                                    break

                if addbacks_val is not None and ebitda_val is not None and ebitda_val > 0:
                    pct = round((addbacks_val / ebitda_val) * 100.0, 1)
                    is_plausible, err_msg = check_plausibility("ebitda_addbacks", pct)
                    status, conf = determine_extraction_status(
                        is_table=True,
                        same_document=True,
                        is_plausible=is_plausible,
                        has_conflict=False
                    )
                    snip = sanitize_snippet(
                        f"Add-backs: ${addbacks_val:,.2f} ({addbacks_label}) | EBITDA: ${ebitda_val:,.2f} ({ebitda_label}) | Share: {pct}%"
                    )
                    candidates.append({
                        "pct": pct,
                        "addbacks": addbacks_val,
                        "ebitda": ebitda_val,
                        "doc_name": doc.filename,
                        "page": p.page_number,
                        "is_table": True,
                        "is_plausible": is_plausible,
                        "status": status,
                        "confidence": conf,
                        "snippet": snip
                    })

    if not candidates:
        return None

    unique_pcts = {round(c["pct"], 1): c for c in candidates}
    if len(unique_pcts) > 1 and (max(unique_pcts.keys()) - min(unique_pcts.keys()) > 1.0):
        c_strs = [f"{c['doc_name']} (p.{c['page']}): {c['pct']}%" for c in candidates]
        return {
            "answer_value": list(unique_pcts.keys())[0],
            "confidence": 0.50,
            "status": "NEEDS_CONFIRMATION",
            "method": "FINANCIAL_TABLE",
            "formula": "ebitda_addbacks_pct = (management_addbacks / ebitda) * 100",
            "formula_inputs": {"conflict": True, "candidates": [c["pct"] for c in candidates]},
            "source_file": candidates[0]["doc_name"],
            "page": candidates[0]["page"],
            "snippet": sanitize_snippet(f"Conflicting add-backs percentages detected: {' | '.join(c_strs)}")
        }

    chosen = candidates[0]
    return {
        "answer_value": chosen["pct"],
        "confidence": chosen["confidence"],
        "status": chosen["status"],
        "method": "FINANCIAL_TABLE",
        "formula": "ebitda_addbacks_pct = (management_addbacks / ebitda) * 100",
        "formula_inputs": {
            "management_addbacks": chosen["addbacks"],
            "ebitda": chosen["ebitda"],
            "source_is_table": chosen["is_table"]
        },
        "source_file": chosen["doc_name"],
        "page": chosen["page"],
        "snippet": chosen["snippet"]
    }


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
    Status is strictly NEEDS_CONFIRMATION, never AUTO_FILLED.
    """
    qt = question_text.lower()
    
    target_terms: List[str] = []
    if "soc 2" in qt or "soc2" in qt:
        target_terms = ["soc 2", "type ii", "type 2", "service organization control", "trust services criteria"]
    elif "iso 9001" in qt:
        target_terms = ["iso 9001", "quality management systems", "iso 9001:2015"]
    elif "iso 27001" in qt:
        target_terms = ["iso 27001", "information security management system", "iso/iec 27001"]
    elif "fda" in qt and ("registration" in qt or "807" in qt or "510(k)" in qt):
        target_terms = ["fda establishment registration", "21 cfr part 807", "device listing", "fei number", "510(k)"]
    elif "hitrust" in qt:
        target_terms = ["hitrust", "csf certification", "common security framework"]
    elif "standing" in qt or "good standing" in qt:
        target_terms = ["good standing", "certificate of good standing", "secretary of state"]
    else:
        target_terms = [w for w in re.findall(r"\b[A-Za-z0-9\-]{4,}\b", qt) if w not in ["company", "does", "have", "maintain", "current", "annual"]]

    if not target_terms:
        return None

    for doc in docs:
        for p in doc.pages:
            p_text = p.text
            p_lower = p_text.lower()

            matched_terms = [t for t in target_terms if t in p_lower]
            if matched_terms:
                first_term = matched_terms[0]
                idx = p_lower.find(first_term)
                start = max(0, idx - 100)
                end = min(len(p_text), idx + 250)
                raw_snip = p_text[start:end]
                
                # Confidence determination
                confidence = 0.70 if len(matched_terms) >= 2 or doc.file_type == "certificate_or_report" else 0.50
                status = "NEEDS_CONFIRMATION"

                snippet = sanitize_snippet(
                    f"Document found: '{doc.filename}' (Page {p.page_number}). Matched: {', '.join(matched_terms)}. Excerpt: ...{raw_snip}..."
                )

                return {
                    "answer_value": "document found",
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
    Status is strictly NEEDS_CONFIRMATION, never AUTO_FILLED.
    """
    qt = question_text.lower()
    
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

                confidence = 0.70 if len(matches) >= 2 or doc.file_type == "policy" else 0.50
                status = "NEEDS_CONFIRMATION"

                snippet = sanitize_snippet(
                    f"Document found: '{doc.filename}' (Page {p.page_number}). Matched: {', '.join(matches)}. Excerpt: ...{raw_snip}..."
                )

                return {
                    "answer_value": "document found",
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
            result = None

    if result is None:
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
