# Runbook — putting Scope on a server, and every deploy after

*v2, 14 November 2026. Sections 1–6 put Scope on a new box, once. **Every deploy after
that is the release train** (below, after Staging): production runs only a tag that a
person has checked on staging, never `main`, and every deploy is logged in
`docs/runbooks/deploys.md`.*

ADR-007 fixes the shape: one DigitalOcean Basic Droplet in Bangalore, under a
product-only account, Caddy and Let's Encrypt in front, systemd behind, daily
droplet backups. Everything below follows from that.

**First run: 21 October 2026**, on the cheapest Basic droplet (512 MB, 10 GB) in
BLR1, which is comfortable for a few dozen traders. Everything below has
been done once and the corrections that run produced are folded in. Expect to
correct a line or two anyway, and commit the correction.

## Before you start

- A DigitalOcean account that holds nothing but this product.
- DNS for `scope.plusev.in` pointing at the droplet. Without it, use the
  self-signed block at the bottom of `deploy/Caddyfile` and reach the box by IP.
- Two secrets, generated on the box and never in the repository: the session key
  and the file key.

## 1. The box

Basic droplet, Bangalore (BLR1), Ubuntu LTS. Enable **daily backups** when you
create it — the consent text's 30-day sentence depends on them existing.

    apt update && apt upgrade -y
    apt install -y git curl ufw sqlite3 debian-keyring debian-archive-keyring apt-transport-https
    ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw --force enable

`sqlite3` is not optional: `backup.sh` takes the backup with the sqlite CLI's
`.backup`, and without it `cron.daily` fails with "command not found" — a
backup that silently never happens.

If `apt upgrade` asks about `sshd_config`, **keep the version currently
installed**. The image's SSH config is deliberately key-only; the maintainer's
version would replace it, and you would find out on the next reboot.

On a 512 MB droplet, add swap before installing anything. The app does not need
it — it runs in about 100 MB — but the install does, and an OOM-killed
`uv sync` leaves you guessing.

    fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab

Caddy, which Ubuntu ships at 2.6.2; the project's own repository is current:

    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" > /etc/apt/sources.list.d/caddy-stable.list
    apt update && apt install -y caddy

Then the user and the directories:

    adduser --system --group --home /srv/scope scope
    mkdir -p /srv/scope/data/files /etc/scope /var/backups/scope
    chown -R scope:scope /srv/scope
    chmod 700 /etc/scope

## 2. The keys

Generate both on the box, into `/etc/scope/scope.env`, mode 0600. The session
key first; the file key after step 3, because it needs the project's own
`cryptography` and a 512 MB box does not want a second Python stack installed
system-wide just to generate one string:

    SCOPE_SECRET_KEY   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
    SCOPE_FILE_KEY     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    SCOPE_DB           sqlite:////srv/scope/data/scope.db
    SCOPE_FILES        /srv/scope/data/files
    SCOPE_PRODUCTION   1
    ADMIN_LOGIN_IDS    <login ids, comma-separated, no spaces>

`ADMIN_LOGIN_IDS` names who may open `/admin`. Unset or empty means nobody: the app
still starts and the page is a 404 for everyone. A login id on the list cannot be
taken at sign-up by anyone, because whoever held it would be an admin. So sign up
first, then add the id here and restart: a change takes effect on restart.

A team member's new account is classified the same day, so `/admin` counts traders only:
`.venv/bin/python -m services.production.api.cli --db <SCOPE_DB> classify --login-id <login id> --development-data`.

**Put the file key in the password manager before anything is uploaded.** Lose it
and every stored tradebook is unreadable — Fernet authenticates, so the app
refuses them rather than returning rubbish, which is correct and no comfort.

`SCOPE_PRODUCTION=1` makes the import path refuse an unverified broker file map
(TD-024). That is deliberate: it refuses until someone has checked the Dhan
export against Dhan's own interface.

## 3. The code

    curl -LsSf https://astral.sh/uv/install.sh | sh    # installs to /root/.local/bin
    cp /root/.local/bin/uv /usr/local/bin/uv
    git clone <repo> /srv/scope && cd /srv/scope

uv's interpreter must not live under `/root`. The service runs as `scope`,
`/root` is 0700, and the venv's `python` is a symlink into it — so the service
fails with `203/EXEC` and "Permission denied" on `.venv/bin/python`, which reads
like a problem with the venv rather than with where the interpreter went:

    mkdir -p /opt/uv/python
    UV_PYTHON_INSTALL_DIR=/opt/uv/python uv python install 3.11
    chmod -R a+rX /opt/uv
    UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research
    chown -R scope:scope /srv/scope

Now the file key, from the project's own environment:

    uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

The research group is not installed on the server: it is the Bayesian stack, the
product does not import it, and leaving it out keeps the box small.

## 4. Run it

    cp deploy/scope.service /etc/systemd/system/
    systemctl daemon-reload && systemctl enable --now scope
    systemctl status scope

Startup takes about five seconds on the smallest droplet — the migration check
and the framework read on one shared vCPU. A `curl` fired straight after a
restart returns 502 with nothing whatever wrong; wait for "Application startup
complete" in `journalctl -u scope`.

    cp deploy/Caddyfile /etc/caddy/Caddyfile
    systemctl reload caddy

Then, as the `scope` user with the environment loaded. `/etc/scope` is 0700 and
root-owned, so root reads the file and passes it in:

    sudo -u scope env $(grep -v '^#' /etc/scope/scope.env | xargs) \
        .venv/bin/python -m services.production.api.cli init-db

Sign-up is open at the site's front door, so there is nothing to mint.

## 5. Backups and the drill

    cp deploy/backup.sh /etc/cron.daily/scope-backup

Run `deploy/restore-drill.sh` by hand the first time, then monthly. It restores
the latest backup into `/tmp` and decrypts one stored file with the live key —
the part a database-only check misses.

## Staging

A second Scope on the same droplet, so a person can check a change before a trader
sees it: `https://staging.scope.plusev.in`, behind a browser password (founder's
password manager), on port 8001, in `/srv/scope-staging`, with its own database and
session key. It runs `main`; production does not.

Refresh it by hand, as root, right before testing — never on a timer:

    /srv/scope-staging/deploy/refresh-staging.sh

It restores the newest backup from `/var/backups/scope` into staging, checks out
`origin/main`, starts `scope-staging`, and prints the version it runs. Migrations
newer than production apply at startup, as they do in production. First install is
the numbered block at the top of the script. Staging is never backed up; it is
rebuilt from production's backups on every refresh. `deploy/scope-staging.service`
can write only `/srv/scope-staging/data`.

## The release train — every deploy after the first

Seven steps, in this order, each by the person named. A block is pasted whole, after its
placeholder line (`TAG=`, `SHA=`, `PREV=`, `RP=`, right under the `cd`) is filled with
the real value; never paste one with an example value still in it. An SSH session idle for half an
hour is reset: reconnect before pasting, or the block runs on your laptop.

| Step | Who | Where |
|---|---|---|
| a. Refresh staging | the tester | droplet, root |
| b. UAT on staging | the tester (never the author of a ticket they check) | browser |
| c. Tag | **the founder only**, after a Pass is recorded | laptop |
| d. Deploy the tag | founder (or whoever the founder names) | droplet, root |
| e. Check production | same person | droplet and browser |
| f. Log it | same person | `docs/runbooks/deploys.md` |
| g. Tell the traders | customer team | the loop tracker |

### a. Refresh staging from `main`

    /srv/scope-staging/deploy/refresh-staging.sh

Expected, last lines:

    ==> 9/9 check /health through Caddy
    without the password: 401, as it must be
    from the app on :8001: {"status":"ok","code_version":"3f2a1bc"}

    Staging is refreshed and running 3f2a1bc.

That sha is **what will be tagged**. Write it at the top of the train page. If the script
stops, it names the step; fix that before anyone tests.

### b. UAT on staging

The tester works through every ticket on the train against its gate, then the fixed pass
in `docs/runbooks/uat-smoke.md` on a phone and a laptop. Results go in the loop tracker
(feedback-loop repo: `tracker/record_verify.py`, Verify result Pass / Fail / Can't
check), on the train page (`trains/<date>.md`), and as a `uat-pass` / `uat-fail` label on
each Jira ticket. The tester's page there, `onboarding/tester.md`, is the whole station.

Nothing is tagged until every ticket on the train has a result and the smoke pass is a
Pass on both devices. A Fail does not stop the train if the founder takes that ticket off
it: its fix rides the next train.

### c. Tag the sha that passed (founder only)

On the founder's laptop, in a clean clone. Tag the sha staging ran in step a, not
whatever `main` is now: `main` may have moved since the test.

    SHA=3f2a1bc; TAG=v2026.11.14; MSG="train: TICKET-..., TICKET-..."
    git fetch --quiet origin
    git merge-base --is-ancestor "$SHA" origin/main && echo "on main"
    git tag -a "$TAG" -m "$MSG" "$SHA"
    git push origin "$TAG"

Expected: `on main`, then `* [new tag]  v2026.11.14 -> v2026.11.14`. A second train the
same day is `v2026.11.14.2`. Tags are annotated and are never moved or deleted once
pushed; a wrong tag is fixed by a new one.

### d. Deploy the tag

Every block starts with `cd /srv/scope || exit 1`, so pasted in the wrong window it does
nothing. First, where production is and what the tag changes:

    cd /srv/scope || exit 1
    TAG=v2026.11.14
    git status --short
    git fetch --quiet --tags origin
    LIVE=$(git describe --tags --exact-match 2>/dev/null || git rev-parse --short HEAD); echo "live: $LIVE"
    git diff --stat "$LIVE" "$TAG" -- migrations/versions deploy/
    git diff "$LIVE" "$TAG" -- migrations/versions | grep -nE "op\.(drop_|alter_column)" || echo "no destructive migration"

Expected: `git status --short` prints **nothing**. Any line there means someone changed
the box by hand: stop and find out who before going on. `live:` is the previous tag (a
sha only on the first train, or after a deploy that skipped the train). The last line
decides the path: `no destructive migration` → **Path A**; any `drop_`/`alter_column`
line → **Path B**.

Production then sits on a detached HEAD at the tag. That is correct, and `git status
--short` still reports local changes, so the guard above still works. Do not "fix" it
with `git switch main`.

**Path A** (no migration, or only additive ones). Back up the live database, then deploy:

    cd /srv/scope || exit 1
    TAG=v2026.11.14
    RP=/var/backups/scope/scope-$(date -u +%Y%m%dT%H%M%SZ).db
    sqlite3 /srv/scope/data/scope.db ".backup '$RP'" && chmod 600 "$RP" && echo "restore point: $RP"
    git checkout --quiet "$TAG"
    UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research
    cmp -s deploy/scope.service /etc/systemd/system/scope.service || { cp deploy/scope.service /etc/systemd/system/ && systemctl daemon-reload && echo "unit updated"; }
    chown -R scope:scope /srv/scope
    systemctl restart scope

**Path B** (a migration drops or alters something). Stop first, so the snapshot is an
exact restore point; rollback for this release is that snapshot, not a checkout:

    cd /srv/scope || exit 1
    TAG=v2026.11.14
    systemctl stop scope
    sqlite3 /srv/scope/data/scope.db "PRAGMA wal_checkpoint(TRUNCATE);"
    RP=/var/backups/scope/scope-$(date -u +%Y%m%dT%H%M%SZ).db
    sqlite3 /srv/scope/data/scope.db ".backup '$RP'" && chmod 600 "$RP" && echo "restore point: $RP"
    sqlite3 "$RP" "PRAGMA integrity_check;"
    git checkout --quiet "$TAG"
    UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research
    cmp -s deploy/scope.service /etc/systemd/system/scope.service || { cp deploy/scope.service /etc/systemd/system/ && systemctl daemon-reload && echo "unit updated"; }
    chown -R scope:scope /srv/scope
    systemctl start scope

Expected (Path B): `integrity_check` prints `ok`. If it does not, `systemctl start scope`
on the old code (`git checkout "$LIVE"` first if you already moved) and stop the train.

Either path: a changed `scope.service` is not applied by checking out code. The `cmp`
line installs it only when it differs, and says `unit updated` when it did.

### e. Check production

Startup takes about five seconds; a `curl` straight after the restart can answer 502
with nothing wrong.

    cd /srv/scope || exit 1
    journalctl -u scope --since "-3 min" --no-pager | grep -E "Application startup complete|Traceback"
    sqlite3 /srv/scope/data/scope.db "select version_num from alembic_version;"
    ls migrations/versions | sort | tail -1
    curl -s https://scope.plusev.in/health; echo
    curl -s -o /dev/null -w '%{http_code}\n' https://scope.plusev.in/login

Expected: `Application startup complete` and no `Traceback`. The alembic revision matches
the newest migration file (the startup log prints no alembic lines, and `alembic current`
cannot run on its own). `/health` says `"code_version":"v2026.11.14"`, **the tag**: a sha
there means the checkout did not land on the tag. `/login` answers `200`.

### f. Log it

Add the entry at the top of `docs/runbooks/deploys.md`, in the shape the entries there
use: tag, previous tag, time IST, who ran it, the restore point printed in step d, the
alembic revision from step e, the train's ticket ids. Open it as a one-file PR titled
`deploy: v2026.11.14`. No login ids, passwords or keys in it; the repository is public.

### g. Close the loop

Every ticket on the train that passed is now live. The tracker shows those rows at
*6b Verified*; the customer team tells each trader who raised one, as the loop says.

### Rollback

The previous tag is the second line of:

    cd /srv/scope || exit 1
    git tag --sort=-creatordate | head -2

**After Path A** (code only):

    cd /srv/scope || exit 1
    PREV=v2026.11.07
    git checkout --quiet "$PREV"
    UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research
    cmp -s deploy/scope.service /etc/systemd/system/scope.service || { cp deploy/scope.service /etc/systemd/system/ && systemctl daemon-reload && echo "unit updated"; }
    chown -R scope:scope /srv/scope
    systemctl restart scope

An additive migration stays applied; older code ignores the new column or table.

**After Path B** (database restore): the older code expects what the migration removed,
so the restore point goes back with it. Anything written after the snapshot (sign-ups,
uploads) is lost; say so in the log.

    cd /srv/scope || exit 1
    PREV=v2026.11.07; RP=/var/backups/scope/scope-20261114T093000Z.db
    systemctl stop scope
    cp "$RP" /srv/scope/data/scope.db && rm -f /srv/scope/data/scope.db-wal /srv/scope/data/scope.db-shm
    git checkout --quiet "$PREV"
    UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research
    cmp -s deploy/scope.service /etc/systemd/system/scope.service || { cp deploy/scope.service /etc/systemd/system/ && systemctl daemon-reload && echo "unit updated"; }
    chown -R scope:scope /srv/scope
    systemctl start scope

Then step e, and a log entry for the rollback.

### Hotfixes

A bug on the 24-hour clock does not wait for the train, and does not skip staging. Its PR
merges to `main`; staging is refreshed (step a); the author **and one other person** check
it there the same day; the founder tags that sha with the day's next number
(`v2026.11.14.2`) and it deploys by step d like any train, logged by step f. No path
deploys `main` directly.

## 6. Before the first partner uploads

The release gate, PRD section 10. None of it is optional and none of it is code:

1. Re-read `docs/runbooks/data-flow-map.md` against the running box, and remove
   its "not yet verified on a running server" line once it has been.
2. Confirm nothing external is reached: no analytics, no error reporter, no
   outbound client. The repository has none; check the box has none either.
3. Delete a fixture account on the server through the page. Confirm the file is
   gone from `/srv/scope/data/files` and the rows from the database, then note
   the date the last backup holding it ages out, and check it on that date.
4. Have someone who did not write it read the consent text, then set
   `reviewed=True` and bump the version in
   `services/production/accounts/consent.py`. **Until that happens the app
   refuses real accounts on purpose** — a real account reaching `/consent` gets
   the "not open yet" page, by design.

## When uploads are refused

The caps are in `services/production/journal/constants.py`, each with its argument.

- **A trader says uploads are refused for storage:** the disk has passed
  `UPLOADS_REFUSED_AT_DISK_PERCENT`. Nothing alerts on this. It's only in the log:
  `journalctl -u scope | grep "uploads refused"`, and `df -h /srv/scope`.
- **Someone can't sign up behind a shared connection:** the count is in memory, so
  `systemctl restart scope` clears it.

## What this does not cover

Postgres (ADR-005, Phase 1), a second app process, log shipping, uptime
monitoring. Each is additive; none is needed for a handful of traders.
