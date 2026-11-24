#!/usr/bin/env bash
set -euo pipefail
umask 077

[[ "$(id -u)" == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
: "${HASHTI_RELEASE_ID:?Set the release commit ID}"
[[ "$HASHTI_RELEASE_ID" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid release ID.' >&2; exit 1; }
archive="/root/hashti-${HASHTI_RELEASE_ID}.tar"
release="/srv/hashti/releases/${HASHTI_RELEASE_ID}"
[[ -f "$archive" && ! -e "$release" ]] || { echo 'Release archive missing or release exists.' >&2; exit 1; }
[[ ! -e /etc/hashti/hashti.env ]] || { echo 'Production env already exists; refusing first-time setup.' >&2; exit 1; }

install -d -m 0755 "$release"
tar -xf "$archive" -C "$release"
db_password="$(openssl rand -hex 32)"
auth_secret="$(openssl rand -hex 32)"
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -v password="$db_password" postgres <<'SQL'
CREATE ROLE hashti_app LOGIN PASSWORD :'password';
CREATE DATABASE hashti OWNER hashti_app;
SQL
install -m 0640 -o root -g hashti /dev/null /etc/hashti/hashti.env
{
  printf 'HASHTI_ENVIRONMENT=production\n'
  printf 'HASHTI_DATABASE_URL=postgresql+psycopg://hashti_app:%s@127.0.0.1:5432/hashti\n' "$db_password"
  printf 'HASHTI_AUTH_SECRET=%s\n' "$auth_secret"
  printf 'HASHTI_PUBLIC_ORIGIN=https://register.ihashti.ir\n'
  printf 'HASHTI_UPLOADS_DIR=/var/lib/hashti/uploads\n'
  printf 'BACKEND_ORIGIN=http://127.0.0.1:8000\n'
  printf 'NEXT_TELEMETRY_DISABLED=1\n'
} > /etc/hashti/hashti.env
unset db_password auth_secret

UV_PYTHON_INSTALL_DIR=/opt/hashti/python /opt/hashti/uv/bin/uv venv --python 3.12 "$release/backend/.venv"
/opt/hashti/uv/bin/uv pip install --python "$release/backend/.venv/bin/python" -r "$release/backend/requirements.txt"
(
  cd "$release/frontend"
  /usr/local/bin/npm ci --no-audit --no-fund
  /usr/local/bin/npm test
  /usr/local/bin/npm run typecheck
  /usr/local/bin/npm run build
)
(
  cd "$release/backend"
  set -a
  . /etc/hashti/hashti.env
  set +a
  .venv/bin/alembic upgrade head
)
ln -s "$release" /srv/hashti/current
install -d -m 0700 -o hashti -g hashti "$release/frontend/.next/cache"
chown -R root:root "$release"
chown -R hashti:hashti "$release/frontend/.next/cache"
chmod 0755 "$release" "$release/backend" "$release/frontend"

install -m 0644 "$release/deploy/hashti-api.service" /etc/systemd/system/hashti-api.service
install -m 0644 "$release/deploy/hashti-web.service" /etc/systemd/system/hashti-web.service
systemctl daemon-reload
systemctl enable --now hashti-api.service hashti-web.service
echo "Release ${HASHTI_RELEASE_ID} installed; verify internal health before exposing it."
