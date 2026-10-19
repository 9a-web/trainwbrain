# AI_CONTEXT.md — TrainWithBrain (Website + Telegram Mini App + PWA)

> **Версия документа:** 4.0
> **Последнее обновление:** Июнь 2026
> **Назначение:** Рабочий контекст для AI‑агентов. Прочитай этот файл ПЕРВЫМ перед любой задачей.
> **Связанные документы:** [`twb_plan.md`](./twb_plan.md) (ТЗ + архитектурный план — источник продуктовой истины) · [`README.md`](./README.md) · [`PROJECT_DETAILS.md`](./PROJECT_DETAILS.md) · [`test_result.md`](./test_result.md) (протокол тестирования) · [`memory/test_credentials.md`](./memory/test_credentials.md)

---

## 0. TL;DR для агента (прочитай за 60 секунд)

- **Что это:** Приложение для трекинга **силовых тренировок** (пауэрлифтинг) с двумя ролями — **спортсмен** и **тренер**. Работает как обычный сайт, как **Telegram Mini App** и как **PWA**.
- **Стек:** React 19 (CRACO) + FastAPI + MongoDB (Motor, async). Кастомный тёмный UI + shadcn/ui + recharts.
- **Текущее состояние:** **зрелый production‑MVP**, НЕ скелет. Реализованы: обязательная аутентификация (email/пароль, Telegram, Google), библиотека программ со скейлингом под 1ПМ, назначение плана, полный жизненный цикл тренировки с **по‑подходным логированием** и таймером отдыха, статистика/streak, **режим тренера** (приглашение, подопечные, редактор плана, видимость draft/published, тренировочные дни), **real‑time co‑scribe через WebSocket**, подтверждение тренером, **старт тренировки тренером**, подробная статистика с графиками, система пропусков. Закрыты **IDOR** на всех `/sessions/*` и `/plans/*`.
- **Где основной код:** backend → `backend/server.py` (монолит ~3400 строк) + `models.py`/`auth.py`/`realtime.py`/`seed.py`. frontend → `frontend/src/` (`App.js`, `api.js`, `components/`, `pages/`, `context/`, `hooks/`).
- **Главное правило:** все API‑роуты начинаются с `/api`. URL/порты/секреты — только из `.env`. ID — только UUID (не ObjectID). Пакеты фронта — только `yarn`. **Аутентификация обязательна** (нет гостевого режима) — почти все запросы требуют `Authorization: Bearer <token>`.

> ⚠️ **Документ v3.0 описывал раннюю версию‑«скелет» (mock‑прогресс, 2 коллекции, 6 эндпоинтов) — это устарело.** Актуальная реальность — ниже.

---

## 1. Суть проекта

**TrainWithBrain (TWB)** — приложение для отслеживания силовых тренировок с **двумя ролями в одном аккаунте**:

- **Спортсмен (athlete)** — выбирает/получает тренировочную программу, запускает тренировку кнопкой «Начать», по ходу отмечает подходы (по‑подходно), видит прогресс, streak и статистику.
- **Тренер (coach)** — ведёт подопечных, готовит и правит планы, **в реальном времени** видит ход тренировки, сам может отмечать/подтверждать выполненное и **запускать тренировку за спортсмена**.

Продуктовое ТЗ, доменная модель и фазовая дорожная карта — в [`twb_plan.md`](./twb_plan.md). Этот файл — техническая карта актуального кода.

---

## 2. Технологический стек (источник истины — `package.json` / `requirements.txt`)

### Frontend
| Технология | Назначение |
|------------|------------|
| React 19 + CRACO | UI, alias `@` → `src` |
| react-router-dom | Роутинг (много маршрутов, см. §6) |
| axios | HTTP‑клиент (`src/api.js`, Bearer‑токен) |
| Tailwind CSS + shadcn/ui + Radix | Стили и компоненты (`src/components/ui/`) |
| recharts | Графики статистики (`pages/Stats.js`) |
| lucide-react | Иконки |
| sonner | Toast‑уведомления (`<Toaster theme="dark" />`) |
| date-fns | Работа с датами |

### Backend
| Технология | Назначение |
|------------|------------|
| FastAPI | REST + нативный WebSocket (`/api/ws`) |
| Motor | Async MongoDB driver |
| Pydantic v2 | Модели (`ConfigDict(extra="ignore")`) |
| passlib[bcrypt] | Хеширование паролей |
| httpx | Async HTTP (Telegram Bot API, Google, Emergent session) |
| openpyxl | Парсинг Excel при генерации seed |
| python-dotenv, uvicorn | Конфиг и ASGI (через supervisor) |

### База данных — MongoDB (Motor), имя из `DB_NAME`
**Коллекции:** `users`, `user_sessions`, `exercises`, `programs`, `plans`, `workout_sessions`, `coach_links`, `plan_day_marks`, `status_checks` (демо).

---

## 3. Структура проекта (актуальная)

```
/app/
├── backend/
│   ├── server.py        # МОНОЛИТ ~3400 строк: все REST‑эндпоинты + WebSocket + бизнес‑логика
│   ├── models.py        # Pydantic‑модели (Exercise, Program*, Plan, WorkoutSession, SetLog, ...)
│   ├── auth.py          # аутентификация: bcrypt, Telegram HMAC, Google (OAuth + Emergent), сессии
│   ├── realtime.py      # ConnectionManager (in-memory), комнаты plan:{id}/user:{tg}, broadcast
│   ├── seed.py          # идемпотентный seed: 29 упражнений + 4 шаблона (uuid5), индексы
│   ├── seed_data/       # исходные данные шаблонов (напр. pl_autumn_3m.json)
│   ├── requirements.txt
│   └── .env             # MONGO_URL, DB_NAME, CORS_ORIGINS, TELEGRAM_BOT_TOKEN, GOOGLE_CLIENT_ID/SECRET
│
├── frontend/
│   └── src/
│       ├── App.js               # AuthProvider + роуты + Splash + Google‑callback
│       ├── api.js               # обёртка axios: API=${REACT_APP_BACKEND_URL}/api, WS_BASE, Bearer
│       ├── context/
│       │   ├── AuthContext.js   # логин/регистрация/logout, switchMode, token в localStorage (twb_token)
│       │   └── UserContext.js   # текущий пользователь, аватар, Telegram init + dev‑fallback
│       ├── hooks/
│       │   ├── useRealtime.js   # WebSocket‑клиент (reconnect + backoff), диспатч событий
│       │   └── useTelegramUI.js # platform-aware Telegram WebApp (haptics, кнопки)
│       ├── components/
│       │   ├── DateSelector.js  # недельный селектор + прогресс‑кольца + «План»‑пикер + пропуски
│       │   ├── WorkoutView.js   # экран тренировки: по‑подходный чек‑лист, таймер отдыха, настройки
│       │   ├── InstallPrompt.js # PWA install‑кнопка
│       │   └── ui/              # shadcn/ui
│       ├── pages/
│       │   ├── Login.js         # 3 метода входа
│       │   ├── Profile.js       # режим athlete/coach, «Подопечные», «Мой тренер», настройки
│       │   ├── Programs.js      # библиотека шаблонов + назначение плана (модалка максимумов/дней)
│       │   ├── Coach.js         # кабинет тренера: invite‑код + список подопечных
│       │   ├── CoachClient.js   # карточка подопечного: план, видимость, дни, публикация недель
│       │   ├── CoachLiveSession.js # LIVE‑экран тренировки подопечного (co-scribe + подтверждение + старт)
│       │   ├── CoachPlanEditor.js  # редактор снимка плана (недели/дни/упражнения CRUD)
│       │   ├── Stats.js         # подробная статистика с графиками (свои + подопечного, recharts)
│       │   └── Streak.js        # экран тренировочной серии
│       └── .env                 # REACT_APP_BACKEND_URL, WDS_SOCKET_PORT
│
├── AI_CONTEXT.md   # ← этот файл (техническая карта кода)
├── twb_plan.md     # ТЗ + архитектура + фазовая дорожная карта (продуктовый источник истины)
├── test_result.md  # протокол тестирования (используется testing‑агентами)
└── memory/test_credentials.md  # тестовые аккаунты + заметки окружения
```

---

## 4. Аутентификация и безопасность (реализовано)

### 4.1 Три метода входа, одна модель сессии
Реализация — `backend/auth.py` + эндпоинты `/api/auth/*` в `server.py`. Гостевого режима НЕТ — вход обязателен.
1. **Email + пароль** — bcrypt (`passlib`), `password_hash` НИКОГДА не возвращается в ответах.
2. **Telegram WebApp** — валидация `initData` по HMAC‑SHA256 бот‑токеном (`validate_telegram_init_data`).
3. **Google** — два пути: прямой OAuth 2.0 (`/auth/google/oauth`, своё брендирование, ключи в `.env`) и Emergent Managed (`/auth/google/session`, keyless, exchange `session_id`).

- Каждый аккаунт ключуется по `telegram_id` (реальный для Telegram; **синтетический** `900_000_000_000+` для email/Google) — вся плановая/сессионная логика работает единообразно.
- Сессии — непрозрачные токены в `user_sessions` `{session_token, telegram_id, auth_method, expires_at(ISO), created_at}`, TTL 7 дней.
- Зависимость `get_current_user` читает `Authorization: Bearer <token>` (в первую очередь), затем cookie `session_token`. Фронт хранит токен в `localStorage["twb_token"]` и ставит его дефолтным заголовком axios.

### 4.2 Авторизация по ролям / защита от IDOR (закрыто на всех `/sessions/*` и `/plans/*`)
Хелперы в `server.py`:
- `_assert_coach_of(coach_tgid, athlete_tgid)` — 403, если между ними нет `active` `coach_link`.
- `_assert_can_edit_plan(current, plan)` — редактировать план может только владелец‑спортсмен ИЛИ его активный/назначенный тренер.
- `_assert_session_read(current, session)` — читать сессию может только владелец или его тренер.
- `_assert_session_actor(current, session, actor, by)` — действия от имени тренера (`actor=coach&by=<tgid>`) разрешены только реальному привязанному тренеру; подмена чужого `by` → 403.
- Неавторизованный запрос → **401**, чужой доступ → **403**. Покрыто backend‑тестами (см. `test_result.md`).

---

## 5. API‑контракт (актуальный, префикс `/api`)

Все роуты в `backend/server.py` через `APIRouter(prefix="/api")`; WebSocket — `@app.websocket("/api/ws")`.

### 5.1 Auth и пользователи
`POST /auth/register` · `POST /auth/login` · `POST /auth/telegram` · `POST /auth/google/session` · `GET /auth/google/config` · `POST /auth/google/oauth` · `GET /auth/me` · `POST /auth/logout`
`POST /users` (upsert) · `GET /users/{telegram_id}` · `PATCH /users/{telegram_id}/mode` · `PATCH /users/{telegram_id}/settings` · `GET /telegram/avatar/{user_id}`

### 5.2 Каталог и программы
`GET /exercises` (?query=&muscle=&owner=) · `POST /exercises`
`GET /programs/templates` (4 built‑in) · `GET /programs/templates/{id}` · `POST /programs/templates`

### 5.3 Планы (снимок программы)
`POST /plans` (из `template_id`; поддерживает `maxes`, `training_days`, `coach_telegram_id`, `visibility`) · `GET /plans/active/{telegram_id}` (для draft‑плана спортсмену возвращает пустые `weeks`) · `GET /plans/{id}` · `GET /plans/{id}/day?week=&day=&viewer=` · `GET /plans/{id}/week-progress?week=&viewer=&dates=`
**Редактор (тренер/владелец, guard `_assert_can_edit_plan`):** `PATCH /plans/{id}` · `PUT/DELETE /plans/{id}/day` · `PUT/DELETE /plans/{id}/exercise` · `POST/DELETE /plans/{id}/week` · `PATCH /plans/{id}/visibility` · `PATCH /plans/{id}/weeks/{week}/publish` · `PATCH /plans/{id}/training-days`
**Пропуски/переносы (P2.1):** `POST /plans/{id}/day/skip` · `POST /plans/{id}/day/reschedule` · `PATCH /plans/{id}/day/{week}/{day}/mark` · `DELETE /plans/{id}/day/{week}/{day}/mark` · `GET /plans/{id}/missed`

### 5.4 Тренировочные сессии (Phase 2 + P4 co‑scribe)
`POST /sessions/start` (409 при активной сессии; поддерживает `coach_telegram_id` → старт тренером) · `GET /sessions/active?plan_id=&week=&day=&athlete=` · `GET /sessions/{id}`
`PATCH /sessions/{id}/exercise/{order}?action=done|skip|reset&actor=&by=` — статус упражнения (co‑scribe)
`PATCH /sessions/{id}/exercise/{order}/set/{set_index}` — **по‑подходное логирование** (done/skipped + факт. вес/повторы)
`PATCH /sessions/{id}/exercise/{order}/edit` — правка схемы подходов/названия/комментария
`POST /sessions/{id}/finish` · `POST /sessions/{id}/resume` · `POST /sessions/{id}/pause?resume=`
`POST /sessions/{id}/confirm` — тренер подтверждает всю тренировку
`PATCH /sessions/{id}/exercise/{order}/confirm` — тренер подтверждает упражнение (toggle)
`GET /sessions/{id}/deviation` — отклонения план↔факт

### 5.5 Тренер
`POST /coach/invite` · `POST /coach/link` · `POST /coach/unlink` · `GET /athlete/{telegram_id}/coach` · `GET /coach/{telegram_id}/clients` · `GET /coach/{coach}/clients/{athlete}/plan` (coach‑gated) · `GET /coach/{coach}/clients/{athlete}/session` (coach‑gated LIVE)

### 5.6 Статистика (P7)
`GET /stats/{telegram_id}` · `GET /stats/{telegram_id}/detailed` · `GET /stats/{telegram_id}/exercise-progress` · `GET /stats/{telegram_id}/streak` · `GET /coach/{coach}/clients/{athlete}/stats` (coach‑gated) · `GET /coach/{coach}/clients/{athlete}/exercise-progress` (coach‑gated)

### 5.7 WebSocket — `WS /api/ws?token=<session_token>`
Хендшейк валидирует токен (иначе рефьюз), подписывает на комнаты `user:{telegram_id}` и `plan:{plan_id}`. События (см. `twb_plan.md` §6.4): `session.started/finished`, `set.filled`, `exercise.confirmed`, `session.confirmed`, `plan.published`, `training_days.updated`, `presence` и т.д. **Источник истины — БД; WS только транслирует.** На реконнекте — REST‑«догон».

### 5.8 Конвенции сериализации (обязательно в новых эндпоинтах)
- `id` = `str(uuid.uuid4())`; для built‑in — детерминированный `uuid5(slug)`.
- `datetime` → ISO‑строка при записи, парсинг при чтении. `datetime.now(timezone.utc)`.
- Чтение из Mongo всегда с `{"_id": 0}` — никаких ObjectId‑утечек и `password_hash` в ответах.

---

## 6. Frontend: маршруты и ключевые компоненты

```
/                        → Home: приветствие, streak (реальный), DateSelector
/programs                → библиотека шаблонов + назначение плана
/profile                 → режим athlete/coach, «Подопечные», «Мой тренер», настройки
/stats                   → своя подробная статистика (recharts)
/streak                  → тренировочная серия
/coach                   → кабинет тренера (invite + подопечные)
/coach/:athleteId        → карточка подопечного (план, видимость, дни)
/coach/:athleteId/live   → LIVE‑экран тренировки (co-scribe, подтверждение, старт за спортсмена)
/coach/:athleteId/edit   → редактор плана подопечного
/coach/:athleteId/stats  → статистика подопечного (coach‑gated)
/auth/google             → обработка Google OAuth redirect
```

- **`WorkoutView.js`** — центральный экран тренировки: по‑подходный чек‑лист (кнопки «Выполнить»/«Пропустить» на каждый подход), редактируемые факт. вес/повторы, оверлей‑**таймер отдыха** (появляется после отметки подхода при наличии `rest_seconds`), модалка **«Настройки тренировки»** (⚡), бейджи подтверждения тренером.
- **`CoachLiveSession.js`** — тренер видит live‑ход тренировки: тумблер‑щит подтверждения на упражнении, кнопка «Подтвердить тренировку», co‑scribe отметки; в пустом состоянии — кнопки старта тренировки за спортсмена.
- **`DateSelector.js`** — недельный селектор (реальный прогресс из `week-progress`), точки‑недели + модалка «План», карточки дней с бейджами пропусков; для draft‑плана — карточка «план готовится».

---

## 7. Дизайн‑система (сохраняется)

- **Цвета:** фон `#1C1C1C`; акцент `#FF6B00`; градиент выбранного дня `linear-gradient(-34deg, #FF8A24, #FFDA24)`; карточка `#333`; muted `#959595`; текст `#FFFFFF`/`rgba(255,255,255,.7)`.
- **Шрифты:** Plus Jakarta Sans (основной) + GG Zaglav (крупная дата 56px, локальный woff2).
- **Тёмная тема сквозная** (веб, Telegram, PWA); адаптив mobile‑first с центрированием колонки `max-width: 720px` при ≥768px. Брейкпоинты `374/767/1023/1024`.
- Toaster `sonner` — тёмная тема, `position="top-center"`.

---

## 8. Кроссплатформенность (реализовано)

- **Website‑first + Telegram WebApp (`telegram-web-app.js`) + PWA** (manifest + service‑worker + иконки, `InstallPrompt.js`).
- Детект среды: `document.documentElement[data-env]` = `telegram | pwa | web`; `[data-platform]` = `tg.platform`.
- `useTelegramUI.js` — platform‑aware: haptics с guard (`tg.HapticFeedback?.impactOccurred?.(...)`), Telegram‑кнопки с graceful‑degradation в вебе.
- Dev‑fallback пользователь вне Telegram (для локальной разработки/автотестов) — в `UserContext.js`.

---

## 9. Правила для AI‑агентов (DO / DON'T)

### ❌ НЕ ДЕЛАТЬ
1. `npm` — только `yarn` для фронта.
2. Хардкод URL/портов/секретов — всё из `.env`; без дефолтов (fail‑fast).
3. MongoDB ObjectID — только UUID; в ответах не должно быть `_id`/`password_hash`.
4. Запуск uvicorn/yarn вручную — только supervisor.
5. Менять значения в `.env` (`REACT_APP_BACKEND_URL`, `MONGO_URL`, `DB_NAME`).
6. `create_file(overwrite=True)` для существующих без нужды — предпочтительно `search_replace`.
7. Реализовывать сторонние интеграции/аутентификацию «по памяти» — только через integration‑playbook.

### ✅ ДЕЛАТЬ
1. Все API‑роуты с префиксом `/api`; фронт → бэкенд через `process.env.REACT_APP_BACKEND_URL` + `/api`.
2. Новые защищённые эндпоинты — с `Depends(get_current_user)` и проверкой владения (IDOR).
3. Datetime → ISO при записи; `{"_id": 0}` при чтении.
4. Каждый интерактивный/значимый элемент UI — с `data-testid` (kebab‑case).
5. После правки `.env`/зависимостей — `sudo supervisorctl restart backend|frontend`.
6. Перед тестированием — обновлять `test_result.md`; backend тестировать первым.
7. Отвечать пользователю **на русском**.

---

## 10. Команды разработки

```bash
sudo supervisorctl status                 # состояние сервисов
sudo supervisorctl restart backend|frontend
tail -n 100 /var/log/supervisor/backend.err.log
curl -s http://localhost:8001/api/         # health (локально)
# внешний e2e: $REACT_APP_BACKEND_URL/api/
```

---

## 11. Статус фаз (кратко; детали — `twb_plan.md`)

| Фаза | Статус | Что готово |
|------|--------|-----------|
| P0 Фундамент | ✅ | индексы, роли/режим, dev‑fallback |
| P1 Программы и план | ✅ | 29 упражнений, 4 шаблона, снимок плана, реальный прогресс (mock убран) |
| P2 Тренировка и статистика | ✅ | lifecycle сессии, **по‑подходный лог + таймер отдыха + настройки**, тоннаж/%1ПМ/streak |
| P2.1 Пропуски + отклонения | ✅ backend | `plan_day_marks`, skip/reschedule/mark/missed, adherence, streak strict/lenient |
| P3 Режим тренера | ✅ | invite/link, подопечные, редактор плана, draft/published, недели, тренировочные дни, **подтверждение тренером**, **старт тренировки тренером** |
| P4 Real‑time (WebSocket) | ✅ | `/api/ws`, ConnectionManager, co‑scribe (`filled_by`/`coach_confirmed`), `useRealtime` |
| Аутентификация | ✅ | 3 метода, сессии, **IDOR закрыт** на `/sessions/*` и `/plans/*` |
| P7 Подробная статистика | ✅ | detailed/exercise‑progress/adherence + экран графиков (recharts) |
| CP Кроссплатформенность | ✅ база | website + Telegram + PWA, детект среды, адаптив, safe‑area |
| P5 Доступ по неделям + оплата | ⏳ | week_access gating + опц. оплата (Stars/Stripe) — не начато |
| P6 Импорт/экспорт + полировка | 🟡 | Excel‑шаблон готов; UI‑загрузка файла, импорт по коду/ссылке, экспорт, конструктор — впереди |

---

## 12. Технический долг / риски
1. `server.py` — монолит ~3400 строк; кандидат на разбиение по FastAPI‑роутерам (`routes/`, `models/`, `services/`). Не приоритет.
2. `ConnectionManager` in‑memory — не масштабируется на несколько подов → Redis Pub/Sub (future).
3. WebSocket за ingress — держать префикс `/api/ws`; на мобильных — reconnect + REST‑«догон» при `visibilitychange`.
4. Bot token / Google secret — держать в секретах, ротировать на проде; при деплое добавить `<origin>/auth/google` в Google Console.
5. Снимок плана дублирует данные — приемлемо ради изоляции истории.

---

## 13. История изменений
| Дата | Версия | Изменения |
|------|--------|-----------|
| Янв–Июль 2025 | 1.0–3.0 | Ранние версии (скелет: Header, DateSelector, mock‑прогресс) |
| Июнь 2026 | 4.0 | **Полная пересборка документа под актуальный код.** Отражены: обязательная аутентификация (email/Telegram/Google, сессии), закрытие IDOR на `/sessions/*` и `/plans/*`, по‑подходное логирование + таймер отдыха + настройки (P2), режим тренера с подтверждением и стартом тренировки тренером (P3), real‑time co‑scribe WebSocket (P4), подробная статистика с графиками (P7), пропуски/отклонения (P2.1), кроссплатформенность (website + Telegram + PWA). Актуализированы структура, API‑контракт (60+ эндпоинтов), коллекции (9), маршруты фронта, правила агентов |
