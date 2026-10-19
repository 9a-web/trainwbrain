#!/usr/bin/env python3
"""
Backend API tests for TrainWithBrain - Plan Editor (Coach) Endpoints
Tests ONLY the new plan editor CRUD endpoints as specified in review_request
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
print(f"Testing Plan Editor endpoints at: {API_BASE}\n")

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

# ============================================================================
# SETUP: Get template and create plan
# ============================================================================
print("=" * 80)
print("SETUP: Creating test plan for plan editor tests")
print("=" * 80)

# Get first template
r = requests.get(f"{API_BASE}/programs/templates")
assert_status(r, 200, "Get templates")
templates = r.json()
assert_true(len(templates) > 0, "Should have at least one template")
template_id = templates[0]["id"]
print(f"✓ Using template: {templates[0]['name']} (id={template_id})")

# Create a plan for athlete 734001
athlete_id = 734001
r = requests.post(f"{API_BASE}/plans", json={
    "athlete_telegram_id": athlete_id,
    "template_id": template_id
})
assert_status(r, 200, "Create plan")
plan = r.json()
plan_id = plan["id"]
print(f"✓ Created plan: {plan_id}")
print(f"  - Weeks: {len(plan.get('weeks', []))}")
print(f"  - Name: {plan.get('name')}")

# Verify plan has 4 weeks (Full Body template)
weeks_count = len(plan.get("weeks", []))
print(f"  - Plan has {weeks_count} weeks")

print()

# ============================================================================
# TEST 1: PATCH /api/plans/{id} - Update plan metadata
# ============================================================================
print("=" * 80)
print("TEST 1: PATCH /api/plans/{id} - Update plan metadata")
print("=" * 80)

def test_1_1_update_name():
    """Update plan name"""
    r = requests.patch(f"{API_BASE}/plans/{plan_id}", json={"name": "Custom"})
    assert_status(r, 200, "Update plan name")
    updated_plan = r.json()
    assert_eq(updated_plan.get("name"), "Custom", "name should be 'Custom'")

test("1.1 Update plan name", test_1_1_update_name)

def test_1_2_update_current_week():
    """Update current_week"""
    r = requests.patch(f"{API_BASE}/plans/{plan_id}", json={"current_week": 2})
    assert_status(r, 200, "Update current_week")
    updated_plan = r.json()
    assert_eq(updated_plan.get("current_week"), 2, "current_week should be 2")

test("1.2 Update current_week", test_1_2_update_current_week)

print()

# ============================================================================
# TEST 2: POST /api/plans/{id}/week - Add week
# ============================================================================
print("=" * 80)
print("TEST 2: POST /api/plans/{id}/week - Add week")
print("=" * 80)

def test_2_1_add_week():
    """Add a new week to the plan"""
    # Get current plan
    r = requests.get(f"{API_BASE}/plans/{plan_id}")
    assert_status(r, 200, "Get plan")
    plan_before = r.json()
    weeks_before = len(plan_before.get("weeks", []))
    max_week_index_before = max((w.get("week_index", 0) for w in plan_before.get("weeks", [])), default=0)
    
    # Add week
    r = requests.post(f"{API_BASE}/plans/{plan_id}/week")
    assert_status(r, 200, "Add week")
    plan_after = r.json()
    weeks_after = len(plan_after.get("weeks", []))
    
    # Verify weeks count increased by 1
    assert_eq(weeks_after, weeks_before + 1, f"weeks count should increase from {weeks_before} to {weeks_before + 1}")
    
    # Verify last week has correct week_index
    last_week = sorted(plan_after.get("weeks", []), key=lambda w: w.get("week_index", 0))[-1]
    assert_eq(last_week.get("week_index"), max_week_index_before + 1, f"last week_index should be {max_week_index_before + 1}")
    
    # Verify new week is published and has empty days
    assert_eq(last_week.get("published"), True, "new week should be published=true")
    assert_eq(last_week.get("days"), [], "new week should have empty days")

test("2.1 Add week (weeks length +1, correct week_index, published=true, days=[])", test_2_1_add_week)

print()

# ============================================================================
# TEST 3: PUT /api/plans/{id}/day - Upsert day
# ============================================================================
print("=" * 80)
print("TEST 3: PUT /api/plans/{id}/day - Upsert day")
print("=" * 80)

def test_3_1_add_day():
    """Add a new day to week 1"""
    r = requests.put(f"{API_BASE}/plans/{plan_id}/day", json={
        "week": 1,
        "day": 2,
        "title": "День тяги",
        "is_rest": False
    })
    assert_status(r, 200, "Add day")
    plan = r.json()
    
    # Find week 1
    week1 = next((w for w in plan.get("weeks", []) if w.get("week_index") == 1), None)
    assert_true(week1, "week 1 should exist")
    
    # Find day 2
    day2 = next((d for d in week1.get("days", []) if d.get("day_index") == 2), None)
    assert_true(day2, "day 2 should exist in week 1")
    assert_eq(day2.get("title"), "День тяги", "day title should be 'День тяги'")
    assert_eq(day2.get("is_rest"), False, "is_rest should be False")

test("3.1 Add day (week=1, day=2, title='День тяги', is_rest=false)", test_3_1_add_day)

def test_3_2_update_day_idempotent():
    """Update same day - should be idempotent"""
    # Call again with same day
    r = requests.put(f"{API_BASE}/plans/{plan_id}/day", json={
        "week": 1,
        "day": 2,
        "title": "День тяги обновлен",
        "is_rest": False
    })
    assert_status(r, 200, "Update day")
    plan = r.json()
    
    # Find week 1
    week1 = next((w for w in plan.get("weeks", []) if w.get("week_index") == 1), None)
    
    # Count days with day_index=2 (should be only 1)
    day2_count = sum(1 for d in week1.get("days", []) if d.get("day_index") == 2)
    assert_eq(day2_count, 1, "should have exactly 1 day with day_index=2 (no duplicate)")
    
    # Verify title updated
    day2 = next((d for d in week1.get("days", []) if d.get("day_index") == 2), None)
    assert_eq(day2.get("title"), "День тяги обновлен", "title should be updated")

test("3.2 Update same day (no duplicate, title updates in place)", test_3_2_update_day_idempotent)

def test_3_3_invalid_day():
    """day=8 should return 400"""
    r = requests.put(f"{API_BASE}/plans/{plan_id}/day", json={
        "week": 1,
        "day": 8,
        "title": "Invalid",
        "is_rest": False
    })
    assert_status(r, 400, "day=8 should return 400")

test("3.3 Invalid day (day=8 -> 400)", test_3_3_invalid_day)

def test_3_4_nonexistent_week():
    """week=99 should return 404"""
    r = requests.put(f"{API_BASE}/plans/{plan_id}/day", json={
        "week": 99,
        "day": 1,
        "title": "Test",
        "is_rest": False
    })
    assert_status(r, 404, "week=99 should return 404")

test("3.4 Nonexistent week (week=99 -> 404)", test_3_4_nonexistent_week)

print()

# ============================================================================
# TEST 4: PUT /api/plans/{id}/exercise - Upsert exercise
# ============================================================================
print("=" * 80)
print("TEST 4: PUT /api/plans/{id}/exercise - Upsert exercise")
print("=" * 80)

def test_4_1_add_exercise():
    """Add exercise to week=1, day=2"""
    r = requests.put(f"{API_BASE}/plans/{plan_id}/exercise", json={
        "week": 1,
        "day": 2,
        "exercise_name": "Становая",
        "muscle_group": "back",
        "difficulty": "Тяжело",
        "sets_scheme": [
            {"weight": 150, "sets": 3, "reps": 5}
        ],
        "rest_seconds": 180
    })
    assert_status(r, 200, "Add exercise")
    plan = r.json()
    
    # Find week 1, day 2
    week1 = next((w for w in plan.get("weeks", []) if w.get("week_index") == 1), None)
    day2 = next((d for d in week1.get("days", []) if d.get("day_index") == 2), None)
    
    # Verify exercise added
    exercises = day2.get("exercises", [])
    assert_true(len(exercises) > 0, "should have at least 1 exercise")
    
    # Find the exercise
    ex = next((e for e in exercises if e.get("exercise_name") == "Становая"), None)
    assert_true(ex, "exercise 'Становая' should exist")
    assert_eq(ex.get("muscle_group"), "back", "muscle_group should be 'back'")
    assert_eq(ex.get("difficulty"), "Тяжело", "difficulty should be 'Тяжело'")
    assert_eq(ex.get("rest_seconds"), 180, "rest_seconds should be 180")
    
    # Verify target_sets and target_weight
    assert_eq(ex.get("target_sets"), 3, "target_sets should be 3")
    assert_eq(ex.get("target_weight"), 150, "target_weight should be 150")

test("4.1 Add exercise (appends, target_sets=3, target_weight=150)", test_4_1_add_exercise)

def test_4_2_edit_exercise():
    """Edit exercise at order=0 with multiple sets"""
    r = requests.put(f"{API_BASE}/plans/{plan_id}/exercise", json={
        "week": 1,
        "day": 2,
        "order": 0,
        "exercise_name": "Становая",
        "muscle_group": "back",
        "difficulty": "Тяжело",
        "sets_scheme": [
            {"weight": 160, "sets": 1, "reps": 3},
            {"weight": 140, "sets": 2, "reps": 5}
        ],
        "rest_seconds": 180
    })
    assert_status(r, 200, "Edit exercise")
    plan = r.json()
    
    # Find week 1, day 2
    week1 = next((w for w in plan.get("weeks", []) if w.get("week_index") == 1), None)
    day2 = next((d for d in week1.get("days", []) if d.get("day_index") == 2), None)
    
    # Get exercise at order 0
    exercises = sorted(day2.get("exercises", []), key=lambda e: e.get("order", 0))
    ex = exercises[0]
    
    # Verify sets_scheme has 2 entries
    sets_scheme = ex.get("sets_scheme", [])
    assert_eq(len(sets_scheme), 2, "should have 2 sets")
    
    # Verify target_sets = sum of sets (1 + 2 = 3)
    assert_eq(ex.get("target_sets"), 3, "target_sets should be 3 (1+2)")
    
    # Verify target_weight = first set weight
    assert_eq(ex.get("target_weight"), 160, "target_weight should be 160 (first set)")

test("4.2 Edit exercise (order=0, 2 sets, target_sets=3)", test_4_2_edit_exercise)

def test_4_3_verify_day_view():
    """Verify GET /api/plans/{id}/day returns exercises with percent_1rm and tonnage"""
    r = requests.get(f"{API_BASE}/plans/{plan_id}/day", params={"week": 1, "day": 2})
    assert_status(r, 200, "Get plan day")
    day_data = r.json()
    
    # Verify exercises present
    exercises = day_data.get("exercises", [])
    assert_true(len(exercises) > 0, "should have exercises")
    
    # Get first exercise
    ex = exercises[0]
    
    # Verify sets_scheme has percent_1rm
    sets_scheme = ex.get("sets_scheme", [])
    assert_true(len(sets_scheme) > 0, "should have sets_scheme")
    for s in sets_scheme:
        assert_true("percent_1rm" in s, "each set should have percent_1rm key")
    
    # Verify tonnage calculation: 160*1*3 + 140*2*5 = 480 + 1400 = 1880
    tonnage = ex.get("tonnage", 0)
    assert_eq(tonnage, 1880, "tonnage should be 1880 (160*1*3 + 140*2*5)")

test("4.3 GET /api/plans/{id}/day?week=1&day=2 -> exercises[0].tonnage=1880, sets have percent_1rm", test_4_3_verify_day_view)

def test_4_4_missing_week():
    """Missing week -> 404"""
    r = requests.put(f"{API_BASE}/plans/{plan_id}/exercise", json={
        "week": 99,
        "day": 1,
        "exercise_name": "Test",
        "muscle_group": "chest",
        "sets_scheme": [{"weight": 100, "sets": 3, "reps": 10}]
    })
    assert_status(r, 404, "missing week should return 404")

test("4.4 Missing week -> 404", test_4_4_missing_week)

def test_4_5_missing_day():
    """Missing day -> 404"""
    r = requests.put(f"{API_BASE}/plans/{plan_id}/exercise", json={
        "week": 1,
        "day": 7,  # day 7 doesn't exist in week 1
        "exercise_name": "Test",
        "muscle_group": "chest",
        "sets_scheme": [{"weight": 100, "sets": 3, "reps": 10}]
    })
    assert_status(r, 404, "missing day should return 404")

test("4.5 Missing day -> 404", test_4_5_missing_day)

print()

# ============================================================================
# TEST 5: DELETE /api/plans/{id}/exercise - Delete exercise
# ============================================================================
print("=" * 80)
print("TEST 5: DELETE /api/plans/{id}/exercise - Delete exercise")
print("=" * 80)

def test_5_1_delete_exercise():
    """Delete exercise at order=0"""
    r = requests.delete(f"{API_BASE}/plans/{plan_id}/exercise", params={
        "week": 1,
        "day": 2,
        "order": 0
    })
    assert_status(r, 200, "Delete exercise")
    plan = r.json()
    
    # Verify exercise removed
    week1 = next((w for w in plan.get("weeks", []) if w.get("week_index") == 1), None)
    day2 = next((d for d in week1.get("days", []) if d.get("day_index") == 2), None)
    exercises = day2.get("exercises", [])
    
    # Should have 0 exercises now (we only added 1)
    assert_eq(len(exercises), 0, "should have 0 exercises after deletion")

test("5.1 Delete exercise (order=0 removed)", test_5_1_delete_exercise)

def test_5_2_out_of_range_order():
    """Out-of-range order -> 404"""
    r = requests.delete(f"{API_BASE}/plans/{plan_id}/exercise", params={
        "week": 1,
        "day": 2,
        "order": 99
    })
    assert_status(r, 404, "out-of-range order should return 404")

test("5.2 Out-of-range order -> 404", test_5_2_out_of_range_order)

print()

# ============================================================================
# TEST 6: DELETE /api/plans/{id}/day - Delete day
# ============================================================================
print("=" * 80)
print("TEST 6: DELETE /api/plans/{id}/day - Delete day")
print("=" * 80)

def test_6_1_delete_day():
    """Delete day week=1, day=2"""
    r = requests.delete(f"{API_BASE}/plans/{plan_id}/day", params={
        "week": 1,
        "day": 2
    })
    assert_status(r, 200, "Delete day")
    plan = r.json()
    
    # Verify day removed
    week1 = next((w for w in plan.get("weeks", []) if w.get("week_index") == 1), None)
    day2 = next((d for d in week1.get("days", []) if d.get("day_index") == 2), None)
    assert_eq(day2, None, "day 2 should be removed")

test("6.1 Delete day (week=1, day=2 removed)", test_6_1_delete_day)

def test_6_2_missing_day():
    """Missing day -> 404"""
    r = requests.delete(f"{API_BASE}/plans/{plan_id}/day", params={
        "week": 1,
        "day": 2  # already deleted
    })
    assert_status(r, 404, "missing day should return 404")

test("6.2 Missing day -> 404", test_6_2_missing_day)

print()

# ============================================================================
# TEST 7: DELETE /api/plans/{id}/week - Delete week and reindex
# ============================================================================
print("=" * 80)
print("TEST 7: DELETE /api/plans/{id}/week - Delete week and reindex")
print("=" * 80)

def test_7_1_delete_week():
    """Delete week 5 (the one we added) and verify reindexing"""
    # Get current plan
    r = requests.get(f"{API_BASE}/plans/{plan_id}")
    assert_status(r, 200, "Get plan")
    plan_before = r.json()
    weeks_before = len(plan_before.get("weeks", []))
    
    # Find the last week index
    last_week_index = max((w.get("week_index", 0) for w in plan_before.get("weeks", [])), default=0)
    
    # Delete the last week
    r = requests.delete(f"{API_BASE}/plans/{plan_id}/week", params={"week": last_week_index})
    assert_status(r, 200, "Delete week")
    plan_after = r.json()
    weeks_after = len(plan_after.get("weeks", []))
    
    # Verify weeks count decreased by 1
    assert_eq(weeks_after, weeks_before - 1, f"weeks count should decrease from {weeks_before} to {weeks_before - 1}")
    
    # Verify remaining weeks are reindexed contiguously 1..N
    week_indices = sorted([w.get("week_index", 0) for w in plan_after.get("weeks", [])])
    expected_indices = list(range(1, weeks_after + 1))
    assert_eq(week_indices, expected_indices, f"week_index should be contiguous 1..{weeks_after}")

test("7.1 Delete week (removed, remaining reindexed 1..N)", test_7_1_delete_week)

def test_7_2_nonexistent_week():
    """Nonexistent week -> 404"""
    r = requests.delete(f"{API_BASE}/plans/{plan_id}/week", params={"week": 99})
    assert_status(r, 404, "nonexistent week should return 404")

test("7.2 Nonexistent week -> 404", test_7_2_nonexistent_week)

print()

# ============================================================================
# SUMMARY
# ============================================================================
print("=" * 80)
print("TEST SUMMARY - PLAN EDITOR ENDPOINTS")
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
    print("✅ ALL PLAN EDITOR TESTS PASSED!")
    sys.exit(0)
