#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# TrainWithBrain — первичная настройка Ubuntu 24.04 LTS.
#
# Запуск (от root):
#   sudo bash deploy/scripts/bootstrap.sh
#
# Скрипт идемпотентен: повторный запуск ничего не ломает.
# Пользователя deploy и SSH-ключи создаём вручную (см. DEPLOY.md, раздел 4.2).
# ---------------------------------------------------------------------------
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запустите от root: sudo bash $0" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "==> Часовой пояс Europe/Moscow"
timedatectl set-timezone Europe/Moscow

echo "==> Базовые пакеты"
apt-get update
apt-get -y upgrade
apt-get install -y \
  curl ca-certificates gnupg lsb-release \
  git build-essential \
  ufw fail2ban unattended-upgrades \
  htop tmux unzip jq \
  nginx certbot python3-certbot-nginx apache2-utils \
  python3 python3-venv python3-dev \
  ripgrep

echo "==> Swap 4G (если ещё нет)"
if ! swapon --show | grep -q '/swapfile'; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10
  grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
fi

echo "==> Автообновления безопасности"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

echo "==> Node.js 24 LTS"
if ! command -v node >/dev/null 2>&1 || [[ "$(node -v)" != v24* ]]; then
  curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
  apt-get install -y nodejs
fi
node -v

echo "==> yarn 1.22 + DeepSeek Harness"
npm install -g yarn@1.22.22
npm install -g @deepseek-ai/dsh@0.2.1-rc.2
dsh --version

echo "==> MongoDB 8.0"
if ! command -v mongod >/dev/null 2>&1; then
  curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc \
    | gpg --dearmor -o /usr/share/keyrings/mongodb-server-8.0.gpg
  echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/ubuntu $(lsb_release -cs)/mongodb-org/8.0 multiverse" \
    > /etc/apt/sources.list.d/mongodb-org-8.0.list
  apt-get update
  apt-get install -y mongodb-org
fi
systemctl enable --now mongod
systemctl is-active mongod || true

echo "==> MongoDB: ограничение кэша (важно для 2 ГБ RAM)"
if ! grep -q 'cacheSizeGB' /etc/mongod.conf 2>/dev/null; then
  cp /etc/mongod.conf /etc/mongod.conf.bak
  python3 - <<'PY'
import re, pathlib
p = pathlib.Path('/etc/mongod.conf')
text = p.read_text()
if 'cacheSizeGB' not in text:
    if re.search(r'^storage:\s*$', text, re.M):
        text = re.sub(r'^storage:\s*$',
                      'storage:\n  wiredTiger:\n    engineConfig:\n      cacheSizeGB: 0.25',
                      text, count=1, flags=re.M)
    else:
        text += '\nstorage:\n  wiredTiger:\n    engineConfig:\n      cacheSizeGB: 0.25\n'
    p.write_text(text)
PY
  # в MongoDB 7+/8 нет флага --test: проверяем валидность через systemd
  systemctl restart mongod
  sleep 2
  if ! systemctl is-active --quiet mongod; then
    echo "!! mongod не поднялся с новым конфигом — откатываю"
    cp /etc/mongod.conf.bak /etc/mongod.conf
    systemctl restart mongod
  fi
fi
systemctl is-active mongod || true

echo "==> Firewall (22/80/443, остальное закрыто)"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
ufw status verbose

echo "==> fail2ban"
systemctl enable --now fail2ban

echo "==> Каталоги"
mkdir -p /var/www/certbot /var/backups/trainwbrain
chown -R www-data:www-data /var/www/certbot
# бэкапы запускаются из cron пользователя deploy
if id deploy >/dev/null 2>&1; then
  chown deploy:deploy /var/backups/trainwbrain
else
  echo "    ВНИМАНИЕ: пользователь deploy ещё не создан — выполните позже:"
  echo "    sudo chown deploy:deploy /var/backups/trainwbrain"
fi

echo
echo "Готово. Дальше:"
echo "  1. создать пользователя deploy и положить SSH-ключ;"
echo "  2. склонировать проект в /opt/trainwbrain;"
echo "  3. backend/.venv, .env, frontend build, nginx, certbot."
echo "Подробности — DEPLOY.md."
