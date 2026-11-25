"""One suite command: parallel across cores by default, `-n 0` for one core.

TICKET-1057. The suite is about 6,300 tests and took 723 s serial, 331 s with
pytest-xdist (the same 6289 passed / 21 skipped). The default has to be the parallel
run, in one place, so CI, the Makefile and the docs cannot drift into three commands.
These tests pin where that command lives; they never run the suite.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PYPROJECT = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
MAKEFILE = Path("Makefile").read_text(encoding="utf-8")
WORKFLOW = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
README = Path("README.md").read_text(encoding="utf-8")


def _run_line(step_name: str) -> str:
    """The `run:` line of the workflow step with this name."""
    match = re.search(rf"- name: {re.escape(step_name)}\n\s+run: (.+)", WORKFLOW)
    assert match, f"no step named {step_name!r} in ci.yml"
    return match.group(1)


def _make_recipe(target: str) -> str:
    match = re.search(rf"^{re.escape(target)}:.*\n((?:\t.*\n?)+)", MAKEFILE, re.MULTILINE)
    assert match, f"no Makefile target {target!r}"
    return match.group(1)


def test_parallel_is_the_project_default():
    addopts = PYPROJECT["tool"]["pytest"]["ini_options"]["addopts"]
    assert "-n auto" in addopts, addopts


def test_xdist_is_in_the_dev_group():
    dev = PYPROJECT["dependency-groups"]["dev"]
    assert any(re.match(r"pytest-xdist\b", dep) for dep in dev), dev


def test_ci_tests_step_uses_the_project_command():
    line = _run_line("Tests")
    assert "pytest" in line and not re.search(r"(^|\s)-n\b|--numprocesses", line), line


def test_makefile_test_target_uses_the_project_command():
    recipe = _make_recipe("test")
    assert "pytest" in recipe and not re.search(r"(^|\s)-n\b|--numprocesses", recipe), recipe


def test_research_fits_job_runs_on_one_core():
    line = _run_line("Research fits")
    assert re.search(r"(^|\s)-n 0(\s|$)", line), line


def test_readme_names_the_single_core_switch():
    assert "-n 0" in README
    assert re.search(r"(one|single) core", README, re.IGNORECASE)
