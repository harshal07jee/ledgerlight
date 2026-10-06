"""
Static analysis test ensuring no test contains dead assertions guarded by
conditionals on question presence or extraction maps (Requirement 1).
"""
import ast
import os
import pytest

TESTS_DIR = os.path.dirname(__file__)


class GuardedAssertionFinder(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.violations = []
        self.current_function = None

    def visit_FunctionDef(self, node):
        if node.name.startswith("test_"):
            old_fn = self.current_function
            self.current_function = node.name
            self.generic_visit(node)
            self.current_function = old_fn
        else:
            self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node):
        if self.current_function:
            # Check if condition checks question presence, ext_map, or question ID
            cond_str = ast.unparse(node.test)
            is_presence_check = (
                "ext_map" in cond_str
                or "extractions" in cond_str
                or "question" in cond_str.lower()
                or any(prefix in cond_str for prefix in ["CORE_", "SAAS_", "HLTH_", "FIN_", "MFG_", "ENERGY_"])
            )

            if is_presence_check:
                # Check if there is an assert inside body or orelse
                for child in ast.walk(node):
                    if isinstance(child, ast.Assert):
                        self.violations.append({
                            "file": self.filename,
                            "function": self.current_function,
                            "line": child.lineno,
                            "condition": cond_str,
                            "assert_code": ast.unparse(child)
                        })

        self.generic_visit(node)


def test_no_assertions_inside_conditionals_on_question_presence():
    """
    Fails if any test file contains an assertion inside an `if` statement
    guarded by question presence or extraction map membership.
    """
    all_violations = []

    for fname in os.listdir(TESTS_DIR):
        if fname.startswith("test_") and fname.endswith(".py") and fname != "test_no_dead_tests.py":
            fpath = os.path.join(TESTS_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=fpath)

            finder = GuardedAssertionFinder(fname)
            finder.visit(tree)
            all_violations.extend(finder.violations)

    if all_violations:
        err_msg = f"Found {len(all_violations)} dead/guarded assertions in tests:\n"
        for v in all_violations:
            err_msg += (
                f"  - {v['file']}:{v['line']} in {v['function']}(): "
                f"guarded by 'if {v['condition']}' -> 'assert {v['assert_code']}'\n"
            )
        pytest.fail(err_msg)
