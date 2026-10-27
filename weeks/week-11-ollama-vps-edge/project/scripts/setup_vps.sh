#!/usr/bin/env bash
# Run ON the VPS as root (Ubuntu 22.04/24.04 or Debian 12), from the project directory:
#
#   sudo SERVER_NAME=ollama.example.com LE_EMAIL=you@example.com \
#        BASIC_AUTH_USER=rag BASIC_AUTH_PASSWORD='choose-a-long-one' \
#        ./scripts/setup_vps.sh
#
# No domain? Use <dashed-ip>.sslip.io (e.g. 203-0-113-7.sslip.io) -- it resolves to your
# IP and Let's Encrypt will issue for it.
#
# Steps: Ollama (bound to loopback) -> pull model -> Nginx + basic auth -> firewall ->
# Let's Encrypt. Safe to re-run.
set -euo pipefail

SERVER_NAME="${SERVER_NAME:?set SERVER_NAME (DNS name pointing at this VPS)}"
LE_EMAIL="${LE_EMAIL:?set LE_EMAIL (email for certificate expiry notices)}"
BASIC_AUTH_USER="${BASIC_AUTH_USER:?set BASIC_AUTH_USER}"
BASIC_AUTH_PASSWORD="${BASIC_AUTH_PASSWORD:?set BASIC_AUTH_PASSWORD}"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
RATE_LIMIT_RPS="${RATE_LIMIT_RPS:-5}"
RATE_LIMIT_BURST="${RATE_LIMIT_BURST:-10}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)"; exit 1; }

echo "==> Swap (a 4 GB box running a 3B model needs the safety net)"
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> Installing Ollama"
command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh

echo "==> Pinning Ollama to loopback and tuning it"
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf <<'CONF'
[Service]
# Loopback only: Nginx is the sole public entry point. (This is also Ollama's default;
# it is written out so a stray OLLAMA_HOST elsewhere can't silently widen it.)
Environment="OLLAMA_HOST=127.0.0.1:11434"
# Keep the model resident between requests -- otherwise each idle gap costs a cold load.
Environment="OLLAMA_KEEP_ALIVE=30m"
# One request at a time: parallel generations split scarce CPU/RAM and slow all of them.
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
CONF
systemctl daemon-reload
systemctl enable --now ollama
systemctl restart ollama

echo "==> Waiting for Ollama, then pulling ${OLLAMA_MODEL}"
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break
  sleep 1
done
ollama pull "$OLLAMA_MODEL"

echo "==> Installing Nginx, certbot, htpasswd"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y nginx certbot python3-certbot-nginx apache2-utils ufw

echo "==> Basic auth user"
htpasswd -bc /etc/nginx/.ollama_htpasswd "$BASIC_AUTH_USER" "$BASIC_AUTH_PASSWORD"
chown root:www-data /etc/nginx/.ollama_htpasswd
chmod 640 /etc/nginx/.ollama_htpasswd

echo "==> Nginx site"
rm -f /etc/nginx/sites-enabled/default
sed -e "s/__SERVER_NAME__/${SERVER_NAME}/g" -e "s/__RATE__/${RATE_LIMIT_RPS}/g" -e "s/__BURST__/${RATE_LIMIT_BURST}/g" "$PROJECT_DIR/deploy/ollama.nginx.conf" \
  > /etc/nginx/conf.d/ollama.conf
nginx -t
systemctl reload nginx

echo "==> Firewall: SSH + HTTP(S) only -- 11434 is never opened"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Let's Encrypt for ${SERVER_NAME}"
certbot --nginx -d "$SERVER_NAME" -m "$LE_EMAIL" --agree-tos --no-eff-email --redirect --non-interactive

echo
echo "Done. From your laptop:  ./scripts/verify_endpoint.sh https://${SERVER_NAME}"
