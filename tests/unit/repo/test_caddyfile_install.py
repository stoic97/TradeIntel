"""TICKET-1016: a changed deploy/Caddyfile is installed by a person, before the deploy window.

Caddy serves production as well as staging, so no deploy script installs its config. The
runbook holds the one way to do it: validate the exact file the tag will carry, with staging's
credentials loaded the way systemd loads them, keep the old file, reload, check both sites at
once, and log it. A plain ``caddy validate`` in a root shell checks a different config (the
staging block reads its user and hash from the environment), so the runbook and the
first-install note both load the file first.
"""
from pathlib import Path

DEPLOY = Path("docs/runbooks/deploy.md").read_text(encoding="utf-8")
TRAIN = DEPLOY[DEPLOY.index("## The release train"):DEPLOY.index("## 6. Before the first partner uploads")]
STAGING_SCRIPT = Path("deploy/refresh-staging.sh").read_text(encoding="utf-8")
LOAD = "set -a; . /etc/caddy/staging-auth.env; set +a;"


def section() -> str:
    head = "### When `deploy/Caddyfile` changes"
    assert head in TRAIN, "no Caddyfile section in the release train"
    rest = TRAIN[TRAIN.index(head):]
    end = rest.find("\n### ", 1)
    return rest if end == -1 else rest[:end]


def test_the_install_is_by_hand_and_before_the_deploy_window():
    s = section()
    assert "never by `refresh-staging.sh`" in s
    assert "update.sh" not in s
    assert "before the deploy window" in s


def test_it_validates_the_tags_file_with_stagings_credentials_loaded():
    s = section()
    assert 'git show "$SHA:deploy/Caddyfile"' in s
    assert LOAD in s and "caddy validate" in s


def test_it_keeps_the_old_file_checks_both_sites_and_can_go_back():
    s = section()
    assert "Caddyfile.before-" in s
    assert "https://scope.plusev.in/health" in s
    assert "https://staging.scope.plusev.in/health" in s and "401" in s
    assert "systemctl reload caddy" in s


def test_it_is_logged():
    assert "docs/runbooks/deploys.md" in section()


def test_the_first_install_note_validates_with_the_credentials_loaded():
    validate = [line for line in STAGING_SCRIPT.splitlines() if "caddy validate" in line]
    assert validate and all(LOAD in line for line in validate), validate


# ---------- review, 24 Nov: what a paste must refuse ----------

def _blocks(s: str) -> list[str]:
    """Each indented command block in the section, as one string."""
    out, cur = [], []
    for line in s.splitlines():
        if line.startswith("    "):
            cur.append(line.strip())
        elif cur:
            out.append("\n".join(cur)); cur = []
    if cur:
        out.append("\n".join(cur))
    return out


def test_every_block_that_uses_sha_stops_when_it_is_unfilled():
    for block in _blocks(section()):
        if "$SHA" in block:
            assert 'test -n "$SHA" || exit 1' in block, block


def test_a_failed_git_show_stops_the_paste_before_anything_is_validated():
    s = section()
    assert '> /tmp/Caddyfile.next || exit 1' in s
    assert "test -s /tmp/Caddyfile.next || exit 1" in s


def test_the_bcrypt_hash_is_single_quoted_so_bash_reads_it_as_systemd_does():
    s = section()
    assert "grep -q \"^SCOPE_STAGING_HASH='\" /etc/caddy/staging-auth.env || exit 1" in s
    assert "SCOPE_STAGING_HASH='<hash>'" in STAGING_SCRIPT


def test_the_installed_file_is_validated_before_the_reload():
    s = section()
    live = "caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile ) && systemctl reload caddy"
    assert live in s
