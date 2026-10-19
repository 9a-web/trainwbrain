# 🏋️ TrainWithBrain — Telegram Web App

> Telegram Mini App для отслеживания тренировочного прогресса пауэрлифтеров и силовых спортсменов.

![React](https://img.shields.io/badge/React-19.0.0-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110.1-green)
![MongoDB](https://img.shields.io/badge/MongoDB-Motor-brightgreen)
![Tailwind](https://img.shields.io/badge/Tailwind-3.4.17-38bdf8)

---

## 📖 Описание

**TrainWithBrain (TWB)** открывается прямо внутри Telegram и помогает спортсменам планировать и отслеживать тренировки. Сейчас реализован UI‑скелет MVP:

- 👋 Персональное приветствие по времени суток (имя берётся из Telegram)
- 🔥 Тренировочная серия — streak (пока статично «0 дней»)
- 📅 Недельный селектор дней с круговым прогрессом (данные прогресса — **временно mock**)
- 👤 Регистрация/обновление пользователя в MongoDB при каждом входе
- 🖼️ Получение аватара пользователя через Telegram Bot API (с fallback)

> 📚 Для AI‑агентов и разработчиков есть подробная документация:
> **[AI_CONTEXT.md](./AI_CONTEXT.md)** — рабочий контекст и правила · **[PROJECT_DETAILS.md](./PROJECT_DETAILS.md)** — глубокий технический разбор.
>
> 🖥️ **Развёртывание на VPS** (frontend + backend + DeepSeek Harness, домен, HTTPS, dev-режим):
> **[DEPLOY.md](./DEPLOY.md)** + готовые конфиги в [`deploy/`](./deploy/).

---

## 🛠️ Технологии

| Слой | Стек |
|------|------|
| Frontend | React 19, CRACO, Tailwind CSS 3.4, shadcn/ui (Radix), React Router 7, Axios |
| Backend | FastAPI, Motor (async MongoDB), Pydantic v2, httpx |
| База данных | MongoDB |
| Интеграции | Telegram WebApp API, Telegram Bot API, PostHog (аналитика) |

---

## 📁 Структура проекта

```
/app/
├── backend/
│   ├── server.py           # Весь backend: модели + эндпоинты
│   ├── requirements.txt
│   └── .env                # MONGO_URL, DB_NAME, CORS_ORIGINS, TELEGRAM_BOT_TOKEN
├── frontend/
│   ├── public/             # index.html, логотип, иконки (svg/png)
│   ├── src/
│   │   ├── App.js          # Главный экран (Home)
│   │   ├── components/
│   │   │   ├── DateSelector.js  # Недельный селектор + ProgressRing
│   │   │   └── ui/              # 46 компонентов shadcn/ui
│   │   ├── hooks/ · lib/ · fonts/
│   │   └── index.css       # шрифты, CSS‑переменные, Tailwind
│   ├── package.json · craco.config.js · tailwind.config.js · .env
├── backend_test.py         # Интеграционные тесты backend
├── AI_CONTEXT.md · PROJECT_DETAILS.md · README.md · test_result.md
```

---

## 🚀 Быстрый старт

Приложение запускается через **supervisor** (uvicorn/craco вручную не запускать).

```bash
# Зависимости
cd /app/backend  && pip install -r requirements.txt
cd /app/frontend && yarn install      # ТОЛЬКО yarn, не npm

# Запуск / перезапуск
sudo supervisorctl restart all
sudo supervisorctl status

# Логи
tail -n 100 /var/log/supervisor/backend.err.log
tail -n 100 /var/log/supervisor/frontend.err.log
```

### Переменные окружения
**backend/.env**
```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=test_database
CORS_ORIGINS=*
TELEGRAM_BOT_TOKEN=<токен вашего Telegram‑бота>
```
**frontend/.env**
```env
REACT_APP_BACKEND_URL=<внешний URL backend>
WDS_SOCKET_PORT=443
ENABLE_HEALTH_CHECK=false
```
> ⚠️ Значения URL/портов в `.env` не менять. Frontend всегда обращается к backend по `REACT_APP_BACKEND_URL` + `/api`.

---

## 📡 API Endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/` | Health check |
| POST | `/api/users` | Создать/обновить пользователя (upsert по `telegram_id`) |
| GET | `/api/users/{telegram_id}` | Получить пользователя (404 если нет) |
| GET | `/api/telegram/avatar/{user_id}` | URL аватара через Telegram Bot API |
| POST | `/api/status` | (демо) Создать запись статуса |
| GET | `/api/status` | (демо) Список статусов |

### Примеры
```bash
curl http://localhost:8001/api/

curl -X POST http://localhost:8001/api/users \
  -H "Content-Type: application/json" \
  -d '{"telegram_id": 12345, "first_name": "Иван", "username": "ivan"}'
```

---

## 📱 Telegram‑интеграция

Приложение использует [Telegram WebApp API](https://core.telegram.org/bots/webapps):

```javascript
if (window.Telegram?.WebApp) {
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();
  const user = tg.initDataUnsafe?.user; // id, first_name, username, language_code...
}
```
> Вне Telegram (обычный браузер) `window.Telegram` отсутствует — имя по умолчанию «Гость», регистрация не вызывается. Это ожидаемое поведение при локальной разработке.

---

## 🗺️ Roadmap

### ✅ Готово
- [x] Базовая структура, шапка с логотипом и меню
- [x] Telegram WebApp init + регистрация пользователя в MongoDB
- [x] Backend‑эндпоинт аватара (Telegram Bot API)
- [x] Приветствие по времени суток
- [x] Недельный DateSelector с progress ring
- [x] Аватар пользователя в шапке
- [x] Реальный прогресс и streak (подсчёт серий тренировок)
- [x] Тренировочные планы и упражнения (CRUD API + экраны)
- [x] Тренировочные сессии с таймером отдыха и логированием подходов
- [x] Режим тренера (P3) — управление спортсменами и планами
- [x] Real-time WebSocket (P4) — синхронизация между тренером и спортсменом
- [x] Детальная статистика (P7) — графики, прогрессия, объём тренировок
- [x] Пропуски и переносы тренировок (P2.1)
- [x] Дневник с ИИ-агентом (co-scribe) — парсинг фото, чат

---

## ⚠️ Важные правила разработки

1. Пакеты фронта — только **yarn**.
2. Все API‑роуты — с префиксом **`/api`**.
3. Не хардкодить URL/порты — только из `.env`.
4. ID в MongoDB — только **UUID**, не ObjectID.
5. Сервисы — только через **supervisor** (hot reload включён; перезапуск нужен при изменении `.env`).

Полные правила — в [AI_CONTEXT.md](./AI_CONTEXT.md).

---

## 📄 Лицензия

Проект создан с использованием [Emergent.sh](https://emergent.sh).
