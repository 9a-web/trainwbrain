#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Ежедневный бэкап MongoDB + секретов.
#
# Установка (от deploy):
#   chmod +x /opt/trainwbrain/deploy/scripts/backup-mongo.sh
#   sudo crontab -e -u deploy
#   # каждый день в 03:30
#   30 3 * * * /opt/trainwbrain/deploy/scripts/backup-mongo.sh >> /var/log/twb-backup.log 2>&1
#
# Если MongoDB с авторизацией — добавьте --username/--password/--authenticationDatabase.
# Хранить бэкапы лучше не только на том же диске: раз в сутки копируйте
# архив в объектное хранилище (rclone / provider snapshots).
# ---------------------------------------------------------------------------
set -euo pipefail

BACKUP_DIR=/var/backups/trainwbrain
STAMP="$(date +%F_%H-%M)"
DB_NAME="${DB_NAME:-trainwbrain_db}"

mkdir -p "$BACKUP_DIR"

echo "[$(date -Is)] dump $DB_NAME"
mongodump \
  --uri="mongodb://127.0.0.1:27017/${DB_NAME}" \
  --gzip \
  --archive="$BACKUP_DIR/twb_${STAMP}.archive"

echo "[$(date -Is)] env backup"
tar czf "$BACKUP_DIR/env_${STAMP}.tar.gz" \
  -C /opt/trainwbrain \
  backend/.env backend/.env.local frontend/.env frontend/.env.production 2>/dev/null || true
chmod 600 "$BACKUP_DIR"/env_*.tar.gz 2>/dev/null || true

echo "[$(date -Is)] rotate (14 дней)"
find "$BACKUP_DIR" -maxdepth 1 -name 'twb_*.archive' -mtime +14 -delete
find "$BACKUP_DIR" -maxdepth 1 -name 'env_*.tar.gz' -mtime +14 -delete

du -sh "$BACKUP_DIR"
