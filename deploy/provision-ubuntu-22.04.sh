#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" != 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi
. /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 22.04 || "$(dpkg --print-architecture)" != amd64 ]]; then
  echo "This script targets Ubuntu 22.04 amd64 only." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gpg xz-utils python3-venv postgresql-common nginx certbot

# PostgreSQL's signed apt repository supplies the project's pinned major version.
install -d /usr/share/postgresql-common/pgdg
curl -fL --retry 3 -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
  https://www.postgresql.org/media/keys/ACCC4CF8.asc
key_fingerprint="$(gpg --show-keys --with-colons /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
  | awk -F: '$1 == "fpr" { print $10; exit }')"
if [[ "$key_fingerprint" != B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8 ]]; then
  echo "PostgreSQL repository key fingerprint mismatch." >&2
  exit 1
fi
cat > /etc/apt/sources.list.d/pgdg.sources <<'EOF'
Types: deb
URIs: https://apt.postgresql.org/pub/repos/apt
Suites: jammy-pgdg
Architectures: amd64
Components: main
Signed-By: /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
EOF
apt-get update
apt-get install -y postgresql-17

# Use an official Node.js binary, checking its published SHA-256 before extraction.
node_version=24.22.3
node_dir="/opt/hashti/node-${node_version}"
if [[ ! -x "$node_dir/bin/node" ]]; then
  archive="$(mktemp /tmp/hashti-node.XXXXXX.tar.xz)"
  trap 'rm -f "$archive"' EXIT
  curl -fL --retry 3 -o "$archive" \
    "https://nodejs.org/dist/v${node_version}/node-v${node_version}-linux-x64.tar.xz"
  echo "4f2b175a6d53a5c617a80dba2676238a0688cef28c6da4eba35c7d844e66fcfb  $archive" \
    | sha256sum -c -
  install -d "$node_dir"
  tar -xJf "$archive" -C "$node_dir" --strip-components=1
fi
for program in node npm npx; do
  target="/usr/local/bin/$program"
  if [[ -e "$target" && "$(readlink -f "$target")" != "$node_dir/bin/$program" ]]; then
    echo "Refusing to replace existing $target." >&2
    exit 1
  fi
  ln -sfn "$node_dir/bin/$program" "$target"
done

# Ubuntu 22.04's system Python is 3.10. Install a supported, isolated Python.
if [[ ! -x /opt/hashti/uv/bin/uv ]]; then
  python3 -m venv /opt/hashti/uv
  /opt/hashti/uv/bin/pip install --no-cache-dir uv==0.13.9
fi
UV_PYTHON_INSTALL_DIR=/opt/hashti/python /opt/hashti/uv/bin/uv python install 3.12

if ! id hashti >/dev/null 2>&1; then
  useradd --system --home /var/lib/hashti --shell /usr/sbin/nologin hashti
fi
install -d -m 0755 /srv/hashti /srv/hashti/releases
install -d -m 0750 -o root -g hashti /etc/hashti
install -d -m 0700 -o hashti -g hashti \
  /var/lib/hashti /var/lib/hashti/uploads \
  /var/lib/hashti/uploads/receipts /var/lib/hashti/uploads/posters

echo "Provisioned: $(/usr/local/bin/node --version), $(/opt/hashti/uv/bin/uv --version), $(psql --version)"
