# planTrainWBrain.md — План развития TrainWithBrain для тренеров

> **Версия:** 1.0
> **Назначение:** рабочий план для ИИ-агентов и разработчиков. Здесь — продуктовая цель, роли, доменная модель, фазы работ, API, компоненты UI, пайплайны ИИ и критерии приёмки.
> **Читать перед стартом:** [`AI_CONTEXT.md`](./AI_CONTEXT.md) → [`twb_plan.md`](./twb_plan.md) → этот файл.
> **Стек (не меняем):** React 19 + CRACO + Tailwind + shadcn/ui + recharts (frontend) · FastAPI + MongoDB (Motor) + Pydantic v2 (backend) · DeepSeek V4 Flash (текст) + Gemini (vision) через RouterAI.

---

## 0. Как пользоваться этим документом (для ИИ-агентов)

1. Прочитай `AI_CONTEXT.md` (технические правила) и этот файл.
2. Работай **по одной фазе** из §6. Не смешивай фазы в одном PR/сеансе.
3. Каждая фаза имеет **Цель · Backend · Frontend · Модель данных · API · DoD (Definition of Done)**. Фаза считается готовой только при выполнении DoD и прохождении тестов из §11.
4. Соблюдай конвенции проекта: `/api`-префикс, UUID (не ObjectID), `datetime`→ISO, чтение Mongo с `{"_id": 0}`, `Depends(get_current_user)` + проверка владения (IDOR), только `yarn` для фронта, секреты только из `.env`, ответы пользователю — на русском.
5. Все новые интерактивные элементы UI — с `data-testid` (kebab-case).
6. Не трогай уже существующие защищённые контракты без причины; расширяй существующие файлы, а не плоди новые.
7. Для ИИ-задач используй существующие хелперы `_ai_chat` (текст) и `_ai_chat_vision` (фото) в `backend/server.py`; не подключай новых вендоров без явного решения.

---

## 1. Продуктовая цель

Превратить TWB из трекера силовых тренировок в **рабочий инструмент фитнес-тренера** и **личного помощника атлета**:

- Тренер ведёт подопечных, назначает силовые и **кардио**-нагрузки, видит объём и баланс по мышцам, контролирует питание.
- Подопечный (managed athlete) ведёт тренировки и видит **read-only отчёт**: как нагрузили (карта мышц), кардио, дневник, прогноз.
- **Самостоятельный атлет (standalone)** — человек без тренера, который хочет вести учёт и прогрессировать сам: тот же движок, но self-service и доступ по инвайт-коду.

### Принципы продукта
- **Одна учётная запись — разные режимы.** Роли/режимы переключаются, данные не дублируются.
- **Тренер — центр ценности.** Всё, что видит атлет, тренер видит лучше и управляет этим.
- **Данные важнее украшений.** Любая визуализация опирается на реальные агрегаты, а не на мок.
- **ИИ — ассистент, не истина.** Все ИИ-оценки (калории, прогноз) помечаются уверенностью и редактируются вручную.
- **Красиво и мобильно.** Тёмная тема `#1C1C1C`, акцент `#FF6B00`, mobile-first, PWA/Telegram.

---

## 2. Роли и модель доступа

### 2.1 Роли (`users.roles`)
| Роль | Описание |
|------|----------|
| `athlete` | Тренируется и ведёт учёт |
| `coach` | Ведёт подопечных, управляет планами/нагрузкой |
| `admin` | Выдаёт standalone-доступ, управляет инвайтами (может быть один — владелец) |

### 2.2 Тип атлета (`users.access_tier`)
| Значение | Как получает | Возможности |
|----------|--------------|-------------|
| `coach_managed` | По инвайту тренера (есть `active` coach_link) | **Силовые — только просмотр** (заполняет тренер); кардио и питание — самостоятельное заполнение; аналитика read-only |
| `standalone` | По standalone-инвайту (обособленный спортсмен) | Полный self-service: сам выбирает/генерирует план, **сам заполняет силовые/кардио/питание**, видит всю аналитику |

> **Вход — только по инвайту.** Новый email/Google/Telegram-аккаунт не получает доступа к приложению, пока не применит код: после регистрации/входа пользователь видит только экран `/welcome` (ввод кода) до успешного `POST /invites/redeem`. Без кода приложение недоступно.
> `access_tier` проставляется при redeem инвайта и хранится явно.

### 2.3 Права (`users.permissions`) — гранулярно, под каждого спортсмена
Возможности управляются **точечно** (админ-панель §Фаза 1 / `/admin`): админ выдаёт права каждому атлету отдельно. Для managed-атлета по умолчанию действует профиль «физический подопечный» (силовые — просмотр), для standalone — «всё доступно».

```jsonc
"permissions": {
  "log_strength": false,   // managed=false (тренер заполняет), standalone=true
  "log_cardio": true,      // атлет сам отмечает дорожку
  "log_nutrition": true,   // атлет сам ведёт питание
  "view_strength": true,
  "view_muscle_map": true,
  "view_cardio": true,
  "view_nutrition": true,
  "view_forecast": true,
  "view_goals": true,
  "manage_plan": false,    // standalone=true
  "ai_programs": false     // standalone=true
}
```
- `permissions` хранится в `users` (с полями `permissions_updated_by`, `permissions_updated_at`); админ может менять в любой момент, это не влияет на `access_tier` и `coach_link`.
- `GET /me/capabilities` возвращает итоговые вычисленные права (дефолт по `access_tier` + админ-оверрайды).

### 2.4 Матрица возможностей (дефолты)
| Возможность | Coach | Managed athlete | Standalone athlete |
|-------------|:-----:|:---------------:|:------------------:|
| Заполнять свою силовую | ✅ (за клиента, co-scribe) | ❌ (только просмотр) | ✅ |
| Заполнять кардио | ✅ (за клиента) | ✅ | ✅ |
| Заполнять питание | ✅ (за клиента) | ✅ | ✅ |
| Карта мышц (своя) | ✅ | ✅ (read-only) | ✅ |
| Дневник + цели + прогноз | ✅ | ✅ (read-only) | ✅ (полный) |
| Редактировать свой план | ✅ (план клиента) | ❌ (план тренера) | ✅ |
| ИИ-генерация программы | ✅ (для клиента) | ❌ | ✅ |
| Аналитика клиента (вкл. детальный дневник питания и вес) | ✅ | ❌ | – |
| Создавать клиентские инвайты | ✅ | ❌ | ❌ |
| Standalone-инвайты и права атлетов | ✅ **только админ** | ❌ | ❌ |

> **Приватность:** тренер видит **все** данные своих подопечных — включая детальный дневник питания, вес/замеры и кардио (решение владельца, O3 закрыто).

---

## 3. Аудит текущего состояния (что переиспользуем)

**Уже есть и работает:**
- Аутентификация: email/пароль, Telegram HMAC, Google OAuth; сессии Bearer, TTL 7 дней; IDOR-гарды (`_assert_can_edit_plan`, `_assert_session_read`, `_assert_session_actor`, `_assert_coach_of`).
- Программы/шаблоны, снимки планов, скейлинг по 1ПМ, редактор тренера, draft/published, недели.
- Тренировочные сессии: по-подходное логирование, таймер отдыха, суперсеты, co-scribe по WebSocket, подтверждение тренером.
- Статистика: `/stats/{tg}`, `/detailed`, `/exercise-progress`, `/streak`, `/muscle-groups`; графики (recharts).
- Дневник (mode=`diary`) + ИИ-парсинг текста/фото, чат-агент (`diary_chats`), profile (`diary_profile`).
- Уведомления (`notification_settings`, `notification_log`, scheduler).
- ИИ: `_ai_chat` (DeepSeek) + `_ai_chat_vision` (Gemini), фоновые задачи (`ai_jobs`), поллинг.

**Коллекции сейчас:** `users, user_sessions, exercises, programs, plans, workout_sessions, coach_links, plan_day_marks, diary_chats, diary_profile, notification_settings, notification_log, ai_jobs, status_checks`.

**Канонические мышцы сейчас** (`seed.py`): `legs, quads, hamstrings, glutes, calves, chest, back, lats, shoulders, biceps, triceps, core` — для карты мышц нужна более детальная таксономия (§6.2).

**Уже исправлено (сессия 2026-09-29):** секреты вынесены из `.env`, TLS-проверка Mongo включена, cookie-аутентификация убрана (CSRF), rate-limit по XFF исправлен, тайминг-атака на login, `state` в Google OAuth, rate-limit на `/ai/*` и `/diary/*`, защита `/users`; фронт: утечка ключа уведомлений, гонка Google-callback, таймер паузы, дубли логов подходов, рассинхрон недель, `useId` для SVG. **Требуется от тренера: отозвать старые токены Mongo/Telegram и заполнить `backend/.env.local`.**

---

## 4. Целевая доменная модель (новые коллекции)

Все ID — UUID-строки. `datetime` — ISO-строки при записи. Чтение — `{"_id": 0}`.

### 4.1 `invite_codes`
```jsonc
{
  "id": "uuid",
  "code": "TWB-7K2M9Q",          // уникальный, человекочитаемый
  "kind": "coach_client" | "standalone" | "coach",
  "created_by": 123456789,         // telegram_id создателя (coach/admin)
  "assigned_coach_telegram_id": 123456789, // для coach_client; null для standalone
  "preset": "traincee" | "standalone" | "custom",  // профиль прав по умолчанию
  "permissions": { /* см. §2.3 — выдаются атлету при redeem; админ может изменить позже */ },
  "max_uses": 1,
  "uses": 0,
  "status": "active" | "revoked" | "expired",
  "expires_at": "2026-12-31T00:00:00Z",
  "note": "Для Дмитрия, зал на Ленина",
  "created_at": "...", "updated_at": "..."
}
```

### 4.2 `cardio_sessions`
```jsonc
{
  "id": "uuid",
  "athlete_telegram_id": 123,
  "coach_telegram_id": null,       // если предписано тренером
  "date": "2026-09-29",
  "type": "treadmill" | "bike" | "rower" | "walk" | "elliptical" | "other",
  "duration_sec": 1800,
  "distance_km": 4.2,
  "avg_hr": 142, "max_hr": 168,
  "calories": 320,                 // расчёт или фото
  "intensity": "low" | "moderate" | "high",
  "rpe": 6.5,
  "incline_percent": 6, "avg_speed_kmh": 8.4, "avg_pace": "07:08", // для дорожки
  "notes": "Прошёл 30 мин, пульс держал 140-150",
  "photo_ref": "uuid-or-null",     // ссылка на загруженное фото консоли
  "source": "manual" | "photo",
  "created_at": "...", "updated_at": "..."
}
```

### 4.3 `body_metrics`
```jsonc
{
  "id": "uuid",
  "athlete_telegram_id": 123,
  "date": "2026-09-29",
  "weight_kg": 82.4,
  "body_fat_percent": 18.5,
  "measurements": { "chest": 104, "waist": 86, "hips": 98, "arm": 37, "thigh": 59 },
  "source": "manual" | "coach",
  "created_at": "..."
}
```

### 4.4 `nutrition_entries` (приём пищи)
```jsonc
{
  "id": "uuid",
  "athlete_telegram_id": 123,
  "date": "2026-09-29",
  "meal_type": "breakfast" | "lunch" | "dinner" | "snack",
  "items": [
    {
      "name": "Овсянка с бананом",
      "name_en": "oatmeal with banana",
      "grams": 320,
      "kcal": 410, "protein_g": 14, "fat_g": 8, "carbs_g": 68,
      "source": "food_db" | "ai_estimate" | "manual",
      "match_id": "openfoodfacts:1234567890",
      "confidence": 0.82
    }
  ],
  "totals": { "kcal": 410, "protein_g": 14, "fat_g": 8, "carbs_g": 68 },
  "photo_ref": "uuid-or-null",
  "created_at": "..."
}
```

### 4.5 `nutrition_profiles`
```jsonc
{
  "athlete_telegram_id": 123,      // 1:1 с пользователем
  "sex": "male" | "female",
  "birth_year": 1992,
  "height_cm": 180,
  "activity_level": "sedentary" | "light" | "moderate" | "high" | "athlete",
  "goal": "cut" | "maintain" | "bulk",
  "target_rate_kg_week": -0.5,
  "bmr": 1780, "tdee": 2750,        // пересчитывается при смене метрик
  "macros": { "protein_g": 180, "fat_g": 80, "carbs_g": 300 },
  "dietary": ["vegetarian"],        // опционально
  "updated_at": "..."
}
```

### 4.6 `goals`
```jsonc
{
  "id": "uuid",
  "athlete_telegram_id": 123,
  "created_by": 123 | "self",
  "type": "strength_1rm" | "lift_weight" | "weekly_workouts" | "cardio_minutes" | "body_weight" | "nutrition_kcal" | "macro_daily",
  "ref": { "slug": "bench-press" },   // уточнение (для силы/лифта)
  "target": 100, "unit": "kg" | "min" | "count" | "kcal" | "g",
  "period": "once" | "weekly" | "daily",
  "deadline": "2026-12-31",
  "status": "active" | "done" | "failed" | "archived",
  "created_at": "...", "updated_at": "..."
}
```

### 4.7 Расширения существующих коллекций
- `users`: `access_tier`, `permissions` (+ `permissions_updated_by`, `permissions_updated_at`), `onboarded_at`, `public_slug` (для визитки тренера, §14), `settings.units`.
- `workout_sessions`: `cardio_session_id` (опц. связка в один день), `muscle_map` (замороженный снимок при finish).
- `exercises`: `muscle_weights` (опц. точные веса вклада), `met` (для кардио-конвертаций — не здесь).
- `coach_links`: без изменений (статус `active` обязателен везде).

---

## 5. Общие требования к качеству

- **Тесты:** новый backend-функционал покрывается offline unit-тестами (`backend/tests/unit`) для чистых хелперов (расчёты TDEE, 1ПМ-прогноз, маппинг мышц, агрегация калорий) и интеграционными сценариями (по образцу `backend/tests/integration`).
- **Безопасность:** каждый новый эндпоинт — с `Depends(get_current_user)`; чтение аналитики клиента — только `_assert_coach_of`; логирование за атлета — только активный тренер; self-fill-эндпоинты (силовые/кардио/питание) — только при соответствующем `permissions`; админ-эндпоинты — только `_assert_admin`; онбординг-гейт не даёт пользоваться приложением без redeem инвайта.
- **Производительность:** индексы из §10; никаких `to_list` без лимита/pagination на растущих коллекциях.
- **UX:** состояния загрузки/пусто/ошибка у каждого экрана; скелетоны; toast-ошибки; haptics в Telegram.
- **Локализация:** русский; единицы из `users.settings.units` (kg/lb).
- **Совместимость:** старые записи читаются (поля опциональны, `ConfigDict(extra="ignore")`).

---

## 6. Фазы работ

### Фаза 1 — Роли, доступ по инвайту и админ-панель (фундамент)
**Цель:** закрытый вход (только по инвайту), `standalone`-атлет, гранулярные права на атлета и админ-панель управления кодами/правами.

**Решения владельца (зафиксировано):**
- Регистрация/вход email/Google/Telegram **не даёт доступа** к приложению, пока не применён валидный инвайт-код (экран-гейт `/welcome`).
- Модель прав: **managed athlete «физический подопечный» → силовые только просмотр** (заполняет тренер через co-scribe/coach-led), кардио и питание заполняет сам; **standalone → самостоятельное заполнение всего**.
- Права выдаются **точечно каждому атлету** через админ-панель.

**Backend** (`server.py`, `models.py`, `seed.py`)
- `models.py`: `InviteCode`, `InviteCreateReq`, `InviteRedeemReq`, `PermissionsUpdateReq`; поля `users.access_tier`, `users.permissions`.
- Хелперы: `_default_permissions(access_tier)` (профили `traincee` / `standalone`), `_assert_admin(current)`, `_get_capabilities(user)`.
- `seed.py`: индексы `invite_codes.code` (unique), `invite_codes.created_by`, `invite_codes.status`, `users.access_tier`, `users.roles`.
- Эндпоинты:
  - **Инвайты:** `POST /invites` (coach → `kind=coach_client`, `preset=traincee`, `assigned_coach=self`; admin → любой kind/preset), `GET /invites`, `POST /invites/{id}/revoke`, `POST /invites/redeem`.
  - **Онбординг-гейт:** `GET /auth/me`/`/me/capabilities` отдают `onboarded: bool`; `POST /invites/redeem` создаёт `coach_link` (для coach_client) или ставит `access_tier=standalone`, копирует `permissions` из инвайта, ставит `onboarded_at`.
  - **Админ-панель:** `GET /admin/summary` (счётчики: атлеты по tier, активные связи, использованные/свободные инвайты), `GET /admin/users` (список+права, фильтры), `PATCH /admin/users/{tg}/permissions` (выдать/снять права), `POST /admin/users/{tg}/access-tier`, `POST /admin/invites`, `GET /admin/invites`, `POST /admin/invites/{id}/revoke`, `POST /admin/users/{tg}/role` (coach/admin). Все — guard `_assert_admin`.
  - `GET /me/capabilities` — итоговые права (дефолт по tier + оверрайды).
- Legacy `POST /coach/invite` и `POST /coach/link` переиспользуют новую логику (обратная совместимость).

**Frontend**
- `pages/Onboarding.js` (`/welcome`): обязательный ввод кода; если код не применён — все прочие маршруты редиректят сюда. Текстовое поле, «Применить», понятные ошибки (код не найден/использован/просрочен); после успеха — переход по роли.
- `pages/Admin.js` + `Admin.css` (`/admin`, только `admin`): 
  - вкладка **Инвайты**: создание (kind: клиент тренера / standalone; выбор тренера; пресет прав; срок; заметка), копирование, QR (опц.), отзыв; статус использования.
  - вкладка **Атлеты**: таблица (имя, telegram_id, tier, тренер, onboarded), редактирование **прав чекбоксами** по каждому атлету, смена tier/роли; поиск/фильтры.
  - вкладка **Тренеры**: список, роли, число подопечных.
  - Стиль — в общей тёмной теме, аккуратные карточки/таблицы, статусные бейджи, подтверждения деструктивных действий.
- `pages/Coach.js`: экран «Приглашения» (клиентские коды) — доступно тренеру.
- `Profile.js`: бейдж режима (`Тренер` / `С подопечным тренером` / `Самостоятельно`), переключение режима (`switchMode`), вход в админ-панель для admin.
- Гейтинг: хук `useCapabilities()` из `GET /me/capabilities`; скрывать/дизейблить недоступное (`log_strength`, `manage_plan`, `ai_programs`, …). Для managed athlete `WorkoutView` (силовая) — **read-only**.

**DoD:** без инвайта приложение недоступно (гейт работает на всех маршрутах); coach-инвайт даёт read-only силовые + кардио/питание; standalone-инвайт даёт полный доступ; админ создаёт коды и меняет права любого атлета; `GET /me/capabilities` соответствует матрице; unit-тесты: дефолты прав, redeem (лимит/просрочка/повтор), `_assert_admin`, применение оверрайдов.

---

### Фаза 2 — Карта мышц 2D + аналитика объёма
**Цель:** наглядная карта проделанной работы (светящиеся зоны), для атлета и тренера.

**Таксономия (канон для карты, расширяет текущую):**
`chest, upper_back, lats, traps, front_delts, side_delts, rear_delts, biceps, triceps, forearms, abs, obliques, lower_back, glutes, quads, hamstrings, adductors, abductors, calves, neck`.
Маппинг старых ключей: `legs→quads(1.0)+hamstrings(0.6)+glutes(0.6)`, `back→lats/upper_back`, `shoulders→front/side/rear_delts`, `core→abs/obliques`.

**Backend**
- `seed.py`: словарь `MUSCLE_CANON` и функция `normalize_muscle_weights(primary, secondary) -> {canon_muscle: weight}` (primary=1.0, secondary=0.5).
- `server.py`:
  - `GET /stats/{tg}/muscle-map?period=week|month|custom&start=&end=` → `{ period, start, end, view:{front|back}, regions:{canon:{volume_kg, working_sets, sessions, intensity_0_1}}, totals:{volume, sets}, imbalance:[...] }`.
  - Объём = `weight × reps` по факт. подходам (для bodyweight — коэффициент от 1ПМ или фикс); рабочие подходы — выполненные (`done`).
  - Тренерская версия: `GET /coach/{coach}/clients/{athlete}/muscle-map` (guard `_assert_coach_of`).
  - Нормализация `intensity_0_1` — по перцентилю относительно лучшей зоны/периода; отдельный флаг `imbalance` (зона > 1.75× медианы).
- Кэш: агрегат можно замораживать при `finish` в `workout_sessions.muscle_map` и суммировать по периоду.

**Frontend**
- `components/MuscleMap.js` + `MuscleMap.css`: два SVG-силуэта (спереди/сзади), регионы с `id=canon-muscle`, заливка по шкале (прозрачный → `#FF6B00` → `#FFDA24`), плавные переходы, tooltip (объём/подходы/тренировки), легенда, переключатель спереди/сзади, селектор периода.
- SVG-ассет: анатомически корректный, открытая лицензия (public domain / CC0). Хранить в `frontend/src/assets/`. Если готового нет — упрощённая схема приемлема.
- Интеграция: `pages/Stats.js` — вкладка «Мышцы»; `pages/CoachClientStatsPage` — для тренера.
- Для managed athlete — read-only (без редактирования).

**DoD:** данные берутся из реальных сессий; карта корректна для пустого периода (все зоны нейтральны); tooltip и переключатели работают; unit-тесты нормализации/агрегации.

---

### Фаза 3 — Кардио-модуль
**Цель:** учёт кардио (дорожка) вручную и по фото консоли; тренер назначает, атлет выполняет.

**Backend**
- `models.py`: `CardioSession`, `CardioCreateReq`; `coach`-предписания — переиспользовать `goals` (`type=cardio_minutes`, `period=weekly`).
- `server.py`:
  - `POST /cardio` — создать (owner или тренер за клиента); владельцам нужен `permissions.log_cardio` (managed-атлеты заполняют кардио сами).
  - `GET /cardio?athlete=&from=&to=` — список (владелец/тренер).
  - `PATCH /cardio/{id}` / `DELETE /cardio/{id}`.
  - `POST /cardio/parse-photo` — фото консоли → vision → черновик `{type, duration_sec, distance_km, avg_hr, calories, incline, speed}`; пользователь подтверждает.
  - `GET /stats/{tg}/cardio?period=` → `{minutes, sessions, km, kcal, by_type, weekly_target, compliance}`.
  - Калькуляция калорий (если нет с фото): MET-формула `kcal = MET × 3.5 × kg / 200 × min`.
- Проверки: `duration_sec>0`, `distance_km>=0`, `avg_hr 30..230`, `rpe 1..10`; даты ISO.

**Frontend**
- `pages/Cardio.js` + CSS: список сессий, быстрый ввод (тип/время/дистанция/пульс), кнопка «Фото консоли».
- Компонент `CardioForm`, мини-графики (recharts): минуты/неделя, дистанция, средний пульс.
- Карточка на `Home` и в `DiaryHome` — «Кардио сегодня».
- Тренер: в `CoachClient.js` — недельная норма кардио и выполнение; уведомление при недоборе.

**DoD:** ручной ввод и фото-парсинг работают; цели по кардио видны атлету и тренеру; агрегаты корректны; тесты калькулятора калорий и валидации.

---

### Фаза 4 — Единый дневник, цели и прогноз нагрузки
**Цель:** одна лента (силовая + кардио + питание), цели и графики с прогнозом роста нагрузки.

**Backend**
- `models.py`: `Goal`, `GoalCreateReq`, `BodyMetric`, `BodyMetricReq`.
- `server.py`:
  - `GET /diary/timeline?athlete=&from=&to=` — объединённая лента (силовые `workout_sessions`, кардио `cardio_sessions`, питание `nutrition_entries`).
  - `POST/GET/PATCH/DELETE /goals`; `GET /goals/progress` — % выполнения по активным целям.
  - `POST/GET /body-metrics` — вес/замеры (для графика веса и пересчёта TDEE).
  - `GET /stats/{tg}/forecast?slug=bench-press&weeks=12` → `{ series:[{date,e1rm}], fit:{slope_kg_week, intercept, r2, n}, projection:[{date,e1rm,low,high}], confidence, ai_comment" }`.
    - `e1RM` по Эпли: `w × (1 + reps/30)` (лучший подход сессии).
    - Прогноз: линейная регрессия; `low/high` = ±1.96·SE; `confidence` = f(r², n, свежесть).
  - `POST /stats/{tg}/forecast/explain` (фоновая `ai_job`) — ИИ-комментарий на русском: тренд, риски, рекомендации по прогрессии/делоуду. Кэшировать по (slug, последняя сессия).
- Делоуд-детектор (эвристика): 3+ недели плато/регресса e1RM → флаг и рекомендация.

**Frontend**
- `pages/DiaryHome.js`/`Diary.js`: переключение лент (Всё / Силовые / Кардио / Питание), карточки с иконками типов, фильтр по дате.
- `pages/Goals.js`: список целей, прогресс-бары, дедлайны; создание/редактирование: standalone — сам, managed — только тренер (атлет видит read-only). Требует `permissions.view_goals`.
- `components/ForecastChart.js`: линия истории + пунктир прогноза + доверительный коридор (recharts `Area`+`Line`), переключатель лифта и горизонта.
- Блок «Прогноз» на `Stats.js` и на карточке клиента у тренера; кнопка «Объяснить» → ИИ-текст.

**DoD:** лента собирается из трёх источников без дублей; прогноз строится на реальной истории; при малых данных показывается понятное пустое состояние; ИИ-комментарий асинхронный и кэшируется; unit-тесты регрессии/Эпли/уверенности.

---

### Фаза 5 — Питание и калории по фото
**Цель:** считать калории и БЖУ, в т.ч. по фото еды; TDEE и макро-цели.

**Пайплайн фото (vision + база питания):**
1. `POST /nutrition/parse-photo` — фото → `_ai_chat_vision` с промптом «верни только JSON: список блюд, оценка порции в граммах, уверенность».
2. Для каждого блюда: поиск в **Open Food Facts** (бесплатный API, без ключа; `User-Agent` обязателен) или в локальном справочнике; извлекаем kcal/БЖУ на 100 г → пересчёт на граммы.
3. Нет совпадения → fallback: ИИ-оценка на порцию (`source=ai_estimate`, ниже `confidence`).
4. Ответ-черновик → пользователь правит граммы/блюда → `POST /nutrition` сохраняет `nutrition_entries`.
5. Кэш поисков OFF (коллекция или in-memory TTL), нормализация названий (ru→en через ИИ один раз).

**Backend**
- `models.py`: `NutritionEntry`, `NutritionItem`, `NutritionProfile`, `NutritionPhotoReq`.
- `server.py`:
  - `GET/PUT /nutrition/profile` — анкета (sex, height, birth_year, activity, goal, rate).
  - Расчёт `bmr` (Mifflin-St Jeor), `tdee = bmr × activity_factor`, макросы (protein 1.6–2.2 г/кг, fat 0.8–1.0 г/кг, остаток — углеводы).
  - `POST /nutrition/parse-photo` (vision, rate-limit), `POST /nutrition` (сохранить), `GET /nutrition?date=`, `PATCH/DELETE /nutrition/{id}`.
  - `GET /stats/{tg}/nutrition?period=` — сумма/средние ккал и БЖУ, adherence к цели, серия дней ведения.
  - Тренерская версия: `GET /coach/{coach}/clients/{athlete}/nutrition` (+ возможность задать цель в `goals`).
  - Фото хранить как в существующем пайплайне фото (посмотреть `_ai_chat_vision`-эндпоинты/AI-импорт; переиспользовать хранение).

**Frontend**
- `pages/Nutrition.js` + CSS: дневник питания по датам, круговые прогресс-бары ккал/БЖУ, список приёмов пищи, кнопка «Сфотографировать еду», экран подтверждения распознанного (правка граммов, удаление позиций), ручное добавление.
- `pages/NutritionProfile.js`: анкета + расчёт нормы (красивый вывод TDEE и макросов).
- Виджет «Калории сегодня» на `Home`; цели по калориям в `Goals.js`.
- Тренер: видит **детальный** дневник питания и вес по каждому клиенту (решение владельца, §13 O3) и может задать цель/макросы через `goals`.

**DoD:** фото → черновик → правка → сохранение работает end-to-end; расчёт TDEE/БЖУ вынесен в чистую функцию и покрыт тестами; OFF-поиск с таймаутом и graceful fallback на ИИ; rate-limit; при недоступности ИИ — понятная ошибка.

---

### Фаза 6 — Панель тренера 2.0 и уведомления
**Цель:** тренер видит сводку по всем подопечным и проактивно реагирует.

**Backend**
- `GET /coach/{coach}/dashboard` — сводка: adherence, кардио-норма, баланс мышц, вес/тренд, флаги внимания (пропуски, плато, перекос), последние активности.
- `GET /coach/{coach}/overview` — live-статусы (уже есть `/clients/live-status`, добавить `status`-фильтр `active` — исправить существующую недоработку с отозванными связями).
- Уведомления: напоминание о кардио, вечернее напоминание заполнить питание/дневник, еженедельный отчёт тренеру, алерт о плато/перекосе. Расширить `notifications.py` + `scheduler.py`.

**Frontend**
- `pages/CoachReports.js`: таблица клиентов со статус-индикаторами, фильтры «требуют внимания», мини-спарклайны.
- Дашборд-виджеты в `Coach.js`: counts (активные, на тренировке, пропустили), недельный объём, агрегированная карта мышц команды (nice-to-have).
- `NotificationSettings.js`: новые тумблеры (кардио, питание, отчёт).

**DoD:** дашборд грузится < 1.5 c на 20 клиентах (индексы, агрегаты); флаги внимания осмысленны; уведомления не спамят (дедуп по `notification_log`); отозванные связи не протекают.

---

### Фаза 7 — Полировка, тесты, безопасность
**Цель:** довести до «идеала»: стабильность, скорость, доступность.

- Полный e2e-прогон ролей: coach ↔ managed ↔ standalone; проверить IDOR на всех новых роутах.
- Пагинация и лимиты на все растущие выборки; индексы из §10.
- Таймзоны: перейти на локальную дату пользователя (поле `users.timezone` или offset в запросах) — исправить известную UTC-проблему.
- Очистка: удалить мёртвые `viewer`-параметры, унифицировать расчёт «плановых подходов».
- Доступность: клавиатурная навигация, контраст, размеры тапов ≥ 44px.
- PWA/Telegram: офлайн-индикатор, haptics, safe-area.

---

## 7. Сводка новых API-эндпоинтов

| Метод | Endpoint | Фаза |
|-------|----------|------|
| POST | `/invites` | 1 |
| GET | `/invites` | 1 |
| POST | `/invites/{id}/revoke` | 1 |
| POST | `/invites/redeem` | 1 |
| GET | `/me/capabilities` | 1 |
| GET | `/admin/summary` | 1 |
| GET | `/admin/users` | 1 |
| PATCH | `/admin/users/{tg}/permissions` | 1 |
| POST | `/admin/users/{tg}/access-tier` | 1 |
| POST | `/admin/users/{tg}/role` | 1 |
| GET | `/admin/invites` | 1 |
| POST | `/admin/invites/{id}/revoke` | 1 |
| GET | `/stats/{tg}/muscle-map` | 2 |
| GET | `/coach/{coach}/clients/{athlete}/muscle-map` | 2 |
| POST | `/cardio` | 3 |
| GET | `/cardio` | 3 |
| PATCH/DELETE | `/cardio/{id}` | 3 |
| POST | `/cardio/parse-photo` | 3 |
| GET | `/stats/{tg}/cardio` | 3 |
| GET | `/diary/timeline` | 4 |
| POST/GET/PATCH/DELETE | `/goals` | 4 |
| GET | `/goals/progress` | 4 |
| POST/GET | `/body-metrics` | 4 |
| GET | `/stats/{tg}/forecast` | 4 |
| POST | `/stats/{tg}/forecast/explain` | 4 |
| GET/PUT | `/nutrition/profile` | 5 |
| POST | `/nutrition/parse-photo` | 5 |
| POST/GET/PATCH/DELETE | `/nutrition` | 5 |
| GET | `/stats/{tg}/nutrition` | 5 |
| GET | `/coach/{coach}/clients/{athlete}/nutrition` | 5 |
| GET | `/coach/{coach}/dashboard` | 6 |

**Правило:** каждый тренерский роут — guard `_assert_coach_of(coach, athlete)`; каждый персональный — владелец по `current_user`; админ-роуты — `_assert_admin`; self-fill-роуты — проверка `permissions`; фото-парсеры — `_rate_limit` на пользователя.

---

## 8. Frontend: маршруты и компоненты

**Новые маршруты:**
```
/welcome                 → Onboarding-гейт (обязательный ввод инвайт-кода; без него нет доступа)
/admin                   → Админ-панель (инвайты, атлеты, права, роли; только admin)
/cardio                  → Cardio (список + форма + фото)
/nutrition               → Nutrition (дневник питания + фото)
/nutrition/profile       → анкета TDEE/БЖУ
/goals                   → Goals (цели и прогресс)
/coach/reports           → дашборд тренера
```
**Изменяемые:** `Stats.js` (+ «Мышцы» и «Прогноз»), `DiaryHome.js` (+ лента/кардио/питание), `Profile.js` (+ режим/инвайты/админ), `Coach.js` (+ приглашения/сводка), `CoachClient.js` (+ нормы кардио/питания, карта мышц), `Home` (виджеты).

**Новые компоненты:** `MuscleMap`, `ForecastChart`, `CardioForm`, `NutritionRing`, `FoodConfirmSheet`, `GoalCard`, `InviteManager`, `PermissionsMatrix`, `useCapabilities`.

**Дизайн-требования (красиво):**
- Единая тёмная тема; акцент `#FF6B00`, вторичный градиент `#FF8A24→#FFDA24`.
- Карта мышц: мягкое свечение зон, плавная интерполяция цвета, tooltip-карточки.
- Графики: тонкие линии, градиентные заливки, корректные оси, тултипы; уникальные SVG-id через `React.useId()`.
- Микроанимации (появление карточек, прогресс-ринги) через `styles/animations.css`; не перегружать.
- Все состояния: loading (скелетон), empty (иллюстрация + CTA), error (понятный текст + retry).
- Mobile-first, колонка max-width 720px на десктопе, safe-area для PWA/Telegram.

---

## 9. ИИ-пайплайны и промпты

**Общие правила:**
- Текст — `_ai_chat` (DeepSeek, `json_mode=True` для структуры), vision — `_ai_chat_vision` (Gemini).
- Долгие задачи — фоном через `ai_jobs`, фронт поллит `/ai/program/jobs/{id}`.
- Всегда валидировать JSON (использовать `json_repair`), при ошибке — повтор/понятная ошибка.
- Промпты возвращают строгую схему; ИИ-оценки помечать `confidence`.

**9.1 Распознавание еды (vision):** вернуть `{items:[{name_ru, name_en, portion_grams, unit, confidence}]}`; запрещено выдумывать бренды; при неоднозначности — одна наиболее вероятная позиция + confidence.

**9.2 Парсинг фото кардио:** вернуть `{type, duration_sec, distance_km, avg_hr, max_hr, calories, incline_percent, avg_speed_kmh}`; неизвестные поля — `null`.

**9.3 Прогноз (текст):** вход — `{slug, slope_kg_week, r2, n, last_bests:[{date,e1rm}], adherence, recent_rpe}`; выход — короткий (3–5 предложений) разбор на русском: тренд, риск плато/перетренированности, конкретная рекомендация (прогрессия/делоуд/техника). Тон — поддерживающий, без медицинских обещаний.

**9.4 Дневник (уже есть):** не трогать контракт; расширить контекстом кардио/питания при генерации недельного разбора.

---

## 10. Индексы MongoDB (добавить в `seed.ensure_indexes`)

```python
invite_codes.code (unique, sparse)
invite_codes.created_by
invite_codes.status
cardio_sessions: (athlete_telegram_id, date), date, type
body_metrics: (athlete_telegram_id, date)
nutrition_entries: (athlete_telegram_id, date), date
nutrition_profiles.athlete_telegram_id (unique)
goals: (athlete_telegram_id, status), (created_by)
users.access_tier
users.roles
users.onboarded_at
invite_codes.assigned_coach_telegram_id
workout_sessions: (athlete_telegram_id, date)   # для дневника/прогноза
workout_sessions.finished_at                    # уже есть
```

---

## 11. Тестирование и критерии приёмки

**Backend unit (offline, `pytest -q` из `backend/`):** TDEE/макросы (Mifflin-St Jeor, границы пола/активности), Эпли/e1RM, линейная регрессия + доверительный интервал, `normalize_muscle_weights`, MET-калькулятор кардио, нормализация порций, использование/просрочка/лимит инвайта, `_default_permissions` (профили `traincee`/`standalone`), слияние оверрайдов прав, `access_tier`-резолвер.

**Backend integration (по образцу `backend/tests/integration`):** онбординг-гейт (доступ к приложению без redeem → 403/redirect-флаг), доступ ролей (coach/managed/standalone) ко всем новым роутам (401/403/200), IDOR-проверки, админ-роуты недоступны не-админам (403), `permissions.log_strength=false` блокирует self-fill силовой, фото-парсеры при отсутствии ключа ИИ → 503, агрегаты muscle-map/cardio/nutrition на фикстурах.

**Frontend:** `yarn build` без ошибок; ручной сценарий: вход без кода → гейт `/welcome` → redeem coach-кода → просмотр силовой (read-only) + заполнение кардио/питания → standalone-код → self-fill + план + ИИ → админ создаёт код и меняет права атлета. Проверка read-only у managed athlete и скрытия недоступного через `useCapabilities`.

**Общий DoD фазы:** код собирается, тесты зелёные, нет `console.log`, нет хардкода секретов/URL, новые эндпоинты защищены, обновлены `AI_CONTEXT.md` (при необходимости) и `test_result.md`.

---

## 12. Рабочий процесс ИИ-агентов

1. Прочитать `AI_CONTEXT.md` → `planTrainWBrain.md`.
2. Взять одну фазу; разбить на задачи (backend → frontend → тесты).
3. Backend первым: модели → хелперы (чистые) → эндпоинты → индексы → unit-тесты.
4. Frontend вторым: api.js-обёртки → компонент(ы) → стили → маршрут → состояния.
5. Прогнать: `python -m pytest -q` (backend), `yarn build` (frontend), при необходимости интеграционные скрипты.
6. Обновить документацию и `test_result.md`.
7. Не коммитить без явной просьбы.
8. Один агент — одна фаза/подсистема; не редактировать один файл параллельно двумя агентами (особенно `server.py`).

---

## 13. Риски и открытые вопросы

**Решено владельцем:**
- **O1 → закрыто:** вход **только по инвайту**; email/Google/Telegram-аккаунт без redeem кода доступа к приложению не получает.
- **O2 → закрыто:** managed athlete («физический подопечный») — **только просмотр силовых** (заполняет тренер); standalone — самостоятельное заполнение всего.
- **O3 → закрыто:** тренер видит **все** данные подопечных, включая детальный дневник питания и вес.
- **O-админ → закрыто:** админ-панель создаёт инвайты и выдаёт права каждому спортсмену точечно.

**Остаётся проработать:**
- **O4:** Хранение фото (еда/консоль): сейчас — как в существующем пайплайне; на проде нужен объектный сторедж (S3-совместимый) и ретеншн.
- **O5:** Open Food Facts — точность по русскоязычным блюдам ограничена; нужен слой нормализации/локальный справочник популярных блюд.
- **O6:** Таймзоны (UTC-баг) — определить способ хранения локальной даты.
- **O7:** Монетизация standalone — тарифы/лимиты (сколько ИИ-разборов, сколько фото) — вне текущего плана, задел на будущее.
- **O8:** Масштабирование WebSocket/`ai_jobs` при нескольких инстансах — Redis Pub/Sub (будущее).
- **O9:** Кому ещё доступна админ-панель (только владелец или доверенные тренеры) — определить список админов и процесс назначения.

---

## 14. Бэклог идей (сверх запрошенного)

1. **Автопрогрессия:** после успешных недель — предложение +2.5 кг / +1 повтор (на основе прогноза и RPE).
2. **Делоуд-планировщик:** раз в 4–6 недель автоматический разгрузочный день/неделя с уведомлением.
3. **Check-in:** фото прогресса тела + замеры, приватные альбомы, графики.
4. **Предписания тренера:** кардио-зоны (пульс), недельные минуты, шаги; авто-контроль выполнения.
5. **Геймификация:** серии (streak уже есть), достижения, рейтинг клиентов у тренера.
6. **Визитка тренера:** публичная страница `/coach/{slug}` с кейсами и записью на тренировку (lead-магнит).
7. **Шаблоны питания:** тренер назначает рацион/макросы; библиотека блюд; быстрый ввод «вчера то же».
8. **Синхронизация носимых:** Apple Health / Google Fit / Garmin / Strava (пульс, шаги, кардио) — отдельная большая фаза.
9. **Видео-техника:** разбор техники ИИ по короткому видео (сложно, отложить).
10. **Штампы техники/травм:** учёт ограничений (уже есть `injuries` в `diary_profile`) и авто-замена упражнений.
11. **Экспорт:** PDF/Excel недельного отчёта для клиента.
12. **Мультиязычность:** RU/EN (сейчас RU).
13. **Роль assistant-тренера** для крупных залов (несколько тренеров на клиента).
14. **Интеграция оплат:** Telegram Stars / Stripe для standalone-доступа.

---

## 15. Быстрый старт (рекомендуемый порядок)

1. **Фаза 1** (инвайт-only вход, роли, права, админ-панель) — фундамент, без него остальное недоступно.
2. **Фаза 2** (карта мышц) — самый сильный визуальный «вау» для тренера и атлета.
3. **Фаза 3** (кардио) — быстро закрывает запрос про дорожку.
4. **Фаза 4** (дневник/цели/прогноз) — ядро ценности.
5. **Фаза 5** (питание/фото) — самый сложный ИИ-модуль.
6. **Фаза 6** (дашборд тренера) — масштабирует продукт.
7. **Фаза 7** (полировка) — доводим до идеала.

---
**Статус:** 🚧 в исполнении. Все ключевые решения (O1–O3, админ-панель) зафиксированы.

**Прогресс по фазам:**
- ✅ **Фаза 1** — роли, инвайты, админ-панель (`PHASE1_COMPLETION_SUMMARY.md`)
- ✅ **Фаза 2** — карта мышц 2D + аналитика объёма
- ✅ **Фаза 3** — кардио-модуль (`PHASE3_COMPLETION_SUMMARY.md`)
- ⏳ **Фаза 4** — единый дневник, цели и прогноз нагрузки ← **следующая**
- ⬜ **Фаза 5** — питание и фото
- ⬜ **Фаза 6** — панель тренера 2.0 и уведомления
- ⬜ **Фаза 7** — полировка, тесты, безопасность

**Отложено по запросу владельца:** дневник (`DiaryHome`, режим `diary`) временно скрыт в UI —
код и API сохранены для последующего возврата.

