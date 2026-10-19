"""
Планировщик задач для автоматических уведомлений.

Использует APScheduler для периодического выполнения проверок.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from motor.motor_asyncio import AsyncIOMotorDatabase

from notifications import (
    notify_upcoming_workouts,
    notify_daily_reports,
    check_and_notify_skipped_workouts
)

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def init_scheduler(db: AsyncIOMotorDatabase):
    """
    Инициализация планировщика задач.
    
    Args:
        db: База данных MongoDB
    """
    
    # Задача 1: Проверка предстоящих тренировок (каждые 15 минут)
    scheduler.add_job(
        func=notify_upcoming_workouts,
        trigger=IntervalTrigger(minutes=15),
        args=[db],
        id="notify_upcoming_workouts",
        name="Напоминания о предстоящих тренировках",
        replace_existing=True,
        max_instances=1
    )
    logger.info("Scheduled: notify_upcoming_workouts (every 15 minutes)")
    
    # Задача 2: Напоминания о заполнении отчетов (каждый день в 20:00)
    scheduler.add_job(
        func=notify_daily_reports,
        trigger=CronTrigger(hour=20, minute=0, timezone="UTC"),
        args=[db],
        id="notify_daily_reports",
        name="Напоминания о заполнении отчетов",
        replace_existing=True,
        max_instances=1
    )
    logger.info("Scheduled: notify_daily_reports (daily at 20:00 UTC)")
    
    # Задача 3: Проверка пропущенных тренировок (каждый день в 23:00)
    scheduler.add_job(
        func=check_and_notify_skipped_workouts,
        trigger=CronTrigger(hour=23, minute=0, timezone="UTC"),
        args=[db],
        id="check_skipped_workouts",
        name="Проверка пропущенных тренировок",
        replace_existing=True,
        max_instances=1
    )
    logger.info("Scheduled: check_skipped_workouts (daily at 23:00 UTC)")
    
    # Задача 4: Очистка старых логов уведомлений (каждую неделю)
    scheduler.add_job(
        func=cleanup_notification_logs,
        trigger=CronTrigger(day_of_week="mon", hour=3, minute=0, timezone="UTC"),
        args=[db],
        id="cleanup_notification_logs",
        name="Очистка старых логов уведомлений",
        replace_existing=True,
        max_instances=1
    )
    logger.info("Scheduled: cleanup_notification_logs (weekly on Monday at 03:00 UTC)")
    
    logger.info("Scheduler initialized with 4 jobs")


def start_scheduler():
    """Запуск планировщика."""
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
    else:
        logger.warning("Scheduler is already running")


def stop_scheduler():
    """Остановка планировщика."""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
    else:
        logger.warning("Scheduler is not running")


async def cleanup_notification_logs(db: AsyncIOMotorDatabase):
    """
    Удаление старых логов уведомлений (старше 30 дней).
    
    Сохраняет историю только за последний месяц для экономии места.
    """
    from datetime import datetime, timezone, timedelta
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
    
    result = await db.notification_log.delete_many({
        "sent_at": {"$lt": cutoff_date}
    })
    
    deleted_count = result.deleted_count
    logger.info(f"Cleaned up {deleted_count} old notification logs")
    
    return deleted_count


def get_scheduler_status():
    """
    Получить статус планировщика и список задач.
    
    Returns:
        Dict с информацией о планировщике
    """
    jobs_info = []
    
    for job in scheduler.get_jobs():
        next_run_time = getattr(job, "next_run_time", None)
        next_run = next_run_time.isoformat() if next_run_time else None
        
        jobs_info.append({
            "id": job.id,
            "name": job.name,
            "next_run": next_run,
            "trigger": str(job.trigger)
        })
    
    return {
        "running": scheduler.running,
        "jobs_count": len(jobs_info),
        "jobs": jobs_info
    }
