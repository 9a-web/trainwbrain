# Инструкции по добавлению Live-статусов клиентов

## Что добавлено

В модель `WorkoutSession` (backend/models.py) добавлены поля:
```python
live_status: str = "idle"  # idle | on_workout | completed | skipped
status_updated_at: Optional[datetime] = Field(default_factory=_now)
```

---

## Интеграция в server.py

### 1. При старте тренировки (POST /api/sessions/start)

Найдите код создания новой сессии и добавьте:

```python
@api_router.post("/sessions/start")
async def start_session(...):
    # ...existing code...
    
    new_session = {
        # ...existing fields...
        "live_status": "on_workout",
        "status_updated_at": datetime.now(timezone.utc)
    }
    
    result = await db.workout_sessions.insert_one(new_session)
    
    # WebSocket broadcast тренеру
    if coach_telegram_id:
        await manager.broadcast_to_room(f"coach_{coach_telegram_id}", {
            "type": "client_status_change",
            "athlete_telegram_id": athlete_telegram_id,
            "status": "on_workout",
            "session_id": session_id
        })
    
    return {"success": True, "session_id": session_id}
```

### 2. При завершении тренировки (PATCH /api/sessions/{id}/finish)

```python
@api_router.patch("/sessions/{id}/finish")
async def finish_session(id: str, caller: dict = Depends(require_auth)):
    # ...existing code...
    
    await db.workout_sessions.update_one(
        {"id": id},
        {
            "$set": {
                "status": "finished",
                "live_status": "completed",
                "status_updated_at": datetime.now(timezone.utc),
                "finished_at": datetime.now(timezone.utc)
            }
        }
    )
    
    # WebSocket broadcast тренеру
    session = await db.workout_sessions.find_one({"id": id})
    if session and session.get("coach_telegram_id"):
        await manager.broadcast_to_room(f"coach_{session['coach_telegram_id']}", {
            "type": "client_status_change",
            "athlete_telegram_id": session["athlete_telegram_id"],
            "status": "completed",
            "session_id": id
        })
    
    return {"success": True}
```

### 3. Автоматическая проверка пропущенных тренировок

Добавьте cron-задачу в `scheduler.py`:

```python
async def update_skipped_workouts(db: AsyncIOMotorDatabase):
    """
    Обновляет live_status на 'skipped' для незавершенных тренировок.
    
    Запускается каждый день в конце дня (23:30).
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Найти все активные сессии за сегодня
    sessions = await db.workout_sessions.find({
        "started_at": {"$gte": today_start, "$lt": now},
        "status": "in_progress",
        "live_status": {"$ne": "completed"}
    }).to_list(1000)
    
    for session in sessions:
        # Обновить статус
        await db.workout_sessions.update_one(
            {"id": session["id"]},
            {
                "$set": {
                    "live_status": "skipped",
                    "status_updated_at": now
                }
            }
        )
        
        # WebSocket broadcast тренеру
        if session.get("coach_telegram_id"):
            await manager.broadcast_to_room(f"coach_{session['coach_telegram_id']}", {
                "type": "client_status_change",
                "athlete_telegram_id": session["athlete_telegram_id"],
                "status": "skipped",
                "session_id": session["id"]
            })
    
    return len(sessions)
```

Добавить в `init_scheduler()`:

```python
scheduler.add_job(
    func=update_skipped_workouts,
    trigger=CronTrigger(hour=23, minute=30, timezone="UTC"),
    args=[db],
    id="update_skipped_workouts",
    name="Обновление пропущенных тренировок",
    replace_existing=True
)
```

### 4. Сброс статусов в начале нового дня

```python
async def reset_daily_statuses(db: AsyncIOMotorDatabase):
    """
    Сбрасывает live_status в 'idle' для всех пользователей.
    
    Запускается каждый день в 00:01.
    """
    result = await db.workout_sessions.update_many(
        {"live_status": {"$in": ["completed", "skipped"]}},
        {
            "$set": {
                "live_status": "idle",
                "status_updated_at": datetime.now(timezone.utc)
            }
        }
    )
    
    return result.modified_count
```

Добавить в `init_scheduler()`:

```python
scheduler.add_job(
    func=reset_daily_statuses,
    trigger=CronTrigger(hour=0, minute=1, timezone="UTC"),
    args=[db],
    id="reset_daily_statuses",
    name="Сброс ежедневных статусов",
    replace_existing=True
)
```

---

## API endpoint для получения live-статусов клиентов

Добавьте в `server.py`:

```python
@api_router.get("/coach/{coach_tg}/clients/live-status")
async def get_clients_live_status(
    coach_tg: int,
    caller: dict = Depends(require_auth)
):
    """Получить live-статусы всех клиентов тренера"""
    # Проверка прав
    if caller["telegram_id"] != coach_tg:
        raise HTTPException(403, "Access denied")
    
    # Получить всех клиентов
    links = await db.coach_links.find({"coach_telegram_id": coach_tg}).to_list(1000)
    athlete_ids = [link["athlete_telegram_id"] for link in links]
    
    # Получить статусы
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    statuses = []
    for athlete_id in athlete_ids:
        # Найти последнюю сессию за сегодня
        session = await db.workout_sessions.find_one(
            {
                "athlete_telegram_id": athlete_id,
                "started_at": {"$gte": today_start}
            },
            sort=[("started_at", -1)]
        )
        
        if session:
            status = session.get("live_status", "idle")
        else:
            status = "idle"
        
        # Получить имя спортсмена
        user = await db.users.find_one({"telegram_id": athlete_id})
        
        statuses.append({
            "athlete_telegram_id": athlete_id,
            "first_name": user.get("first_name") if user else "Unknown",
            "live_status": status,
            "last_updated": session.get("status_updated_at").isoformat() if session and session.get("status_updated_at") else None
        })
    
    return {"clients": statuses}
```

---

## Frontend интеграция (React)

### 1. Обновить `frontend/src/pages/Coach.js`

```jsx
import { useRealtime } from '../hooks/useRealtime';
import { useState, useEffect } from 'react';

function Coach() {
  const [clients, setClients] = useState([]);
  const { subscribe } = useRealtime();
  
  useEffect(() => {
    // Загрузить начальные статусы
    fetchClientStatuses();
    
    // Подписаться на обновления через WebSocket
    const unsubscribe = subscribe('client_status_change', (event) => {
      setClients(prev => prev.map(client => 
        client.athlete_telegram_id === event.athlete_telegram_id
          ? { ...client, live_status: event.status }
          : client
      ));
    });
    
    return () => unsubscribe();
  }, []);
  
  const fetchClientStatuses = async () => {
    const response = await api.get(`/coach/${currentUser.telegram_id}/clients/live-status`);
    setClients(response.data.clients);
  };
  
  const getStatusBadge = (status) => {
    switch (status) {
      case 'on_workout':
        return <span className="badge badge-success">🟢 На тренировке</span>;
      case 'completed':
        return <span className="badge badge-info">✅ Завершил</span>;
      case 'skipped':
        return <span className="badge badge-danger">🔴 Пропустил</span>;
      default:
        return <span className="badge badge-secondary">⏸️ Ожидает</span>;
    }
  };
  
  return (
    <div>
      <h1>Мои клиенты</h1>
      <div className="clients-list">
        {clients.map(client => (
          <div key={client.athlete_telegram_id} className="client-card">
            <h3>{client.first_name}</h3>
            {getStatusBadge(client.live_status)}
          </div>
        ))}
      </div>
    </div>
  );
}
```

### 2. Добавить стили в `Coach.css`

```css
.badge {
  display: inline-block;
  padding: 0.25rem 0.6rem;
  font-size: 0.85rem;
  font-weight: 600;
  border-radius: 0.5rem;
  margin-left: 0.5rem;
}

.badge-success {
  background-color: #22c55e;
  color: white;
}

.badge-info {
  background-color: #3b82f6;
  color: white;
}

.badge-danger {
  background-color: #ef4444;
  color: white;
}

.badge-secondary {
  background-color: #6b7280;
  color: white;
}

.client-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  margin-bottom: 0.5rem;
}

.client-card:hover {
  background-color: #f9fafb;
  cursor: pointer;
}
```

---

## Тестирование

### 1. Запустить тренировку

```bash
curl -X POST http://localhost:8000/api/sessions/start \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "plan123",
    "athlete_telegram_id": 123456,
    "week": 1,
    "day": 1
  }'
```

Проверить что `live_status` = `"on_workout"`.

### 2. Завершить тренировку

```bash
curl -X PATCH http://localhost:8000/api/sessions/{session_id}/finish \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Проверить что `live_status` = `"completed"`.

### 3. Проверить статусы в UI

Открыть страницу тренера → должны быть видны цветные бейджи со статусами.

---

## Готово! 🎯

Теперь тренер видит в реальном времени:
- 🟢 Кто сейчас на тренировке
- ✅ Кто завершил тренировку
- 🔴 Кто пропустил
- ⏸️ Кто ещё не начинал

Обновления приходят через WebSocket без перезагрузки страницы.
