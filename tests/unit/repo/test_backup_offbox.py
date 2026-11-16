"""Backups leave the droplet, and every document says the same about them (TICKET-941).

Repo audit finding M10 (epic TICKET-927). The nightly copies sat on the droplet they
protect, and the documents disagreed on how often DigitalOcean backs the droplet up: daily
in deploy.md and ADR-007, weekly in the data-flow map and in the consent review of 22 Oct.
The consent text promises that backups roll off within 30 days, so every copy, on the
droplet and off it, has to be gone inside 30.

These read the scripts and runbooks as text. What proves the copies exist and restore is
on the droplet: last night's object in the bucket, and restore-drill.sh --from-spaces.
"""

from __future__ import annotations

import re
from pathlib import Path

FREQUENCY = "DigitalOcean droplet backups: weekly, the four most recent kept"
OURS = (
    "Scope's own nightly copies: 29 days on the droplet and in Spaces (BLR1); "
    "the Spaces lifecycle rule deletes at 30"
)

ADR = "docs/adr/ADR-007-scope-v1-runtime.md"
DEPLOY = "docs/runbooks/deploy.md"
DELETION = "docs/runbooks/data-deletion.md"
MAP = "docs/runbooks/data-flow-map.md"
BACKUP = "deploy/backup.sh"
DRILL = "deploy/restore-drill.sh"

STALE = ("daily droplet backup", "enable **daily backups**", "copies the whole disk nightly")


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_gate_3_every_backup_document_states_the_same_frequency_and_retention():
    for path in (DEPLOY, ADR, DELETION, MAP):
        text = read(path)
        assert FREQUENCY in text, f"{path} does not say {FREQUENCY!r}"
        assert OURS in text, f"{path} does not say {OURS!r}"


def test_nothing_else_still_says_the_droplet_is_backed_up_daily():
    """ADR-007's Decision keeps its words (SR-011); its Amendments entry corrects them."""
    for path in (DEPLOY, DELETION, MAP, BACKUP, "services/production/accounts/deletion.py"):
        found = [s for s in STALE if s in read(path).lower()]
        assert found == [], f"{path} still says {found}"


def test_adr_007_is_amended_for_the_backups_not_edited():
    decision, amendments = read(ADR).split("## Amendments", 1)
    assert "daily droplet backups" in decision, "the Decision stays as accepted (SR-011)"
    parts = amendments.split("(TICKET-941)", 1)
    assert len(parts) == 2, "no Amendments entry for TICKET-941"
    assert FREQUENCY in parts[1] and "Spaces" in parts[1], "the entry names neither"


def test_the_nightly_copy_leaves_the_droplet_encrypted_and_never_with_the_key():
    script = read(BACKUP)
    puts = [line for line in script.splitlines() if "s3cmd" in line and " put " in line]
    assert len(puts) == 2, f"the database copy and the files tarball go up, got {puts}"
    for line in puts:
        assert ".enc" in line or "files-" in line, f"uploads something unencrypted: {line}"
        assert "scope.env" not in line and "SCOPE_FILE_KEY" not in line, f"key in: {line}"
    assert ".db.enc" in script, "the database copy is encrypted before it leaves"


def test_every_copy_is_gone_inside_the_30_days_the_consent_text_promises():
    """`find -mtime +30` matches only at 31 days, so, run once a day, a copy would have lived
    31 to 32. Pre-empted: the oldest copy was 26 days old when this landed."""
    script = read(BACKUP)
    assert "KEEP_DAYS=${SCOPE_BACKUP_DAYS:-29}" in script
    assert "-mtime" not in script, "find -mtime +N removes a file only at N+1 days"
    assert "CUTOFF" in script and " del " in script, "copies in Spaces older than that go too"
    finds = [line for line in script.splitlines() if line.lstrip().startswith("find ")]
    assert finds and all("-name" not in line for line in finds), (
        "the sweep goes by age over the whole directory, restore points and stray copies too"
    )
    assert all("-maxdepth 1" in line for line in finds), (
        "only files sitting in the backup directory: a wrong SCOPE_BACKUPS must not recurse"
    )


def test_the_restore_drill_restores_from_the_off_box_copy():
    drill = read(DRILL)
    assert "--from-spaces" in drill
    assert "s3cmd" in drill and " get " in drill


def test_the_data_flow_map_names_spaces():
    assert re.search(r"^\|[^|\n]*Spaces[^|\n]*BLR1", read(MAP), re.MULTILINE), "no Spaces row"


def test_a_deploy_installs_a_changed_backup_script():
    """cron.daily runs a copy, so checking out a tag leaves the old script running."""
    text = read(DEPLOY)
    installs = text.count("cmp -s deploy/backup.sh /etc/cron.daily/scope-backup")
    units = text.count("cmp -s deploy/scope.service /etc/systemd/system/scope.service")
    assert units >= 4 and installs == units, f"{installs} backup installs for {units} unit installs"


def test_the_map_says_the_weekly_images_hold_the_key_too():
    """DigitalOcean's weekly image is of the whole disk, so /etc/scope/ is in it as well."""
    rows = [line for line in read(MAP).splitlines() if line.startswith("| Weekly droplet backups")]
    assert len(rows) == 1 and "whole disk" in rows[0] and "/etc/scope/" in rows[0], rows
    assert "never in the repo or in backups" not in read(MAP)
