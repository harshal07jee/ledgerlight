"""
Pure, deterministic Diligence Readiness Scoring Engine (PRD Section 8).
Calculates:
- Dimension scores: DimScore_d = 100 * sum(w_q * s_q) / sum(w_q) over answered applicable questions
- Overall score: Overall = sum(W[txn_type][d] * DimScore_d) / sum(W[txn_type][d])
- Critical-fail cap: if any CRITICAL question is FAIL, overall score capped at ceiling (default 60)
- Evidence completeness & Provisional badge (< 60%)
- Explanatory deduction trace rows (Why this score)

CRITICAL: This module contains PURE mathematical functions with NO database or network calls.
"""
import json
import os
from typing import Dict, Any, List, Optional, Tuple, Union
from apps.api.core.pass_rules import evaluate_pass_rule, AnswerState

DEFAULT_SEVERITY_WEIGHTS = {
    "CRITICAL": 8.0,
    "HIGH": 5.0,
    "MEDIUM": 3.0,
    "LOW": 1.0
}

DEFAULT_PARTIAL_MULTIPLIER = 0.5
DEFAULT_CRITICAL_FAIL_CAP = 60.0
DEFAULT_PROVISIONAL_THRESHOLD = 60.0
DEFAULT_CONFIG_VERSION = "1.0.0"
DEFAULT_QB_VERSION = "1.0.0"

DEFAULT_TRANSACTION_MATRICES = {
    "VC_GROWTH_FINANCING": {
        "GOVERNANCE": 10.0,
        "FIN_CONTROLS": 10.0,
        "LEGAL_IP_REG": 15.0,
        "OPS_TECH_CYBER": 10.0,
        "HUMAN_CAPITAL": 5.0,
        "TXN_READINESS": 10.0,
        "FIN_PERFORMANCE": 15.0,
        "PROFIT_CASHFLOW": 10.0,
        "REVENUE_QUALITY": 10.0,
        "MGMT_DEPTH": 5.0,
        "CUSTOMER_MARKET": 5.0,
        "INDUSTRY_REG": 10.0
    },
    "M&A_SELL_SIDE": {
        "GOVERNANCE": 15.0,
        "FIN_CONTROLS": 15.0,
        "LEGAL_IP_REG": 20.0,
        "OPS_TECH_CYBER": 10.0,
        "HUMAN_CAPITAL": 10.0,
        "TXN_READINESS": 15.0,
        "FIN_PERFORMANCE": 10.0,
        "PROFIT_CASHFLOW": 10.0,
        "REVENUE_QUALITY": 10.0,
        "MGMT_DEPTH": 5.0,
        "CUSTOMER_MARKET": 5.0,
        "INDUSTRY_REG": 15.0
    },
    "IPO_PREP": {
        "GOVERNANCE": 20.0,
        "FIN_CONTROLS": 20.0,
        "LEGAL_IP_REG": 15.0,
        "OPS_TECH_CYBER": 10.0,
        "HUMAN_CAPITAL": 10.0,
        "TXN_READINESS": 15.0,
        "FIN_PERFORMANCE": 15.0,
        "PROFIT_CASHFLOW": 10.0,
        "REVENUE_QUALITY": 10.0,
        "MGMT_DEPTH": 10.0,
        "CUSTOMER_MARKET": 5.0,
        "INDUSTRY_REG": 15.0
    },
    "DEBT_FINANCING": {
        "GOVERNANCE": 10.0,
        "FIN_CONTROLS": 20.0,
        "LEGAL_IP_REG": 10.0,
        "OPS_TECH_CYBER": 5.0,
        "HUMAN_CAPITAL": 5.0,
        "TXN_READINESS": 10.0,
        "FIN_PERFORMANCE": 15.0,
        "PROFIT_CASHFLOW": 25.0,
        "REVENUE_QUALITY": 15.0,
        "MGMT_DEPTH": 5.0,
        "CUSTOMER_MARKET": 5.0,
        "INDUSTRY_REG": 10.0
    }
}


def load_scoring_config(custom_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Loads versioned scoring config from JSON file.
    Falls back to built-in defaults if file cannot be read.
    """
    candidates = [
        custom_path,
        os.path.join("packages", "schema", "config", "scoring_config_v1.json"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "schema", "config", "scoring_config_v1.json"))
    ]
    for p in candidates:
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

    return {
        "config_version": DEFAULT_CONFIG_VERSION,
        "severity_weights": DEFAULT_SEVERITY_WEIGHTS,
        "partial_score_multiplier": DEFAULT_PARTIAL_MULTIPLIER,
        "critical_fail_cap": DEFAULT_CRITICAL_FAIL_CAP,
        "provisional_threshold_pct": DEFAULT_PROVISIONAL_THRESHOLD,
        "transaction_matrices": DEFAULT_TRANSACTION_MATRICES
    }


def describe_expected_rule(rule: Optional[Dict[str, Any]]) -> str:
    """Formats a concise human-readable summary of what the pass rule expects."""
    if not rule:
        return "Compliant (Yes/True)"

    rule_type = rule.get("type", "bool")
    if rule_type == "bool":
        pass_when = rule.get("pass_when", True)
        return "Compliant (Yes/True)" if pass_when else "Compliant (No / Absence of violation)"
    elif rule_type == "choice":
        pass_vals = rule.get("pass_values", [])
        return f"One of: {', '.join(str(v) for v in pass_vals)}" if pass_vals else "Approved selection"
    elif rule_type == "threshold":
        op = rule.get("op", "gte")
        sym = ">=" if op == "gte" else "<=" if op == "lte" else ">" if op == "gt" else "<" if op == "lt" else "=="
        val = rule.get("value")
        field = rule.get("field", "metric")
        partial = rule.get("partial")
        if partial:
            p_op = partial.get("op", op)
            p_sym = ">=" if p_op == "gte" else "<=" if p_op == "lte" else ">" if p_op == "gt" else "<" if p_op == "lt" else "=="
            p_val = partial.get("value")
            return f"{sym} {val} ({field}) [partial: {p_sym} {p_val}]"
        return f"{sym} {val} ({field})"
    elif rule_type == "self_attested":
        return "Self-attested compliant response"
    elif rule_type == "routing":
        return "Routing selection (excluded from scoring)"
    elif rule_type == "disclosed":
        return "Unscored disclosure (recorded in report)"

    return "Compliant response"


def is_scorable_question(q: Dict[str, Any]) -> bool:
    """Returns True if a question is subject to scoring (not routing or disclosed)."""
    rule = q.get("pass_rule")
    if isinstance(rule, dict):
        r_type = str(rule.get("type", "")).strip().lower()
        if r_type in ("routing", "disclosed"):
            return False
    return True


def compute_readiness_score(
    applicable_questions: List[Dict[str, Any]],
    answers: Dict[str, Any],
    company_profile: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Pure, deterministic scoring function (PRD Section 8).

    Inputs:
    - applicable_questions: List of question dictionaries applicable to assessment
    - answers: Map of question_id -> answer value (or answer dict with metadata)
    - company_profile: Dict containing transaction_type, industry, etc.
    - config: Dict containing severity_weights, transaction_matrices, critical_fail_cap, etc.

    Outputs:
    - overall_score: float (0.0 - 100.0)
    - unconstrained_score: float (score prior to critical-fail ceiling)
    - critical_cap_applied: bool
    - failed_critical_items: List of failed critical question dictionaries
    - dimension_scores: Dict of per-dimension metrics & scores
    - completeness: Dict of total, answered, completeness_pct, is_provisional
    - trace_rows: List of deduction rows explaining points lost
    - weight_origin_share: Dict of self-attested vs evidence-backed weight breakdown
    - unscored_disclosures: List of disclosed question responses
    - config_version: str
    - question_bank_version: str
    """
    if config is None:
        config = load_scoring_config()

    severity_weights = config.get("severity_weights", DEFAULT_SEVERITY_WEIGHTS)
    partial_multiplier = float(config.get("partial_score_multiplier", DEFAULT_PARTIAL_MULTIPLIER))
    critical_fail_cap = float(config.get("critical_fail_cap", DEFAULT_CRITICAL_FAIL_CAP))
    provisional_threshold = float(config.get("provisional_threshold_pct", DEFAULT_PROVISIONAL_THRESHOLD))
    transaction_matrices = config.get("transaction_matrices", DEFAULT_TRANSACTION_MATRICES)
    config_version = str(config.get("config_version", DEFAULT_CONFIG_VERSION))
    qb_version = str(config.get("question_bank_version", DEFAULT_QB_VERSION))

    txn_type = (company_profile.get("transaction_type") or "VC_GROWTH_FINANCING").upper()
    active_txn_matrix = transaction_matrices.get(txn_type, transaction_matrices.get("VC_GROWTH_FINANCING", {}))

    # 1. Evaluate answers and collect deductions & dimension accumulators
    dim_accumulators: Dict[str, Dict[str, Any]] = {}
    failed_critical_items: List[Dict[str, Any]] = []
    trace_rows: List[Dict[str, Any]] = []
    unscored_disclosures: List[Dict[str, Any]] = []
    self_attested_weight_sum: float = 0.0
    evidence_backed_weight_sum: float = 0.0

    total_applicable = len(applicable_questions)
    answered_applicable = 0

    for q in applicable_questions:
        qid = q.get("question_id")
        dim = q.get("dimension", "OTHER")
        risk_weight_str = (q.get("risk_weight") or "MEDIUM").upper()
        w_q = float(severity_weights.get(risk_weight_str, 3.0))

        if dim not in dim_accumulators:
            dim_accumulators[dim] = {
                "total_applicable": 0,
                "answered_count": 0,
                "earned_weight_sum": 0.0,
                "total_weight_sum": 0.0,
                "questions": []
            }
        dim_accumulators[dim]["total_applicable"] += 1

        # Extract answer value and metadata
        ans_entry = answers.get(qid)
        ans_val = None
        user_action = "manual"
        notes = None
        evidence_snippet = None

        if isinstance(ans_entry, dict) and "value" in ans_entry:
            ans_val = ans_entry.get("value")
            user_action = ans_entry.get("user_action", "manual")
            notes = ans_entry.get("notes")
            evidence_snippet = ans_entry.get("evidence_snippet")
        else:
            ans_val = ans_entry

        # Evaluate pass rule deterministically
        state = evaluate_pass_rule(q.get("pass_rule"), ans_val)

        # UNVERIFIED and unanswered questions are excluded from score calculation,
        # but counted in completeness, and NEVER treated as PASS.
        if state == AnswerState.UNVERIFIED or ans_val is None or ans_val == "":
            # Unanswered / unverified: skip from dimension score math
            continue

        # Handle ROUTING and DISCLOSED questions:
        # Never scored, never PASS/FAIL, but count toward completeness.
        if state in (AnswerState.ROUTING, AnswerState.DISCLOSED):
            answered_applicable += 1
            if state == AnswerState.DISCLOSED:
                unscored_disclosures.append({
                    "question_id": qid,
                    "question_text": q.get("question_text", ""),
                    "dimension": dim,
                    "input_type": q.get("input_type", ""),
                    "value": ans_val,
                    "notes": notes or f"Disclosed: {ans_val}"
                })
            continue

        # Answered applicable scored question
        answered_applicable += 1
        dim_accumulators[dim]["answered_count"] += 1

        # Track weight origin (self-attested vs evidence-backed)
        ev_type = str(q.get("evidence_type", "SELF_ATTESTED")).upper()
        rule_type = ""
        if isinstance(q.get("pass_rule"), dict):
            rule_type = str(q.get("pass_rule", {}).get("type", "")).lower()
        is_self_attested = (ev_type == "SELF_ATTESTED" or rule_type == "self_attested")
        origin = "self-attested" if is_self_attested else "evidence-backed"
        if is_self_attested:
            self_attested_weight_sum += w_q
        else:
            evidence_backed_weight_sum += w_q

        if state == AnswerState.PASS:
            s_q = 1.0
        elif state == AnswerState.PARTIAL:
            s_q = partial_multiplier
        else:  # FAIL
            s_q = 0.0

        dim_accumulators[dim]["earned_weight_sum"] += (w_q * s_q)
        dim_accumulators[dim]["total_weight_sum"] += w_q

        points_lost = round(w_q * (1.0 - s_q), 2)
        is_critical_fail = (risk_weight_str == "CRITICAL" and state == AnswerState.FAIL)

        if is_critical_fail:
            failed_critical_items.append({
                "question_id": qid,
                "question_text": q.get("question_text", ""),
                "dimension": dim,
                "risk_weight": risk_weight_str,
                "points_lost": points_lost,
                "source_doc": q.get("source_doc"),
                "source_ref": q.get("source_ref"),
                "origin": origin
            })

        # Deduction trace row (PRD Section 8.6: for every deduction the trace stores details)
        if points_lost > 0.0:
            trace_rows.append({
                "question_id": qid,
                "question_text": q.get("question_text", ""),
                "dimension": dim,
                "risk_weight": risk_weight_str,
                "weight_value": w_q,
                "answer_state": state.value,
                "user_answer": ans_val,
                "expected_rule": describe_expected_rule(q.get("pass_rule")),
                "points_lost": points_lost,
                "source_doc": q.get("source_doc") or "",
                "source_ref": q.get("source_ref") or "",
                "evidence_snippet": evidence_snippet or "",
                "answer_origin": user_action or "manual",
                "origin": origin,
                "evidence_type": ev_type,
                "notes": notes or "",
                "is_critical_fail": is_critical_fail
            })

    # Sort trace rows by points lost descending
    trace_rows.sort(key=lambda r: (r["points_lost"], r["weight_value"]), reverse=True)

    # 2. Compute per-dimension scores: DimScore_d = 100 * Σ(w_q * s_q) / Σ(w_q)
    dimension_scores: Dict[str, Dict[str, Any]] = {}
    weighted_dim_sum = 0.0
    active_txn_weight_sum = 0.0

    for dim, acc in dim_accumulators.items():
        ans_count = acc["answered_count"]
        tot_wt = acc["total_weight_sum"]
        earned_wt = acc["earned_weight_sum"]
        txn_dim_weight = float(active_txn_matrix.get(dim, 10.0))

        if ans_count > 0 and tot_wt > 0.0:
            score = round((100.0 * earned_wt / tot_wt), 2)
            dimension_scores[dim] = {
                "dimension": dim,
                "score": score,
                "answered_count": ans_count,
                "total_applicable": acc["total_applicable"],
                "earned_weight": round(earned_wt, 2),
                "total_weight": round(tot_wt, 2),
                "transaction_weight": txn_dim_weight
            }
            # Only include dimensions with >= 1 answered question in overall score
            weighted_dim_sum += (txn_dim_weight * score)
            active_txn_weight_sum += txn_dim_weight
        else:
            dimension_scores[dim] = {
                "dimension": dim,
                "score": None,  # Excluded from overall calculation
                "answered_count": 0,
                "total_applicable": acc["total_applicable"],
                "earned_weight": 0.0,
                "total_weight": 0.0,
                "transaction_weight": txn_dim_weight
            }

    # 3. Overall score: Overall = Σ( W[txn_type][d] × DimScore_d ) / Σ W[txn_type][d]
    if active_txn_weight_sum > 0.0:
        unconstrained_score = round(weighted_dim_sum / active_txn_weight_sum, 2)
    else:
        unconstrained_score = 0.0

    # 4. Critical-fail cap (PRD Section 8.4)
    # If any CRITICAL question is FAIL, cap overall score at critical_fail_cap (default 60)
    has_critical_fail = len(failed_critical_items) > 0
    if has_critical_fail:
        critical_cap_applied = True
        overall_score = min(unconstrained_score, critical_fail_cap)
    else:
        critical_cap_applied = False
        overall_score = unconstrained_score

    # 5. Best-Case and Worst-Case Scores
    # Best-case: unverified questions counted as PASS (s_q = 1.0)
    # Worst-case: unverified questions counted as FAIL (s_q = 0.0)
    best_weighted_sum = 0.0
    worst_weighted_sum = 0.0
    total_txn_weight_sum = 0.0
    has_unverified_critical = False

    for dim, acc in dim_accumulators.items():
        txn_dim_weight = float(active_txn_matrix.get(dim, 10.0))

        # Only scorable questions in this dimension
        scorable_qs = [
            q for q in applicable_questions
            if q.get("dimension", "OTHER") == dim and is_scorable_question(q)
        ]

        tot_applicable_wt = sum(
            float(severity_weights.get((q.get("risk_weight") or "MEDIUM").upper(), 3.0))
            for q in scorable_qs
        )

        unverified_wt = sum(
            float(severity_weights.get((q.get("risk_weight") or "MEDIUM").upper(), 3.0))
            for q in scorable_qs
            if (
                evaluate_pass_rule(q.get("pass_rule"), answers.get(q.get("question_id"), {}).get("value") if isinstance(answers.get(q.get("question_id")), dict) else answers.get(q.get("question_id"))) == AnswerState.UNVERIFIED
                or (answers.get(q.get("question_id"), {}).get("value") if isinstance(answers.get(q.get("question_id")), dict) else answers.get(q.get("question_id"))) is None
                or (answers.get(q.get("question_id"), {}).get("value") if isinstance(answers.get(q.get("question_id")), dict) else answers.get(q.get("question_id"))) == ""
            )
        )

        # Check if any unverified scorable question in this dimension is CRITICAL
        for q in scorable_qs:
            ans_v = answers.get(q.get("question_id"), {}).get("value") if isinstance(answers.get(q.get("question_id")), dict) else answers.get(q.get("question_id"))
            if ans_v is None or ans_v == "" or evaluate_pass_rule(q.get("pass_rule"), ans_v) == AnswerState.UNVERIFIED:
                if (q.get("risk_weight") or "").upper() == "CRITICAL":
                    has_unverified_critical = True

        if tot_applicable_wt > 0.0:
            best_earned_wt = acc["earned_weight_sum"] + (unverified_wt * 1.0)
            worst_earned_wt = acc["earned_weight_sum"] + (unverified_wt * 0.0)

            best_dim_score = round(100.0 * best_earned_wt / tot_applicable_wt, 2)
            worst_dim_score = round(100.0 * worst_earned_wt / tot_applicable_wt, 2)

            best_weighted_sum += (txn_dim_weight * best_dim_score)
            worst_weighted_sum += (txn_dim_weight * worst_dim_score)
            total_txn_weight_sum += txn_dim_weight

    if total_txn_weight_sum > 0.0:
        unconstrained_best = round(best_weighted_sum / total_txn_weight_sum, 2)
        unconstrained_worst = round(worst_weighted_sum / total_txn_weight_sum, 2)
    else:
        unconstrained_best = overall_score
        unconstrained_worst = overall_score

    # Apply critical cap to best and worst
    # Best case only capped if an already-answered CRITICAL failed
    best_case_score = min(unconstrained_best, critical_fail_cap) if has_critical_fail else unconstrained_best
    # Worst case capped if already-answered CRITICAL failed OR unverified CRITICAL failed
    worst_has_crit = has_critical_fail or has_unverified_critical
    worst_case_score = min(unconstrained_worst, critical_fail_cap) if worst_has_crit else unconstrained_worst

    # 6. Weight Origin Share (Self-attested vs Evidence-backed)
    total_scored_weight = self_attested_weight_sum + evidence_backed_weight_sum
    if total_scored_weight > 0.0:
        self_attested_share_pct = round((self_attested_weight_sum / total_scored_weight) * 100.0, 1)
        evidence_backed_share_pct = round((evidence_backed_weight_sum / total_scored_weight) * 100.0, 1)
    else:
        self_attested_share_pct = 0.0
        evidence_backed_share_pct = 0.0

    weight_origin_share = {
        "self_attested_weight": round(self_attested_weight_sum, 2),
        "evidence_backed_weight": round(evidence_backed_weight_sum, 2),
        "total_scored_weight": round(total_scored_weight, 2),
        "self_attested_share_pct": self_attested_share_pct,
        "evidence_backed_share_pct": evidence_backed_share_pct,
        "self_attested_pct": self_attested_share_pct,
        "evidence_backed_pct": evidence_backed_share_pct
    }

    # 7. Completeness & Provisional Flag (PRD Section 8.5)
    completeness_pct = round((answered_applicable / total_applicable * 100.0), 1) if total_applicable > 0 else 0.0
    is_provisional = completeness_pct < provisional_threshold

    return {
        "overall_score": overall_score,
        "unconstrained_score": unconstrained_score,
        "best_case_score": best_case_score,
        "worst_case_score": worst_case_score,
        "critical_cap_applied": critical_cap_applied,
        "critical_fail_cap": critical_fail_cap,
        "failed_critical_count": len(failed_critical_items),
        "failed_critical_items": failed_critical_items,
        "dimension_scores": dimension_scores,
        "completeness": {
            "total_applicable": total_applicable,
            "answered_count": answered_applicable,
            "unanswered_count": total_applicable - answered_applicable,
            "completeness_pct": completeness_pct,
            "is_provisional": is_provisional,
            "provisional_threshold_pct": provisional_threshold
        },
        "weight_origin_share": weight_origin_share,
        "unscored_disclosures": unscored_disclosures,
        "trace_rows": trace_rows,
        "total_deductions": len(trace_rows),
        "total_points_lost": round(sum(r["points_lost"] for r in trace_rows), 2),
        "transaction_type": txn_type,
        "config_version": config_version,
        "question_bank_version": qb_version
    }

