"""
Core Diligence Remediation Roadmap & Re-assessment Delta Engine (PRD Section 9.1 & 9.3).
Pure functions for:
1. Roadmap task generation & horizon bucket assignment (30/60/90/180)
2. Priority score ordering: weight x points_lost descending
3. Root-cause clustering by dimension + sub_category
4. Re-assessment delta & flipped items tracking
"""
from typing import Dict, Any, List, Optional
from apps.api.core.pass_rules import evaluate_pass_rule, AnswerState
from apps.api.core.scoring import load_scoring_config, DEFAULT_SEVERITY_WEIGHTS

VALID_HORIZONS = [30, 60, 90, 180]


def normalize_horizon(val: Any) -> int:
    """Clamps or maps remediation horizon to 30, 60, 90, or 180 days."""
    try:
        n = int(val)
        if n in VALID_HORIZONS:
            return n
        # Map to closest bucket
        return min(VALID_HORIZONS, key=lambda x: abs(x - n))
    except (ValueError, TypeError):
        return 90


def generate_roadmap_tasks_data(
    applicable_questions: List[Dict[str, Any]],
    answers: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generates remediation roadmap tasks from applicable questions (PRD Section 9.1).

    Criteria:
    - One task per FAIL question
    - One task per PARTIAL question
    - One task per CRITICAL UNVERIFIED question
    - Bucketed by remediation_horizon_days (30, 60, 90, 180)
    - Ordered within each bucket by weight x points_lost descending
    - Grouped by root cause (dimension + sub_category)
    - Playbook text derived ONLY from question.remediation_action (NO LLM text generation)
    """
    if config is None:
        config = load_scoring_config()

    severity_weights = config.get("severity_weights", DEFAULT_SEVERITY_WEIGHTS)
    partial_multiplier = float(config.get("partial_score_multiplier", 0.5))

    buckets: Dict[int, List[Dict[str, Any]]] = {30: [], 60: [], 90: [], 180: []}
    all_tasks: List[Dict[str, Any]] = []

    for q in applicable_questions:
        qid = q.get("question_id")
        dim = q.get("dimension", "OTHER")
        sub_cat = q.get("sub_category") or "General"
        risk_weight = (q.get("risk_weight") or "MEDIUM").upper()
        w_q = float(severity_weights.get(risk_weight, 3.0))

        # Extract answer value
        ans_entry = answers.get(qid)
        ans_val = ans_entry.get("value") if isinstance(ans_entry, dict) else ans_entry

        state = evaluate_pass_rule(q.get("pass_rule"), ans_val)

        # Inclusion condition per PRD 9.1: FAIL, PARTIAL, or CRITICAL UNVERIFIED
        is_fail = (state == AnswerState.FAIL)
        is_partial = (state == AnswerState.PARTIAL)
        is_critical_unverified = (state == AnswerState.UNVERIFIED and risk_weight == "CRITICAL")

        if not (is_fail or is_partial or is_critical_unverified):
            continue

        if is_fail:
            s_q = 0.0
            trigger_reason = "FAIL"
        elif is_partial:
            s_q = partial_multiplier
            trigger_reason = "PARTIAL"
        else:
            s_q = 0.0
            trigger_reason = "CRITICAL_UNVERIFIED"

        points_lost = round(w_q * (1.0 - s_q), 2)
        priority_score = round(w_q * points_lost, 2)  # weight x points lost

        horizon = normalize_horizon(q.get("remediation_horizon_days", 90))

        # Playbook text strictly from question bank
        action_text = (q.get("remediation_action") or "").strip()
        if not action_text:
            action_text = f"Address diligence verification requirement: {q.get('question_text', '')}"

        # Clean title
        title = action_text.split(".")[0].strip() if action_text else f"Remediate {qid}"
        if len(title) > 90:
            title = title[:87] + "..."

        task = {
            "question_id": qid,
            "title": title,
            "description": action_text,
            "dimension": dim,
            "sub_category": sub_cat,
            "horizon_days": horizon,
            "risk_weight": risk_weight,
            "weight_value": w_q,
            "points_recoverable": points_lost,
            "priority_score": priority_score,
            "trigger_reason": trigger_reason,
            "source_doc": q.get("source_doc") or "",
            "source_ref": q.get("source_ref") or "",
            "status": "todo",
            "assignee": None,
            "comments": []
        }

        buckets[horizon].append(task)
        all_tasks.append(task)

    # Order within each bucket by weight x points_lost descending
    for h in VALID_HORIZONS:
        buckets[h].sort(key=lambda t: (t["priority_score"], t["weight_value"], t["question_id"]), reverse=True)

    # Group tasks sharing dimension + sub_category (PRD 9.1: Root cause clustering)
    groups_dict: Dict[str, Dict[str, Any]] = {}
    for t in all_tasks:
        key = f"{t['dimension']}::{t['sub_category']}"
        if key not in groups_dict:
            groups_dict[key] = {
                "group_key": key,
                "dimension": t["dimension"],
                "sub_category": t["sub_category"],
                "tasks": [],
                "total_points_recoverable": 0.0,
                "task_count": 0
            }
        groups_dict[key]["tasks"].append(t)
        groups_dict[key]["total_points_recoverable"] = round(groups_dict[key]["total_points_recoverable"] + t["points_recoverable"], 2)
        groups_dict[key]["task_count"] += 1

    sorted_groups = sorted(groups_dict.values(), key=lambda g: g["total_points_recoverable"], reverse=True)

    total_pts = round(sum(t["points_recoverable"] for t in all_tasks), 2)
    crit_count = sum(1 for t in all_tasks if t["risk_weight"] == "CRITICAL")

    return {
        "buckets": {
            30: buckets[30],
            60: buckets[60],
            90: buckets[90],
            180: buckets[180]
        },
        "groups": sorted_groups,
        "summary": {
            "total_tasks": len(all_tasks),
            "total_points_recoverable": total_pts,
            "critical_tasks_count": crit_count,
            "by_horizon": {h: len(buckets[h]) for h in VALID_HORIZONS}
        }
    }


def compute_reassessment_delta(
    current_run: Dict[str, Any],
    previous_run: Optional[Dict[str, Any]] = None,
    current_answers: Optional[Dict[str, Any]] = None,
    previous_answers: Optional[Dict[str, Any]] = None,
    questions_by_id: Optional[Dict[str, Any]] = None,
    current_trace_rows: Optional[List[Dict[str, Any]]] = None,
    previous_trace_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Computes delta between two score runs (PRD Section 9.3).
    - Per-dimension change
    - Which items flipped from FAIL to PASS
    - Overall readiness movement
    """
    if not previous_run:
        # Initial run has zero delta
        return {
            "is_initial_assessment": True,
            "overall_score_delta": 0.0,
            "unconstrained_score_delta": 0.0,
            "completeness_delta": 0.0,
            "critical_cap_status": {
                "previous_capped": False,
                "current_capped": bool(current_run.get("critical_cap_applied", False)),
                "cap_lifted": False,
                "cap_imposed": False
            },
            "dimension_deltas": [],
            "flipped_items": [],
            "total_flipped_to_pass": 0,
            "current_run_id": current_run.get("id"),
            "previous_run_id": None
        }

    c_overall = float(current_run.get("overall_score", 0.0))
    p_overall = float(previous_run.get("overall_score", 0.0))
    overall_delta = round(c_overall - p_overall, 2)

    c_unconstrained = float(current_run.get("unconstrained_score", 0.0))
    p_unconstrained = float(previous_run.get("unconstrained_score", 0.0))
    unconstrained_delta = round(c_unconstrained - p_unconstrained, 2)

    c_comp = float(current_run.get("completeness", {}).get("completeness_pct", current_run.get("completeness_pct", 0.0)))
    p_comp = float(previous_run.get("completeness", {}).get("completeness_pct", previous_run.get("completeness_pct", 0.0)))
    comp_delta = round(c_comp - p_comp, 1)

    c_cap = bool(current_run.get("critical_cap_applied", False))
    p_cap = bool(previous_run.get("critical_cap_applied", False))
    cap_lifted = (p_cap and not c_cap)
    cap_imposed = (not p_cap and c_cap)

    # Dimension Deltas
    c_dims = current_run.get("dimension_scores", {})
    p_dims = previous_run.get("dimension_scores", {})
    all_dim_keys = list(dict.fromkeys(list(c_dims.keys()) + list(p_dims.keys())))

    dim_deltas = []
    for d in all_dim_keys:
        c_item = c_dims.get(d, {})
        p_item = p_dims.get(d, {})

        c_val = c_item.get("score") if isinstance(c_item, dict) else None
        p_val = p_item.get("score") if isinstance(p_item, dict) else None

        if c_val is not None and p_val is not None:
            d_delta = round(c_val - p_val, 2)
        elif c_val is not None:
            d_delta = round(c_val, 2)
        else:
            d_delta = 0.0

        dim_deltas.append({
            "dimension": d,
            "current_score": c_val,
            "previous_score": p_val,
            "delta": d_delta
        })

    dim_deltas.sort(key=lambda x: abs(x["delta"]), reverse=True)

    # Flipped Items Tracking
    # Compare state of each question between previous and current
    flipped_items = []
    if current_answers and previous_answers and questions_by_id:
        for qid, q in questions_by_id.items():
            p_ans = previous_answers.get(qid)
            c_ans = current_answers.get(qid)

            p_val = p_ans.get("value") if isinstance(p_ans, dict) else p_ans
            c_val = c_ans.get("value") if isinstance(c_ans, dict) else c_ans

            p_state = evaluate_pass_rule(q.get("pass_rule"), p_val)
            c_state = evaluate_pass_rule(q.get("pass_rule"), c_val)

            if p_state != c_state:
                flipped_to_pass = (p_state in (AnswerState.FAIL, AnswerState.PARTIAL, AnswerState.UNVERIFIED) and c_state == AnswerState.PASS)
                flipped_to_fail = (p_state == AnswerState.PASS and c_state in (AnswerState.FAIL, AnswerState.PARTIAL))

                w_q = float(DEFAULT_SEVERITY_WEIGHTS.get((q.get("risk_weight") or "MEDIUM").upper(), 3.0))

                flipped_items.append({
                    "question_id": qid,
                    "question_text": q.get("question_text", ""),
                    "dimension": q.get("dimension", ""),
                    "previous_state": p_state.value,
                    "current_state": c_state.value,
                    "flipped_to_pass": flipped_to_pass,
                    "flipped_to_fail": flipped_to_fail,
                    "points_recovered": w_q if flipped_to_pass else 0.0,
                    "source_doc": q.get("source_doc", ""),
                    "source_ref": q.get("source_ref", "")
                })
    elif previous_trace_rows is not None and current_trace_rows is not None:
        p_trace_map = {r["question_id"]: r for r in previous_trace_rows}
        c_trace_map = {r["question_id"]: r for r in current_trace_rows}

        # Check items that were in previous trace (deductions)
        for qid, p_row in p_trace_map.items():
            p_state = p_row.get("answer_state", "FAIL")
            c_row = c_trace_map.get(qid)
            if not c_row:
                # Deduction disappeared -> resolved and flipped to PASS!
                flipped_items.append({
                    "question_id": qid,
                    "question_text": p_row.get("question_text", ""),
                    "dimension": p_row.get("dimension", ""),
                    "previous_state": p_state,
                    "current_state": "PASS",
                    "flipped_to_pass": True,
                    "flipped_to_fail": False,
                    "points_recovered": float(p_row.get("points_lost", 0.0)),
                    "source_doc": p_row.get("source_doc", ""),
                    "source_ref": p_row.get("source_ref", "")
                })
            else:
                c_state = c_row.get("answer_state", "FAIL")
                if p_state != c_state:
                    is_to_pass = (c_state == "PASS")
                    flipped_items.append({
                        "question_id": qid,
                        "question_text": p_row.get("question_text", ""),
                        "dimension": p_row.get("dimension", ""),
                        "previous_state": p_state,
                        "current_state": c_state,
                        "flipped_to_pass": is_to_pass,
                        "flipped_to_fail": (not is_to_pass and p_state == "PASS"),
                        "points_recovered": float(p_row.get("points_lost", 0.0)) - float(c_row.get("points_lost", 0.0)) if is_to_pass else 0.0,
                        "source_doc": p_row.get("source_doc", ""),
                        "source_ref": p_row.get("source_ref", "")
                    })

        # Check items newly appearing in current trace (flipped to fail)
        for qid, c_row in c_trace_map.items():
            if qid not in p_trace_map:
                c_state = c_row.get("answer_state", "FAIL")
                if c_state in ("FAIL", "PARTIAL"):
                    flipped_items.append({
                        "question_id": qid,
                        "question_text": c_row.get("question_text", ""),
                        "dimension": c_row.get("dimension", ""),
                        "previous_state": "PASS",
                        "current_state": c_state,
                        "flipped_to_pass": False,
                        "flipped_to_fail": True,
                        "points_recovered": 0.0,
                        "source_doc": c_row.get("source_doc", ""),
                        "source_ref": c_row.get("source_ref", "")
                    })

    return {
        "is_initial_assessment": False,
        "overall_score_delta": overall_delta,
        "unconstrained_score_delta": unconstrained_delta,
        "completeness_delta": comp_delta,
        "critical_cap_status": {
            "previous_capped": p_cap,
            "current_capped": c_cap,
            "cap_lifted": cap_lifted,
            "cap_imposed": cap_imposed
        },
        "dimension_deltas": dim_deltas,
        "flipped_items": flipped_items,
        "total_flipped_to_pass": sum(1 for f in flipped_items if f["flipped_to_pass"]),
        "current_run_id": current_run.get("id"),
        "previous_run_id": previous_run.get("id")
    }
