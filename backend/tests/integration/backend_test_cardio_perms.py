"""Проверка прав кардио: coach-доступ и permissions.log_cardio."""
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient

BASE = "http://127.0.0.1:8000/api"
ATHLETE = 950000000123
COACH = 950000000777

db = MongoClient("mongodb://localhost:27017")["trainwbrain_db"]
now = datetime.now(timezone.utc).isoformat()


def mk_session(tg, tag):
    token = f"test_{tag}_{int(time.time() * 1000)}"
    db.user_sessions.insert_one({
        "session_token": token, "telegram_id": tg, "auth_method": "email",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": now,
    })
    return token


def req(method, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=h, method=method)
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


passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(f"{'PASS' if cond else 'FAIL'}: {name}" + (f"  -> {detail}" if detail else ""))


# Тренер
db.users.update_one(
    {"telegram_id": COACH},
    {"$set": {"id": f"test-{COACH}", "telegram_id": COACH, "first_name": "CardioCoach",
              "access_tier": "standalone", "roles": ["coach"],
              "onboarded_at": now, "created_at": now, "updated_at": now}},
    upsert=True,
)
db.coach_links.update_one(
    {"coach_telegram_id": COACH, "athlete_telegram_id": ATHLETE},
    {"$set": {"id": f"link-{COACH}-{ATHLETE}", "coach_telegram_id": COACH,
              "athlete_telegram_id": ATHLETE, "status": "active",
              "created_at": now, "updated_at": now}},
    upsert=True,
)
coach_token = mk_session(COACH, "coach")

print("=== 1. Тренер создаёт кардио подопечному ===")
st, created = req("POST", "/cardio", {
    "athlete_telegram_id": ATHLETE, "type": "bike", "duration_min": 40,
    "distance_km": 15.0, "intensity": "moderate",
}, coach_token)
check("тренер: POST /cardio -> 200", st == 200, f"status={st}")
check("coach_telegram_id проставлен", created and created.get("coach_telegram_id") == COACH,
      str(created.get("coach_telegram_id") if created else None))
cid = created["id"] if created else None

print("\n=== 2. Тренер читает кардио подопечного ===")
st, lst = req("GET", f"/cardio?athlete={ATHLETE}", token=coach_token)
check("тренер: GET /cardio?athlete -> 200", st == 200, f"status={st}")
check("запись видна тренеру", any(i["id"] == cid for i in (lst or {}).get("items", [])))
st, stats = req("GET", f"/stats/{ATHLETE}/cardio", token=coach_token)
check("тренер: GET /stats/{tg}/cardio -> 200", st == 200, f"status={st}")

print("\n=== 3. Посторонний не видит (IDOR) ===")
OTHER = 950000000999
db.users.update_one(
    {"telegram_id": OTHER},
    {"$set": {"id": f"test-{OTHER}", "telegram_id": OTHER, "first_name": "Stranger",
              "access_tier": "standalone", "onboarded_at": now,
              "created_at": now, "updated_at": now}},
    upsert=True,
)
other = mk_session(OTHER, "other")
st, _ = req("GET", f"/stats/{ATHLETE}/cardio", token=other)
check("403 постороннему", st == 403, f"status={st}")

print("\n=== 4. Права log_cardio (coach_managed без права) ===")
db.users.update_one(
    {"telegram_id": ATHLETE},
    {"$set": {"access_tier": "coach_managed",
              "permissions": {"log_cardio": False, "log_strength": False,
                              "view_strength": True, "view_cardio": True}}},
)
athlete_token = mk_session(ATHLETE, "ath")
st, _ = req("POST", "/cardio", {"type": "walk", "duration_min": 20}, athlete_token)
check("403 атлету без log_cardio", st == 403, f"status={st}")
st, _ = req("GET", f"/stats/{ATHLETE}/cardio", token=athlete_token)
check("просмотр кардио разрешён (view_cardio)", st == 200, f"status={st}")

print("\n=== 5. Возврат права log_cardio ===")
db.users.update_one({"telegram_id": ATHLETE},
                    {"$set": {"permissions.log_cardio": True}})
st, _ = req("POST", "/cardio", {"type": "walk", "duration_min": 20}, athlete_token)
check("200 после выдачи права", st == 200, f"status={st}")

print("\n=== 6. Не-тренер не пишет за атлета ===")
st, _ = req("POST", "/cardio", {"athlete_telegram_id": ATHLETE, "type": "walk",
                                "duration_min": 10}, other)
check("403 постороннему за атлета", st == 403, f"status={st}")

# Очистка
db.cardio_sessions.delete_many({"athlete_telegram_id": ATHLETE})
db.coach_links.delete_one({"coach_telegram_id": COACH, "athlete_telegram_id": ATHLETE})
db.users.update_one({"telegram_id": ATHLETE},
                    {"$unset": {"permissions": ""}, "$set": {"access_tier": "standalone"}})
db.users.delete_one({"telegram_id": OTHER})

print(f"\n{'='*60}\nИТОГО: {len(passed)} PASS, {len(failed)} FAIL")
if failed:
    print("Провалено: " + ", ".join(failed))
sys.exit(1 if failed else 0)
