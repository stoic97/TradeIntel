"""TICKET-1073: a migration merged behind a shipped head is skipped on production with no error,
or leaves two heads that stop the upgrade. These pin the three guards: every revision id is
used once, the deploy runbook checks new migrations against the live tag's head before a train
is classified, and the merge practice says a migration's down_revision is main's head today.
"""
import re
from pathlib import Path

VERSIONS = Path("migrations/versions")
DEPLOY = Path("docs/runbooks/deploy.md").read_text(encoding="utf-8")
CONTRIBUTING = Path("CONTRIBUTING.md").read_text(encoding="utf-8")


def _ids(path: Path) -> tuple[str, str | None]:
    text = path.read_text(encoding="utf-8")
    rev = re.search(r"^revision = ['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    down = re.search(r"^down_revision = (?:['\"]([^'\"]+)['\"]|None)", text, re.MULTILINE)
    assert rev and down, f"{path.name} names no revision or down_revision"
    return rev.group(1), down.group(1)


def test_every_revision_id_is_used_once_and_matches_its_file_name():
    seen: dict[str, str] = {}
    for path in sorted(VERSIONS.glob("[0-9]*.py")):
        rev, _ = _ids(path)
        assert rev not in seen, f"revision {rev} is in both {seen[rev]} and {path.name}"
        seen[rev] = path.name
        assert path.name.startswith(f"{rev}_"), f"{path.name} says revision {rev} inside"


def test_the_train_checks_new_migrations_against_the_live_tags_head():
    step = DEPLOY[DEPLOY.index("### d. Deploy the tag"):]
    step = step[:step.index("Production then sits on a detached HEAD")]
    assert "live head" in step
    assert "down_revision" in step
    assert "--diff-filter=A" in step
    # and why: the two ways a migration behind the head goes wrong
    assert "skipped with no error" in step
    assert "two heads" in step


def test_the_merge_practice_says_down_revision_is_mains_head_today():
    before_review = CONTRIBUTING[CONTRIBUTING.index("## Before review"):CONTRIBUTING.index("## Review and merge")]
    assert re.search(r"`down_revision` is `main`'s head today", before_review)
