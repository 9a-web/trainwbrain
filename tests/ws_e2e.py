"""E2E real-time тест P4: тренер ↔ спортсмен через WebSocket.

Сценарий:
  1. Регистрируем спортсмена и тренера (email-auth).
  2. Тренер генерирует invite-код, спортсмен привязывается.
  3. Тренер назначает план спортсмену из шаблона.
  4. Оба подключаются к WS и подписываются на комнату плана.
  5. Спортсмен стартует тренировку -> тренер получает session.started.
  6. Тренер отмечает упражнение (actor=coach) -> спортсмен получает session.updated с filled_by=coach.
  7. Тренер подтверждает упражнение -> coach_confirmed=true приходит вживую.
  8. Спортсмен отмечает упражнение -> тренер получает обновление.
  9. coach-gated GET .../session возвращает живую сессию; чужой тренер -> 403.
"""
import asyncio
import json
import time

import requests
import websockets

HTTP = "http://localhost:8001"
WS = "ws://localhost:8001/api/ws"


def reg(name):
    email = f"rt_{name}_{int(time.time()*1000)}@example.com"
    r = requests.post(f"{HTTP}/api/auth/register",
                      json={"email": email, "password": "password123", "name": name}, timeout=20)
    r.raise_for_status()
    d = r.json()
    return d["token"], d["user"]["telegram_id"]


async def drain(ws, seconds=1.5):
    """Собрать все события из WS за указанное время."""
    out = []
    end = time.time() + seconds
    while time.time() < end:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.05, end - time.time()))
            out.append(json.loads(raw))
        except asyncio.TimeoutError:
            break
        except Exception:
            break
    return out


def types(events):
    return [e.get("type") for e in events]


async def main():
    ok = True
    token_a, a = reg("athlete")
    token_c, c = reg("coach")
    token_x, x = reg("othercoach")
    print(f"athlete={a} coach={c} other={x}")

    # invite + link
    code = requests.post(f"{HTTP}/api/coach/invite", json={"coach_telegram_id": c}, timeout=20).json()["invite_code"]
    requests.post(f"{HTTP}/api/coach/link", json={"code": code, "athlete_telegram_id": a}, timeout=20).raise_for_status()
    print("linked, code=", code)

    # assign plan from template (full-body-beginner — без requires_maxes)
    tpls = requests.get(f"{HTTP}/api/programs/templates", timeout=20).json()
    tpl = next((t for t in tpls if t.get("slug") == "full-body-beginner"), tpls[0])
    plan = requests.post(f"{HTTP}/api/plans", json={
        "athlete_telegram_id": a, "template_id": tpl["id"], "coach_telegram_id": c,
    }, timeout=20).json()
    plan_id = plan["id"]
    # publish so athlete-side semantics are realistic (start_session не требует, но ок)
    requests.patch(f"{HTTP}/api/plans/{plan_id}/visibility", json={"visibility": "published"}, timeout=20)
    # найти week 1 + первый non-rest день
    pfull = requests.get(f"{HTTP}/api/plans/{plan_id}", timeout=20).json()
    wk = next(w for w in pfull["weeks"] if w["week_index"] == 1)
    day = next(d for d in wk["days"] if not d.get("is_rest"))
    day_idx = day["day_index"]
    print(f"plan={plan_id} week=1 day={day_idx} exercises={len(day['exercises'])}")

    # connect both WS and subscribe
    async with websockets.connect(f"{WS}?token={token_c}", ping_interval=None, open_timeout=15) as wc, \
               websockets.connect(f"{WS}?token={token_a}", ping_interval=None, open_timeout=15) as wa:
        await drain(wc, 0.5); await drain(wa, 0.5)  # consume 'connected'
        await wc.send(json.dumps({"type": "subscribe", "plan_id": plan_id}))
        await wa.send(json.dumps({"type": "subscribe", "plan_id": plan_id}))
        await drain(wc, 0.8); await drain(wa, 0.8)  # consume presence

        # 5. athlete starts session
        sess = requests.post(f"{HTTP}/api/sessions/start", json={
            "plan_id": plan_id, "athlete_telegram_id": a, "week": 1, "day": day_idx,
        }, timeout=20).json()
        sid = sess["id"]
        ev_c = await drain(wc, 1.5)
        print("coach after start:", types(ev_c))
        started = any(e["type"] == "session.started" for e in ev_c)
        print("  session.started received by coach:", started); ok &= started

        # 6. coach marks exercise 0 done (co-scribe)
        r = requests.patch(f"{HTTP}/api/sessions/{sid}/exercise/0",
                           params={"action": "done", "actor": "coach", "by": c}, timeout=20)
        print("  coach mark status:", r.status_code)
        ev_a = await drain(wa, 1.5)
        print("athlete after coach-mark:", types(ev_a))
        upd = [e for e in ev_a if e["type"] in ("session.updated", "session.finished")]
        filled_ok = False
        if upd:
            exs = upd[-1]["payload"]["session"]["exercises"]
            filled_ok = exs[0].get("filled_by") == "coach" and exs[0].get("status") == "done"
        print("  filled_by=coach + done received by athlete:", filled_ok); ok &= filled_ok

        # 7. coach confirms exercise 0
        r = requests.patch(f"{HTTP}/api/sessions/{sid}/exercise/0/confirm",
                           json={"coach_telegram_id": c}, timeout=20)
        ev_a = await drain(wa, 1.5)
        conf = [e for e in ev_a if e["type"] == "session.updated"]
        confirm_ok = bool(conf) and conf[-1]["payload"]["session"]["exercises"][0].get("coach_confirmed") is True
        print("  exercise coach_confirmed received by athlete:", confirm_ok); ok &= confirm_ok

        # 8. athlete marks exercise 1 done -> coach receives
        if len(day["exercises"]) > 1:
            requests.patch(f"{HTTP}/api/sessions/{sid}/exercise/1", params={"action": "done"}, timeout=20)
            ev_c = await drain(wc, 1.5)
            got = any(e["type"] in ("session.updated", "session.finished") for e in ev_c)
            print("  athlete-mark received by coach:", got); ok &= got

    # 9. coach-gated live session
    live = requests.get(f"{HTTP}/api/coach/{c}/clients/{a}/session", timeout=20)
    live_ok = live.status_code == 200 and live.json() and live.json().get("id") == sid
    print("coach live session ok:", live_ok); ok &= live_ok
    other = requests.get(f"{HTTP}/api/coach/{x}/clients/{a}/session", timeout=20)
    print("other coach 403:", other.status_code == 403); ok &= (other.status_code == 403)
    # other coach cannot mark as coach
    r = requests.patch(f"{HTTP}/api/sessions/{sid}/exercise/0",
                       params={"action": "reset", "actor": "coach", "by": x}, timeout=20)
    print("other coach mark forbidden (403):", r.status_code == 403); ok &= (r.status_code == 403)

    print("\n==== RESULT:", "PASS" if ok else "FAIL", "====")


asyncio.run(main())
