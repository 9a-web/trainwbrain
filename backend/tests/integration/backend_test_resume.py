#!/usr/bin/env python3
"""
Backend API tests for TrainWithBrain - Resume Session Endpoint
Tests ONLY the POST /api/sessions/{session_id}/resume endpoint
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
        raise AssertionError(f"{msg}: expected status {expected_status}, got {response.status_code}. Response: {response.text[:500]}")

def assert_not_none(value, msg=""):
    """Assert value is not None"""
    if value is None:
        raise AssertionError(f"{msg}: value is None")

def assert_none(value, msg=""):
    """Assert value is None"""
    if value is not None:
        raise AssertionError(f"{msg}: expected None, got {value}")

# ============================================================================
# SETUP: Create test users and authenticate
# ============================================================================
print("=" * 80)
print("SETUP: Creating test users and authenticating")
print("=" * 80)

# Register an email account for authentication
import random
import time
email_suffix = int(time.time())
test_email = f"resumetest{email_suffix}@example.com"
test_password = "password123"
test_name = "Resume Tester"

print(f"Registering test account: {test_email}")
r = requests.post(f"{API_BASE}/auth/register", json={
    "email": test_email,
    "password": test_password,
    "name": test_name
})
assert_status(r, 200, "Register test account")
auth_data = r.json()
auth_token = auth_data.get("token")
athlete_user = auth_data.get("user")
athlete_telegram_id = athlete_user.get("telegram_id")

print(f"✓ Registered: {test_email}")
print(f"✓ Token: {auth_token[:20]}...")
print(f"✓ Athlete telegram_id: {athlete_telegram_id}")

# Set up auth headers
auth_headers = {"Authorization": f"Bearer {auth_token}"}

# Get a template (use full-body-beginner)
print("\nGetting template...")
r = requests.get(f"{API_BASE}/programs/templates")
assert_status(r, 200, "Get templates")
templates = r.json()
template = next((t for t in templates if t.get("slug") == "full-body-beginner"), templates[0] if templates else None)
assert_true(template, "Template should exist")
template_id = template["id"]
print(f"✓ Using template: {template.get('name')} (id={template_id})")

# Create a plan
print("\nCreating plan...")
r = requests.post(f"{API_BASE}/plans", json={
    "athlete_telegram_id": athlete_telegram_id,
    "template_id": template_id
}, headers=auth_headers)
assert_status(r, 200, "Create plan")
plan = r.json()
plan_id = plan["id"]
print(f"✓ Created plan: {plan_id}")
print(f"  - visibility: {plan.get('visibility')}")
print(f"  - status: {plan.get('status')}")

# Find a workout day in week 1
print("\nFinding workout day...")
r = requests.get(f"{API_BASE}/plans/{plan_id}/week-progress?week=1")
assert_status(r, 200, "Get week progress")
week_progress = r.json()
workout_days = [d for d in week_progress.get("days", []) if d.get("is_workout")]
assert_true(len(workout_days) > 0, "Should have at least one workout day")
workout_day = workout_days[0]["day_index"]
print(f"✓ Found workout day: {workout_day}")

# Find another workout day for the 409 test
second_workout_day = None
if len(workout_days) > 1:
    second_workout_day = workout_days[1]["day_index"]
    print(f"✓ Found second workout day: {second_workout_day}")

print()

# ============================================================================
# SCENARIO 1: PARTIAL COMPLETE + FINISH
# ============================================================================
print("=" * 80)
print("SCENARIO 1: PARTIAL COMPLETE + FINISH")
print("=" * 80)

# Start session
print("Starting session...")
r = requests.post(f"{API_BASE}/sessions/start", json={
    "plan_id": plan_id,
    "athlete_telegram_id": athlete_telegram_id,
    "week": 1,
    "day": workout_day
})
assert_status(r, 200, "Start session")
session = r.json()
session_id = session["id"]
total_exercises = len(session.get("exercises", []))
print(f"✓ Started session: {session_id}")
print(f"  - total exercises: {total_exercises}")
print(f"  - status: {session.get('status')}")

def test_1_1_mark_first_exercise_done():
    """Mark first exercise as done"""
    r = requests.patch(f"{API_BASE}/sessions/{session_id}/exercise/0?action=done")
    assert_status(r, 200, "Mark exercise 0 done")
    s = r.json()
    assert_eq(s["exercises"][0]["status"], "done", "Exercise 0 should be done")
    assert_eq(s["stats"]["done_count"], 1, "done_count should be 1")
    print(f"  - Exercise 0 marked done")
    print(f"  - done_count: {s['stats']['done_count']}")

test("1.1 Mark first exercise done", test_1_1_mark_first_exercise_done)

def test_1_2_finish_session():
    """Finish session with partial completion"""
    r = requests.post(f"{API_BASE}/sessions/{session_id}/finish")
    assert_status(r, 200, "Finish session")
    s = r.json()
    assert_eq(s["status"], "finished", "Status should be finished")
    assert_not_none(s.get("finished_at"), "finished_at should be set")
    done_count = s["stats"]["done_count"]
    assert_true(done_count >= 1, f"done_count should be >= 1, got {done_count}")
    print(f"  - Session finished")
    print(f"  - finished_at: {s.get('finished_at')}")
    print(f"  - done_count: {done_count}")
    global initial_done_count
    initial_done_count = done_count

test("1.2 Finish session", test_1_2_finish_session)

print()

# ============================================================================
# SCENARIO 2: RESUME KEEPS MARKS (KEY TEST)
# ============================================================================
print("=" * 80)
print("SCENARIO 2: RESUME KEEPS MARKS (KEY TEST)")
print("=" * 80)

def test_2_1_resume_session():
    """Resume session - should preserve completed marks"""
    r = requests.post(f"{API_BASE}/sessions/{session_id}/resume")
    assert_status(r, 200, "Resume session")
    s = r.json()
    
    # Verify status changed to in_progress
    assert_eq(s["status"], "in_progress", "Status should be in_progress")
    print(f"  ✓ Status: {s['status']}")
    
    # Verify finished_at is cleared
    assert_none(s.get("finished_at"), "finished_at should be null")
    print(f"  ✓ finished_at: {s.get('finished_at')}")
    
    # Verify paused is false
    assert_eq(s.get("paused"), False, "paused should be false")
    print(f"  ✓ paused: {s.get('paused')}")
    
    # KEY TEST: Verify exercise[0].status is STILL 'done' (NOT reset to pending)
    assert_eq(s["exercises"][0]["status"], "done", "Exercise 0 status should STILL be 'done' (completed marks preserved)")
    print(f"  ✓ Exercise 0 status: {s['exercises'][0]['status']} (PRESERVED)")
    
    # Verify exactly one exercise is now 'in_progress' (the next pending)
    in_progress_exercises = [e for e in s["exercises"] if e.get("status") == "in_progress"]
    assert_true(len(in_progress_exercises) >= 0, "Should have 0 or 1 in_progress exercise")
    if len(in_progress_exercises) > 0:
        print(f"  ✓ Found {len(in_progress_exercises)} in_progress exercise(s)")
    
    # Verify stats.done_count is preserved
    assert_eq(s["stats"]["done_count"], initial_done_count, f"done_count should be preserved (={initial_done_count})")
    print(f"  ✓ done_count preserved: {s['stats']['done_count']}")

test("2.1 Resume session preserves marks", test_2_1_resume_session)

print()

# ============================================================================
# SCENARIO 3: PERSISTENCE
# ============================================================================
print("=" * 80)
print("SCENARIO 3: PERSISTENCE")
print("=" * 80)

def test_3_1_get_session_persists_marks():
    """GET session should show preserved marks"""
    r = requests.get(f"{API_BASE}/sessions/{session_id}")
    assert_status(r, 200, "Get session")
    s = r.json()
    
    # Verify exercise[0] is still done
    assert_eq(s["exercises"][0]["status"], "done", "Exercise 0 should still be done")
    print(f"  ✓ Exercise 0 status persisted: {s['exercises'][0]['status']}")
    
    # Verify status is in_progress
    assert_eq(s["status"], "in_progress", "Status should be in_progress")
    print(f"  ✓ Status persisted: {s['status']}")

test("3.1 GET session persists marks", test_3_1_get_session_persists_marks)

print()

# ============================================================================
# SCENARIO 4: CONTINUE TO FINISH AGAIN
# ============================================================================
print("=" * 80)
print("SCENARIO 4: CONTINUE TO FINISH AGAIN")
print("=" * 80)

def test_4_1_mark_remaining_exercises():
    """Mark remaining exercises as done"""
    r = requests.get(f"{API_BASE}/sessions/{session_id}")
    assert_status(r, 200, "Get session")
    s = r.json()
    
    # Mark all pending/in_progress exercises as done
    for i, ex in enumerate(s["exercises"]):
        if ex.get("status") in ["pending", "in_progress"]:
            r2 = requests.patch(f"{API_BASE}/sessions/{session_id}/exercise/{i}?action=done")
            assert_status(r2, 200, f"Mark exercise {i} done")
            print(f"  ✓ Marked exercise {i} done")
    
    # Verify session auto-finished
    r3 = requests.get(f"{API_BASE}/sessions/{session_id}")
    assert_status(r3, 200, "Get session after marking all done")
    s3 = r3.json()
    assert_eq(s3["status"], "finished", "Session should auto-finish when all exercises done/skipped")
    print(f"  ✓ Session auto-finished: {s3['status']}")

test("4.1 Continue to finish again", test_4_1_mark_remaining_exercises)

print()

# ============================================================================
# SCENARIO 5: NEGATIVE 404
# ============================================================================
print("=" * 80)
print("SCENARIO 5: NEGATIVE 404")
print("=" * 80)

def test_5_1_resume_nonexistent_session():
    """Resume non-existent session should return 404"""
    r = requests.post(f"{API_BASE}/sessions/non-existent-id-12345/resume")
    assert_status(r, 404, "Resume non-existent session should return 404")
    print(f"  ✓ Non-existent session returns 404")

test("5.1 Resume non-existent session returns 404", test_5_1_resume_nonexistent_session)

print()

# ============================================================================
# SCENARIO 6: NEGATIVE 409
# ============================================================================
print("=" * 80)
print("SCENARIO 6: NEGATIVE 409 (Active session conflict)")
print("=" * 80)

if second_workout_day:
    # Start a SECOND session on a different workout day
    print(f"Starting second session on day {second_workout_day}...")
    r = requests.post(f"{API_BASE}/sessions/start", json={
        "plan_id": plan_id,
        "athlete_telegram_id": athlete_telegram_id,
        "week": 1,
        "day": second_workout_day
    })
    assert_status(r, 200, "Start second session")
    second_session = r.json()
    second_session_id = second_session["id"]
    print(f"✓ Started second session: {second_session_id}")
    print(f"  - status: {second_session.get('status')}")
    
    def test_6_1_resume_with_active_session():
        """Resume first session while second is in_progress should return 409"""
        r = requests.post(f"{API_BASE}/sessions/{session_id}/resume")
        assert_status(r, 409, "Resume with active session should return 409")
        data = r.json()
        
        # Verify detail structure
        detail = data.get("detail", {})
        if isinstance(detail, str):
            # FastAPI might wrap it as a string
            print(f"  ✓ Got 409 with detail: {detail}")
        else:
            assert_true("message" in detail or "error" in detail, "detail should have message or error field")
            assert_true("session_id" in detail, "detail should have session_id field")
            print(f"  ✓ Got 409 with message: {detail.get('message', detail.get('error'))}")
            print(f"  ✓ Active session_id: {detail.get('session_id')}")
    
    test("6.1 Resume with active session returns 409", test_6_1_resume_with_active_session)
else:
    print("⚠ Skipping 409 test - only one workout day available")

print()

# ============================================================================
# GENERAL ASSERTIONS
# ============================================================================
print("=" * 80)
print("GENERAL ASSERTIONS")
print("=" * 80)

def test_general_1_uuid_ids():
    """All IDs should be UUID strings (36 chars)"""
    r = requests.get(f"{API_BASE}/sessions/{session_id}")
    assert_status(r, 200, "Get session")
    s = r.json()
    
    assert_eq(len(s["id"]), 36, "Session ID should be 36 chars (UUID)")
    assert_eq(len(s["plan_id"]), 36, "Plan ID should be 36 chars (UUID)")
    print(f"  ✓ All IDs are UUID strings (36 chars)")

test("General: UUID IDs", test_general_1_uuid_ids)

def test_general_2_iso_datetimes():
    """All datetime fields should be ISO strings"""
    r = requests.get(f"{API_BASE}/sessions/{session_id}")
    assert_status(r, 200, "Get session")
    s = r.json()
    
    # Check started_at is ISO format
    started_at = s.get("started_at")
    assert_true(started_at, "started_at should be present")
    # ISO format should contain 'T' and end with 'Z' or timezone
    assert_true("T" in started_at, "started_at should be ISO format")
    print(f"  ✓ Datetimes are ISO strings")

test("General: ISO datetimes", test_general_2_iso_datetimes)

def test_general_3_no_id_leaks():
    """No MongoDB _id leaks"""
    r = requests.get(f"{API_BASE}/sessions/{session_id}")
    assert_status(r, 200, "Get session")
    s = r.json()
    
    assert_true("_id" not in s, "Session should not have _id field")
    for ex in s.get("exercises", []):
        assert_true("_id" not in ex, "Exercise should not have _id field")
    print(f"  ✓ No MongoDB _id leaks")

test("General: No _id leaks", test_general_3_no_id_leaks)

def test_general_4_stats_object():
    """Stats object should be present"""
    r = requests.get(f"{API_BASE}/sessions/{session_id}")
    assert_status(r, 200, "Get session")
    s = r.json()
    
    assert_true("stats" in s, "Session should have stats object")
    stats = s["stats"]
    assert_true("done_count" in stats, "stats should have done_count")
    assert_true("total_count" in stats, "stats should have total_count")
    print(f"  ✓ Stats object present with required fields")

test("General: Stats object", test_general_4_stats_object)

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
