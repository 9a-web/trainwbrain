#!/usr/bin/env python3
"""
Backend test for BUGFIX ROUND (Groups A+B) - TrainWithBrain app
Tests ONLY the bugfix changes:
1. Training-days remap (PATCH /api/plans/{id}/training-days)
2. Streak counts only sessions with >=1 done exercise
3. Robustness: plan day/week-progress/start-session defensive reads + explicit rest day + session.date
"""

import requests
import json
import sys
from datetime import datetime

# Backend URL from frontend/.env
BASE_URL = "https://learning-boost-24.preview.emergentagent.com/api"

# Test athletes
ATHLETE_1 = 821001  # For training-days remap tests
ATHLETE_2 = 821002  # For streak test (all skipped)
ATHLETE_3 = 821003  # For streak test (>=1 done)

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

def assert_in(item, container, msg):
    if item not in container:
        raise AssertionError(f"{msg}: {item} not in {container}")
    log(f"✓ {msg}")

def assert_not_in(item, container, msg):
    if item in container:
        raise AssertionError(f"{msg}: {item} should not be in {container}")
    log(f"✓ {msg}")

def create_user(telegram_id, first_name):
    """Create a test user"""
    resp = requests.post(f"{BASE_URL}/users", json={
        "telegram_id": telegram_id,
        "first_name": first_name,
        "last_name": "Test",
        "username": f"test{telegram_id}"
    })
    assert_equal(resp.status_code, 200, f"Create user {telegram_id}")
    return resp.json()

def get_templates():
    """Get program templates"""
    resp = requests.get(f"{BASE_URL}/programs/templates")
    assert_equal(resp.status_code, 200, "Get templates")
    return resp.json()

def create_plan(athlete_id, template_id):
    """Create a plan from template"""
    resp = requests.post(f"{BASE_URL}/plans", json={
        "athlete_telegram_id": athlete_id,
        "template_id": template_id
    })
    assert_equal(resp.status_code, 200, f"Create plan for athlete {athlete_id}")
    return resp.json()

def get_week_progress(plan_id, week=1):
    """Get week progress"""
    resp = requests.get(f"{BASE_URL}/plans/{plan_id}/week-progress", params={"week": week})
    assert_equal(resp.status_code, 200, f"Get week progress for plan {plan_id} week {week}")
    return resp.json()

def get_plan_day(plan_id, week, day):
    """Get plan day"""
    resp = requests.get(f"{BASE_URL}/plans/{plan_id}/day", params={"week": week, "day": day})
    assert_equal(resp.status_code, 200, f"Get plan day {plan_id} week={week} day={day}")
    return resp.json()

def patch_training_days(plan_id, training_days):
    """PATCH training days"""
    resp = requests.patch(f"{BASE_URL}/plans/{plan_id}/training-days", json={
        "training_days": training_days
    })
    return resp

def start_session(plan_id, athlete_id, week, day):
    """Start a workout session"""
    resp = requests.post(f"{BASE_URL}/sessions/start", json={
        "plan_id": plan_id,
        "athlete_telegram_id": athlete_id,
        "week": week,
        "day": day
    })
    return resp

def patch_exercise_action(session_id, order, action):
    """Mark exercise as done/skip/reset"""
    resp = requests.patch(f"{BASE_URL}/sessions/{session_id}/exercise/{order}", params={"action": action})
    assert_equal(resp.status_code, 200, f"Patch exercise {order} action={action}")
    return resp.json()

def get_session(session_id):
    """Get session by id"""
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}")
    assert_equal(resp.status_code, 200, f"Get session {session_id}")
    return resp.json()

def get_stats(telegram_id):
    """Get athlete stats"""
    resp = requests.get(f"{BASE_URL}/stats/{telegram_id}")
    assert_equal(resp.status_code, 200, f"Get stats for {telegram_id}")
    return resp.json()

def test_training_days_remap():
    """
    TEST 1: TRAINING-DAYS REMAP (main fix)
    After creating a plan, PATCH /api/plans/{id}/training-days should ACTUALLY MOVE
    the workouts in the plan snapshot, not just store the field.
    """
    log("\n" + "="*80)
    log("TEST 1: TRAINING-DAYS REMAP")
    log("="*80)
    
    # Create user
    create_user(ATHLETE_1, "Athlete1")
    
    # Get full-body-beginner template (3 workout days per week)
    templates = get_templates()
    fb_template = next((t for t in templates if t.get("slug") == "full-body-beginner"), None)
    if not fb_template:
        log("⚠️  full-body-beginner template not found, using first template")
        fb_template = templates[0]
    
    template_id = fb_template["id"]
    log(f"Using template: {fb_template.get('name')} (id={template_id})")
    
    # Create plan
    plan = create_plan(ATHLETE_1, template_id)
    plan_id = plan["id"]
    log(f"Created plan: {plan_id}")
    
    # Get initial week progress to see original workout days
    week_progress = get_week_progress(plan_id, 1)
    original_workout_days = [d["day_index"] for d in week_progress["days"] if d["is_workout"]]
    log(f"Original workout days: {original_workout_days}")
    
    # Verify at least one workout day exists
    assert_true(len(original_workout_days) > 0, "Plan has at least one workout day")
    
    # CRITICAL TEST: PATCH training-days to [2,4,6]
    log("\n--- PATCH training-days to [2,4,6] ---")
    resp = patch_training_days(plan_id, [2, 4, 6])
    assert_equal(resp.status_code, 200, "PATCH training-days [2,4,6] returns 200")
    updated_plan = resp.json()
    assert_equal(updated_plan["training_days"], [2, 4, 6], "Plan training_days field updated to [2,4,6]")
    
    # CRITICAL: Verify workouts ACTUALLY MOVED in the snapshot
    week_progress = get_week_progress(plan_id, 1)
    workout_days = [d["day_index"] for d in week_progress["days"] if d["is_workout"]]
    log(f"Workout days after PATCH: {workout_days}")
    
    # Check that workouts appear ONLY on the selected days [2,4,6]
    # (or a subset if there are fewer than 3 workouts)
    for day_idx in workout_days:
        assert_in(day_idx, [2, 4, 6], f"Workout day {day_idx} is in selected days [2,4,6]")
    
    # Verify day 2 has a real workout
    day2 = get_plan_day(plan_id, 1, 2)
    assert_equal(day2["is_rest"], False, "Day 2 is a workout day (not rest)")
    assert_true(len(day2["exercises"]) > 0, "Day 2 has exercises")
    
    # Verify day 1 is now rest (was not selected)
    day1 = get_plan_day(plan_id, 1, 1)
    assert_equal(day1["is_rest"], True, "Day 1 is now rest (not in selected days)")
    assert_equal(len(day1["exercises"]), 0, "Day 1 has no exercises")
    
    # CRITICAL TEST: Re-PATCH to [1,3,5,7]
    log("\n--- Re-PATCH training-days to [1,3,5,7] ---")
    resp = patch_training_days(plan_id, [1, 3, 5, 7])
    assert_equal(resp.status_code, 200, "PATCH training-days [1,3,5,7] returns 200")
    updated_plan = resp.json()
    assert_equal(updated_plan["training_days"], [1, 3, 5, 7], "Plan training_days field updated to [1,3,5,7]")
    
    # Verify workouts moved again
    week_progress = get_week_progress(plan_id, 1)
    workout_days = [d["day_index"] for d in week_progress["days"] if d["is_workout"]]
    log(f"Workout days after re-PATCH: {workout_days}")
    
    # Check that workouts appear ONLY on the selected days [1,3,5,7]
    for day_idx in workout_days:
        assert_in(day_idx, [1, 3, 5, 7], f"Workout day {day_idx} is in selected days [1,3,5,7]")
    
    # Verify NO duplicate day_index
    assert_equal(len(workout_days), len(set(workout_days)), "No duplicate day_index in workout days")
    
    # Verify no workouts lost (same count as original)
    assert_equal(len(workout_days), len(original_workout_days), "Same number of workouts (no workouts lost)")
    
    # Verify day 1 now has a workout
    day1 = get_plan_day(plan_id, 1, 1)
    assert_equal(day1["is_rest"], False, "Day 1 is now a workout day")
    assert_true(len(day1["exercises"]) > 0, "Day 1 has exercises")
    
    # Verify day 2 is now rest (not in selected days)
    day2 = get_plan_day(plan_id, 1, 2)
    assert_equal(day2["is_rest"], True, "Day 2 is now rest (not in selected days)")
    
    # Test out-of-range [0,8] -> 400
    log("\n--- Test out-of-range training-days [0,8] ---")
    resp = patch_training_days(plan_id, [0, 8])
    assert_equal(resp.status_code, 400, "PATCH training-days [0,8] returns 400 (out of range)")
    
    log("\n✅ TEST 1 PASSED: Training-days remap working correctly")
    return True

def test_streak_only_counts_real_work():
    """
    TEST 2: STREAK ONLY COUNTS REAL WORK
    A session where ALL exercises are skipped should NOT count toward streak/total_workouts.
    A session with >=1 exercise marked 'done' should count.
    """
    log("\n" + "="*80)
    log("TEST 2: STREAK ONLY COUNTS REAL WORK")
    log("="*80)
    
    # Test 2A: All exercises skipped -> streak=0, total_workouts=0
    log("\n--- Test 2A: All exercises skipped ---")
    create_user(ATHLETE_2, "Athlete2")
    
    # Get template and create plan
    templates = get_templates()
    template_id = templates[0]["id"]
    plan = create_plan(ATHLETE_2, template_id)
    plan_id = plan["id"]
    
    # Find a workout day
    week_progress = get_week_progress(plan_id, 1)
    workout_day = next((d["day_index"] for d in week_progress["days"] if d["is_workout"]), None)
    assert_true(workout_day is not None, "Found a workout day")
    log(f"Starting session on day {workout_day}")
    
    # Start session
    resp = start_session(plan_id, ATHLETE_2, 1, workout_day)
    assert_equal(resp.status_code, 200, "Start session")
    session = resp.json()
    session_id = session["id"]
    
    # Get exercise count
    exercises = session["exercises"]
    exercise_count = len(exercises)
    log(f"Session has {exercise_count} exercises")
    
    # Mark ALL exercises as skipped
    for i in range(exercise_count):
        patch_exercise_action(session_id, i, "skip")
    
    # Verify session auto-finished
    session = get_session(session_id)
    assert_equal(session["status"], "finished", "Session auto-finished after all skipped")
    assert_equal(session["stats"]["done_count"], 0, "No exercises done")
    assert_equal(session["stats"]["skipped_count"], exercise_count, f"All {exercise_count} exercises skipped")
    
    # CRITICAL: Check stats - should NOT count this session
    stats = get_stats(ATHLETE_2)
    assert_equal(stats["streak_days"], 0, "Streak is 0 (all-skipped session not counted)")
    assert_equal(stats["total_workouts"], 0, "Total workouts is 0 (all-skipped session not counted)")
    
    log("\n✅ TEST 2A PASSED: All-skipped session NOT counted")
    
    # Test 2B: At least one exercise done -> streak>=1, total_workouts>=1
    log("\n--- Test 2B: At least one exercise done ---")
    create_user(ATHLETE_3, "Athlete3")
    
    # Create plan
    plan = create_plan(ATHLETE_3, template_id)
    plan_id = plan["id"]
    
    # Find a workout day
    week_progress = get_week_progress(plan_id, 1)
    workout_day = next((d["day_index"] for d in week_progress["days"] if d["is_workout"]), None)
    log(f"Starting session on day {workout_day}")
    
    # Start session
    resp = start_session(plan_id, ATHLETE_3, 1, workout_day)
    assert_equal(resp.status_code, 200, "Start session")
    session = resp.json()
    session_id = session["id"]
    
    # Mark first exercise as done
    patch_exercise_action(session_id, 0, "done")
    
    # Mark remaining exercises as skipped
    exercises = session["exercises"]
    for i in range(1, len(exercises)):
        patch_exercise_action(session_id, i, "skip")
    
    # Verify session finished
    session = get_session(session_id)
    assert_equal(session["status"], "finished", "Session finished")
    assert_true(session["stats"]["done_count"] >= 1, "At least one exercise done")
    
    # CRITICAL: Check stats - should count this session
    stats = get_stats(ATHLETE_3)
    assert_true(stats["streak_days"] >= 1, "Streak >= 1 (session with done exercise counted)")
    assert_true(stats["total_workouts"] >= 1, "Total workouts >= 1 (session with done exercise counted)")
    
    log("\n✅ TEST 2B PASSED: Session with >=1 done exercise counted")
    log("\n✅ TEST 2 PASSED: Streak only counts real work")
    return True

def test_robustness():
    """
    TEST 3: ROBUSTNESS
    - GET /api/plans/{id}/day?week=99&day=1 returns is_rest rest response (no 500)
    - GET /api/plans/{id}/week-progress?week=99 returns 200 with 7 rest days (no 500)
    - A day explicitly set is_rest=true returns is_rest=true from day endpoint
    - POST /api/sessions/start on a rest day -> 400
    - After starting a session, GET /api/sessions/{id} has session.date as non-null ISO date
    """
    log("\n" + "="*80)
    log("TEST 3: ROBUSTNESS")
    log("="*80)
    
    # Use ATHLETE_1's plan from test 1
    # Create a fresh user and plan for robustness tests
    athlete_id = 821004
    create_user(athlete_id, "Athlete4")
    
    templates = get_templates()
    template_id = templates[0]["id"]
    plan = create_plan(athlete_id, template_id)
    plan_id = plan["id"]
    
    # Test 3A: Out-of-range week (week=99) for day endpoint -> rest response (no 500)
    log("\n--- Test 3A: GET day with week=99 ---")
    day_resp = get_plan_day(plan_id, 99, 1)
    assert_equal(day_resp["is_rest"], True, "Week 99 day 1 returns is_rest=true (no 500)")
    assert_equal(day_resp["title"], "День отдыха", "Week 99 day 1 returns rest title")
    assert_equal(len(day_resp["exercises"]), 0, "Week 99 day 1 has no exercises")
    
    # Test 3B: Out-of-range week (week=99) for week-progress -> 7 rest days (no 500)
    log("\n--- Test 3B: GET week-progress with week=99 ---")
    week_progress = get_week_progress(plan_id, 99)
    assert_equal(len(week_progress["days"]), 7, "Week 99 returns 7 days")
    for day in week_progress["days"]:
        assert_equal(day["is_workout"], False, f"Week 99 day {day['day_index']} is rest (is_workout=false)")
    
    # Test 3C: Explicit rest day (find a rest day in week 1)
    log("\n--- Test 3C: Explicit rest day ---")
    week_progress = get_week_progress(plan_id, 1)
    rest_day = next((d["day_index"] for d in week_progress["days"] if not d["is_workout"]), None)
    if rest_day:
        day_resp = get_plan_day(plan_id, 1, rest_day)
        assert_equal(day_resp["is_rest"], True, f"Day {rest_day} is explicitly rest")
        log(f"✓ Day {rest_day} is rest")
    else:
        log("⚠️  No rest days in week 1, skipping explicit rest day test")
    
    # Test 3D: POST /api/sessions/start on a rest day -> 400
    log("\n--- Test 3D: Start session on rest day ---")
    if rest_day:
        resp = start_session(plan_id, athlete_id, 1, rest_day)
        assert_equal(resp.status_code, 400, "Starting session on rest day returns 400")
        log(f"✓ Starting session on rest day {rest_day} returns 400")
    else:
        log("⚠️  No rest days in week 1, skipping start session on rest day test")
    
    # Test 3E: session.date is non-null ISO date (YYYY-MM-DD)
    log("\n--- Test 3E: Session date is non-null ISO date ---")
    workout_day = next((d["day_index"] for d in week_progress["days"] if d["is_workout"]), None)
    assert_true(workout_day is not None, "Found a workout day")
    
    resp = start_session(plan_id, athlete_id, 1, workout_day)
    assert_equal(resp.status_code, 200, "Start session on workout day")
    session = resp.json()
    session_id = session["id"]
    
    # Check session.date
    assert_true("date" in session, "Session has 'date' field")
    assert_true(session["date"] is not None, "Session date is not null")
    
    # Verify ISO date format (YYYY-MM-DD)
    try:
        date_obj = datetime.fromisoformat(session["date"])
        log(f"✓ Session date is valid ISO date: {session['date']}")
    except Exception as e:
        raise AssertionError(f"Session date is not valid ISO date: {session['date']}, error: {e}")
    
    # Verify it's a date string (10 chars: YYYY-MM-DD)
    assert_equal(len(session["date"]), 10, "Session date is YYYY-MM-DD format (10 chars)")
    
    log("\n✅ TEST 3 PASSED: Robustness checks passed")
    return True

def test_general_assertions():
    """
    GENERAL ASSERTIONS: UUIDs only, ISO datetime strings, no MongoDB _id leaks
    """
    log("\n" + "="*80)
    log("GENERAL ASSERTIONS")
    log("="*80)
    
    # Use ATHLETE_1's plan
    athlete_id = 821005
    create_user(athlete_id, "Athlete5")
    
    templates = get_templates()
    template_id = templates[0]["id"]
    plan = create_plan(athlete_id, template_id)
    plan_id = plan["id"]
    
    # Check plan response
    assert_true(len(plan["id"]) == 36, "Plan ID is UUID (36 chars)")
    assert_true("-" in plan["id"], "Plan ID has hyphens (UUID format)")
    assert_true("_id" not in plan, "Plan response has no _id field")
    
    # Check week-progress response
    week_progress = get_week_progress(plan_id, 1)
    assert_true("_id" not in week_progress, "Week-progress response has no _id field")
    
    # Check day response
    day_resp = get_plan_day(plan_id, 1, 1)
    assert_true("_id" not in day_resp, "Day response has no _id field")
    
    # Check stats response
    stats = get_stats(athlete_id)
    assert_true("_id" not in stats, "Stats response has no _id field")
    
    log("\n✅ GENERAL ASSERTIONS PASSED: UUIDs only, no _id leaks")
    return True

def main():
    """Run all bugfix tests"""
    log("="*80)
    log("BUGFIX ROUND (Groups A+B) - Backend Tests")
    log("="*80)
    
    try:
        # Test 1: Training-days remap
        test_training_days_remap()
        
        # Test 2: Streak only counts real work
        test_streak_only_counts_real_work()
        
        # Test 3: Robustness
        test_robustness()
        
        # General assertions
        test_general_assertions()
        
        log("\n" + "="*80)
        log("✅ ALL BUGFIX TESTS PASSED")
        log("="*80)
        return 0
        
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
