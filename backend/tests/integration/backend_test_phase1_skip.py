#!/usr/bin/env python3
"""
PHASE 1 PER-SET LOGGING WITH SKIP TEST SUITE
Tests the PATCH /api/sessions/{id}/exercise/{order}/set/{set_index} endpoint
with the NEW per-set SKIP functionality added in follow-up change.

This test suite covers:
- NEW SKIP scenarios (aa)-(ff)
- Original done-path scenarios (a)-(g) to ensure backward compatibility
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
    log("PHASE 1 PER-SET LOGGING WITH SKIP TEST SUITE")
    log("=" * 80)
    
    # SETUP: Register athlete
    rand_id = random.randint(1000000000, 9999999999)
    athlete_email = f"phase1skip{rand_id}@example.com"
    athlete_password = "password123"
    athlete_name = "Phase1 Skip Test Athlete"
    
    log(f"\n[SETUP] Registering athlete: {athlete_email}")
    athlete_token, athlete_tg = register_email_user(athlete_email, athlete_password, athlete_name)
    log(f"Athlete telegram_id: {athlete_tg}")
    
    # Get templates and find suitable one
    log("\n[SETUP] Finding template...")
    templates = get_templates()
    
    # Try to find 'full-body-beginner'
    template = None
    for t in templates:
        if t.get("slug") == "full-body-beginner":
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
    
    # ========================================================================
    # NEW TEST (aa): SKIP ONE SET
    # ========================================================================
    log("\n" + "=" * 80)
    log("NEW TEST (aa): SKIP ONE SET - PATCH set/0 {skipped:true}")
    log("=" * 80)
    
    # Start fresh session
    session_aa = start_session(athlete_token, plan_id, athlete_tg, week=1, day=workout_day, date="2026-01-10")
    session_aa_id = session_aa["id"]
    log(f"Session started: {session_aa_id}")
    
    # PATCH first set with skipped:true
    log(f"PATCH /sessions/{session_aa_id}/exercise/0/set/0 {{skipped:true}}")
    resp = patch_set(session_aa_id, 0, 0, {"skipped": True})
    assert_test(resp.status_code == 200, "PATCH set/0 skipped:true returns 200")
    
    updated = resp.json()
    ex0 = updated["exercises"][0]
    
    # Verify set_logs[0].skipped == true AND done == false
    assert_test(ex0["set_logs"][0]["skipped"] == True, "set_logs[0].skipped == True")
    assert_test(ex0["set_logs"][0]["done"] == False, "set_logs[0].done == False")
    
    # Verify exercise status is 'in_progress' (not all sets settled)
    assert_test(ex0["status"] == "in_progress", "exercise.status == 'in_progress'")
    
    # Finish session_aa to allow starting new sessions
    log("\nFinishing session_aa...")
    for ex in session_aa["exercises"]:
        resp = patch_exercise(session_aa_id, ex["order"], "done")
        assert_test(resp.status_code == 200, f"Mark exercise {ex['order']} done")
    
    # ========================================================================
    # NEW TEST (bb): MIX SKIP AND DONE
    # ========================================================================
    log("\n" + "=" * 80)
    log("NEW TEST (bb): MIX SKIP AND DONE - 1 set skipped + rest done -> status 'done'")
    log("=" * 80)
    
    # Start fresh session
    session_bb = start_session(athlete_token, plan_id, athlete_tg, week=1, day=workout_day, date="2026-01-11")
    session_bb_id = session_bb["id"]
    log(f"Session started: {session_bb_id}")
    
    # Get first exercise
    ex0_bb = session_bb["exercises"][0]
    total_sets = len(ex0_bb["set_logs"])
    log(f"First exercise has {total_sets} sets")
    
    # Mark first set as skipped
    log("PATCH set/0 {skipped:true}")
    resp = patch_set(session_bb_id, 0, 0, {"skipped": True})
    assert_test(resp.status_code == 200, "PATCH set/0 skipped:true returns 200")
    
    # Mark all remaining sets as done
    for i in range(1, total_sets):
        log(f"PATCH set/{i} {{done:true}}")
        resp = patch_set(session_bb_id, 0, i, {"done": True})
        assert_test(resp.status_code == 200, f"PATCH set/{i} done:true returns 200")
    
    # Get final state
    final_bb = get_session(session_bb_id)
    ex0_final = final_bb["exercises"][0]
    
    # Verify exercise status is 'done' (because at least one set is done)
    assert_test(ex0_final["status"] == "done", 
               "exercise.status == 'done' (at least one set done, even with skipped sets)")
    
    # Verify set_logs reflect mix
    assert_test(ex0_final["set_logs"][0]["skipped"] == True, "set_logs[0].skipped == True")
    assert_test(ex0_final["set_logs"][0]["done"] == False, "set_logs[0].done == False")
    for i in range(1, total_sets):
        assert_test(ex0_final["set_logs"][i]["done"] == True, f"set_logs[{i}].done == True")
        assert_test(ex0_final["set_logs"][i].get("skipped", False) == False, 
                   f"set_logs[{i}].skipped == False")
    
    # Finish session_bb
    log("\nFinishing session_bb...")
    for ex in session_bb["exercises"]:
        if ex["order"] != 0:
            resp = patch_exercise(session_bb_id, ex["order"], "done")
            assert_test(resp.status_code == 200, f"Mark exercise {ex['order']} done")
    
    # ========================================================================
    # NEW TEST (cc): SKIP ALL SETS
    # ========================================================================
    log("\n" + "=" * 80)
    log("NEW TEST (cc): SKIP ALL SETS - all sets skipped -> status 'skipped', tonnage 0")
    log("=" * 80)
    
    # Start fresh session
    session_cc = start_session(athlete_token, plan_id, athlete_tg, week=1, day=workout_day, date="2026-01-12")
    session_cc_id = session_cc["id"]
    log(f"Session started: {session_cc_id}")
    
    # Get first exercise
    ex0_cc = session_cc["exercises"][0]
    total_sets_cc = len(ex0_cc["set_logs"])
    log(f"First exercise has {total_sets_cc} sets")
    
    # Mark all sets as skipped
    for i in range(total_sets_cc):
        log(f"PATCH set/{i} {{skipped:true}}")
        resp = patch_set(session_cc_id, 0, i, {"skipped": True})
        assert_test(resp.status_code == 200, f"PATCH set/{i} skipped:true returns 200")
    
    # Get final state
    final_cc = get_session(session_cc_id)
    ex0_final_cc = final_cc["exercises"][0]
    
    # Verify exercise status is 'skipped'
    assert_test(ex0_final_cc["status"] == "skipped", 
               "exercise.status == 'skipped' (all sets skipped)")
    
    # Verify tonnage is 0
    assert_test(ex0_final_cc["tonnage"] == 0, "tonnage == 0 (all sets skipped)")
    
    # Verify all set_logs are skipped
    for i in range(total_sets_cc):
        assert_test(ex0_final_cc["set_logs"][i]["skipped"] == True, 
                   f"set_logs[{i}].skipped == True")
        assert_test(ex0_final_cc["set_logs"][i]["done"] == False, 
                   f"set_logs[{i}].done == False")
    
    # Finish session_cc
    log("\nFinishing session_cc...")
    for ex in session_cc["exercises"]:
        if ex["order"] != 0:
            resp = patch_exercise(session_cc_id, ex["order"], "done")
            assert_test(resp.status_code == 200, f"Mark exercise {ex['order']} done")
    
    # ========================================================================
    # NEW TEST (dd): EXCLUSIVITY - done and skipped are mutually exclusive
    # ========================================================================
    log("\n" + "=" * 80)
    log("NEW TEST (dd): EXCLUSIVITY - done and skipped are mutually exclusive")
    log("=" * 80)
    
    # Start fresh session
    session_dd = start_session(athlete_token, plan_id, athlete_tg, week=1, day=workout_day, date="2026-01-13")
    session_dd_id = session_dd["id"]
    log(f"Session started: {session_dd_id}")
    
    # Step 1: Mark set/0 as skipped
    log("Step 1: PATCH set/0 {skipped:true}")
    resp = patch_set(session_dd_id, 0, 0, {"skipped": True})
    assert_test(resp.status_code == 200, "PATCH set/0 skipped:true returns 200")
    
    s1 = resp.json()
    assert_test(s1["exercises"][0]["set_logs"][0]["skipped"] == True, "set_logs[0].skipped == True")
    assert_test(s1["exercises"][0]["set_logs"][0]["done"] == False, "set_logs[0].done == False")
    
    # Step 2: Mark set/0 as done (should clear skipped)
    log("Step 2: PATCH set/0 {done:true} (should clear skipped)")
    resp = patch_set(session_dd_id, 0, 0, {"done": True})
    assert_test(resp.status_code == 200, "PATCH set/0 done:true returns 200")
    
    s2 = resp.json()
    assert_test(s2["exercises"][0]["set_logs"][0]["done"] == True, "set_logs[0].done == True")
    assert_test(s2["exercises"][0]["set_logs"][0]["skipped"] == False, 
               "set_logs[0].skipped == False (cleared by done:true)")
    
    # Step 3: Mark set/0 as skipped again (should clear done)
    log("Step 3: PATCH set/0 {skipped:true} (should clear done)")
    resp = patch_set(session_dd_id, 0, 0, {"skipped": True})
    assert_test(resp.status_code == 200, "PATCH set/0 skipped:true returns 200")
    
    s3 = resp.json()
    assert_test(s3["exercises"][0]["set_logs"][0]["skipped"] == True, "set_logs[0].skipped == True")
    assert_test(s3["exercises"][0]["set_logs"][0]["done"] == False, 
               "set_logs[0].done == False (cleared by skipped:true)")
    
    # Finish session_dd
    log("\nFinishing session_dd...")
    for ex in session_dd["exercises"]:
        resp = patch_exercise(session_dd_id, ex["order"], "done")
        assert_test(resp.status_code == 200, f"Mark exercise {ex['order']} done")
    
    # ========================================================================
    # NEW TEST (ee): COACH CO-SCRIBE WITH SKIP
    # ========================================================================
    log("\n" + "=" * 80)
    log("NEW TEST (ee): COACH CO-SCRIBE WITH SKIP")
    log("=" * 80)
    
    # Register coach
    coach_email = f"phase1skipcoach{rand_id}@example.com"
    coach_token, coach_tg = register_email_user(coach_email, "password123", "Phase1 Skip Coach")
    log(f"Coach telegram_id: {coach_tg}")
    
    # Link coach to athlete
    link_coach_to_athlete(coach_token, coach_tg, athlete_tg)
    
    # Start fresh session
    session_ee = start_session(athlete_token, plan_id, athlete_tg, week=1, day=workout_day, date="2026-01-14")
    session_ee_id = session_ee["id"]
    log(f"Session started: {session_ee_id}")
    
    # Coach marks set/0 as skipped
    log(f"Coach PATCH set/0 {{skipped:true}} with actor=coach&by={coach_tg}")
    resp = patch_set(session_ee_id, 0, 0, {"skipped": True}, actor="coach", by=coach_tg)
    assert_test(resp.status_code == 200, "Coach PATCH set/0 skipped:true returns 200")
    
    s_ee = resp.json()
    assert_test(s_ee["exercises"][0]["set_logs"][0]["skipped"] == True, 
               "set_logs[0].skipped == True (by coach)")
    
    # Test UNLINKED coach (should return 403)
    log("\nTesting UNLINKED coach with skip...")
    unlinked_coach_email = f"phase1skipunlinked{rand_id}@example.com"
    unlinked_token, unlinked_tg = register_email_user(unlinked_coach_email, "password123", "Unlinked Skip Coach")
    
    resp = patch_set(session_ee_id, 0, 0, {"skipped": True}, actor="coach", by=unlinked_tg)
    assert_test(resp.status_code == 403, "Unlinked coach returns 403")
    
    # Test actor=coach WITHOUT by parameter (should return 400)
    log("\nTesting actor=coach WITHOUT by parameter...")
    url = f"{BASE_URL}/sessions/{session_ee_id}/exercise/0/set/0"
    resp = requests.patch(url, json={"skipped": True}, params={"actor": "coach"})
    assert_test(resp.status_code == 400, "actor=coach without 'by' returns 400")
    
    # Finish session_ee
    log("\nFinishing session_ee...")
    for ex in session_ee["exercises"]:
        resp = patch_exercise(session_ee_id, ex["order"], "done")
        assert_test(resp.status_code == 200, f"Mark exercise {ex['order']} done")
    
    # ========================================================================
    # NEW TEST (ff): COMPAT ACTIONS - action=skip, action=done, action=reset
    # ========================================================================
    log("\n" + "=" * 80)
    log("NEW TEST (ff): COMPAT ACTIONS - action=skip/done/reset with set_logs")
    log("=" * 80)
    
    # Start fresh session
    session_ff = start_session(athlete_token, plan_id, athlete_tg, week=1, day=workout_day, date="2026-01-15")
    session_ff_id = session_ff["id"]
    log(f"Session started: {session_ff_id}")
    
    # Get first exercise
    ex0_ff = session_ff["exercises"][0]
    total_sets_ff = len(ex0_ff["set_logs"])
    
    # Test action=skip
    log("\nTest action=skip...")
    resp = patch_exercise(session_ff_id, 0, "skip")
    assert_test(resp.status_code == 200, "PATCH exercise/0?action=skip returns 200")
    
    s_skip = resp.json()
    ex_skip = s_skip["exercises"][0]
    
    # Verify all set_logs[].skipped == true AND done == false
    for i in range(total_sets_ff):
        assert_test(ex_skip["set_logs"][i]["skipped"] == True, 
                   f"action=skip: set_logs[{i}].skipped == True")
        assert_test(ex_skip["set_logs"][i]["done"] == False, 
                   f"action=skip: set_logs[{i}].done == False")
    
    # Verify status is 'skipped'
    assert_test(ex_skip["status"] == "skipped", "action=skip: exercise.status == 'skipped'")
    
    # Verify tonnage is 0
    assert_test(ex_skip["tonnage"] == 0, "action=skip: tonnage == 0")
    
    # Test action=done
    log("\nTest action=done...")
    resp = patch_exercise(session_ff_id, 0, "done")
    assert_test(resp.status_code == 200, "PATCH exercise/0?action=done returns 200")
    
    s_done = resp.json()
    ex_done = s_done["exercises"][0]
    
    # Verify all set_logs[].done == true AND skipped == false
    for i in range(total_sets_ff):
        assert_test(ex_done["set_logs"][i]["done"] == True, 
                   f"action=done: set_logs[{i}].done == True")
        assert_test(ex_done["set_logs"][i]["skipped"] == False, 
                   f"action=done: set_logs[{i}].skipped == False")
    
    # Verify status is 'done'
    assert_test(ex_done["status"] == "done", "action=done: exercise.status == 'done'")
    
    # Test action=reset
    log("\nTest action=reset...")
    resp = patch_exercise(session_ff_id, 0, "reset")
    assert_test(resp.status_code == 200, "PATCH exercise/0?action=reset returns 200")
    
    s_reset = resp.json()
    ex_reset = s_reset["exercises"][0]
    
    # Verify all set_logs[].done == false AND skipped == false
    for i in range(total_sets_ff):
        assert_test(ex_reset["set_logs"][i]["done"] == False, 
                   f"action=reset: set_logs[{i}].done == False")
        assert_test(ex_reset["set_logs"][i]["skipped"] == False, 
                   f"action=reset: set_logs[{i}].skipped == False")
    
    # Verify status is 'pending'
    assert_test(ex_reset["status"] == "pending", "action=reset: exercise.status == 'pending'")
    
    # Finish session_ff
    log("\nFinishing session_ff...")
    for ex in session_ff["exercises"]:
        resp = patch_exercise(session_ff_id, ex["order"], "done")
        assert_test(resp.status_code == 200, f"Mark exercise {ex['order']} done")
    
    # ========================================================================
    # RE-VERIFY ORIGINAL DONE-PATH SCENARIOS
    # ========================================================================
    log("\n" + "=" * 80)
    log("RE-VERIFY ORIGINAL DONE-PATH SCENARIOS")
    log("=" * 80)
    
    # Start fresh session for original tests
    session_orig = start_session(athlete_token, plan_id, athlete_tg, week=1, day=workout_day, date="2026-01-16")
    session_orig_id = session_orig["id"]
    log(f"Session started: {session_orig_id}")
    
    # (a) STRUCTURE
    log("\n(a) STRUCTURE - verify set_logs structure")
    exercises = session_orig.get("exercises", [])
    first_ex = exercises[0]
    set_logs = first_ex.get("set_logs", [])
    sets_scheme = first_ex.get("sets_scheme", [])
    expected_sets = sum(s.get("sets", 0) for s in sets_scheme)
    
    assert_test(len(set_logs) == expected_sets, 
               f"(a) set_logs length ({len(set_logs)}) matches sum of target_sets ({expected_sets})")
    assert_test("rest_seconds" in first_ex, "(a) rest_seconds field present")
    
    # Verify accessory exercises have empty set_logs
    accessory_ex = next((e for e in exercises if e.get("is_accessory")), None)
    if accessory_ex:
        assert_test(len(accessory_ex.get("set_logs", [])) == 0, 
                   "(a) Accessory exercise has empty set_logs")
    
    # (b) LOG ONE SET WITH ACTUALS
    log("\n(b) LOG ONE SET WITH ACTUALS")
    resp = patch_set(session_orig_id, 0, 0, {"done": True, "weight": 60, "reps": 5})
    assert_test(resp.status_code == 200, "(b) PATCH set/0 with done/weight/reps returns 200")
    
    s_b = resp.json()
    ex_b = s_b["exercises"][0]
    
    assert_test(ex_b.get("edited") == True, "(b) exercise.edited == True")
    assert_test(ex_b["set_logs"][0]["done"] == True, "(b) set_logs[0].done == True")
    assert_test(ex_b["set_logs"][0]["weight"] == 60, "(b) set_logs[0].weight == 60")
    assert_test(ex_b["set_logs"][0]["reps"] == 5, "(b) set_logs[0].reps == 5")
    assert_test(ex_b["tonnage"] == 300, "(b) tonnage == 300 (60*1*5)")
    assert_test(ex_b["status"] == "in_progress", "(b) exercise.status == 'in_progress'")
    
    # (c) COMPLETE EXERCISE VIA SETS
    log("\n(c) COMPLETE EXERCISE VIA SETS")
    total_sets_orig = len(ex_b["set_logs"])
    for i in range(1, total_sets_orig):
        resp = patch_set(session_orig_id, 0, i, {"done": True})
        assert_test(resp.status_code == 200, f"(c) PATCH set/{i} returns 200")
    
    s_c = get_session(session_orig_id)
    ex_c = s_c["exercises"][0]
    
    all_done = all(s["done"] for s in ex_c["set_logs"])
    assert_test(all_done, "(c) All set_logs[].done == True")
    assert_test(ex_c["status"] == "done", "(c) exercise.status == 'done'")
    assert_test(ex_c.get("filled_by") == "athlete", "(c) filled_by == 'athlete'")
    
    # Verify next exercise became 'in_progress'
    if len(s_c["exercises"]) > 1:
        next_ex = s_c["exercises"][1]
        assert_test(next_ex["status"] == "in_progress", 
                   "(c) Next exercise status == 'in_progress'")
    
    # (d) UNDO A SET
    log("\n(d) UNDO A SET")
    resp = patch_set(session_orig_id, 0, 0, {"done": False})
    assert_test(resp.status_code == 200, "(d) PATCH set/0 done:false returns 200")
    
    s_d = resp.json()
    ex_d = s_d["exercises"][0]
    
    assert_test(ex_d["set_logs"][0]["done"] == False, "(d) set_logs[0].done == False")
    assert_test(ex_d["status"] == "in_progress", "(d) exercise.status == 'in_progress'")
    assert_test(s_d["status"] != "finished", "(d) session.status != 'finished'")
    
    # Re-mark for next tests
    resp = patch_set(session_orig_id, 0, 0, {"done": True})
    assert_test(resp.status_code == 200, "(d) Re-mark set/0 as done")
    
    # (f) AUTO-FINISH
    log("\n(f) AUTO-FINISH")
    # Mark all remaining exercises done
    for ex in exercises:
        if ex["order"] != 0:
            resp = patch_exercise(session_orig_id, ex["order"], "done")
            assert_test(resp.status_code == 200, f"(f) Mark exercise {ex['order']} done")
    
    s_f = get_session(session_orig_id)
    assert_test(s_f["status"] == "finished", "(f) session.status == 'finished'")
    
    stats = s_f.get("stats")
    assert_test(stats is not None, "(f) session.stats is not null")
    assert_test(stats.get("progress_pct") == 100, "(f) stats.progress_pct == 100")
    
    # (g) NEGATIVES
    log("\n(g) NEGATIVES")
    resp = patch_set(session_orig_id, 0, 999, {"done": True})
    assert_test(resp.status_code == 404, "(g) set_index=999 returns 404")
    
    resp = patch_set("non-existent-session-id-12345", 0, 0, {"done": True})
    assert_test(resp.status_code == 404, "(g) Unknown session returns 404")
    
    # ========================================================================
    # GENERAL ASSERTIONS
    # ========================================================================
    log("\n" + "=" * 80)
    log("GENERAL ASSERTIONS - UUIDs, ISO datetimes, no _id leaks")
    log("=" * 80)
    
    test_session = get_session(session_orig_id)
    
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
    log("✅✅✅ ALL PHASE 1 PER-SET LOGGING WITH SKIP TESTS PASSED ✅✅✅")
    log("=" * 80)
    log(f"\nTest Summary:")
    log(f"  Athlete: {athlete_email} (telegram_id={athlete_tg})")
    log(f"  Coach: {coach_email} (telegram_id={coach_tg})")
    log(f"  Plan: {plan_id}")
    log(f"  Template: {template['name']}")
    log(f"\nAll scenarios verified:")
    log(f"  NEW SKIP SCENARIOS:")
    log(f"    (aa) ✅ SKIP ONE SET: skipped=true, done=false, status='in_progress'")
    log(f"    (bb) ✅ MIX SKIP AND DONE: 1 skipped + rest done -> status='done'")
    log(f"    (cc) ✅ SKIP ALL SETS: all skipped -> status='skipped', tonnage=0")
    log(f"    (dd) ✅ EXCLUSIVITY: done and skipped are mutually exclusive")
    log(f"    (ee) ✅ COACH CO-SCRIBE WITH SKIP: coach can skip, unlinked 403, no 'by' 400")
    log(f"    (ff) ✅ COMPAT ACTIONS: action=skip/done/reset work with set_logs")
    log(f"  ORIGINAL DONE-PATH SCENARIOS:")
    log(f"    (a) ✅ STRUCTURE: set_logs length and structure correct")
    log(f"    (b) ✅ LOG ONE SET: PATCH with done/weight/reps works")
    log(f"    (c) ✅ COMPLETE EXERCISE: marking all sets done completes exercise")
    log(f"    (d) ✅ UNDO SET: done:false reverts status")
    log(f"    (f) ✅ AUTO-FINISH: all exercises done -> session finished with stats")
    log(f"    (g) ✅ NEGATIVES: out of range 404, unknown session 404")
    log(f"  GENERAL:")
    log(f"    ✅ UUIDs, ISO datetimes, no _id/password_hash leaks")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ TEST FAILED WITH EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
