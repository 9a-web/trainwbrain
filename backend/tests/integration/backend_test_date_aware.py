#!/usr/bin/env python3
"""
Test script for Date-aware day progress fix (week-progress + active session by calendar date)

The core bug being fixed: workout progress used to "bleed" across calendar weeks 
(a workout done on a date showed on the same weekday of other weeks) because matching 
was only by plan (week_index, day_index). Now it matches by the real calendar date (session.date).

Test scenarios:
1. Start a session with date="2026-06-17" (a workout day), mark all exercises done
2. GET week-progress with dates of the week containing 2026-06-17 -> day has progress
3. GET week-progress with dates of PREVIOUS week (2026-06-10) -> day has NO progress (key test)
4. GET sessions/active with date=2026-06-17 -> returns session; with date=2026-06-10 -> returns null
5. Backward compat: week-progress WITHOUT dates still shows progress
6. Confirm POST /sessions/start with date stamps session.date to that date
"""

import requests
import json
import random
import sys
from datetime import datetime, timedelta

# Base URL from frontend/.env
BASE_URL = "https://1db6bd65-9d5b-4875-a5d8-adc82ec9d902.preview.emergentagent.com/api"

def log(msg):
    print(f"[TEST] {msg}")

def assert_equal(actual, expected, msg):
    if actual != expected:
        raise AssertionError(f"{msg}: expected {expected}, got {actual}")
    log(f"✓ {msg}")

def assert_true(condition, msg):
    if not condition:
        raise AssertionError(f"{msg}: condition is False")
    log(f"✓ {msg}")

def assert_false(condition, msg):
    if condition:
        raise AssertionError(f"{msg}: condition is True")
    log(f"✓ {msg}")

def assert_gt(actual, expected, msg):
    if not (actual > expected):
        raise AssertionError(f"{msg}: expected {actual} > {expected}")
    log(f"✓ {msg}")

def assert_uuid(value, msg):
    if not isinstance(value, str) or len(value) != 36:
        raise AssertionError(f"{msg}: {value} is not a valid UUID")
    log(f"✓ {msg}")

def assert_iso_datetime(value, msg):
    if not isinstance(value, str) or 'T' not in value:
        raise AssertionError(f"{msg}: {value} is not an ISO datetime")
    log(f"✓ {msg}")

def main():
    log("=" * 80)
    log("DATE-AWARE DAY PROGRESS FIX TEST")
    log("=" * 80)
    
    # Generate unique test email
    timestamp = random.randint(1000000000, 9999999999)
    email = f"datetest{timestamp}@example.com"
    password = "testpass123"
    name = "Date Test User"
    
    # Step 1: Register email account
    log("\n[STEP 1] Register email account for auth")
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "name": name
    })
    assert_equal(resp.status_code, 200, "Register returns 200")
    data = resp.json()
    token = data["token"]
    athlete_telegram_id = data["user"]["telegram_id"]
    log(f"Registered: email={email}, telegram_id={athlete_telegram_id}")
    assert_true(athlete_telegram_id >= 900000000000, "Synthetic telegram_id >= 900000000000")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Step 2: Find template "full-body-beginner"
    log("\n[STEP 2] Find template 'full-body-beginner'")
    resp = requests.get(f"{BASE_URL}/programs/templates")
    assert_equal(resp.status_code, 200, "GET templates returns 200")
    templates = resp.json()
    template = next((t for t in templates if t["slug"] == "full-body-beginner"), None)
    assert_true(template is not None, "Template 'full-body-beginner' found")
    template_id = template["id"]
    log(f"Template ID: {template_id}")
    
    # Step 3: Create plan from template
    log("\n[STEP 3] Create plan from template")
    resp = requests.post(f"{BASE_URL}/plans", headers=headers, json={
        "athlete_telegram_id": athlete_telegram_id,
        "template_id": template_id
    })
    assert_equal(resp.status_code, 200, "POST /plans returns 200")
    plan = resp.json()
    plan_id = plan["id"]
    log(f"Plan ID: {plan_id}")
    assert_uuid(plan_id, "Plan ID is UUID")
    
    # Verify workout days [1,3,5]
    week1 = plan["weeks"][0]
    workout_days = [d["day_index"] for d in week1["days"] if not d.get("is_rest", False)]
    log(f"Workout days: {workout_days}")
    assert_true(1 in workout_days or 3 in workout_days or 5 in workout_days, 
                "Plan has workout days")
    
    # Pick a workout day (prefer day 1, 3, or 5)
    workout_day_index = next((di for di in [1, 3, 5] if di in workout_days), workout_days[0])
    log(f"Selected workout day_index: {workout_day_index}")
    
    # Step 4: Start session with date="2026-06-17"
    log("\n[STEP 4] Start session with date='2026-06-17'")
    session_date = "2026-06-17"
    resp = requests.post(f"{BASE_URL}/sessions/start", headers=headers, json={
        "plan_id": plan_id,
        "athlete_telegram_id": athlete_telegram_id,
        "week": 1,
        "day": workout_day_index,
        "date": session_date
    })
    assert_equal(resp.status_code, 200, "POST /sessions/start returns 200")
    session = resp.json()
    session_id = session["id"]
    log(f"Session ID: {session_id}")
    assert_uuid(session_id, "Session ID is UUID")
    assert_equal(session["date"], session_date, "Session date is '2026-06-17'")
    assert_equal(session["status"], "in_progress", "Session status is 'in_progress'")
    
    # Get exercise count
    exercise_count = len(session["exercises"])
    log(f"Session has {exercise_count} exercises")
    
    # Step 5: Mark all exercises done
    log("\n[STEP 5] Mark all exercises done")
    for i in range(exercise_count):
        resp = requests.patch(
            f"{BASE_URL}/sessions/{session_id}/exercise/{i}?action=done",
            headers=headers
        )
        assert_equal(resp.status_code, 200, f"Mark exercise {i} done returns 200")
    
    # Verify session is finished
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}", headers=headers)
    assert_equal(resp.status_code, 200, "GET session returns 200")
    session = resp.json()
    assert_equal(session["status"], "finished", "Session auto-finished after all exercises done")
    log(f"Session finished: progress_pct={session['stats']['progress_pct']}")
    
    # Step 6: Calculate week dates
    log("\n[STEP 6] Calculate week dates")
    # We started session with day_index=workout_day_index and date="2026-06-17"
    # The dates array maps day_index to calendar dates
    # So if workout_day_index=1 and date=2026-06-17, then:
    # day_index 1 = 2026-06-17, day_index 2 = 2026-06-18, etc.
    
    # Current week dates (day_index 1-7 starting from 2026-06-17)
    current_week_dates = [
        "2026-06-17",  # day_index 1
        "2026-06-18",  # day_index 2
        "2026-06-19",  # day_index 3
        "2026-06-20",  # day_index 4
        "2026-06-21",  # day_index 5
        "2026-06-22",  # day_index 6
        "2026-06-23",  # day_index 7
    ]
    
    # Previous week dates (7 days earlier)
    previous_week_dates = [
        "2026-06-10",  # day_index 1
        "2026-06-11",  # day_index 2
        "2026-06-12",  # day_index 3
        "2026-06-13",  # day_index 4
        "2026-06-14",  # day_index 5
        "2026-06-15",  # day_index 6
        "2026-06-16",  # day_index 7
    ]
    
    log(f"Current week dates: {current_week_dates}")
    log(f"Previous week dates: {previous_week_dates}")
    
    # Step 7: GET week-progress with current week dates
    log("\n[STEP 7] GET week-progress with current week dates (should show progress)")
    dates_param = ",".join(current_week_dates)
    resp = requests.get(
        f"{BASE_URL}/plans/{plan_id}/week-progress",
        params={"week": 1, "viewer": athlete_telegram_id, "dates": dates_param}
    )
    assert_equal(resp.status_code, 200, "GET week-progress returns 200")
    progress = resp.json()
    
    # Find the day with workout_day_index
    day_data = next((d for d in progress["days"] if d["day_index"] == workout_day_index), None)
    assert_true(day_data is not None, f"Day {workout_day_index} found in progress")
    assert_gt(day_data["progress_pct"], 0, f"Day {workout_day_index} has progress_pct > 0")
    assert_true(day_data["is_done"], f"Day {workout_day_index} is_done=true")
    assert_true(day_data["has_session"], f"Day {workout_day_index} has_session=true")
    log(f"Day {workout_day_index} in current week: progress_pct={day_data['progress_pct']}, is_done={day_data['is_done']}, has_session={day_data['has_session']}")
    
    # Step 8: GET week-progress with previous week dates (KEY TEST - should show NO progress)
    log("\n[STEP 8] GET week-progress with previous week dates (should show NO progress - KEY TEST)")
    dates_param = ",".join(previous_week_dates)
    resp = requests.get(
        f"{BASE_URL}/plans/{plan_id}/week-progress",
        params={"week": 1, "viewer": athlete_telegram_id, "dates": dates_param}
    )
    assert_equal(resp.status_code, 200, "GET week-progress returns 200")
    progress = resp.json()
    
    # Find the day with workout_day_index
    day_data = next((d for d in progress["days"] if d["day_index"] == workout_day_index), None)
    assert_true(day_data is not None, f"Day {workout_day_index} found in progress")
    assert_equal(day_data["progress_pct"], 0, f"Day {workout_day_index} has progress_pct=0 (NO BLEED)")
    assert_false(day_data["is_done"], f"Day {workout_day_index} is_done=false (NO BLEED)")
    assert_false(day_data["has_session"], f"Day {workout_day_index} has_session=false (NO BLEED)")
    log(f"Day {workout_day_index} in previous week: progress_pct={day_data['progress_pct']}, is_done={day_data['is_done']}, has_session={day_data['has_session']}")
    log("✓✓✓ KEY TEST PASSED: NO progress bleed to previous week ✓✓✓")
    
    # Step 9: GET sessions/active with date filter
    log("\n[STEP 9] GET sessions/active with date filter")
    
    # With date=2026-06-17 (should return session)
    resp = requests.get(
        f"{BASE_URL}/sessions/active",
        params={
            "plan_id": plan_id,
            "week": 1,
            "day": workout_day_index,
            "athlete": athlete_telegram_id,
            "date": "2026-06-17"
        }
    )
    assert_equal(resp.status_code, 200, "GET sessions/active with date=2026-06-17 returns 200")
    active_session = resp.json()
    assert_true(active_session is not None, "Session returned for date=2026-06-17")
    assert_equal(active_session["id"], session_id, "Returned session ID matches")
    log(f"GET sessions/active with date=2026-06-17: session_id={active_session['id']}")
    
    # With date=2026-06-10 (should return null)
    resp = requests.get(
        f"{BASE_URL}/sessions/active",
        params={
            "plan_id": plan_id,
            "week": 1,
            "day": workout_day_index,
            "athlete": athlete_telegram_id,
            "date": "2026-06-10"
        }
    )
    assert_equal(resp.status_code, 200, "GET sessions/active with date=2026-06-10 returns 200")
    active_session = resp.json()
    assert_true(active_session is None, "No session returned for date=2026-06-10")
    log(f"GET sessions/active with date=2026-06-10: null (correct)")
    
    # Step 10: Backward compatibility - week-progress WITHOUT dates
    log("\n[STEP 10] Backward compatibility - week-progress WITHOUT dates")
    resp = requests.get(
        f"{BASE_URL}/plans/{plan_id}/week-progress",
        params={"week": 1, "viewer": athlete_telegram_id}
    )
    assert_equal(resp.status_code, 200, "GET week-progress without dates returns 200")
    progress = resp.json()
    
    day_data = next((d for d in progress["days"] if d["day_index"] == workout_day_index), None)
    assert_true(day_data is not None, f"Day {workout_day_index} found in progress")
    assert_true(day_data["has_session"], f"Day {workout_day_index} has_session=true (backward compat)")
    assert_gt(day_data["progress_pct"], 0, f"Day {workout_day_index} has progress_pct > 0 (backward compat)")
    log(f"Week-progress without dates: day {workout_day_index} has_session={day_data['has_session']}, progress_pct={day_data['progress_pct']}")
    
    # Step 11: Verify UUIDs and ISO datetimes
    log("\n[STEP 11] Verify UUIDs and ISO datetimes")
    assert_uuid(session["id"], "Session ID is UUID")
    assert_uuid(session["plan_id"], "Session plan_id is UUID")
    assert_iso_datetime(session["started_at"], "Session started_at is ISO datetime")
    assert_iso_datetime(session["finished_at"], "Session finished_at is ISO datetime")
    assert_true("_id" not in session, "No _id leak in session")
    log("All UUIDs and ISO datetimes verified, no _id leaks")
    
    log("\n" + "=" * 80)
    log("ALL TESTS PASSED ✓✓✓")
    log("=" * 80)
    log("\nSUMMARY:")
    log("1. ✓ Session started with date='2026-06-17' and stamped correctly")
    log("2. ✓ Week-progress with current week dates shows progress")
    log("3. ✓ Week-progress with previous week dates shows NO progress (NO BLEED)")
    log("4. ✓ sessions/active with date filter works correctly")
    log("5. ✓ Backward compatibility maintained (week-progress without dates)")
    log("6. ✓ UUIDs, ISO datetimes, no _id leaks verified")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
