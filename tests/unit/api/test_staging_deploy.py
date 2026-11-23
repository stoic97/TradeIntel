"""TICKET-948: staging is the production app with five unit lines changed, behind a password,
refreshed by one script that never touches production.

These read the files in deploy/. What only the droplet can show (the 401, the certificate,
yesterday's traders on staging) is checked on the box, in the PR.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path("deploy")
SCRIPT = DEPLOY / "refresh-staging.sh"


def _directives(path):
    """A unit's settings, comments dropped, continuation lines joined."""
    text = path.read_text(encoding="utf-8").replace("\\\n", " ")
    lines = [ln.strip() for ln in text.splitlines()]
    return [re.sub(r"\s+", " ", ln) for ln in lines if ln and not ln.startswith("#")]


def _key(line):
    return line.split("=", 1)[0]


def test_the_staging_unit_differs_from_production_in_the_five_permitted_lines_only():
    prod, staging = _directives(DEPLOY / "scope.service"), _directives(DEPLOY / "scope-staging.service")
    assert [_key(ln) for ln in prod] == [_key(ln) for ln in staging]
    changed = {_key(a) for a, b in zip(prod, staging, strict=True) if a != b}
    assert changed == {"Description", "WorkingDirectory", "EnvironmentFile", "ExecStart", "ReadWritePaths"}


def test_the_staging_unit_can_write_only_its_own_data():
    staging = dict(ln.split("=", 1) for ln in _directives(DEPLOY / "scope-staging.service") if "=" in ln)
    assert staging["ReadWritePaths"] == "/srv/scope-staging/data"
    assert staging["ProtectSystem"] == "strict"
    assert staging["EnvironmentFile"] == "/etc/scope/staging.env"
    assert staging["WorkingDirectory"] == "/srv/scope-staging"
    start = staging["ExecStart"]
    assert start.startswith("/srv/scope-staging/.venv/bin/uvicorn ")
    assert "--port 8001" in start and "--host 127.0.0.1" in start
    # Rate limits count by address (TICKET-847): staging sits behind the same Caddy.
    assert "--proxy-headers --forwarded-allow-ips 127.0.0.1" in start


def test_the_refresh_script_never_names_production_except_its_backups():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "/srv/scope/" not in text
    assert re.findall(r"/srv/scope\b(?!-staging)", text) == []
    assert "/var/backups/scope" in text
    assert "never backed up" in text.lower()


def test_the_refresh_script_does_the_steps_in_order():
    text = SCRIPT.read_text(encoding="utf-8")
    body = text[text.index("set -Eeuo pipefail"):]
    steps = [
        'systemctl stop "$SERVICE"',
        '"$BACKUPS"/scope-*.db',
        'rm -f "$DATA/scope.db"',
        ".restore",
        '"$BACKUPS"/files-*.tar.gz',
        "fetch --quiet --tags origin",
        '--detach "$REF_SHA"',
        "uv sync --frozen --no-group research",
        'chown -R scope:scope "$STAGING"',
        'systemctl start "$SERVICE"',
        "Application startup complete",
        "https://$HOST/health",
    ]
    at = [body.index(s) for s in steps]
    assert at == sorted(at), steps
    assert body.count('step "') == 9
    assert "FAILED at step" in body  # a failure names its step and exits non-zero


def test_the_refresh_script_takes_one_optional_ref_defaulting_to_main():
    """TICKET-1003: no argument keeps today's behaviour; one argument is a tag or sha."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'REF="${1:-origin/main}"' in text
    assert "--detach origin/main" not in text
    assert '--detach "$REF_SHA"' in text


def test_the_ref_is_judged_before_anything_stops():
    """TICKET-1003: a typo must leave staging running what it was running."""
    text = SCRIPT.read_text(encoding="utf-8")
    body = text[text.index("set -Eeuo pipefail"):]
    stop = body.index('systemctl stop "$SERVICE"')
    assert "fetch --quiet --tags --prune origin" in body
    assert body.index("fetch --quiet --tags --prune origin") < stop
    assert "rev-parse --verify --quiet" in body
    assert body.index("rev-parse --verify --quiet") < stop
    assert "merge-base --is-ancestor" in body
    assert body.index("merge-base --is-ancestor") < stop


def test_a_ref_that_does_not_resolve_is_refused():
    body = SCRIPT.read_text(encoding="utf-8")
    assert "does not resolve to a commit" in body
    assert "Nothing was stopped." in body


def test_a_ref_that_is_not_on_main_is_refused():
    body = SCRIPT.read_text(encoding="utf-8")
    assert 'merge-base --is-ancestor "$REF_SHA" origin/main' in body
    assert "is not on origin/main" in body


def test_both_refusals_name_the_step():
    body = SCRIPT.read_text(encoding="utf-8")
    assert 'STEP="checking the ref"' in body
    assert "FAILED at step" in body


def test_step_4_names_and_prints_the_commit_it_checked_out():
    body = SCRIPT.read_text(encoding="utf-8")
    assert 'step "4/9 check out $REF"' in body
    assert "log -1 --format='%h %s'" in body


def test_the_last_line_says_which_ref_staging_runs():
    body = SCRIPT.read_text(encoding="utf-8")
    assert 'echo "Staging is refreshed and running $version (origin/main)."' in body
    assert 'echo "Staging is refreshed and running $version (ref $REF, not main)."' in body


def test_a_ref_can_be_checked_without_changing_anything():
    """The droplet rehearsal: judge the ref, stop before step 1/9."""
    text = SCRIPT.read_text(encoding="utf-8")
    body = text[text.index("set -Eeuo pipefail"):]
    assert "REFRESH_STAGING_CHECK_ONLY" in body
    assert body.index("REFRESH_STAGING_CHECK_ONLY") < body.index('systemctl stop "$SERVICE"')


def test_the_script_still_sets_up_no_automatic_refresh():
    low = SCRIPT.read_text(encoding="utf-8").lower()
    for banned in ("oncalendar", "crontab", "systemd-run", ".timer"):
        assert banned not in low, banned

def test_the_refresh_script_parses():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash here")
    subprocess.run([bash, "-n", str(SCRIPT)], check=True)


def _block(caddyfile, host):
    start = caddyfile.index(f"\n{host} {{")
    depth, i = 0, caddyfile.index("{", start)
    for j in range(i, len(caddyfile)):
        depth += {"{": 1, "}": -1}.get(caddyfile[j], 0)
        if depth == 0:
            return caddyfile[i:j + 1]
    raise AssertionError("unbalanced")


def test_every_staging_path_sits_behind_the_password_robots_included():
    caddy = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    block = _block(caddy, "staging.scope.plusev.in")
    assert "basic_auth {" in block
    assert block.index("basic_auth") < block.index("handle /robots.txt") < block.index("reverse_proxy")
    assert "reverse_proxy 127.0.0.1:8001" in block
    assert "Disallow: /" in block
    prod = _block(caddy, "scope.plusev.in")
    for header in re.findall(r"^\t\t(\S+) ", prod[prod.index("header {"):], flags=re.MULTILINE):
        assert f"\t\t{header} " in block, header


def test_no_password_hash_is_committed():
    caddy = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    assert re.search(r"\$2[aby]\$\d\d\$", caddy) is None
    assert "{$SCOPE_STAGING_USER} {$SCOPE_STAGING_HASH}" in caddy


def test_the_env_example_names_every_setting_with_a_comment_and_no_real_value():
    lines = (DEPLOY / "staging.env.example").read_text(encoding="utf-8").splitlines()
    settings = {}
    for n, line in enumerate(lines):
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            settings[key] = value
            assert lines[n - 1].startswith("#"), f"{key} has no comment above it"
    assert set(settings) == {"SCOPE_SECRET_KEY", "SCOPE_FILE_KEY", "SCOPE_DB", "SCOPE_FILES",
                             "SCOPE_PRODUCTION", "ADMIN_LOGIN_IDS", "SCOPE_MARKET_DIR"}
    # TICKET-997: staging reads production's day files; its unit can write only its own data.
    assert settings["SCOPE_MARKET_DIR"] == "/srv/scope/data/market"
    assert settings["SCOPE_PRODUCTION"] == "1"
    assert settings["SCOPE_DB"] == "sqlite:////srv/scope-staging/data/scope.db"
    assert settings["SCOPE_FILES"] == "/srv/scope-staging/data/files"
    for key in ("SCOPE_SECRET_KEY", "SCOPE_FILE_KEY", "ADMIN_LOGIN_IDS"):
        assert "-" in settings[key] and len(settings[key]) < 45, f"{key} looks like a real value"
