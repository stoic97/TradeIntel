# Runbook — putting Scope on a server

ADR-007 fixes the shape: one DigitalOcean Basic Droplet in Bangalore, under a
product-only account, Caddy and Let's Encrypt in front, systemd behind, daily
droplet backups. Everything below follows from that.

**First run: 21 October 2026**, on the cheapest Basic droplet (512 MB, 10 GB) in
BLR1, which is comfortable for a few dozen invited traders. Everything below has
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
    sudo -u scope env $(grep -v '^#' /etc/scope/scope.env | xargs) \
        .venv/bin/python -m services.production.api.cli invite --code <code>

The invite command prints a `127.0.0.1` URL because it has no idea what hostname
it is reachable at. Substitute the real one.

## 5. Backups and the drill

    cp deploy/backup.sh /etc/cron.daily/scope-backup

Run `deploy/restore-drill.sh` by hand the first time, then monthly. It restores
the latest backup into `/tmp` and decrypts one stored file with the live key —
the part a database-only check misses.

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

## What this does not cover

Postgres (ADR-005, Phase 1), a second app process, log shipping, uptime
monitoring. Each is additive; none is needed for a handful of invited traders.
