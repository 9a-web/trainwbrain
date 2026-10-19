"""Создаёт демо-аккаунт streakdemo@twb.dev с несколькими сериями тренировок.

Серии: 5 дней (~4 нед назад), 3 дня (~2 нед назад), текущая 2 дня (вчера+сегодня),
плюс одиночные дни. Используется для проверки экрана «Тренировочная серия».
"""
import requests, asyncio, os, uuid
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8001/api"
EMAIL, PWD = "streakdemo@twb.dev", "password123"


def main():
    r = requests.post(f"{BASE}/auth/register", json={"email": EMAIL, "password": PWD, "name": "Стрик Демо"})
    if r.status_code != 200:
        r = requests.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PWD})
    r.raise_for_status()
    d = r.json()
    tok, tg = d["token"], d["user"]["telegram_id"]
    print("tg:", tg)

    today = datetime.now(timezone.utc).date()
    # смещения дней (0 = сегодня) для серий и одиночных дней
    offsets = []
    offsets += [1, 0]                       # текущая серия: вчера + сегодня (2 дня)
    offsets += [13, 12, 11]                 # серия 3 дня ~2 недели назад
    offsets += [30, 29, 28, 27, 26]         # серия 5 дней ~4 недели назад
    offsets += [7, 20, 36]                  # одиночные дни
    days = sorted({today - timedelta(days=o) for o in offsets})

    async def insert():
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        await db.workout_sessions.delete_many({"athlete_telegram_id": tg})
        docs = []
        for i, day in enumerate(days):
            start = datetime(day.year, day.month, day.day, 17, 0, tzinfo=timezone.utc)
            fin = start + timedelta(minutes=65)
            docs.append({
                "id": str(uuid.uuid4()),
                "plan_id": None,
                "athlete_telegram_id": tg,
                "week_index": i // 7 + 1,
                "day_index": i % 7 + 1,
                "status": "finished",
                "date": day.isoformat(),
                "started_at": start.isoformat(),
                "finished_at": fin.isoformat(),
                "exercises": [
                    {"order": 0, "name": "Приседания со штангой", "slug": "back-squat",
                     "status": "done", "sets": 5, "reps": 5, "weight": 120.0},
                    {"order": 1, "name": "Жим лёжа", "slug": "bench-press",
                     "status": "done", "sets": 5, "reps": 5, "weight": 80.0},
                ],
                "stats": {"duration_sec": 65 * 60, "tonnage": 5000},
            })
        if docs:
            await db.workout_sessions.insert_many(docs)
        print("inserted sessions:", len(docs))

    asyncio.run(insert())

    s = requests.get(f"{BASE}/stats/{tg}/streak", params={"weeks": 12},
                     headers={"Authorization": f"Bearer {tok}"}).json()
    print("current_streak:", s.get("current_streak"), "| best:", s.get("best_streak"),
          "| streaks:", [(x["start"], x["length"]) for x in s.get("streaks", [])])
    print("CREDS:", EMAIL, PWD, "tg", tg)


if __name__ == "__main__":
    main()
