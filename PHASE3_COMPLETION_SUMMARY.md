# ✅ Итоговый отчёт: Фаза 3 завершена — Кардио-модуль

**Дата:** 2026-10-10
**План:** `planTrainWBrain.md` §6, Фаза 3
**Статус:** реализовано, покрыто тестами и проверено против живого backend

---

## 🎯 DoD Фазы 3

| Критерий | Статус | Доказательство |
|---|---|---|
| Ручной ввод кардио работает | ✅ | E2E `backend_test_cardio.py` (29/29 PASS) |
| Фото-парсинг консоли работает | ✅ | `POST /cardio/parse-photo` → vision → черновик + валидация; без ключа Gemini — понятная 503 |
| Цели по кардио видны атлету | ✅ | виджет на Home, экран `/cardio`, блок в `Stats.js` |
| Цели по кардио видны тренеру | ✅ | блок в `CoachClient.js` + `CardioStatsCard` в статистике подопечного |
| Агрегаты корректны | ✅ | minutes/sessions/km/kcal/by_type/weekly_target/compliance проверены вручную и E2E |
| Тесты калькулятора калорий и валидации | ✅ | `tests/unit/test_cardio.py` (19 тестов) |

---

## Backend

### `models.py`
- `CardioSession` — документ коллекции `cardio_sessions` (§4.2 плана) со всеми полями:
  `type`, `duration_sec`, `distance_km`, `avg_hr`/`max_hr`, `calories`, `intensity`, `rpe`,
  `incline_percent`, `avg_speed_kmh`, `avg_pace`, `notes`, `photo_ref`, `source`,
  `coach_telegram_id`.
- `CardioCreateReq` (создание и PATCH), `CardioPhotoReq`.
- Константы `CARDIO_TYPES`, `CARDIO_INTENSITIES`, `CARDIO_SOURCES`.

### `server.py` — эндпоинты (все с `Depends(get_current_user)`)
| Метод | Путь | Доступ |
|---|---|---|
| POST | `/cardio` | владелец (нужно `permissions.log_cardio`) или тренер за подопечного |
| GET | `/cardio?athlete=&from=&to=&limit=` | владелец или активный тренер (`_assert_can_read_stats`) |
| PATCH | `/cardio/{id}` | владелец или тренер |
| DELETE | `/cardio/{id}` | владелец или тренер |
| POST | `/cardio/parse-photo` | self-fill + `_rate_limit` (20/10 мин) |
| GET | `/stats/{tg}/cardio?period=` | владелец или активный тренер |

### Чистые хелперы (покрыты offline unit-тестами)
- `cardio_met(type, intensity)` — MET по Compendium of Physical Activities.
- `cardio_kcal(type, intensity, weight_kg, duration_sec)` — `kcal = MET × 3.5 × кг / 200 × мин`.
- `_parse_hhmmss_pace()` / `_avg_speed_kmh()` — производные темп и скорость.
- `_clean_cardio_payload(payload, partial)` — единый валидатор для POST/PATCH/vision:
  `duration_sec > 0` (макс 12 ч), `0 ≤ distance_km ≤ 500`, `avg_hr/max_hr 30..230`,
  `rpe 1..10`, `calories 0..20000`, `incline 0..40%`, `speed 0..60 км/ч`, ISO-даты,
  отсечение `NaN/Inf`, обрезка заметок до 1000 символов.
- `_athlete_cardio_stats()` — агрегат за период + норма текущей календарной недели (пн–вс).
- `_cardio_weekly_target()` — недельная норма из `goals (type=cardio_minutes, period=weekly, status=active)`;
  коллекции `goals` ещё нет (Фаза 4) — чтение защитное, `None` не ломает модуль.

### Особенности реализации
- **Калории:** если не переданы — считаются по MET с весом из `body_metrics` (fallback 75 кг).
- **Производные поля:** `avg_pace` и `avg_speed_kmh` считаются при создании и **пересчитываются при PATCH**,
  если изменили дистанцию/время; калории пересчитываются при смене длительности/интенсивности/типа.
- **PATCH использует `exclude_unset`** — иначе дефолт Pydantic `type="treadmill"` молча перетирал бы данные,
  а пустой запрос возвращал бы 200 вместо 400. Явный `null` очищает необязательные поля
  (`CARDIO_NULLABLE`) — например, смена дорожки на вело убирает наклон.
- **Права:** `_assert_can_log_permission()` — зеркало `_assert_can_selffill_strength`;
  managed-атлет без `log_cardio` получает 403, но просмотр (`view_cardio`) остаётся.
- **IDOR:** чужой атлет → 403; тренерская запись помечается `coach_telegram_id`.

---

## Frontend

| Файл | Что сделано |
|---|---|
| `pages/Cardio.js` (372 стр.) + `Cardio.css` | список сессий, hero с минутами за неделю и нормой, график по дням (recharts, 7/30 дней), кнопка «Добавить по фото консоли», правка/удаление, скелетон/пусто/ошибка |
| `components/CardioForm.js` + `.css` | форма создания и правки: 6 типов, дата, длительность, дистанция, пульс, калории, RPE, наклон (только дорожка/ходьба), интенсивность, заметка; живой предпросмотр темпа; клиентская валидация |
| `App.js` | маршрут `/cardio` + виджет «Кардио за неделю» на Home с прогресс-баром нормы |
| `App.css` | стили виджета `.cardio-widget` |
| `pages/Stats.js` + `Stats.css` | `CardioStatsCard` — период 7/30 дней, норма и её выполнение, KPI (минуты/сессии/км/ккал), разбивка по типам; подключён и для атлета, и для подопечного у тренера |
| `pages/CoachClient.js` + `Coach.css` | блок «Кардио за неделю» с бейджем «норма выполнена/не выполнена», прогресс-баром и KPI |
| `api.js` | `createCardio`, `listCardio`, `patchCardio`, `deleteCardio`, `getCardioStats`, `parseCardioPhoto` (multipart) |

Все интерактивные элементы имеют `data-testid` в kebab-case
(`cardio-page`, `cardio-add`, `cardio-photo-btn`, `cardio-type-*`, `cardio-save`, `cardio-modal`,
`home-cardio-widget`, `coach-cardio-block`, `cardio-summary` и т.д.).

---

## Тесты и проверка

```
backend/tests/unit/test_cardio.py .................... 19 passed
backend/tests/unit (всего) ............................ 81 passed
backend/tests/integration/backend_test_cardio.py ...... 29 PASS / 0 FAIL
backend/tests/integration/backend_test_cardio_perms.py  10 PASS / 0 FAIL
frontend: yarn build ................................. Compiled (только 2 ранее существовавших eslint-warning)
```

`backend_test_cardio.py` создаёт тестового пользователя сам (можно передать готовый токен аргументом).
Покрыто: создание, список, агрегаты, 5 сценариев валидации (400), PATCH, пустой PATCH (400), IDOR (403), DELETE, повторный DELETE (404).
`backend_test_cardio_perms.py`: запись тренером за подопечного, чтение тренером, 403 постороннему,
403 атлету без `log_cardio`, разрешённый просмотр, 200 после выдачи права, 403 не-тренеру.

Проверено вручную против живого backend: пересчёт темпа/скорости/калорий после PATCH,
смена типа с очисткой наклона, норма 150 мин → `compliance` 0.0 → 0.667, graceful `None` без цели.

---

## Отклонения от плана (осознанные)

1. **Карточка в `DiaryHome`** не добавлена — дневник временно скрыт по запросу владельца
   (переключатель режимов убран, Home всегда в режиме «План»). Карточка есть на Home.
2. **Уведомление при недоборе кардио** отложено в Фазу 6 — план сам относит
   «напоминание о кардио» к блоку уведомлений Фазы 6.
3. **`weekly_target`** читается из `goals`, которая появится в Фазе 4. До этого норма
   возвращается как `null`, и UI корректно показывает состояние «норма не задана».

---

## Следующая фаза

**Фаза 4 — Единый дневник, цели и прогноз нагрузки:** `GET /diary/timeline` (силовые + кардио + питание),
CRUD `/goals` и `/goals/progress`, `/body-metrics`, `GET /stats/{tg}/forecast` (регрессия e1RM по Эпли),
`POST /stats/{tg}/forecast/explain` (ИИ-комментарий), детектор делоуда; фронт —
`pages/Goals.js`, `components/ForecastChart.js`, блок «Прогноз» в `Stats.js`.
