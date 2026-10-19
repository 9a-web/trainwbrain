# Инструкции по интеграции системы уведомлений

## Шаг 1: Добавить импорты в server.py

Добавьте в начало файла `backend/server.py` (после существующих импортов):

```python
# Система уведомлений
from scheduler import init_scheduler, start_scheduler, stop_scheduler, get_scheduler_status
from notifications import (
    get_notification_settings,
    notify_coach_on_workout_complete,
    notify_coach_on_new_client
)
from telegram_bot import send_test_message, get_bot_info
```

---

## Шаг 2: Инициализировать scheduler в startup

Найдите функцию `@app.on_event("startup")` и добавьте в конец:

```python
@app.on_event("startup")
async def startup_seed():
    """Идемпотентно создаёт индексы и встроенные данные"""
    # ...existing code...
    
    # Инициализация планировщика уведомлений
    try:
        init_scheduler(db)
        start_scheduler()
        logger.info("Notification scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
```

---

## Шаг 3: Остановить scheduler при shutdown

Добавьте новый event handler после `startup_seed`:

```python
@app.on_event("shutdown")
async def shutdown_scheduler():
    """Graceful shutdown планировщика"""
    try:
        stop_scheduler()
        logger.info("Notification scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
```

---

## Шаг 4: Добавить API endpoints для уведомлений

Добавьте в конец файла `server.py` (перед `app.include_router(api_router, prefix="/api")`):

```python
# ============================================================================
# NOTIFICATIONS API
# ============================================================================

class NotificationSettings(BaseModel):
    """Настройки уведомлений пользователя"""
    workout_reminders: bool = True
    report_reminders: bool = True
    achievement_notifications: bool = True
    coach_notifications: bool = True
    time_before_workout_minutes: int = 120
    report_reminder_time: str = "20:00"
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "08:00"


@api_router.get("/notifications/settings")
async def get_user_notification_settings(caller: dict = Depends(require_auth)):
    """Получить настройки уведомлений текущего пользователя"""
    settings = await get_notification_settings(db, caller["telegram_id"])
    return settings


@api_router.patch("/notifications/settings")
async def update_notification_settings(
    updates: NotificationSettings,
    caller: dict = Depends(require_auth)
):
    """Обновить настройки уведомлений"""
    user_tg = caller["telegram_id"]
    
    update_dict = updates.model_dump()
    update_dict["user_telegram_id"] = user_tg
    update_dict["updated_at"] = datetime.now(timezone.utc)
    
    await db.notification_settings.update_one(
        {"user_telegram_id": user_tg},
        {"$set": update_dict},
        upsert=True
    )
    
    return {"success": True, "settings": update_dict}


@api_router.post("/notifications/test")
async def send_test_notification(caller: dict = Depends(require_auth)):
    """Отправить тестовое уведомление (проверка работы бота)"""
    user_tg = caller["telegram_id"]
    
    success = await send_test_message(user_tg)
    
    if success:
        return {"success": True, "message": "Тестовое уведомление отправлено"}
    else:
        raise HTTPException(500, "Не удалось отправить уведомление. Проверьте TELEGRAM_BOT_TOKEN")


@api_router.get("/notifications/bot-info")
async def get_telegram_bot_info(caller: dict = Depends(require_auth)):
    """Получить информацию о боте"""
    info = await get_bot_info()
    
    if info:
        return {
            "bot_username": info.get("username"),
            "bot_name": info.get("first_name"),
            "bot_id": info.get("id")
        }
    else:
        raise HTTPException(500, "Не удалось получить информацию о боте")


@api_router.get("/notifications/scheduler-status")
async def get_notification_scheduler_status(caller: dict = Depends(require_auth)):
    """Получить статус планировщика (только для тренеров)"""
    # Опционально: добавить проверку что caller - тренер
    status = get_scheduler_status()
    return status
```

---

## Шаг 5: Интегрировать уведомления в существующие endpoints

### 5.1 Уведомление при завершении тренировки

Найдите endpoint `PATCH /api/sessions/{id}/finish` и добавьте после обновления статуса:

```python
@api_router.patch("/sessions/{id}/finish")
async def finish_session(...):
    # ...existing code для обновления сессии...
    
    # Отправить уведомление тренеру
    try:
        await notify_coach_on_workout_complete(db, session_id, caller["telegram_id"])
    except Exception as e:
        logger.warning(f"Failed to notify coach: {e}")
    
    return {"success": True, ...}
```

### 5.2 Уведомление при добавлении нового клиента

Найдите endpoint `POST /api/coach/clients/add` (или аналогичный) и добавьте:

```python
@api_router.post("/coach/clients/add")
async def add_client(...):
    # ...existing code для создания coach_link...
    
    # Отправить уведомление тренеру
    try:
        await notify_coach_on_new_client(db, coach_telegram_id, athlete_telegram_id)
    except Exception as e:
        logger.warning(f"Failed to notify coach about new client: {e}")
    
    return {"success": True, ...}
```

---

## Шаг 6: Создать индексы для новых коллекций

Добавьте в `backend/seed.py` в функцию `ensure_indexes()`:

```python
async def ensure_indexes(db) -> None:
    """Создаёт индексы (идемпотентно)."""
    # ...existing indexes...
    
    # Индексы для системы уведомлений
    await db.notification_settings.create_index("user_telegram_id", unique=True)
    await db.notification_log.create_index([("user_telegram_id", 1), ("sent_at", -1)])
    await db.notification_log.create_index("sent_at")  # для cleanup
```

---

## Шаг 7: Обновить .env (ВАЖНО!)

Убедитесь что в `backend/.env` указан **НОВЫЙ** токен бота (старый нужно отозвать):

```env
TELEGRAM_BOT_TOKEN=your_new_bot_token_here
```

Получить новый токен: https://t.me/BotFather → `/newbot`

---

## Шаг 8: Установить зависимости и запустить

```bash
cd backend
pip install -r requirements.txt
python server.py
```

Проверить что scheduler запустился:
- Смотрите в логах: `"Notification scheduler started successfully"`
- Проверьте endpoint: `GET /api/notifications/scheduler-status`

---

## Шаг 9: Тестирование

### Тест 1: Отправка тестового уведомления
```bash
curl -X POST http://localhost:8000/api/notifications/test \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Должно прийти сообщение в Telegram.

### Тест 2: Обновление настроек
```bash
curl -X PATCH http://localhost:8000/api/notifications/settings \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workout_reminders": true,
    "time_before_workout_minutes": 60
  }'
```

### Тест 3: Проверка планировщика
```bash
curl http://localhost:8000/api/notifications/scheduler-status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Должны быть 4 задачи: `notify_upcoming_workouts`, `notify_daily_reports`, `check_skipped_workouts`, `cleanup_notification_logs`.

---

## Готово! 🎉

Система уведомлений интегрирована. Клиенты будут получать:
- ✅ Напоминания о тренировках (за 2 часа)
- ✅ Напоминания о заполнении отчетов (в 20:00)
- ✅ Поздравления с достижениями

Тренеры будут получать:
- ✅ Уведомления о завершенных тренировках
- ✅ Уведомления о пропущенных тренировках (в 23:00)
- ✅ Уведомления о новых клиентах

---

## Troubleshooting

### Проблема: Уведомления не приходят

**Проверка 1:** Бот запущен?
```bash
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

**Проверка 2:** Пользователь начал диалог с ботом?
- Пользователь должен найти бота по username и нажать `/start`
- Без этого бот не может отправлять сообщения

**Проверка 3:** Планировщик работает?
```bash
GET /api/notifications/scheduler-status
```

### Проблема: Scheduler не запускается

Проверьте логи на ошибки импорта. Убедитесь что `APScheduler==3.10.4` установлен:
```bash
pip list | grep APScheduler
```

### Проблема: Уведомления приходят не вовремя

Проверьте timezone. Все времена в UTC. Для локального времени нужно конвертировать в CronTrigger.
