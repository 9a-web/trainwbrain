"""E2E-проверка кардио-эндпоинтов (Фаза 3) против живого backend на :8000.

Запуск (backend и MongoDB должны быть подняты):
    python tests/integration/backend_test_cardio.py [session_token]

Без аргумента скрипт сам создаёт тестового пользователя и сессию в MongoDB.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("TWB_BASE", "http://127.0.0.1:8000/api")
ATHLETE = 950000000123


def seed_token():
    """Создаёт тестового пользователя (standalone) и Bearer-сессию."""
    from pymongo import MongoClient
    db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "trainwbrain_db")
    ]
    now = datetime.now(timezone.utc).isoformat()
    db.users.update_one(
        {"telegram_id": ATHLETE},
        {"$set": {
            "id": f"test-{ATHLETE}", "telegram_id": ATHLETE,
            "first_name": "CardioTest", "access_tier": "standalone",
            "onboarded_at": now, "created_at": now, "updated_at": now,
        }},
        upsert=True,
    )
    token = f"test_cardio_{int(time.time() * 1000)}"
    db.user_sessions.insert_one({
        "session_token": token, "telegram_id": ATHLETE, "auth_method": "email",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": now,
    })
    return token


TOKEN = sys.argv[1] if len(sys.argv) > 1 else seed_token()
HDRS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(f"{'PASS' if cond else 'FAIL'}: {name}" + (f"  -> {detail}" if detail else ""))


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=HDRS, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


print("=== 1. Создание кардио (дорожка, 30 мин, 4.2 км) ===")
st, created = req("POST", "/cardio", {
    "type": "treadmill", "date": "2026-10-10", "duration_min": 30,
    "distance_km": 4.2, "avg_hr": 142, "max_hr": 168,
    "intensity": "moderate", "rpe": 6.5, "incline_percent": 6,
    "notes": "Пульс держал 140-150",
})
check("POST /cardio -> 200", st == 200, f"status={st}")
check("id присвоен", bool(created and created.get("id")))
check("duration_sec = 1800", created and created.get("duration_sec") == 1800, str(created.get("duration_sec") if created else None))
check("калории рассчитаны автоматически", bool(created and created.get("calories")), str(created.get("calories") if created else None))
check("avg_pace рассчитан", bool(created and created.get("avg_pace")), str(created.get("avg_pace") if created else None))
check("source=manual", created and created.get("source") == "manual")
cid = created["id"] if created else None

print("\n=== 2. Список кардио ===")
st, lst = req("GET", "/cardio?limit=50")
check("GET /cardio -> 200", st == 200, f"status={st}")
check("созданная запись в списке", any(i["id"] == cid for i in (lst or {}).get("items", [])))

print("\n=== 3. Агрегат статистики ===")
st, stats = req("GET", "/stats/950000000123/cardio?period=week")
check("GET /stats/{tg}/cardio -> 200", st == 200, f"status={st}")
check("minutes >= 30", stats and stats.get("minutes", 0) >= 30, str(stats.get("minutes") if stats else None))
check("sessions >= 1", stats and stats.get("sessions", 0) >= 1)
check("km учтён", stats and stats.get("km", 0) >= 4.2, str(stats.get("km") if stats else None))
check("kcal учтён", stats and stats.get("kcal", 0) > 0)
check("by_type содержит treadmill", stats and "treadmill" in (stats.get("by_type") or {}))
check("weekly_minutes посчитан", stats and stats.get("weekly_minutes", 0) >= 30)

print("\n=== 4. Валидация (ожидаем 400) ===")
for name, body in [
    ("неверный type", {"type": "swimming", "duration_min": 10}),
    ("пульс вне диапазона", {"type": "bike", "duration_min": 10, "avg_hr": 400}),
    ("отрицательная длительность", {"type": "bike", "duration_min": -5}),
    ("RPE > 10", {"type": "bike", "duration_min": 10, "rpe": 15}),
    ("плохая дата", {"type": "bike", "duration_min": 10, "date": "not-a-date"}),
]:
    st, _ = req("POST", "/cardio", body)
    check(f"400 на {name}", st == 400, f"status={st}")

print("\n=== 5. PATCH (правка) ===")
st, upd = req("PATCH", f"/cardio/{cid}", {"duration_min": 45, "notes": "Обновлено"})
check("PATCH -> 200", st == 200, f"status={st}")
check("duration обновлён", upd and upd.get("duration_sec") == 2700, str(upd.get("duration_sec") if upd else None))
check("notes обновлён", upd and upd.get("notes") == "Обновлено")
st, _ = req("PATCH", f"/cardio/{cid}", {})
check("400 на пустой PATCH", st == 400, f"status={st}")

print("\n=== 6. Чужой доступ (IDOR) ===")
st, _ = req("GET", "/stats/999999999/cardio")
check("403 на чужую статистику", st == 403, f"status={st}")
st, _ = req("GET", "/cardio?athlete=999999999")
check("403 на чужой список", st == 403, f"status={st}")

print("\n=== 7. DELETE ===")
st, _ = req("DELETE", f"/cardio/{cid}")
check("DELETE -> 200", st == 200, f"status={st}")
st, lst2 = req("GET", "/cardio?limit=50")
check("запись удалена", not any(i["id"] == cid for i in (lst2 or {}).get("items", [])))
st, _ = req("DELETE", f"/cardio/{cid}")
check("404 при повторном DELETE", st == 404, f"status={st}")

print(f"\n{'='*60}\nИТОГО: {len(passed)} PASS, {len(failed)} FAIL")
if failed:
    print("Провалено: " + ", ".join(failed))
sys.exit(1 if failed else 0)
