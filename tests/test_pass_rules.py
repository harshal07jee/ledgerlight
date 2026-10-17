
"""
Unit tests for Pass Rules and Polarity Inversion (PRD Section 6.5).
"""

import json
from pathlib import Path

from apps.api.core.pass_rules import (
    AnswerState,
    KNOWN_RULE_TYPES,
    evaluate_pass_rule,
    infer_pass_rule,
    should_pass_when_no,
)


def test_polarity_inversion_detection():
    # Desirable answer is No / False
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
    rule_standard = {"type": "bool", "pass_when": True}

    assert evaluate_pass_rule(rule_standard, True) == AnswerState.PASS
    assert evaluate_pass_rule(rule_standard, "Yes") == AnswerState.PASS
    assert evaluate_pass_rule(rule_standard, "yes") == AnswerState.PASS
    assert evaluate_pass_rule(rule_standard, False) == AnswerState.FAIL
    assert evaluate_pass_rule(rule_standard, "No") == AnswerState.FAIL
    assert evaluate_pass_rule(rule_standard, None) == AnswerState.UNVERIFIED

    rule_inverted = {"type": "bool", "pass_when": False}

    assert evaluate_pass_rule(rule_inverted, False) == AnswerState.PASS
    assert evaluate_pass_rule(rule_inverted, "No") == AnswerState.PASS
    assert evaluate_pass_rule(rule_inverted, True) == AnswerState.FAIL
    assert evaluate_pass_rule(rule_inverted, "Yes") == AnswerState.FAIL


def test_evaluate_threshold_rules():
    # Runway: >= 9 PASS, >= 6 PARTIAL, < 6 FAIL
    runway_rule = {
        "type": "threshold",
        "field": "runway_months",
        "op": "gte",
        "value": 9,
        "partial": {"op": "gte", "value": 6},
    }

    assert evaluate_pass_rule(runway_rule, 14.0) == AnswerState.PASS
    assert evaluate_pass_rule(runway_rule, 9.0) == AnswerState.PASS
    assert evaluate_pass_rule(runway_rule, 7.5) == AnswerState.PARTIAL
    assert evaluate_pass_rule(runway_rule, 6.0) == AnswerState.PARTIAL
    assert evaluate_pass_rule(runway_rule, 4.0) == AnswerState.FAIL

    # Customer concentration: <= 20% PASS, > 20% FAIL
    cust_rule = {
        "type": "threshold",
        "field": "top1_customer_pct",
        "op": "lte",
        "value": 20,
    }

    assert evaluate_pass_rule(cust_rule, 12.5) == AnswerState.PASS
    assert evaluate_pass_rule(cust_rule, 20.0) == AnswerState.PASS
    assert evaluate_pass_rule(cust_rule, 34.0) == AnswerState.FAIL


def test_evaluate_choice_rules():
    choice_rule = {
        "type": "choice",
        "pass_values": ["Class I", "Class II"],
        "partial_values": ["Pending Review"],
        "fail_values": ["Class III", "Non-compliant"],
    }

    assert evaluate_pass_rule(choice_rule, "Class II") == AnswerState.PASS
    assert evaluate_pass_rule(choice_rule, "Pending Review") == AnswerState.PARTIAL
    assert evaluate_pass_rule(choice_rule, "Class III") == AnswerState.FAIL


def test_unknown_or_malformed_rule_returns_unverified():
    """Unknown or malformed rules must never return PASS."""

    unknown_rule = {"type": "quantum_ai_evaluator", "foo": "bar"}
    state, note = evaluate_pass_rule(unknown_rule, True, return_note=True)
    assert state == AnswerState.UNVERIFIED
    assert "Unrecognized rule_type" in note

    state, note = evaluate_pass_rule({}, "yes", return_note=True)
    assert state == AnswerState.UNVERIFIED
    assert "Malformed" in note or "missing" in note

    state, note = evaluate_pass_rule(None, "yes", return_note=True)
    assert state == AnswerState.UNVERIFIED
    assert "Malformed or missing" in note

    state, _ = evaluate_pass_rule("type: bool", "yes", return_note=True)
    assert state == AnswerState.UNVERIFIED

    malformed_thresh = {"type": "threshold", "op": "gte"}
    state, note = evaluate_pass_rule(malformed_thresh, 10, return_note=True)
    assert state == AnswerState.UNVERIFIED
    assert "missing 'value'" in note

    state, note = evaluate_pass_rule(
        {"type": "choice"}, "Class I", return_note=True
    )
    assert state == AnswerState.UNVERIFIED
    assert "Malformed choice" in note


def test_all_questions_in_bank_resolve_through_known_rule_type():
    """Validate pass rules in the checked-in question seed files."""

    root = Path(__file__).resolve().parents[1]
    seed_files = [
        root / "data" / "seeds" / "normalized_branch_questions.json",
        root / "data" / "seeds" / "draft_universal_core.json",
    ]

    questions = []
    for path in seed_files:
        assert path.exists(), f"Question seed file missing: {path}"
        questions.extend(json.loads(path.read_text(encoding="utf-8")))

    assert questions, "Question bank must not be empty"

    for question in questions:
        qid = question["question_id"]
        rule = question.get("pass_rule")

        assert isinstance(rule, dict), (
            f"Question {qid} pass_rule must be a dict"
        )

        rule_type = str(rule.get("type", "")).strip().lower()
        assert rule_type in KNOWN_RULE_TYPES, (
            f"Question {qid} has unknown rule type: {rule.get('type')!r}"
        )


def test_routing_rule_and_unrecognized_choice():
    """Routing questions are excluded from scoring."""

    routing_rule = {
        "type": "routing",
        "description": (
            "Routing question: routes conditional branches; "
            "excluded from scoring."
        ),
    }

    state, note = evaluate_pass_rule(
        routing_rule, "B2B Enterprise SaaS", return_note=True
    )
    assert state == AnswerState.ROUTING
    assert "excluded from score calculation" in note

    choice_rule = {
        "type": "choice",
        "pass_values": ["Class I", "Class II"],
        "partial_values": ["Pending Review"],
        "fail_values": ["Class III"],
    }

    state, note = evaluate_pass_rule(
        choice_rule, "Completely Unknown Option", return_note=True
    )
    assert state == AnswerState.UNVERIFIED
    assert "unrecognized" in note


def test_self_attested_strict_scoring_and_disclosed():
    """Self-attested rules must not pass arbitrary text or numbers."""

    sa_rule = {"type": "self_attested"}

    assert evaluate_pass_rule(sa_rule, "yes") == AnswerState.PASS
    assert evaluate_pass_rule(sa_rule, True) == AnswerState.PASS
    assert evaluate_pass_rule(sa_rule, "no") == AnswerState.FAIL
    assert evaluate_pass_rule(sa_rule, False) == AnswerState.FAIL

    assert (
        evaluate_pass_rule(
            sa_rule, "Executive succession plan is in place"
        )
        == AnswerState.UNVERIFIED
    )
    assert evaluate_pass_rule(sa_rule, 1500000) == AnswerState.UNVERIFIED
    assert evaluate_pass_rule(sa_rule, "85%") == AnswerState.UNVERIFIED
    assert evaluate_pass_rule(sa_rule, 85.5) == AnswerState.UNVERIFIED

    disc_rule = {
        "type": "disclosed",
        "description": (
            "Unscored disclosure: recorded in diligence report; "
            "excluded from score calculation."
        ),
    }

    state, note = evaluate_pass_rule(
        disc_rule, "$1,500,000 NWC Peg", return_note=True
    )
    assert state == AnswerState.DISCLOSED
    assert "Recorded unscored disclosure" in note
