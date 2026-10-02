# 🃏 PokerBot — покерный клуб в Telegram

Безлимитный Холдем с друзьями: бот-консьерж (приглашения, уведомления, итоги)
+ Mini App со столом. Кэш-игра на условные фишки, расчёт долгов в конце сессии.

Полный дизайн-документ и план фаз — в **[PLAN.md](PLAN.md)**.

**Текущая фаза: M1 — каркас** (авторизация Mini App, /start с кнопкой, API).

## Быстрый старт (разработка)

### Бэкенд

```bash
python -m venv .venv
source .venv/Scripts/activate      # Git Bash на Windows
pip install -r requirements.txt
cp .env.example .env               # вписать BOT_TOKEN от @BotFather
```

### Mini App

```bash
cd web
npm install
npm run build                      # сборка в web/dist — её отдаёт FastAPI
```

### Запуск

```bash
python -m app.main
```

- API: <http://localhost:8000/api/health>
- Mini App (сборка): <http://localhost:8000>
- Дев-режим фронта с hot reload: `cd web && npm run dev` → <http://localhost:5173>
  (API проксируется на бэкенд автоматически)

### Проверка внутри Telegram

Mini App требует публичный **HTTPS**. Подними туннель:

```bash
cloudflared tunnel --url http://localhost:8000
```

Полученный адрес впиши в `.env` как `BASE_URL` и перезапусти процесс. Затем:
открой бота в Telegram → `/start` → кнопка «🎰 Открыть покер-клуб».

Без `BOT_TOKEN` процесс стартует в режиме «только API» — удобно для работы над фронтом.

## Тесты

```bash
.venv/Scripts/python -m pytest -q
```

## Структура

Краткая карта репозитория — в [PLAN.md](PLAN.md), раздел 7.
