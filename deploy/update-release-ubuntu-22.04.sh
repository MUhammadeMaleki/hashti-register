#!/usr/bin/env bash
set -euo pipefail
umask 077

[[ "$(id -u)" == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
: "${HASHTI_RELEASE_ID:?Set the release commit ID}"
[[ "$HASHTI_RELEASE_ID" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid release ID.' >&2; exit 1; }
archive="/root/hashti-${HASHTI_RELEASE_ID}.tar"
release="/srv/hashti/releases/${HASHTI_RELEASE_ID}"
previous="$(readlink -f /srv/hashti/current)"
[[ -f "$archive" && ! -e "$release" && -d "$previous" ]] || {
  echo 'Release archive missing, release exists, or current release is unavailable.' >&2
  exit 1
}

install -d -m 0755 "$release"
tar -xf "$archive" -C "$release"
UV_PYTHON_INSTALL_DIR=/opt/hashti/python /opt/hashti/uv/bin/uv venv --python 3.12 "$release/backend/.venv"
/opt/hashti/uv/bin/uv pip install --python "$release/backend/.venv/bin/python" \
  -r "$release/backend/requirements.txt"
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

install -d -m 0700 -o hashti -g hashti "$release/frontend/.next/cache"
chown -R root:root "$release"
chmod -R a+rX "$release"
chown -R hashti:hashti "$release/frontend/.next/cache"
chmod -R go-rwx "$release/frontend/.next/cache"
ln -sfn "$release" /srv/hashti/current
systemctl restart hashti-api.service hashti-web.service
if ! systemctl is-active --quiet hashti-api.service ||
   ! systemctl is-active --quiet hashti-web.service ||
   ! curl --fail --silent --show-error --retry 10 --retry-delay 2 \
     http://127.0.0.1:8000/api/health/ready >/dev/null ||
   ! curl --fail --silent --show-error --retry 10 --retry-delay 2 \
     http://127.0.0.1:3000/ >/dev/null; then
  ln -sfn "$previous" /srv/hashti/current
  systemctl restart hashti-api.service hashti-web.service
  echo 'Health check failed. Previous application release restored.' >&2
  exit 1
fi
echo "Release ${HASHTI_RELEASE_ID} active; previous release: ${previous}"
