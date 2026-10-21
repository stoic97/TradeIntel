# Runbook — putting Scope on a server

ADR-007 fixes the shape: one DigitalOcean Basic Droplet in Bangalore, under a
product-only account, Caddy and Let's Encrypt in front, systemd behind, daily
droplet backups. Everything below follows from that.

**Nothing here has been run yet.** It is written from the code and the ADR, and
the first person to follow it should expect to correct a line or two and commit
the correction.

## Before you start

- A DigitalOcean account that holds nothing but this product.
- DNS for `scope.plusev.in` pointing at the droplet. Without it, use the
  self-signed block at the bottom of `deploy/Caddyfile` and reach the box by IP.
- Two secrets, generated on the box and never in the repository: the session key
  and the file key.

## 1. The box

Basic droplet, Bangalore (BLR1), Ubuntu LTS. Enable **daily backups** when you
create it — the consent text's 30-day sentence depends on them existing.

    adduser --system --group --home /srv/scope scope
    mkdir -p /srv/scope/data/files /etc/scope /var/backups/scope
    chown -R scope:scope /srv/scope
    chmod 700 /etc/scope

## 2. The keys

Generate both on the box, into `/etc/scope/scope.env`, mode 0600:

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

    curl -LsSf https://astral.sh/uv/install.sh | sh    # to /usr/local/bin/uv
    git clone <repo> /srv/scope && cd /srv/scope
    uv sync --frozen --no-group research

The research group is not installed on the server: it is the Bayesian stack, the
product does not import it, and leaving it out keeps the box small.

## 4. Run it

    cp deploy/scope.service /etc/systemd/system/
    systemctl daemon-reload && systemctl enable --now scope
    systemctl status scope

    cp deploy/Caddyfile /etc/caddy/Caddyfile
    systemctl reload caddy

Then, as the `scope` user with the environment loaded:

    python -m services.production.api.cli init-db
    python -m services.production.api.cli invite --code <code-for-the-first-partner>

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
