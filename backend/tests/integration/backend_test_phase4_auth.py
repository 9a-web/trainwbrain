#!/usr/bin/env python3
"""
PHASE 4 Session Authorization / IDOR Hardening Tests
Tests ALL /api/sessions* endpoints require Bearer token + ownership/coach checks
"""
import requests
import random
import sys

BASE_URL = "https://neuro-learn-30.preview.emergentagent.com/api"

def register_user(email_prefix):
    """Register a new user and return (token, telegram_id)"""
    email = f"{email_prefix}{random.randint(100000, 999999)}@example.com"
    password = "password123"
    name = f"User_{email_prefix}"
    
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "name": name
    })
    assert resp.status_code == 200, f"Register failed: {resp.status_code} {resp.text}"
    data = resp.json()
    token = data["token"]
    telegram_id = data["user"]["telegram_id"]
    print(f"✓ Registered {email_prefix}: email={email}, telegram_id={telegram_id}")
    return token, telegram_id, email

def set_coach_mode(token, telegram_id):
    """Set user mode to coach"""
    resp = requests.patch(f"{BASE_URL}/users/{telegram_id}/mode", 
                         json={"mode": "coach"},
                         headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Set coach mode failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "coach" in data["roles"], "Coach role not added"
    invite_code = data.get("invite_code")
    print(f"✓ Set coach mode, invite_code={invite_code}")
    return invite_code

def link_coach_to_athlete(coach_token, invite_code, athlete_tg):
    """Link coach to athlete"""
    resp = requests.post(f"{BASE_URL}/coach/link",
                        json={"code": invite_code, "athlete_telegram_id": athlete_tg},
                        headers={"Authorization": f"Bearer {coach_token}"})
    assert resp.status_code == 200, f"Link coach failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["status"] == "active", "Link not active"
    print(f"✓ Linked coach to athlete (status={data['status']})")

def get_template_id(token, slug="full-body-beginner"):
    """Get template ID by slug"""
    resp = requests.get(f"{BASE_URL}/programs/templates", 
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Get templates failed: {resp.status_code}"
    templates = resp.json()
    template = next((t for t in templates if t["slug"] == slug), None)
    assert template, f"Template {slug} not found"
    print(f"✓ Found template '{slug}': id={template['id']}")
    return template["id"]

def create_plan(token, athlete_tg, template_id):
    """Create a plan for athlete"""
    resp = requests.post(f"{BASE_URL}/plans",
                        json={
                            "athlete_telegram_id": athlete_tg,
                            "template_id": template_id,
                            "training_days": [1, 3, 5]
                        },
                        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Create plan failed: {resp.status_code} {resp.text}"
    data = resp.json()
    plan_id = data["id"]
    print(f"✓ Created plan: id={plan_id}")
    return plan_id

def find_first_workout_day(token, plan_id):
    """Find first non-rest day in week 1"""
    resp = requests.get(f"{BASE_URL}/plans/{plan_id}/week-progress?week=1",
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Get week progress failed: {resp.status_code}"
    data = resp.json()
    days = data.get("days", [])
    workout_day = next((d for d in days if d.get("is_workout")), None)
    assert workout_day, "No workout day found in week 1"
    day_index = workout_day["day_index"]
    print(f"✓ Found first workout day: day_index={day_index}")
    return day_index

def start_session(token, plan_id, athlete_tg, week, day, date="2026-06-20", coach_tg=None):
    """Start a session"""
    payload = {
        "plan_id": plan_id,
        "athlete_telegram_id": athlete_tg,
        "week": week,
        "day": day,
        "date": date
    }
    if coach_tg:
        payload["coach_telegram_id"] = coach_tg
    
    resp = requests.post(f"{BASE_URL}/sessions/start",
                        json=payload,
                        headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        return None, resp.status_code
    data = resp.json()
    session_id = data["id"]
    print(f"✓ Started session: id={session_id}, status={data['status']}")
    return session_id, 200

def main():
    print("=" * 80)
    print("PHASE 4: SESSION AUTHORIZATION / IDOR HARDENING TESTS")
    print("=" * 80)
    
    # ========== SETUP ==========
    print("\n[SETUP] Registering 3 accounts...")
    owner_token, owner_tg, owner_email = register_user("phase4_owner")
    coach_token, coach_tg, coach_email = register_user("phase4_coach")
    stranger_token, stranger_tg, stranger_email = register_user("phase4_stranger")
    
    print("\n[SETUP] Setting coach mode...")
    invite_code = set_coach_mode(coach_token, coach_tg)
    # Also set stranger as coach for spoof test
    set_coach_mode(stranger_token, stranger_tg)
    
    print("\n[SETUP] Linking coach to owner athlete...")
    link_coach_to_athlete(coach_token, invite_code, owner_tg)
    
    print("\n[SETUP] Creating self-plan for owner...")
    template_id = get_template_id(owner_token)
    plan_id = create_plan(owner_token, owner_tg, template_id)
    
    print("\n[SETUP] Finding first workout day...")
    day_index = find_first_workout_day(owner_token, plan_id)
    
    print("\n[SETUP] Starting session as owner...")
    session_id, status = start_session(owner_token, plan_id, owner_tg, 1, day_index)
    assert status == 200, f"Failed to start session: {status}"
    
    print(f"\n{'='*80}")
    print(f"SETUP COMPLETE:")
    print(f"  OWNER: {owner_email} (tg={owner_tg})")
    print(f"  COACH: {coach_email} (tg={coach_tg})")
    print(f"  STRANGER: {stranger_email} (tg={stranger_tg})")
    print(f"  PLAN: {plan_id}")
    print(f"  SESSION: {session_id}")
    print(f"{'='*80}\n")
    
    results = []
    
    # ========== TEST 1: NO TOKEN -> 401 ==========
    print("\n[TEST 1] NO TOKEN -> 401")
    
    # GET /sessions/{id}
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}")
    print(f"  GET /sessions/{{id}} (no token): {resp.status_code}")
    results.append(("1a", "GET /sessions/{id} no token", 401, resp.status_code))
    
    # PATCH /sessions/{id}/exercise/0/set/0
    resp = requests.patch(f"{BASE_URL}/sessions/{session_id}/exercise/0/set/0",
                         json={"done": True})
    print(f"  PATCH /sessions/{{id}}/exercise/0/set/0 (no token): {resp.status_code}")
    results.append(("1b", "PATCH set no token", 401, resp.status_code))
    
    # POST /sessions/{id}/finish
    resp = requests.post(f"{BASE_URL}/sessions/{session_id}/finish")
    print(f"  POST /sessions/{{id}}/finish (no token): {resp.status_code}")
    results.append(("1c", "POST finish no token", 401, resp.status_code))
    
    # ========== TEST 2: STRANGER TOKEN -> 403 ==========
    print("\n[TEST 2] STRANGER TOKEN -> 403")
    
    # GET /sessions/{id}
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}",
                       headers={"Authorization": f"Bearer {stranger_token}"})
    print(f"  GET /sessions/{{id}} (stranger): {resp.status_code}")
    results.append(("2a", "GET /sessions/{id} stranger", 403, resp.status_code))
    
    # PATCH /sessions/{id}/exercise/0/set/0
    resp = requests.patch(f"{BASE_URL}/sessions/{session_id}/exercise/0/set/0",
                         json={"done": True},
                         headers={"Authorization": f"Bearer {stranger_token}"})
    print(f"  PATCH /sessions/{{id}}/exercise/0/set/0 (stranger): {resp.status_code}")
    results.append(("2b", "PATCH set stranger", 403, resp.status_code))
    
    # POST /sessions/{id}/finish
    resp = requests.post(f"{BASE_URL}/sessions/{session_id}/finish",
                        headers={"Authorization": f"Bearer {stranger_token}"})
    print(f"  POST /sessions/{{id}}/finish (stranger): {resp.status_code}")
    results.append(("2c", "POST finish stranger", 403, resp.status_code))
    
    # GET /sessions/active
    resp = requests.get(f"{BASE_URL}/sessions/active",
                       params={
                           "plan_id": plan_id,
                           "week": 1,
                           "day": day_index,
                           "athlete": owner_tg,
                           "date": "2026-06-20"
                       },
                       headers={"Authorization": f"Bearer {stranger_token}"})
    print(f"  GET /sessions/active (stranger): {resp.status_code}")
    results.append(("2d", "GET /sessions/active stranger", 403, resp.status_code))
    
    # ========== TEST 3: OWNER TOKEN -> 200 ==========
    print("\n[TEST 3] OWNER TOKEN -> 200")
    
    # GET /sessions/{id}
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}",
                       headers={"Authorization": f"Bearer {owner_token}"})
    print(f"  GET /sessions/{{id}} (owner): {resp.status_code}")
    results.append(("3a", "GET /sessions/{id} owner", 200, resp.status_code))
    
    # PATCH /sessions/{id}/exercise/0/set/0
    resp = requests.patch(f"{BASE_URL}/sessions/{session_id}/exercise/0/set/0",
                         json={"done": True},
                         headers={"Authorization": f"Bearer {owner_token}"})
    print(f"  PATCH /sessions/{{id}}/exercise/0/set/0 (owner): {resp.status_code}")
    results.append(("3b", "PATCH set owner", 200, resp.status_code))
    assert resp.status_code == 200, f"Owner PATCH set failed: {resp.text}"
    
    # GET /sessions/active
    resp = requests.get(f"{BASE_URL}/sessions/active",
                       params={
                           "plan_id": plan_id,
                           "week": 1,
                           "day": day_index,
                           "athlete": owner_tg,
                           "date": "2026-06-20"
                       },
                       headers={"Authorization": f"Bearer {owner_token}"})
    print(f"  GET /sessions/active (owner): {resp.status_code}")
    results.append(("3c", "GET /sessions/active owner", 200, resp.status_code))
    
    # ========== TEST 4: LINKED COACH -> 200 ==========
    print("\n[TEST 4] LINKED COACH -> 200")
    
    # PATCH set (co-scribe)
    resp = requests.patch(f"{BASE_URL}/sessions/{session_id}/exercise/0/set/1",
                         json={"done": True},
                         params={"actor": "coach", "by": coach_tg},
                         headers={"Authorization": f"Bearer {coach_token}"})
    print(f"  PATCH /sessions/{{id}}/exercise/0/set/1 actor=coach&by={{coach}} (coach): {resp.status_code}")
    results.append(("4a", "PATCH set coach co-scribe", 200, resp.status_code))
    
    # POST finish (no actor - coach allowed)
    resp = requests.post(f"{BASE_URL}/sessions/{session_id}/finish",
                        headers={"Authorization": f"Bearer {coach_token}"})
    print(f"  POST /sessions/{{id}}/finish (coach, no actor): {resp.status_code}")
    results.append(("4b", "POST finish coach", 200, resp.status_code))
    
    # POST confirm session
    resp = requests.post(f"{BASE_URL}/sessions/{session_id}/confirm",
                        json={"coach_telegram_id": coach_tg},
                        headers={"Authorization": f"Bearer {coach_token}"})
    print(f"  POST /sessions/{{id}}/confirm (coach): {resp.status_code}")
    results.append(("4c", "POST confirm session coach", 200, resp.status_code))
    
    # PATCH exercise confirm
    resp = requests.patch(f"{BASE_URL}/sessions/{session_id}/exercise/0/confirm",
                         json={"coach_telegram_id": coach_tg},
                         headers={"Authorization": f"Bearer {coach_token}"})
    print(f"  PATCH /sessions/{{id}}/exercise/0/confirm (coach): {resp.status_code}")
    results.append(("4d", "PATCH exercise confirm coach", 200, resp.status_code))
    
    # ========== TEST 5: SPOOF -> 403 ==========
    print("\n[TEST 5] SPOOF (stranger token with actor=coach&by=coach_tg) -> 403")
    
    # Resume session first to make it active again
    resp = requests.post(f"{BASE_URL}/sessions/{session_id}/resume",
                        headers={"Authorization": f"Bearer {owner_token}"})
    print(f"  (Resume session for spoof test: {resp.status_code})")
    
    # STRANGER token with actor=coach&by=<coach_tg> (spoofing)
    resp = requests.patch(f"{BASE_URL}/sessions/{session_id}/exercise/0/set/2",
                         json={"done": True},
                         params={"actor": "coach", "by": coach_tg},
                         headers={"Authorization": f"Bearer {stranger_token}"})
    print(f"  PATCH set actor=coach&by={{coach}} (stranger token): {resp.status_code}")
    results.append(("5", "SPOOF: stranger with actor=coach&by=coach", 403, resp.status_code))
    
    # ========== TEST 6: NOT-A-COACH CONFIRM -> 403 ==========
    print("\n[TEST 6] NOT-A-COACH CONFIRM -> 403")
    
    # Owner (not a coach) tries to confirm
    resp = requests.post(f"{BASE_URL}/sessions/{session_id}/confirm",
                        json={"coach_telegram_id": owner_tg},
                        headers={"Authorization": f"Bearer {owner_token}"})
    print(f"  POST confirm with owner as coach (owner token): {resp.status_code}")
    results.append(("6a", "Owner confirm (not a coach)", 403, resp.status_code))
    
    # Stranger coach (not linked) tries to confirm
    resp = requests.post(f"{BASE_URL}/sessions/{session_id}/confirm",
                        json={"coach_telegram_id": stranger_tg},
                        headers={"Authorization": f"Bearer {stranger_token}"})
    print(f"  POST confirm with stranger coach (stranger token): {resp.status_code}")
    results.append(("6b", "Stranger coach confirm (not linked)", 403, resp.status_code))
    
    # ========== TEST 7: COACH-LED START MISMATCH -> 403 ==========
    print("\n[TEST 7] COACH-LED START MISMATCH -> 403")
    
    # Finish current session first
    resp = requests.post(f"{BASE_URL}/sessions/{session_id}/finish",
                        headers={"Authorization": f"Bearer {owner_token}"})
    print(f"  (Finish session for coach-led test: {resp.status_code})")
    
    # Owner tries to start with coach_telegram_id (caller != coach_telegram_id)
    session_id2, status = start_session(owner_token, plan_id, owner_tg, 1, day_index, 
                                       date="2026-06-21", coach_tg=coach_tg)
    print(f"  POST /sessions/start with coach_telegram_id (owner token): {status}")
    results.append(("7", "Coach-led start mismatch", 403, status))
    
    # ========== TEST 8: REGRESSION (owner happy-path) ==========
    print("\n[TEST 8] REGRESSION (owner happy-path still works)")
    
    # Resume the finished session
    resp = requests.post(f"{BASE_URL}/sessions/{session_id}/resume",
                        headers={"Authorization": f"Bearer {owner_token}"})
    print(f"  POST /sessions/{{id}}/resume (owner): {resp.status_code}")
    results.append(("8a", "Resume session owner", 200, resp.status_code))
    
    # Per-set log
    resp = requests.patch(f"{BASE_URL}/sessions/{session_id}/exercise/1/set/0",
                         json={"done": True, "weight": 100, "reps": 5},
                         headers={"Authorization": f"Bearer {owner_token}"})
    print(f"  PATCH set (owner): {resp.status_code}")
    results.append(("8b", "Per-set log owner", 200, resp.status_code))
    
    # Finish
    resp = requests.post(f"{BASE_URL}/sessions/{session_id}/finish",
                        headers={"Authorization": f"Bearer {owner_token}"})
    print(f"  POST finish (owner): {resp.status_code}")
    results.append(("8c", "Finish owner", 200, resp.status_code))
    
    # GET session with frozen stats
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}",
                       headers={"Authorization": f"Bearer {owner_token}"})
    print(f"  GET /sessions/{{id}} (owner): {resp.status_code}")
    results.append(("8d", "GET session with stats owner", 200, resp.status_code))
    if resp.status_code == 200:
        data = resp.json()
        assert "stats" in data, "Stats not present in finished session"
        assert data["status"] == "finished", f"Session not finished: {data['status']}"
        print(f"    ✓ Session finished with stats (progress_pct={data['stats'].get('progress_pct')})")
    
    # ========== DEVIATION ENDPOINT AUTH ==========
    print("\n[DEVIATION ENDPOINT AUTH]")
    
    # No token -> 401
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}/deviation")
    print(f"  GET /sessions/{{id}}/deviation (no token): {resp.status_code}")
    results.append(("9a", "GET deviation no token", 401, resp.status_code))
    
    # Stranger -> 403
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}/deviation",
                       headers={"Authorization": f"Bearer {stranger_token}"})
    print(f"  GET /sessions/{{id}}/deviation (stranger): {resp.status_code}")
    results.append(("9b", "GET deviation stranger", 403, resp.status_code))
    
    # Owner -> 200
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}/deviation",
                       headers={"Authorization": f"Bearer {owner_token}"})
    print(f"  GET /sessions/{{id}}/deviation (owner): {resp.status_code}")
    results.append(("9c", "GET deviation owner", 200, resp.status_code))
    
    # ========== SUMMARY ==========
    print("\n" + "=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for test_id, desc, expected, actual in results:
        status = "✅ PASS" if expected == actual else "❌ FAIL"
        if expected == actual:
            passed += 1
        else:
            failed += 1
        print(f"{status} [{test_id}] {desc}: expected {expected}, got {actual}")
    
    print(f"\n{'='*80}")
    print(f"TOTAL: {passed} passed, {failed} failed out of {len(results)} tests")
    print(f"{'='*80}\n")
    
    if failed > 0:
        print("❌ PHASE 4 TESTS FAILED")
        sys.exit(1)
    else:
        print("✅ PHASE 4 TESTS PASSED")
        sys.exit(0)

if __name__ == "__main__":
    main()
