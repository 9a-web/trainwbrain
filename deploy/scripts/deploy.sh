#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Обновление задеплоенного приложения: код -> зависимости -> сборка -> рестарт.
#
# Запуск:
#   ssh deploy@SERVER
#   bash /opt/trainwbrain/deploy/scripts/deploy.sh
#
# Если менялись .env / nginx-конфиги — см. DEPLOY.md, раздел 12.
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR=/opt/trainwbrain
# CRA-сборка на 4 ГБ heap; на 8 ГБ RAM этого достаточно с запасом.
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=4096}"
cd "$APP_DIR"

echo "==> git pull"
git pull --ff-only

echo "==> backend: зависимости"
"$APP_DIR/backend/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/backend/.venv/bin/pip" install -q -r "$APP_DIR/deploy/requirements.server.txt"

echo "==> frontend: зависимости + сборка"
cd "$APP_DIR/frontend"
yarn install --frozen-lockfile --non-interactive
yarn build

echo "==> рестарт backend"
sudo systemctl restart twb-backend

echo "==> перезагрузка nginx"
sudo systemctl reload nginx

echo "==> health check"
sleep 2
curl -fsS http://127.0.0.1:8000/api/ && echo
echo "OK"
