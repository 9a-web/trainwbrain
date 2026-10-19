"""
Telegram Bot для отправки уведомлений клиентам и тренерам.

Использует httpx для прямого взаимодействия с Telegram Bot API.
Не требует дополнительных зависимостей.
"""

import os
import httpx
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def send_message(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    disable_notification: bool = False,
    reply_markup: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Отправка сообщения через Telegram Bot API.
    
    Args:
        chat_id: Telegram ID получателя
        text: Текст сообщения (поддерживает HTML)
        parse_mode: Режим парсинга (HTML, Markdown)
        disable_notification: Тихое уведомление
        reply_markup: Клавиатура (inline buttons)
    
    Returns:
        True если отправлено успешно
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment")
        return False
    
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_notification": disable_notification
    }
    
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                logger.info(f"Message sent to {chat_id}")
                return True
            else:
                logger.error(f"Failed to send message to {chat_id}: {response.text}")
                return False
    
    except Exception as e:
        logger.exception(f"Error sending message to {chat_id}: {e}")
        return False


async def send_workout_reminder(
    athlete_telegram_id: int,
    workout_name: str,
    scheduled_time: Optional[str] = None
) -> bool:
    """
    Напоминание о предстоящей тренировке.
    
    Args:
        athlete_telegram_id: Telegram ID спортсмена
        workout_name: Название тренировки
        scheduled_time: Время тренировки (опционально)
    """
    time_text = f" в {scheduled_time}" if scheduled_time else " сегодня"
    
    text = f"""
🏋️ <b>Напоминание о тренировке</b>

Тренировка{time_text}: <b>{workout_name}</b>

Не забудь отметить выполнение после завершения!
    """.strip()
    
    return await send_message(athlete_telegram_id, text)


async def send_report_reminder(
    athlete_telegram_id: int,
    athlete_name: str
) -> bool:
    """
    Напоминание о заполнении ежедневного отчета.
    
    Args:
        athlete_telegram_id: Telegram ID спортсмена
        athlete_name: Имя спортсмена
    """
    text = f"""
📝 <b>Время заполнить отчет</b>

{athlete_name}, не забудь заполнить сегодняшний отчет:
• Калории и БЖУ
• Вода и сон
• Шаги

Это займет всего 2 минуты!
    """.strip()
    
    return await send_message(athlete_telegram_id, text)


async def send_workout_completed_notification(
    coach_telegram_id: int,
    athlete_name: str,
    workout_name: str,
    completion_time: datetime
) -> bool:
    """
    Уведомление тренеру о завершенной тренировке клиента.
    
    Args:
        coach_telegram_id: Telegram ID тренера
        athlete_name: Имя спортсмена
        workout_name: Название тренировки
        completion_time: Время завершения
    """
    time_str = completion_time.strftime("%H:%M")
    
    text = f"""
✅ <b>Клиент завершил тренировку</b>

<b>{athlete_name}</b> выполнил тренировку "<b>{workout_name}</b>" в {time_str}

Можешь посмотреть результаты в приложении.
    """.strip()
    
    return await send_message(coach_telegram_id, text, disable_notification=True)


async def send_new_client_notification(
    coach_telegram_id: int,
    athlete_name: str,
    athlete_telegram_id: int
) -> bool:
    """
    Уведомление тренеру о новом клиенте.
    
    Args:
        coach_telegram_id: Telegram ID тренера
        athlete_name: Имя нового клиента
        athlete_telegram_id: Telegram ID клиента
    """
    text = f"""
🎉 <b>Новый клиент</b>

<b>{athlete_name}</b> присоединился к твоей команде!

Не забудь назначить первую программу тренировок.
    """.strip()
    
    return await send_message(coach_telegram_id, text)


async def send_workout_skipped_notification(
    coach_telegram_id: int,
    athlete_name: str,
    workout_name: str
) -> bool:
    """
    Уведомление тренеру о пропущенной тренировке.
    
    Args:
        coach_telegram_id: Telegram ID тренера
        athlete_name: Имя спортсмена
        workout_name: Название тренировки
    """
    text = f"""
⚠️ <b>Пропущена тренировка</b>

<b>{athlete_name}</b> пропустил тренировку "<b>{workout_name}</b>"

Возможно, стоит уточнить причину.
    """.strip()
    
    return await send_message(coach_telegram_id, text, disable_notification=True)


async def send_congratulations(
    athlete_telegram_id: int,
    athlete_name: str,
    achievement: str
) -> bool:
    """
    Поздравление с достижением.
    
    Args:
        athlete_telegram_id: Telegram ID спортсмена
        athlete_name: Имя спортсмена
        achievement: Описание достижения
    """
    text = f"""
🎊 <b>Поздравляем, {athlete_name}!</b>

{achievement}

Продолжай в том же духе! 💪
    """.strip()
    
    return await send_message(athlete_telegram_id, text)


async def send_streak_milestone(
    athlete_telegram_id: int,
    athlete_name: str,
    streak_days: int
) -> bool:
    """
    Уведомление о достижении серии тренировок.
    
    Args:
        athlete_telegram_id: Telegram ID спортсмена
        athlete_name: Имя спортсмена
        streak_days: Количество дней подряд
    """
    emoji = "🔥" if streak_days >= 7 else "⭐"
    
    text = f"""
{emoji} <b>Серия тренировок: {streak_days} дней!</b>

{athlete_name}, ты тренируешься {streak_days} дней подряд!

Отличная дисциплина! Так держать! 💪
    """.strip()
    
    return await send_message(athlete_telegram_id, text)


async def send_test_message(telegram_id: int) -> bool:
    """
    Тестовое сообщение для проверки работы бота.
    
    Args:
        telegram_id: Telegram ID получателя
    """
    text = """
✅ <b>Тестовое сообщение</b>

Бот работает корректно! Уведомления настроены.
    """.strip()
    
    return await send_message(telegram_id, text)


# Вспомогательная функция для получения информации о боте
async def get_bot_info() -> Optional[Dict[str, Any]]:
    """
    Получение информации о боте (username, name).
    
    Returns:
        Dict с данными бота или None при ошибке
    """
    if not TELEGRAM_BOT_TOKEN:
        return None
    
    url = f"{TELEGRAM_API_BASE}/getMe"
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return data.get("result")
            
            return None
    
    except Exception as e:
        logger.exception(f"Error getting bot info: {e}")
        return None
