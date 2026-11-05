#!/usr/bin/env bash
# ============================================================
# build-ios-capgo.sh
# Сборка iOS приложения TrainWithBrain для Capgo Cloud Build.
#
# Требования:
#   - @capgo/cli установлен (yarn global add @capgo/cli)
#   - Capacitor проект инициализирован
#   - Фронтенд собран (yarn build)
#
# Использование:
#   CAPGO_TOKEN=<token> ./build-ios-capgo.sh [--upload]
#
# Флаги:
#   --upload    Загрузить билд в Capgo Cloud после сборки
#
# Переменные окружения (можно задать в .env):
#   CAPGO_TOKEN       — API токен Capgo (обязательно)
#   CAPGO_APP_ID      — ID приложения в Capgo
#   APPLE_TEAM_ID     — Apple Team ID для подписи
#   APPLE_KEY_ID      — ID App Store Connect API ключа
#   APPLE_ISSUER_ID   — Issuer ID App Store Connect API
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
IOS_DIR="$FRONTEND_DIR/ios"

echo "=== TrainWithBrain iOS Build (Capgo Cloud) ==="
echo "Root: $ROOT_DIR"

# Проверка токена
if [ -z "${CAPGO_TOKEN:-}" ]; then
  echo "❌ CAPGO_TOKEN не задан. Укажите токен или экспортируйте CAPGO_TOKEN=<token>"
  exit 1
fi

# 1. Сборка фронтенда
echo ""
echo "📦 [1/4] Сборка фронтенда..."
cd "$FRONTEND_DIR"
yarn build
echo "✅ Фронтенд собран"

# 2. Копирование ресурсов в iOS проект
echo ""
echo "📱 [2/4] Копирование веб-ресурсов в iOS проект..."
npx cap sync ios --deployment
echo "✅ Ресурсы скопированы"

# 3. Настройка Capgo Cloud
echo ""
echo "☁️  [3/4] Настройка Capgo Cloud..."

# Убедимся, что @capgo/cli установлен
if ! command -v capgo &>/dev/null; then
  echo "   Установка @capgo/cli..."
  npm install -g @capgo/cli
fi

# 4. Запуск сборки
echo ""
echo "🚀 [4/4] Запуск сборки в Capgo Cloud..."
cd "$IOS_DIR"

if [ "${1:-}" = "--upload" ]; then
  capgo cloud build ios \
    --token "$CAPGO_TOKEN" \
    --app-id "${CAPGO_APP_ID:-com.trainwbrain.app}" \
    --config "$FRONTEND_DIR/capacitor.config.json"
else
  capgo cloud build ios \
    --token "$CAPGO_TOKEN" \
    --app-id "${CAPGO_APP_ID:-com.trainwbrain.app}" \
    --config "$FRONTEND_DIR/capacitor.config.json" \
    --no-upload
fi

echo ""
echo "✅ Сборка завершена! Результат доступен в дашборде Capgo."
echo "   https://capgo.app/dashboard/builds"