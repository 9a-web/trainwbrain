"""Создаёт тестовые данные и опрашивает эндпоинты статистики для анализа багов."""
import requests, json, time, sys

BASE = "http://localhost:8001/api"


def reg(email, password="password123", name="Probe"):
    r = requests.post(f"{BASE}/auth/register", json={"email": email, "password": password, "name": name})
    if r.status_code != 200:
        # already exists -> login
        r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    d = r.json()
    return d["token"], d["user"]["telegram_id"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    ts = int(time.time())
    email = f"statsprobe{ts}@ex.com"
    tok, tg = reg(email)
    print(f"athlete tg={tg} token={tok[:8]}...")

    # template
    tpls = requests.get(f"{BASE}/programs/templates").json()
    tpl = next((t for t in tpls if t["slug"] == "pl-autumn-3m"), tpls[0])
    print("template:", tpl["slug"], "requires_maxes=", tpl.get("requires_maxes"))

    maxes = {"squat": 200, "bench": 130, "deadlift": 230}
    training_days = [1, 3, 5]
    plan = requests.post(f"{BASE}/plans", json={
        "template_id": tpl["id"], "athlete_telegram_id": tg,
        "maxes": maxes, "training_days": training_days,
    }, headers=H(tok)).json()
    plan_id = plan["id"]
    print("plan:", plan_id, "weeks:", len(plan.get("weeks") or []))

    # Пройдём несколько дней в неделях 1..3, логируя подходы (часть с изменённым весом)
    done_days = []
    for week in (1, 2, 3):
        for day in training_days:
            # start session
            sresp = requests.post(f"{BASE}/sessions/start", json={
                "plan_id": plan_id, "athlete_telegram_id": tg, "week": week, "day": day,
            }, headers=H(tok))
            if sresp.status_code == 409:
                # active exists, fetch it
                sresp = requests.get(f"{BASE}/sessions/active", params={"plan_id": plan_id, "week": week, "day": day, "athlete": tg}, headers=H(tok))
            sess = sresp.json()
            sid = sess["id"]
            # log sets for each main exercise; skip one exercise on week 2 day 3
            for e in sess["exercises"]:
                order = e["order"]
                logs = e.get("set_logs") or []
                if not logs:
                    # accessory -> mark whole done
                    requests.patch(f"{BASE}/sessions/{sid}/exercise/{order}", params={"action": "done"}, headers=H(tok))
                    continue
                if week == 2 and day == 3 and order == 1:
                    # пропускаем целиком
                    requests.patch(f"{BASE}/sessions/{sid}/exercise/{order}", params={"action": "skip"}, headers=H(tok))
                    continue
                for i, lg in enumerate(logs):
                    body = {"done": True}
                    # на 3-й неделе поднимаем чуть больше плана
                    if week == 3 and i == 0 and lg.get("weight"):
                        body["weight"] = round(lg["weight"] + 5, 1)
                        body["reps"] = (lg.get("reps") or 3)
                    requests.patch(f"{BASE}/sessions/{sid}/exercise/{order}/set/{i}", json=body, headers=H(tok))
            # finish (если ещё не finished)
            requests.post(f"{BASE}/sessions/{sid}/finish", headers=H(tok))
            done_days.append((week, day))
    print("done days:", done_days)

    # Опрос эндпоинтов
    def dump(title, url, params=None):
        r = requests.get(url, params=params)
        print(f"\n===== {title} ({r.status_code}) =====")
        try:
            print(json.dumps(r.json(), ensure_ascii=False, indent=1)[:2600])
        except Exception:
            print(r.text[:1000])

    dump("detailed PLAN scope", f"{BASE}/stats/{tg}/detailed", {"plan_id": plan_id})
    dump("detailed ALL scope", f"{BASE}/stats/{tg}/detailed")
    dump("exercise-progress PLAN", f"{BASE}/stats/{tg}/exercise-progress", {"plan_id": plan_id})
    dump("exercise-progress ALL", f"{BASE}/stats/{tg}/exercise-progress")
    dump("streak", f"{BASE}/stats/{tg}/streak")
    dump("summary", f"{BASE}/stats/{tg}")

    print("\n\nCREDS:", email, "tg", tg, "plan", plan_id)


if __name__ == "__main__":
    main()
