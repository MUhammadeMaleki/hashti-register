#!/usr/bin/env bash
set -euo pipefail
umask 077

# Requires PGHOST/PGPORT/PGUSER/PGPASSFILE and a dedicated backup role.
# Quiesce writes or use a coordinated database/filesystem snapshot for a
# consistent database+uploads pair. Never place PGPASSWORD in this script.
: "${HASHTI_BACKUP_DB:?Set the database name}"
: "${HASHTI_BACKUP_ROOT:?Set a private backup directory}"
: "${HASHTI_UPLOADS_DIR:?Set the shared absolute uploads directory}"
[[ "$HASHTI_UPLOADS_DIR" = /* && "$HASHTI_BACKUP_ROOT" = /* ]] || {
    echo 'Backup paths must be absolute' >&2; exit 1;
}
[[ "$(basename "$HASHTI_UPLOADS_DIR")" = uploads ]] || {
    echo 'Uploads directory must end in /uploads' >&2; exit 1;
}
[[ -d "$HASHTI_UPLOADS_DIR" ]] || { echo 'Uploads directory missing' >&2; exit 1; }
mkdir -p -- "$HASHTI_BACKUP_ROOT"
backup_dir="$HASHTI_BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -- "$backup_dir"
date -u +%Y-%m-%dT%H:%M:%SZ > "$backup_dir/started_at_utc"
pg_dump --format=custom --no-owner --no-acl --file="$backup_dir/database.dump" "$HASHTI_BACKUP_DB"
tar -C "$(dirname "$HASHTI_UPLOADS_DIR")" -cf "$backup_dir/uploads.tar" "$(basename "$HASHTI_UPLOADS_DIR")"
pg_restore --list "$backup_dir/database.dump" > "$backup_dir/database.list"
tar -tf "$backup_dir/uploads.tar" > "$backup_dir/uploads.list"
(cd -- "$backup_dir" && sha256sum database.dump uploads.tar > SHA256SUMS)
date -u +%Y-%m-%dT%H:%M:%SZ > "$backup_dir/finished_at_utc"
printf 'Backup verified: %s\n' "$backup_dir"
