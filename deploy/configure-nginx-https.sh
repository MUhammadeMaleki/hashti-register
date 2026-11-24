#!/usr/bin/env bash
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
domain=register.ihashti.ir
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
install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
install -m 0755 "$(dirname "$0")/certbot-renew-nginx.sh" \
  /etc/letsencrypt/renewal-hooks/deploy/hashti-nginx-reload.sh
curl --fail --silent --show-error --resolve "$domain:443:127.0.0.1" \
  "https://$domain/api/health/ready"
echo "HTTPS ready for $domain"
