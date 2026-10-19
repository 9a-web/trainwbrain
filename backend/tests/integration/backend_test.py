#!/usr/bin/env python3
"""
Backend API tests for TrainWithBrain - Phase 3 Coach Mode
Tests ONLY the new P3 endpoints as specified in test_result.md
"""
import requests
import json
import sys
from datetime import datetime

# Read backend URL from frontend/.env
with open('/app/frontend/.env', 'r') as f:
    for line in f:
        if line.startswith('REACT_APP_BACKEND_URL='):
            BACKEND_URL = line.strip().split('=', 1)[1]
            break

API_BASE = f"{BACKEND_URL}/api"
print(f"Testing backend at: {API_BASE}\n")

# Test counters
tests_passed = 0
tests_failed = 0
test_results = []

def test(name, fn):
    """Run a test and track results"""
    global tests_passed, tests_failed
    try:
        fn()
        tests_passed += 1
        test_results.append(f"✅ {name}")
        print(f"✅ {name}")
    except AssertionError as e:
        tests_failed += 1
        test_results.append(f"❌ {name}: {str(e)}")
        print(f"❌ {name}: {str(e)}")
    except Exception as e:
        tests_failed += 1
        test_results.append(f"❌ {name}: {type(e).__name__}: {str(e)}")
        print(f"❌ {name}: {type(e).__name__}: {str(e)}")

def assert_eq(actual, expected, msg=""):
    """Assert equality with helpful message"""
    if actual != expected:
        raise AssertionError(f"{msg}: expected {expected}, got {actual}")

def assert_in(item, container, msg=""):
    """Assert item in container"""
    if item not in container:
        raise AssertionError(f"{msg}: {item} not in {container}")

def assert_true(condition, msg=""):
    """Assert condition is true"""
    if not condition:
        raise AssertionError(msg)

def assert_status(response, expected_status, msg=""):
    """Assert HTTP status code"""
    if response.status_code != expected_status:
        raise AssertionError(f"{msg}: expected status {expected_status}, got {response.status_code}. Response: {response.text[:200]}")

# ============================================================================
# SETUP: Create test users
# ============================================================================
print("=" * 80)
print("SETUP: Creating test users")
print("=" * 80)

# Create coach user (telegram_id=701001)
coach_data = {
    "telegram_id": 701001,
    "first_name": "Coach",
    "last_name": "Smith",
    "username": "coach_smith"
}
r = requests.post(f"{API_BASE}/users", json=coach_data)
assert_status(r, 200, "Create coach user")
coach_user = r.json()
print(f"✓ Created coach user: telegram_id={coach_user['telegram_id']}, name={coach_user['first_name']}")

# Create athlete user (telegram_id=701002)
athlete_data = {
    "telegram_id": 701002,
    "first_name": "Sam",
    "last_name": "Athlete",
    "username": "sam_athlete"
}
r = requests.post(f"{API_BASE}/users", json=athlete_data)
assert_status(r, 200, "Create athlete user")
athlete_user = r.json()
print(f"✓ Created athlete user: telegram_id={athlete_user['telegram_id']}, name={athlete_user['first_name']}")

# Create unlinked coach user (telegram_id=701003)
unlinked_coach_data = {
    "telegram_id": 701003,
    "first_name": "Unlinked",
    "last_name": "Coach",
    "username": "unlinked_coach"
}
r = requests.post(f"{API_BASE}/users", json=unlinked_coach_data)
assert_status(r, 200, "Create unlinked coach user")
unlinked_coach_user = r.json()
print(f"✓ Created unlinked coach user: telegram_id={unlinked_coach_user['telegram_id']}, name={unlinked_coach_user['first_name']}")

print()

# ============================================================================
# TEST 1: PATCH /api/users/{telegram_id}/mode - Role/mode switch
# ============================================================================
print("=" * 80)
print("TEST 1: PATCH /api/users/{telegram_id}/mode - Role/mode switch")
print("=" * 80)

def test_1_1_switch_to_coach():
    """Switch user 701001 to coach mode"""
    r = requests.patch(f"{API_BASE}/users/701001/mode", json={"mode": "coach"})
    assert_status(r, 200, "Switch to coach mode")
    user = r.json()
    assert_in("athlete", user.get("roles", []), "roles should include 'athlete'")
    assert_in("coach", user.get("roles", []), "roles should include 'coach'")
    assert_eq(user.get("active_mode"), "coach", "active_mode should be 'coach'")
    assert_true(user.get("invite_code"), "invite_code should be present")
    assert_true(len(user.get("invite_code", "")) == 8, "invite_code should be 8 chars")
    global coach_invite_code
    coach_invite_code = user.get("invite_code")

test(1.1, test_1_1_switch_to_coach)

def test_1_2_invalid_mode():
    """Invalid mode should return 400"""
    r = requests.patch(f"{API_BASE}/users/701001/mode", json={"mode": "bad"})
    assert_status(r, 400, "Invalid mode should return 400")

test(1.2, test_1_2_invalid_mode)

def test_1_3_unknown_user():
    """Unknown user should return 404"""
    r = requests.patch(f"{API_BASE}/users/999999/mode", json={"mode": "coach"})
    assert_status(r, 404, "Unknown user should return 404")

test(1.3, test_1_3_unknown_user)

def test_1_4_switch_back_to_athlete():
    """Switch back to athlete mode keeps coach role"""
    r = requests.patch(f"{API_BASE}/users/701001/mode", json={"mode": "athlete"})
    assert_status(r, 200, "Switch back to athlete mode")
    user = r.json()
    assert_in("athlete", user.get("roles", []), "roles should still include 'athlete'")
    assert_in("coach", user.get("roles", []), "roles should still include 'coach'")
    assert_eq(user.get("active_mode"), "athlete", "active_mode should be 'athlete'")
    # Switch back to coach for remaining tests
    requests.patch(f"{API_BASE}/users/701001/mode", json={"mode": "coach"})

test(1.4, test_1_4_switch_back_to_athlete)

print()

# ============================================================================
# TEST 2: POST /api/coach/invite - Generate invite code
# ============================================================================
print("=" * 80)
print("TEST 2: POST /api/coach/invite - Generate invite code")
print("=" * 80)

def test_2_1_generate_invite():
    """Generate invite code for coach"""
    r = requests.post(f"{API_BASE}/coach/invite", json={"coach_telegram_id": 701001})
    assert_status(r, 200, "Generate invite code")
    data = r.json()
    assert_true(data.get("invite_code"), "invite_code should be present")
    assert_true(data.get("deep_link"), "deep_link should be present")
    assert_true(data.get("bot_username"), "bot_username should be present")
    global first_invite_code
    first_invite_code = data.get("invite_code")

test(2.1, test_2_1_generate_invite)

def test_2_2_stable_invite_code():
    """Second call returns SAME invite code"""
    r = requests.post(f"{API_BASE}/coach/invite", json={"coach_telegram_id": 701001})
    assert_status(r, 200, "Second invite call")
    data = r.json()
    assert_eq(data.get("invite_code"), first_invite_code, "invite_code should be stable")

test(2.2, test_2_2_stable_invite_code)

print()

# ============================================================================
# TEST 3: POST /api/coach/link - Link athlete to coach
# ============================================================================
print("=" * 80)
print("TEST 3: POST /api/coach/link - Link athlete to coach")
print("=" * 80)

def test_3_1_link_athlete():
    """Link athlete 701002 to coach 701001"""
    r = requests.post(f"{API_BASE}/coach/link", json={
        "code": first_invite_code,
        "athlete_telegram_id": 701002
    })
    assert_status(r, 200, "Link athlete to coach")
    data = r.json()
    assert_eq(data.get("status"), "active", "status should be 'active'")
    assert_true(data.get("coach"), "coach brief should be present")
    assert_eq(data["coach"]["telegram_id"], 701001, "coach telegram_id should be 701001")

test(3.1, test_3_1_link_athlete)

def test_3_2_unknown_code():
    """Unknown code should return 404"""
    r = requests.post(f"{API_BASE}/coach/link", json={
        "code": "BADCODE1",
        "athlete_telegram_id": 701002
    })
    assert_status(r, 404, "Unknown code should return 404")

test(3.2, test_3_2_unknown_code)

def test_3_3_self_link():
    """Self-link should return 400"""
    r = requests.post(f"{API_BASE}/coach/link", json={
        "code": first_invite_code,
        "athlete_telegram_id": 701001
    })
    assert_status(r, 400, "Self-link should return 400")

test(3.3, test_3_3_self_link)

def test_3_4_verify_athlete_coach_field():
    """Verify athlete has coach via /athlete/{id}/coach endpoint"""
    r = requests.get(f"{API_BASE}/athlete/701002/coach")
    assert_status(r, 200, "Get athlete's coach")
    data = r.json()
    assert_true(data.get("coach"), "coach should be present")
    assert_eq(data["coach"]["telegram_id"], 701001, "coach telegram_id should be 701001")

test(3.4, test_3_4_verify_athlete_coach_field)

print()

# ============================================================================
# TEST 4: GET /api/athlete/{telegram_id}/coach - Get athlete's coach
# ============================================================================
print("=" * 80)
print("TEST 4: GET /api/athlete/{telegram_id}/coach - Get athlete's coach")
print("=" * 80)

def test_4_1_athlete_has_coach():
    """Athlete 701002 should have coach"""
    r = requests.get(f"{API_BASE}/athlete/701002/coach")
    assert_status(r, 200, "Get athlete's coach")
    data = r.json()
    assert_true(data.get("coach"), "coach should be present")
    assert_eq(data["coach"]["telegram_id"], 701001, "coach telegram_id should be 701001")

test(4.1, test_4_1_athlete_has_coach)

def test_4_2_coach_has_no_coach():
    """Coach 701001 should have no coach"""
    r = requests.get(f"{API_BASE}/athlete/701001/coach")
    assert_status(r, 200, "Get coach's coach")
    data = r.json()
    assert_eq(data.get("coach"), None, "coach should be null")

test(4.2, test_4_2_coach_has_no_coach)

print()

# ============================================================================
# TEST 5: GET /api/coach/{telegram_id}/clients - Get coach's clients
# ============================================================================
print("=" * 80)
print("TEST 5: GET /api/coach/{telegram_id}/clients - Get coach's clients")
print("=" * 80)

def test_5_1_coach_clients_list():
    """Coach 701001 should have athlete 701002 in clients"""
    r = requests.get(f"{API_BASE}/coach/701001/clients")
    assert_status(r, 200, "Get coach's clients")
    data = r.json()
    assert_eq(data.get("coach_telegram_id"), 701001, "coach_telegram_id should be 701001")
    clients = data.get("clients", [])
    assert_true(len(clients) >= 1, "should have at least 1 client")
    athlete_client = next((c for c in clients if c["athlete"]["telegram_id"] == 701002), None)
    assert_true(athlete_client, "athlete 701002 should be in clients list")
    assert_true("plan" in athlete_client, "client should have plan field")
    assert_true("is_training_now" in athlete_client, "client should have is_training_now field")
    assert_true("last_workout_at" in athlete_client, "client should have last_workout_at field")
    assert_true("linked_at" in athlete_client, "client should have linked_at field")

test(5.1, test_5_1_coach_clients_list)

print()

# ============================================================================
# TEST 6: POST /api/plans with coach_telegram_id - Coach creates draft plan
# ============================================================================
print("=" * 80)
print("TEST 6: POST /api/plans with coach_telegram_id - Coach creates draft plan")
print("=" * 80)

# First, get a template ID
r = requests.get(f"{API_BASE}/programs/templates")
templates = r.json()
template_id = templates[0]["id"] if templates else None
print(f"Using template_id: {template_id}")

def test_6_1_coach_creates_draft_plan():
    """Coach creates plan for athlete -> visibility='draft'"""
    r = requests.post(f"{API_BASE}/plans", json={
        "athlete_telegram_id": 701002,
        "coach_telegram_id": 701001,
        "template_id": template_id
    })
    assert_status(r, 200, "Coach creates plan")
    plan = r.json()
    assert_eq(plan.get("visibility"), "draft", "visibility should be 'draft'")
    assert_eq(plan.get("prepared_by_coach"), True, "prepared_by_coach should be true")
    assert_true(len(plan.get("weeks", [])) > 0, "weeks should be non-empty")
    global draft_plan_id
    draft_plan_id = plan["id"]

test(6.1, test_6_1_coach_creates_draft_plan)

def test_6_2_athlete_sees_draft_hidden():
    """GET /api/plans/active/701002 returns draft with weeks=[]"""
    r = requests.get(f"{API_BASE}/plans/active/701002")
    assert_status(r, 200, "Get active plan for athlete")
    plan = r.json()
    assert_eq(plan.get("visibility"), "draft", "visibility should be 'draft'")
    assert_eq(plan.get("weeks"), [], "weeks should be empty (hidden)")

test(6.2, test_6_2_athlete_sees_draft_hidden)

def test_6_3_coach_sees_full_draft():
    """GET /api/coach/701001/clients/701002/plan returns full weeks"""
    r = requests.get(f"{API_BASE}/coach/701001/clients/701002/plan")
    assert_status(r, 200, "Coach gets client plan")
    plan = r.json()
    assert_eq(plan.get("visibility"), "draft", "visibility should be 'draft'")
    assert_true(len(plan.get("weeks", [])) > 0, "coach should see full weeks")

test(6.3, test_6_3_coach_sees_full_draft)

def test_6_4_unlinked_coach_forbidden():
    """Unlinked coach 701003 calling endpoint -> 403"""
    r = requests.get(f"{API_BASE}/coach/701003/clients/701002/plan")
    assert_status(r, 403, "Unlinked coach should get 403")

test(6.4, test_6_4_unlinked_coach_forbidden)

print()

# ============================================================================
# TEST 7: PATCH /api/plans/{id}/visibility - Publish plan
# ============================================================================
print("=" * 80)
print("TEST 7: PATCH /api/plans/{id}/visibility - Publish plan")
print("=" * 80)

def test_7_1_publish_plan():
    """PATCH visibility to 'published' sets published_at"""
    r = requests.patch(f"{API_BASE}/plans/{draft_plan_id}/visibility", json={"visibility": "published"})
    assert_status(r, 200, "Publish plan")
    plan = r.json()
    assert_eq(plan.get("visibility"), "published", "visibility should be 'published'")
    assert_true(plan.get("published_at"), "published_at should be set")

test(7.1, test_7_1_publish_plan)

def test_7_2_athlete_sees_full_weeks():
    """GET /api/plans/active/701002 now returns full weeks"""
    r = requests.get(f"{API_BASE}/plans/active/701002")
    assert_status(r, 200, "Get active plan for athlete")
    plan = r.json()
    assert_eq(plan.get("visibility"), "published", "visibility should be 'published'")
    assert_true(len(plan.get("weeks", [])) > 0, "athlete should now see full weeks")

test(7.2, test_7_2_athlete_sees_full_weeks)

def test_7_3_invalid_visibility():
    """Invalid visibility value -> 400"""
    r = requests.patch(f"{API_BASE}/plans/{draft_plan_id}/visibility", json={"visibility": "invalid"})
    assert_status(r, 400, "Invalid visibility should return 400")

test(7.3, test_7_3_invalid_visibility)

print()

# ============================================================================
# TEST 8: PATCH /api/plans/{id}/weeks/{week}/publish - Toggle week publish
# ============================================================================
print("=" * 80)
print("TEST 8: PATCH /api/plans/{id}/weeks/{week}/publish - Toggle week publish")
print("=" * 80)

def test_8_1_unpublish_week():
    """PATCH week 1 published=false"""
    r = requests.patch(f"{API_BASE}/plans/{draft_plan_id}/weeks/1/publish", json={"published": False})
    assert_status(r, 200, "Unpublish week 1")
    plan = r.json()
    week1 = next((w for w in plan.get("weeks", []) if w.get("week_index") == 1), None)
    assert_true(week1, "week 1 should exist")
    assert_eq(week1.get("published"), False, "week 1 published should be false")

test(8.1, test_8_1_unpublish_week)

def test_8_2_nonexistent_week():
    """Non-existent week -> 404"""
    r = requests.patch(f"{API_BASE}/plans/{draft_plan_id}/weeks/99/publish", json={"published": False})
    assert_status(r, 404, "Non-existent week should return 404")

test(8.2, test_8_2_nonexistent_week)

print()

# ============================================================================
# TEST 9: PATCH /api/plans/{id}/training-days - Set training days
# ============================================================================
print("=" * 80)
print("TEST 9: PATCH /api/plans/{id}/training-days - Set training days")
print("=" * 80)

def test_9_1_set_training_days():
    """PATCH training_days [1,3,5] -> stored sorted"""
    r = requests.patch(f"{API_BASE}/plans/{draft_plan_id}/training-days", json={"training_days": [1, 3, 5]})
    assert_status(r, 200, "Set training days")
    plan = r.json()
    assert_eq(plan.get("training_days"), [1, 3, 5], "training_days should be [1,3,5]")

test(9.1, test_9_1_set_training_days)

def test_9_2_out_of_range():
    """Out-of-range days -> 400"""
    r = requests.patch(f"{API_BASE}/plans/{draft_plan_id}/training-days", json={"training_days": [0, 8]})
    assert_status(r, 400, "Out-of-range days should return 400")

test(9.2, test_9_2_out_of_range)

print()

# ============================================================================
# TEST 10: POST /api/plans WITHOUT coach - Self-created plan is published
# ============================================================================
print("=" * 80)
print("TEST 10: POST /api/plans WITHOUT coach - Self-created plan is published")
print("=" * 80)

def test_10_1_self_plan_published():
    """POST plan without coach_telegram_id -> visibility='published'"""
    r = requests.post(f"{API_BASE}/plans", json={
        "athlete_telegram_id": 701002,
        "template_id": template_id
    })
    assert_status(r, 200, "Create self plan")
    plan = r.json()
    assert_eq(plan.get("visibility"), "published", "visibility should be 'published' (backward compatible)")

test(10.1, test_10_1_self_plan_published)

print()

# ============================================================================
# TEST 11: POST /api/sessions/{id}/confirm - Coach confirms session
# ============================================================================
print("=" * 80)
print("TEST 11: POST /api/sessions/{id}/confirm - Coach confirms session")
print("=" * 80)

# First, start a session for the athlete
r = requests.get(f"{API_BASE}/plans/active/701002")
active_plan = r.json()
active_plan_id = active_plan["id"]

r = requests.post(f"{API_BASE}/sessions/start", json={
    "plan_id": active_plan_id,
    "athlete_telegram_id": 701002,
    "week": 1,
    "day": 1
})
if r.status_code == 200:
    session = r.json()
    session_id = session["id"]
    print(f"✓ Started session: {session_id}")
else:
    print(f"⚠ Could not start session (status {r.status_code}), skipping session confirm tests")
    session_id = None

def test_11_1_coach_confirms_session():
    """Coach confirms session -> coach_confirmed=true"""
    if not session_id:
        print("  SKIP: No session available")
        return
    r = requests.post(f"{API_BASE}/sessions/{session_id}/confirm", json={"coach_telegram_id": 701001})
    assert_status(r, 200, "Coach confirms session")
    session = r.json()
    assert_eq(session.get("coach_confirmed"), True, "coach_confirmed should be true")
    assert_eq(session.get("confirmed_by"), 701001, "confirmed_by should be 701001")
    assert_true(session.get("confirmed_at"), "confirmed_at should be set")

if session_id:
    test(11.1, test_11_1_coach_confirms_session)

def test_11_2_nonlinked_coach_forbidden():
    """Non-linked coach -> 403"""
    if not session_id:
        print("  SKIP: No session available")
        return
    r = requests.post(f"{API_BASE}/sessions/{session_id}/confirm", json={"coach_telegram_id": 701003})
    assert_status(r, 403, "Non-linked coach should get 403")

if session_id:
    test(11.2, test_11_2_nonlinked_coach_forbidden)

def test_11_3_missing_session():
    """Missing session -> 404"""
    r = requests.post(f"{API_BASE}/sessions/bad-session-id/confirm", json={"coach_telegram_id": 701001})
    assert_status(r, 404, "Missing session should return 404")

test(11.3, test_11_3_missing_session)

print()

# ============================================================================
# TEST 12: POST /api/coach/unlink - Unlink athlete from coach
# ============================================================================
print("=" * 80)
print("TEST 12: POST /api/coach/unlink - Unlink athlete from coach")
print("=" * 80)

def test_12_1_unlink_athlete():
    """Unlink athlete 701002 from coach"""
    r = requests.post(f"{API_BASE}/coach/unlink", json={"athlete_telegram_id": 701002})
    assert_status(r, 200, "Unlink athlete")
    data = r.json()
    assert_eq(data.get("ok"), True, "ok should be true")

test(12.1, test_12_1_unlink_athlete)

def test_12_2_athlete_coach_null():
    """Athlete coach should be null after unlink"""
    r = requests.get(f"{API_BASE}/athlete/701002/coach")
    assert_status(r, 200, "Get athlete's coach")
    data = r.json()
    assert_eq(data.get("coach"), None, "coach should be null")

test(12.2, test_12_2_athlete_coach_null)

def test_12_3_clients_list_empty():
    """Coach clients list should not include 701002"""
    r = requests.get(f"{API_BASE}/coach/701001/clients")
    assert_status(r, 200, "Get coach's clients")
    data = r.json()
    clients = data.get("clients", [])
    athlete_client = next((c for c in clients if c["athlete"]["telegram_id"] == 701002), None)
    assert_eq(athlete_client, None, "athlete 701002 should not be in clients list")

test(12.3, test_12_3_clients_list_empty)

print()

# ============================================================================
# SUMMARY
# ============================================================================
print("=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print(f"Total tests: {tests_passed + tests_failed}")
print(f"Passed: {tests_passed}")
print(f"Failed: {tests_failed}")
print()

if tests_failed > 0:
    print("FAILED TESTS:")
    for result in test_results:
        if result.startswith("❌"):
            print(result)
    print()
    sys.exit(1)
else:
    print("✅ ALL TESTS PASSED!")
    sys.exit(0)
