#!/usr/bin/env python3
"""
PHASE 1 PER-SET LOGGING TEST SUITE
Tests the new PATCH /api/sessions/{id}/exercise/{order}/set/{set_index} endpoint
and related set_logs functionality.
"""

import requests
import json
import random
import sys

# Backend URL from frontend/.env
BASE_URL = "https://e85f3b80-9cd5-4258-b364-92e2bfe58807.preview.emergentagent.com/api"

def log(msg):
    print(f"[TEST] {msg}")

def assert_test(condition, message):
    if not condition:
        log(f"❌ ASSERTION FAILED: {message}")
        sys.exit(1)
    log(f"✅ {message}")

def register_email_user(email, password, name):
    """Register email user and return token + telegram_id"""
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "name": name
    })
    assert_test(resp.status_code == 200, f"Register user {email}")
    data = resp.json()
    return data["token"], data["user"]["telegram_id"]

def get_templates():
    """Get program templates"""
    resp = requests.get(f"{BASE_URL}/programs/templates")
    assert_test(resp.status_code == 200, "Get templates")
    return resp.json()

def create_plan(token, athlete_tg, template_id, maxes=None, training_days=None):
    """Create a plan from template"""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "athlete_telegram_id": athlete_tg,
        "template_id": template_id
    }
    if maxes:
        payload["maxes"] = maxes
    if training_days:
        payload["training_days"] = training_days
    
    resp = requests.post(f"{BASE_URL}/plans", json=payload, headers=headers)
    assert_test(resp.status_code == 200, f"Create plan from template {template_id}")
    return resp.json()

def start_session(token, plan_id, athlete_tg, week, day, date=None):
    """Start a workout session"""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "plan_id": plan_id,
        "athlete_telegram_id": athlete_tg,
        "week": week,
        "day": day
    }
    if date:
        payload["date"] = date
    
    resp = requests.post(f"{BASE_URL}/sessions/start", json=payload, headers=headers)
    assert_test(resp.status_code == 200, f"Start session week={week} day={day}")
    return resp.json()

def get_session(session_id):
    """Get session details"""
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}")
    assert_test(resp.status_code == 200, f"Get session {session_id}")
    return resp.json()

def patch_set(session_id, order, set_index, payload, actor="athlete", by=None):
    """PATCH a specific set"""
    url = f"{BASE_URL}/sessions/{session_id}/exercise/{order}/set/{set_index}"
    params = {"actor": actor}
    if by is not None:
        params["by"] = by
    
    resp = requests.patch(url, json=payload, params=params)
    return resp

def patch_exercise(session_id, order, action, actor="athlete", by=None):
    """PATCH exercise with action (done/reset/skip)"""
    url = f"{BASE_URL}/sessions/{session_id}/exercise/{order}"
    params = {"action": action, "actor": actor}
    if by is not None:
        params["by"] = by
    
    resp = requests.patch(url, params=params)
    return resp

def link_coach_to_athlete(coach_token, coach_tg, athlete_tg):
    """Link coach to athlete"""
    # First generate invite code
    headers = {"Authorization": f"Bearer {coach_token}"}
    resp = requests.post(f"{BASE_URL}/coach/invite", json={"coach_telegram_id": coach_tg}, headers=headers)
    assert_test(resp.status_code == 200, "Generate coach invite code")
    invite_code = resp.json()["invite_code"]
    
    # Link athlete to coach
    resp = requests.post(f"{BASE_URL}/coach/link", json={
        "code": invite_code,
        "athlete_telegram_id": athlete_tg
    })
    assert_test(resp.status_code == 200, f"Link athlete {athlete_tg} to coach {coach_tg}")
    return invite_code

def main():
    log("=" * 80)
    log("PHASE 1 PER-SET LOGGING TEST SUITE")
    log("=" * 80)
    
    # SETUP: Register athlete
    rand_id = random.randint(1000000000, 9999999999)
    athlete_email = f"phase1test{rand_id}@example.com"
    athlete_password = "password123"
    athlete_name = "Phase1 Test Athlete"
    
    log(f"\n[SETUP] Registering athlete: {athlete_email}")
    athlete_token, athlete_tg = register_email_user(athlete_email, athlete_password, athlete_name)
    log(f"Athlete telegram_id: {athlete_tg}")
    
    # Get templates and find suitable one
    log("\n[SETUP] Finding template...")
    templates = get_templates()
    
    # Try to find 'full-body-beginner' or 'pl-autumn-3m'
    template = None
    for t in templates:
        if t.get("slug") in ["full-body-beginner", "pl-autumn-3m"]:
            template = t
            break
    
    if not template:
        template = templates[0]  # Use first available
    
    log(f"Using template: {template['name']} (slug={template.get('slug')})")
    
    # Create plan
    log("\n[SETUP] Creating plan...")
    maxes = None
    if template.get("requires_maxes"):
        maxes = {"squat": 200, "bench": 130, "deadlift": 230}
    
    training_days = [1, 3, 5]
    plan = create_plan(athlete_token, athlete_tg, template["id"], maxes=maxes, training_days=training_days)
    plan_id = plan["id"]
    log(f"Plan created: {plan_id}")
    
    # Find first workout day
    log("\n[SETUP] Finding first workout day...")
    workout_day = None
    for week in plan.get("weeks", []):
        for day in week.get("days", []):
            if not day.get("is_rest") and day.get("exercises"):
                workout_day = day["day_index"]
                break
        if workout_day:
            break
    
    if not workout_day:
        workout_day = training_days[0]
    
    log(f"First workout day: {workout_day}")
    
    # Start session
    log("\n[SETUP] Starting session...")
    session = start_session(athlete_token, plan_id, athlete_tg, week=1, day=workout_day)
    session_id = session["id"]
    log(f"Session started: {session_id}")
    
    # ========================================================================
    # TEST (a): STRUCTURE - verify set_logs structure
    # ========================================================================
    log("\n" + "=" * 80)
    log("TEST (a): STRUCTURE - verify set_logs length and structure")
    log("=" * 80)
    
    exercises = session.get("exercises", [])
    assert_test(len(exercises) > 0, "Session has exercises")
    
    first_ex = exercises[0]
    log(f"First exercise: {first_ex.get('exercise_name')}")
    log(f"is_accessory: {first_ex.get('is_accessory')}")
    
    # Main exercises should have set_logs
    if not first_ex.get("is_accessory"):
        set_logs = first_ex.get("set_logs", [])
        sets_scheme = first_ex.get("sets_scheme", [])
        
        # Calculate expected number of sets
        expected_sets = sum(s.get("sets", 0) for s in sets_scheme)
        
        log(f"sets_scheme: {sets_scheme}")
        log(f"Expected total sets: {expected_sets}")
        log(f"Actual set_logs length: {len(set_logs)}")
        
        assert_test(len(set_logs) == expected_sets, 
                   f"set_logs length ({len(set_logs)}) matches sum of target_sets ({expected_sets})")
        
        # Verify structure of each set_log
        for i, log_entry in enumerate(set_logs):
            assert_test("weight" in log_entry, f"set_logs[{i}] has 'weight' key")
            assert_test("reps" in log_entry, f"set_logs[{i}] has 'reps' key")
            assert_test("percent_1rm" in log_entry, f"set_logs[{i}] has 'percent_1rm' key")
            assert_test("done" in log_entry, f"set_logs[{i}] has 'done' key")
            assert_test(log_entry["done"] == False, f"set_logs[{i}].done is initially False")
        
        # Verify rest_seconds is present
        assert_test("rest_seconds" in first_ex, "rest_seconds field present")
        log(f"rest_seconds: {first_ex.get('rest_seconds')}")
    
    # Accessory exercises should have empty set_logs
    accessory_ex = next((e for e in exercises if e.get("is_accessory")), None)
    if accessory_ex:
        log(f"Accessory exercise: {accessory_ex.get('exercise_name')}")
        assert_test(len(accessory_ex.get("set_logs", [])) == 0, 
                   "Accessory exercise has empty set_logs")
    
    # ========================================================================
    # TEST (b): LOG ONE SET WITH ACTUALS
    # ========================================================================
    log("\n" + "=" * 80)
    log("TEST (b): LOG ONE SET WITH ACTUALS - PATCH set/0 with done:true, weight, reps")
    log("=" * 80)
    
    # Find first main exercise
    main_ex_order = None
    for ex in exercises:
        if not ex.get("is_accessory") and len(ex.get("set_logs", [])) > 0:
            main_ex_order = ex["order"]
            break
    
    assert_test(main_ex_order is not None, "Found main exercise with set_logs")
    
    # PATCH first set
    log(f"PATCH /sessions/{session_id}/exercise/{main_ex_order}/set/0")
    resp = patch_set(session_id, main_ex_order, 0, {
        "done": True,
        "weight": 60,
        "reps": 5
    })
    assert_test(resp.status_code == 200, "PATCH set/0 returns 200")
    
    updated_session = resp.json()
    updated_ex = next(e for e in updated_session["exercises"] if e["order"] == main_ex_order)
    
    # Verify edited flag
    assert_test(updated_ex.get("edited") == True, "exercise.edited == True")
    
    # Verify set_logs[0] updated
    set_log_0 = updated_ex["set_logs"][0]
    assert_test(set_log_0["done"] == True, "set_logs[0].done == True")
    assert_test(set_log_0["weight"] == 60, "set_logs[0].weight == 60")
    assert_test(set_log_0["reps"] == 5, "set_logs[0].reps == 5")
    
    # Verify sets_scheme collapsed to only done sets
    new_scheme = updated_ex["sets_scheme"]
    log(f"Updated sets_scheme: {new_scheme}")
    assert_test(len(new_scheme) == 1, "sets_scheme has 1 group (only done sets)")
    assert_test(new_scheme[0]["weight"] == 60, "sets_scheme[0].weight == 60")
    assert_test(new_scheme[0]["sets"] == 1, "sets_scheme[0].sets == 1")
    assert_test(new_scheme[0]["reps"] == 5, "sets_scheme[0].reps == 5")
    
    # Verify tonnage
    expected_tonnage = 60 * 1 * 5  # 300
    assert_test(updated_ex["tonnage"] == expected_tonnage, 
               f"tonnage == {expected_tonnage} (60*1*5)")
    
    # Verify status is 'in_progress' (not all sets done yet)
    assert_test(updated_ex["status"] == "in_progress", 
               "exercise.status == 'in_progress' (not all sets done)")
    
    # ========================================================================
    # TEST (c): COMPLETE EXERCISE VIA SETS
    # ========================================================================
    log("\n" + "=" * 80)
    log("TEST (c): COMPLETE EXERCISE VIA SETS - mark all remaining sets done")
    log("=" * 80)
    
    # Mark all remaining sets as done
    total_sets = len(updated_ex["set_logs"])
    log(f"Total sets in exercise: {total_sets}")
    
    for i in range(1, total_sets):
        log(f"Marking set {i} as done...")
        resp = patch_set(session_id, main_ex_order, i, {"done": True})
        assert_test(resp.status_code == 200, f"PATCH set/{i} returns 200")
    
    # Get final state
    final_session = get_session(session_id)
    completed_ex = next(e for e in final_session["exercises"] if e["order"] == main_ex_order)
    
    # Verify all sets are done
    all_done = all(s["done"] for s in completed_ex["set_logs"])
    assert_test(all_done, "All set_logs[].done == True")
    
    # Verify exercise status is 'done'
    assert_test(completed_ex["status"] == "done", "exercise.status == 'done'")
    
    # Verify filled_by is 'athlete'
    assert_test(completed_ex.get("filled_by") == "athlete", "filled_by == 'athlete'")
    
    # Verify next exercise became 'in_progress'
    next_ex = next((e for e in final_session["exercises"] if e["order"] == main_ex_order + 1), None)
    if next_ex:
        assert_test(next_ex["status"] == "in_progress", 
                   "Next exercise status == 'in_progress'")
    
    # ========================================================================
    # TEST (d): UNDO A SET
    # ========================================================================
    log("\n" + "=" * 80)
    log("TEST (d): UNDO A SET - PATCH set/0 with done:false")
    log("=" * 80)
    
    resp = patch_set(session_id, main_ex_order, 0, {"done": False})
    assert_test(resp.status_code == 200, "PATCH set/0 done:false returns 200")
    
    undone_session = resp.json()
    undone_ex = next(e for e in undone_session["exercises"] if e["order"] == main_ex_order)
    
    # Verify set_logs[0].done is False
    assert_test(undone_ex["set_logs"][0]["done"] == False, "set_logs[0].done == False")
    
    # Verify exercise status is 'in_progress' again
    assert_test(undone_ex["status"] == "in_progress", 
               "exercise.status == 'in_progress' (after undo)")
    
    # Verify session status is NOT 'finished'
    assert_test(undone_session["status"] != "finished", 
               "session.status != 'finished' (after undo)")
    
    # Verify coach_confirmed reset to false
    assert_test(undone_ex.get("coach_confirmed") == False, 
               "coach_confirmed reset to False")
    
    # Re-mark the set as done for next tests
    resp = patch_set(session_id, main_ex_order, 0, {"done": True})
    assert_test(resp.status_code == 200, "Re-mark set/0 as done")
    
    # Finish the first session to allow starting a fresh one
    log("\nFinishing first session to allow fresh session for coach test...")
    for ex in exercises:
        if ex["order"] != main_ex_order:  # Skip already completed exercise
            resp = patch_exercise(session_id, ex["order"], "done")
            assert_test(resp.status_code == 200, f"Mark exercise {ex['order']} done")
    
    # Verify first session is now finished
    finished_check = get_session(session_id)
    log(f"First session status after completing all exercises: {finished_check['status']}")
    
    # ========================================================================
    # TEST (e): COACH CO-SCRIBE
    # ========================================================================
    log("\n" + "=" * 80)
    log("TEST (e): COACH CO-SCRIBE - coach marking sets with actor=coach&by=<coach_tg>")
    log("=" * 80)
    
    # Register coach
    coach_email = f"phase1coach{rand_id}@example.com"
    coach_token, coach_tg = register_email_user(coach_email, "password123", "Phase1 Coach")
    log(f"Coach telegram_id: {coach_tg}")
    
    # Link coach to athlete
    link_coach_to_athlete(coach_token, coach_tg, athlete_tg)
    
    # Find another workout day for coach test (use second workout day if available)
    coach_test_day = training_days[1] if len(training_days) > 1 else training_days[0]
    
    # Start a new session for coach test
    session2 = start_session(athlete_token, plan_id, athlete_tg, week=1, day=coach_test_day)
    session2_id = session2["id"]
    log(f"Started new session for coach test (day={coach_test_day}): {session2_id}")
    
    # Get first exercise with set_logs
    session2_ex0 = session2["exercises"][0]
    total_sets_ex0 = len(session2_ex0.get("set_logs", []))
    
    # Coach marks first set
    log(f"Coach PATCH /sessions/{session2_id}/exercise/0/set/0 with actor=coach&by={coach_tg}")
    resp = patch_set(session2_id, 0, 0, {"done": True}, actor="coach", by=coach_tg)
    assert_test(resp.status_code == 200, "Coach PATCH set/0 returns 200")
    
    coach_session = resp.json()
    coach_ex = coach_session["exercises"][0]
    
    # Verify set is marked done
    assert_test(coach_ex["set_logs"][0]["done"] == True, "set_logs[0].done == True (by coach)")
    
    # Mark all remaining sets by coach to complete the exercise
    for i in range(1, total_sets_ex0):
        resp = patch_set(session2_id, 0, i, {"done": True}, actor="coach", by=coach_tg)
        assert_test(resp.status_code == 200, f"Coach PATCH set/{i} returns 200")
    
    # Get final state and verify filled_by
    coach_final = get_session(session2_id)
    coach_completed_ex = coach_final["exercises"][0]
    
    if coach_completed_ex["status"] == "done":
        assert_test(coach_completed_ex.get("filled_by") == "coach", 
                   "filled_by == 'coach' (when coach completes exercise)")
    
    # Test UNLINKED coach (should return 403)
    log("\nTesting UNLINKED coach...")
    unlinked_coach_email = f"phase1unlinked{rand_id}@example.com"
    unlinked_token, unlinked_tg = register_email_user(unlinked_coach_email, "password123", "Unlinked Coach")
    
    # Try to mark set with unlinked coach
    resp = patch_set(session2_id, 0, 0, {"done": True}, actor="coach", by=unlinked_tg)
    assert_test(resp.status_code == 403, "Unlinked coach returns 403")
    
    # Test actor=coach WITHOUT by parameter (should return 400)
    log("\nTesting actor=coach WITHOUT by parameter...")
    url = f"{BASE_URL}/sessions/{session2_id}/exercise/0/set/0"
    resp = requests.patch(url, json={"done": True}, params={"actor": "coach"})
    assert_test(resp.status_code == 400, "actor=coach without 'by' returns 400")
    
    # Finish the coach test session to allow starting new sessions
    log("\nFinishing coach test session...")
    for ex in session2["exercises"]:
        if ex["status"] != "done":
            resp = patch_exercise(session2_id, ex["order"], "done")
            assert_test(resp.status_code == 200, f"Mark exercise {ex['order']} done")
    
    coach_final_check = get_session(session2_id)
    log(f"Coach test session status: {coach_final_check['status']}")
    
    # ========================================================================
    # TEST (f): AUTO-FINISH
    # ========================================================================
    log("\n" + "=" * 80)
    log("TEST (f): AUTO-FINISH - mark all sets of all exercises done")
    log("=" * 80)
    
    # Now we can start a new session (no active sessions exist)
    session3 = start_session(athlete_token, plan_id, athlete_tg, week=1, day=workout_day, date="2026-08-15")
    session3_id = session3["id"]
    log(f"Started new session for auto-finish test (week=1, day={workout_day}, date=2026-08-15): {session3_id}")
    
    # Mark all exercises done using action=done
    for ex in session3["exercises"]:
        order = ex["order"]
        log(f"Marking exercise {order} as done...")
        resp = patch_exercise(session3_id, order, "done")
        assert_test(resp.status_code == 200, f"PATCH exercise/{order}?action=done returns 200")
    
    # Get final session
    finished_session = get_session(session3_id)
    
    # Verify session status is 'finished'
    assert_test(finished_session["status"] == "finished", "session.status == 'finished'")
    
    # Verify stats are frozen
    stats = finished_session.get("stats")
    assert_test(stats is not None, "session.stats is not null")
    assert_test(stats.get("sets_done", 0) > 0, "stats.sets_done > 0")
    # Note: tonnage may be 0 if template doesn't have weights defined
    log(f"Frozen stats: sets_done={stats.get('sets_done')}, tonnage={stats.get('tonnage')}, progress_pct={stats.get('progress_pct')}")
    
    # ========================================================================
    # TEST (g): NEGATIVES
    # ========================================================================
    log("\n" + "=" * 80)
    log("TEST (g): NEGATIVES - out of range set_index, unknown session")
    log("=" * 80)
    
    # Test set_index out of range
    log("Testing set_index out of range (999)...")
    resp = patch_set(session_id, 0, 999, {"done": True})
    assert_test(resp.status_code == 404, "set_index=999 returns 404")
    
    # Test unknown session
    log("Testing unknown session...")
    resp = patch_set("non-existent-session-id-12345", 0, 0, {"done": True})
    assert_test(resp.status_code == 404, "Unknown session returns 404")
    
    # ========================================================================
    # TEST (h): COMPATIBILITY
    # ========================================================================
    log("\n" + "=" * 80)
    log("TEST (h): COMPATIBILITY - action=done marks all set_logs, action=reset clears")
    log("=" * 80)
    
    # Use a much later date parameter to create a distinct session for the same week/day
    session4 = start_session(athlete_token, plan_id, athlete_tg, week=1, day=workout_day, date="2026-09-15")
    session4_id = session4["id"]
    log(f"Started new session for compatibility test (week=1, day={workout_day}, date=2026-09-15): {session4_id}")
    
    # Use action=done on first exercise
    log("PATCH /exercise/0?action=done...")
    resp = patch_exercise(session4_id, 0, "done")
    assert_test(resp.status_code == 200, "PATCH exercise/0?action=done returns 200")
    
    compat_session = resp.json()
    compat_ex = compat_session["exercises"][0]
    
    # Verify all set_logs[].done == True
    all_done = all(s["done"] for s in compat_ex.get("set_logs", []))
    assert_test(all_done, "action=done marks all set_logs[].done == True")
    
    # Verify status is 'done'
    assert_test(compat_ex["status"] == "done", "exercise.status == 'done'")
    
    # Now use action=reset
    log("PATCH /exercise/0?action=reset...")
    resp = patch_exercise(session4_id, 0, "reset")
    assert_test(resp.status_code == 200, "PATCH exercise/0?action=reset returns 200")
    
    reset_session = resp.json()
    reset_ex = reset_session["exercises"][0]
    
    # Verify all set_logs[].done == False
    all_not_done = all(not s["done"] for s in reset_ex.get("set_logs", []))
    assert_test(all_not_done, "action=reset marks all set_logs[].done == False")
    
    # Verify status is 'pending'
    assert_test(reset_ex["status"] == "pending", "exercise.status == 'pending'")
    
    # ========================================================================
    # GENERAL ASSERTIONS
    # ========================================================================
    log("\n" + "=" * 80)
    log("GENERAL ASSERTIONS - UUIDs, ISO datetimes, no _id leaks")
    log("=" * 80)
    
    # Check session structure
    test_session = get_session(session_id)
    
    # Verify UUID format (36 chars)
    assert_test(len(test_session["id"]) == 36, "session.id is UUID (36 chars)")
    assert_test(len(test_session["plan_id"]) == 36, "session.plan_id is UUID")
    
    # Verify ISO datetime format
    assert_test("T" in test_session.get("started_at", ""), "started_at is ISO datetime")
    
    # Verify no _id leaks
    assert_test("_id" not in test_session, "No _id in session response")
    for ex in test_session.get("exercises", []):
        assert_test("_id" not in ex, "No _id in exercise")
    
    # Verify no password_hash leaks
    resp = requests.get(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {athlete_token}"})
    user = resp.json()
    assert_test("password_hash" not in user, "No password_hash in user response")
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    log("\n" + "=" * 80)
    log("✅✅✅ ALL PHASE 1 PER-SET LOGGING TESTS PASSED ✅✅✅")
    log("=" * 80)
    log(f"\nTest Summary:")
    log(f"  Athlete: {athlete_email} (telegram_id={athlete_tg})")
    log(f"  Coach: {coach_email} (telegram_id={coach_tg})")
    log(f"  Plan: {plan_id}")
    log(f"  Template: {template['name']}")
    log(f"  Sessions tested: {session_id}, {session2_id}, {session3_id}, {session4_id}")
    log(f"\nAll scenarios verified:")
    log(f"  (a) ✅ STRUCTURE: set_logs length and structure correct")
    log(f"  (b) ✅ LOG ONE SET: PATCH with done/weight/reps works")
    log(f"  (c) ✅ COMPLETE EXERCISE: marking all sets done completes exercise")
    log(f"  (d) ✅ UNDO SET: done:false reverts status")
    log(f"  (e) ✅ COACH CO-SCRIBE: coach can mark sets, unlinked coach 403, no 'by' 400")
    log(f"  (f) ✅ AUTO-FINISH: all exercises done -> session finished with stats")
    log(f"  (g) ✅ NEGATIVES: out of range 404, unknown session 404")
    log(f"  (h) ✅ COMPATIBILITY: action=done/reset works with set_logs")
    log(f"  (i) ✅ GENERAL: UUIDs, ISO datetimes, no _id/password_hash leaks")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ TEST FAILED WITH EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
