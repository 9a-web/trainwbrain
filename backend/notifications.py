"""
Система уведомлений для TrainWBrain.

Логика определения когда и кому отправлять уведомления.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

from telegram_bot import (
    send_workout_reminder,
    send_report_reminder,
    send_workout_completed_notification,
    send_new_client_notification,
    send_workout_skipped_notification,
    send_congratulations,
    send_streak_milestone
)

logger = logging.getLogger(__name__)


async def get_notification_settings(db: AsyncIOMotorDatabase, user_telegram_id: int) -> Dict:
    """
    Получить настройки уведомлений пользователя.
    
    Если настройки не найдены, возвращает дефолтные значения.
    """
    settings = await db.notification_settings.find_one({"user_telegram_id": user_telegram_id})
    
    if not settings:
        # Дефолтные настройки
        return {
            "user_telegram_id": user_telegram_id,
            "workout_reminders": True,
            "report_reminders": True,
            "achievement_notifications": True,
            "coach_notifications": True,
            "time_before_workout_minutes": 120,  # за 2 часа
            "report_reminder_time": "20:00",
            "quiet_hours_enabled": False,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00"
        }
    
    return settings


async def should_send_notification(settings: Dict, notification_type: str) -> bool:
    """
    Проверка разрешено ли отправлять уведомление данного типа.
    """
    type_mapping = {
        "workout_reminder": "workout_reminders",
        "report_reminder": "report_reminders",
        "achievement": "achievement_notifications",
        "coach": "coach_notifications"
    }
    
    setting_key = type_mapping.get(notification_type)
    if not setting_key:
        return True
    
    return settings.get(setting_key, True)


async def is_quiet_hours(settings: Dict) -> bool:
    """
    Проверка находимся ли в тихих часах.
    """
    if not settings.get("quiet_hours_enabled", False):
        return False
    
    now = datetime.now(timezone.utc)
    current_time = now.strftime("%H:%M")
    
    start = settings.get("quiet_hours_start", "22:00")
    end = settings.get("quiet_hours_end", "08:00")
    
    # Обработка случая когда диапазон переходит через полночь
    if start > end:
        return current_time >= start or current_time <= end
    else:
        return start <= current_time <= end


async def notify_upcoming_workouts(db: AsyncIOMotorDatabase) -> int:
    """
    Проверяет запланированные тренировки и отправляет напоминания.
    
    Вызывается каждые 15 минут через scheduler.
    
    Returns:
        Количество отправленных уведомлений
    """
    sent_count = 0
    now = datetime.now(timezone.utc)
    
    # Получить все активные планы
    plans = await db.plans.find({"status": "active"}).to_list(1000)
    
    for plan in plans:
        athlete_tg = plan.get("athlete_telegram_id")
        if not athlete_tg:
            continue
        
        # Получить настройки уведомлений
        settings = await get_notification_settings(db, athlete_tg)
        
        if not await should_send_notification(settings, "workout_reminder"):
            continue
        
        if await is_quiet_hours(settings):
            continue
        
        # Время до тренировки
        time_before = settings.get("time_before_workout_minutes", 120)
        target_time = now + timedelta(minutes=time_before)
        
        # Проверить есть ли тренировка в это время
        # Логика зависит от типа расписания плана
        schedule = plan.get("schedule", {})
        schedule_type = schedule.get("type")
        
        workout_name = None
        scheduled_time = None
        
        if schedule_type == "days_of_week":
            # Проверить день недели
            target_weekday = target_time.weekday()  # 0=Monday
            days = schedule.get("days", [])
            
            if target_weekday in days:
                # Есть тренировка в этот день
                workout_name = plan.get("name", "Тренировка")
                scheduled_time = schedule.get("time")  # если указано время
        
        elif schedule_type == "calendar":
            # Проверить конкретную дату
            dates = schedule.get("dates", [])
            target_date_str = target_time.date().isoformat()
            
            if target_date_str in dates:
                workout_name = plan.get("name", "Тренировка")
        
        elif schedule_type == "any_day":
            # Для "любой день" не отправляем автонапоминания
            pass
        
        if workout_name:
            # Проверить не было ли уже отправлено напоминание сегодня
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            existing = await db.notification_log.find_one({
                "user_telegram_id": athlete_tg,
                "type": "workout_reminder",
                "plan_id": plan["id"],
                "sent_at": {"$gte": today_start}
            })
            
            if not existing:
                success = await send_workout_reminder(
                    athlete_tg,
                    workout_name,
                    scheduled_time
                )
                
                if success:
                    # Записать в лог
                    await db.notification_log.insert_one({
                        "user_telegram_id": athlete_tg,
                        "type": "workout_reminder",
                        "plan_id": plan["id"],
                        "sent_at": now,
                        "success": True
                    })
                    sent_count += 1
                    logger.info(f"Sent workout reminder to {athlete_tg} for '{workout_name}'")
    
    return sent_count


async def notify_daily_reports(db: AsyncIOMotorDatabase) -> int:
    """
    Напоминания о заполнении ежедневных отчетов.
    
    Вызывается каждый вечер в указанное время через scheduler.
    
    Returns:
        Количество отправленных уведомлений
    """
    sent_count = 0
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Получить всех активных спортсменов
    links = await db.coach_links.find({}).to_list(10000)
    
    athlete_ids = list(set([link["athlete_telegram_id"] for link in links]))
    
    for athlete_tg in athlete_ids:
        # Получить настройки
        settings = await get_notification_settings(db, athlete_tg)
        
        if not await should_send_notification(settings, "report_reminder"):
            continue
        
        if await is_quiet_hours(settings):
            continue
        
        # Проверить заполнен ли отчет за сегодня
        # (Предполагается что есть коллекция daily_reports)
        report = await db.daily_reports.find_one({
            "athlete_telegram_id": athlete_tg,
            "date": today_start
        })
        
        if report and report.get("is_filled"):
            # Отчет уже заполнен
            continue
        
        # Проверить не было ли уже напоминание сегодня
        existing = await db.notification_log.find_one({
            "user_telegram_id": athlete_tg,
            "type": "report_reminder",
            "sent_at": {"$gte": today_start}
        })
        
        if not existing:
            # Получить имя спортсмена
            user = await db.users.find_one({"telegram_id": athlete_tg})
            athlete_name = user.get("first_name", "Атлет") if user else "Атлет"
            
            success = await send_report_reminder(athlete_tg, athlete_name)
            
            if success:
                await db.notification_log.insert_one({
                    "user_telegram_id": athlete_tg,
                    "type": "report_reminder",
                    "sent_at": now,
                    "success": True
                })
                sent_count += 1
                logger.info(f"Sent report reminder to {athlete_tg}")
    
    return sent_count


async def notify_coach_on_workout_complete(
    db: AsyncIOMotorDatabase,
    session_id: str,
    athlete_telegram_id: int
) -> bool:
    """
    Уведомление тренеру о завершении тренировки клиентом.
    
    Вызывается из endpoint PATCH /api/sessions/{id}/finish
    """
    # Получить сессию
    session = await db.workout_sessions.find_one({"id": session_id})
    if not session:
        return False
    
    # Получить план
    plan_id = session.get("plan_id")
    if not plan_id:
        return False
    
    plan = await db.plans.find_one({"id": plan_id})
    if not plan:
        return False
    
    coach_tg = plan.get("coach_telegram_id")
    if not coach_tg:
        return False
    
    # Получить настройки тренера
    settings = await get_notification_settings(db, coach_tg)
    
    if not await should_send_notification(settings, "coach"):
        return False
    
    # Получить имя спортсмена
    athlete = await db.users.find_one({"telegram_id": athlete_telegram_id})
    athlete_name = athlete.get("first_name", "Спортсмен") if athlete else "Спортсмен"
    
    workout_name = plan.get("name", "Тренировка")
    # finished_at хранится ISO-строкой; telegram_bot вызывает .strftime(),
    # поэтому приводим к datetime (иначе уведомление тренеру не уходит).
    completion_time = session.get("finished_at") or datetime.now(timezone.utc)
    if isinstance(completion_time, str):
        try:
            completion_time = datetime.fromisoformat(completion_time)
        except ValueError:
            completion_time = datetime.now(timezone.utc)
    
    success = await send_workout_completed_notification(
        coach_tg,
        athlete_name,
        workout_name,
        completion_time
    )
    
    if success:
        logger.info(f"Notified coach {coach_tg} about workout completion by {athlete_telegram_id}")
    
    return success


async def notify_coach_on_new_client(
    db: AsyncIOMotorDatabase,
    coach_telegram_id: int,
    athlete_telegram_id: int
) -> bool:
    """
    Уведомление тренеру о новом клиенте.
    
    Вызывается при создании coach_link.
    """
    settings = await get_notification_settings(db, coach_telegram_id)
    
    if not await should_send_notification(settings, "coach"):
        return False
    
    # Получить имя спортсмена
    athlete = await db.users.find_one({"telegram_id": athlete_telegram_id})
    athlete_name = athlete.get("first_name", "Новый клиент") if athlete else "Новый клиент"
    
    success = await send_new_client_notification(
        coach_telegram_id,
        athlete_name,
        athlete_telegram_id
    )
    
    if success:
        logger.info(f"Notified coach {coach_telegram_id} about new client {athlete_telegram_id}")
    
    return success


async def check_and_notify_skipped_workouts(db: AsyncIOMotorDatabase) -> int:
    """
    Проверяет пропущенные тренировки и уведомляет тренеров.
    
    Вызывается в конце дня (23:00) через scheduler.
    
    Returns:
        Количество отправленных уведомлений
    """
    sent_count = 0
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    # Получить все активные планы
    plans = await db.plans.find({"status": "active"}).to_list(1000)
    
    for plan in plans:
        athlete_tg = plan.get("athlete_telegram_id")
        coach_tg = plan.get("coach_telegram_id")
        
        if not athlete_tg or not coach_tg:
            continue
        
        # Проверить была ли тренировка запланирована на сегодня
        schedule = plan.get("schedule", {})
        schedule_type = schedule.get("type")
        
        was_scheduled = False
        
        if schedule_type == "days_of_week":
            today_weekday = now.weekday()
            days = schedule.get("days", [])
            was_scheduled = today_weekday in days
        
        elif schedule_type == "calendar":
            today_date = now.date().isoformat()
            dates = schedule.get("dates", [])
            was_scheduled = today_date in dates
        
        if not was_scheduled:
            continue
        
        # Проверить была ли выполнена тренировка
        session = await db.workout_sessions.find_one({
            "athlete_telegram_id": athlete_tg,
            "plan_id": plan["id"],
            "started_at": {"$gte": today_start, "$lt": today_end},
            "status": "finished"
        })
        
        if session:
            # Тренировка была выполнена
            continue
        
        # Тренировка пропущена — уведомить тренера
        settings = await get_notification_settings(db, coach_tg)
        
        if not await should_send_notification(settings, "coach"):
            continue
        
        # Проверить не было ли уже уведомления
        existing = await db.notification_log.find_one({
            "user_telegram_id": coach_tg,
            "type": "workout_skipped",
            "athlete_telegram_id": athlete_tg,
            "plan_id": plan["id"],
            "sent_at": {"$gte": today_start}
        })
        
        if existing:
            continue
        
        # Получить имя спортсмена
        athlete = await db.users.find_one({"telegram_id": athlete_tg})
        athlete_name = athlete.get("first_name", "Спортсмен") if athlete else "Спортсмен"
        
        workout_name = plan.get("name", "Тренировка")
        
        success = await send_workout_skipped_notification(
            coach_tg,
            athlete_name,
            workout_name
        )
        
        if success:
            await db.notification_log.insert_one({
                "user_telegram_id": coach_tg,
                "type": "workout_skipped",
                "athlete_telegram_id": athlete_tg,
                "plan_id": plan["id"],
                "sent_at": now,
                "success": True
            })
            sent_count += 1
            logger.info(f"Notified coach {coach_tg} about skipped workout by {athlete_tg}")
    
    return sent_count


async def check_and_notify_streaks(db: AsyncIOMotorDatabase) -> int:
    """
    Проверяет серии тренировок и отправляет поздравления.
    
    Вызывается после завершения тренировки.
    
    Returns:
        Количество отправленных уведомлений
    """
    sent_count = 0
    
    # Получить всех спортсменов
    links = await db.coach_links.find({}).to_list(10000)
    athlete_ids = list(set([link["athlete_telegram_id"] for link in links]))
    
    for athlete_tg in athlete_ids:
        # Подсчитать streak
        now = datetime.now(timezone.utc)
        streak_days = 0
        current_date = now.date()
        
        while True:
            day_start = datetime.combine(current_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)
            
            # Проверить была ли тренировка в этот день
            session = await db.workout_sessions.find_one({
                "athlete_telegram_id": athlete_tg,
                "started_at": {"$gte": day_start, "$lt": day_end},
                "status": "finished"
            })
            
            if session:
                streak_days += 1
                current_date -= timedelta(days=1)
            else:
                break
        
        # Отправить уведомление на milestone (7, 14, 30, 60, 100 дней)
        milestones = [7, 14, 30, 60, 100]
        
        if streak_days in milestones:
            # Проверить не было ли уже уведомления
            existing = await db.notification_log.find_one({
                "user_telegram_id": athlete_tg,
                "type": "streak_milestone",
                "streak_days": streak_days
            })
            
            if not existing:
                settings = await get_notification_settings(db, athlete_tg)
                
                if await should_send_notification(settings, "achievement"):
                    athlete = await db.users.find_one({"telegram_id": athlete_tg})
                    athlete_name = athlete.get("first_name", "Атлет") if athlete else "Атлет"
                    
                    success = await send_streak_milestone(
                        athlete_tg,
                        athlete_name,
                        streak_days
                    )
                    
                    if success:
                        await db.notification_log.insert_one({
                            "user_telegram_id": athlete_tg,
                            "type": "streak_milestone",
                            "streak_days": streak_days,
                            "sent_at": now,
                            "success": True
                        })
                        sent_count += 1
    
    return sent_count
