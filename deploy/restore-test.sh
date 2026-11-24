#!/usr/bin/env bash
set -euo pipefail
umask 077

# Requires a PostgreSQL role with CREATEDB, PGHOST/PGPORT/PGUSER/PGPASSFILE.
# Creates a new database and private temporary uploads directory; keeps both
# for inspection. It never restores over an existing database.
backup_dir="${1:?Pass the absolute backup directory}"
[[ "$backup_dir" = /* && -f "$backup_dir/database.dump" && -f "$backup_dir/uploads.tar" ]] || {
    echo 'Complete absolute backup directory required' >&2; exit 1;
}
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
(cd -- "$backup_dir" && sha256sum -c SHA256SUMS)
restore_db="hashti_restore_$(date -u +%Y%m%d%H%M%S)_$$"
restore_dir="$(mktemp -d)"
createdb --maintenance-db=postgres "$restore_db"
printf 'Temporary database: %s\nTemporary files: %s\n' "$restore_db" "$restore_dir"
pg_restore --exit-on-error --no-owner --no-privileges --dbname="$restore_db" "$backup_dir/database.dump"
tar -xf "$backup_dir/uploads.tar" -C "$restore_dir"
psql -X -v ON_ERROR_STOP=1 -d "$restore_db" -f "$script_dir/verify-restore.sql"
psql -X -A -t -v ON_ERROR_STOP=1 -d "$restore_db" -c \
    "SELECT original_receipt_path FROM payment_submissions WHERE original_receipt_path IS NOT NULL
     UNION SELECT display_receipt_path FROM payment_submissions WHERE display_receipt_path IS NOT NULL" |
while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    [[ "$name" != */* && "$name" != '..' ]] || { echo 'Unsafe receipt path' >&2; exit 1; }
    [[ -f "$restore_dir/uploads/receipts/$name" ]] || { echo 'Missing receipt file' >&2; exit 1; }
done
psql -X -A -t -v ON_ERROR_STOP=1 -d "$restore_db" -c \
    "SELECT poster_path FROM events WHERE poster_path IS NOT NULL" |
while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    [[ "$name" != */* && "$name" != '..' ]] || { echo 'Unsafe poster path' >&2; exit 1; }
    [[ -f "$restore_dir/uploads/posters/$name" ]] || { echo 'Missing poster file' >&2; exit 1; }
done
printf 'Restore checks passed. Review and remove the temporary database/files manually.\n'
