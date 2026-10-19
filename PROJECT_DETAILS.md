# PROJECT_DETAILS.md — TrainWithBrain

> **Назначение:** Глубокий технический разбор проекта для разработчиков и AI‑агентов: архитектура, потоки данных, схема БД, контракт API, инфраструктура, краевые случаи.
> **Версия:** 1.0 · **Обновлено:** Июль 2025
> **Смотри также:** [`AI_CONTEXT.md`](./AI_CONTEXT.md) · [`README.md`](./README.md)

---

## 1. Обзор архитектуры

TrainWithBrain — full‑stack Telegram Mini App. Три слоя:

```
┌──────────────────────────────────────────────────────────────┐
│  Telegram client (мобильный/десктоп)                          │
│  └─ открывает Web App во встроенном WebView                   │
│     window.Telegram.WebApp → initDataUnsafe.user              │
└───────────────┬──────────────────────────────────────────────┘
                │ HTTPS (REACT_APP_BACKEND_URL)
                ▼
┌──────────────────────────────────────────────────────────────┐
│  FRONTEND  React 19 (CRACO) — порт 3000                       │
│  App.js (Home) → axios → `${REACT_APP_BACKEND_URL}/api/...`   │
└───────────────┬──────────────────────────────────────────────┘
                │ /api/* (Kubernetes ingress → :8001)
                ▼
┌──────────────────────────────────────────────────────────────┐
│  BACKEND  FastAPI — 0.0.0.0:8001 (supervisor)                 │
│  server.py: APIRouter(prefix="/api")                          │
│   ├─ Motor (async) ──────────► MongoDB (MONGO_URL)            │
│   └─ httpx ──────────────────► Telegram Bot API              │
└──────────────────────────────────────────────────────────────┘
```

**Принцип маршрутизации:** ingress направляет всё, что начинается с `/api`, на backend (:8001), остальное — на frontend (:3000). Поэтому **каждый** backend‑роут обязан иметь префикс `/api`.

---

## 2. Backend (`backend/server.py`)

Весь backend в одном файле. Логическая разбивка:

| Блок | Строки (≈) | Содержание |
|------|-----------|------------|
| Bootstrap | загрузка `.env`, подключение Motor, чтение `TELEGRAM_BOT_TOKEN` |
| Модели | `StatusCheck(Create)`, `User`, `UserCreate` (Pydantic v2) |
| Status‑эндпоинты | `GET /api/`, `POST /api/status`, `GET /api/status` |
| User‑эндпоинты | `POST /api/users`, `GET /api/users/{telegram_id}` |
| Telegram | `GET /api/telegram/avatar/{user_id}` |
| Инфраструктура | `include_router`, CORS middleware, logging, shutdown hook |

### 2.1 Подключение к БД
```python
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
```
Имя БД — строго из `DB_NAME` (не хардкодить).

### 2.2 CORS
```python
allow_origins = os.environ.get('CORS_ORIGINS', '*').split(',')
allow_credentials=True, allow_methods=['*'], allow_headers=['*']
```

### 2.3 Конвенции (соблюдать в любом новом коде)
- **ID:** только `str(uuid.uuid4())`. ObjectID запрещён (не JSON‑сериализуем).
- **datetime:** при записи → `.isoformat()` (строка); при чтении → `datetime.fromisoformat()`.
- **Mongo read:** всегда `find(filter, {"_id": 0})`, иначе `_id` сломает сериализацию.
- **Pydantic:** модели БД используют `model_config = ConfigDict(extra="ignore")`, чтобы игнорировать лишние поля из Mongo.
- **Ошибки внешних API** (Telegram) не пробрасываются как 500 — возвращается JSON с `error`.

---

## 3. Схема базы данных (MongoDB)

БД: `test_database` (из `DB_NAME`). Схемы нет (NoSQL), фактическая структура документов:

### Коллекция `users`
| Поле | Тип | Примечание |
|------|-----|-----------|
| `id` | string (UUID) | Внутренний идентификатор |
| `telegram_id` | int | **Ключ upsert**, уникален логически |
| `first_name` | string | |
| `last_name` | string \| null | |
| `username` | string \| null | |
| `language_code` | string \| null | |
| `created_at` | string (ISO datetime) | Не меняется при обновлении |
| `updated_at` | string (ISO datetime) | Обновляется при каждом входе |

> Уникальный индекс по `telegram_id` пока НЕ создаётся в коде — уникальность обеспечивается логикой upsert (find → update/insert). При росте нагрузки стоит добавить индекс.

### Коллекция `status_checks` (демо из шаблона)
| Поле | Тип |
|------|-----|
| `id` | string (UUID) |
| `client_name` | string |
| `timestamp` | string (ISO datetime) |

---

## 4. Контракт API (детально)

### `GET /api/`
Health check. → `{"message": "Hello World"}`.

### `POST /api/users` — upsert пользователя
**Запрос:**
```json
{ "telegram_id": 12345, "first_name": "Имя", "last_name": null, "username": null, "language_code": "ru" }
```
**Логика:** ищет по `telegram_id`. Если найден — обновляет `first_name/last_name/username/language_code/updated_at`, сохраняет `created_at` и `id`. Если нет — создаёт новый документ с новым UUID.
**Ответ:** объект `User`. Вызывается фронтом при каждом запуске Web App.

### `GET /api/users/{telegram_id}`
→ `User` или **404** `{"detail": "User not found"}`.

### `GET /api/telegram/avatar/{user_id}`
Алгоритм:
1. `getUserProfilePhotos(user_id, limit=1)` → если нет `ok` или нет фото → `{"avatar_url": null, ...}`.
2. Берёт самый большой размер последнего фото → `file_id`.
3. `getFile(file_id)` → `file_path`.
4. Формирует `https://api.telegram.org/file/bot<TOKEN>/<file_path>`.

Краевые случаи (все возвращают `avatar_url: null`): токен не задан, у юзера нет фото, юзер не найден ботом, таймаут 10с, любое исключение.

### `POST /api/status` / `GET /api/status`
Демо‑эндпоинты из шаблона. Можно использовать как пример паттерна или удалить при чистке.

---

## 5. Frontend — потоки данных

### 5.1 Старт приложения (`App.js`)
```
mount → useEffect → initTelegram()
   ├─ если window.Telegram.WebApp есть:
   │     tg.ready(); tg.expand();
   │     user = tg.initDataUnsafe.user
   │     setTelegramUser(user)
   │     registerUser(user) → POST /api/users → setDbUser(resp)
   └─ иначе: ничего (имя = «Гость»)
getGreetingData() → текст+иконка по new Date().getHours()
render: Header + Greeting + Streak(0) + <DateSelector/>
```

### 5.2 `DateSelector.js`
```
state: selectedDate (Date), weekOffset (int)
weekDays = useMemo(... weekOffset):
   monday = понедельник недели с учётом offset
   7 карточек: { date, dayName(Вс..Сб), dayNumber, progress=MOCK_PROGRESS[dayOfWeek] }
prev/next week → weekOffset ±1
click day → setSelectedDate
ProgressRing: SVG circle, strokeDashoffset = C - (progress/100)*C
title: `${day} ${MONTH_NAMES[month]}` шрифтом GG Zaglav
```
**Точка интеграции для реальных данных:** заменить `MOCK_PROGRESS` на данные с backend (например, `GET /api/progress?week=...`), сохранив форму `{ dayOfWeek: percent }` или перейдя на массив по датам.

### 5.3 Переменные окружения фронта
```
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;   // всегда так формировать URL
```

---

## 6. Сборка и алиасы

- **CRACO** (`craco.config.js`):
  - alias `@` → `src` (импорты вида `@/components/...`, `@/App.css`).
  - `watchOptions` для hot reload.
  - Опциональный health‑check webpack‑плагин (вкл. через `ENABLE_HEALTH_CHECK`).
- `jsconfig.json` дублирует alias `@/*` для подсказок IDE.
- Tailwind: `tailwind.config.js` + `postcss.config.js`. Базовые токены/HSL‑переменные shadcn — в `src/index.css` (`@layer base :root`).
- `components.json` — конфиг shadcn/ui CLI.

---

## 7. Внешние интеграции и аналитика

| Интеграция | Где | Назначение |
|------------|-----|-----------|
| Telegram WebApp JS | `public/index.html` (через клиент Telegram) | данные пользователя, управление окном |
| Telegram Bot API | backend `httpx` | получение аватара |
| PostHog | `public/index.html` (ключ `phc_...`) | продуктовая аналитика + session recording |
| Emergent scripts | `public/index.html` | visual edits / debug monitor (только в iframe) |
| ui-avatars.com | fallback‑URL | заглушка аватара |

> `emergentintegrations==0.1.0` установлена в backend, но в коде не используется. Зарезервирована под будущие LLM‑интеграции (через Emergent LLM key).

---

## 8. Инфраструктура и окружение

### Процессы (supervisor)
| Сервис | Порт | Команда |
|--------|------|---------|
| backend | 8001 | uvicorn (FastAPI) на `0.0.0.0:8001` |
| frontend | 3000 | `craco start` |
| mongodb | 27017 | локальный MongoDB |

Hot reload включён для кода фронта и бэка. Перезапуск нужен только при изменении `.env` или установке зависимостей.

### Переменные окружения
**backend/.env** (не менять URL/порты):
```
MONGO_URL="mongodb://localhost:27017"
DB_NAME="test_database"
CORS_ORIGINS="*"
TELEGRAM_BOT_TOKEN=<bot token>
```
**frontend/.env**:
```
REACT_APP_BACKEND_URL=<внешний URL preview>
WDS_SOCKET_PORT=443
ENABLE_HEALTH_CHECK=false
```

> 🔐 **Замечание по безопасности:** `TELEGRAM_BOT_TOKEN` сейчас закоммичен в репозиторий. Для продакшена токен следует ротировать и хранить только в секретах окружения, а не в git.

---

## 9. Тестирование

- **`backend_test.py`** (корень) — интеграционные тесты на `requests`: проверяют upsert пользователя, получение по `telegram_id` (вкл. 404), эндпоинт аватара. Используют продакшен‑URL.
- **`test_result.md`** — протокол общения main‑агента и testing‑агента (НЕ редактировать защищённую секцию). Текущий статус: все backend‑эндпоинты протестированы и работают; frontend‑регистрацию нельзя протестировать вне Telegram.
- Ручная проверка: `curl -s http://localhost:8001/api/`.

---

## 10. Известные ограничения / технический долг

1. **Прогресс — mock.** `MOCK_PROGRESS` в `DateSelector.js` не связан с БД.
2. **Streak статичен** — всегда «0 дней».
3. **Аватар не выведен в UI** — backend готов, фронт его не вызывает/не рендерит.
4. **Кнопка меню без действия** — нет навигации/Drawer.
5. **Нет уникального индекса** по `telegram_id` в Mongo (только логический upsert).
6. **Один маршрут** `/` — роутер подключён, но экранов больше нет.
7. **Нет аутентификации запросов** — backend не валидирует Telegram `initData` (подпись). Для продакшена стоит проверять `hash` из `initData`.
8. **Демо‑эндпоинты `/api/status`** — наследие шаблона, можно удалить.

---

## 11. Рекомендации по развитию (для AI‑агентов)

При добавлении фич придерживаться существующих паттернов:
- Новые сущности (планы, упражнения, сессии) → отдельные Pydantic‑модели + коллекции, ID = UUID, datetime → ISO.
- Эндпоинты группировать на том же `api_router` с префиксом `/api`.
- Frontend: новые экраны — через `react-router-dom`, UI — из `components/ui` (shadcn), стили — Tailwind + точечный CSS как в `DateSelector.css`.
- Сначала backend (+тест через `deep_testing_backend_v2`), затем frontend.
- Реальные данные прогресса: добавить `progress`/`workout_session` модель, связать с `telegram_id`, заменить `MOCK_PROGRESS`.
