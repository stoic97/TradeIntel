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


# --- review of 24 Nov 22:20: the guard must see heads, and the deploy block must not pass on nothing ---

from tests.helpers.migration_chain import chain_problems


def _scratch(tmp_path: Path, files: dict[str, tuple[str, str | None]]) -> Path:
    for name, (rev, down) in files.items():
        down_line = "None" if down is None else f"'{down}'"
        (tmp_path / f"{name}.py").write_text(f"revision = '{rev}'\ndown_revision = {down_line}\n", encoding="utf-8")
    return tmp_path


def test_two_migrations_revising_the_same_parent_are_two_heads(tmp_path):
    d = _scratch(tmp_path, {"0015_a": ("0015", None), "0017_b": ("0017", "0015"),
                            "0018_c": ("0018", "0017"), "0021_d": ("0021", "0017")})
    assert any("two heads" in p for p in chain_problems(d))


def test_a_migration_whose_parent_is_behind_the_head_is_caught(tmp_path):
    d = _scratch(tmp_path, {"0015_a": ("0015", None), "0017_b": ("0017", "0015"),
                            "0018_c": ("0018", "0015")})
    assert any("behind" in p or "two heads" in p for p in chain_problems(d))


def test_a_parent_that_no_file_holds_is_caught(tmp_path):
    d = _scratch(tmp_path, {"0015_a": ("0015", None), "0019_b": ("0019", "0016")})
    assert any("0016" in p for p in chain_problems(d))


def test_mains_own_migrations_make_one_straight_chain():
    assert chain_problems(VERSIONS) == []


def _head_check_block() -> str:
    step = DEPLOY[DEPLOY.index("### d. Deploy the tag"):]
    start = step.index("check that no new migration sits behind the live tag's head")
    return step[start:step.index("Expected: the first new migration's")]


def test_the_head_check_stops_loudly_when_tag_or_live_is_unset():
    block = _head_check_block()
    for var in ("TAG", "LIVE"):
        assert f"STOP: {var} is not set" in block


def test_the_head_check_reads_revision_ids_from_inside_the_files():
    block = _head_check_block()
    assert "grep -oE '/[0-9]{4}_'" not in block
    assert '"^revision = "' in block or "'^revision = '" in block


def test_the_head_check_comes_before_the_path_a_or_b_decision():
    step = DEPLOY[DEPLOY.index("### d. Deploy the tag"):]
    assert step.index("check that no new migration sits behind the live tag's head") < step.index("decides the path")
