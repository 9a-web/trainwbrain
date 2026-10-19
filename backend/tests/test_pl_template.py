#!/usr/bin/env python3
"""
TrainWithBrain - Test imported powerlifting template + plan scaling
Tests the new '3 мес Подготовка на осень' template with maxes scaling and day remapping
"""
import requests
import json
from datetime import datetime

# Backend URL from frontend/.env
BASE_URL = "https://c066af1d-c6a2-4b54-9d64-10f4bb06bb78.preview.emergentagent.com/api"

# Test athletes
ATHLETE_WITH_MAXES = 661001
ATHLETE_NO_MAXES = 661002

def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def print_test(name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {name}")
    if details:
        print(f"  → {details}")

def test_1_template_list():
    """TEST 1: Template list - should have 4 templates now"""
    print_section("TEST 1: Template List (4 templates)")
    
    resp = requests.get(f"{BASE_URL}/programs/templates")
    assert resp.status_code == 200, f"GET templates failed: {resp.status_code}"
    templates = resp.json()
    
    # Should have exactly 4 templates
    count = len(templates)
    print_test("Template count is 4", count == 4, f"Count: {count}")
    
    # Find the new template
    pl_autumn = None
    for t in templates:
        if t.get("slug") == "pl-autumn-3m":
            pl_autumn = t
            break
    
    print_test("Found 'pl-autumn-3m' template", pl_autumn is not None)
    
    if pl_autumn:
        # Verify basic fields
        name_correct = pl_autumn.get("name") == "3 мес Подготовка на осень"
        print_test("Template name correct", name_correct, f"name='{pl_autumn.get('name')}'")
        
        weeks_count = pl_autumn.get("weeks_count")
        print_test("weeks_count is 12", weeks_count == 12, f"weeks_count={weeks_count}")
        
        requires_maxes = pl_autumn.get("requires_maxes")
        print_test("requires_maxes is true", requires_maxes is True, f"requires_maxes={requires_maxes}")
        
        base_maxes = pl_autumn.get("base_maxes", {})
        expected_base = {"squat": 200, "bench": 131, "deadlift": 230}
        base_correct = (base_maxes.get("squat") == 200 and 
                       base_maxes.get("bench") == 131 and 
                       base_maxes.get("deadlift") == 230)
        print_test("base_maxes correct", base_correct, 
                  f"base_maxes={base_maxes}")
        
        return pl_autumn["id"]
    
    return None


def test_2_template_detail(template_id):
    """TEST 2: Template detail - full 12 weeks structure"""
    print_section("TEST 2: Template Detail (12 weeks, 3 days/week)")
    
    resp = requests.get(f"{BASE_URL}/programs/templates/{template_id}")
    assert resp.status_code == 200, f"GET template detail failed: {resp.status_code}"
    template = resp.json()
    
    weeks = template.get("weeks", [])
    print_test("Template has 12 weeks", len(weeks) == 12, f"weeks count: {len(weeks)}")
    
    if weeks:
        week1 = weeks[0]
        days = week1.get("days", [])
        print_test("Week 1 has 3 days", len(days) == 3, f"days count: {len(days)}")
        
        # Check day indices (should be 2, 4, 6 = Tue, Thu, Sat)
        day_indices = sorted([d.get("day_index") for d in days])
        indices_correct = day_indices == [2, 4, 6]
        print_test("Week 1 day indices are [2,4,6]", indices_correct, f"day_indices={day_indices}")
        
        # Check first day structure
        if days:
            day1 = days[0]
            exercises = day1.get("exercises", [])
            print_test("Day 1 has exercises", len(exercises) > 0, f"exercise count: {len(exercises)}")
            
            # Find main exercises (with lift_group)
            main_exercises = [e for e in exercises if e.get("lift_group") in ["squat", "bench", "deadlift"]]
            print_test("Day 1 has main exercises with lift_group", len(main_exercises) > 0,
                      f"main exercises: {len(main_exercises)}")
            
            # Find accessory exercises
            accessory_exercises = [e for e in exercises if e.get("is_accessory") is True]
            print_test("Day 1 has accessory exercises", len(accessory_exercises) > 0,
                      f"accessory exercises: {len(accessory_exercises)}")
            
            # Verify accessory exercises have empty sets_scheme
            if accessory_exercises:
                acc = accessory_exercises[0]
                sets_scheme = acc.get("sets_scheme", [])
                print_test("Accessory exercise has empty sets_scheme", len(sets_scheme) == 0,
                          f"'{acc.get('exercise_name')}' sets_scheme length: {len(sets_scheme)}")
            
            # Verify main exercise has sets_scheme with weights
            if main_exercises:
                main = main_exercises[0]
                sets_scheme = main.get("sets_scheme", [])
                has_weights = len(sets_scheme) > 0 and sets_scheme[0].get("weight") is not None
                print_test("Main exercise has sets_scheme with weights", has_weights,
                          f"'{main.get('exercise_name')}' first set weight: {sets_scheme[0].get('weight') if sets_scheme else 'N/A'}")


def test_3_plan_with_scaling(template_id):
    """TEST 3: Plan creation with custom maxes and training_days - verify scaling"""
    print_section("TEST 3: Plan Creation with Scaling")
    
    # Custom maxes (different from base_maxes)
    custom_maxes = {
        "squat": 180,    # base: 200, factor: 0.9
        "bench": 120,    # base: 131, factor: 0.916
        "deadlift": 210  # base: 230, factor: 0.913
    }
    
    # Custom training days (Mon, Wed, Fri instead of Tue, Thu, Sat)
    training_days = [1, 3, 5]
    
    print(f"Creating plan with maxes={custom_maxes}, training_days={training_days}")
    
    plan_payload = {
        "athlete_telegram_id": ATHLETE_WITH_MAXES,
        "template_id": template_id,
        "maxes": custom_maxes,
        "training_days": training_days
    }
    
    resp = requests.post(f"{BASE_URL}/plans", json=plan_payload)
    assert resp.status_code == 200, f"POST plan failed: {resp.status_code} - {resp.text}"
    plan = resp.json()
    plan_id = plan["id"]
    
    # Verify plan.maxes stored
    plan_maxes = plan.get("maxes", {})
    maxes_correct = (plan_maxes.get("squat") == 180 and 
                    plan_maxes.get("bench") == 120 and 
                    plan_maxes.get("deadlift") == 210)
    print_test("Plan.maxes stored correctly", maxes_correct, f"maxes={plan_maxes}")
    
    # Verify plan.training_days stored
    plan_days = plan.get("training_days", [])
    days_correct = sorted(plan_days) == [1, 3, 5]
    print_test("Plan.training_days stored correctly", days_correct, f"training_days={plan_days}")
    
    # Verify one_rep_max scaled
    orm = plan.get("one_rep_max", {})
    print("\nVerifying scaled one_rep_max:")
    
    # squat-competition: base 200 * 0.9 = 180.0
    squat_comp = orm.get("squat-competition")
    squat_correct = squat_comp == 180.0
    print_test("squat-competition scaled to 180.0", squat_correct, f"value={squat_comp}")
    
    # bench-no-legs: base 117.9 * (120/131) = 108.0 (rounded)
    bench_no_legs = orm.get("bench-no-legs")
    # Expected: 117.9 * 0.916 = 108.0 (rounded to 1 decimal)
    bench_expected = round(117.9 * 120 / 131, 1)
    bench_correct = abs(bench_no_legs - bench_expected) < 0.2
    print_test(f"bench-no-legs scaled to ~{bench_expected}", bench_correct, 
              f"value={bench_no_legs}, expected={bench_expected}")
    
    # deadlift-classic: base 207 * (210/230) = 189.0
    deadlift_classic = orm.get("deadlift-classic")
    deadlift_expected = round(207 * 210 / 230, 1)
    deadlift_correct = abs(deadlift_classic - deadlift_expected) < 0.2
    print_test(f"deadlift-classic scaled to ~{deadlift_expected}", deadlift_correct,
              f"value={deadlift_classic}, expected={deadlift_expected}")
    
    # squat-paused: base 175 * 0.9 = 157.5
    squat_paused = orm.get("squat-paused")
    squat_paused_expected = round(175 * 180 / 200, 1)
    squat_paused_correct = abs(squat_paused - squat_paused_expected) < 0.2
    print_test(f"squat-paused scaled to ~{squat_paused_expected}", squat_paused_correct,
              f"value={squat_paused}, expected={squat_paused_expected}")
    
    # Verify week 1 days have remapped day_index [1,3,5]
    print("\nVerifying day remapping:")
    weeks = plan.get("weeks", [])
    if weeks:
        week1 = weeks[0]
        days = week1.get("days", [])
        workout_days = [d for d in days if not d.get("is_rest")]
        day_indices = sorted([d.get("day_index") for d in workout_days])
        
        indices_remapped = day_indices == [1, 3, 5]
        print_test("Week 1 workout days remapped to [1,3,5]", indices_remapped,
                  f"day_indices={day_indices}")
        
        # Verify first exercise weights are scaled
        if workout_days:
            day1 = workout_days[0]
            exercises = day1.get("exercises", [])
            
            # Find first squat exercise (should be squat-competition)
            squat_ex = None
            for e in exercises:
                if e.get("lift_group") == "squat":
                    squat_ex = e
                    break
            
            if squat_ex:
                sets_scheme = squat_ex.get("sets_scheme", [])
                if sets_scheme:
                    # Original weights: 160, 167.5, 135
                    # Scaled by 0.9: 144, 150.75, 121.5
                    # Rounded to 2.5kg: 145, 150, 122.5
                    weights = [s.get("weight") for s in sets_scheme]
                    expected_weights = [145.0, 150.0, 122.5]
                    
                    weights_correct = weights == expected_weights
                    print_test(f"Squat weights scaled correctly", weights_correct,
                              f"weights={weights}, expected={expected_weights}")
    
    return plan_id


def test_4_plan_day_endpoint(plan_id):
    """TEST 4: Plan day endpoint - verify exercises and accessory exercises"""
    print_section("TEST 4: Plan Day Endpoint")
    
    # Get week 1, day 1 (should be a workout day)
    resp = requests.get(f"{BASE_URL}/plans/{plan_id}/day", params={"week": 1, "day": 1})
    assert resp.status_code == 200, f"GET day failed: {resp.status_code}"
    day = resp.json()
    
    is_workout = not day.get("is_rest", True)
    print_test("Day 1 is workout day", is_workout, f"is_rest={day.get('is_rest')}")
    
    title = day.get("title", "")
    print_test("Day has title", bool(title), f"title='{title}'")
    
    group = day.get("group", "")
    print_test("Day has group", bool(group), f"group='{group}'")
    
    difficulty = day.get("difficulty")
    print_test("Day has difficulty", difficulty is not None, f"difficulty='{difficulty}'")
    
    exercises = day.get("exercises", [])
    print_test("Day has exercises", len(exercises) > 0, f"count={len(exercises)}")
    
    # Verify main exercises
    main_exercises = [e for e in exercises if not e.get("is_accessory")]
    print_test("Day has main exercises", len(main_exercises) > 0, f"count={len(main_exercises)}")
    
    if main_exercises:
        main = main_exercises[0]
        sets_scheme = main.get("sets_scheme", [])
        print_test("Main exercise has non-empty sets_scheme", len(sets_scheme) > 0,
                  f"'{main.get('exercise_name')}' sets count: {len(sets_scheme)}")
        
        if sets_scheme:
            first_set = sets_scheme[0]
            has_percent = "percent_1rm" in first_set
            print_test("Main exercise sets have percent_1rm", has_percent,
                      f"percent_1rm={first_set.get('percent_1rm')}")
    
    # Verify accessory exercises
    accessory_exercises = [e for e in exercises if e.get("is_accessory") is True]
    print_test("Day has accessory exercises", len(accessory_exercises) > 0,
              f"count={len(accessory_exercises)}")
    
    if accessory_exercises:
        acc = accessory_exercises[0]
        sets_scheme = acc.get("sets_scheme", [])
        print_test("Accessory exercise has EMPTY sets_scheme", len(sets_scheme) == 0,
                  f"'{acc.get('exercise_name')}' sets count: {len(sets_scheme)}")
        
        is_acc_flag = acc.get("is_accessory")
        print_test("Accessory exercise has is_accessory=true", is_acc_flag is True,
                  f"is_accessory={is_acc_flag}")
    
    # Test rest day
    print("\nTesting rest day (day 2):")
    resp = requests.get(f"{BASE_URL}/plans/{plan_id}/day", params={"week": 1, "day": 2})
    assert resp.status_code == 200, f"GET day 2 failed: {resp.status_code}"
    day2 = resp.json()
    
    is_rest = day2.get("is_rest", False)
    print_test("Day 2 is rest day", is_rest, f"is_rest={is_rest}")


def test_5_week_progress(plan_id):
    """TEST 5: Week progress - verify training days remapped"""
    print_section("TEST 5: Week Progress")
    
    resp = requests.get(f"{BASE_URL}/plans/{plan_id}/week-progress", params={"week": 1})
    assert resp.status_code == 200, f"GET week-progress failed: {resp.status_code}"
    progress = resp.json()
    
    days = progress.get("days", [])
    print_test("Week progress has 7 days", len(days) == 7, f"count={len(days)}")
    
    # Find workout days
    workout_days = [d for d in days if d.get("is_workout") is True]
    workout_indices = sorted([d.get("day_index") for d in workout_days])
    
    print_test("Workout days are [1,3,5]", workout_indices == [1, 3, 5],
              f"workout day_indices={workout_indices}")
    
    # Verify rest days
    rest_days = [d for d in days if d.get("is_workout") is False]
    rest_indices = sorted([d.get("day_index") for d in rest_days])
    
    print_test("Rest days are [2,4,6,7]", rest_indices == [2, 4, 6, 7],
              f"rest day_indices={rest_indices}")


def test_6_no_maxes_path(template_id):
    """TEST 6: Create plan without maxes/training_days - should use defaults"""
    print_section("TEST 6: Plan Creation WITHOUT Maxes (default path)")
    
    plan_payload = {
        "athlete_telegram_id": ATHLETE_NO_MAXES,
        "template_id": template_id
        # NO maxes, NO training_days
    }
    
    resp = requests.post(f"{BASE_URL}/plans", json=plan_payload)
    assert resp.status_code == 200, f"POST plan failed: {resp.status_code} - {resp.text}"
    plan = resp.json()
    plan_id = plan["id"]
    
    print_test("Plan created successfully without maxes", True, f"plan_id={plan_id[:8]}...")
    
    # Verify one_rep_max uses template defaults
    orm = plan.get("one_rep_max", {})
    squat_comp = orm.get("squat-competition")
    squat_default = squat_comp == 200.0  # template default
    print_test("one_rep_max uses template default (squat-competition=200)", squat_default,
              f"value={squat_comp}")
    
    # Verify week 1 days use template default day_index [2,4,6]
    weeks = plan.get("weeks", [])
    if weeks:
        week1 = weeks[0]
        days = week1.get("days", [])
        workout_days = [d for d in days if not d.get("is_rest")]
        day_indices = sorted([d.get("day_index") for d in workout_days])
        
        indices_default = day_indices == [2, 4, 6]
        print_test("Week 1 days use template default [2,4,6]", indices_default,
                  f"day_indices={day_indices}")
    
    # Verify first exercise weights are author defaults (not scaled)
    resp = requests.get(f"{BASE_URL}/plans/{plan_id}/day", params={"week": 1, "day": 2})
    assert resp.status_code == 200, f"GET day failed: {resp.status_code}"
    day = resp.json()
    
    exercises = day.get("exercises", [])
    if exercises:
        # Find first squat exercise
        squat_ex = None
        for e in exercises:
            if e.get("lift_group") == "squat":
                squat_ex = e
                break
        
        if squat_ex:
            sets_scheme = squat_ex.get("sets_scheme", [])
            if sets_scheme:
                # Original template weights: 160, 167.5, 135 (not scaled)
                first_weight = sets_scheme[0].get("weight")
                weight_default = first_weight == 160.0
                print_test("Squat weight uses template default (160.0)", weight_default,
                          f"first set weight={first_weight}")


def test_7_general_integrity():
    """TEST 7: General data integrity - UUIDs, no ObjectId, ISO datetimes"""
    print_section("TEST 7: General Data Integrity")
    
    resp = requests.get(f"{BASE_URL}/programs/templates")
    assert resp.status_code == 200
    templates = resp.json()
    
    if templates:
        t = templates[0]
        
        # Check UUID format
        has_id = "id" in t and isinstance(t["id"], str) and len(t["id"]) == 36
        print_test("Template has UUID string id", has_id, f"id length: {len(t.get('id', ''))}")
        
        # Check no MongoDB _id leak
        no_underscore_id = "_id" not in t
        print_test("No '_id' field (MongoDB ObjectId) leaked", no_underscore_id)
        
        # Check datetime is ISO string
        created_at = t.get("created_at")
        is_iso = isinstance(created_at, str)
        print_test("Datetime fields are ISO strings", is_iso,
                  f"created_at type: {type(created_at).__name__}")
        
        if is_iso:
            try:
                datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                print_test("Datetime is valid ISO format", True)
            except:
                print_test("Datetime is valid ISO format", False, f"value={created_at}")


def main():
    print("\n" + "="*80)
    print("  TrainWithBrain - Imported Powerlifting Template + Plan Scaling Test")
    print("  Template: '3 мес Подготовка на осень' (pl-autumn-3m)")
    print("  Testing: maxes scaling, day remapping, accessory exercises")
    print("="*80)
    
    try:
        # TEST 1: Template list (4 templates)
        template_id = test_1_template_list()
        if not template_id:
            print("\n❌ CRITICAL: Template 'pl-autumn-3m' not found. Cannot continue.")
            return 1
        
        # TEST 2: Template detail (12 weeks, 3 days/week)
        test_2_template_detail(template_id)
        
        # TEST 3: Plan with scaling (custom maxes + training_days)
        plan_id = test_3_plan_with_scaling(template_id)
        
        # TEST 4: Plan day endpoint (exercises + accessory)
        test_4_plan_day_endpoint(plan_id)
        
        # TEST 5: Week progress (remapped days)
        test_5_week_progress(plan_id)
        
        # TEST 6: No-maxes path (defaults)
        test_6_no_maxes_path(template_id)
        
        # TEST 7: General integrity
        test_7_general_integrity()
        
        print_section("ALL TESTS COMPLETED")
        print("✅ Imported powerlifting template + plan scaling tests complete!")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
