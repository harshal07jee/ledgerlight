"""
Unit tests for Pass Rules and Polarity Inversion (PRD Section 6.5).
"""
import pytest
from apps.api.core.pass_rules import (
    should_pass_when_no,
    infer_pass_rule,
    evaluate_pass_rule,
    AnswerState
)


def test_polarity_inversion_detection():
    # Desirable answer is No / False (compliance risk, violation, liabilities)
    assert should_pass_when_no("Has the company been cited for any OSHA violations?") is True
    assert should_pass_when_no("Does the software rely on viral copyleft open-source licenses?") is True
    assert should_pass_when_no("Do active SLAs contain unlimited financial liability caps?") is True
    assert should_pass_when_no("Are core product functionalities entirely dependent on a single third-party API?") is True
    assert should_pass_when_no("Do any compensation structures factor in referral volume?") is True
    assert should_pass_when_no("Are there active environmental liabilities?") is True

    # Desirable answer is Yes / True
    assert should_pass_when_no("Is the company validly existing and in good standing?") is False
    assert should_pass_when_no("Has the company completed an independent SOC 2 Type II audit?") is False
    assert should_pass_when_no("Has every employee executed a binding PIIA invention assignment agreement?") is False


def test_evaluate_boolean_rules():
    # Rule 1: Pass when True
    rule_standard = {"type": "bool", "pass_when": True}
    assert evaluate_pass_rule(rule_standard, True) == AnswerState.PASS
    assert evaluate_pass_rule(rule_standard, "Yes") == AnswerState.PASS
    assert evaluate_pass_rule(rule_standard, "yes") == AnswerState.PASS
    assert evaluate_pass_rule(rule_standard, False) == AnswerState.FAIL
    assert evaluate_pass_rule(rule_standard, "No") == AnswerState.FAIL
    assert evaluate_pass_rule(rule_standard, None) == AnswerState.UNVERIFIED

    # Rule 2: Pass when False (polarity inverted)
    rule_inverted = {"type": "bool", "pass_when": False}
    assert evaluate_pass_rule(rule_inverted, False) == AnswerState.PASS
    assert evaluate_pass_rule(rule_inverted, "No") == AnswerState.PASS
    assert evaluate_pass_rule(rule_inverted, True) == AnswerState.FAIL
    assert evaluate_pass_rule(rule_inverted, "Yes") == AnswerState.FAIL


def test_evaluate_threshold_rules():
    # Runway months: >= 9 is PASS, >= 6 is PARTIAL, < 6 is FAIL (PRD 6.5 & questions.txt)
    runway_rule = {
        "type": "threshold",
        "field": "runway_months",
        "op": "gte",
        "value": 9,
        "partial": {"op": "gte", "value": 6}
    }
    assert evaluate_pass_rule(runway_rule, 14.0) == AnswerState.PASS
    assert evaluate_pass_rule(runway_rule, 9.0) == AnswerState.PASS
    assert evaluate_pass_rule(runway_rule, 7.5) == AnswerState.PARTIAL
    assert evaluate_pass_rule(runway_rule, 6.0) == AnswerState.PARTIAL
    assert evaluate_pass_rule(runway_rule, 4.0) == AnswerState.FAIL

    # Customer concentration: <= 20% is PASS, > 20% is FAIL
    cust_rule = {
        "type": "threshold",
        "field": "top1_customer_pct",
        "op": "lte",
        "value": 20
    }
    assert evaluate_pass_rule(cust_rule, 12.5) == AnswerState.PASS
    assert evaluate_pass_rule(cust_rule, 20.0) == AnswerState.PASS
    assert evaluate_pass_rule(cust_rule, 34.0) == AnswerState.FAIL


def test_evaluate_choice_rules():
    choice_rule = {
        "type": "choice",
        "pass_values": ["Class I", "Class II"],
        "partial_values": ["Pending Review"],
        "fail_values": ["Class III", "Non-compliant"]
    }
    assert evaluate_pass_rule(choice_rule, "Class II") == AnswerState.PASS
    assert evaluate_pass_rule(choice_rule, "Pending Review") == AnswerState.PARTIAL
    assert evaluate_pass_rule(choice_rule, "Class III") == AnswerState.FAIL


def test_unknown_or_malformed_rule_returns_unverified():
    """Safety requirement: unrecognized or malformed pass_rule must NEVER return PASS; must return UNVERIFIED."""
    # Unknown rule type
    unknown_rule = {"type": "quantum_ai_evaluator", "foo": "bar"}
    state, note = evaluate_pass_rule(unknown_rule, True, return_note=True)
    assert state == AnswerState.UNVERIFIED
    assert "Unrecognized rule_type" in note

    # Empty dict rule
    empty_rule = {}
    state, note = evaluate_pass_rule(empty_rule, "yes", return_note=True)
    assert state == AnswerState.UNVERIFIED
    assert "Malformed" in note or "missing" in note

    # None rule
    state, note = evaluate_pass_rule(None, "yes", return_note=True)
    assert state == AnswerState.UNVERIFIED
    assert "Malformed or missing" in note

    # Non-dict rule
    state, note = evaluate_pass_rule("type: bool", "yes", return_note=True)
    assert state == AnswerState.UNVERIFIED

    # Malformed threshold missing value
    malformed_thresh = {"type": "threshold", "op": "gte"}
    state, note = evaluate_pass_rule(malformed_thresh, 10, return_note=True)
    assert state == AnswerState.UNVERIFIED
    assert "missing 'value'" in note

    # Malformed choice with no values
    malformed_choice = {"type": "choice"}
    state, note = evaluate_pass_rule(malformed_choice, "Class I", return_note=True)
    assert state == AnswerState.UNVERIFIED
    assert "Malformed choice" in note


def test_all_questions_in_bank_resolve_through_known_rule_type():
    """Verify EVERY question in the bank has a valid pass_rule matching a known rule type."""
    import sqlite3
    import json
    from apps.api.core.pass_rules import KNOWN_RULE_TYPES

    conn = sqlite3.connect("ledgerlight.db")
    c = conn.cursor()
    c.execute("SELECT question_id, input_type, pass_rule FROM questions")
    rows = c.fetchall()
    assert len(rows) > 0, "Question bank must not be empty"

    for qid, input_type, pass_rule_raw in rows:
        assert pass_rule_raw is not None, f"Question {qid} is missing pass_rule"
        rule = json.loads(pass_rule_raw) if isinstance(pass_rule_raw, str) else pass_rule_raw
        assert isinstance(rule, dict), f"Question {qid} pass_rule is not a dict"
        rule_type = str(rule.get("type", "")).strip().lower()
        assert rule_type in KNOWN_RULE_TYPES, f"Question {qid} has unknown rule type: '{rule.get('type')}'"


def test_routing_rule_and_unrecognized_choice():
    """Routing questions return ROUTING, and unrecognized choices return UNVERIFIED (not FAIL)."""
    routing_rule = {
        "type": "routing",
        "description": "Routing question: routes conditional branches; excluded from scoring."
    }
    # Any valid choice answer returns ROUTING
    state, note = evaluate_pass_rule(routing_rule, "B2B Enterprise SaaS", return_note=True)
    assert state == AnswerState.ROUTING
    assert "excluded from score calculation" in note

    # Unrecognized choice answers must return UNVERIFIED, NOT FAIL
    choice_rule = {
        "type": "choice",
        "pass_values": ["Class I", "Class II"],
        "partial_values": ["Pending Review"],
        "fail_values": ["Class III"]
    }
    state, note = evaluate_pass_rule(choice_rule, "Completely Unknown Option", return_note=True)
    assert state == AnswerState.UNVERIFIED
    assert "unrecognized" in note


def test_self_attested_strict_scoring_and_disclosed():
    """A self_attested rule must NEVER return PASS for arbitrary text or numbers; disclosed returns DISCLOSED."""
    sa_rule = {"type": "self_attested"}

    # Boolean affirmations pass/fail
    assert evaluate_pass_rule(sa_rule, "yes") == AnswerState.PASS
    assert evaluate_pass_rule(sa_rule, True) == AnswerState.PASS
    assert evaluate_pass_rule(sa_rule, "no") == AnswerState.FAIL
    assert evaluate_pass_rule(sa_rule, False) == AnswerState.FAIL

    # Arbitrary text, numbers, percentages MUST NEVER RETURN PASS
    assert evaluate_pass_rule(sa_rule, "Executive succession plan is in place") == AnswerState.UNVERIFIED
    assert evaluate_pass_rule(sa_rule, 1500000) == AnswerState.UNVERIFIED
    assert evaluate_pass_rule(sa_rule, "85%") == AnswerState.UNVERIFIED
    assert evaluate_pass_rule(sa_rule, 85.5) == AnswerState.UNVERIFIED

    # Disclosed rule returns DISCLOSED
    disc_rule = {
        "type": "disclosed",
        "description": "Unscored disclosure: recorded in diligence report; excluded from score calculation."
    }
    state, note = evaluate_pass_rule(disc_rule, "$1,500,000 NWC Peg", return_note=True)
    assert state == AnswerState.DISCLOSED
    assert "Recorded unscored disclosure" in note


