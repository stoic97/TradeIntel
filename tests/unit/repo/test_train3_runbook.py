"""TICKET-1072: train 3 is the first deploy that needs more than a pull and a restart.

Three Fyers settings, the market folder and two units must be in place before production
restarts, staging is checked first, and the market bars get one copy off the droplet. These read
the runbook and the backup script as text; what proves them is the train-3 deploy itself
(TICKET-1078) and the next night's backup.
"""

from __future__ import annotations

import re
from pathlib import Path

DEPLOY = Path("docs/runbooks/deploy.md").read_text(encoding="utf-8")
BACKUP = Path("deploy/backup.sh").read_text(encoding="utf-8")
HEAD = "### Train 3, once: market data before the restart"
GUARD = "cd /srv/scope || exit 1"
KEYS = ("FYERS_APP_ID", "FYERS_SECRET_KEY", "FYERS_REDIRECT_URI")


def _section() -> str:
    start = DEPLOY.index(HEAD)
    rest = DEPLOY[start + len(HEAD):]
    end = re.search(r"^#{2,3} ", rest, flags=re.MULTILINE)
    return rest[: end.start()] if end else rest


def _blocks(text: str) -> list[str]:
    """Indented (pasteable) blocks, each as one string."""
    blocks, current = [], []
    for line in text.splitlines():
        if line.startswith("    "):
            current.append(line[4:])
        elif current and line.strip():
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def test_the_train3_section_sits_inside_the_release_train():
    assert HEAD in DEPLOY
    assert DEPLOY.index("## The release train") < DEPLOY.index(HEAD) < DEPLOY.index(
        "## 6. Before the first partner uploads")


def test_the_blocks_run_in_order_staging_first():
    blocks = _blocks(_section())
    def first(marker: str) -> int:
        return next(i for i, b in enumerate(blocks) if marker in b)
    order = [first("/etc/scope/staging.env"), first("FYERS_APP_ID"), first("--expiry-prefix=scope/"),
             first("install -d -o scope -g scope"), first("systemctl enable scope-market.timer"),
             first("systemctl start scope-market.timer")]
    assert order == sorted(order) and len(set(order)) == len(order), order


def test_every_block_starts_with_the_guard_and_stops_on_a_failure():
    blocks = _blocks(_section())
    assert len(blocks) >= 6
    for block in blocks:
        lines = block.splitlines()
        assert lines[0] == GUARD, lines[0]
        assert "set -eu" in block, block
        assert block.rstrip().endswith('|| echo "STOPPED: fix the line above before going on"'), block


def test_no_block_holds_a_key_or_sources_an_env_file():
    for block in _blocks(_section()):
        for key in KEYS:
            for m in re.finditer(rf"{key}=(\S*)", block):
                assert m.group(1).startswith(("<", "'", '"', "%")) or m.group(1) == "", m.group(0)
        assert not re.search(r"(^|[;&|(]\s*)(\.|source) /etc/scope/", block, re.MULTILINE), block


def test_a_placeholder_stops_the_check():
    check = next(b for b in _blocks(_section()) if "still a placeholder" in b)
    for key in KEYS:
        assert key in check
    assert "'<'*" in check


def test_the_units_come_from_the_tag_and_the_timer_starts_only_after_the_restart():
    blocks = _blocks(_section())
    install = next(b for b in blocks if "systemctl enable scope-market.timer" in b)
    assert 'git show "$TAG:deploy/$u"' in install
    assert "enable --now" not in install
    assert "STOP: fill TAG=" in install


def test_the_lifecycle_rule_is_scoped_to_scope_before_any_market_copy():
    section = _section()
    assert "--expiry-prefix=scope/" in section and "getlifecycle" in section
    assert "<Prefix>scope/</Prefix>" in section


def test_the_runbook_names_the_prefix_and_why():
    section = " ".join(_section().split())
    assert "`market/`" in section
    assert "cannot fetch it again" in section


def test_the_nightly_job_copies_the_market_bars_under_market():
    assert "sync --no-delete-removed" in BACKUP
    sync = next(line for line in BACKUP.splitlines() if "sync --no-delete-removed" in line)
    assert "/market/" in sync and "$BUCKET" in sync
    assert BACKUP.index("copied off the droplet") < BACKUP.index("sync --no-delete-removed"), (
        "the market copy runs after the trader copies, so its failure never stops them")
    assert 'BUCKET=${SPACES%/scope}' in BACKUP
    assert "MARKET COPY NOT MADE" in BACKUP


def test_no_second_backup_job():
    jobs = [p.name for p in Path("deploy").iterdir() if "backup" in p.name]
    assert jobs == ["backup.sh"], jobs
