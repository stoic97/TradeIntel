#!/usr/bin/env bash
# Nightly backup of the database and the encrypted file store, kept on the droplet and
# copied off it.
#
# DigitalOcean's droplet backup already copies the whole disk weekly. This exists
# because a disk-level copy of a live SQLite database in WAL mode can catch it
# mid-write, because a restore drill needs something smaller than a whole droplet to
# practise on, and because a copy kept only on the droplet is lost with the droplet or
# its account. So each night's copy also goes to a Spaces bucket in BLR1, under the
# same product-only account (TICKET-941).
#
# The encryption key is NOT backed up here, deliberately: a backup holding both
# the encrypted files and the key that opens them is one theft, not two. The key
# lives in /etc/scope/ and in the founder's password manager. The stored files are
# encrypted already; the database copy is encrypted with the same key before it
# leaves the droplet, and the key itself never leaves.
#
# Install: cp deploy/backup.sh /etc/cron.daily/scope-backup (deploy.md, section 5;
# every deploy re-installs a changed copy). The off-box copy needs /etc/scope/s3cfg
# (s3cmd's keys) and /etc/scope/spaces.env (SCOPE_SPACES=s3://<bucket>/scope).
# Without them the local copy is still made, and the script exits non-zero, so a
# missed off-box copy is not silent.
set -euo pipefail

DATA=${SCOPE_DATA:-/srv/scope/data}
DEST=${SCOPE_BACKUPS:-/var/backups/scope}
APP=${SCOPE_APP:-/srv/scope}
KEYS=${SCOPE_ENV_FILE:-/etc/scope/scope.env}
S3CFG=${SCOPE_S3CFG:-/etc/scope/s3cfg}
[ -r /etc/scope/spaces.env ] && . /etc/scope/spaces.env
SPACES=${SCOPE_SPACES:-}

# The consent text promises that backups roll off within 30 days. cron.daily runs this
# once a day, so a copy removed once it is older than 29 days is gone before it is 30.
# These lines keep that promise, so changing them changes a promise.
KEEP_DAYS=${SCOPE_BACKUP_DAYS:-29}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
CUTOFF=$(date -u -d "-$KEEP_DAYS days" +%Y%m%dT%H%M%SZ)

mkdir -p "$DEST"

# .backup takes a consistent snapshot of a live database. cp does not.
sqlite3 "$DATA/scope.db" ".backup '$DEST/scope-$STAMP.db'"

tar -czf "$DEST/files-$STAMP.tar.gz" -C "$DATA" files

chmod 600 "$DEST/scope-$STAMP.db" "$DEST/files-$STAMP.tar.gz"

find "$DEST" -name 'scope-*.db' -mmin "+$((KEEP_DAYS * 1440))" -delete
find "$DEST" -name 'files-*.tar.gz' -mmin "+$((KEEP_DAYS * 1440))" -delete

echo "backed up to $DEST at $STAMP; keeping $KEEP_DAYS days"

if [ -z "$SPACES" ] || [ ! -r "$S3CFG" ]; then
  echo "OFF-BOX COPY NOT MADE: no SCOPE_SPACES in /etc/scope/spaces.env, or no $S3CFG (deploy.md, section 5)" >&2
  exit 1
fi

# The database copy is encrypted with the file key, Fernet as the file store uses.
# The interpreter reads the key from the env file itself, so it never passes through
# this shell, an argument or the bucket. The project's own interpreter, not `uv run`
# (see restore-drill.sh).
ENC="$DEST/scope-$STAMP.db.enc"
trap 'rm -f "$ENC"' EXIT
"$APP/.venv/bin/python" - "$KEYS" "$DEST/scope-$STAMP.db" "$ENC" <<'PY'
import sys
from pathlib import Path

from cryptography.fernet import Fernet

keys, src, dst = (Path(a) for a in sys.argv[1:4])
pairs = (line.partition("=") for line in keys.read_text().splitlines())
key = next(v.strip().strip("\"'") for k, _, v in pairs if k.strip() == "SCOPE_FILE_KEY")
dst.write_bytes(Fernet(key.encode()).encrypt(src.read_bytes()))
dst.chmod(0o600)
PY

s3cmd -c "$S3CFG" --quiet put "$ENC" "$SPACES/scope-$STAMP.db.enc"
s3cmd -c "$S3CFG" --quiet put "$DEST/files-$STAMP.tar.gz" "$SPACES/files-$STAMP.tar.gz"

# Copies in Spaces go by the same clock as the ones here. The bucket's 30-day
# lifecycle rule is the backstop: it rounds expiry up to midnight UTC, so on its own
# it could keep a copy past 30 days.
s3cmd -c "$S3CFG" ls "$SPACES/" | awk '{print $NF}' | while read -r url; do
  name=${url##*/}
  case "$name" in scope-*.db.enc|files-*.tar.gz) ;; *) continue ;; esac
  stamp=${name#*-}; stamp=${stamp%%.*}
  if [[ "$stamp" < "$CUTOFF" ]]; then s3cmd -c "$S3CFG" --quiet del "$url"; fi
done

echo "copied off the droplet to $SPACES at $STAMP; Spaces copies older than $KEEP_DAYS days removed"
