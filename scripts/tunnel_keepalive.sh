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

PROVIDER="${TUNNEL_PROVIDER:-serveo}"
# Стабильное имя (serveo): SERVEO_NAME=kartishki — после регистрации SSH-ключа
# в консоли serveo.net имя не меняется при пересоздании туннеля.
SERVEO_NAME="${SERVEO_NAME:-kartishki}"
# Стабильный поддомен (localhost.run): LHR_DOMAIN=… — платная функция, тут не используется.
LHR_DOMAIN="${LHR_DOMAIN:-}"
mkdir -p .tools

case "$PROVIDER" in
  serveo)
    SSH_CMD=(ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
             -i .tools/lhr_key \
             -R "$SERVEO_NAME:80:localhost:8000" serveo.net)
    URL_RE="https://[a-z0-9-]+\.serveousercontent\.com"
    ;;
  lhr)
    if [ -n "$LHR_DOMAIN" ]; then
      # Кастомный поддомен требует входа под аккаунтом (plan@) и ключа.
      SSH_CMD=(ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
               -i .tools/lhr_key \
               -R "$LHR_DOMAIN:80:localhost:8000" plan@localhost.run)
      URL="https://$LHR_DOMAIN"
    else
      SSH_CMD=(ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:localhost:8000 nokey@localhost.run)
      URL=""
    fi
    URL_RE="https://[a-z0-9-]+\.lhr\.life"
    ;;
  pinggy)
    SSH_CMD=(ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -p 443 -R 0:localhost:8000 a.pinggy.io)
    URL=""
    URL_RE="https://[a-z0-9.-]+\.pinggy\.net"
    ;;
  *)
    echo "неизвестный TUNNEL_PROVIDER: $PROVIDER (доступны serveo, lhr, pinggy)"
    exit 1
    ;;
esac

while true; do
  echo "[$(date +%H:%M:%S)] поднимаю туннель ($PROVIDER)…"
  "${SSH_CMD[@]}" > .tools/tunnel.log 2>&1 &
  SSH_PID=$!

  if [ -z "${URL:-}" ]; then
    # Анонимный режим: адрес выдаётся в логе.
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
  else
    # Стабильный домен: ждём, пока туннель начнёт отвечать.
    for _ in $(seq 1 30); do
      sleep 1
      code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$URL/api/health" || true)
      [ "$code" = "200" ] && break
    done
  fi

  echo "[$(date +%H:%M:%S)] туннель: $URL"

  # Переключаем сервер на адрес с ретраями: при одновременном старте
  # сервер может ещё не слушать порт (ловили гонку — адрес оставался
  # localhost:8000 и Telegram отвергал кнопки).
  switched=""
  for _ in $(seq 1 24); do
    res=$(curl -s --max-time 5 -X POST http://127.0.0.1:8000/api/admin/public-url \
        -H "Content-Type: application/json" \
        -d "{\"url\": \"$URL\"}" || true)
    if echo "$res" | grep -q '"ok":true'; then
      echo "[$(date +%H:%M:%S)] сервер переключён: $res"
      switched=1
      break
    fi
    sleep 5
  done
  if [ -z "$switched" ]; then
    echo "[$(date +%H:%M:%S)] !! сервер не принял адрес за 2 минуты — продолжаю, вахта повторит"
  fi

  # Вахта: провайдер может молча убить туннель, пока ssh выглядит живым —
  # опрашиваем адрес и при сбое пересоздаём (окно простоя ≈ 15–20 секунд).
  # Заодно каждый такт повторно привязываем адрес: если сервер перезапускался
  # (сброс на localhost:8000) — он получит актуальный туннель сам.
  (
    while kill -0 "$SSH_PID" 2>/dev/null; do
      sleep 15
      code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$URL/api/health" || true)
      if [ "$code" != "200" ]; then
        echo "[$(date +%H:%M:%S)] туннель не отвечает (HTTP ${code:-нет}), пересоздаю…"
        kill "$SSH_PID" 2>/dev/null || true
        break
      fi
      curl -s --max-time 5 -o /dev/null -X POST http://127.0.0.1:8000/api/admin/public-url \
          -H "Content-Type: application/json" \
          -d "{\"url\": \"$URL\"}" || true
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
