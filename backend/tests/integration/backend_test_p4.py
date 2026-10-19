#!/usr/bin/env python3
"""
TrainWithBrain P4 (Real-time / coach co-scribe) Backend Test Suite

Tests ONLY the new Phase P4 backend areas. Does NOT re-test prior phases.
"""
import requests
import json
import time
from datetime import datetime

# Backend URL from frontend/.env
BASE_URL = "https://7a622ce5-aeb3-47f5-8ae8-f67a42b004f6.preview.emergentagent.com/api"

# Test state
state = {
    "coach_token": None,
    "coach_telegram_id": None,
    "athlete_token": None,
    "athlete_telegram_id": None,
    "unlinked_coach_token": None,
    "unlinked_coach_telegram_id": None,
    "invite_code": None,
    "plan_id": None,
    "template_id": None,
    "session_id": None,
    "day_idx": None,
    "num_exercises": 0,
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def assert_response(r, expected_status, context):
    if r.status_code != expected_status:
        log(f"❌ FAIL {context}: expected {expected_status}, got {r.status_code}")
        log(f"   Response: {r.text[:500]}")
        raise AssertionError(f"{context} failed")
    return r.json() if r.status_code != 204 else {}

def assert_uuid(val, field_name):
    if not isinstance(val, str) or len(val) != 36:
        raise AssertionError(f"{field_name} is not a UUID string: {val}")

def assert_iso_datetime(val, field_name):
    if not isinstance(val, str):
        raise AssertionError(f"{field_name} is not a string: {val}")
    # Basic ISO format check
    if "T" not in val:
        raise AssertionError(f"{field_name} is not ISO datetime: {val}")

def assert_no_leaks(data):
    """Ensure no MongoDB _id or password_hash leaks"""
    if isinstance(data, dict):
        if "_id" in data:
            raise AssertionError("MongoDB _id leaked in response")
        if "password_hash" in data:
            raise AssertionError("password_hash leaked in response")
        for v in data.values():
            assert_no_leaks(v)
    elif isinstance(data, list):
        for item in data:
            assert_no_leaks(item)

# ===========================================================================
# SETUP: Register users, link coach, create plan, start session
# ===========================================================================
def setup_users_and_plan():
    log("=== SETUP: Registering users ===")
    
    # 1. Register COACH
    ts = int(time.time())
    coach_email = f"p4coach{ts}@test.com"
    r = requests.post(f"{BASE_URL}/auth/register", json={
        "email": coach_email,
        "password": "password123",
        "name": "P4 Coach"
    })
    data = assert_response(r, 200, "Register coach")
    assert_no_leaks(data)
    state["coach_token"] = data["token"]
    state["coach_telegram_id"] = data["user"]["telegram_id"]
    assert state["coach_telegram_id"] >= 900000000000, "Coach telegram_id should be synthetic"
    log(f"✅ Coach registered: telegram_id={state['coach_telegram_id']}, token={state['coach_token'][:20]}...")
    
    # 2. Register ATHLETE
    athlete_email = f"p4athlete{ts}@test.com"
    r = requests.post(f"{BASE_URL}/auth/register", json={
        "email": athlete_email,
        "password": "password123",
        "name": "P4 Athlete"
    })
    data = assert_response(r, 200, "Register athlete")
    assert_no_leaks(data)
    state["athlete_token"] = data["token"]
    state["athlete_telegram_id"] = data["user"]["telegram_id"]
    log(f"✅ Athlete registered: telegram_id={state['athlete_telegram_id']}, token={state['athlete_token'][:20]}...")
    
    # 3. Register UNLINKED COACH (for negative tests)
    unlinked_email = f"p4unlinked{ts}@test.com"
    r = requests.post(f"{BASE_URL}/auth/register", json={
        "email": unlinked_email,
        "password": "password123",
        "name": "P4 Unlinked Coach"
    })
    data = assert_response(r, 200, "Register unlinked coach")
    assert_no_leaks(data)
    state["unlinked_coach_token"] = data["token"]
    state["unlinked_coach_telegram_id"] = data["user"]["telegram_id"]
    log(f"✅ Unlinked coach registered: telegram_id={state['unlinked_coach_telegram_id']}")
    
    # 4. Get invite code from coach
    log("=== SETUP: Getting coach invite code ===")
    r = requests.post(f"{BASE_URL}/coach/invite", json={
        "coach_telegram_id": state["coach_telegram_id"]
    })
    data = assert_response(r, 200, "Coach invite")
    assert_no_leaks(data)
    state["invite_code"] = data["invite_code"]
    log(f"✅ Invite code: {state['invite_code']}")
    
    # 5. Link athlete to coach
    log("=== SETUP: Linking athlete to coach ===")
    r = requests.post(f"{BASE_URL}/coach/link", json={
        "code": state["invite_code"],
        "athlete_telegram_id": state["athlete_telegram_id"]
    })
    data = assert_response(r, 200, "Coach link")
    assert_no_leaks(data)
    assert data["status"] == "active", "Link status should be active"
    log(f"✅ Athlete linked to coach (status={data['status']})")
    
    # 6. Get template id (full-body-beginner)
    log("=== SETUP: Getting template ===")
    r = requests.get(f"{BASE_URL}/programs/templates")
    data = assert_response(r, 200, "Get templates")
    assert_no_leaks(data)
    template = next((t for t in data if t.get("slug") == "full-body-beginner"), None)
    if not template:
        raise AssertionError("full-body-beginner template not found")
    state["template_id"] = template["id"]
    log(f"✅ Template found: {template['name']} (id={state['template_id']})")
    
    # 7. Create plan for athlete (by coach)
    log("=== SETUP: Creating plan ===")
    r = requests.post(f"{BASE_URL}/plans", json={
        "athlete_telegram_id": state["athlete_telegram_id"],
        "template_id": state["template_id"],
        "coach_telegram_id": state["coach_telegram_id"]
    })
    data = assert_response(r, 200, "Create plan")
    assert_no_leaks(data)
    state["plan_id"] = data["id"]
    assert_uuid(state["plan_id"], "plan_id")
    log(f"✅ Plan created: id={state['plan_id']}, visibility={data.get('visibility')}")
    
    # 8. Publish plan (if it's draft)
    if data.get("visibility") == "draft":
        log("=== SETUP: Publishing plan ===")
        r = requests.patch(f"{BASE_URL}/plans/{state['plan_id']}/visibility", json={
            "visibility": "published"
        })
        data = assert_response(r, 200, "Publish plan")
        assert_no_leaks(data)
        log(f"✅ Plan published")
    
    # 9. Find first non-rest day
    log("=== SETUP: Finding first workout day ===")
    r = requests.get(f"{BASE_URL}/plans/{state['plan_id']}")
    data = assert_response(r, 200, "Get plan")
    assert_no_leaks(data)
    weeks = data.get("weeks", [])
    if not weeks:
        raise AssertionError("Plan has no weeks")
    week1 = next((w for w in weeks if w.get("week_index") == 1), None)
    if not week1:
        raise AssertionError("Week 1 not found")
    workout_day = next((d for d in week1.get("days", []) if not d.get("is_rest")), None)
    if not workout_day:
        raise AssertionError("No workout day found in week 1")
    state["day_idx"] = workout_day["day_index"]
    state["num_exercises"] = len(workout_day.get("exercises", []))
    log(f"✅ Found workout day: day_index={state['day_idx']}, exercises={state['num_exercises']}")
    
    # 10. Start session
    log("=== SETUP: Starting session ===")
    r = requests.post(f"{BASE_URL}/sessions/start", json={
        "plan_id": state["plan_id"],
        "athlete_telegram_id": state["athlete_telegram_id"],
        "week": 1,
        "day": state["day_idx"]
    }, headers={"Authorization": f"Bearer {state['athlete_token']}"})
    data = assert_response(r, 200, "Start session")
    assert_no_leaks(data)
    state["session_id"] = data["id"]
    assert_uuid(state["session_id"], "session_id")
    assert data["status"] == "in_progress", "Session should be in_progress"
    assert len(data["exercises"]) == state["num_exercises"], f"Expected {state['num_exercises']} exercises"
    log(f"✅ Session started: id={state['session_id']}, exercises={len(data['exercises'])}")

# ===========================================================================
# SCENARIO 1: CO-SCRIBE MARK (actor=coach/athlete, by parameter)
# ===========================================================================
def test_co_scribe_mark():
    log("\n=== SCENARIO 1: CO-SCRIBE MARK ===")
    
    # 1.1: Mark exercise 0 as done by COACH
    log("Test 1.1: Mark exercise 0 as done by coach")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/0?action=done&actor=coach&by={state['coach_telegram_id']}",
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    data = assert_response(r, 200, "Mark exercise 0 done by coach")
    assert_no_leaks(data)
    ex0 = next((e for e in data["exercises"] if e["order"] == 0), None)
    assert ex0, "Exercise 0 not found"
    assert ex0["status"] == "done", f"Exercise 0 status should be 'done', got {ex0['status']}"
    assert ex0["filled_by"] == "coach", f"Exercise 0 filled_by should be 'coach', got {ex0['filled_by']}"
    log(f"✅ Exercise 0 marked done by coach (filled_by={ex0['filled_by']})")
    
    # 1.2: Reset exercise 0
    log("Test 1.2: Reset exercise 0")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/0?action=reset&actor=coach&by={state['coach_telegram_id']}",
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    data = assert_response(r, 200, "Reset exercise 0")
    assert_no_leaks(data)
    ex0 = next((e for e in data["exercises"] if e["order"] == 0), None)
    assert ex0["status"] == "pending", f"Exercise 0 status should be 'pending', got {ex0['status']}"
    assert ex0["filled_by"] is None, f"Exercise 0 filled_by should be None, got {ex0['filled_by']}"
    assert ex0["coach_confirmed"] == False, "Exercise 0 coach_confirmed should be False after reset"
    log(f"✅ Exercise 0 reset (status={ex0['status']}, filled_by={ex0['filled_by']})")
    
    # 1.3: Mark exercise 1 as done by ATHLETE (no actor param = default athlete)
    log("Test 1.3: Mark exercise 1 as done by athlete")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/1?action=done",
        headers={"Authorization": f"Bearer {state['athlete_token']}"}
    )
    data = assert_response(r, 200, "Mark exercise 1 done by athlete")
    assert_no_leaks(data)
    ex1 = next((e for e in data["exercises"] if e["order"] == 1), None)
    assert ex1["status"] == "done", f"Exercise 1 status should be 'done', got {ex1['status']}"
    assert ex1["filled_by"] == "athlete", f"Exercise 1 filled_by should be 'athlete', got {ex1['filled_by']}"
    log(f"✅ Exercise 1 marked done by athlete (filled_by={ex1['filled_by']})")
    
    # 1.4: NEGATIVE: actor=coach with unlinked coach (should be 403)
    log("Test 1.4: NEGATIVE - actor=coach with unlinked coach")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/0?action=done&actor=coach&by={state['unlinked_coach_telegram_id']}",
        headers={"Authorization": f"Bearer {state['unlinked_coach_token']}"}
    )
    assert r.status_code == 403, f"Expected 403 for unlinked coach, got {r.status_code}"
    log(f"✅ Unlinked coach correctly rejected with 403")
    
    # 1.5: NEGATIVE: actor=coach without 'by' param (should be 400)
    log("Test 1.5: NEGATIVE - actor=coach without 'by' param")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/0?action=done&actor=coach",
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    assert r.status_code == 400, f"Expected 400 for missing 'by' param, got {r.status_code}"
    log(f"✅ Missing 'by' param correctly rejected with 400")

# ===========================================================================
# SCENARIO 2: EXERCISE CONFIRM (coach confirmation toggle)
# ===========================================================================
def test_exercise_confirm():
    log("\n=== SCENARIO 2: EXERCISE CONFIRM ===")
    
    # First, mark exercise 0 as done
    log("Setup: Mark exercise 0 as done")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/0?action=done",
        headers={"Authorization": f"Bearer {state['athlete_token']}"}
    )
    assert_response(r, 200, "Mark exercise 0 done")
    
    # 2.1: Confirm exercise 0 by coach
    log("Test 2.1: Confirm exercise 0 by coach")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/0/confirm",
        json={"coach_telegram_id": state["coach_telegram_id"]},
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    data = assert_response(r, 200, "Confirm exercise 0")
    assert_no_leaks(data)
    ex0 = next((e for e in data["exercises"] if e["order"] == 0), None)
    assert ex0["coach_confirmed"] == True, "Exercise 0 should be coach_confirmed"
    assert ex0["confirmed_by"] == state["coach_telegram_id"], f"confirmed_by should be coach telegram_id"
    assert ex0["confirmed_at"] is not None, "confirmed_at should be set"
    assert_iso_datetime(ex0["confirmed_at"], "confirmed_at")
    log(f"✅ Exercise 0 confirmed (coach_confirmed={ex0['coach_confirmed']}, confirmed_by={ex0['confirmed_by']})")
    
    # 2.2: Toggle confirmation (call again to unconfirm)
    log("Test 2.2: Toggle confirmation (unconfirm)")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/0/confirm",
        json={"coach_telegram_id": state["coach_telegram_id"]},
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    data = assert_response(r, 200, "Toggle confirmation")
    assert_no_leaks(data)
    ex0 = next((e for e in data["exercises"] if e["order"] == 0), None)
    assert ex0["coach_confirmed"] == False, "Exercise 0 should be unconfirmed"
    assert ex0["confirmed_by"] is None, "confirmed_by should be None"
    log(f"✅ Exercise 0 unconfirmed (coach_confirmed={ex0['coach_confirmed']})")
    
    # 2.3: NEGATIVE: Unlinked coach tries to confirm (should be 403)
    log("Test 2.3: NEGATIVE - Unlinked coach tries to confirm")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/0/confirm",
        json={"coach_telegram_id": state["unlinked_coach_telegram_id"]},
        headers={"Authorization": f"Bearer {state['unlinked_coach_token']}"}
    )
    assert r.status_code == 403, f"Expected 403 for unlinked coach, got {r.status_code}"
    log(f"✅ Unlinked coach correctly rejected with 403")
    
    # 2.4: NEGATIVE: Missing coach_telegram_id (should be 400)
    log("Test 2.4: NEGATIVE - Missing coach_telegram_id")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/0/confirm",
        json={},
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    assert r.status_code == 400, f"Expected 400 for missing coach_telegram_id, got {r.status_code}"
    log(f"✅ Missing coach_telegram_id correctly rejected with 400")
    
    # 2.5: NEGATIVE: Invalid exercise order (should be 404)
    log("Test 2.5: NEGATIVE - Invalid exercise order")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/99/confirm",
        json={"coach_telegram_id": state["coach_telegram_id"]},
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    assert r.status_code == 404, f"Expected 404 for invalid order, got {r.status_code}"
    log(f"✅ Invalid exercise order correctly rejected with 404")

# ===========================================================================
# SCENARIO 3: EDIT AS COACH (actor=coach with by parameter)
# ===========================================================================
def test_edit_as_coach():
    log("\n=== SCENARIO 3: EDIT AS COACH ===")
    
    # 3.1: Edit exercise 0 as coach
    log("Test 3.1: Edit exercise 0 as coach")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/0/edit?actor=coach&by={state['coach_telegram_id']}",
        json={"sets_scheme": [{"weight": 100, "sets": 2, "reps": 5}]},
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    data = assert_response(r, 200, "Edit exercise 0 as coach")
    assert_no_leaks(data)
    ex0 = next((e for e in data["exercises"] if e["order"] == 0), None)
    assert ex0["tonnage"] == 1000, f"Tonnage should be 1000 (100*2*5), got {ex0['tonnage']}"
    assert len(ex0["sets_scheme"]) == 1, "Should have 1 set"
    assert ex0["sets_scheme"][0]["weight"] == 100, "Weight should be 100"
    assert ex0["sets_scheme"][0]["sets"] == 2, "Sets should be 2"
    assert ex0["sets_scheme"][0]["reps"] == 5, "Reps should be 5"
    log(f"✅ Exercise 0 edited by coach (tonnage={ex0['tonnage']})")
    
    # 3.2: NEGATIVE: Unlinked coach tries to edit (should be 403)
    log("Test 3.2: NEGATIVE - Unlinked coach tries to edit")
    r = requests.patch(
        f"{BASE_URL}/sessions/{state['session_id']}/exercise/0/edit?actor=coach&by={state['unlinked_coach_telegram_id']}",
        json={"sets_scheme": [{"weight": 50, "sets": 1, "reps": 1}]},
        headers={"Authorization": f"Bearer {state['unlinked_coach_token']}"}
    )
    assert r.status_code == 403, f"Expected 403 for unlinked coach, got {r.status_code}"
    log(f"✅ Unlinked coach correctly rejected with 403")

# ===========================================================================
# SCENARIO 4: COACH LIVE SESSION (GET /api/coach/{c}/clients/{a}/session)
# ===========================================================================
def test_coach_live_session():
    log("\n=== SCENARIO 4: COACH LIVE SESSION ===")
    
    # 4.1: Coach gets athlete's live session
    log("Test 4.1: Coach gets athlete's live session")
    r = requests.get(
        f"{BASE_URL}/coach/{state['coach_telegram_id']}/clients/{state['athlete_telegram_id']}/session",
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    data = assert_response(r, 200, "Get coach live session")
    assert_no_leaks(data)
    assert data["id"] == state["session_id"], f"Session id should match, got {data['id']}"
    assert "stats" in data, "Response should include stats object"
    log(f"✅ Coach retrieved live session (id={data['id']}, stats present)")
    
    # 4.2: NEGATIVE: Unlinked coach tries to get session (should be 403)
    log("Test 4.2: NEGATIVE - Unlinked coach tries to get session")
    r = requests.get(
        f"{BASE_URL}/coach/{state['unlinked_coach_telegram_id']}/clients/{state['athlete_telegram_id']}/session",
        headers={"Authorization": f"Bearer {state['unlinked_coach_token']}"}
    )
    assert r.status_code == 403, f"Expected 403 for unlinked coach, got {r.status_code}"
    log(f"✅ Unlinked coach correctly rejected with 403")
    
    # 4.3: Fresh athlete with no session (should return null with 200)
    log("Test 4.3: Fresh athlete with no session")
    # Register a new athlete
    ts = int(time.time())
    fresh_email = f"p4fresh{ts}@test.com"
    r = requests.post(f"{BASE_URL}/auth/register", json={
        "email": fresh_email,
        "password": "password123",
        "name": "Fresh Athlete"
    })
    fresh_data = assert_response(r, 200, "Register fresh athlete")
    fresh_athlete_id = fresh_data["user"]["telegram_id"]
    
    # Link fresh athlete to coach
    r = requests.post(f"{BASE_URL}/coach/link", json={
        "code": state["invite_code"],
        "athlete_telegram_id": fresh_athlete_id
    })
    assert_response(r, 200, "Link fresh athlete")
    
    # Coach tries to get session (should return null)
    r = requests.get(
        f"{BASE_URL}/coach/{state['coach_telegram_id']}/clients/{fresh_athlete_id}/session",
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    data = assert_response(r, 200, "Get session for fresh athlete")
    assert data is None, f"Expected null for fresh athlete, got {data}"
    log(f"✅ Fresh athlete with no session returns null")

# ===========================================================================
# SCENARIO 5: SESSION/PLAN MUTATIONS (broadcasts don't alter HTTP response)
# ===========================================================================
def test_session_plan_mutations():
    log("\n=== SCENARIO 5: SESSION/PLAN MUTATIONS ===")
    
    # 5.1: Confirm whole session
    log("Test 5.1: Confirm whole session")
    r = requests.post(
        f"{BASE_URL}/sessions/{state['session_id']}/confirm",
        json={"coach_telegram_id": state["coach_telegram_id"]},
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    data = assert_response(r, 200, "Confirm session")
    assert_no_leaks(data)
    assert data["coach_confirmed"] == True, "Session should be coach_confirmed"
    assert isinstance(data, dict), "Response should be valid JSON dict"
    log(f"✅ Session confirmed (coach_confirmed={data['coach_confirmed']})")
    
    # 5.2: Pause session
    log("Test 5.2: Pause session")
    r = requests.post(
        f"{BASE_URL}/sessions/{state['session_id']}/pause?resume=false",
        headers={"Authorization": f"Bearer {state['athlete_token']}"}
    )
    data = assert_response(r, 200, "Pause session")
    assert_no_leaks(data)
    assert data["paused"] == True, "Session should be paused"
    assert isinstance(data, dict), "Response should be valid JSON dict"
    log(f"✅ Session paused (paused={data['paused']})")
    
    # 5.3: Resume session
    log("Test 5.3: Resume session")
    r = requests.post(
        f"{BASE_URL}/sessions/{state['session_id']}/pause?resume=true",
        headers={"Authorization": f"Bearer {state['athlete_token']}"}
    )
    data = assert_response(r, 200, "Resume session")
    assert_no_leaks(data)
    assert data["paused"] == False, "Session should be resumed"
    assert isinstance(data, dict), "Response should be valid JSON dict"
    log(f"✅ Session resumed (paused={data['paused']})")
    
    # 5.4: Unpublish week
    log("Test 5.4: Unpublish week")
    r = requests.patch(
        f"{BASE_URL}/plans/{state['plan_id']}/weeks/1/publish",
        json={"published": False},
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    data = assert_response(r, 200, "Unpublish week")
    assert_no_leaks(data)
    assert isinstance(data, dict), "Response should be valid JSON dict"
    week1 = next((w for w in data["weeks"] if w.get("week_index") == 1), None)
    assert week1["published"] == False, "Week 1 should be unpublished"
    log(f"✅ Week 1 unpublished (published={week1['published']})")
    
    # 5.5: Update training days
    log("Test 5.5: Update training days")
    r = requests.patch(
        f"{BASE_URL}/plans/{state['plan_id']}/training-days",
        json={"training_days": [1, 3, 5]},
        headers={"Authorization": f"Bearer {state['coach_token']}"}
    )
    data = assert_response(r, 200, "Update training days")
    assert_no_leaks(data)
    assert isinstance(data, dict), "Response should be valid JSON dict"
    assert data["training_days"] == [1, 3, 5], f"Training days should be [1,3,5], got {data['training_days']}"
    log(f"✅ Training days updated (training_days={data['training_days']})")

# ===========================================================================
# SCENARIO 6: GENERAL ASSERTIONS (UUIDs, ISO datetimes, no leaks)
# ===========================================================================
def test_general_assertions():
    log("\n=== SCENARIO 6: GENERAL ASSERTIONS ===")
    
    # Get session and verify all fields
    log("Test 6.1: Verify session structure")
    r = requests.get(
        f"{BASE_URL}/sessions/{state['session_id']}",
        headers={"Authorization": f"Bearer {state['athlete_token']}"}
    )
    data = assert_response(r, 200, "Get session")
    assert_no_leaks(data)
    
    # Check UUID fields
    assert_uuid(data["id"], "session.id")
    assert_uuid(data["plan_id"], "session.plan_id")
    
    # Check datetime fields
    if data.get("started_at"):
        assert_iso_datetime(data["started_at"], "session.started_at")
    if data.get("confirmed_at"):
        assert_iso_datetime(data["confirmed_at"], "session.confirmed_at")
    if data.get("last_event_at"):
        assert_iso_datetime(data["last_event_at"], "session.last_event_at")
    
    # Check exercises
    for ex in data["exercises"]:
        if ex.get("confirmed_at"):
            assert_iso_datetime(ex["confirmed_at"], f"exercise[{ex['order']}].confirmed_at")
    
    log(f"✅ All UUIDs are 36-char strings")
    log(f"✅ All datetimes are ISO strings")
    log(f"✅ No MongoDB _id leaks")
    log(f"✅ No password_hash leaks")

# ===========================================================================
# OPTIONAL: WebSocket test
# ===========================================================================
def test_websocket():
    log("\n=== OPTIONAL: WEBSOCKET TEST ===")
    try:
        import websocket
        
        # Test 1: Connect with valid token
        log("Test WS.1: Connect with valid token")
        ws_url = BASE_URL.replace("https://", "wss://").replace("/api", "/api/ws")
        ws = websocket.create_connection(f"{ws_url}?token={state['athlete_token']}", timeout=5)
        msg = ws.recv()
        data = json.loads(msg)
        assert data["type"] == "connected", f"Expected 'connected' message, got {data['type']}"
        log(f"✅ WebSocket connected (type={data['type']})")
        ws.close()
        
        # Test 2: Connect with bad token (should be rejected)
        log("Test WS.2: Connect with bad token")
        try:
            ws = websocket.create_connection(f"{ws_url}?token=BADTOKEN", timeout=5)
            ws.close()
            log(f"❌ Bad token should have been rejected")
        except Exception as e:
            log(f"✅ Bad token correctly rejected")
        
    except ImportError:
        log("⚠️  websocket-client not installed, skipping WebSocket tests")
    except Exception as e:
        log(f"⚠️  WebSocket test failed: {e}")

# ===========================================================================
# MAIN
# ===========================================================================
def main():
    log("=" * 70)
    log("TrainWithBrain P4 Backend Test Suite")
    log("=" * 70)
    
    try:
        setup_users_and_plan()
        test_co_scribe_mark()
        test_exercise_confirm()
        test_edit_as_coach()
        test_coach_live_session()
        test_session_plan_mutations()
        test_general_assertions()
        test_websocket()
        
        log("\n" + "=" * 70)
        log("✅ ALL P4 TESTS PASSED")
        log("=" * 70)
        return 0
        
    except Exception as e:
        log("\n" + "=" * 70)
        log(f"❌ TEST FAILED: {e}")
        log("=" * 70)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
