"""Создаёт стабильный демо-аккаунт statsdemo@twb.dev с 9 тренировками за 3 недели."""
import requests, asyncio, os, sys
from datetime import datetime, timedelta, timezone, date

BASE = "http://localhost:8001/api"
EMAIL, PWD = "statsdemo@twb.dev", "password123"


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    r = requests.post(f"{BASE}/auth/register", json={"email": EMAIL, "password": PWD, "name": "Демо Атлет"})
    if r.status_code != 200:
        r = requests.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PWD})
    r.raise_for_status()
    d = r.json()
    tok, tg = d["token"], d["user"]["telegram_id"]
    print("tg:", tg)

    tpls = requests.get(f"{BASE}/programs/templates", headers=H(tok)).json()
    tpl = next((t for t in tpls if t["slug"] == "pl-autumn-3m"), tpls[0])
    plan = requests.post(f"{BASE}/plans", json={
        "template_id": tpl["id"], "athlete_telegram_id": tg,
        "maxes": {"squat": 200, "bench": 130, "deadlift": 230},
        "training_days": [1, 3, 5],
    }, headers=H(tok)).json()
    plan_id = plan["id"]
    print("plan:", plan_id)

    for week in (1, 2, 3):
        for day in (1, 3, 5):
            s = requests.post(f"{BASE}/sessions/start", json={
                "plan_id": plan_id, "athlete_telegram_id": tg, "week": week, "day": day,
            }, headers=H(tok))
            if s.status_code == 409:
                s = requests.get(f"{BASE}/sessions/active", params={
                    "plan_id": plan_id, "week": week, "day": day, "athlete": tg}, headers=H(tok))
            sess = s.json()
            sid = sess["id"]
            for e in sess["exercises"]:
                order = e["order"]
                logs = e.get("set_logs") or []
                if not logs:
                    requests.patch(f"{BASE}/sessions/{sid}/exercise/{order}",
                                   params={"action": "done"}, headers=H(tok))
                    continue
                if week == 2 and day == 3 and order == 1:
                    requests.patch(f"{BASE}/sessions/{sid}/exercise/{order}",
                                   params={"action": "skip"}, headers=H(tok))
                    continue
                for i, lg in enumerate(logs):
                    body = {"done": True}
                    if week >= 2 and i == 0 and lg.get("weight"):
                        body["weight"] = round(lg["weight"] + 2.5 * week, 1)
                        body["reps"] = lg.get("reps") or 3
                    requests.patch(f"{BASE}/sessions/{sid}/exercise/{order}/set/{i}",
                                   json=body, headers=H(tok))
            requests.post(f"{BASE}/sessions/{sid}/finish", headers=H(tok))
            print("finished", week, day, sid[:8])

    # --- Раскидываем даты по календарю (неделя 3 = текущая) ---
    async def backdate():
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        today = datetime.now(timezone.utc).date()
        monday = today - timedelta(days=today.weekday())
        sessions = await db.workout_sessions.find(
            {"athlete_telegram_id": tg, "status": "finished"}, {"_id": 0, "id": 1, "week_index": 1, "day_index": 1}
        ).to_list(100)
        for s in sessions:
            w, dd = s.get("week_index") or 1, s.get("day_index") or 1
            day_date = monday - timedelta(weeks=(3 - w)) + timedelta(days=dd - 1)
            if day_date > today:
                day_date = today
            start = datetime(day_date.year, day_date.month, day_date.day, 17, 0, tzinfo=timezone.utc)
            fin = start + timedelta(minutes=72)
            await db.workout_sessions.update_one({"id": s["id"]}, {"$set": {
                "date": day_date.isoformat(),
                "started_at": start.isoformat(),
                "finished_at": fin.isoformat(),
                "stats.duration_sec": 72 * 60,
            }})
        print("backdated", len(sessions))
    asyncio.run(backdate())
    print("CREDS:", EMAIL, PWD, "tg", tg, "plan", plan_id)


if __name__ == "__main__":
    main()
