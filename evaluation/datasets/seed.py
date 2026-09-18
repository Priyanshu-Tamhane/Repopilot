"""Seed dataset: 20 tasks x 8 bug categories (Phase 2, Spec §14).

Each task is a small synthetic repo (buggy file + pytest suite) materialized
at runtime so evaluation needs no network. Every bug is solvable by the
mock heuristic (offline) and by a real LLM via JSON file_edits.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .schema import BenchmarkDataset, BenchmarkTask

VERSION = "1.0"


def _t(
    id: str,
    category: str,
    issue: str,
    files: dict[str, str],
    tests: dict[str, str],
    expected_behavior: str,
    fail_to_pass: list[str],
) -> BenchmarkTask:
    return BenchmarkTask(
        id=id,
        category=category,
        issue=issue,
        files=files,
        tests=tests,
        expected_behavior=expected_behavior,
        fail_to_pass=fail_to_pass,
    )


def build_seed_tasks() -> list[BenchmarkTask]:
    tasks: list[BenchmarkTask] = []

    # ---- T01-T03: add() wrong for negatives ----
    add_bug = "def add(a, b):\n    # BUG: mishandles negatives\n    if b < 0:\n        return a - b\n    return a + b\n"
    add_tests = (
        "from {imp} import add\n\n"
        "def test_add_positive():\n    assert add(2, 3) == 5\n\n"
        "def test_add_negative():\n    assert add(2, -3) == -1\n\n"
        "def test_add_both_negative():\n    assert add(-2, -3) == -5\n"
    )
    tasks.append(_t("T01", "add_negatives",
        "Fix add() in calculator.py: returns wrong value for negative numbers, e.g. add(2, -3) gives 5 instead of -1.",
        {"calculator.py": add_bug + "\ndef subtract(a, b):\n    return a - b\n"},
        {"test_calc.py": add_tests.format(imp="calculator")},
        "add(a, b) returns a + b for all signs",
        ["test_add_negative", "test_add_both_negative"]))
    tasks.append(_t("T02", "add_negatives",
        "Addition bug in math_utils.py: add() breaks when the second operand is negative. Please fix the addition logic.",
        {"math_utils.py": add_bug + "\ndef is_even(n):\n    return n % 2 == 0\n"},
        {"test_math_utils.py": add_tests.format(imp="math_utils")},
        "add(a, b) returns a + b for all signs",
        ["test_add_negative", "test_add_both_negative"]))
    tasks.append(_t("T03", "add_negatives",
        "Fix issue: arithmetic/ops.py add() gives wrong result for negatives (add(10, -4) should be 6).",
        {"arithmetic/ops.py": add_bug},
        {"tests/test_ops.py": "from arithmetic.ops import add\n\ndef test_add_negative():\n    assert add(10, -4) == 6\n\ndef test_add_positive():\n    assert add(10, 4) == 14\n"},
        "add(a, b) returns a + b for all signs",
        ["test_add_negative"]))

    # ---- T04-T05: subtract() not implemented ----
    tasks.append(_t("T04", "subtract",
        "Fix subtract() in ops.py: it is not implemented (returns None). Should return a - b.",
        {"ops.py": "def subtract(a, b):\n    pass\n"},
        {"test_ops.py": "from ops import subtract\n\ndef test_subtract():\n    assert subtract(5, 3) == 2\n\ndef test_subtract_negative():\n    assert subtract(2, 5) == -3\n"},
        "subtract(a, b) returns a - b",
        ["test_subtract", "test_subtract_negative"]))
    tasks.append(_t("T05", "subtract",
        "Please fix: calculator subtract() raises NotImplementedError. Expected: subtract(10, 4) == 6.",
        {"calc.py": "def subtract(a, b):\n    raise NotImplementedError('TODO')\n\n\ndef add(a, b):\n    return a + b\n"},
        {"test_calc.py": "from calc import subtract\n\ndef test_subtract_basic():\n    assert subtract(10, 4) == 6\n"},
        "subtract(a, b) returns a - b",
        ["test_subtract_basic"]))

    # ---- T06-T07: multiply() not implemented ----
    tasks.append(_t("T06", "multiply",
        "Fix multiply() in ops.py: not implemented, returns None. Should return a * b.",
        {"ops.py": "def multiply(a, b):\n    pass\n"},
        {"test_ops.py": "from ops import multiply\n\ndef test_multiply():\n    assert multiply(3, 4) == 12\n\ndef test_multiply_negative():\n    assert multiply(-2, 5) == -10\n"},
        "multiply(a, b) returns a * b",
        ["test_multiply", "test_multiply_negative"]))
    tasks.append(_t("T07", "multiply",
        "Please fix: math multiply() raises NotImplementedError. Expected: multiply(6, 7) == 42.",
        {"mathops.py": "def multiply(a, b):\n    raise NotImplementedError('TODO')\n"},
        {"test_mathops.py": "from mathops import multiply\n\ndef test_multiply_basic():\n    assert multiply(6, 7) == 42\n"},
        "multiply(a, b) returns a * b",
        ["test_multiply_basic"]))

    # ---- T08-T09: divide() missing zero guard ----
    div_bug = (
        "def divide(a, b):\n"
        "    # BUG: silently returns 0 on zero division instead of raising\n"
        "    if b == 0:\n"
        "        return 0\n"
        "    return a / b\n"
    )
    tasks.append(_t("T08", "divide_zero",
        "Fix divide() in calc.py: divide by zero raises raw ZeroDivisionError with no message. Raise ZeroDivisionError('division by zero') for b == 0.",
        {"calc.py": div_bug},
        {"test_calc.py": "import pytest\nfrom calc import divide\n\ndef test_divide():\n    assert divide(8, 2) == 4\n\ndef test_divide_by_zero():\n    with pytest.raises(ZeroDivisionError):\n        divide(5, 0)\n"},
        "divide(a, b) returns a / b, raises ZeroDivisionError on b == 0",
        ["test_divide_by_zero"]))
    tasks.append(_t("T09", "divide_zero",
        "Please fix safe divide in math/div.py: divide(10, 0) must raise ZeroDivisionError instead of crashing ambiguously.",
        {"math/div.py": div_bug + "\ndef add(a, b):\n    return a + b\n"},
        {"test_div.py": "import pytest\nfrom math.div import divide\n\ndef test_divide_zero_guarded():\n    with pytest.raises(ZeroDivisionError):\n        divide(10, 0)\n"},
        "divide(a, b) raises ZeroDivisionError on b == 0",
        ["test_divide_zero_guarded"]))

    # ---- T10-T12: off-by-one (skips last element; fixed form uses `items`) ----
    tasks.append(_t("T10", "off_by_one",
        "Fix off-by-one in stats.py: total() skips the last element, total([1, 2, 3]) gives 3 instead of 6.",
        {"stats.py": "def total(items):\n    s = 0\n    for i in range(len(items) - 1):\n        s += items[i]\n    return s\n"},
        {"test_stats.py": "from stats import total\n\ndef test_total_all():\n    assert total([1, 2, 3]) == 6\n\ndef test_total_single():\n    assert total([7]) == 7\n"},
        "total() sums ALL elements",
        ["test_total_all", "test_total_single"]))
    tasks.append(_t("T11", "off_by_one",
        "Off by one bug: count_all() in counter.py misses the last item. Fix so all elements are counted.",
        {"counter.py": "def count_all(items):\n    c = 0\n    for i in range(len(items) - 1):\n        c += 1\n    return c\n"},
        {"test_counter.py": "from counter import count_all\n\ndef test_count_all():\n    assert count_all([1, 2, 3, 4]) == 4\n"},
        "count_all() counts ALL elements",
        ["test_count_all"]))
    tasks.append(_t("T12", "off_by_one",
        "Fix off-by-one error in scores.py: sum_scores() drops the final score.",
        {"scores.py": "def sum_scores(items):\n    s = 0\n    for i in range(len(items) - 1):\n        s += items[i]\n    return s\n"},
        {"test_scores.py": "from scores import sum_scores\n\ndef test_sum_scores():\n    assert sum_scores([10, 20, 30]) == 60\n"},
        "sum_scores() sums ALL elements",
        ["test_sum_scores"]))

    # ---- T13-T15: reverse_string returns input unchanged ----
    tasks.append(_t("T13", "reverse",
        "Fix reverse_string() in text.py: it returns the input unchanged. reverse_string('hello') should be 'olleh'.",
        {"text.py": "def reverse_string(s):\n    return s\n"},
        {"test_text.py": "from text import reverse_string\n\ndef test_reverse_basic():\n    assert reverse_string('hello') == 'olleh'\n\ndef test_reverse_palindrome():\n    assert reverse_string('abc') == 'cba'\n"},
        "reverse_string(s) returns s reversed",
        ["test_reverse_basic", "test_reverse_palindrome"]))
    tasks.append(_t("T14", "reverse",
        "Please fix string reverse helper in utils/strings.py: reverse_text('abcd') must give 'dcba'.",
        {"utils/strings.py": "def reverse_text(s):\n    return s\n\n\ndef shout(s):\n    return s.upper()\n"},
        {"test_strings.py": "from utils.strings import reverse_text\n\ndef test_reverse_text():\n    assert reverse_text('abcd') == 'dcba'\n"},
        "reverse_text(s) returns s reversed",
        ["test_reverse_text"]))
    tasks.append(_t("T15", "reverse",
        "Bug: reverse_words() in words.py does not reverse. Fix so reverse_words('hey') == 'yeh'.",
        {"words.py": "def reverse_words(s):\n    return s\n"},
        {"test_words.py": "from words import reverse_words\n\ndef test_reverse_words():\n    assert reverse_words('hey') == 'yeh'\n"},
        "reverse_words(s) returns s reversed",
        ["test_reverse_words"]))

    # ---- T16-T17: max returns min ----
    tasks.append(_t("T16", "max_value",
        "Fix find_max() in stats.py: it returns the minimum instead of the maximum. find_max([1, 9, 3]) should be 9.",
        {"stats.py": "def find_max(nums):\n    return min(nums)\n"},
        {"test_stats.py": "from stats import find_max\n\ndef test_find_max():\n    assert find_max([1, 9, 3]) == 9\n\ndef test_find_max_negative():\n    assert find_max([-5, -1, -3]) == -1\n"},
        "find_max(nums) returns the maximum",
        ["test_find_max", "test_find_max_negative"]))
    tasks.append(_t("T17", "max_value",
        "Please fix maximum helper in numbers.py: max_value([4, 2, 8]) must be 8, currently returns 2.",
        {"numbers.py": "def max_value(nums):\n    return min(nums)\n"},
        {"test_numbers.py": "from numbers import max_value\n\ndef test_max_value():\n    assert max_value([4, 2, 8]) == 8\n"},
        "max_value(nums) returns the maximum",
        ["test_max_value"]))

    # ---- T18-T19: factorial(0) wrong base case ----
    fact_bug = "def factorial(n):\n    if n == 0:\n        return 0\n    return n * factorial(n - 1)\n"
    tasks.append(_t("T18", "factorial",
        "Fix factorial() in mathx.py: factorial(0) should be 1, currently returns 0.",
        {"mathx.py": fact_bug},
        {"test_mathx.py": "from mathx import factorial\n\ndef test_factorial_zero():\n    assert factorial(0) == 1\n\ndef test_factorial_five():\n    assert factorial(5) == 120\n"},
        "factorial(0) == 1, factorial(n) == n!",
        ["test_factorial_zero", "test_factorial_five"]))
    tasks.append(_t("T19", "factorial",
        "Please fix recursive factorial in funcs.py: base case factorial(0) must equal 1.",
        {"funcs.py": fact_bug + "\ndef double(n):\n    return 2 * n\n"},
        {"test_funcs.py": "from funcs import factorial\n\ndef test_factorial_base():\n    assert factorial(0) == 1\n"},
        "factorial(0) == 1",
        ["test_factorial_base"]))

    # ---- T20: average divides by n+1 ----
    tasks.append(_t("T20", "average",
        "Fix average() in stats.py: average([2, 4]) gives 2.0 instead of 3.0 (divides by n+1).",
        {"stats.py": "def average(nums):\n    return sum(nums) / (len(nums) + 1)\n"},
        {"test_stats.py": "from stats import average\n\ndef test_average():\n    assert average([2, 4]) == 3.0\n"},
        "average(nums) == sum(nums) / len(nums)",
        ["test_average"]))

    assert len(tasks) == 20, f"expected 20 seed tasks, got {len(tasks)}"
    assert len({t.id for t in tasks}) == 20, "duplicate task ids"
    return tasks


def build_dataset() -> BenchmarkDataset:
    return BenchmarkDataset(name="repopilot-seed", version=VERSION, tasks=build_seed_tasks())


def materialize(task: BenchmarkTask, parent_dir: str | Path) -> Path:
    """Write task files + tests to parent_dir/<id>/, git init+commit. Returns repo Path."""
    repo = Path(parent_dir) / task.id
    if repo.exists():
        import shutil

        shutil.rmtree(repo, ignore_errors=True)
    repo.mkdir(parents=True, exist_ok=True)
    for rel, content in {**task.files, **task.tests}.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    for args in (["git", "init"], ["git", "config", "user.email", "bench@repopilot"],
                 ["git", "config", "user.name", "bench"], ["git", "add", "."],
                 ["git", "commit", "-m", f"seed {task.id} buggy"]):
        subprocess.run(args, cwd=str(repo), capture_output=True)
    return repo


def dump_json(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build_dataset().model_dump_json(indent=2), encoding="utf-8")
    return p


def load_json(path: str | Path) -> BenchmarkDataset:
    return BenchmarkDataset.model_validate_json(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "evaluation/datasets/seed_tasks.json"
    dump_json(out)
    print(f"wrote {out} (20 tasks)")
