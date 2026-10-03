#!/usr/bin/env bash
# «Бессрочный» туннель для тестов: когда туннель умирает, поднимает новый
# и переключает на него сервер через /api/admin/public-url БЕЗ рестарта —
# игра, стеки и раздачи не теряются. Бот заодно перевязывает кнопки
# в уже отправленных сообщениях на новый адрес.
#
# Провайдеры (TUNNEL_PROVIDER):
#   lhr    — localhost.run (по умолчанию): без предупреждающей страницы;
#   pinggy — free живёт ~час и показывает браузерам страницу-предупреждение
#            (обходится заголовком X-Pinggy-No-Screen в API-запросах).
set -euo pipefail
cd "$(dirname "$0")/.."

PROVIDER="${TUNNEL_PROVIDER:-lhr}"
mkdir -p .tools

case "$PROVIDER" in
  lhr)
    SSH_CMD=(ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:localhost:8000 nokey@localhost.run)
    URL_RE="https://[a-z0-9-]+\.lhr\.life"
    ;;
  pinggy)
    SSH_CMD=(ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -p 443 -R 0:localhost:8000 a.pinggy.io)
    URL_RE="https://[a-z0-9.-]+\.pinggy\.net"
    ;;
  *)
    echo "неизвестный TUNNEL_PROVIDER: $PROVIDER (доступны lhr, pinggy)"
    exit 1
    ;;
esac

while true; do
  echo "[$(date +%H:%M:%S)] поднимаю туннель ($PROVIDER)…"
  "${SSH_CMD[@]}" > .tools/tunnel.log 2>&1 &
  SSH_PID=$!

  URL=""
  for _ in $(seq 1 20); do
    sleep 1
    URL=$(grep -oE "$URL_RE" .tools/tunnel.log | head -1 || true)
    [ -n "$URL" ] && break
  done
  if [ -z "${URL:-}" ]; then
    echo "[$(date +%H:%M:%S)] адрес не получен, повтор через 5 с"
    kill "$SSH_PID" 2>/dev/null || true
    sleep 5
    continue
  fi

  echo "[$(date +%H:%M:%S)] туннель: $URL"
  curl -s -X POST http://127.0.0.1:8000/api/admin/public-url \
      -H "Content-Type: application/json" \
      -d "{\"url\": \"$URL\"}" && echo " — сервер переключён"

  # Вахта: провайдер может молча убить туннель, пока ssh выглядит живым —
  # опрашиваем адрес и при сбое пересоздаём (окно простоя ≈ 15–20 секунд).
  (
    while kill -0 "$SSH_PID" 2>/dev/null; do
      sleep 15
      code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$URL/api/health" || true)
      if [ "$code" != "200" ]; then
        echo "[$(date +%H:%M:%S)] туннель не отвечает (HTTP ${code:-нет}), пересоздаю…"
        kill "$SSH_PID" 2>/dev/null || true
        break
      fi
    done
  ) &
  WATCHDOG_PID=$!

  # Ждём смерти туннеля (ssh или вахта), затем пересоздаём.
  wait "$SSH_PID" || true
  kill "$WATCHDOG_PID" 2>/dev/null || true
  wait "$WATCHDOG_PID" 2>/dev/null || true
  echo "[$(date +%H:%M:%S)] туннель умер, пересоздаю…"
  sleep 2
done
