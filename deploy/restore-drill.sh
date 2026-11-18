#!/usr/bin/env bash
# Restore the latest backup into a scratch directory and prove it is usable.
#
# A backup nobody has restored is a hope. This restores into /tmp, opens the
# database, and decrypts one stored file with the real key -- which is the part a
# database-only check misses: the files are encrypted, and a backup you cannot
# decrypt is not a backup of anything.
#
# --from-spaces restores the newest copy in the Spaces bucket instead (TICKET-941):
# it downloads it, decrypts the database copy with the live key, and runs the same
# checks. That is the copy that survives losing the droplet, so it is the one a
# drill has to prove. The key comes from the environment, as below.
#
# It touches nothing in /srv/scope. Run it monthly, alternating the two sources, and
# after any change to the backup script or the key.
set -euo pipefail

DEST=${SCOPE_BACKUPS:-/var/backups/scope}
S3CFG=${SCOPE_S3CFG:-/etc/scope/s3cfg}
[ -r /etc/scope/spaces.env ] && . /etc/scope/spaces.env
SPACES=${SCOPE_SPACES:-}
WORK=$(mktemp -d /tmp/scope-restore-XXXXXX)
trap 'rm -rf "$WORK"' EXIT

if [ "${1:-}" = "--from-spaces" ]; then
  [ -n "$SPACES" ] && [ -r "$S3CFG" ] || { echo "no SCOPE_SPACES or no $S3CFG: see deploy.md, section 5"; exit 1; }
  ENC=$(s3cmd -c "$S3CFG" ls "$SPACES/" | awk '{print $NF}' | grep '/scope-.*\.db\.enc$' | sort | tail -1 || true)
  [ -n "$ENC" ] || { echo "no backup found in $SPACES"; exit 1; }
  STAMP=${ENC##*/scope-}; STAMP=${STAMP%%.*}
  echo "downloading $ENC and $SPACES/files-$STAMP.tar.gz"
  s3cmd -c "$S3CFG" --quiet get "$ENC" "$WORK/download.db.enc"
  s3cmd -c "$S3CFG" --quiet get "$SPACES/files-$STAMP.tar.gz" "$WORK/download.tar.gz"
  /srv/scope/.venv/bin/python - "$WORK/download.db.enc" "$WORK/download.db" <<'PY'
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

src, dst = (Path(a) for a in sys.argv[1:3])
dst.write_bytes(Fernet(os.environ["SCOPE_FILE_KEY"].encode()).decrypt(src.read_bytes()))
print(f"the database copy decrypts with the live key: {dst.stat().st_size} bytes")
PY
  DB="$WORK/download.db"
  FILES="$WORK/download.tar.gz"
else
  DB=$(ls -1t "$DEST"/scope-*.db 2>/dev/null | head -1)
  FILES=$(ls -1t "$DEST"/files-*.tar.gz 2>/dev/null | head -1)
  [ -n "$DB" ] && [ -n "$FILES" ] || { echo "no backup found in $DEST"; exit 1; }
fi

echo "restoring $DB and $FILES into $WORK"
cp "$DB" "$WORK/scope.db"
tar -xzf "$FILES" -C "$WORK"

echo "--- the database opens, and has the tables it should"
sqlite3 "$WORK/scope.db" "select count(*) || ' tables' from sqlite_master where type='table';"
sqlite3 "$WORK/scope.db" "select 'imports: ' || count(*) from \"import\";"

echo "--- a stored file decrypts with the live key"
# The project's own interpreter, not `uv run`. uv rebuilds the editable install
# and leaves venv files owned by whoever ran the drill -- root, from cron.daily --
# and the service then cannot start. A monthly drill that breaks the thing it is
# meant to reassure you about is worse than no drill.
cd /srv/scope
SCOPE_FILES="$WORK/files" .venv/bin/python - <<'PY'
import os
from pathlib import Path
from services.production.accounts.file_store import FileStore

root = Path(os.environ["SCOPE_FILES"])
blobs = sorted(root.glob("*.enc"))
if not blobs:
    print("no files in the backup yet: nothing to decrypt, which is fine on a new box")
    raise SystemExit(0)

store = FileStore(root, os.environ["SCOPE_FILE_KEY"])
digest = blobs[0].stem
content = store.get(digest)
print(f"decrypted {digest[:12]}...: {len(content)} bytes")
PY

echo "--- restore drill passed. Record the date as a line in /srv/scope/data/deletion-log.md on the server (never in git)."
