"""
Deterministic Pass Rule Evaluator and Rule Inferencer (PRD Section 6.5 & 8.2).
States:
- PASS (1.0)
- PARTIAL (0.5)
- FAIL (0.0)
- UNVERIFIED (unanswered / missing)
"""
import re
from enum import Enum
from typing import Dict, Any, Optional, Union, List, Tuple


class AnswerState(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"
    ROUTING = "ROUTING"
    DISCLOSED = "DISCLOSED"


# Patterns indicating that "No" or "False" is the passing (safe/compliant) answer
NEGATIVE_PASS_PATTERNS = [
    r"\bviolations?\b",
    r"\bcitations?\b",
    r"\bfines?\b",
    r"\bliabilit(y|ies)\b",
    r"\blitigat(ion|ed|ing)\b",
    r"\bunlimited\s+liability\b",
    r"\bcopyleft\b",
    r"\bgpl\b",
    r"\bagpl\b",
    r"\bviral\b",
    r"\breferral\s+volume\b",
    r"\bkickback\b",
    r"\bsingle\s+point\s+of\s+failure\b",
    r"\bentirely\s+dependent\s+on\s+a\s+single\b",
    r"\bprohibited\b",
    r"\bforeign\s+entities\s+of\s+concern\b",
    r"\bfeoc\b",
    r"\bdisqualif(ied|ication)\b",
    r"\bmaterial\s+breach(es)?\b",
    r"\bdefaults?\b",
    r"\bpenalty\b",
    r"\bpenalties\b",
    r"\bdegradation\b",
    r"\bhazardous\b",
    r"\bforced\s+labor\b",
]


def should_pass_when_no(question_text: str) -> bool:
    """
    Detects if answering 'No' is the desirable, compliant outcome for a question.
    Example: 'Has the company been cited for any OSHA violations?' -> No is passing.
    """
    txt = question_text.lower()
    for pattern in NEGATIVE_PASS_PATTERNS:
        if re.search(pattern, txt):
            return True
    return False


def infer_pass_rule(question_text: str, input_type: str, explicit_threshold: Optional[str] = None) -> Dict[str, Any]:
    """Generates an explicit deterministic pass_rule based on question semantics and input_type."""
    inp = input_type.upper()

    if inp == "BOOLEAN":
        pass_when = False if should_pass_when_no(question_text) else True
        return {
            "type": "bool",
            "pass_when": pass_when
        }

    if inp == "MULTIPLE_CHOICE":
        return {
            "type": "routing",
            "description": "Routing question: routes conditional branches; excluded from scoring."
        }

    # Threshold rules for financial / numerical metrics explicitly cited in PRD 6.5 / questions.txt
    txt = question_text.lower()
    if "runway" in txt or "cash burn" in txt:
        return {
            "type": "threshold",
            "field": "runway_months",
            "op": "gte",
            "value": 9,
            "partial": {"op": "gte", "value": 6}
        }

    if "largest customer" in txt or "top 1" in txt or "customer concentration" in txt:
        return {
            "type": "threshold",
            "field": "top1_customer_pct",
            "op": "lte",
            "value": 20
        }

    if "net revenue retention" in txt or "nrr" in txt:
        return {
            "type": "threshold",
            "field": "nrr_pct",
            "op": "gte",
            "value": 100
        }

    if "budget variance" in txt or "forecast" in txt:
        return {
            "type": "threshold",
            "field": "budget_variance_pct",
            "op": "lte",
            "value": 15
        }

    if "add-backs" in txt or "ebitda" in txt and "add-back" in txt:
        return {
            "type": "threshold",
            "field": "ebitda_add_backs_pct",
            "op": "lte",
            "value": 10
        }

    if "gross margin" in txt:
        return {
            "type": "threshold",
            "field": "gross_margin_pct",
            "op": "gte",
            "value": 70,
            "partial": {"op": "gte", "value": 50}
        }

    # For PERCENTAGE, CURRENCY, NUMBER, and TEXT questions without an explicit numeric threshold:
    # They are unscored disclosures (recorded and shown in report, excluded from score calculation)
    return {
        "type": "disclosed",
        "description": "Unscored disclosure: recorded in diligence report; excluded from score calculation."
    }


KNOWN_RULE_TYPES = {"bool", "boolean", "choice", "threshold", "self_attested", "routing", "disclosed"}


def evaluate_pass_rule(
    rule: Optional[Dict[str, Any]], 
    answer_value: Any,
    return_note: bool = False
) -> Union[AnswerState, Tuple[AnswerState, Optional[str]]]:
    """
    Evaluates an answer value deterministically against a question's pass_rule.
    PRD 6.5 & 8.2:
    - PASS (1.0)
    - PARTIAL (0.5)
    - FAIL (0.0)
    - UNVERIFIED: unanswered, missing, or malformed/unrecognized rule.
    - ROUTING: routing question (conditional branches); excluded from score, counts in completeness.
    - DISCLOSED: unscored disclosure; recorded in report, excluded from score, counts in completeness.

    CRITICAL SAFETY REQUIREMENT:
    An unrecognized, missing, or malformed pass_rule must NEVER return PASS.
    It returns UNVERIFIED (excluded from score, counted in completeness) with a clear note.
    """
    if answer_value is None or answer_value == "":
        res = (AnswerState.UNVERIFIED, "No answer provided")
        return res if return_note else res[0]

    if not rule or not isinstance(rule, dict):
        res = (AnswerState.UNVERIFIED, f"Malformed or missing pass_rule: expected dict, got {type(rule).__name__}")
        return res if return_note else res[0]

    raw_rule_type = rule.get("type")
    if not raw_rule_type:
        res = (AnswerState.UNVERIFIED, "Malformed pass_rule: missing 'type' key")
        return res if return_note else res[0]

    rule_type = str(raw_rule_type).strip().lower()

    if rule_type not in KNOWN_RULE_TYPES:
        res = (AnswerState.UNVERIFIED, f"Unrecognized rule_type '{raw_rule_type}'. Treated as UNVERIFIED.")
        return res if return_note else res[0]

    if rule_type == "routing":
        res = (AnswerState.ROUTING, f"Routing selection: '{answer_value}' (excluded from score calculation)")
        return res if return_note else res[0]

    elif rule_type == "disclosed":
        res = (AnswerState.DISCLOSED, f"Recorded unscored disclosure: '{answer_value}'")
        return res if return_note else res[0]

    elif rule_type in ("bool", "boolean"):
        expected_bool = rule.get("pass_when", rule.get("value", True))
        if isinstance(answer_value, bool):
            actual_bool = answer_value
        else:
            val_str = str(answer_value).strip().lower()
            if val_str in ("yes", "true", "1", "pass", "compliant"):
                actual_bool = True
            elif val_str in ("no", "false", "0", "fail", "non-compliant"):
                actual_bool = False
            else:
                res = (AnswerState.UNVERIFIED, f"Unrecognized boolean value '{answer_value}'")
                return res if return_note else res[0]

        is_pass = (actual_bool == expected_bool)
        state = AnswerState.PASS if is_pass else AnswerState.FAIL
        note = f"Expected {expected_bool}, got {actual_bool}"
        return (state, note) if return_note else state

    elif rule_type == "choice":
        pass_vals = [str(v).strip().lower() for v in rule.get("pass_values", [])]
        fail_vals = [str(v).strip().lower() for v in rule.get("fail_values", [])]
        partial_vals = [str(v).strip().lower() for v in rule.get("partial_values", [])]

        if not pass_vals and not fail_vals and not partial_vals:
            res = (AnswerState.UNVERIFIED, "Malformed choice pass_rule: no pass_values, fail_values, or partial_values defined")
            return res if return_note else res[0]

        if isinstance(answer_value, bool):
            ans_str = "yes" if answer_value else "no"
        else:
            ans_str = str(answer_value).strip().lower()

        if ans_str in pass_vals:
            return (AnswerState.PASS, f"Choice '{ans_str}' matches pass_values") if return_note else AnswerState.PASS
        if ans_str in partial_vals:
            return (AnswerState.PARTIAL, f"Choice '{ans_str}' matches partial_values") if return_note else AnswerState.PARTIAL
        if ans_str in fail_vals:
            return (AnswerState.FAIL, f"Choice '{ans_str}' matches fail_values") if return_note else AnswerState.FAIL

        # Unrecognized choice answers return UNVERIFIED, consistent with all other rule types
        return (AnswerState.UNVERIFIED, f"Choice '{ans_str}' is unrecognized; expected one of pass/partial/fail options") if return_note else AnswerState.UNVERIFIED

    elif rule_type == "threshold":
        try:
            num = float(answer_value)
        except (ValueError, TypeError):
            res = (AnswerState.UNVERIFIED, f"Non-numeric answer '{answer_value}' for threshold rule")
            return res if return_note else res[0]

        op = rule.get("op", "gte")
        val_raw = rule.get("value")
        if val_raw is None:
            res = (AnswerState.UNVERIFIED, "Malformed threshold pass_rule: missing 'value'")
            return res if return_note else res[0]
        try:
            target = float(val_raw)
        except (ValueError, TypeError):
            res = (AnswerState.UNVERIFIED, f"Malformed threshold pass_rule: invalid target '{val_raw}'")
            return res if return_note else res[0]

        # Check main pass threshold
        passed = _eval_numeric_op(num, op, target)
        if passed:
            return (AnswerState.PASS, f"{num} {op} {target}") if return_note else AnswerState.PASS

        # Check partial threshold if present
        partial_spec = rule.get("partial")
        if partial_spec and isinstance(partial_spec, dict):
            p_op = partial_spec.get("op", op)
            try:
                p_target = float(partial_spec.get("value", 0))
                if _eval_numeric_op(num, p_op, p_target):
                    return (AnswerState.PARTIAL, f"{num} meets partial {p_op} {p_target}") if return_note else AnswerState.PARTIAL
            except (ValueError, TypeError):
                pass

        return (AnswerState.FAIL, f"{num} failed threshold {op} {target}") if return_note else AnswerState.FAIL

    elif rule_type == "self_attested":
        ans_str = str(answer_value).strip().lower()
        if ans_str in ("yes", "true", "1", "compliant", "complete", "pass"):
            return (AnswerState.PASS, "Self-attested compliant") if return_note else AnswerState.PASS
        if ans_str in ("no", "false", "0", "non-compliant", "incomplete", "fail"):
            return (AnswerState.FAIL, "Self-attested non-compliant") if return_note else AnswerState.FAIL
        # Arbitrary text, numbers, or percentages must NEVER return PASS
        res = (AnswerState.UNVERIFIED, f"Self-attested answer '{answer_value}' is not a recognized binary affirmation/denial; treated as UNVERIFIED")
        return res if return_note else res[0]

    # Explicit fallback: NEVER return PASS on unrecognized rules
    res = (AnswerState.UNVERIFIED, f"Unrecognized fallback for rule {rule}. Treated as UNVERIFIED.")
    return res if return_note else res[0]


def _eval_numeric_op(num: float, op: str, target: float) -> bool:
    if op == "gte":
        return num >= target
    elif op == "lte":
        return num <= target
    elif op == "gt":
        return num > target
    elif op == "lt":
        return num < target
    elif op == "eq":
        return num == target
    return False
