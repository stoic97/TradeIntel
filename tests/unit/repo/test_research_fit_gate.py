"""The research-fit gate: the required check never runs an MCMC fit.

TICKET-954. CI has failed on every push to main since it was switched on
(#144, 14 Nov). Every red was a research MCMC fit - B2's end-to-end bar, or
M1's diagnostics - while about 5,000 other tests passed in every run. A red
nobody can act on hides the next real one, so the fits move to a second,
non-blocking job and the required `checks` job runs everything else.

These tests pin the gate, never the fits themselves.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PYPROJECT = Path("pyproject.toml").read_text(encoding="utf-8")
MAKEFILE = Path("Makefile").read_text(encoding="utf-8")
WORKFLOW = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
TESTS = Path("tests")
# This file has to name the pattern it forbids, so it excuses itself and nothing else.
SELF = Path(__file__).resolve()

MARKER = "research_fit"
SELECTOR = "not research_fit"

# Every way a test can reach a sampler today. A new one gets added here, or its
# tests get marked; silence is not an option this gate allows.
FIT_CALLS = ("m1.fit", "b2.run", "sbc.run", "ce.BACKENDS")
FIT_FIXTURES = ("fits",)
FIT_DIRS = ("unit/engine", "unit/models")


def _tests_in(path: Path):
    src = path.read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            yield node, src


def _is_marked(node: ast.FunctionDef) -> bool:
    return any(
        isinstance(sub, ast.Attribute) and sub.attr == MARKER
        for dec in node.decorator_list
        for sub in ast.walk(dec)
    )


def _raises_blocks(node: ast.FunctionDef, src: str) -> list[str]:
    """The source of every with-pytest.raises block inside this test."""
    out = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.With):
            continue
        for item in sub.items:
            call = item.context_expr
            if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "raises":
                out.append(ast.get_source_segment(src, sub) or "")
    return out


def _reaches_a_sampler(node: ast.FunctionDef, src: str) -> bool:
    """A fit call the test expects to raise never reaches the sampler: M1 refuses a
    one-day history, and a history that is almost one number, before pm.Model is
    entered. Counting those would push a fast, deterministic test out of the
    required check for nothing."""
    if any(arg.arg in FIT_FIXTURES for arg in node.args.args):
        return True
    body = ast.get_source_segment(src, node) or ""
    for block in _raises_blocks(node, src):
        body = body.replace(block, "")
    return any(call in body for call in FIT_CALLS)


def test_the_research_fit_marker_is_registered():
    """An unregistered marker only warns, and the test runs anyway - so a misspelled
    mark would put a fit straight back into the required job."""
    block = re.search(r"^\[tool\.pytest\.ini_options\](.*?)(?=^\[|\Z)", PYPROJECT, re.MULTILINE | re.DOTALL)
    assert block, "pyproject.toml has no [tool.pytest.ini_options]"
    markers = re.search(r"^markers = \[(.*?)\]", block.group(1), re.MULTILINE | re.DOTALL)
    assert markers, "[tool.pytest.ini_options] declares no markers"
    entry = re.search(rf'"{MARKER}:\s*([^"]+)"', markers.group(1))
    assert entry and entry.group(1).strip(), f"{MARKER} is not registered with a description"


def test_no_test_is_excused_by_platform():
    """Gate 4. TD-023 and TD-034 were carried as xfail(sys.platform == ...), which
    wrote a fact into the suite that has since changed: B2 fails on Linux too, and
    the two M1 tests sometimes pass there, which a strict xfail turns red. A fit is
    either gated or it is not; which machine ran it is not the test's business."""
    hits = [
        f"{path.as_posix()}:{n}"
        for path in sorted(TESTS.rglob("*.py"))
        if path.resolve() != SELF
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "sys.platform" in line
    ]
    assert hits == [], hits


def test_the_marker_is_on_exactly_the_tests_that_reach_a_sampler():
    """Marking today's seventeen fixes today. A fit test added tomorrow would land in
    the required job and CI would go red again for the same reason, so the rule is
    checked rather than the list. The other direction matters too: a deterministic
    test carrying the marker leaves the required check without anyone noticing."""
    unmarked, over_marked = [], []
    for folder in FIT_DIRS:
        for path in sorted((TESTS / folder).rglob("test_*.py")):
            for node, src in _tests_in(path):
                name = f"{path.as_posix()}::{node.name}"
                if _reaches_a_sampler(node, src) and not _is_marked(node):
                    unmarked.append(name)
                if _is_marked(node) and not _reaches_a_sampler(node, src):
                    over_marked.append(name)
    assert unmarked == [], f"these reach a sampler unmarked: {unmarked}"
    assert over_marked == [], f"these are marked but never fit: {over_marked}"


def test_make_test_and_the_required_job_select_the_same_tests():
    """make test is the deploy check (handoff 12, step 2). If it and CI's required job
    disagree about what runs, one of the two is lying to whoever reads it."""
    recipe = re.search(r"^test:.*\n(?:\t.*\n)+", MAKEFILE, re.MULTILINE)
    assert recipe, "the Makefile has no test target"
    assert SELECTOR in recipe.group(0), recipe.group(0)
    assert "-m research_fit" in MAKEFILE, "no test-research target for the marked tests"
    step = re.search(r"name: Tests\n\s+run: (.+)", WORKFLOW)
    assert step, "the required job has no Tests step"
    assert SELECTOR in step.group(1), step.group(1)
    assert "continue-on-error: true" in WORKFLOW, "research-fits must not fail the workflow"
    assert "lscpu" in WORKFLOW, "gate 2 wants the runner's CPU on record"