#!/usr/bin/env bash
# Refresh staging: yesterday's production data on today's main (TICKET-948).
#
# Run as root on the droplet, no arguments, by whoever is about to run UAT:
#     /srv/scope-staging/deploy/refresh-staging.sh
# It prints each step and ends with the version staging now runs. On any failure it
# stops, names the step, and exits non-zero. No cron and no auto-deploy: a refresh in
# the middle of someone's test is worse than a stale staging.
#
# Staging is disposable and is NEVER backed up. /etc/cron.daily/scope-backup backs up
# production only. This script reads production's backups in /var/backups/scope and
# writes nowhere outside /srv/scope-staging.
#
# FIRST INSTALL, once, as root (in this order):
#  1. git clone https://github.com/stoic97/TradeIntel.git /srv/scope-staging
#  2. mkdir -p /srv/scope-staging/data/files
#  3. install -m 600 -o root -g root /dev/null /etc/scope/staging.env
#     and fill it as deploy/staging.env.example says (its own SCOPE_SECRET_KEY; the
#     same SCOPE_FILE_KEY and ADMIN_LOGIN_IDS as production; SCOPE_PRODUCTION=1).
#  4. cp /srv/scope-staging/deploy/scope-staging.service /etc/systemd/system/
#     systemctl daemon-reload && systemctl enable scope-staging
#  5. The browser password for staging. The founder picks it and keeps it in the
#     password manager; only its hash reaches the box:
#       caddy hash-password            # prompts twice, prints the hash
#       mkdir -p /etc/systemd/system/caddy.service.d
#       install -m 600 -o root -g root /dev/null /etc/caddy/staging-auth.env
#       # write two lines into it:  SCOPE_STAGING_USER=<user>   SCOPE_STAGING_HASH=<hash>
#       printf '[Service]\nEnvironmentFile=/etc/caddy/staging-auth.env\n' \
#           > /etc/systemd/system/caddy.service.d/staging-auth.conf
#       systemctl daemon-reload && systemctl restart caddy
#  6. DNS: an A record staging.scope.plusev.in -> the droplet's address (founder, at the
#     registrar). Wait until `dig +short staging.scope.plusev.in` answers it.
#  7. cp /srv/scope-staging/deploy/Caddyfile /etc/caddy/Caddyfile
#     caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && systemctl reload caddy
#     Let's Encrypt issues the certificate on this first reload.
#  8. Run this script.
set -Eeuo pipefail
shopt -s nullglob

# Step 4 rewrites this file (it lives in the checkout it refreshes), and bash reads a
# script as it runs. So run from a copy.
if [ -z "${REFRESH_STAGING_COPY:-}" ]; then
    copy="$(mktemp)"
    cp "$0" "$copy"
    REFRESH_STAGING_COPY="$copy" exec bash "$copy" "$@"
fi
trap 'rm -f "$REFRESH_STAGING_COPY"' EXIT

STAGING=/srv/scope-staging
DATA="$STAGING/data"
BACKUPS=/var/backups/scope
SERVICE=scope-staging
HOST=staging.scope.plusev.in
PORT=8001
STARTUP_SECONDS=90

STEP="checking it runs as root"
trap 'echo "FAILED at step: $STEP" >&2; exit 1' ERR
step() { STEP="$1"; echo; echo "==> $1"; }
fail() { echo "$1" >&2; false; }

[ "$(id -u)" -eq 0 ] || fail "Run as root."
[ -d "$STAGING/.git" ] || fail "$STAGING is not a checkout; see FIRST INSTALL at the top of this file."

step "1/9 stop $SERVICE"
systemctl stop "$SERVICE"
echo "stopped"

step "2/9 restore the newest database backup"
dbs=("$BACKUPS"/scope-*.db)
[ ${#dbs[@]} -gt 0 ] || fail "No $BACKUPS/scope-*.db to restore."
db="${dbs[-1]}"   # names carry a UTC stamp, so the last in sort order is the newest
rm -f "$DATA/scope.db" "$DATA/scope.db-wal" "$DATA/scope.db-shm"
sqlite3 "$DATA/scope.db" ".restore '$db'"
[ "$(sqlite3 "$DATA/scope.db" 'PRAGMA integrity_check;')" = "ok" ] || fail "integrity_check failed on the restored copy."
echo "restored $db"
echo "schema: $(sqlite3 "$DATA/scope.db" 'select version_num from alembic_version;')"

step "3/9 restore the newest file store"
tars=("$BACKUPS"/files-*.tar.gz)
[ ${#tars[@]} -gt 0 ] || fail "No $BACKUPS/files-*.tar.gz to restore."
tarball="${tars[-1]}"
rm -rf "$DATA/files"
tar -xzf "$tarball" -C "$DATA"   # the archive holds files/, as backup.sh writes it
[ -d "$DATA/files" ] || fail "$tarball held no files/ directory."
echo "restored $tarball ($(find "$DATA/files" -type f | wc -l) files)"

step "4/9 check out origin/main"
git -c safe.directory="$STAGING" -C "$STAGING" fetch --quiet --tags origin
git -c safe.directory="$STAGING" -C "$STAGING" checkout --quiet --force --detach origin/main
echo "at $(git -c safe.directory="$STAGING" -C "$STAGING" log -1 --format='%h %s')"

step "5/9 install dependencies"
(cd "$STAGING" && UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research)

step "6/9 hand the checkout to the scope user"
chown -R scope:scope "$STAGING"
echo "done"

step "7/9 start $SERVICE"
since="$(date '+%Y-%m-%d %H:%M:%S')"
systemctl start "$SERVICE"
echo "started"

step "8/9 wait for Application startup complete"
started_up() {   # the log first, then grep: grep -q quitting early must not fail a pipe
    local log
    log="$(journalctl -u "$SERVICE" --since "$since" --no-pager -q)"
    grep -q "Application startup complete" <<<"$log"
}
for _ in $(seq "$STARTUP_SECONDS"); do
    started_up && break
    sleep 1
done
started_up || fail "No 'Application startup complete' within ${STARTUP_SECONDS}s. Read: journalctl -u $SERVICE --since '$since'"
echo "up (migrations newer than production applied at startup, as in production)"

step "9/9 check /health through Caddy"
code="$(curl -s -o /dev/null -w '%{http_code}' --resolve "$HOST:443:127.0.0.1" "https://$HOST/health")"
[ "$code" = "401" ] || fail "https://$HOST/health without the password answered $code, not 401."
echo "without the password: 401, as it must be"
if [ -n "${STAGING_AUTH:-}" ]; then   # user:password, if the person running this has it to hand
    body="$(curl -sf -u "$STAGING_AUTH" --resolve "$HOST:443:127.0.0.1" "https://$HOST/health")"
    echo "through Caddy with the password: $body"
else
    body="$(curl -sf "http://127.0.0.1:$PORT/health")"
    echo "from the app on :$PORT: $body"
fi
version="$(printf '%s' "$body" | grep -o '"code_version": *"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/' || true)"
[ -n "$version" ] || fail "/health carried no code_version."

echo
echo "Staging is refreshed and running $version."
echo "Write that version at the top of the train page."
