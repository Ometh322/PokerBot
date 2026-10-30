#!/usr/bin/env bash
# Дев-запуск клуба: сервер с ботом + автопереключаемый туннель serveo
# со стабильным именем (kartishki.serveousercontent.com).
#
# Пока работает этот скрипт — публичный адрес всегда живой: вахта следит
# за туннелем, пересоздаёт его на ТО ЖЕ ИМЯ и переключает сервер без
# рестарта (игра не теряется). Боту нужен HAPP: он переподключится сам,
# как только прокси поднимется.
#
# Ctrl+C останавливает и сервер, и туннель. Данные — в pokerbot.db.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p .tools
if [ ! -f .env ]; then
  cp .env.example .env
  echo "!! Создан .env — впиши BOT_TOKEN и запусти скрипт снова"
  exit 1
fi

echo "[1/2] Запускаю автотуннель (serveo, kartishki.serveousercontent.com)…"
bash scripts/tunnel_keepalive.sh &
KEEPALIVE_PID=$!

echo "[2/2] Запускаю сервер и бота (Ctrl+C — остановить всё)…"
trap 'kill '"$KEEPALIVE_PID"' 2>/dev/null || true' EXIT
".venv/Scripts/python" -m app.main
