"""
Unit tests for Dependency Logic and Chained Evaluation (PRD Section 6.4 & M1 Acceptance).
"""
import pytest
from apps.api.core.dependencies import (
    parse_legacy_depends_on,
    evaluate_single_condition,
    evaluate_condition_group,
    is_question_applicable
)


def test_parse_legacy_depends_on_strings():
    # Single equality
    res1 = parse_legacy_depends_on("MED_DEV_01:Class II")
    assert res1 == {"all": [{"question_id": "MED_DEV_01", "op": "eq", "value": "Class II"}]}

    # Boolean yes
    res2 = parse_legacy_depends_on("MED_DEV_CYBER_01:Yes")
    assert res2 == {"all": [{"question_id": "MED_DEV_CYBER_01", "op": "eq", "value": "Yes"}]}

    # None / Empty
    assert parse_legacy_depends_on("NONE") is None
    assert parse_legacy_depends_on("") is None
    assert parse_legacy_depends_on(None) is None

    # Multi-value (in op)
    res3 = parse_legacy_depends_on("SAAS_01:B2B Enterprise SaaS|AI Infrastructure")
    assert res3 == {"all": [{"question_id": "SAAS_01", "op": "in", "value": ["B2B Enterprise SaaS", "AI Infrastructure"]}]}


def test_evaluate_single_condition_ops():
    answers = {"Q1": "Yes", "Q2": "No", "NUM": 12, "STR_NUM": "7.5"}

    # eq
    assert evaluate_single_condition({"question_id": "Q1", "op": "eq", "value": "Yes"}, answers) is True
    assert evaluate_single_condition({"question_id": "Q1", "op": "eq", "value": "No"}, answers) is False

    # neq
    assert evaluate_single_condition({"question_id": "Q2", "op": "neq", "value": "Yes"}, answers) is True

    # in
    assert evaluate_single_condition({"question_id": "Q1", "op": "in", "value": ["Yes", "Maybe"]}, answers) is True
    assert evaluate_single_condition({"question_id": "Q2", "op": "in", "value": ["Yes", "Maybe"]}, answers) is False

    # gte / lte
    assert evaluate_single_condition({"question_id": "NUM", "op": "gte", "value": 10}, answers) is True
    assert evaluate_single_condition({"question_id": "NUM", "op": "lte", "value": 5}, answers) is False
    assert evaluate_single_condition({"question_id": "STR_NUM", "op": "gte", "value": 7}, answers) is True

    # answered
    assert evaluate_single_condition({"question_id": "Q1", "op": "answered"}, answers) is True
    assert evaluate_single_condition({"question_id": "NON_EXISTENT", "op": "answered"}, answers) is False


def test_evaluate_nested_condition_groups():
    answers = {"Q1": "Yes", "Q2": "No", "Q3": "Gold"}

    # All pass
    all_group = {"all": [
        {"question_id": "Q1", "op": "eq", "value": "Yes"},
        {"question_id": "Q3", "op": "eq", "value": "Gold"}
    ]}
    assert evaluate_condition_group(all_group, answers) is True

    # Any pass
    any_group = {"any": [
        {"question_id": "Q2", "op": "eq", "value": "Yes"},
        {"question_id": "Q3", "op": "eq", "value": "Gold"}
    ]}
    assert evaluate_condition_group(any_group, answers) is True


def test_chained_dependencies_pass_and_fail():
    """
    Test scenario:
    - Q_GRANDPARENT (e.g. 'Does device contain software?')
    - Q_PARENT (e.g. 'Is device connected to cloud?' -> depends on Q_GRANDPARENT == 'Yes')
    - Q_CHILD (e.g. 'Is cloud communication TLS 1.3 encrypted?' -> depends on Q_PARENT == 'Yes')
    """
    all_q = {
        "Q_GP": {
            "question_id": "Q_GP",
            "scope": "BRANCH",
            "industry": "HEALTHCARE",
            "sub_sector": "ALL",
            "depends_on": None
        },
        "Q_P": {
            "question_id": "Q_P",
            "scope": "BRANCH",
            "industry": "HEALTHCARE",
            "sub_sector": "ALL",
            "depends_on": {"all": [{"question_id": "Q_GP", "op": "eq", "value": "Yes"}]}
        },
        "Q_C": {
            "question_id": "Q_C",
            "scope": "BRANCH",
            "industry": "HEALTHCARE",
            "sub_sector": "ALL",
            "depends_on": {"all": [{"question_id": "Q_P", "op": "eq", "value": "Yes"}]}
        }
    }
    profile = {"industry": "HEALTHCARE", "sub_sector": "ALL"}

    # Case 1: Both parent and grandparent answered Yes -> Child applicable
    answers_valid = {"Q_GP": "Yes", "Q_P": "Yes"}
    assert is_question_applicable(all_q["Q_C"], profile, answers_valid, all_q) is True

    # Case 2: Parent answered No -> Child NOT applicable
    answers_parent_no = {"Q_GP": "Yes", "Q_P": "No"}
    assert is_question_applicable(all_q["Q_C"], profile, answers_parent_no, all_q) is False

    # Case 3: Grandparent answered No -> Parent is not applicable -> Child is NOT applicable!
    answers_gp_no = {"Q_GP": "No", "Q_P": "Yes"}
    assert is_question_applicable(all_q["Q_P"], profile, answers_gp_no, all_q) is False
    assert is_question_applicable(all_q["Q_C"], profile, answers_gp_no, all_q) is False


def test_cyclic_dependency_protection():
    """Verify that circular dependency loops return False safely without hanging."""
    all_q = {
        "Q_LOOP_A": {
            "question_id": "Q_LOOP_A",
            "depends_on": {"all": [{"question_id": "Q_LOOP_B", "op": "eq", "value": "Yes"}]}
        },
        "Q_LOOP_B": {
            "question_id": "Q_LOOP_B",
            "depends_on": {"all": [{"question_id": "Q_LOOP_A", "op": "eq", "value": "Yes"}]}
        }
    }
    profile = {}
    answers = {"Q_LOOP_A": "Yes", "Q_LOOP_B": "Yes"}
    assert is_question_applicable(all_q["Q_LOOP_A"], profile, answers, all_q) is False


def test_company_profile_gating():
    q_healthcare = {
        "question_id": "Q_MED",
        "scope": "BRANCH",
        "industry": "HEALTHCARE",
        "sub_sector": "MEDICAL_DEVICES",
        "stage": ["STARTUP", "GROWTH"],
        "geography": ["USA"],
        "depends_on": None
    }
    all_q = {"Q_MED": q_healthcare}

    # Matching profile
    prof_match = {"industry": "HEALTHCARE", "sub_sector": "MEDICAL_DEVICES", "stage": "STARTUP", "geography": "USA"}
    assert is_question_applicable(q_healthcare, prof_match, {}, all_q) is True

    # Wrong industry
    prof_fintech = {"industry": "FINTECH", "sub_sector": "ALL", "stage": "STARTUP", "geography": "USA"}
    assert is_question_applicable(q_healthcare, prof_fintech, {}, all_q) is False

    # Wrong subsector
    prof_pharma = {"industry": "HEALTHCARE", "sub_sector": "PHARMACEUTICALS", "stage": "STARTUP", "geography": "USA"}
    assert is_question_applicable(q_healthcare, prof_pharma, {}, all_q) is False

    # Universal core question passes regardless of industry
    q_core = {
        "question_id": "CORE_Q1",
        "scope": "CORE",
        "industry": "UNIVERSAL",
        "sub_sector": "ALL",
        "depends_on": None
    }
    assert is_question_applicable(q_core, prof_fintech, {}, {"CORE_Q1": q_core}) is True
