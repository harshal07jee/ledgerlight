"""
Dependency parser and evaluation engine (PRD Section 6.4).
Supports:
- Legacy string parsing (e.g. 'MED_DEV_01:Class II', 'NONE') -> structured JSON
- Conditional operations: 'eq', 'neq', 'in', 'gte', 'lte', 'answered'
- Logical operators: 'all', 'any', nested groups
- Chained dependencies: question applicable only if condition met AND parent is applicable
- Company-level profile gating (industry, sub_sector, stage, geography)
"""
from typing import Dict, Any, Optional, Set, List, Union


def parse_legacy_depends_on(raw: Optional[Union[str, Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """
    Parses a legacy string like 'MED_DEV_01:Class II' or 'MED_DEV_CYBER_01:Yes'
    into canonical JSON:
    { 'all': [ { 'question_id': 'MED_DEV_01', 'op': 'eq', 'value': 'Class II' } ] }
    """
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw

    s = str(raw).strip()
    if not s or s.upper() in ("NONE", "NULL", "N/A", "NO_DEPENDENCY"):
        return None

    # Handle multiple comma-separated or semicolon-separated dependencies
    parts = [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
    conditions = []

    for part in parts:
        if ":" in part:
            qid, expected = part.split(":", 1)
            qid = qid.strip()
            expected = expected.strip()

            # Handle comma/pipe-separated multiple acceptable values
            if "|" in expected:
                vals = [v.strip() for v in expected.split("|")]
                conditions.append({"question_id": qid, "op": "in", "value": vals})
            else:
                # Type cast boolean strings if obvious
                val: Union[str, bool] = expected
                if expected.lower() == "yes":
                    val = "Yes"
                elif expected.lower() == "no":
                    val = "No"
                conditions.append({"question_id": qid, "op": "eq", "value": val})
        else:
            # Standalone question ID means it just needs to be answered / truthy
            conditions.append({"question_id": part.strip(), "op": "answered", "value": True})

    if not conditions:
        return None

    return {"all": conditions}


def evaluate_single_condition(cond: Dict[str, Any], answers: Dict[str, Any]) -> bool:
    """Evaluates a single condition dictionary against the answers map."""
    qid = cond.get("question_id")
    op = cond.get("op", "eq").lower()
    target_val = cond.get("value")

    if not qid:
        return True

    ans = answers.get(qid)

    if op == "answered":
        return ans is not None and ans != ""

    if ans is None:
        return False

    if op == "eq":
        # Compare strings case-insensitively if strings, or direct equality
        if isinstance(ans, str) and isinstance(target_val, str):
            return ans.strip().lower() == target_val.strip().lower()
        return ans == target_val

    elif op == "neq":
        if isinstance(ans, str) and isinstance(target_val, str):
            return ans.strip().lower() != target_val.strip().lower()
        return ans != target_val

    elif op == "in":
        target_list = target_val if isinstance(target_val, list) else [target_val]
        if isinstance(ans, str):
            lowered_ans = ans.strip().lower()
            return any(lowered_ans == str(t).strip().lower() for t in target_list)
        return ans in target_list

    elif op == "gte":
        try:
            return float(ans) >= float(target_val)
        except (ValueError, TypeError):
            return False

    elif op == "lte":
        try:
            return float(ans) <= float(target_val)
        except (ValueError, TypeError):
            return False

    return False


def evaluate_condition_group(group: Dict[str, Any], answers: Dict[str, Any]) -> bool:
    """Recursively evaluates 'all' or 'any' groups."""
    if not group:
        return True

    if "all" in group:
        sub_conds = group["all"]
        return all(
            evaluate_condition_group(c, answers) if isinstance(c, dict) and ("all" in c or "any" in c)
            else evaluate_single_condition(c, answers)
            for c in sub_conds
        )

    if "any" in group:
        sub_conds = group["any"]
        return any(
            evaluate_condition_group(c, answers) if isinstance(c, dict) and ("all" in c or "any" in c)
            else evaluate_single_condition(c, answers)
            for c in sub_conds
        )

    # Fallback if a single condition was passed without group wrapper
    return evaluate_single_condition(group, answers)


def is_question_applicable(
    question: Dict[str, Any],
    company_profile: Dict[str, Any],
    answers: Dict[str, Any],
    all_questions_by_id: Dict[str, Dict[str, Any]],
    visited: Optional[Set[str]] = None
) -> bool:
    """
    Determines whether a question is applicable based on:
    1. Company profile gating (industry, sub_sector, stage, geography)
    2. depends_on logic
    3. Chained parent dependency (parent question must itself be applicable)
    """
    qid = question.get("question_id")
    if visited is None:
        visited = set()

    if qid in visited:
        # Prevent infinite recursion in case of cyclic dependencies
        return False
    visited.add(qid)

    # 1. Company profile gating
    scope = question.get("scope", "BRANCH")
    q_industry = (question.get("industry") or "").upper()
    prof_industry = (company_profile.get("industry") or "").upper()

    if scope == "BRANCH":
        if q_industry not in ("UNIVERSAL", "ALL", "") and q_industry != prof_industry:
            return False

    # Sub-sector gating
    q_sub = (question.get("sub_sector") or "ALL").upper()
    prof_sub = (company_profile.get("sub_sector") or "ALL").upper()
    if q_sub not in ("ALL", "", "UNIVERSAL") and prof_sub not in ("ALL", ""):
        if q_sub != prof_sub:
            return False

    # Stage gating
    q_stages = [s.upper() for s in question.get("stage", ["ALL"])]
    prof_stage = (company_profile.get("stage") or "ALL").upper()
    if "ALL" not in q_stages and prof_stage not in ("ALL", ""):
        if prof_stage not in q_stages:
            return False

    # Geography gating
    q_geos = [g.upper() for g in question.get("geography", ["USA"])]
    raw_prof_geo = company_profile.get("geography") or ["USA"]
    if isinstance(raw_prof_geo, str):
        prof_geos = [raw_prof_geo.upper()]
    else:
        prof_geos = [g.upper() for g in raw_prof_geo]

    if "UNIVERSAL" not in q_geos and "ALL" not in q_geos:
        if not any(g in q_geos for g in prof_geos):
            return False

    # 2. Dependency logic
    raw_dep = question.get("depends_on")
    if not raw_dep:
        return True

    dep_group = parse_legacy_depends_on(raw_dep) if isinstance(raw_dep, str) else raw_dep
    if not dep_group:
        return True

    # 3. Check chained parent applicability
    # For every condition referenced in dep_group, verify that the parent question is applicable
    parent_qids = extract_referenced_qids(dep_group)
    for parent_qid in parent_qids:
        parent_q = all_questions_by_id.get(parent_qid)
        if parent_q:
            parent_applicable = is_question_applicable(
                parent_q,
                company_profile,
                answers,
                all_questions_by_id,
                visited.copy()
            )
            if not parent_applicable:
                return False

    # Evaluate the conditions against answers
    return evaluate_condition_group(dep_group, answers)


def extract_referenced_qids(group: Any) -> List[str]:
    """Extracts all question IDs referenced in a condition tree."""
    qids = []
    if not isinstance(group, dict):
        return qids

    if "question_id" in group:
        qids.append(group["question_id"])

    for sub in group.get("all", []):
        qids.extend(extract_referenced_qids(sub))
    for sub in group.get("any", []):
        qids.extend(extract_referenced_qids(sub))

    return list(dict.fromkeys(qids))
