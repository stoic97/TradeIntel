"""TICKET-949: production deploys a tag that passed UAT on staging, never main, and every
deploy is logged. These pin the runbook's guards so a later edit cannot quietly drop one.
"""
import re
from pathlib import Path

RUNBOOKS = Path("docs/runbooks")
DEPLOY = (RUNBOOKS / "deploy.md").read_text(encoding="utf-8")
TRAIN = DEPLOY[DEPLOY.index("## The release train"):DEPLOY.index("## 6. Before the first partner uploads")]


def _blocks(text):
    """Indented (pasteable) blocks, each as a list of lines."""
    blocks, current = [], []
    for line in text.splitlines():
        if line.startswith("    "):
            current.append(line[4:])
        elif current and line.strip():
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def test_the_train_runs_in_its_seven_steps_in_order():
    heads = re.findall(r"^### ([a-g])\. ", TRAIN, flags=re.MULTILINE)
    assert heads == list("abcdefg")


def test_no_path_deploys_main():
    assert "git pull" not in DEPLOY
    assert "No path deploys `main` directly." in " ".join(TRAIN.split())
    assert 'git checkout --quiet "$TAG"' in TRAIN


def test_every_block_that_touches_production_starts_with_the_guard():
    touching = [b for b in _blocks(TRAIN)
                if any(w in " ".join(b) for w in ("systemctl", "git checkout", "/srv/scope/data"))]
    assert len(touching) >= 5
    for block in touching:
        assert block[0] == "cd /srv/scope || exit 1", block[0]


def test_the_runbook_keeps_what_the_first_deploys_taught():
    for kept in (
        "git status --short",                                 # stop on local changes
        ".backup '$RP'",                                      # backup before the checkout
        "**Path A**", "**Path B**",                           # destructive migrations split
        "systemctl stop scope\n    sqlite3 /srv/scope/data/scope.db \"PRAGMA wal_checkpoint",  # stop, then snapshot
        "cmp -s deploy/scope.service /etc/systemd/system/scope.service",
        'select version_num from alembic_version;',            # alembic via sqlite
        "git tag --sort=-creatordate | head -2",               # where the previous tag is
    ):
        assert kept in TRAIN, kept


def test_only_the_founder_tags_and_a_hotfix_needs_two_people():
    assert "**the founder only**" in TRAIN
    assert "the author **and one other person**" in TRAIN
    assert "v2026.11.14.2" in TRAIN


def test_the_deploy_log_is_newest_first_and_the_last_step_adds_to_it():
    log = (RUNBOOKS / "deploys.md").read_text(encoding="utf-8")
    stamps = re.findall(r"^### (\d{4}-\d\d-\d\d \d\d:\d\d) IST", log, flags=re.MULTILINE)
    assert len(stamps) >= 6
    assert stamps == sorted(stamps, reverse=True)
    assert "docs/runbooks/deploys.md" in TRAIN[TRAIN.index("### f."):]
    assert "ADMIN_LOGIN_IDS=" not in log  # login ids never go in a public file


def test_the_smoke_pass_covers_what_every_train_needs():
    smoke = (RUNBOOKS / "uat-smoke.md").read_text(encoding="utf-8")
    for words in ("Create account", "Agree and continue", "Try it with a demo file", "Open your report",
                  "Your Journals", "What we read", "Your account", "Add charges", "Read this file again",
                  "Running deploy:", "There is nothing at this address.", "Delete everything", "Sign out"):
        assert words in smoke, words
    assert "never a trader's" in smoke
