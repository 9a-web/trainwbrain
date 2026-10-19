#!/usr/bin/env python3
"""
TrainWithBrain - Test Enhanced Edit Exercise Endpoint
Tests PATCH /api/sessions/{session_id}/exercise/{order}/edit
with add/delete sets and coach comment functionality
"""
import requests
import json

# Backend URL from frontend/.env
BASE_URL = "https://c066af1d-c6a2-4b54-9d64-10f4bb06bb78.preview.emergentagent.com/api"

# Test athlete
ATHLETE_ID = 990011

def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def print_test(name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {name}")
    if details:
        print(f"  → {details}")

def setup_session():
    """Setup: Create plan and start session"""
    print_section("SETUP: Create Plan and Start Session")
    
    # 1. Find powerlifting-peaking template
    print("1. Finding 'powerlifting-peaking' template...")
    resp = requests.get(f"{BASE_URL}/programs/templates")
    assert resp.status_code == 200, f"GET templates failed: {resp.status_code}"
    templates = resp.json()
    
    pl_template = None
    for t in templates:
        if t.get("slug") == "powerlifting-peaking":
            pl_template = t
            break
    
    assert pl_template is not None, "powerlifting-peaking template not found"
    template_id = pl_template["id"]
    print_test("Found powerlifting-peaking template", True, f"Template ID: {template_id}")
    
    # 2. Create plan for athlete 990011
    print("\n2. Creating plan for athlete 990011...")
    resp = requests.post(f"{BASE_URL}/plans", json={
        "athlete_telegram_id": ATHLETE_ID,
        "template_id": template_id
    })
    assert resp.status_code == 200, f"POST /api/plans failed: {resp.status_code} - {resp.text}"
    plan = resp.json()
    plan_id = plan["id"]
    
    # Verify one_rep_max
    orm = plan.get("one_rep_max", {})
    squat_1rm = orm.get("squat-competition")
    bench_1rm = orm.get("bench-press")
    deadlift_1rm = orm.get("deadlift")
    
    print_test("Plan created with one_rep_max", True, 
               f"squat-competition:{squat_1rm}, bench-press:{bench_1rm}, deadlift:{deadlift_1rm}")
    
    # 3. Start session for week=1, day=1
    print("\n3. Starting session for week=1, day=1...")
    resp = requests.post(f"{BASE_URL}/sessions/start", json={
        "plan_id": plan_id,
        "athlete_telegram_id": ATHLETE_ID,
        "week": 1,
        "day": 1
    })
    assert resp.status_code == 200, f"POST /api/sessions/start failed: {resp.status_code} - {resp.text}"
    session = resp.json()
    session_id = session["id"]
    
    exercises = session.get("exercises", [])
    ex0 = exercises[0] if exercises else None
    
    print_test("Session started", True, 
               f"Session ID: {session_id}, Exercises: {len(exercises)}, Ex[0] slug: {ex0.get('exercise_slug') if ex0 else 'N/A'}")
    
    # Verify exercise 0 is squat-competition
    assert ex0 and ex0.get("exercise_slug") == "squat-competition", \
        f"Exercise 0 should be squat-competition, got {ex0.get('exercise_slug') if ex0 else 'None'}"
    
    return plan_id, session_id, squat_1rm

def test_add_sets(session_id, squat_1rm):
    """Test 1: ADD SETS - add 3 sets with specific weights"""
    print_section("TEST 1: ADD SETS")
    
    resp = requests.patch(
        f"{BASE_URL}/sessions/{session_id}/exercise/0/edit",
        json={
            "sets_scheme": [
                {"weight": 100, "sets": 2, "reps": 5},
                {"weight": 110, "sets": 1, "reps": 3},
                {"weight": 120, "sets": 1, "reps": 1}
            ]
        }
    )
    
    assert resp.status_code == 200, f"PATCH edit failed: {resp.status_code} - {resp.text}"
    session = resp.json()
    
    ex0 = session["exercises"][0]
    sets = ex0.get("sets_scheme", [])
    tonnage = ex0.get("tonnage")
    
    # Verify 3 sets
    test_passed = len(sets) == 3
    print_test("Exercise has exactly 3 sets", test_passed, f"Got {len(sets)} sets")
    
    # Verify percent_1rm calculations (squat-competition 1RM = 170)
    # 100kg -> 59%, 110kg -> 65%, 120kg -> 71%
    expected_percents = [59, 65, 71]
    actual_percents = [s.get("percent_1rm") for s in sets]
    
    percents_match = actual_percents == expected_percents
    print_test("Percent 1RM calculated correctly", percents_match, 
               f"Expected {expected_percents}, Got {actual_percents}")
    
    # Verify tonnage: 100*2*5 + 110*1*3 + 120*1*1 = 1000 + 330 + 120 = 1450
    expected_tonnage = 1450
    tonnage_match = tonnage == expected_tonnage
    print_test("Tonnage calculated correctly", tonnage_match, 
               f"Expected {expected_tonnage}, Got {tonnage}")
    
    # Print sets details
    print("\nSets details:")
    for i, s in enumerate(sets):
        print(f"  Set {i+1}: weight={s.get('weight')}kg, sets={s.get('sets')}, reps={s.get('reps')}, percent_1rm={s.get('percent_1rm')}%")
    
    return test_passed and percents_match and tonnage_match

def test_delete_sets(session_id):
    """Test 2: DELETE SETS - reduce to 1 set"""
    print_section("TEST 2: DELETE SETS")
    
    resp = requests.patch(
        f"{BASE_URL}/sessions/{session_id}/exercise/0/edit",
        json={
            "sets_scheme": [
                {"weight": 100, "sets": 1, "reps": 5}
            ]
        }
    )
    
    assert resp.status_code == 200, f"PATCH edit failed: {resp.status_code} - {resp.text}"
    session = resp.json()
    
    ex0 = session["exercises"][0]
    sets = ex0.get("sets_scheme", [])
    tonnage = ex0.get("tonnage")
    
    # Verify exactly 1 set
    test_passed = len(sets) == 1
    print_test("Exercise has exactly 1 set", test_passed, f"Got {len(sets)} sets")
    
    # Verify tonnage: 100*1*5 = 500
    expected_tonnage = 500
    tonnage_match = tonnage == expected_tonnage
    print_test("Tonnage calculated correctly", tonnage_match, 
               f"Expected {expected_tonnage}, Got {tonnage}")
    
    print(f"\nRemaining set: weight={sets[0].get('weight')}kg, sets={sets[0].get('sets')}, reps={sets[0].get('reps')}, tonnage={tonnage}")
    
    return test_passed and tonnage_match

def test_comment_add(session_id):
    """Test 3: COMMENT ADD - add comment with whitespace (must trim)"""
    print_section("TEST 3: COMMENT ADD (with whitespace trimming)")
    
    resp = requests.patch(
        f"{BASE_URL}/sessions/{session_id}/exercise/0/edit",
        json={
            "comment": "  Болело плечо, снизил вес  "
        }
    )
    
    assert resp.status_code == 200, f"PATCH edit failed: {resp.status_code} - {resp.text}"
    session = resp.json()
    
    ex0 = session["exercises"][0]
    comment = ex0.get("comment")
    
    # Verify comment is trimmed
    expected_comment = "Болело плечо, снизил вес"
    comment_match = comment == expected_comment
    print_test("Comment trimmed correctly", comment_match, 
               f"Expected '{expected_comment}', Got '{comment}'")
    
    # Verify sets_scheme unchanged from test 2 (should still be 1 set)
    sets = ex0.get("sets_scheme", [])
    sets_unchanged = len(sets) == 1 and sets[0].get("weight") == 100
    print_test("Sets scheme unchanged", sets_unchanged, 
               f"Still has 1 set with weight=100kg")
    
    return comment_match and sets_unchanged

def test_comment_clear(session_id):
    """Test 4: COMMENT CLEAR - clear with empty string and null"""
    print_section("TEST 4: COMMENT CLEAR")
    
    # Clear with empty string
    print("4a. Clearing comment with empty string...")
    resp = requests.patch(
        f"{BASE_URL}/sessions/{session_id}/exercise/0/edit",
        json={
            "comment": ""
        }
    )
    
    assert resp.status_code == 200, f"PATCH edit failed: {resp.status_code} - {resp.text}"
    session = resp.json()
    
    ex0 = session["exercises"][0]
    comment = ex0.get("comment")
    
    cleared_with_empty = comment is None
    print_test("Comment cleared with empty string", cleared_with_empty, 
               f"comment = {comment}")
    
    # Set comment again for next test
    print("\n4b. Setting comment again...")
    resp = requests.patch(
        f"{BASE_URL}/sessions/{session_id}/exercise/0/edit",
        json={
            "comment": "Тест комментарий"
        }
    )
    assert resp.status_code == 200
    
    # Clear with null
    print("\n4c. Clearing comment with null...")
    resp = requests.patch(
        f"{BASE_URL}/sessions/{session_id}/exercise/0/edit",
        json={
            "comment": None
        }
    )
    
    assert resp.status_code == 200, f"PATCH edit failed: {resp.status_code} - {resp.text}"
    session = resp.json()
    
    ex0 = session["exercises"][0]
    comment = ex0.get("comment")
    
    cleared_with_null = comment is None
    print_test("Comment cleared with null", cleared_with_null, 
               f"comment = {comment}")
    
    return cleared_with_empty and cleared_with_null

def test_comment_persistence(session_id, plan_id):
    """Test 5: COMMENT PERSISTENCE - verify comment in GET endpoints"""
    print_section("TEST 5: COMMENT PERSISTENCE")
    
    # Set a comment
    print("5a. Setting comment...")
    resp = requests.patch(
        f"{BASE_URL}/sessions/{session_id}/exercise/0/edit",
        json={
            "comment": "Комментарий для тренера"
        }
    )
    assert resp.status_code == 200, f"PATCH edit failed: {resp.status_code} - {resp.text}"
    
    # Verify via GET /api/sessions/{session_id}
    print("\n5b. Verifying via GET /api/sessions/{session_id}...")
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}")
    assert resp.status_code == 200, f"GET session failed: {resp.status_code}"
    session = resp.json()
    
    ex0 = session["exercises"][0]
    comment_in_get = ex0.get("comment")
    
    get_session_match = comment_in_get == "Комментарий для тренера"
    print_test("Comment persisted in GET /api/sessions/{id}", get_session_match, 
               f"comment = '{comment_in_get}'")
    
    # Verify via GET /api/sessions/active
    print("\n5c. Verifying via GET /api/sessions/active...")
    resp = requests.get(f"{BASE_URL}/sessions/active", params={
        "plan_id": plan_id,
        "week": 1,
        "day": 1,
        "athlete": ATHLETE_ID
    })
    assert resp.status_code == 200, f"GET active session failed: {resp.status_code}"
    session = resp.json()
    
    ex0 = session["exercises"][0]
    comment_in_active = ex0.get("comment")
    
    get_active_match = comment_in_active == "Комментарий для тренера"
    print_test("Comment persisted in GET /api/sessions/active", get_active_match, 
               f"comment = '{comment_in_active}'")
    
    return get_session_match and get_active_match

def test_clamp(session_id):
    """Test 6: CLAMP - verify sets>=1 and reps>=0 clamping"""
    print_section("TEST 6: CLAMP (sets>=1, reps>=0)")
    
    resp = requests.patch(
        f"{BASE_URL}/sessions/{session_id}/exercise/0/edit",
        json={
            "sets_scheme": [
                {"weight": 80, "sets": 0, "reps": -3}
            ]
        }
    )
    
    assert resp.status_code == 200, f"PATCH edit failed: {resp.status_code} - {resp.text}"
    session = resp.json()
    
    ex0 = session["exercises"][0]
    sets = ex0.get("sets_scheme", [])
    tonnage = ex0.get("tonnage")
    
    # Verify clamping: sets=0 -> 1, reps=-3 -> 0
    if sets:
        actual_sets = sets[0].get("sets")
        actual_reps = sets[0].get("reps")
        
        sets_clamped = actual_sets == 1
        reps_clamped = actual_reps == 0
        
        print_test("Sets clamped to 1", sets_clamped, f"sets = {actual_sets}")
        print_test("Reps clamped to 0", reps_clamped, f"reps = {actual_reps}")
        
        # Tonnage should be 0 (since reps=0)
        tonnage_zero = tonnage == 0
        print_test("Tonnage is 0 (reps=0)", tonnage_zero, f"tonnage = {tonnage}")
        
        return sets_clamped and reps_clamped and tonnage_zero
    else:
        print_test("Sets scheme exists", False, "No sets found")
        return False

def test_combined(session_id):
    """Test 7: COMBINED - update both sets_scheme and comment on different exercise"""
    print_section("TEST 7: COMBINED (sets_scheme + comment on exercise order=1)")
    
    resp = requests.patch(
        f"{BASE_URL}/sessions/{session_id}/exercise/1/edit",
        json={
            "sets_scheme": [
                {"weight": 90, "sets": 3, "reps": 5}
            ],
            "comment": "норм"
        }
    )
    
    assert resp.status_code == 200, f"PATCH edit failed: {resp.status_code} - {resp.text}"
    session = resp.json()
    
    ex1 = session["exercises"][1]
    sets = ex1.get("sets_scheme", [])
    tonnage = ex1.get("tonnage")
    comment = ex1.get("comment")
    
    # Verify sets_scheme updated
    sets_match = len(sets) == 1 and sets[0].get("weight") == 90
    print_test("Sets scheme updated", sets_match, 
               f"1 set with weight=90kg")
    
    # Verify tonnage: 90*3*5 = 1350
    expected_tonnage = 1350
    tonnage_match = tonnage == expected_tonnage
    print_test("Tonnage calculated correctly", tonnage_match, 
               f"Expected {expected_tonnage}, Got {tonnage}")
    
    # Verify comment
    comment_match = comment == "норм"
    print_test("Comment set correctly", comment_match, 
               f"comment = '{comment}'")
    
    # Verify exercise 0 is untouched
    ex0 = session["exercises"][0]
    ex0_sets = ex0.get("sets_scheme", [])
    ex0_untouched = len(ex0_sets) == 1 and ex0_sets[0].get("weight") == 80
    print_test("Exercise 0 data untouched", ex0_untouched, 
               f"Ex0 still has 1 set with weight=80kg")
    
    return sets_match and tonnage_match and comment_match and ex0_untouched

def test_name_edit(session_id):
    """Test 8: NAME EDIT - verify exercise_name edit still works"""
    print_section("TEST 8: NAME EDIT (exercise_name)")
    
    resp = requests.patch(
        f"{BASE_URL}/sessions/{session_id}/exercise/2/edit",
        json={
            "exercise_name": "Тест присед"
        }
    )
    
    assert resp.status_code == 200, f"PATCH edit failed: {resp.status_code} - {resp.text}"
    session = resp.json()
    
    ex2 = session["exercises"][2]
    name = ex2.get("exercise_name")
    
    name_match = name == "Тест присед"
    print_test("Exercise name updated", name_match, 
               f"exercise_name = '{name}'")
    
    return name_match

def verify_response_structure(session_id):
    """Verify general response structure"""
    print_section("GENERAL ASSERTIONS")
    
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}")
    assert resp.status_code == 200
    session = resp.json()
    
    # Check no MongoDB _id leaks
    has_no_id = "_id" not in session
    print_test("No MongoDB _id in response", has_no_id)
    
    # Check all ids are UUID strings
    session_id_is_uuid = isinstance(session.get("id"), str) and len(session.get("id", "")) == 36
    print_test("Session ID is UUID string", session_id_is_uuid, 
               f"id = {session.get('id')}")
    
    # Check datetimes are ISO strings
    started_at = session.get("started_at")
    is_iso = isinstance(started_at, str) and "T" in started_at
    print_test("Datetime is ISO string", is_iso, 
               f"started_at = {started_at}")
    
    # Check stats object present
    has_stats = "stats" in session
    print_test("Stats object present", has_stats)
    
    return has_no_id and session_id_is_uuid and is_iso and has_stats

def main():
    print("\n" + "="*80)
    print("  TrainWithBrain - Enhanced Edit Exercise Endpoint Test")
    print("  Testing PATCH /api/sessions/{id}/exercise/{order}/edit")
    print("="*80)
    
    try:
        # Setup
        plan_id, session_id, squat_1rm = setup_session()
        
        # Run tests
        results = []
        results.append(("ADD SETS", test_add_sets(session_id, squat_1rm)))
        results.append(("DELETE SETS", test_delete_sets(session_id)))
        results.append(("COMMENT ADD", test_comment_add(session_id)))
        results.append(("COMMENT CLEAR", test_comment_clear(session_id)))
        results.append(("COMMENT PERSISTENCE", test_comment_persistence(session_id, plan_id)))
        results.append(("CLAMP", test_clamp(session_id)))
        results.append(("COMBINED", test_combined(session_id)))
        results.append(("NAME EDIT", test_name_edit(session_id)))
        results.append(("GENERAL ASSERTIONS", verify_response_structure(session_id)))
        
        # Summary
        print_section("TEST SUMMARY")
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status}: {name}")
        
        print(f"\n{'='*80}")
        print(f"  TOTAL: {passed}/{total} tests passed")
        print(f"{'='*80}\n")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED!")
            return 0
        else:
            print(f"⚠️  {total - passed} test(s) failed")
            return 1
            
    except Exception as e:
        print(f"\n❌ TEST EXECUTION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
