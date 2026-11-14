"""No trader-derived content in git, ever (README rule 1, SR-006). TICKET-930.

Git history cannot be deleted on request, so anything a trader sent us, or anything
derived from one trader's history, must never be committed: a deletion we promised
would be a promise git cannot keep. Two guards, and the deletion log moved out:

* **The tree.** No tracked file outside the allowed paths has a data extension. The
  allowed paths hold only synthetic data, made by code from a committed seed.
* **The ignore rules.** Everything under ``data/`` is ignored except the allowed paths,
  and a broker contract note (.pdf), a .tsv or a database is ignored anywhere, so one
  dropped into the tree cannot be committed by accident.
* **The deletion log** recorded each deleted trader's id and login id, in git, forever.
  It now lives on the server beside the data it describes (docs/runbooks/data-deletion.md).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

DATA_EXTENSIONS = re.compile(
    r"\.(csv|tsv|xlsx|xls|pdf|parquet|jsonl|db|sqlite\d*|zip)$", re.IGNORECASE
)
ALLOWED = (
    "data/fixtures/",   # synthetic fixtures: no real trader's trades
    "data/golden/",     # their goldens
    "data/null_rate/",  # a synthetic research run (planted signal, fixed seed); research seat's call
    "tests/fixtures/",  # test inputs, synthetic
)
SERVER_LOG = "/srv/scope/data/deletion-log.md"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False).stdout


def ignored(path: str) -> bool:
    """Whether git would refuse to add this path. --no-index: the rules, not the index."""
    return subprocess.run(["git", "check-ignore", "--no-index", "-q", path],
                          check=False).returncode == 0


# ---------- the tree ----------

def test_no_tracked_data_file_outside_the_allowed_paths():
    tracked = git("ls-files").splitlines()
    assert tracked, "run from the repository root"
    stray = [f for f in tracked if DATA_EXTENSIONS.search(f) and not f.startswith(ALLOWED)]
    assert stray == [], f"data files outside {ALLOWED}: {stray}"


# ---------- the ignore rules ----------

def test_anything_under_data_is_ignored_unless_it_is_an_allowed_path():
    for path in ("data/x.pdf", "data/x.json", "data/x.txt", "data/partner/tradebook.csv",
                 "data/null_rate_new/x.jsonl", "data/market/prices.csv"):
        assert ignored(path), path
    for path in ("data/fixtures/x.csv", "data/golden/x.json", "data/market/CROSSINGS.md",
                 "data/null_rate/recall-b2.meta.json"):
        assert not ignored(path), path


def test_a_contract_note_a_tsv_or_a_database_is_ignored_anywhere():
    for path in ("foo.tsv", "contract_note.pdf", "docs/x.pdf", "scope.db", "x.sqlite",
                 "x.sqlite3", "services/x.db", "notes/export.jsonl"):
        assert ignored(path), path


def test_synthetic_fixtures_of_any_type_can_still_be_added():
    for path in ("data/fixtures/x.pdf", "data/fixtures/demo/x.tsv", "data/fixtures/x.db"):
        assert not ignored(path), path


# ---------- the deletion log ----------

def test_the_repository_holds_no_deletion_log():
    """A log row is an identifier of a person whose data we just deleted. It lives on the
    server now; git's copy would outlive every deletion it records."""
    assert not Path("docs/runbooks/deletion-log.md").exists()
    for f in git("ls-files", "*.md").splitlines():
        text = Path(f).read_text(encoding="utf-8")
        header = r"^\|\s*Requested\s*\|\s*Completed\s*\|\s*Trader ID"
        assert not re.search(header, text, re.MULTILINE), f


def test_the_runbook_says_where_the_log_lives_and_every_reference_follows_it():
    runbook = Path("docs/runbooks/data-deletion.md").read_text(encoding="utf-8")
    assert SERVER_LOG in runbook
    refs = [f"{f}" for f in git("grep", "-l", "deletion-log.md").splitlines()
            if SERVER_LOG not in Path(f).read_text(encoding="utf-8")
            and f != "tests/unit/repo/test_no_data_in_git.py"]
    assert refs == [], f"still point at the old log in git: {refs}"
