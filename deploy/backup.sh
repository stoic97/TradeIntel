#!/usr/bin/env bash
# Daily backup of the database and the encrypted file store.
#
# DigitalOcean's droplet backup already copies the whole disk nightly. This exists
# because a disk-level copy of a live SQLite database in WAL mode can catch it
# mid-write, and because a restore drill needs something smaller than a whole
# droplet to practise on.
#
# The encryption key is NOT backed up here, deliberately: a backup holding both
# the encrypted files and the key that opens them is one theft, not two. The key
# lives in /etc/scope/ and in the founder's password manager.
#
# Install: /etc/cron.daily/scope-backup -> this file.
set -euo pipefail

DATA=${SCOPE_DATA:-/srv/scope/data}
DEST=${SCOPE_BACKUPS:-/var/backups/scope}
KEEP_DAYS=${SCOPE_BACKUP_DAYS:-30}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

mkdir -p "$DEST"

# .backup takes a consistent snapshot of a live database. cp does not.
sqlite3 "$DATA/scope.db" ".backup '$DEST/scope-$STAMP.db'"

tar -czf "$DEST/files-$STAMP.tar.gz" -C "$DATA" files

chmod 600 "$DEST/scope-$STAMP.db" "$DEST/files-$STAMP.tar.gz"

# The consent text promises 30 days. This is the line that keeps that true, so
# changing it changes a promise.
find "$DEST" -name 'scope-*.db' -mtime "+$KEEP_DAYS" -delete
find "$DEST" -name 'files-*.tar.gz' -mtime "+$KEEP_DAYS" -delete

echo "backed up to $DEST at $STAMP; keeping $KEEP_DAYS days"
