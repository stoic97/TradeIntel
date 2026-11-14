"""The rules five people follow, and the documents the code cites, are visible in the repo.

TICKET-936 (repo audit, findings H5, M11, L9). Code cites "PRD §x" and the handoff over two
hundred times, and the Developer Manual and the technical design besides, while none of them
was named anywhere a newcomer could find; the merge practice lived only in the Project; and
the same people committed under several identities.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def references() -> str:
    path = Path("docs/references.md")
    return path.read_text(encoding="utf-8") if path.exists() else ""

CODE = [p for d in ("services", "tests", "scripts") for p in Path(d).rglob("*")
        if p.suffix in {".py", ".html"} and "__pycache__" not in p.parts]

# How the code names an outside document -> the name references.md lists it under.
CITED_AS = {
    r"\bPRD\b": "**PRD**",
    r"\bhandoff\b": "**handoff**",
    r"\bManual\b": "**Developer Manual**",
    r"Technical Design": "**Technical Design**",
    r"\bbuild plan\b": "**build plan**",
    r"\bR-Spec\b": "**R-Spec**",
    r"\bScope_Feedback\b": "**Scope_Feedback**",
    r"\bThesis\b": "**Thesis**",
    r"\bWorkbook\b": "**Workbook**",
    r"\bmethodology\b": "**methodology**",
    r"\bAnnex H\b": "**Annex H**",
    r"\bBrand Strategy\b": "**Brand Strategy**",
}


def tracked() -> set[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout
    return {Path(f).name for f in out.splitlines()}


def test_every_document_the_code_names_is_listed_with_where_it_lives():
    used = {label for pattern, label in CITED_AS.items()
            if any(re.search(pattern, p.read_text(encoding="utf-8", errors="replace")) for p in CODE)}
    assert {"**PRD**", "**handoff**", "**Developer Manual**"} <= used, "the scan found nothing"
    missing = sorted(label for label in used if label not in references())
    assert missing == [], f"named in code, not in docs/references.md: {missing}"


def test_every_versioned_document_cited_in_the_docs_resolves():
    """A versioned filename cited anywhere in docs/ or the README is either in the repo or
    listed in references.md with where it lives."""
    docs = [*Path("docs").rglob("*.md"), Path("README.md")]
    cited = {m for p in docs for m in re.findall(r"\b[a-z0-9_]+_v[0-9][a-z0-9_.]*\.md\b",
                                                 p.read_text(encoding="utf-8"))}
    unresolved = sorted(f for f in cited - tracked() if f not in references())
    assert unresolved == [], f"cited, but neither in the repo nor in references.md: {unresolved}"


def test_one_name_and_email_per_person():
    """git shortlog shows one line per person: every alias seen on main maps to one identity."""
    aliases = {
        "stoic97 <pawan.rathore.iitk@gmail.com>": "Pawan Rathore <pawan.rathore.iitk@gmail.com>",
        "Pawan Rathore <pawan.rathore.iitk@gmail.com>": "Pawan Rathore <pawan.rathore.iitk@gmail.com>",
        "Harshad Yadav <HARSHAD.Y10@gmail.com>": "Harshad Yadav <Harshad.y10@gmail.com>",
        "Harshad Yadav <Harshad.y10@gmail.com>": "Harshad Yadav <Harshad.y10@gmail.com>",
        "rikk-awal <team@plusev.in>": "rikk-awal <rikk.haq@gmail.com>",
    }
    for alias, canonical in aliases.items():
        got = subprocess.run(["git", "check-mailmap", alias], capture_output=True, text=True,
                             check=True).stdout.strip()
        assert got == canonical, f"{alias} -> {got}"
    # The shared team address is mapped for Rikk's name only, never for everyone.
    stranger = subprocess.run(["git", "check-mailmap", "Someone Else <team@plusev.in>"],
                              capture_output=True, text=True, check=True).stdout.strip()
    assert stranger == "Someone Else <team@plusev.in>"


def test_a_new_pr_opens_with_the_template():
    path = Path(".github/pull_request_template.md")
    assert path.exists(), "no PR template"
    template = path.read_text(encoding="utf-8")
    for part in ("TICKET-NNN", "### Gate", "RED", "### Screenshots", "No trader data", "Reviewer (not the author)"):
        assert part in template, part


def test_contributing_states_the_rules():
    path = Path("CONTRIBUTING.md")
    assert path.exists(), "no CONTRIBUTING.md"
    rules = path.read_text(encoding="utf-8")
    for rule in ("`fix/`", "`feat/`", "`docs/`", "`refactor/`", "TICKET-NNN", "RED first",
                 "One PR closes one ticket", "Merge commit, never squash", "The reviewer is not the author",
                 "Stacked PRs merge base first", "Done only when its gate is true on the running product",
                 "No WIP commits on `main`", "Screenshots go **in the PR**", "`data/fixtures/`",
                 "`tests/fixtures/`", "scope_pr_merge_practice_v1.md", "docs/references.md"):
        assert rule in rules, rule
