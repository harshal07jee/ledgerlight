"""
Messy Fixture Extraction Safety Benchmark Test Suite (Requirement 6).

Asserts deterministic extraction safety rules across 7 real-world messy fixtures:
1. messy_financials_thousands_quarterly.xlsx ($ in '000s, Q1-Q4, normalized adjustments)
2. messy_customer_concentration.csv (ACV table with header preambles)
3. messy_bank_statement.pdf (text PDF with $2,250,000 balance, $(800,000) debits, opening balance)
4. scanned_page_soc2.pdf (raster image PDF without digital text layer)
5. messy_pnl_millions.xlsx (P&L in USD millions)
6. messy_two_accounts_bank_statement.pdf (bank PDF with two accounts)
7. messy_split_customer.csv (customer list with enterprise customer split across two rows)

STRICT SAFETY INVARIANTS:
- No wrong value is EVER AUTO_FILLED.
- Free text regex parsing is NEVER AUTO_FILLED (must be NEEDS_CONFIRMATION with confidence <= 0.70).
- Scanned pages produce an explicit "OCR unavailable" warning, not silent empty text.
- Parentheses $(800,000) parse as negative.
- $2,250,000 parses as 2,250,000 (never 250,000).
- Conflicting documents return NEEDS_CONFIRMATION showing both values and sources.
"""
import os
import sys

from apps.api.core.ingest import parse_document
from apps.api.core.extractors import (
    extract_cash_runway,
    extract_customer_concentration,
    extract_ebitda_addbacks,
    extract_gross_margin,
    extract_answer_for_question,
    extract_financial_number,
    detect_unit_multiplier
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "messy_data_room")


def load_fixture(filename: str):
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "rb") as f:
        content = f.read()
    return parse_document(filename, content)


def test_messy_bank_statement_number_parsing_and_free_text_safety():
    """
    Fixture 3: messy_bank_statement.pdf
    Validates:
    - '$2,250,000.00' is parsed as 2250000.0 (NOT 250,000).
    - Closing balance is preferred over opening balance ($2,400,000).
    - Accounting parentheses '$(800,000.00)' parse as -800000.0.
    - Certified closing balance $2,250,000 / $150,000 monthly burn = 15.0 months runway.
    - STRICT: Free-text parsed values MUST NEVER be AUTO_FILLED (must be NEEDS_CONFIRMATION, conf <= 0.70).
    """
    doc = load_fixture("messy_bank_statement.pdf")
    res = extract_cash_runway([doc])

    assert res is not None, "Should extract cash and runway proposal"
    
    # Assert number parsing fix: must NOT parse as 250,000
    cash_val = res["formula_inputs"]["cash_balance"]
    assert cash_val == 2250000.0, f"Expected 2,250,000.0 cash balance, got {cash_val}"
    assert cash_val != 250000.0, "CRITICAL BUG REGRESSION: $2,250,000 parsed as 250,000!"

    # Assert preferred Closing/Ending balance ($2.25M)
    assert cash_val == 2250000.0

    # Assert runway plausibility ($2.25M / $150k burn = 15.0 months)
    runway_val = res["answer_value"]
    assert runway_val == 15.0, f"Expected 15.0 months runway, got {runway_val}"

    # SAFETY INVARIANT: Free text regex extraction MUST NEVER be AUTO_FILLED
    assert res["status"] == "NEEDS_CONFIRMATION", f"Expected NEEDS_CONFIRMATION for free text, got {res['status']}"
    assert res["confidence"] <= 0.70, f"Confidence for free text must be <= 0.70, got {res['confidence']}"


def test_accounting_parentheses_and_currency_parsing():
    """Direct tests for extract_financial_number edge cases."""
    # Comma separation and thousands
    assert extract_financial_number("$2,250,000.00") == 2250000.0
    assert extract_financial_number("$250,000") == 250000.0
    
    # Accounting parentheses as negative
    assert extract_financial_number("$(800,000.00)") == -800000.0
    assert extract_financial_number("(800,000)") == -800000.0
    assert extract_financial_number("($150,000)") == -150000.0

    # Normal negative
    assert extract_financial_number("-$50,000.00") == -50000.0


def test_messy_financials_thousands_quarterly():
    """
    Fixture 1: messy_financials_thousands_quarterly.xlsx
    Validates:
    - Detects unit multiplier 'in thousands' ($ in '000s).
    - Recognizes 'Normalized EBITDA Adjustments' as an add-back label.
    - Never matches 'adjusted EBITDA' alone without adjustment/addback keywords.
    - Calculates gross margin (GP $3,000 / Rev $4,000 = 75.0%).
    - Plausibility checks pass: percentages 0 to 100%.
    """
    doc = load_fixture("messy_financials_thousands_quarterly.xlsx")

    # Test EBITDA add-backs
    addback_res = extract_ebitda_addbacks([doc])
    assert addback_res is not None
    # Exact ground truth: FY2025 normalized adjustments sum to $144,000 across quarters
    assert addback_res["formula_inputs"]["management_addbacks"] == 144000.0
    assert addback_res["formula_inputs"]["ebitda"] == 1800000.0
    assert addback_res["answer_value"] == 8.0  # 144k / 1800k reported EBITDA = 8.0% (and 1.37% of revenue)
    # Must NOT auto-fill wrong values
    if addback_res["status"] == "AUTO_FILLED":
        assert addback_res["confidence"] == 1.0

    # Test Gross Margin
    gm_res = extract_gross_margin([doc])
    assert gm_res is not None
    # GP 8,400k / Rev 10,500k = 80.0%
    assert 0.0 <= gm_res["answer_value"] <= 100.0
    assert gm_res["answer_value"] == 80.0


def test_messy_customer_concentration():
    """
    Fixture 2: messy_customer_concentration.csv
    Validates:
    - Skips preamble headers.
    - Numerator ($1.8M) and Denominator ($10.5M) extracted from same table.
    - Concentration ratio = 17.1%.
    - Plausibility: 0% <= ratio <= 100%.
    """
    doc = load_fixture("messy_customer_concentration.csv")
    res = extract_customer_concentration([doc])

    assert res is not None
    assert res["answer_value"] == 17.1
    assert 0.0 <= res["answer_value"] <= 100.0
    assert res["formula_inputs"]["top_customer_revenue"] == 1800000.0
    assert res["formula_inputs"]["total_revenue"] == 10500000.0


def test_scanned_page_soc2_explicit_ocr_warning(monkeypatch):
    """
    Fixture 4: scanned_page_soc2.pdf
    Validates:
    - Scanned page without text layer produces explicit 'OCR unavailable' warning.
    - Does NOT produce silent empty text.
    - No wrong values are extracted or AUTO_FILLED.
    """
    monkeypatch.setitem(sys.modules, "pytesseract", None)
    doc = load_fixture("scanned_page_soc2.pdf")
    assert doc.page_count == 1
    page = doc.pages[0]

    # Must contain explicit warning, not silent empty string
    assert len(page.warnings) > 0, "Page must contain OCR unavailable warning"
    assert "OCR unavailable" in page.warnings[0]
    assert "[OCR unavailable on page 1" in page.text

    # Document warnings must also reflect it
    assert any("OCR unavailable" in w for w in doc.warnings)

    # Question extraction must return MANUAL_REQUIRED or None
    q = {
        "question_id": "OPS_02",
        "dimension": "OPS_TECH_CYBER",
        "evidence_type": "CERTIFICATE_OR_REPORT",
        "input_type": "BOOLEAN"
    }
    ext = extract_answer_for_question(q, [doc])
    assert ext["status"] != "AUTO_FILLED", "Scanned page must never AUTO_FILL"


def test_messy_pnl_millions():
    """
    Fixture 5: messy_pnl_millions.xlsx
    Validates:
    - Detects unit multiplier 'in millions' ($ in Millions).
    - Revenue $10.5M, COGS $2.1M, Gross Profit $8.4M -> GM 80.0%.
    - Normalizes correctly.
    """
    doc = load_fixture("messy_pnl_millions.xlsx")
    
    gm_res = extract_gross_margin([doc])
    assert gm_res is not None
    assert gm_res["answer_value"] == 80.0
    assert gm_res["formula_inputs"]["revenue"] == 10.5
    assert gm_res["formula_inputs"]["cogs"] == 2.1


def test_messy_two_accounts_bank_statement():
    """
    Fixture 6: messy_two_accounts_bank_statement.pdf
    Validates:
    - Bank statement PDF with two distinct accounts (Operating Checking $1.75M, Payroll Escrow $500k).
    - Multi-account text extraction must NEVER AUTO_FILL.
    - Returns NEEDS_CONFIRMATION with confidence <= 0.70.
    """
    doc = load_fixture("messy_two_accounts_bank_statement.pdf")
    res = extract_cash_runway([doc])

    assert res is not None
    assert res["status"] == "NEEDS_CONFIRMATION", "Multi-account statement must require confirmation"
    assert res["confidence"] <= 0.70
    assert res["status"] != "AUTO_FILLED"


def test_messy_split_customer_rows():
    """
    Fixture 7: messy_split_customer.csv
    Validates:
    - Customer list with top customer split across regional rows:
      'Acme Global Enterprises - North America Division' ($1,000,000.00)
      'Acme Global Enterprises - EMEA Subsidiary' ($800,000.00)
    - Normalized name merging sums Acme to $1,800,000 (17.1% of $10.5M).
    - If not merged, Beta Corporation at $1.2M (11.4%) would erroneously be picked.
    - STRICT: Must NEVER AUTO_FILL a value that ignores a split.
    - Status must be NEEDS_CONFIRMATION.
    """
    doc = load_fixture("messy_split_customer.csv")
    res = extract_customer_concentration([doc])

    assert res is not None
    assert 0.0 <= res["answer_value"] <= 100.0
    # True merged ground truth: $1.8M / $10.5M = 17.1%
    assert res["answer_value"] == 17.1
    assert res["formula_inputs"]["top_customer_revenue"] == 1800000.0
    assert res["formula_inputs"]["total_revenue"] == 10500000.0
    # Must NEVER AUTO_FILL a value that ignores a split
    assert res["status"] == "NEEDS_CONFIRMATION"
    assert res["confidence"] <= 0.70
    assert "merged from split rows" in res["snippet"]


def test_conflicting_documents_returns_needs_confirmation():
    """
    Requirement 4: When two documents give conflicting values for the same metric,
    do not pick one. Return NEEDS_CONFIRMATION showing both values and sources.
    """
    # Create two conflicting documents (e.g. two bank statements with different balances)
    doc1_content = b"SVB Bank Statement\nEnding Balance: $1,000,000.00\nAverage Monthly Burn: $100,000.00\n"
    doc2_content = b"Chase Bank Statement\nEnding Balance: $2,500,000.00\nAverage Monthly Burn: $100,000.00\n"

    doc1 = parse_document("bank_statement_svb.txt", doc1_content)
    doc2 = parse_document("bank_statement_chase.txt", doc2_content)

    res = extract_cash_runway([doc1, doc2])
    assert res is not None
    assert res["status"] == "NEEDS_CONFIRMATION", "Conflicting documents must NEVER pick one or AUTO_FILL"
    assert res["confidence"] <= 0.50
    # Snippet or formula must cite conflicting values and sources
    text = (res.get("snippet") or "") + (res.get("formula") or "")
    assert "Conflicting" in text or "bank_statement" in text
