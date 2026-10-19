# twb_plan.md — TrainWithBrain: Концепция и архитектура (ТЗ)

> **Версия документа:** 3.2
> **Дата:** Июнь 2026 (v3.2 — синхронизация статусов с кодом: P4 real-time co-scribe ✅, обязательная аутентификация 3 методов ✅, закрытие IDOR на `/sessions/*` и `/plans/*` ✅, по-подходное логирование + таймер отдыха + настройки ✅, подтверждение тренером и **старт тренировки тренером** ✅) · v3.1 — режим тренера P3 и редактор плана подопечного P3.1; запланированная «подробная статистика подопечного с графиками» P7
> **Тип:** Техническое задание + архитектурный план разработки
> **Связанные документы:** [`AI_CONTEXT.md`](./AI_CONTEXT.md) · [`PROJECT_DETAILS.md`](./PROJECT_DETAILS.md) · [`README.md`](./README.md) · [`test_result.md`](./test_result.md)
> **Базовый стек (источник истины — `package.json` / `requirements.txt`):** React 19 (CRACO) + FastAPI + MongoDB (Motor), Telegram Mini App.

---

## 0. TL;DR (за 60 секунд)

**TrainWithBrain (TWB)** — это Telegram Mini App для силовых тренировок с **двумя ролями в одном приложении**:

- **Спортсмен (athlete)** — выбирает / создаёт / импортирует тренировочную программу, запускает тренировку кнопкой «Начать», по ходу отмечает выполненные упражнения, видит прогресс и статистику.
- **Тренер (coach)** — ведёт своих подопечных, **в реальном времени** видит ход тренировки, заполняет/правит план, подтверждает выполненное и **еженедельно подтверждает продление доступа** к плану (с опциональной оплатой).

Четыре ключевые функции из ТЗ:

| # | Функция | Решение |
|---|---------|---------|
| 1 | Своя/импортированная/готовая программа + трекинг прогресса | Конструктор программ + импорт (JSON/CSV/Excel) + библиотека шаблонов; прогресс по реальным данным сессий |
| 2 | Запуск тренировки «Начать» + отметка упражнений → статистика | `WorkoutSession` lifecycle + `SetLog` + агрегаты (тоннаж, completion, streak) |
| 3 | Доступ: тренер подтверждает каждую неделю | `WeekAccess` (gating по неделям) + подтверждение тренера + опциональная оплата (Telegram Payments / Stars) |
| 4 | Синхронизация в реальном времени с тренером | **WebSocket** (`/api/ws`) + ConnectionManager + событийная модель |

> **Доработка v3.0 (что добавлено к ТЗ):** уточнён и расширен режим тренера и сопутствующие механики. Кратко (детали — §0.2 и соответствующие разделы):
> - **Подготовка плана заранее + видимость:** тренер собирает план подопечного впереди и сам решает — показывать его спортсмену или держать черновиком (`Plan.visibility` + показ недель по одной).
> - **Тренер выставляет тренировочные дни** (видимые спортсмену) — управление `training_days` на уровне плана.
> - **Real-time синхронизация в обе стороны:** тренер видит ход тренировки вживую и **сам заполняет/подтверждает** выполненное (co-scribe + подтверждение).
> - **Доступ по неделям:** тренер еженедельно подтверждает продление плана (gating + опц. оплата).
> - **Импорт программы по коду/ссылке** (share-code + deep link), помимо файлов.
> - **Система пропусков тренировок** (skip/missed/reschedule, влияние на streak).
> - **Статистика отклонений от плана** (adherence: план vs факт по объёму/весу/расписанию).
>
> ❗ **Кроссплатформенность — с самого начала.** Приложение обязано корректно работать на всех платформах Telegram (iOS, Android, Telegram Desktop, Web/macOS) и адаптивно — на телефоне/планшете/десктопе. См. §12.1.

**Принципы (наследуем из проекта):** все роуты с префиксом `/api`; ID — только UUID; `datetime` → ISO-строка в Mongo; `find(..., {"_id": 0})`; пакеты фронта — только `yarn`; URL/порты — только из `.env`.

---

## 0.1 Статус реализации (актуально)

| Фаза | Статус | Примечание |
|------|--------|-----------|
| **P0** Фундамент | ✅ Готово | модульная структура, индексы, dev-fallback пользователя |
| **P1** Программы и план | ✅ Готово | `exercises`/`programs`/`plans`, seed-библиотека, экран «Программы», реальные данные дня/недели (mock убран) |
| **P2** Тренировка и статистика | ✅ Готово | `WorkoutSession` lifecycle, тоннаж/%1ПМ/прогресс/streak; экран дня `WorkoutView` |
| **P3** Режим тренера | ✅ Готово | роли/режим (`active_mode`, `roles[]`), invite-код + deep link (`/coach/invite`), привязка подопечных (`/coach/link`,`/unlink`), список подопечных (`/coach/{id}/clients`), просмотр плана подопечного, видимость плана `draft/published`, публикация недель по одной, тренировочные дни, **подтверждение тренировки/упражнений тренером**, **старт тренировки тренером** (`sessions/start` с `coach_telegram_id`), LIVE-экран подопечного. Профиль: переключатель режима + секция «Подопечные» (аватарки) |
| **P3.1** Редактор плана подопечного | ✅ Готово | тренер правит снимок плана: недели/дни/упражнения (подходы·вес·повторы·RPE·заметки, добавить/удалить). Эндпоинты `PATCH /plans/{id}`, `PUT/DELETE /plans/{id}/day`, `PUT/DELETE /plans/{id}/exercise`, `POST/DELETE /plans/{id}/week`; экран `/coach/:id/edit` |
| **P4** Real-time (WebSocket) | ✅ Готово | `WS /api/ws` (валидация session-токена, комнаты `plan:{id}`/`user:{tg}`), `ConnectionManager` (in-memory, `backend/realtime.py`), co-scribe (`filled_by`/`coach_confirmed`, `actor`/`by`), broadcast-события (§6.4), фронт-хук `useRealtime`. БД — источник истины, WS транслирует; на реконнекте REST-«догон». Протестировано (backend_test_p4.py, всё зелёное) |
| **Auth** Обязательная аутентификация | ✅ Готово | 3 метода: email/пароль (bcrypt), Telegram initData (HMAC), Google (прямой OAuth + Emergent managed). Единая модель сессий `user_sessions`, Bearer-токен (`twb_token`). Гостевого режима нет. **IDOR закрыт** на всех `/sessions/*` и `/plans/*` (хелперы `_assert_coach_of`/`_assert_can_edit_plan`/`_assert_session_read`/`_assert_session_actor` → 401/403). Протестировано |
| **P2 (доп.)** По-подходное логирование | ✅ Готово | `SetLog` + `PATCH /sessions/{id}/exercise/{order}/set/{index}`: чек-лист подходов (done/skipped) с редактируемым факт. весом/повторами, оверлей-таймер отдыха (по `rest_seconds`), модалка «Настройки тренировки» (`WorkoutView.js`) |
| **P5** Доступ по неделям + оплата | ⏳ Не начато | |
| **P6** Импорт/экспорт + полировка | 🟡 Частично | Excel-программа импортирована как **встроенный шаблон** (без UI-загрузки файла); конструктор/экспорт/загрузка файла — впереди |
| **P7** Подробная статистика подопечного (графики) | 🟢 Бэкенд готов | Сбор статистики с КАЖДОЙ тренировки: снимок `stats` замораживается при finish (тоннаж/объём план↔факт, distribution по группам, lifts с оценкой 1ПМ). Эндпоинты: `GET /stats/{tg}/detailed`, `/stats/{tg}/exercise-progress`, `GET /sessions/{id}/deviation`, coach-gated `/coach/{c}/clients/{a}/stats` и `/exercise-progress`. 1ПМ — «по плану/как в таблице» (вес÷план%): `one_rep_max_est.planned` из `plan.maxes`. Протестировано (deep_testing_backend_v2, всё зелёное). Осталось: экран графиков на recharts (`/stats`, `/coach/:id/stats`) — §11.5 |
| **P2.1** Пропуски + отклонения | 🟢 Бэкенд готов | Коллекция `plan_day_marks` + эндпоинты skip/reschedule/mark/unmark, `GET /plans/{id}/missed` (авто-детект missed по фронтиру достигнутых дней), adherence по расписанию, тренировочный streak с учётом `streak_mode` (strict/lenient), `PATCH /users/{tg}/settings`. Протестировано. Осталось: UI пропусков/отклонений в селекторе и статистике |

> 🆕 **Доработка v3.0** добавляет к фазам P3–P6 новый объём (видимость плана, тренерское заполнение в real-time, тренировочные дни, импорт по коду/ссылке) и две сквозные темы — **кроссплатформенность** (с самого начала) и **пропуски + статистика отклонений**. Карта новых требований — §0.2.

### Что добавлено сверх исходного плана (реализовано и протестировано)

1. **Режим «Изменить упражнение» (✨)** — модалка правки в сессии:
   - добавление/удаление подходов (`sets_scheme` переменной длины, пересчёт %1ПМ и тоннажа, округление весов до 2.5 кг);
   - поле **«Заметки»** (комментарий спортсмена, поле `comment` на `SessionExercise`, помечено «виден тренеру» — задел под P3);
   - флажок **«изменено»** (карандаш) на упражнении, если правились название/подходы (поле `edited`);
   - **дифф подходов в карточке**: у добавленных/изменённых подходов — иконка‑карандаш, удалённые из плана — зачёркнуты и тусклые, в порядке плана (сравнение текущей схемы сессии с планом через `planSetsByOrder`).
2. **Импортированная программа «3 мес Подготовка на осень»** (`slug: pl-autumn-3m`) — 12 недель × 3 дня × 4 основных + подсобка:
   - seed из `backend/seed_data/pl_autumn_3m.json` (идемпотентно, `uuid5`);
   - **масштабирование под спортсмена**: шаблон `requires_maxes=true`, `base_maxes={squat:200,bench:131,deadlift:230}`; каждое упражнение тегируется `lift_group` (squat/bench/deadlift); при создании плана веса = `вес_автора × (макс_спортсмена / макс_автора)`, округление 2.5 кг, %1ПМ сохраняется (масштабируется и `one_rep_max`);
   - **выбор дней тренировок** при назначении (`training_days` → ремаппинг тренировочных дней на выбранные дни недели);
   - **подсобные упражнения** (`is_accessory=true`, без веса/подходов) — в раскрываемой «папке» **«Подсобные упражнения»**; своя рекомендация «4 подхода», свои кнопки выполнить/изменить/отменить.
   - UI выбора: **модалка настройки** в `/programs` (3 максимума + дни) для шаблонов с `requires_maxes`.
3. **График «Прогноз по плану»** — реальная динамика топового веса упражнения по неделям плана: пройденное — сплошной линией, предстоящее — пунктиром, текущая неделя отмечена точкой (расчёт на фронте из `plan.weeks`).
4. **Правила старта тренировки**:
   - запрет нескольких одновременных тренировок (старт при наличии активной сессии → **HTTP 409**);
   - подтверждение старта, если выбранный день ≠ сегодня.

### Новые/расширенные поля и эндпоинты (сверх §4–§5)
- `ProgramTemplate`: `requires_maxes: bool`, `base_maxes: dict`.
- `ProgramExercise`: `lift_group`, `is_accessory`, `sets_scheme`.
- `Plan` / `PlanCreate`: `maxes`, `training_days`, `one_rep_max`.
- `SessionExercise`: `comment`, `edited`, `lift_group`, `is_accessory`, `plan_sets_scheme`.
- `POST /api/plans` — принимает `maxes` + `training_days`, масштабирует снимок и ремаппит дни.
- `PATCH /api/sessions/{id}/exercise/{order}/edit` — `exercise_name` / `sets_scheme` / `comment`.
- `POST /api/sessions/start` — 409 при наличии активной (`in_progress`) сессии.
- Зависимости: добавлен `openpyxl` (парсинг Excel при генерации seed).

---

## 0.2 Доработка v3.0 — карта новых требований

> Источник: уточнённое ТЗ заказчика (июль 2025). Каждое требование привязано к решению и разделу/фазе. Базовые принципы проекта (UUID, `/api`, ISO-даты, `{"_id":0}`, `yarn`, `.env`) сохраняются без изменений.

| # | Требование (из ТЗ) | Решение | Где описано | Фаза |
|---|--------------------|---------|-------------|------|
| 1 | **Тренер:** доступ к программе — еженедельное подтверждение продолжения плана | `week_access` gating + подтверждение недели тренером (+ опц. оплата) | §4.7, §5.7, §7, §6.4 | P5 |
| 2 | **Тренер:** синхронизация — видит полный план в реальном времени и **сам заполняет/подтверждает** выполненное | WebSocket `plan:{id}` + двунаправленные события + `filled_by`/`coach_confirmed` | §6, §5.6, §5.8, §4.11 | P3–P4 |
| 3 | **Тренер:** готовит план заранее + на выбор показывать/нет | `Plan.visibility` (`draft`/`published`) + показ недель по одной (`ProgramWeek.published`) | §4.11, §5.8, §3.4 | P3 |
| 4 | **Тренер:** выставляет тренировочные дни (видимые) | управление `Plan.training_days` тренером, видно спортсмену в недельном селекторе | §4.11, §5.8 | P3 |
| 5 | **Кроссплатформенность сразу** | platform-aware Telegram WebApp (iOS/Android/Desktop/Web), адаптив, safe-area, темы, haptics с fallback, тест-матрица | §12.1 | сквозная (с P0) |
| 6 | **Импорт программы по коду/ссылке** | share-code + deep link `startapp=prog_<code>`, импорт-эндпоинты | §8.5, §5.8, §4.11 | P6 |
| 7 | **Система пропусков тренировок** | `skipped`/`missed`/`rescheduled` (коллекция `plan_day_marks`), влияние на streak (strict/lenient), перенос | §9.1, §4.11, §5.8, §6.4 | P2.1/P3 |
| 8 | **Статистика при отклонении от плана** | adherence-метрики (план vs факт по объёму/весу/расписанию), отчёт по сессии и плану | §9.2, §5.8 | P2.1 |
| 9 | **Тренер: подробная статистика подопечного с графиками** 🆕 | экран аналитики подопечного у тренера на recharts: тоннаж по неделям, прогресс топ-весов по упражнениям, частота/completion/streak, adherence (план vs факт), распределение по группам мышц; coach-gated эндпоинты | §9.3, §5.9 | P7 |

> Также реализовано сверх ТЗ: **редактор плана подопечного** (тренер правит недели/дни/упражнения снимка плана) — §11.4, фаза P3.1.

> Рекомендованный приоритет реализации: **(5) кроссплатформенность — заложить сразу**, далее (3,4) видимость/дни и (2) real-time тренера → (1) доступ по неделям → (7,8) пропуски и отклонения → (6) импорт по коду → **(9) подробная статистика подопечного с графиками**.

---

## 1. Видение продукта и проблема

### 1.1 Проблема
Силовые спортсмены (пауэрлифтинг, бодибилдинг) и их тренеры сегодня ведут планы в разрозненных инструментах: Google Sheets, заметки, мессенджеры. Минусы:
- тренер не видит выполнение **вживую** — обратная связь запаздывает;
- спортсмену неудобно отмечать подходы в таблице во время тренировки;
- нет единого учёта прогресса, тоннажа, серии (streak);
- нет управляемого доступа: тренер не может «по неделям» контролировать выдачу плана и оплату.

### 1.2 Решение
Единое Telegram-приложение, где **спортсмен тренируется**, а **тренер управляет и наблюдает в реальном времени**. Telegram выбран как платформа: нулевой порог входа (не нужно ставить отдельное приложение), встроенная идентификация пользователя, уведомления, платежи.

### 1.3 Целевые пользователи
- **Спортсмен-самоучка** — ведёт себя сам, берёт готовый шаблон или создаёт свою программу.
- **Спортсмен с тренером** — получает план от тренера, тренируется, отмечает выполнение.
- **Тренер** — ведёт от 1 до N подопечных, строит планы, контролирует выполнение и доступ.

### 1.4 Что НЕ входит в MVP (явно)
- Социальная лента / соревнования между пользователями.
- Видеоаналитика техники, ИИ-рекомендации (зарезервировано под `emergentintegrations`/LLM на будущее).
- Полноценный биллинг/бухгалтерия (оплата — опциональный модуль, заглушка → интеграция позже).

---

## 2. Роли, права и пользовательские сценарии

### 2.1 Роли
| Роль | Описание | Может |
|------|----------|-------|
| `athlete` | Спортсмен | Видеть свой активный план, запускать тренировку, отмечать подходы, видеть свою статистику, выбирать/создавать/импортировать программу (если ведёт себя сам) |
| `coach` | Тренер | Управлять списком подопечных, создавать/править их планы, видеть выполнение в реальном времени, подтверждать выполненное, подтверждать доступ к неделе, (опц.) выставлять оплату |
| `coach+athlete` | Гибрид | Один Telegram-аккаунт может быть и тренером, и спортсменом одновременно (переключатель режима) |

> Роль не «жёсткая»: пользователь регистрируется как `athlete` по умолчанию. Стать тренером можно через переключение режима в профиле. Связь «тренер ↔ спортсмен» создаётся через приглашение (deep link / код).

### 2.2 Модель связи тренер ↔ спортсмен
- Тренер генерирует **invite-код** или deep link `https://t.me/<bot>?startapp=coach_<code>`.
- Спортсмен открывает ссылку → создаётся `coach_link` (статус `pending` → `active` после подтверждения спортсменом).
- У спортсмена в один момент времени — **один активный тренер** (или режим self-coached). У тренера — много спортсменов.

### 2.3 Ключевые user stories

**Спортсмен**
- US-A1: Как спортсмен, я хочу выбрать готовую программу из библиотеки, чтобы быстро начать.
- US-A2: Как спортсмен, я хочу создать свою программу в конструкторе (недели → дни → упражнения с подходами/повторами/весом).
- US-A3: Как спортсмен, я хочу импортировать программу из файла (JSON/CSV/Excel), чтобы перенести существующий план.
- US-A4: Как спортсмен, я хочу нажать «Начать» и пошагово отмечать выполненные подходы.
- US-A5: Как спортсмен, я хочу видеть прогресс по дням недели (кольцо выполнения), тоннаж, серию тренировок (streak).
- US-A6: Как спортсмен, я хочу видеть, какие недели плана мне доступны, а какие ждут подтверждения тренера.

**Тренер**
- US-C1: Как тренер, я хочу видеть список подопечных и их активность.
- US-C2: Как тренер, я хочу составлять/править план подопечного (тот же конструктор).
- US-C3: Как тренер, я хочу **в реальном времени** видеть, как спортсмен выполняет тренировку (какой подход отмечен).
- US-C4: Как тренер, я хочу подтверждать выполненное упражнение/тренировку.
- US-C5: Как тренер, я хочу **еженедельно подтверждать** продление доступа спортсмена к плану (с опциональной оплатой).
- US-C6: Как тренер, я хочу получать уведомление, когда спортсмен начал/закончил тренировку.
- US-C7: Как тренер, я хочу **подготовить план подопечного заранее** и сам решить, показать его спортсмену сейчас или позже (черновик/публикация, в т.ч. показ недель по одной).
- US-C8: Как тренер, я хочу **выставлять тренировочные дни** недели для подопечного, и чтобы спортсмен видел их в календаре.
- US-C9: Как тренер, я хочу во время тренировки подопечного **сам отмечать/исправлять выполненные подходы** (если он диктует) и подтверждать упражнения — в реальном времени.
- US-C10: Как тренер, я хочу видеть **отклонения от плана** подопечного (сделал больше/меньше/другой вес/пропустил).
- US-C11: Как тренер, я хочу видеть **пропущенные тренировки** подопечного и решать: засчитать как уважительный пропуск, перенести или оставить пропуском.

**Спортсмен (доп. истории v3.0)**
- US-A7: Как спортсмен, я хочу **импортировать программу по коду или ссылке** от тренера/друга, а не только файлом.
- US-A8: Как спортсмен, если я **пропустил день**, я хочу пометить пропуск (с причиной) или перенести тренировку, чтобы streak не рвался несправедливо.
- US-A9: Как спортсмен, я хочу видеть, **насколько я следую плану** (adherence) и где отклонился.

---

## 3. Доменная модель

### 3.1 Сущности и связи (ER-обзор)

```
User (telegram_id)
  ├─ role: athlete | coach (+ режим)
  ├─ coach_link ──────────────► User (coach)        # M:1 (у спортсмена один тренер)
  │
  ├─ Plan (assigned instance)  # активный план спортсмена
  │    ├─ source_template_id ─► ProgramTemplate (опц.)
  │    ├─ weeks[] ─ days[] ─ exercises[]  # СНИМОК структуры (не ссылка), чтобы правки не ломали шаблон
  │    └─ WeekAccess[]         # доступ по неделям (gating)
  │
  ├─ WorkoutSession            # один запуск тренировки («Начать»)
  │    ├─ plan_id, week_index, day_index, date
  │    ├─ status: in_progress | finished | aborted
  │    └─ set_logs[]           # фактические подходы (reps/weight/completed/rpe)
  │
  └─ ProgramTemplate (owned)   # созданные/импортированные шаблоны

Exercise (catalog)             # справочник упражнений (built-in + кастомные)
Payment (опц.)                 # привязан к WeekAccess
Notification                   # системные уведомления
```

### 3.2 Ключевое архитектурное решение: «снимок» (snapshot) плана
`ProgramTemplate` — это **многоразовый шаблон** (библиотека/конструктор). При назначении спортсмену создаётся `Plan` со **скопированной структурой** недель/дней/упражнений. Так:
- правки тренера в плане конкретного спортсмена не меняют общий шаблон;
- история тренировок остаётся корректной, даже если шаблон позже изменят/удалят.

### 3.3 Прогресс — больше никаких mock
Текущий `MOCK_PROGRESS` и `WORKOUT_STATS` в `DateSelector.js` заменяются на вычисляемые значения:
- **План** даёт «запланированные» упражнения дня (target).
- **WorkoutSession + SetLog** дают «фактическое» выполнение.
- Прогресс дня = `completed_sets / planned_sets * 100`.

### 3.4 Новые доменные понятия (v3.0)
- **Видимость плана (visibility):** план может быть `draft` (тренер готовит, спортсмен не видит содержимого) или `published`. Дополнительно недели плана можно открывать по одной (`ProgramWeek.published`) — реализует «показывать заранее или нет».
- **Авторство действия (provenance):** отметка подхода/упражнения хранит, кто её сделал — спортсмен или тренер (`filled_by`), и подтверждена ли тренером (`coach_confirmed`). Нужно для real-time co-scribe (§6) и для требования «тренер сам заполняет/подтверждает».
- **Статус дня плана:** помимо «выполнено/в процессе», у запланированного дня есть `missed` (пропущен без отметки), `skipped` (осознанный пропуск с причиной), `excused` (тренер засчитал уважительным) и `rescheduled` (перенесён). Хранится в `plan_day_marks` (§4.11).
- **Отклонение (deviation):** разница «план vs факт» по объёму/весу/составу упражнений; основа — `plan_sets_scheme` vs `sets_scheme` и `status='skipped'` на `SessionExercise` (уже есть в моделях).
- **Шаринг программы:** шаблон можно расшарить коротким кодом/ссылкой (`share_code`), получатель импортирует его клоном в свою библиотеку (§8.5).

---

## 4. Схема базы данных (MongoDB)

> Конвенции: `id` = `str(uuid.uuid4())` (для встроенных — детерминированный `uuid5` от slug, чтобы сидирование было идемпотентным). Все `datetime` хранятся как ISO-строки. Чтение всегда с `{"_id": 0}`.

### 4.1 Коллекция `users` (расширение существующей)
| Поле | Тип | Примечание |
|------|-----|-----------|
| `id` | string (UUID) | внутренний id |
| `telegram_id` | int | ключ upsert, **уникальный индекс** |
| `first_name`, `last_name`, `username`, `language_code` | string\|null | из Telegram |
| `roles` | string[] | `["athlete"]` по умолчанию; может содержать `"coach"` |
| `active_mode` | string | `"athlete"` \| `"coach"` (текущий режим UI) |
| `coach_telegram_id` | int\|null | текущий тренер спортсмена |
| `invite_code` | string\|null | код приглашения, если пользователь — тренер |
| `settings` | object | единицы (кг/lb), таймер отдыха по умолчанию, уведомления |
| `created_at`, `updated_at` | string (ISO) | |

### 4.2 Коллекция `exercises` (справочник)
| Поле | Тип | Примечание |
|------|-----|-----------|
| `id` | string (UUID) | для built-in — `uuid5(slug)` |
| `slug` | string | стабильный ключ built-in (`bench-press`) |
| `name` | string | «Жим лёжа» |
| `muscle_groups` | string[] | `["chest","triceps"]` |
| `equipment` | string | `barbell`/`dumbbell`/`machine`/`bodyweight`/... |
| `category` | string | `compound`/`isolation` |
| `is_builtin` | bool | системное упражнение |
| `owner_telegram_id` | int\|null | автор кастомного упражнения |
| `created_at` | string (ISO) | |

### 4.3 Встроенные структуры программы (embedded)
```python
ProgramExercise:
  exercise_id: str            # ссылка на exercises.id
  exercise_name: str          # денормализация для быстрого рендера
  order: int                  # порядок в дне
  target_sets: int
  target_reps: str            # строка: "5", "8-12", "AMRAP"
  target_weight: float|null   # кг (или null/процент)
  weight_type: str            # "kg" | "percent_1rm" | "rpe" | "bodyweight"
  target_rpe: float|null
  rest_seconds: int|null
  notes: str|null

ProgramDay:
  day_index: int              # 1..N в рамках недели (или 1..7)
  title: str                  # «День 1 — Присед»
  is_rest: bool               # день отдыха
  exercises: ProgramExercise[]

ProgramWeek:
  week_index: int             # 1..weeks_count
  days: ProgramDay[]
```

### 4.4 Коллекция `programs` (шаблоны)
| Поле | Тип | Примечание |
|------|-----|-----------|
| `id` | string (UUID) | built-in → `uuid5(slug)` |
| `slug` | string\|null | стабильный ключ built-in |
| `name` | string | «5/3/1 для начинающих» |
| `description` | string | |
| `author` | string | «TWB» / имя тренера |
| `level` | string | `beginner`/`intermediate`/`advanced` |
| `goal` | string | `strength`/`hypertrophy`/`powerlifting`/`general` |
| `days_per_week` | int | |
| `weeks_count` | int | |
| `weeks` | ProgramWeek[] | полная структура |
| `is_builtin` | bool | |
| `owner_telegram_id` | int\|null | автор кастомного шаблона |
| `tags` | string[] | |
| `created_at`, `updated_at` | string (ISO) | |

### 4.5 Коллекция `plans` (назначенный план спортсмена)
| Поле | Тип | Примечание |
|------|-----|-----------|
| `id` | string (UUID) | |
| `athlete_telegram_id` | int | владелец-спортсмен (**индекс**) |
| `coach_telegram_id` | int\|null | тренер (если есть) |
| `source_template_id` | string\|null | из какого шаблона создан |
| `name` | string | |
| `status` | string | `active`/`paused`/`completed` |
| `start_date` | string (ISO date) | дата начала недели 1 |
| `current_week` | int | текущая неделя (1-based) |
| `weeks` | ProgramWeek[] | **снимок** структуры (правится независимо) |
| `created_at`, `updated_at` | string (ISO) | |

### 4.6 Коллекция `workout_sessions`
| Поле | Тип | Примечание |
|------|-----|-----------|
| `id` | string (UUID) | |
| `plan_id` | string | |
| `athlete_telegram_id` | int | **индекс** |
| `coach_telegram_id` | int\|null | для real-time нотификаций |
| `week_index`, `day_index` | int | какой день плана выполняется |
| `date` | string (ISO date) | дата тренировки |
| `status` | string | `in_progress`/`finished`/`aborted` |
| `started_at`, `finished_at` | string (ISO)\|null | |
| `set_logs` | SetLog[] | фактические подходы (см. ниже) |
| `stats` | object | агрегаты сессии (tonnage, duration_sec, completion_pct, muscle_groups, difficulty) |
| `coach_confirmed` | bool | тренер подтвердил выполнение |
| `created_at`, `updated_at` | string (ISO) | |

```python
SetLog:
  exercise_id: str
  exercise_name: str
  set_index: int              # 1..target_sets
  target_reps: str
  target_weight: float|null
  done_reps: int|null         # факт
  done_weight: float|null     # факт
  rpe: float|null
  completed: bool
  completed_at: string|null   # ISO
```

### 4.7 Коллекция `week_access` (доступ по неделям)
| Поле | Тип | Примечание |
|------|-----|-----------|
| `id` | string (UUID) | |
| `plan_id` | string | |
| `athlete_telegram_id` | int | |
| `coach_telegram_id` | int\|null | кто подтверждает |
| `week_index` | int | какая неделя |
| `status` | string | `locked`/`pending`/`approved`/`expired` |
| `requires_payment` | bool | нужна ли оплата |
| `payment_status` | string | `none`/`pending`/`paid` |
| `payment_id` | string\|null | ссылка на `payments` |
| `confirmed_by` | int\|null | telegram_id тренера |
| `confirmed_at` | string (ISO)\|null | |
| `valid_until` | string (ISO)\|null | срок действия доступа |
| `created_at`, `updated_at` | string (ISO) | |

### 4.8 Коллекция `coach_links`
| Поле | Тип | Примечание |
|------|-----|-----------|
| `id` | string (UUID) | |
| `coach_telegram_id` | int | |
| `athlete_telegram_id` | int | |
| `status` | string | `pending`/`active`/`revoked` |
| `created_at`, `updated_at` | string (ISO) | |

### 4.9 Коллекции `payments` (опц.) и `notifications`
- `payments`: `id, week_access_id, athlete_telegram_id, coach_telegram_id, provider(telegram_stars/stripe/manual), amount, currency, status, provider_payload, created_at`.
- `notifications`: `id, telegram_id, type, payload, read, created_at`.

### 4.10 Индексы (создавать при старте, идемпотентно)
- `users`: unique `telegram_id`.
- `exercises`: `slug`, `owner_telegram_id`.
- `programs`: `is_builtin`, `owner_telegram_id`.
- `plans`: `athlete_telegram_id`, составной `(athlete_telegram_id, status)`.
- `workout_sessions`: `athlete_telegram_id`, составной `(plan_id, week_index, day_index)`.
- `week_access`: составной `(plan_id, week_index)`.
- `coach_links`: составной `(coach_telegram_id, athlete_telegram_id)`.

### 4.11 Доработка v3.0 — новые поля и коллекции

**`plans` (расширение):**
| Поле | Тип | Примечание |
|------|-----|-----------|
| `visibility` | string | `draft` \| `published`. Coach-created → по умолчанию `draft`; self-created → `published` |
| `published_at` | string (ISO)\|null | когда план показан спортсмену |
| `prepared_by_coach` | bool | план собран тренером заранее |

**`ProgramWeek` (в снимке плана, расширение):**
| Поле | Тип | Примечание |
|------|-----|-----------|
| `published` | bool | неделя видна спортсмену (показ «по одной неделе»); по умолчанию `true` для published-плана |

**`SessionExercise` / отметки (расширение) — для real-time co-scribe тренера:**
| Поле | Тип | Примечание |
|------|-----|-----------|
| `filled_by` | string\|null | `athlete` \| `coach` — кто заполнил факт |
| `coach_confirmed` | bool | тренер подтвердил выполнение упражнения |
| `confirmed_by` | int\|null | telegram_id тренера |
| `confirmed_at` | string (ISO)\|null | |

> На уровне `WorkoutSession` добавляется `coach_confirmed: bool` (вся тренировка подтверждена) и `last_event_at` (для presence/диффа real-time).

**`programs` (расширение) — шаринг по коду/ссылке:**
| Поле | Тип | Примечание |
|------|-----|-----------|
| `share_code` | string\|null | короткий код (6–8 симв., A–Z0–9), **уникальный sparse-индекс** |
| `is_public` | bool | доступен по коду/ссылке |
| `shared_at` | string (ISO)\|null | |

> Альтернатива/дополнение — отдельная коллекция `program_shares` (`id, code, template_id, owner_telegram_id, expires_at, max_uses, used_count, created_at`) — если нужны срок действия и лимиты. Для MVP достаточно поля `share_code` на шаблоне.

**Новая коллекция `plan_day_marks` (пропуски/переносы):**
| Поле | Тип | Примечание |
|------|-----|-----------|
| `id` | string (UUID) | |
| `plan_id` | string | |
| `athlete_telegram_id` | int | **индекс** |
| `week_index`, `day_index` | int | какой день плана |
| `status` | string | `skipped` \| `missed` \| `rescheduled` \| `excused` |
| `reason` | string\|null | причина (болезнь, форс-мажор, …) |
| `rescheduled_to` | string (ISO date)\|null | новая дата (для переноса) |
| `marked_by` | int | кто пометил (telegram_id спортсмена/тренера) |
| `created_at`, `updated_at` | string (ISO) | |

> `missed` может выставляться **автоматически** (запланированный день прошёл без `finished`-сессии) — лениво при чтении прогресса или фоновой проверкой; `skipped`/`excused`/`rescheduled` — явное действие пользователя/тренера.

**`users.settings` (расширение):**
| Поле | Тип | Примечание |
|------|-----|-----------|
| `streak_mode` | string | `strict` (пропуск рвёт серию) \| `lenient` (уважительный пропуск/перенос не рвёт) |
| `units` | string | `kg` \| `lb` |
| `default_rest_sec` | int | таймер отдыха по умолчанию |

**Новые индексы (идемпотентно в `startup`):**
- `programs`: unique sparse `share_code`.
- `plans`: добавить `(coach_telegram_id, status)` (планы подопечных тренера) и `visibility`.
- `plan_day_marks`: составной `(plan_id, week_index, day_index)`, `athlete_telegram_id`.

---

## 5. API-контракт (REST, префикс `/api`)

> Аутентификация (Phase 0/позже): заголовок `X-Telegram-Init-Data` валидируется по HMAC бот-токена; до этого — `telegram_id` в пути/теле (как сейчас). Все ответы — JSON, ошибки внешних API не пробрасываются как 500.

### 5.1 Пользователи и роли
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| POST | `/api/users` | Upsert пользователя (как сейчас) + поля roles/mode |
| GET | `/api/users/{telegram_id}` | Профиль |
| PATCH | `/api/users/{telegram_id}/mode` | Переключить `active_mode` (athlete/coach) |
| GET | `/api/telegram/avatar/{user_id}` | Аватар (как сейчас) |

### 5.2 Справочник упражнений
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| GET | `/api/exercises?query=&muscle=` | Список (built-in + кастомные) |
| POST | `/api/exercises` | Создать кастомное упражнение |

### 5.3 Программы (шаблоны)
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| GET | `/api/programs/templates?level=&goal=&owner=` | Библиотека шаблонов |
| GET | `/api/programs/templates/{id}` | Детали шаблона |
| POST | `/api/programs/templates` | Создать шаблон (конструктор/импорт) |
| PUT | `/api/programs/templates/{id}` | Редактировать свой шаблон |
| POST | `/api/programs/import` | Импорт из файла (multipart) → шаблон |
| GET | `/api/programs/templates/{id}/export?format=json` | Экспорт |

### 5.4 Планы (назначенные)
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| POST | `/api/plans` | Создать план для спортсмена (из `template_id` или inline) |
| GET | `/api/plans/active/{telegram_id}` | Активный план спортсмена (или null) |
| GET | `/api/plans/{plan_id}` | Детали плана |
| PUT | `/api/plans/{plan_id}` | Редактировать план (тренер/владелец) |
| GET | `/api/plans/{plan_id}/day?week=&day=` | День плана: упражнения + статус выполнения |
| GET | `/api/plans/{plan_id}/week-progress?week=` | Прогресс по дням недели (для колец) |

### 5.5 Тренировочные сессии (Phase 2)
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| POST | `/api/sessions/start` | «Начать»: создать сессию для дня плана |
| GET | `/api/sessions/{id}` | Текущее состояние сессии |
| PATCH | `/api/sessions/{id}/set` | Отметить подход (reps/weight/completed) |
| POST | `/api/sessions/{id}/finish` | Завершить тренировку → пересчёт статистики |
| GET | `/api/sessions?telegram_id=&from=&to=` | История сессий (для streak/статистики) |
| GET | `/api/stats/{telegram_id}` | Сводная статистика (streak, тоннаж, частота) |

### 5.6 Тренер (Phase 3)
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| GET | `/api/coach/{telegram_id}/clients` | Список подопечных + статус активности |
| POST | `/api/coach/invite` | Создать invite-код / deep link |
| POST | `/api/coach/link` | Привязать спортсмена по коду |
| GET | `/api/coach/{telegram_id}/clients/{athlete_id}/plan` | План подопечного |
| PATCH | `/api/sessions/{id}/confirm` | Подтвердить выполнение упражнения/сессии |

### 5.7 Доступ по неделям + оплата (Phase 5)
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| GET | `/api/plans/{plan_id}/access` | Карта доступа по неделям |
| POST | `/api/access/request` | Спортсмен запрашивает следующую неделю |
| POST | `/api/access/confirm` | Тренер подтверждает неделю (с/без оплаты) |
| POST | `/api/payments/create` | Создать оплату (Telegram Stars/Stripe) |
| POST | `/api/payments/webhook` | Webhook провайдера |

### 5.8 Доработка v3.0 — новые эндпоинты

**Видимость плана и тренерская подготовка (P3)**
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| POST | `/api/plans` (расширение) | поддержать `visibility=draft`, `prepared_by_coach=true` |
| PATCH | `/api/plans/{id}/visibility` | переключить `draft`/`published` (только тренер/владелец); `{ "visibility": "published" }` |
| PATCH | `/api/plans/{id}/weeks/{week}/publish` | открыть/скрыть конкретную неделю (`{ "published": true }`) |
| PATCH | `/api/plans/{id}/training-days` | тренер выставляет дни недели (`{ "training_days": [1,3,5] }`), видно спортсмену |
| GET | `/api/plans/active/{telegram_id}` (поведение) | для `draft`-плана спортсмену вернуть «план готовится» (без содержимого) |

**Real-time заполнение/подтверждение тренером (P3–P4)**
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| PATCH | `/api/sessions/{id}/set` (расширение) | принимает `actor` (`athlete`/`coach`) → пишет `filled_by`; broadcast события |
| PATCH | `/api/sessions/{id}/exercise/{order}/confirm` | тренер подтверждает упражнение (`coach_confirmed=true`) |
| POST | `/api/sessions/{id}/confirm` | тренер подтверждает всю тренировку |

**Импорт по коду/ссылке (P6)**
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| POST | `/api/programs/templates/{id}/share` | сгенерировать/вернуть `share_code` + deep link |
| GET | `/api/programs/by-code/{code}` | превью шаблона по коду (без импорта) |
| POST | `/api/programs/import-by-code` | `{ "code": "ABC123" }` → клонировать шаблон в библиотеку пользователя |

**Пропуски тренировок (P2.1/P3)**
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| POST | `/api/plans/{id}/day/skip` | пометить день `skipped` (`{week,day,reason}`) |
| POST | `/api/plans/{id}/day/reschedule` | перенести (`{week,day,rescheduled_to}`) |
| PATCH | `/api/plans/{id}/day/{week}/{day}/mark` | тренер: `excused`/`missed` (засчитать/нет) |
| GET | `/api/plans/{id}/missed` | список пропущенных/перенесённых дней |

**Статистика отклонений (P2.1)**
| Метод | Endpoint | Назначение |
|-------|----------|------------|
| GET | `/api/sessions/{id}/deviation` | отклонения сессии: план vs факт по упражнениям |
| GET | `/api/stats/{telegram_id}/adherence?plan_id=` | adherence по плану: объём, вес, расписание |

### 5.9 Подробная статистика подопечного с графиками (P7) 🆕

> Источник истины — завершённые `workout_sessions` спортсмена + снимок `plan`. Все эндпоинты возвращают готовые к рендеру ряды (recharts). Тренерские эндпоинты — **coach-gated** (тренер должен быть привязан к спортсмену, иначе `403`), как `GET /api/coach/{id}/clients/{athlete}/plan`.

| Метод | Endpoint | Назначение |
|-------|----------|------------|
| GET | `/api/stats/{telegram_id}/detailed?from=&to=&plan_id=` | Сводка + временные ряды: тоннаж по неделям, частота/нед, completion%, streak, распределение по группам мышц, оценка 1ПМ по основным движениям |
| GET | `/api/stats/{telegram_id}/exercise-progress?slug=&plan_id=` | Прогресс конкретного упражнения: фактический топ-вес и тоннаж по датам/неделям (для линейного графика) |
| GET | `/api/coach/{coach_id}/clients/{athlete_id}/stats?from=&to=&plan_id=` | То же, что `detailed`, но для подопечного (coach-gated, `403` если не его спортсмен) |
| GET | `/api/coach/{coach_id}/clients/{athlete_id}/exercise-progress?slug=` | Прогресс упражнения подопечного (coach-gated) |

**Формат ответа `detailed` (пример):**
```json
{
  "telegram_id": 701002,
  "range": {"from": "2025-06-01", "to": "2025-07-31"},
  "summary": {
    "total_workouts": 18, "streak_days": 4, "avg_per_week": 3.1,
    "completion_pct": 86, "total_tonnage": 142500
  },
  "tonnage_by_week": [{"week": "2025-W23", "tonnage": 18200}, ...],
  "frequency_by_week": [{"week": "2025-W23", "count": 3}, ...],
  "muscle_distribution": [{"group": "Н", "sets": 64}, {"group": "Г", "sets": 40}, ...],
  "one_rep_max_est": [{"slug": "squat-competition", "name": "Присед", "value": 205}, ...],
  "adherence": {"volume_pct": 91, "schedule_pct": 88, "tonnage_dev_pct": -4}
}
```

> На фронте эти ряды рисуются через **recharts** (зависимость уже есть) — см. §9.3 и §11.5.

---

## 6. Real-time архитектура (WebSocket)

### 6.1 Цель
Тренер видит ход тренировки спортсмена «вживую»: запуск, каждая отметка подхода, завершение; правки плана и подтверждения доходят моментально в обе стороны.

### 6.2 Транспорт
- **Нативный WebSocket FastAPI** — endpoint `WS /api/ws` (важно: префикс `/api`, чтобы ingress направил на backend:8001).
- **ConnectionManager** (in-memory) для MVP: словарь «комната → набор соединений».
  - Комнаты: `plan:{plan_id}` (общая для спортсмена и его тренера) и `user:{telegram_id}` (личные уведомления).
- **Масштабирование (future):** при нескольких инстансах backend — Redis Pub/Sub как шина событий между подами. В MVP — один инстанс, in-memory достаточно. (Записано в техдолг.)

### 6.3 Хендшейк и аутентификация
1. Клиент подключается: `wss://<host>/api/ws?init_data=<telegram_initData>` (или токен).
2. Сервер валидирует `initData` (HMAC бот-токена), извлекает `telegram_id`.
3. Сервер подписывает соединение на комнаты пользователя: `user:{telegram_id}` и все его `plan:{plan_id}` (для спортсмена — свой план; для тренера — планы подопечных, открытые в UI).
4. Ping/pong каждые ~25с для удержания соединения.

### 6.4 Событийная модель (JSON)
Формат сообщения: `{ "type": <event>, "room": <room>, "payload": {...}, "ts": <iso> }`.

| Событие | Кто шлёт | Кто получает | Payload |
|---------|----------|--------------|---------|
| `session.started` | athlete | coach | plan_id, session_id, day_index |
| `set.completed` | athlete | coach | session_id, exercise_id, set_index, done_reps, done_weight |
| `exercise.completed` | athlete | coach | session_id, exercise_id |
| `session.finished` | athlete | coach | session_id, stats |
| `plan.updated` | coach | athlete | plan_id, week_index, day_index |
| `set.confirmed` | coach | athlete | session_id, exercise_id |
| `week.approved` | coach | athlete | plan_id, week_index, valid_until |
| `presence` | server | room | who is online |
| `plan.published` | coach | athlete | plan_id, visibility |
| `week.published` | coach | athlete | plan_id, week_index |
| `training_days.updated` | coach | athlete | plan_id, training_days[] |
| `set.filled` | coach\|athlete | room | session_id, exercise_order, set_index, filled_by, done_reps, done_weight |
| `exercise.confirmed` | coach | athlete | session_id, exercise_order, confirmed_by |
| `session.confirmed` | coach | athlete | session_id |
| `session.missed` | server | coach | plan_id, week_index, day_index |
| `day.skipped` | athlete\|coach | room | plan_id, week_index, day_index, status, reason |
| `day.rescheduled` | athlete\|coach | room | plan_id, week_index, day_index, rescheduled_to |

> **Источник истины — БД.** WebSocket только транслирует изменения. Каждое событие сначала персистится REST/обработчиком, затем broadcast. На реконнекте клиент делает REST-«догон» (refetch текущего состояния), поэтому потеря сокет-сообщения не приводит к рассинхрону.

### 6.5 Frontend
- Хук `useRealtime(planId)` — открывает соединение, переподключение с backoff, диспатчит события в стор.
- Оптимистичный апдейт у спортсмена при отметке подхода + подтверждение по ответу REST.
- У тренера — «живой» экран сессии подопечного, обновляется по событиям.

---

## 7. Доступ по неделям + подтверждение тренера + оплата

### 7.1 Логика gating
- При создании плана из шаблона на N недель создаются записи `week_access`:
  - неделя 1 → `approved` (старт сразу), либо `pending`, если тренер требует подтверждения с самого начала;
  - недели 2..N → `locked`.
- Спортсмен видит заблокированные недели с пометкой «Ожидает подтверждения тренера».
- За X дней до конца недели спортсмен/тренер получает напоминание о продлении.

### 7.2 Сценарий подтверждения
1. Спортсмен (или система) создаёт `access.request` на следующую неделю → статус `pending`, тренеру приходит уведомление (+ `week.approved`/`presence` события).
2. Тренер в своём режиме видит запрос и:
   - **без оплаты** → `access.confirm` → статус `approved`, `valid_until` = +7 дней;
   - **с оплатой** → `requires_payment=true` → спортсмену выставляется счёт → после `paid` → `approved`.
3. После `approved` неделя разблокируется, real-time событие `week.approved` обновляет UI спортсмена.

### 7.3 Оплата (опциональный модуль)
- **Провайдеры (выбор на этапе Phase 5):** Telegram Stars (нативно в Mini App) или Stripe (через playbook-эксперта). В MVP — заглушка `provider=manual` (тренер вручную отмечает оплату).
- Интеграция платежей выполняется **только через `integration_playbook_expert_v2`** и после получения ключей от пользователя.

---

## 8. Программы: импорт, экспорт, шаблоны, конструктор

### 8.1 Встроенная библиотека шаблонов (seed)
Идемпотентное сидирование при старте backend (детерминированные `uuid5` от slug). Стартовый набор (примерные, силовые):
- **Full Body для новичка** (3 дня/нед, 4 недели) — присед/жим/тяга, линейная прогрессия.
- **Upper/Lower** (4 дня/нед, 4 недели) — гипертрофия.
- **Powerlifting Peaking** (4 дня/нед, 3 недели) — присед/жим/тяга по процентам от 1ПМ.

### 8.2 Конструктор программ (in-app)
UI «недели → дни → упражнения». Поля упражнения: упражнение из справочника, подходы, повторы (строка), вес/тип веса/RPE, отдых, заметка. Drag-and-drop порядка — на будущее.

### 8.3 Импорт из файла
- **Форматы:** JSON (нативная схема TWB), CSV, Excel (.xlsx). Бэкенд уже имеет `pandas` и `python-multipart` в `requirements.txt` — Excel/CSV парсинг доступен.
- **Поток:** `POST /api/programs/import` (multipart) → определить формат → распарсить в `ProgramTemplate` → вернуть превью на подтверждение → сохранить.
- **CSV/Excel-схема (пример колонок):** `week, day, day_title, exercise, sets, reps, weight, weight_type, rpe, rest, notes`.
- **Маппинг упражнений:** по имени ищем в `exercises`; если нет — создаём кастомное (`is_builtin=false`).
- **Валидация:** ошибки строк собираются в отчёт, не падаем целиком.

### 8.4 Экспорт
`GET /api/programs/templates/{id}/export?format=json|csv` — для переноса/бэкапа.

### 8.5 Импорт по коду/ссылке (share-code + deep link)
Помимо файлов (§8.3), программой можно поделиться **коротким кодом** или **ссылкой**:
- **Шаринг:** автор/тренер вызывает `POST /api/programs/templates/{id}/share` → генерируется `share_code` (6–8 символов, A–Z0–9, уникальный) и deep link вида `https://t.me/<bot>?startapp=prog_<code>`. Код стабилен (повторный вызов возвращает тот же).
- **Импорт по коду:** получатель вводит код в UI → `GET /api/programs/by-code/{code}` (превью) → `POST /api/programs/import-by-code` → шаблон **клонируется** (новый `uuid`, `is_builtin=false`, `owner_telegram_id` = импортирующий, `share_code` не копируется). Сохраняются неизменяемые данные автора (`base_maxes`, `requires_maxes`, `lift_group`).
- **Импорт по ссылке (deep link):** при открытии Mini App с `startapp=prog_<code>` фронт читает `tg.initDataUnsafe.start_param`, извлекает код и автоматически открывает экран превью/импорта.
- **Безопасность:** код даёт доступ только на чтение/копирование; оригинал и его правки остаются у автора (изоляция через клон, как со снимком плана).
- **Отзыв/срок (опц.):** для срока действия и лимита использований — коллекция `program_shares` (§4.11).

---

## 9. Статистика и прогресс (формулы)

| Метрика | Формула |
|---------|---------|
| Прогресс дня, % | `completed_sets / planned_sets * 100` (если день — отдых, прогресс = N/A) |
| Тоннаж сессии | `Σ (done_weight × done_reps)` по всем выполненным подходам |
| Длительность | `finished_at − started_at` |
| Группы мышц | объединение `muscle_groups` упражнений дня |
| Сложность | эвристика по тоннажу/объёму/RPE: `Легко / Средне / Тяжело` |
| Streak (серия) | число подряд идущих дней (или тренировочных дней по плану) с завершённой ≥1 сессией; прерывается при пропуске запланированного дня |
| Частота/нед | число завершённых сессий за 7 дней |

> Эти значения заменяют `MOCK_PROGRESS` и `WORKOUT_STATS` в `DateSelector.js`, а также статичный «0 дней» streak в `App.js`.

### 9.1 Система пропусков тренировок (skip / missed / reschedule)
Запланированный тренировочный день (по `training_days` и расписанию плана) может оказаться невыполненным. Состояния и логика:

| Состояние | Как возникает | Streak (`strict`) | Streak (`lenient`) |
|-----------|----------------|-------------------|--------------------|
| `missed` | день прошёл без `finished`-сессии (авто) | **рвёт** серию | рвёт серию |
| `skipped` | спортсмен осознанно пометил пропуск (+причина) | рвёт серию | **не рвёт** (если причина указана) |
| `excused` | тренер засчитал пропуск уважительным | не рвёт | не рвёт |
| `rescheduled` | перенос на другую дату | не рвёт (до новой даты) | не рвёт |

- **Авто-детект `missed`:** лениво при чтении прогресса недели / `GET /api/plans/{id}/missed` или фоновой проверкой (день < сегодня, нет `finished`-сессии, день не `rest`/`skipped`/`rescheduled`).
- **Перенос (`reschedule`):** создаёт запись в `plan_day_marks` (`rescheduled_to`); исходная дата не считается пропуском, UI показывает «перенесено на …».
- **Streak (обновление формулы §9):** серия = подряд идущие **тренировочные** дни плана с выполнением; `excused`/`rescheduled` и (в режиме `lenient`) `skipped` с причиной — **не прерывают** серию. Режим — `users.settings.streak_mode`.
- **Real-time:** `session.missed` (тренеру), `day.skipped`/`day.rescheduled` (в комнату плана).
- **UI:** в недельном селекторе пропущенный день — приглушён/перечёркнут с бейджем; действия «Пропустить (причина)» и «Перенести».

### 9.2 Статистика отклонений от плана (adherence)
Сравнение «план vs факт» (основа — `plan_sets_scheme` vs `sets_scheme` и `status` на `SessionExercise`):

| Метрика | Формула |
|---------|---------|
| Adherence по объёму, % | `выполнено_как_в_плане_подходов / запланировано_подходов × 100` |
| Отклонение по тоннажу, % | `(факт_тоннаж − план_тоннаж) / план_тоннаж × 100` |
| Отклонение по весу (упр./лифт) | `факт_вес − план_вес` (агрегируется по `lift_group`) |
| Adherence по расписанию, % | `завершено_дней / запланировано_дней` (учитывает §9.1) |
| Состав | добавленные/удалённые/заменённые упражнения (по `edited`, отсутствию в плане) |

**Флаги отклонения на упражнение:** `more_volume` / `less_volume` / `weight_up` / `weight_down` / `skipped` / `extra` / `removed` / `substituted`.

- **На сессию:** `GET /api/sessions/{id}/deviation` — список упражнений с план/факт и флагами.
- **На план/спортсмена:** `GET /api/stats/{telegram_id}/adherence?plan_id=` — сводка для спортсмена и тренера (где систематически отклоняется: недобирает объём, занижает/завышает веса, пропускает дни).
- **UI:** в `WorkoutView` и статистике — цветовые бейджи отклонений; у тренера — индикатор adherence по подопечному.

### 9.3 Подробная статистика подопечного с графиками (P7) 🆕

Тренер открывает экран аналитики подопечного (`/coach/:athleteId/stats`) и видит **подробную статистику с графиками** (на базе recharts). Тот же экран доступен спортсмену для себя (`/stats`). Источник данных — завершённые `workout_sessions` + снимок плана; эндпоинты — §5.9 (тренерские — coach-gated).

**Состав экрана (карточки + графики):**

| Блок | Тип графика (recharts) | Данные |
|------|------------------------|--------|
| Сводка | KPI-карточки | всего тренировок, streak, частота/нед, completion %, суммарный тоннаж |
| Тоннаж по неделям | столбчатый (`BarChart`) | `tonnage_by_week` |
| Частота тренировок | столбчатый/линия | `frequency_by_week` |
| Прогресс упражнения | линейный (`LineChart`) | факт топ-вес по неделям для выбранного движения (`exercise-progress`); опц. пунктиром — план (как «Прогноз по плану» в `DateSelector`) |
| Распределение по группам мышц | круговой/радиальный (`PieChart`) | `muscle_distribution` (буквы Н/Г/С/П/Р/К) |
| Оценка 1ПМ | KPI/линия | `one_rep_max_est` по основным движениям (Эпли/Бжицки от факт. подходов) |
| Adherence (план vs факт) | прогресс-бары | `adherence.volume_pct`, `schedule_pct`, `tonnage_dev_pct` (§9.2) |

**Формулы (бэкенд считает, фронт только рисует):**
- Тоннаж недели — Σ выполненных `done_weight × done_reps` по сессиям недели (см. §9).
- Частота/нед — число `finished`-сессий за ISO-неделю.
- Оценка 1ПМ — Эпли: `вес × (1 + повторы/30)` (берётся максимум по тяжёлым подходам движения).
- Распределение по группам — сумма выполненных подходов по `muscle_group` → буквы (§ seed `MUSCLE_LETTER`).
- Adherence — из §9.2 (план vs факт).

**Доступ/безопасность:** тренерские эндпоинты (§5.9) проверяют связь `coach_links` (active) — иначе `403`. Спортсмен видит только свои данные.

**Кроссплатформенность:** графики адаптивны (`ResponsiveContainer`), тёмная тема (#1C1C1C, акцент #FF6B00), читаемость на узких экранах телефона и широком Telegram Desktop (§12.1).

---

## 10. Аутентификация и безопасность

1. **Telegram initData validation** (Phase 0/2): backend проверяет HMAC-подпись `initData` бот-токеном → доверенный `telegram_id`. До внедрения — текущий упрощённый upsert по `telegram_id`.
2. **Авторизация по ролям:** проверка, что тренер обращается только к своим подопечным; спортсмен — только к своим данным.
3. **Bot token** хранится только в `backend/.env` (используется на сервере). ⚠️ В репозитории токен закоммичен — в проде ротировать и держать в секретах (техдолг из `PROJECT_DETAILS.md`).
4. **WebSocket auth** — тот же initData при подключении.
5. **CORS** — из `CORS_ORIGINS`.

---

## 11. Frontend: архитектура

### 11.1 Навигация (react-router-dom уже есть)
```
/                       → Home (спортсмен): приветствие, streak, недельный селектор, день
/programs               → Библиотека/мои программы (выбор/создание/импорт)
/programs/:id           → Просмотр шаблона
/builder                → Конструктор программы
/workout/:sessionId     → Экран активной тренировки (отметка подходов)  [Phase 2]
/coach                  → Режим тренера: список подопечных             [✅ P3]
/coach/:athleteId       → Карточка подопечного: план, видимость, дни, недели  [✅ P3]
/coach/:athleteId/edit  → Редактор плана подопечного (недели/дни/упражнения)  [✅ P3.1]
/coach/:athleteId/stats → Подробная статистика подопечного с графиками  [⏳ P7]
/stats                  → Своя подробная статистика с графиками         [⏳ P7]
/profile                → Профиль, режим (athlete/coach), «Подопечные», «Мой тренер»  [✅ P3]
```

### 11.2 Слои
- `src/api.js` — единая обёртка над axios (`API = ${REACT_APP_BACKEND_URL}/api`).
- `src/context/UserContext.js` — текущий пользователь, режим, telegram init (+ dev-fallback для браузера вне Telegram).
- `src/context/AuthContext.js` — авторизация + `switchMode(athlete/coach)`.
- `src/hooks/useRealtime.js` — WebSocket (Phase 4).
- Компоненты — поверх существующих shadcn/ui (`components/ui`) + точечный CSS как в `DateSelector.css`. Дизайн-систему НЕ меняем (раздел 6 `AI_CONTEXT.md`).

### 11.3 Dev-fallback (важно для разработки/тестов)
Вне Telegram `window.Telegram` отсутствует. Для локальной разработки и автотестов используем фиксированный dev-пользователь (`telegram_id` из константы), который авто-регистрируется. В Telegram — реальные `initDataUnsafe.user`. Логика выбора инкапсулируется в `UserContext`.

### 11.4 Редактор плана подопечного (✅ реализовано, P3.1)
Экран `/coach/:athleteId/edit` (`pages/CoachPlanEditor.js`). Тренер правит **снимок** плана подопечного:
- недели: пилюли-переключатели + добавить/удалить (с авто-перенумерацией);
- дни: модалка выбора дня недели (Пн–Вс), название, флаг «отдых», удаление;
- упражнения: модалка с полями название/группа мышц/сложность/подсобное/RPE/отдых/заметка и редактором подходов (вес × подходы × повторы, несколько строк), добавление/изменение/удаление.
Каждое действие persists через эндпоинты §11.4-backend (`PATCH /plans/{id}`, `PUT/DELETE /plans/{id}/day|exercise`, `POST/DELETE /plans/{id}/week`); локальный план обновляется из полного ответа `Plan`. %1ПМ/тоннаж считаются на чтении дня.

### 11.5 Экран подробной статистики с графиками (⏳ P7) 🆕
Экран `/coach/:athleteId/stats` (тренеру) и `/stats` (спортсмену себе) на **recharts** (зависимость уже в проекте). Рисует ряды из §5.9: KPI-карточки, тоннаж/частота по неделям (`BarChart`), прогресс топ-веса упражнения (`LineChart`, план — пунктиром), распределение по группам мышц (`PieChart`), оценка 1ПМ, adherence (прогресс-бары). Адаптив через `ResponsiveContainer`, тёмная тема. Тренерские данные — coach-gated.

---

## 12. Дизайн-система
Полностью наследуется из текущего проекта (см. `AI_CONTEXT.md` §6): фон `#1C1C1C`, акцент `#FF6B00`, градиент выбранного дня `#FF8A24 → #FFDA24`, карточка дня `#333`, шрифты Plus Jakarta Sans + GG Zaglav, mobile-first брейкпоинты `374/767/1023/1024`. Новые экраны выдерживают тот же стиль (тёмная тема, оранжевый акцент, скруглённые карточки).

### 12.1 Кроссплатформенность (обязательно с самого начала) ❗
Приложение — Telegram Mini App, что **само по себе кроссплатформенно**, но «сразу» означает явную поддержку и тестирование на всех средах с первого дня:

**Целевые платформы:** Telegram iOS, Telegram Android, Telegram Desktop (Windows/Linux), Telegram macOS, Telegram Web (`web`/`weba`). Плюс обычный браузер (dev-fallback / будущий web-режим).

**Принципы реализации:**
1. **Определение платформы:** `tg.platform` (`ios`/`android`/`tdesktop`/`macos`/`web`/`weba`) и `tg.version` — для условной логики (haptics, BackButton, MainButton).
2. **Адаптивная вёрстка:** расширить mobile-first (≤374/≤767) брейкпоинтами планшета и **десктопа** (Telegram Desktop даёт широкое окно): центрированный контейнер с `max-width`, чтобы UI не «растягивался». Брейкпоинты: `≤374 / ≤767 / 768–1023 / ≥1024`.
3. **Safe-area / вьюпорт:** учитывать `tg.viewportStableHeight`, `tg.safeAreaInset` / CSS `env(safe-area-inset-*)` (notch на iOS), `tg.expand()`; не завязываться на `100vh`.
4. **Темы:** уважать `tg.themeParams`/`colorScheme`, но сохранять фирменную тёмную тему (#1C1C1C, акцент #FF6B00). В вебе вне Telegram — те же стили.
5. **Haptics с fallback:** `tg.HapticFeedback` есть не везде — оборачивать в guard (`tg.HapticFeedback?.impactOccurred?.('light')`).
6. **Кнопки Telegram:** `MainButton`/`BackButton`/`SettingsButton` — единообразно (например, «Начать» через MainButton), с graceful-degradation в вебе (обычные кнопки).
7. **WebSocket-устойчивость:** мобильные платформы усыпляют WebView в фоне — обязателен reconnect с backoff и REST-«догон» состояния (§6.5) при возврате на передний план (`visibilitychange`).
8. **Ввод/жесты:** тач и мышь; не полагаться только на hover; крупные тач-зоны (кнопки подходов).

**Тест-матрица (минимум):** iOS (Telegram), Android (Telegram), Telegram Desktop (широкое окно), Web. Проверять: init/регистрацию, недельный селектор, старт/отметку подходов, real-time, импорт по коду, отображение пропусков.

**Техдолг:** автоматический фронт-тест прогоняем минимум на «desktop»-вьюпорте (1920×800) и мобильном (~430px).

---

## 13. Дорожная карта по фазам

| Фаза | Название | Статус | Содержание | Критерий приёмки |
|------|----------|--------|------------|------------------|
| **P0** | Фундамент | ✅ | Индексы БД, расширение `users` (roles/mode), модульная структура backend, dev-fallback пользователя | Сервисы поднимаются; существующие тесты зелёные |
| **P1** | Программы и план | ✅ | `exercises`/`programs`/`plans` модели + CRUD, seed библиотеки, экран «Программы», назначение плана, **реальные данные дня/недели вместо mock** | Можно выбрать шаблон → он становится активным планом → недельный селектор и день показывают реальные упражнения из БД |
| **P2** | Тренировка и статистика | ✅ | `WorkoutSession` lifecycle: «Начать» → отметка подходов → «Завершить»; расчёт тоннажа/прогресса/streak; правка упражнений + дифф подходов; запрет двойного старта/подтверждение даты | Прогресс-кольца и streak считаются по реальным сессиям |
| **P3** | Режим тренера + видимость плана | ✅ | Роли/режим (athlete/coach), invite-link, список подопечных, просмотр/правка плана, **подготовка плана заранее (`draft`/`published`)**, **показ недель по одной**, **тренер выставляет тренировочные дни**, **подтверждение выполнения тренером**, **старт тренировки тренером** | Тренер ведёт подопечных, готовит план как черновик и публикует когда хочет; выставляет дни; подтверждает выполненное; может запустить тренировку за спортсмена |
| **P4** | Real-time (WebSocket) | ✅ | `/api/ws`, ConnectionManager, события (§6.4), `useRealtime`, **тренер сам заполняет/подтверждает подходы вживую** (`filled_by`/`coach_confirmed`) | Тренер видит и заполняет ход тренировки спортсмена «вживую» без перезагрузки |
| **P5** | Доступ по неделям + оплата | ⏳ | `week_access` gating, **еженедельное подтверждение тренером**, опциональная оплата (Stars/Stripe через playbook) | Недели разблокируются по подтверждению тренера; оплата опциональна |
| **P6** | Импорт/экспорт + полировка | 🟡 | Excel-шаблон со скейлингом (готово); осталось: UI-загрузка файла (JSON/CSV/Excel), **импорт по коду/ссылке (§8.5)**, экспорт, конструктор, меню/Drawer | Импорт реального файла и **импорт по коду/ссылке** через UI создают корректный шаблон |
| **P2.1** | Пропуски + отклонения | ⏳ | **Система пропусков** (skip/missed/reschedule, streak strict/lenient, §9.1), **статистика отклонений от плана** (adherence, §9.2) | Пропуски корректно влияют на streak; видна adherence «план vs факт» |
| **CP** | Кроссплатформенность | 🟢 база готова | Website-first + Telegram WebApp (telegram-web-app.js) + PWA (manifest/SW/иконки), детект среды (`platform.js`), адаптив-центрирование ≥768px, safe-area, install-кнопка. Осталось: haptics в сценариях, MainButton/BackButton, устойчивый WS (с P4) | UI и сценарии работают как сайт, в Telegram и как PWA |

---

## 14. Фаза 1 — детальный план реализации (✅ выполнено, оставлено для истории)

### 14.1 Backend (делаем первым, тестируем `deep_testing_backend_v2`)
1. **Модели** (`backend/models.py` или в `server.py`): `Exercise`, `ProgramExercise`, `ProgramDay`, `ProgramWeek`, `ProgramTemplate`, `Plan` (+ `PlanCreate`).
2. **Seed** (`backend/seed.py`): идемпотентно создать built-in упражнения (≈20–30) и 2–3 шаблона программ (детерминированные `uuid5`). Вызывается в `startup`.
3. **Индексы** в `startup`: unique `users.telegram_id`, `plans.athlete_telegram_id`, `exercises.slug`.
4. **Эндпоинты:**
   - `GET /api/exercises`, `POST /api/exercises`
   - `GET /api/programs/templates`, `GET /api/programs/templates/{id}`, `POST /api/programs/templates`
   - `POST /api/plans` (из `template_id`: снимок недель), `GET /api/plans/active/{telegram_id}`, `GET /api/plans/{id}`
   - `GET /api/plans/{id}/day?week=&day=`, `GET /api/plans/{id}/week-progress?week=`
5. **Конвенции:** UUID, datetime→ISO, `{"_id": 0}`, `/api`-префикс, `ConfigDict(extra="ignore")`.

### 14.2 Frontend (после backend; тест фронта — только с разрешения пользователя)
1. `src/api.js` — методы под новые эндпоинты.
2. `src/context/UserContext.js` — текущий пользователь + dev-fallback.
3. Экран **Программы** (`/programs`): список шаблонов из библиотеки → кнопка «Выбрать» → `POST /api/plans` → активный план.
4. **DateSelector**: заменить `MOCK_PROGRESS` на данные `week-progress` активного плана (дни с тренировкой/отдыхом); заменить `WORKOUT_STATS` на планируемые показатели выбранного дня; вывести список упражнений дня под селектором.
5. Кнопка «Начать» остаётся, но её действие (старт сессии) — Phase 2.

### 14.3 Критерий готовности Фазы 1
- Backend: все новые эндпоинты возвращают корректные данные, seed создаёт библиотеку, план создаётся снимком — подтверждено `deep_testing_backend_v2`.
- Frontend: выбор программы из библиотеки делает её активным планом; недельный селектор и день показывают **реальные** данные из БД (никакого mock).

---

## 15. Тестирование
- **Backend-first** через `deep_testing_backend_v2` после каждого изменения backend; обновлять `test_result.md` перед запуском (не трогать защищённую секцию).
- **Frontend** — `auto_frontend_testing_agent` **только** с явного разрешения пользователя.
- Dev-fallback пользователь позволяет тестировать фронт вне Telegram.
- Ручная проверка backend: `curl -s http://localhost:8001/api/`.

---

## 16. Риски и технический долг
1. **WebSocket за ingress** — проверить, что `wss://.../api/ws` проксируется (префикс `/api`). При проблемах — fallback на polling.
2. **In-memory ConnectionManager** не масштабируется на несколько подов → Redis Pub/Sub (future).
3. **initData не валидируется** сейчас — внедрить HMAC-проверку до продакшена.
4. **Bot token в git** — ротировать, держать в секретах.
5. **Оплата** — только через playbook-эксперта и ключи пользователя; в MVP `manual`.
6. **Снимок плана** увеличивает дублирование данных — приемлемо ради изоляции истории.

---

## 17. Глоссарий
- **Athlete / спортсмен** — пользователь, который тренируется.
- **Coach / тренер** — пользователь, который ведёт спортсменов.
- **ProgramTemplate / шаблон** — многоразовая программа (библиотека/конструктор/импорт).
- **Plan / план** — назначенный спортсмену экземпляр программы (снимок).
- **WorkoutSession / сессия** — один запуск тренировки кнопкой «Начать».
- **SetLog** — запись о фактически выполненном подходе.
- **WeekAccess** — доступ к конкретной неделе плана (gating + подтверждение/оплата).
- **Streak / серия** — число подряд тренировочных дней с выполнением.

---

## 18. История изменений
| Дата | Версия | Изменения |
|------|--------|-----------|
| Июль 2025 | 1.0 | Создан документ: концепция, доменная модель, схема БД, REST/WS-контракты, доступ по неделям + оплата, импорт/экспорт, фазовая дорожная карта, детальный план Фазы 1 |
| Июль 2025 | 2.0 | Актуализация: P0–P2 готовы, P6 частично. Добавлены раздел «0.1 Статус реализации», статусы в дорожной карте. Реализованы: режим «Изменить упражнение» (добавить/удалить подходы, заметки тренеру, флажок «изменено», дифф подходов с зачёркиванием удалённых), импорт программы «3 мес Подготовка на осень» как встроенный шаблон со скейлингом весов под максимумы (присед/жим/тяга) и выбором дней, подсобные упражнения в «папке», график «Прогноз по плану» (сплошная/пунктир), запрет двойного старта (409) и подтверждение старта не на сегодня. Новые поля моделей и `openpyxl` в зависимостях |
| Июль 2025 | 3.0 | **Доработка v3.0:** расширен режим тренера — подготовка плана заранее и видимость (`draft`/`published`, показ недель по одной), тренер выставляет тренировочные дни, real-time заполнение/подтверждение подходов тренером (`filled_by`/`coach_confirmed`); добавлены **кроссплатформенность с самого начала** (§12.1), **импорт по коду/ссылке** (§8.5), **система пропусков** (skip/missed/reschedule, §9.1) и **статистика отклонений от плана** (adherence, §9.2). Обновлены §0/§0.2, §2.3, §3.4, §4.11, §5.8, §6.4, §13 (фазы P2.1/CP) |
| Июнь 2026 | 3.2 | **Синхронизация статусов с фактическим кодом.** Отмечены как готовые: **P4** (real-time WebSocket co-scribe: `/api/ws`, ConnectionManager, `filled_by`/`coach_confirmed`, `useRealtime`), **обязательная аутентификация** (email/пароль bcrypt, Telegram HMAC, Google OAuth+Emergent, сессии `user_sessions`, Bearer `twb_token`), **закрытие IDOR** на всех `/sessions/*` и `/plans/*` (401/403), **по-подходное логирование** (`SetLog` + `/sessions/{id}/exercise/{order}/set/{index}`, таймер отдыха, настройки тренировки), **подтверждение тренером** и **старт тренировки тренером** (`sessions/start` c `coach_telegram_id`). Обновлены §0.1 и §13. Техническая карта кода — в `AI_CONTEXT.md` v4.0 |
