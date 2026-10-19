# Test Credentials & Environment Notes — TrainWithBrain

## Auth
- **NEW: Three authentication methods implemented (mandatory auth, no guest mode):**
  1. **Email/Password** — bcrypt hashing, JWT-less session tokens
  2. **Telegram WebApp** — initData HMAC validation with bot token
  3. **Google OAuth** — Emergent Managed Auth (session exchange)
- Every account has a `telegram_id` (real for Telegram users, synthetic 900000000000+ for email/Google)
- Session model: `user_sessions` collection with `session_token`, `telegram_id`, `auth_method`, `expires_at`, `created_at`
- Auth dependency reads `Authorization: Bearer <token>` header first, then `session_token` cookie

### Test Accounts Created (Email Auth)
- **Email**: `authtest+1781538884@example.com`
- **Password**: `password123`
- **telegram_id**: `950454640997` (synthetic)
- **Token**: Session tokens are ephemeral and regenerated on each login

### Test Accounts Created (Telegram Auth)
- **telegram_id**: `123456789` (test account via valid HMAC signature)
- **first_name**: `TestTG`
- **username**: `testtg`

## URLs
- ⚠️ ВАЖНО (июль 2025): актуальный внешний URL контейнера = `https://71abc944-116e-42bd-b095-cd66d156f438.preview.emergentagent.com` (из env `preview_endpoint`). `frontend/.env` REACT_APP_BACKEND_URL обновлён на него (был устаревший `avatar-loader-1...` из клона — он отдавал 404 на всех `/api`). Менять не нужно.
- Backend локально: `http://localhost:8001` (health: `/api/`).

## Diary (Дневник) — UI demo account (июль 2025)
- Email: `diaryui@twb.dev`  Password: `password123` (name Иван) — имеет 1 дневниковую запись на сегодня.
- ИИ: RouterAI DeepSeek V4 Flash АКТИВЕН (AI_BASE_URL/AI_API_KEY/AI_MODEL в backend/.env), `/api/ai/status` enabled=true. Vision (Gemini) НЕ настроен (фото-разбор — future).
- Дневник = отдельный режим (тумблер «План/Дневник» на главном экране). Эндпоинты /api/diary/* протестированы (11/11 сценариев зелёные).

## (устар.) URLs — прошлые сессии
- Внешний URL приложения (frontend + `/api` + WebSocket `/api/ws`): `https://7fa95d68-09f5-4c1c-a975-7595ef3af056.preview.emergentagent.com`
- Backend локально: `http://localhost:8001` (health: `/api/`).
- `frontend/.env` → `REACT_APP_BACKEND_URL=https://7fa95d68-09f5-4c1c-a975-7595ef3af056.preview.emergentagent.com` (обновлён под текущий контейнер из env `preview_endpoint`). Менять не нужно.
- ⚠️ Google OAuth: в текущем `backend/.env` НЕТ `GOOGLE_CLIENT_ID/SECRET` → прямой Google-вход не работает без ключей и без обновления redirect_uri под новый домен. Email-вход работает.

## Stats demo account (актуальный, июнь 2026, redesign статистики)
- Email: `statsdemo@twb.dev`  Password: `password123`
- telegram_id: 961727460933; активный план: pl-autumn-3m (maxes 200/130/230, дни [1,3,5]); план id d72cc5d5-a11b-40be-9526-622ef5da628a (обновлён iter6)
- 9 завершённых тренировок за 3 микроцикла (после ре-сидов тест-агентом может быть больше; актуальный план см. ниже), даты раскиданы по 3 календарным неделям.
- Использовать для проверки /stats и /streak. Пересоздать данные: `python /app/scripts/setup_stats_demo.py`.
- Демо-шаблон P6: «Силовая база 5×5» id `b85dbff0-ef78-48f6-805d-2a6417e912df`, share code `TWB-ZZB5ZS` (НЕ удалять — используется тестами импорта/landing).
- Второй пользователь (импорт/403-проверки): `dbg1783466020@ex.com` / `password123` (tg 922324126010).
- ИИ (P6): **АКТИВИРОВАН** через RouterAI (`https://routerai.ru/api/v1`, модель `deepseek/deepseek-v4-flash`). Ключ и base URL — в `backend/.env` (`AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`). `/api/ai/status` → `{enabled: true}`. Проверено `/api/ai/program/generate` — генерирует валидные программы с прогрессией и fuzzy-маппингом на каталог.
- ИИ-генерация (июнь 2026): системный промпт усилен (`_AI_SYSTEM_GEN` в server.py) — научно обоснованные принципы (объём 10–20 подходов/мышцу/нед, частота 2×/нед, RIR, волновая периодизация Wendler 5/3/1, deload каждая 4-я неделя); `max_tokens` поднят до 32000 (модель reasoning — рассуждения съедают бюджет токенов, при 16000 ответ обрезался). JSON-парсинг устойчив: `_extract_json` использует `json_repair` (markdown-обёртки, обрезанный JSON, висячие запятые). Проверено e2e: 4 нед × 4 дня × 7 упр, прогрессия 65/75/85 → 70/80/90 → 75/85/95 → deload 50%.
- Двухшаговая генерация (июнь 2026): `POST /api/ai/program/questions` (уточняющие вопросы 3–5 с вариантами) → фронт показывает чипсы + «свой ответ» → `POST /api/ai/program/generate` с `answers`. Долгие ИИ-запросы (>60 c обрубает ingress) выполняются как фоновые задачи: generate/parse/parse-file возвращают `{job_id}`, статус — `GET /api/ai/program/jobs/{job_id}` (pending|done|error, done → поле template). Фронт поллит каждые 3 c (AiImport.js run()). Коллекция БД: `ai_jobs`.
- Прочие аккаунты из прошлых сессий (coachdemo/athdemo/phase1demo/statsdemo1782072251) в БД текущего форка ОТСУТСТВУЮТ.

## Phase 3 LIVE demo (coach-led session start) — fresh pair, plan PUBLISHED, NO session yet (regenerated Jun 2026)
- COACH: `coachlive_1783465140@twb.dev` / `password123` (tg 963560813038, active_mode=coach, linked to athlete below)
- ATHLETE: `athlive_1783465140@twb.dev` / `password123` (tg 948427726315, plan published, NO workout session)
- Plan: full-body-beginner, training_days [2,4,6] (today = Tue = day 2 is a workout day). Plan id 33643cd8-2503-4652-be03-f677d9890cc2.
- NOTE: re-run /tmp/setup_live.py to regenerate a fresh no-session pair if the session was already started.

## Phase 2 demo accounts (coach confirmation) — coach linked to athlete, athlete has a FINISHED workout today- COACH: `coachdemo_1783458678@twb.dev` / `password123` (role coach; open the client's live session to confirm)
- ATHLETE: `athdemo_1783458678@twb.dev` / `password123` (has a finished workout today; will show confirmed badges after coach confirms)
- Flow: login as coach -> Профиль says coach mode / open «Кабинет тренера» -> client card -> «Наблюдать» (live) -> confirm exercises (shield toggle) + «Подтвердить тренировку». Then login as athlete -> Home workout shows blue «подтв.» badges + «Тренировка подтверждена тренером» banner.

## Phase 1 demo account (per-set logging + rest timer) — has an IN-PROGRESS workout
- Email: `phase1demo_1783429894@twb.dev`  Password: `password123`
- Active plan: pl-autumn-3m (maxes 200/130/230). An in-progress session exists on today's workout day; exercise #0 has a 6-set checklist with sets 1–2 already marked done (set 2 edited to 152.5кг × 4).
- Use for verifying: per-set checkboxes, editable weight/reps per set, ⏱ rest button -> bottom rest-timer overlay, ⚡ button -> «Настройки тренировки» modal.
- NOTE: session dates are stamped to the container's "today"; if the demo session isn't visible on Home, re-run /tmp/setup_known.py to create a fresh one.

## Cross-platform (реализовано)
- Website-first + Telegram WebApp (telegram-web-app.js) + PWA (manifest + service-worker + иконки).
- Детект среды: `document.documentElement[data-env]` = `telegram | pwa | web`, `[data-platform]` = `tg.platform`.
- Адаптив: контент центрируется в колонке `max-width: 720px` при `>=768px`; мобильный (<768px) не изменён.

## Seed data (built-in)
- 29 упражнений, 4 шаблона программ: `full-body-beginner`, `upper-lower`, `powerlifting-peaking` (slug), `pl-autumn-3m` («3 мес Подготовка на осень»).

## Google OAuth (direct, own credentials) — added
- Switched from Emergent-managed to DIRECT Google OAuth (own branding on consent screen).
- Config: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in backend/.env (secret NOT stored here).
- Public config endpoint: GET /api/auth/google/config -> {client_id}.
- Flow: frontend redirects to accounts.google.com -> back to <origin>/auth/google?code=... -> POST /api/auth/google/oauth {code, redirect_uri} -> {token, user}.
- Registered redirect URI (Google Console): https://brainjam-1.preview.emergentagent.com/auth/google
- No app-managed password for Google accounts. On deploy, the deployed domain's origin + /auth/google must also be added in Google Console.

## Stats demo account (P7, has data)
- Email: `statsdemo1782072251@example.com`  Password: `password123`
- telegram_id: 950482709876; active plan: pl-autumn-3m (maxes 200/130/230, days [1,3,5]); 9 finished workouts across 3 microcycles.
- Use for /stats and (after linking a coach) /coach/{coach}/clients/950482709876/stats.

## Streak demo account (июль 2026, редизайн «Тренировочной серии»)
- Email: `streakdemo@twb.dev`  Password: `password123`  (tg 992689326272)
- 13 завершённых тренировок: серии 5 дн (~4 нед назад), 3 дн (~2 нед назад), текущая 2 дн (вчера+сегодня) + 3 одиночных дня.
- Использовать для проверки GET /api/stats/{tg}/streak (поля streaks, this_month, avg_per_week, streak_len/streak_start/streak_end в calendar) и экрана /streak.
- Пересоздать: `python /app/scripts/setup_streak_demo.py` (даты привязаны к «сегодня» контейнера).

## AI dual-provider (июль 2026, эта сессия)
- **Текстовый провайдер (генерация/refine/parse):** DeepSeek V4 Flash через RouterAI.
  - `AI_BASE_URL=https://routerai.ru/api/v1`, `AI_MODEL=deepseek/deepseek-v4-flash`,
    `AI_API_KEY=sk-nsDjxUsUAi_WkeICOwhWIgMcwNM7IMKm` (RouterAI, не официальный DeepSeek — важно!)
- **Vision-провайдер (разбор фото):** Google Gemini через OpenAI-совместимый эндпоинт.
  - `AI_VISION_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`,
    `AI_VISION_MODEL=gemini-flash-latest`, `AI_VISION_API_KEY=AQ.Ab8RN6Lm-...` (из AI Studio).
- `GET /api/ai/status` → `{enabled: true, model: "...", vision_enabled: true, vision_model: "..."}`.
- Новый эндпоинт `POST /api/ai/program/parse-photo` (multipart, до 8 файлов, ≤8МБ каждый, image/*):
  двухшаговый пайплайн Gemini(текст из фото) → DeepSeek(структура) → сохранённый шаблон.
  Фоновая задача (job_id), опрос через `GET /api/ai/program/jobs/{id}`. E2E проверено curl'ом на реальном
  тестовом изображении с расписанием — вернулась валидная программа.
- Frontend `AiImport.js` — третья вкладка «По фото» с фото-гридом (до 8 фото), превью с крестиками
  удаления, счётчик N/8, «Очистить», отдельный BusyOverlay (40–90 c).
- test IDs: `ai-tab-photo`, `ai-photo-input`, `ai-photo-pick-btn`, `ai-photo-add-more`,
  `ai-photo-thumb-{i}`, `ai-photo-remove-{i}`, `ai-photos-grid`, `ai-photos-clear`, `ai-parse-photo-btn`,
  `ai-vision-disabled`.

## Diary Test Accounts (created 2026-07-17T08:57:58.590957)
- User1: diarytest1_4439866453@example.com / password123 (telegram_id=940106816105)
- User2: diarytest2_4439866453@example.com / password123 (telegram_id=932320348665)

## Diary Test Accounts (created 2026-07-17T08:58:32.762412)
- User1: diarytest1_5725097977@example.com / password123 (telegram_id=964061407257)
- User2: diarytest2_5725097977@example.com / password123 (telegram_id=948083179997)

## Diary Test Accounts (created 2026-07-17T08:59:50.071602)
- User1: diarytest1_9007716683@example.com / password123 (telegram_id=948226801050)
- User2: diarytest2_9007716683@example.com / password123 (telegram_id=950384182754)

## Diary Test Accounts (created 2026-07-17T09:01:09.117780)
- User1: diarytest1_8766816358@example.com / password123 (telegram_id=910261795567)
- User2: diarytest2_8766816358@example.com / password123 (telegram_id=902045044155)
