#!/usr/bin/env bash
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
domain=register.ihashti.ir
address="$(getent ahostsv4 "$domain" 2>/dev/null | awk 'NR == 1 { print $1 }' || true)"
[[ "$address" == 37.32.6.45 ]] || { echo "DNS for $domain does not point directly to this VPS." >&2; exit 1; }
[[ -L /srv/hashti/current ]] || { echo 'Hashti release is missing.' >&2; exit 1; }

install -d -m 0755 /var/www/hashti-acme
if [[ ! -f /etc/letsencrypt/live/$domain/fullchain.pem ]]; then
  cat > /etc/nginx/sites-available/hashti <<'NGINX'
server {
    listen 80;
    server_name register.ihashti.ir;
    location /.well-known/acme-challenge/ {
        root /var/www/hashti-acme;
    }
    location / { return 503; }
}
NGINX
  ln -sfn /etc/nginx/sites-available/hashti /etc/nginx/sites-enabled/hashti
  nginx -t
  systemctl reload nginx
  certbot certonly --webroot --webroot-path /var/www/hashti-acme \
    --domains "$domain" --non-interactive --agree-tos \
    --register-unsafely-without-email
fi

sed "s/CHANGE_ME.example.com/$domain/g" \
  /srv/hashti/current/deploy/nginx.conf.example > /etc/nginx/sites-available/hashti
nginx -t
systemctl reload nginx
curl --fail --silent --show-error "https://$domain/api/health/ready"
echo "HTTPS ready for $domain"
