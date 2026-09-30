from pathlib import Path

import pytest

from app.services.ast_analyzer import PATTERN_QUERIES, analyze_code


def kinds(source: str) -> list[tuple[str, int]]:
    return [(p.kind, p.line_start) for p in analyze_code(source)]


@pytest.mark.parametrize(
    "source, expected",
    [
        ("for a in xs:\n    for b in ys:\n        print(a, b)\n", ("nested_loop", 1)),
        ("allowed = [1, 2]\nfor x in xs:\n    if x in allowed:\n        pass\n", ("linear_search_in_loop", 3)),
        ("seen = list()\nfor x in xs:\n    n = seen.count(x)\n", ("linear_search_in_loop", 3)),
        ("s = ''\nfor x in xs:\n    s += str(x)\n", ("string_concat_in_loop", 3)),
        ("s = ''\nfor x in xs:\n    s = s + str(x)\n", ("string_concat_in_loop", 3)),
        ("out = []\nfor x in xs:\n    out.append(x * 2)\n", ("append_loop", 2)),
        ("out = []\nfor x in xs:\n    if x:\n        out.append(x)\n", ("append_loop", 2)),
        ("for x in xs:\n    top = sorted(data)\n", ("invariant_call_in_loop", 2)),
        ("while running:\n    total = sum(data)\n", ("invariant_call_in_loop", 2)),
        ("for x in xs:\n    with open('f.txt') as f:\n        f.read()\n", ("file_io_in_loop", 2)),
        ("for p in paths:\n    p.read_text()\n", ("file_io_in_loop", 2)),
        ("import re\nfor x in xs:\n    re.search(r'a+', x)\n", ("regex_in_loop", 3)),
        ("def fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)\n", ("uncached_recursion", 1)),
        ("total = sum([x * x for x in xs])\n", ("list_in_aggregate", 1)),
        ("for i, row in df.iterrows():\n    pass\n", ("pandas_row_iteration", 1)),
        ("while q:\n    q.pop(0)\n", ("queue_pop_front", 2)),
    ],
)
def test_detects_pattern(source: str, expected: tuple[str, int]):
    assert expected in kinds(source)


@pytest.mark.parametrize(
    "source",
    [
        # Values that change every iteration are not loop-invariant.
        "for x in xs:\n    items.append(x)\n    total = sum(items)\n",
        "for x in xs:\n    top = sorted(x)\n",
        # Calls with unknown side effects are not flagged as invariant.
        "for x in xs:\n    top = sorted(load())\n",
        # Membership on a set is fine.
        "allowed = {1, 2}\nfor x in xs:\n    if x in allowed:\n        pass\n",
        # Numeric += is not string concatenation.
        "total = 0\nfor x in xs:\n    total += x\n",
        # Cached recursion and single recursion are fine.
        "from functools import lru_cache\n@lru_cache\ndef fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)\n",
        "def fact(n):\n    return 1 if n < 2 else n * fact(n - 1)\n",
        # Generators in aggregates, and a loop in a function defined inside a loop.
        "total = sum(x * x for x in xs)\n",
        "for x in xs:\n    def f():\n        return 1\n",
        # Comprehensions are the recommended form.
        "out = [x * 2 for x in xs]\n",
        # pop() from the end is O(1).
        "while q:\n    q.pop()\n",
    ],
)
def test_clean_code_has_no_false_positives(source: str):
    assert kinds(source) == []


def test_pattern_lines_cover_the_loop():
    source = "for a in xs:\n    for b in ys:\n        print(a, b)\n\nprint('done')\n"
    (pattern,) = analyze_code(source)
    assert (pattern.line_start, pattern.line_end) == (1, 3)
    assert "2 levels" in pattern.description


def test_every_pattern_kind_has_a_rag_query():
    source = (Path(__file__).parent / "fixtures" / "inefficient.py").read_text()
    found = {p.kind for p in analyze_code(source)}
    assert found <= PATTERN_QUERIES.keys()
    assert len(found) >= 8


def test_syntax_error_is_raised():
    with pytest.raises(SyntaxError):
        analyze_code("def broken(:\n")
