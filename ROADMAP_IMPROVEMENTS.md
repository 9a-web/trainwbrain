# TrainWBrain — Roadmap улучшений на основе анализа Fitness Friends

> Документ создан: 2026-09-03  
> На основе анализа: https://fitness-friend.ru

---

## 🎯 Стратегия улучшений

### Приоритизация по матрице Impact × Effort

| Приоритет | Фичи |
|-----------|------|
| **P0 (Критичные)** | Telegram уведомления, Live-статусы, История весов |
| **P1 (Высокий)** | Статистика по мышцам, Sliding session |
| **P2 (Средний)** | ИИ-генерация программ, Суперсеты |
| **P3 (Низкий)** | Визитка тренера, PWA, Рейтинг клиентов |

---

## 📋 PHASE 1: Критические улучшения (1-2 недели)

### 1.1 Telegram Bot Уведомления

**Проблема:** Клиенты забывают про тренировки, тренеры тратят время на напоминания  
**Решение:** Автоматические уведомления через Telegram Bot

**Функционал:**
- ✅ Напоминание о тренировке (за 2 часа до назначенного времени)
- ✅ Напоминание о заполнении ежедневного отчета (вечером)
- ✅ Поздравление с завершением тренировки
- ✅ Уведомление тренеру о новом клиенте
- ✅ Уведомление тренеру о завершенной тренировке клиента

**Файлы для создания:**
```
backend/
├── notifications.py         # Логика отправки уведомлений
├── scheduler.py            # Cron-задачи для проверки расписания
└── telegram_bot.py         # Инициализация бота (уже есть токен в .env)
```

**API endpoints:**
```python
POST /api/notifications/test/{telegram_id}  # Тестовая отправка
GET  /api/notifications/settings/{user_id}  # Настройки уведомлений
PATCH /api/notifications/settings/{user_id} # Обновить настройки
```

**DB Schema:**
```python
# Коллекция notification_settings
{
    "user_telegram_id": int,
    "workout_reminders": bool,  # default: true
    "report_reminders": bool,   # default: true
    "time_before_workout": int, # minutes, default: 120
    "report_reminder_time": str # "20:00"
}
```

**Эффект:** 8 из 10 клиентов будут присылать отчеты БЕЗ ручных напоминаний тренера

---

### 1.2 Live-статусы клиентов

**Проблема:** Тренер не видит текущую активность клиентов на одном экране  
**Решение:** Real-time индикаторы статуса

**Статусы:**
- 🟢 `on_workout` — клиент сейчас на тренировке
- ✅ `completed` — завершил тренировку сегодня
- ⏸️ `idle` — не начинал тренировку
- 🔴 `skipped` — пропустил запланированную тренировку

**Изменения в коде:**

**backend/models.py:**
```python
class WorkoutSession(BaseModel):
    # ...existing fields
    live_status: Literal["idle", "on_workout", "completed", "skipped"] = "idle"
    status_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

**backend/server.py:**
```python
# При старте тренировки:
await db.workout_sessions.update_one(
    {"_id": session_id},
    {
        "$set": {
            "live_status": "on_workout",
            "status_updated_at": datetime.now(timezone.utc)
        }
    }
)
# WebSocket broadcast тренеру
await manager.broadcast_to_room(f"coach_{coach_id}", {
    "type": "client_status_change",
    "athlete_telegram_id": athlete_tg,
    "status": "on_workout"
})
```

**frontend/src/pages/Coach.js:**
```jsx
// Добавить индикатор статуса рядом с именем клиента
<div className="client-status">
  {client.live_status === 'on_workout' && <span className="status-badge on-workout">🟢 На тренировке</span>}
  {client.live_status === 'completed' && <span className="status-badge completed">✅ Завершил</span>}
  {client.live_status === 'skipped' && <span className="status-badge skipped">🔴 Пропустил</span>}
</div>
```

**Дополнительно:**
- Автоматический перевод в `skipped` если тренировка не начата до конца дня (cron)
- Сброс статусов в `idle` в начале нового дня

**Эффект:** Тренер видит всех активных клиентов на одном экране без листания чатов

---

### 1.3 История весов в редакторе планов

**Проблема:** Тренер вручную вспоминает предыдущие веса клиента при создании программы  
**Решение:** Показывать историю выполнения упражнения прямо в редакторе

**API endpoint:**
```python
GET /api/exercises/{slug}/history/{athlete_tg}?limit=10

Response:
{
    "slug": "bench-press",
    "athlete_telegram_id": 123,
    "last_performed": "2026-08-30T18:30:00Z",
    "max_weight": 85.0,
    "history": [
        {
            "date": "2026-08-30",
            "sets": [
                {"weight": 80, "reps": 8, "completed": true},
                {"weight": 82.5, "reps": 6, "completed": true}
            ],
            "session_id": "abc123"
        },
        // ... до 10 последних
    ]
}
```

**Реализация в backend/server.py:**
```python
@api_router.get("/api/exercises/{slug}/history/{athlete_tg}")
async def get_exercise_history(
    slug: str,
    athlete_tg: int,
    limit: int = 10,
    caller: dict = Depends(require_auth)
):
    # Проверка прав (только тренер этого клиента)
    link = await db.coach_links.find_one({
        "coach_telegram_id": caller["telegram_id"],
        "athlete_telegram_id": athlete_tg
    })
    if not link:
        raise HTTPException(403, "Not your client")
    
    # Поиск сессий с этим упражнением
    sessions = await db.workout_sessions.find({
        "athlete_telegram_id": athlete_tg,
        "status": "finished",
        "exercises.slug": slug
    }).sort("finished_at", -1).limit(limit).to_list(limit)
    
    history = []
    max_weight = 0.0
    
    for s in sessions:
        for ex in s.get("exercises", []):
            if ex.get("slug") == slug:
                sets = ex.get("completed_sets", [])
                weights = [set.get("weight", 0) for set in sets if set.get("weight")]
                if weights:
                    max_weight = max(max_weight, max(weights))
                
                history.append({
                    "date": s["finished_at"].date().isoformat(),
                    "sets": sets,
                    "session_id": s["id"]
                })
    
    return {
        "slug": slug,
        "athlete_telegram_id": athlete_tg,
        "last_performed": sessions[0]["finished_at"] if sessions else None,
        "max_weight": max_weight,
        "history": history
    }
```

**Интеграция в frontend/src/pages/CoachPlanEditor.js:**
```jsx
// Кнопка рядом с упражнением
<button onClick={() => fetchExerciseHistory(exercise.slug, athleteId)}>
  📊 История
</button>

// Модальное окно с историей
<ExerciseHistoryModal 
  history={historyData}
  onSelectWeight={(weight) => setExerciseWeight(weight)}
/>
```

**Эффект:** Тренер видит прогрессию и назначает адекватные веса за 30 секунд вместо 5 минут

---

## 📊 PHASE 2: Аналитика и UX (2-3 недели)

### 2.1 Статистика по мышечным группам

**Проблема:** Нет визуализации дисбаланса нагрузки  
**Решение:** Карта нагрузки по мышцам за период

**Изменения в backend/models.py:**
```python
class Exercise(BaseModel):
    # ...existing fields
    muscle_groups: List[str] = []  # ["chest", "triceps", "shoulders"]
    secondary_groups: List[str] = []  # ["core"]
```

**Обновление seed_data (backend/seed_data/exercises.json):**
```json
{
    "slug": "bench-press",
    "name": "Жим штанги лежа",
    "muscle_groups": ["chest", "triceps"],
    "secondary_groups": ["shoulders"]
}
```

**API endpoint:**
```python
GET /api/stats/{athlete_tg}/muscle-groups?period=week|month|all

Response:
{
    "period": "week",
    "start_date": "2026-08-27",
    "end_date": "2026-09-03",
    "muscle_groups": {
        "chest": {"volume": 2400, "sessions": 2},
        "back": {"volume": 3200, "sessions": 2},
        "legs": {"volume": 4500, "sessions": 1},
        "shoulders": {"volume": 800, "sessions": 1},
        "biceps": {"volume": 600, "sessions": 1},
        "triceps": {"volume": 1200, "sessions": 2}
    },
    "imbalance_warning": "legs" // если нагрузка на 50%+ выше других
}
```

**Расчет volume:**
```python
volume = weight × reps × sets
```

**Визуализация (frontend):**
- Radial chart (круговая диаграмма по группам)
- Bar chart (столбцы объёма)
- Цветовая индикация дисбаланса

**Эффект:** Тренер сразу видит перекосы в программе и корректирует

---

### 2.2 Sliding Session (автообновление токена)

**Проблема:** Клиент выходит из системы после истечения токена  
**Решение:** Автоматическое продление при >50% TTL

**backend/auth.py:**
```python
def should_refresh_token(token: str) -> bool:
    """Проверка нужно ли обновить токен"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        iat = payload.get("iat")  # issued at
        exp = payload.get("exp")  # expires at
        now = datetime.now(timezone.utc).timestamp()
        
        ttl = exp - iat
        elapsed = now - iat
        
        # Если прошло >50% времени жизни
        return elapsed > (ttl * 0.5)
    except:
        return False

@api_router.post("/api/auth/refresh")
async def refresh_token(
    authorization: Optional[str] = Header(None),
    access_token: Optional[str] = Cookie(None)
):
    """Обновление токена"""
    token = authorization.replace("Bearer ", "") if authorization else access_token
    
    if not token:
        raise HTTPException(401, "No token provided")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        
        # Проверить что пользователь существует
        user = await db.users.find_one({"telegram_id": user_id})
        if not user:
            raise HTTPException(404, "User not found")
        
        # Создать новый токен с тем же TTL
        ttl = payload.get("exp") - payload.get("iat")
        new_token = create_access_token(user, ttl)
        
        return {"access_token": new_token}
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(401, "Invalid token")
```

**frontend/src/api.js:**
```javascript
// Перехватчик запросов
api.interceptors.request.use(async (config) => {
  const token = localStorage.getItem('auth_token');
  const tokenIssuedAt = localStorage.getItem('token_issued_at');
  
  if (token && tokenIssuedAt) {
    const now = Date.now();
    const elapsed = now - parseInt(tokenIssuedAt);
    const ttl = 24 * 60 * 60 * 1000; // 24 часа
    
    // Если прошло >50% времени
    if (elapsed > ttl * 0.5) {
      try {
        const response = await axios.post('/api/auth/refresh', {}, {
          headers: { Authorization: `Bearer ${token}` }
        });
        
        const newToken = response.data.access_token;
        localStorage.setItem('auth_token', newToken);
        localStorage.setItem('token_issued_at', now.toString());
        config.headers.Authorization = `Bearer ${newToken}`;
      } catch (error) {
        // Если refresh не удался — logout
        localStorage.clear();
        window.location.href = '/login';
      }
    }
  }
  
  return config;
});
```

**Эффект:** Пользователь никогда не вылетает из сессии во время активного использования

---

## 🤖 PHASE 3: AI и автоматизация (3-4 недели)

### 3.1 ИИ-генерация программ на основе истории

**Проблема:** Тренер тратит 30+ минут на составление персональной программы  
**Решение:** AI генерирует черновик за 30 секунд

**Workflow:**
1. Тренер выбирает клиента
2. Указывает цель (масса/сила/похудение/выносливость)
3. Указывает количество тренировок в неделю
4. AI генерирует программу с учётом:
   - Истории упражнений клиента
   - Последних рабочих весов
   - Проблемных зон (упражнения с регрессом)
   - Предпочтений (часто выполняемые упражнения)

**API endpoint:**
```python
POST /api/programs/ai-generate

Request:
{
    "athlete_telegram_id": 123,
    "goal": "strength",  // strength, hypertrophy, fat_loss, endurance
    "workouts_per_week": 3,
    "duration_weeks": 8,
    "focus_groups": ["legs", "back"]  // optional
}

Response:
{
    "program_id": "generated_abc123",
    "name": "Силовая программа 8 недель",
    "weeks": [
        {
            "week": 1,
            "workouts": [
                {
                    "name": "День 1: Ноги + Плечи",
                    "exercises": [
                        {
                            "slug": "squat",
                            "name": "Приседания",
                            "target_weight": 100,  // из истории
                            "sets": 4,
                            "reps": 6,
                            "rest_seconds": 180
                        },
                        // ...
                    ]
                }
            ]
        }
    ]
}
```

**Реализация:**
```python
@api_router.post("/api/programs/ai-generate")
async def ai_generate_program(
    req: ProgramGenerateReq,
    caller: dict = Depends(require_auth)
):
    # 1. Получить историю клиента
    history = await get_client_training_history(req.athlete_telegram_id, limit=50)
    
    # 2. Извлечь последние веса по упражнениям
    exercise_weights = {}
    for session in history:
        for ex in session.get("exercises", []):
            slug = ex.get("slug")
            sets = ex.get("completed_sets", [])
            weights = [s.get("weight") for s in sets if s.get("weight")]
            if weights:
                exercise_weights[slug] = max(weights)
    
    # 3. Найти проблемные зоны (регресс)
    weak_points = analyze_progression(history)
    
    # 4. Сформировать prompt для AI
    prompt = f"""
    Создай {req.duration_weeks}-недельную программу тренировок для клиента.
    
    Цель: {req.goal}
    Тренировок в неделю: {req.workouts_per_week}
    Фокус: {', '.join(req.focus_groups or [])}
    
    История клиента:
    - Последние рабочие веса: {json.dumps(exercise_weights, indent=2)}
    - Проблемные зоны: {', '.join(weak_points)}
    
    Требования:
    - Использовать упражнения из истории клиента где возможно
    - Ставить адекватные веса (± 5-10% от последних)
    - Прогрессия нагрузки по неделям
    - Баланс групп мышц
    
    Формат ответа: JSON с полями name, weeks[], workouts[], exercises[]
    """
    
    # 5. Вызов AI (используем существующий _call_ai)
    ai_response = await _call_ai([{"role": "user", "content": prompt}])
    
    # 6. Парсинг и валидация JSON
    program_data = json.loads(ai_response)
    
    # 7. Сохранить как draft
    program = await db.programs.insert_one({
        **program_data,
        "owner_telegram_id": caller["telegram_id"],
        "is_draft": True,
        "is_ai_generated": True,
        "created_at": datetime.now(timezone.utc)
    })
    
    return program_data
```

**Frontend интеграция:**
```jsx
// В CoachPlanEditor.js
<button onClick={handleAIGenerate}>
  ✨ Сгенерировать программу с AI
</button>

// После генерации — редактор с возможностью правки
<ProgramEditor program={aiGeneratedProgram} editable={true} />
```

**Эффект:** Тренер экономит 20-30 минут на каждой программе

---

### 3.2 Суперсеты

**Проблема:** Нельзя назначить упражнения без отдыха между ними  
**Решение:** Группировка упражнений в суперсеты

**DB Schema (обновление exercises в workout_sessions):**
```python
{
    "exercises": [
        {
            "superset_id": "ss_1",  // new field
            "superset_order": 1,    // new field
            "slug": "bench-press",
            "sets": 3,
            "reps": 8,
            // ...
        },
        {
            "superset_id": "ss_1",
            "superset_order": 2,
            "slug": "bent-over-row",
            "sets": 3,
            "reps": 8,
            "rest_after_superset": 120  // отдых после всех упражнений
        }
    ]
}
```

**Frontend:**
```jsx
// Визуализация суперсета
<div className="superset-container">
  <div className="superset-label">Суперсет A</div>
  <ExerciseCard exercise={exercise1} />
  <div className="superset-connector">↓ Без отдыха</div>
  <ExerciseCard exercise={exercise2} />
  <div className="rest-indicator">⏱️ Отдых 2:00</div>
</div>
```

**Эффект:** Экономия времени тренировки на 15-20%

---

## 🌟 PHASE 4: Маркетинг и рост (4+ недели)

### 4.1 Публичная визитка тренера

**Проблема:** Тренеру нужен лендинг для привлечения клиентов  
**Решение:** Автогенерация публичной страницы с кейсами

**URL:** `https://trainwbrain.com/coach/{username}`

**Содержимое:**
- Фото и био тренера
- Достижения (количество клиентов, тренировок)
- Кейсы (фото до/после клиентов с их разрешения)
- Отзывы клиентов
- Кнопка "Стать клиентом" → квиз

**API:**
```python
GET /api/coach/{username}/public-profile

Response:
{
    "username": "john_trainer",
    "first_name": "Иван",
    "bio": "Сертифицированный тренер...",
    "photo_url": "...",
    "stats": {
        "total_clients": 24,
        "total_workouts": 1240,
        "avg_rating": 4.8
    },
    "cases": [
        {
            "client_name": "Анна",
            "before_photo": "...",
            "after_photo": "...",
            "weight_lost": -12,
            "duration_weeks": 16,
            "testimonial": "Похудела на 12 кг..."
        }
    ]
}
```

**Эффект:** Тренер получает готовый инструмент для продаж

---

### 4.2 Рейтинг клиентов (геймификация)

**Проблема:** Клиенты теряют мотивацию  
**Решение:** Ежемесячная таблица лидеров

**Критерии:**
- Выполненные тренировки вовремя
- Заполненные отчёты
- Шаги/активность

**Коллекция:**
```python
# monthly_ratings
{
    "coach_telegram_id": 123,
    "month": "2026-09",
    "rankings": [
        {
            "athlete_telegram_id": 456,
            "score": 245,
            "workouts_completed": 12,
            "reports_filled": 28,
            "steps_total": 180000,
            "rank": 1
        }
    ]
}
```

**Эффект:** Повышение вовлечённости клиентов на 30%

---

### 4.3 PWA манифест

**Проблема:** Клиенты не устанавливают приложение  
**Решение:** Progressive Web App для установки на главный экран

**frontend/public/manifest.json:**
```json
{
  "name": "TrainWBrain",
  "short_name": "TWB",
  "description": "Твой тренер в телефоне",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#4F46E5",
  "icons": [
    {
      "src": "/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
```

**Эффект:** Установка как нативное приложение на iOS/Android

---

## 📈 Метрики успеха

### KPI после внедрения:

| Метрика | До | Цель | Измерение |
|---------|----|----|-----------|
| Время тренера на 1 клиента/день | ~60 мин | 41 мин | Логи действий |
| % клиентов с отчётами без напоминаний | 30% | 80% | DB queries |
| Время составления программы | 30 мин | 5 мин | User action tracking |
| Retention клиентов (30 дней) | ? | 85% | Cohort analysis |
| NPS тренеров | ? | 8+ | Surveys |

---

## 🛠️ Технический стек обновлений

**Backend:**
- `python-telegram-bot` — для уведомлений
- `APScheduler` — для cron-задач
- Расширение существующих коллекций MongoDB

**Frontend:**
- `recharts` — для графиков мышечных групп (уже есть)
- WebSocket подписки на live-статусы (уже есть `useRealtime`)
- Модальные окна для истории весов

**Инфраструктура:**
- Не требуется новых сервисов
- Всё работает в рамках существующего FastAPI + MongoDB

---

## ⏱️ Оценка времени

| Phase | Задачи | Время |
|-------|--------|-------|
| **P0** | Уведомления + Live-статусы + История весов | 1-2 недели |
| **P1** | Статистика мышц + Sliding session | 1 неделя |
| **P2** | ИИ-генерация + Суперсеты | 1-2 недели |
| **P3** | Визитка + Рейтинг + PWA | 2-3 недели |

**Итого:** 5-8 недель на полную реализацию

---

## 🚀 С чего начать

### Шаг 1: Telegram Bot уведомления (самый быстрый win)
- Создать `backend/notifications.py`
- Настроить scheduler
- Добавить настройки уведомлений в профиль

### Шаг 2: Live-статусы (визуальный эффект)
- Обновить модель `WorkoutSession`
- Добавить WebSocket события
- Обновить UI Coach.js

### Шаг 3: История весов (value для тренеров)
- Создать endpoint `/api/exercises/{slug}/history/{athlete_tg}`
- Интегрировать в CoachPlanEditor

---

**Статус документа:** 📝 Ready for implementation  
**Следующий шаг:** Начать с Phase 1.1 (Telegram Bot)
