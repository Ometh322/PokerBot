#!/usr/bin/env bash
# Дев-запуск клуба: SSH-туннель pinggy + сервер с ботом в одном процессе.
# Адрес туннеля автоматически прописывается в .env (BASE_URL).
#
# Бесплатный pinggy живёт 60 минут: просто перезапусти скрипт —
# поднимется новый адрес, данные сохранятся (pokerbot.db).
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p .tools
if [ ! -f .env ]; then
  cp .env.example .env
  echo "!! Создан .env — впиши BOT_TOKEN и запусти скрипт снова"
  exit 1
fi

echo "[1/2] Поднимаю туннель pinggy (SSH, порт 443)..."
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -p 443 \
    -R 0:localhost:8000 a.pinggy.io > .tools/tunnel.log 2>&1 &
TUNNEL_PID=$!
sleep 8
URL=$(grep -o "https://[a-z0-9.-]*\.pinggy\.net" .tools/tunnel.log | head -1 || true)
if [ -z "${URL:-}" ]; then
  echo "Туннель не поднялся, лог:"
  cat .tools/tunnel.log
  kill "$TUNNEL_PID" 2>/dev/null || true
  exit 1
fi
echo "      Публичный адрес: $URL"
sed -i.bak "s|^BASE_URL=.*|BASE_URL=$URL|" .env && rm -f .env.bak

echo "[2/2] Запускаю сервер и бота (Ctrl+C — остановить всё)..."
trap 'kill '"$TUNNEL_PID"' 2>/dev/null || true' EXIT
".venv/Scripts/python" -m app.main
