"""docs/README.md lists every document under docs/, and every path a document cites exists.

TICKET-933 (repo audit, findings H6, L1, L2, L4). Superseded documents sat beside live ones
with no index, and documents cited files that were never there.

* docs/README.md has one row for each .md under docs/: what it is, status, owner, last checked.
* Outside docs/archive/, every relative link and every backticked path must exist in git.
  A path that cannot exist yet, or that lives elsewhere, is named at the foot with its reason.

What counts as a path: a backticked token made only of path characters that starts at a top
folder (ROOTS), or that ends in a known extension or a slash. A path from a top folder must
exist exactly; a shorter one may be relative to the document or the tail of a real path.
Commands and prose in backticks are not read.
"""

from __future__ import annotations

import functools
import posixpath
import re
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INDEX = ROOT / "docs" / "README.md"
ARCHIVE = "docs/archive/"
ROOTS = ("docs", "services", "tests", "scripts", "data", "migrations", ".github")
EXT = re.compile(r"\.(md|py|json|ya?ml|html|css|js|sha256|toml|csv|txt)$")
LINK = re.compile(r"\]\(([^)\s]+)")
TICK = re.compile(r"`([^`\n]+)`")
PATHY = re.compile(r"^[\w.\-/*]+$")
STATUS = re.compile(
    r"^(live|archived|target state|frozen (v[\d.]+|Accepted|amended \d{4}-\d\d-\d\d))$")
VERSIONED = re.compile(r"^(.+?)_v(\d+(?:[._]\d+)*)(?:_final)?\.md$")


@functools.cache
def tracked() -> tuple[frozenset[str], frozenset[str]]:
    """Every file git holds or would hold (nothing ignored), and every folder above one."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    files = frozenset(f for f in out.split("\0") if f and (ROOT / f).is_file())
    dirs = frozenset(f.rsplit("/", n)[0] for f in files for n in range(1, f.count("/") + 1))
    return files, dirs


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def documents() -> list[str]:
    return sorted(f for f in tracked()[0] if f.startswith("docs/") and f.endswith(".md"))


def live_documents() -> list[str]:
    """Archived documents are kept as they were, so their links are not read."""
    return [doc for doc in documents() if not doc.startswith(ARCHIVE)]


def exists(path: str) -> bool:
    files, dirs = tracked()
    path = path.rstrip("/")
    if "*" in path:
        return any(fnmatchcase(f, path) for f in files)
    return path in files or path in dirs


def is_tail(path: str) -> bool:
    files, dirs = tracked()
    tail = "/" + path.rstrip("/")
    return any(("/" + known).endswith(tail) for known in files | dirs)


def cited(body: str):
    """(line, kind, target) for each relative link and each backticked path in a document."""
    for n, line in enumerate(body.splitlines(), 1):
        for target in LINK.findall(line):
            target = target.split("#")[0]
            if target and not re.match(r"[A-Za-z][\w+.-]*:|/", target):
                yield n, "link", target
        for token in TICK.findall(line):
            token = re.sub(r":\d+(-\d+)?$", "", token.strip()).rstrip(".,;:")
            if not PATHY.match(token):
                continue
            if "/" in token and token.split("/")[0] in ROOTS:
                yield n, "root", token
            elif re.match(r"\w", token) and "*" not in token and (
                    EXT.search(token) or token.endswith("/")):
                yield n, "loose", token


def unresolved(doc: str, body: str) -> list[tuple[int, str]]:
    """The links and paths in one document that point at nothing."""
    here = posixpath.dirname(doc)
    missing = []
    for n, kind, target in cited(body):
        near = posixpath.normpath(posixpath.join(here, target))
        if kind == "root":
            found = exists(target)
        else:
            found = exists(near) or (kind == "loose" and is_tail(target))
        if not found:
            missing.append((n, target))
    return missing


def index_rows() -> dict[str, list[str]]:
    """Each row of the index: the document -> what it is, status, owner, last checked."""
    assert INDEX.is_file(), "docs/README.md does not exist"
    rows = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        row = re.match(r"\| \[[^\]]+\]\(([^)]+\.md)\) \|(.+)\|\s*$", line)
        if row:
            doc = posixpath.normpath("docs/" + row.group(1))
            cells = [cell.strip() for cell in row.group(2).split("|")]
            assert len(cells) == 4 and all(cells), (
                f"{doc}: a row is what it is, status, owner, last checked")
            rows[doc] = cells
    return rows


def test_the_index_lists_every_document_under_docs_and_nothing_else():
    """Gate 1."""
    listed, there = set(index_rows()), set(documents()) - {"docs/README.md"}
    assert there <= listed, f"under docs/ but not in docs/README.md: {sorted(there - listed)}"
    assert listed <= there, f"in docs/README.md but not under docs/: {sorted(listed - there)}"


def test_every_row_has_one_of_the_four_statuses_and_a_date():
    for doc, (_, status, _, checked) in index_rows().items():
        assert STATUS.match(status), (
            f"{doc}: {status!r} is not live, frozen <version>, archived or target state")
        assert re.fullmatch(r"\d{4}-\d\d-\d\d", checked), f"{doc}: {checked!r} is not a date"


def test_a_frozen_row_names_the_version_the_document_itself_says():
    for doc, (_, status, _, _) in index_rows().items():
        if status.startswith("frozen "):
            head = "\n".join(read(doc).splitlines()[:4])
            assert status[7:] in head, f"{doc}: the index says {status!r}, the document does not"


def test_archived_documents_are_in_the_archive_and_only_they_are():
    """Gate 3: a document the index calls archived is not left beside live ones."""
    for doc, (_, status, _, _) in index_rows().items():
        assert (status == "archived") == doc.startswith(ARCHIVE), f"{doc}: status {status!r}"


def test_an_archived_row_names_what_superseded_it():
    """Archiving records a supersession; it does not hide a file (Pawan, 20 Nov)."""
    for doc, (what, status, _, _) in index_rows().items():
        if status == "archived":
            assert "Superseded by" in what, f"{doc}: an archived row says what superseded it"


def test_only_the_newest_version_of_a_document_sits_outside_the_archive():
    """Gate 3: thesis v1.4 beside v1.5 is the case this was written for."""
    held: dict[tuple[str, str], list[tuple[tuple[int, ...], str]]] = {}
    for doc in live_documents():
        named = VERSIONED.match(posixpath.basename(doc))
        if named:
            version = tuple(int(part) for part in re.split(r"[._]", named.group(2)))
            held.setdefault((posixpath.dirname(doc), named.group(1)), []).append((version, doc))
    superseded = [doc for versions in held.values() for _, doc in sorted(versions)[:-1]]
    assert superseded == [], f"{superseded}: superseded, so they belong in {ARCHIVE}"


def test_no_gitkeep_is_left_beside_real_files():
    """Finding L1: a placeholder is not needed once its folder holds files."""
    files, _ = tracked()
    left = [f for f in sorted(files) if f.endswith("/.gitkeep")
            and any(g != f and g.startswith(f[:-8]) for g in files)]
    assert left == [], f"{left}: the folder has real files, so delete the placeholder"


def test_each_phase0_result_file_names_the_script_and_commit_that_produced_it():
    """Finding L2: a result file recorded its commit, but not the script that wrote it."""
    assert INDEX.is_file(), "docs/README.md does not exist"
    lines = INDEX.read_text(encoding="utf-8").splitlines()
    for path in sorted(f for f in tracked()[0] if re.match(r"docs/phase0/[^/]+\.json$", f)):
        name = path.removeprefix("docs/")
        row = next((line for line in lines if f"`{name}`" in line), "")
        script = re.search(r"`((?:scripts|services)/[\w/]+\.py)`", row)
        assert script and exists(script.group(1)), f"{path}: the index names no script for it"
        commit = re.search(r'"code_commit": "([0-9a-f]{7})', read(path))
        if commit:
            assert f"`{commit.group(1)}`" in row, f"{path}: no {commit.group(1)} in its row"


def test_every_link_and_every_backticked_path_in_the_documents_exists():
    """Gate 2."""
    broken = [f"{doc}:{n} {target}" for doc in live_documents()
              for n, target in unresolved(doc, read(doc)) if target not in ALLOWED]
    assert broken == [], "cited but not there:\n" + "\n".join(broken)


def test_a_planted_bad_link_and_planted_bad_paths_are_caught():
    """Gate 2: the check has been seen to fail."""
    planted = ("See [the plan](no_such_plan.md), `docs/no_such_file.md` and `no_such_card.md`.\n"
               "`docs/references.md` and `references.md` are real.\n")
    assert unresolved("docs/planted.md", planted) == [
        (1, "no_such_plan.md"), (1, "docs/no_such_file.md"), (1, "no_such_card.md")]


def test_every_allowed_path_is_still_cited_and_still_missing():
    """An entry outlives its reason the day the file is written or the citation goes."""
    still = {target for doc in live_documents() for _, target in unresolved(doc, read(doc))}
    assert set(ALLOWED) <= still, f"remove from the allow-list: {sorted(set(ALLOWED) - still)}"


def test_target_state_paths_are_marked_target_state_in_the_methodology():
    marked = re.search(r"\*\*Target state paths\.\*\*(.+)", read("docs/methodology.md"))
    assert marked, "docs/methodology.md has no '**Target state paths.**' paragraph"
    unmarked = [path for path in TARGET_STATE if f"`{path}`" not in marked.group(1)]
    assert unmarked == [], f"not marked target state in docs/methodology.md: {unmarked}"


def test_documents_kept_outside_the_repo_are_named_on_the_references_page():
    page = read("docs/references.md")
    unnamed = [name for name in ELSEWHERE if name not in page]
    assert unnamed == [], f"docs/references.md does not say where these live: {unnamed}"


# Named in docs/methodology.md as the target state, and marked so there. Not built yet.
TARGET_STATE = (
    "../../docs/research/README.md",
    ".github/workflows/hash-check.yml",
    ".github/workflows/import-boundaries.yml",
    ".github/workflows/research-gate.yml",
    "services/production/agent/",
    "services/production/ctr/ingestion/",
    "services/production/ctr/reconstruction/",
    "services/production/deletion/",
    "services/production/registry/",
    "services/shared/lineage/credit_chain.py",
    "services/shared/schemas/evidence_object_v1.py",
    "tests/e2e/",
    "WALL.md",
    "framework_v1.yaml.sha256",
    "hash-check.yml",
    "import-boundaries.yml",
    "infra/",
    "infra/config/",
    "web/",
    "web/src/",
)

# Kept in the claude.ai Project or in another repository. docs/references.md says where.
ELSEWHERE = (
    "BRAND_RULES_CARD.md",
    "prd_v0.1_skeleton.md",
    "scope_prd_v1_2_frozen.md",
    "scope_thin_slice_plan_v1.md",
    "scope_v1_build_completion_v1.md",
    "scope_v1_build_plan_v1.md",
    "scope_v1_technical_design_v1.md",
    "claude/scope_annex_h_multileg_convention_v2.md",
    "claude/scope_deploy_log.md",
    "claude/scope_deploy_update_runbook_v1.md",
    "claude/scope_feedback_loop_rn0001_status_v1.md",
    "claude/scope_feedback_loop_v1.md",
    "claude/scope_pr_merge_practice_v1.md",
    "claude/scope_prd_v1_2_amendments.md",
    "claude/scope_prd_v1_2_decision_list.md",
    "claude/scope_rn0002_round2_register_12nov.md",
)

# Everything else that is cited and is not in git, each with its reason.
OTHER = {
    "file.py": "methodology.md: a made-up name inside an example",
    "subdirectory/": "methodology.md: a made-up name inside an example",
    "data/corpus/corpus_a_v1/": "corpus-a.md: gitignored, it regenerates from code and seeds",
    "docs/phase0/recall-b2.md": "deferrals.md TD-033: the write-up that row asks for",
    "manifest.json": "ADR-005 (frozen): written at the first charged run, not built yet",
    "crude_1m_current.csv": "ADR-008 (frozen): the gitignored crude series, see crude-series.md",
    "data/market/crude_1m_current.csv": "crude-series.md: gitignored data the runbook extends",
    "crude_1m_current.json": "crude-series.md: the manifest beside the gitignored series",
    "crude_1m.csv": "crude-series.md: the fund's file, in the fund's repository",
    "data/market/crude_1m.csv": "corpus-a.md, crude-series.md: gitignored, pinned by its digest",
    "screens/preview/": "design kit README: previews are generated in the app, not kept in git",
    "screens/preview/08-calculating.html": "design kit README: a generated preview, not in git",
    "08-calculating-done.html": "design kit README: a generated preview, not in git",
    "share_positive_total.json": "definitions_v1.md: a fixture name its table asks for, not in git",
    "share_over_100.json": "definitions_v1.md: a fixture name its table asks for, not in git",
    "claude/scope_engineering_handoff_v1.md": "testing register: the handoff's old path; now docs/product",
    "mirror.html": "testing register: named there, not in this repository",
    "report.txt": "data-deletion.md: an example inspection report, kept by the founder",
    "docs/runbooks/deletion-log.md":
        "data-deletion.md: kept on the server at /srv/scope/data/deletion-log.md, never in git",
    "tracker/record_verify.py": "deploy.md: lives in the feedback-loop repository",
    "onboarding/tester.md": "deploy.md, uat-smoke.md: lives in the feedback-loop repository",
}

ALLOWED = {**dict.fromkeys(TARGET_STATE, "target state"),
           **dict.fromkeys(ELSEWHERE, "kept elsewhere"), **OTHER}
