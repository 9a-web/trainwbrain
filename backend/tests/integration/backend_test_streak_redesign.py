"""
Test suite for Streak Redesign (GET /api/stats/{tg}/streak)
Tests new fields: streaks, this_month, avg_per_week, first_workout_date
Tests calendar day annotations: streak_len, streak_start, streak_end
Tests auth and empty user case
"""
import requests
import os
from datetime import datetime, timezone

# Use the backend URL from frontend/.env
BACKEND_URL = "https://fc46ec61-14a3-445d-bd01-eba40c2bef2d.preview.emergentagent.com/api"

# Demo account credentials (from test_credentials.md)
DEMO_EMAIL = "streakdemo@twb.dev"
DEMO_PASSWORD = "password123"
DEMO_TELEGRAM_ID = 992689326272

def test_streak_redesign():
    print("\n" + "="*80)
    print("STREAK REDESIGN TEST SUITE")
    print("="*80)
    
    # ========================================================================
    # STEP 1: Login with demo account
    # ========================================================================
    print("\n[STEP 1] Login with demo account...")
    login_resp = requests.post(
        f"{BACKEND_URL}/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.status_code} {login_resp.text}"
    login_data = login_resp.json()
    token = login_data["token"]
    user = login_data["user"]
    assert user["telegram_id"] == DEMO_TELEGRAM_ID, f"Expected telegram_id {DEMO_TELEGRAM_ID}, got {user['telegram_id']}"
    print(f"✅ Login successful: telegram_id={user['telegram_id']}")
    
    # ========================================================================
    # STEP 2: GET /api/stats/992689326272/streak?weeks=12 with auth
    # ========================================================================
    print("\n[STEP 2] GET /api/stats/992689326272/streak?weeks=12 with Authorization header...")
    headers = {"Authorization": f"Bearer {token}"}
    streak_resp = requests.get(
        f"{BACKEND_URL}/stats/{DEMO_TELEGRAM_ID}/streak",
        params={"weeks": 12},
        headers=headers
    )
    assert streak_resp.status_code == 200, f"Streak endpoint failed: {streak_resp.status_code} {streak_resp.text}"
    streak_data = streak_resp.json()
    print(f"✅ Streak endpoint returned 200")
    
    # ========================================================================
    # STEP 2a: Verify OLD fields are unchanged
    # ========================================================================
    print("\n[STEP 2a] Verify OLD fields are unchanged...")
    assert "telegram_id" in streak_data, "Missing telegram_id"
    assert streak_data["telegram_id"] == DEMO_TELEGRAM_ID, f"Expected telegram_id {DEMO_TELEGRAM_ID}, got {streak_data['telegram_id']}"
    
    assert "current_streak" in streak_data, "Missing current_streak"
    assert "best_streak" in streak_data, "Missing best_streak"
    assert "total_workouts" in streak_data, "Missing total_workouts"
    assert "active_days" in streak_data, "Missing active_days"
    assert "weekly_goal" in streak_data, "Missing weekly_goal"
    assert "trained_this_week" in streak_data, "Missing trained_this_week"
    assert "week" in streak_data, "Missing week"
    assert "calendar" in streak_data, "Missing calendar"
    
    print(f"  telegram_id: {streak_data['telegram_id']}")
    print(f"  current_streak: {streak_data['current_streak']}")
    print(f"  best_streak: {streak_data['best_streak']}")
    print(f"  total_workouts: {streak_data['total_workouts']}")
    print(f"  active_days: {streak_data['active_days']}")
    print(f"✅ All OLD fields present")
    
    # ========================================================================
    # STEP 2b: Verify expected values from demo data
    # ========================================================================
    print("\n[STEP 2b] Verify expected values from demo data...")
    # Demo has: 5-day series (~4 weeks ago), 3-day series (~2 weeks ago), 
    # current 2-day series (yesterday+today), plus 3 isolated single days
    # Total: 5+3+2+3 = 13 workouts
    
    assert streak_data["current_streak"] == 2, f"Expected current_streak=2, got {streak_data['current_streak']}"
    print(f"✅ current_streak=2 (correct)")
    
    assert streak_data["best_streak"] == 5, f"Expected best_streak=5, got {streak_data['best_streak']}"
    print(f"✅ best_streak=5 (correct)")
    
    assert streak_data["total_workouts"] == 13, f"Expected total_workouts=13, got {streak_data['total_workouts']}"
    print(f"✅ total_workouts=13 (correct)")
    
    assert streak_data["active_days"] == 13, f"Expected active_days=13, got {streak_data['active_days']}"
    print(f"✅ active_days=13 (correct)")
    
    # ========================================================================
    # STEP 2c: Verify NEW field: streaks
    # ========================================================================
    print("\n[STEP 2c] Verify NEW field: streaks...")
    assert "streaks" in streak_data, "Missing NEW field: streaks"
    streaks = streak_data["streaks"]
    assert isinstance(streaks, list), f"streaks should be a list, got {type(streaks)}"
    
    # Should have exactly 3 series (lengths 2, 3, 5)
    assert len(streaks) == 3, f"Expected 3 streaks (>=2 consecutive days), got {len(streaks)}"
    print(f"✅ streaks has 3 items (correct)")
    
    # Verify each streak has required fields
    for i, s in enumerate(streaks):
        assert "start" in s, f"Streak {i} missing 'start'"
        assert "end" in s, f"Streak {i} missing 'end'"
        assert "length" in s, f"Streak {i} missing 'length'"
        assert "is_current" in s, f"Streak {i} missing 'is_current'"
        assert "is_best" in s, f"Streak {i} missing 'is_best'"
        
        # Verify ISO date format
        try:
            datetime.fromisoformat(s["start"])
            datetime.fromisoformat(s["end"])
        except ValueError:
            raise AssertionError(f"Streak {i} has invalid ISO date format")
    
    print(f"✅ All streaks have required fields (start, end, length, is_current, is_best)")
    
    # Verify streaks are sorted recent-first
    lengths = [s["length"] for s in streaks]
    print(f"  Streak lengths (recent-first): {lengths}")
    assert lengths == [2, 3, 5], f"Expected lengths [2, 3, 5] (recent-first), got {lengths}"
    print(f"✅ Streaks sorted recent-first (correct)")
    
    # Verify first streak (length 2) has is_current=true
    assert streaks[0]["is_current"] == True, f"Expected first streak (length 2) to have is_current=true, got {streaks[0]['is_current']}"
    print(f"✅ First streak (length 2) has is_current=true (correct)")
    
    # Verify last streak (length 5) has is_best=true
    assert streaks[2]["is_best"] == True, f"Expected last streak (length 5) to have is_best=true, got {streaks[2]['is_best']}"
    print(f"✅ Last streak (length 5) has is_best=true (correct)")
    
    # Verify only ONE streak has is_best=true
    best_count = sum(1 for s in streaks if s["is_best"])
    assert best_count == 1, f"Expected exactly 1 streak with is_best=true, got {best_count}"
    print(f"✅ Only ONE streak has is_best=true (correct)")
    
    # ========================================================================
    # STEP 2d: Verify NEW metrics: this_month, avg_per_week, first_workout_date
    # ========================================================================
    print("\n[STEP 2d] Verify NEW metrics: this_month, avg_per_week, first_workout_date...")
    
    assert "this_month" in streak_data, "Missing NEW field: this_month"
    assert isinstance(streak_data["this_month"], int), f"this_month should be int, got {type(streak_data['this_month'])}"
    assert streak_data["this_month"] >= 1, f"Expected this_month>=1, got {streak_data['this_month']}"
    print(f"✅ this_month={streak_data['this_month']} (>=1, correct)")
    
    assert "avg_per_week" in streak_data, "Missing NEW field: avg_per_week"
    assert isinstance(streak_data["avg_per_week"], (int, float)), f"avg_per_week should be number, got {type(streak_data['avg_per_week'])}"
    assert streak_data["avg_per_week"] > 0, f"Expected avg_per_week>0, got {streak_data['avg_per_week']}"
    print(f"✅ avg_per_week={streak_data['avg_per_week']} (>0, correct)")
    
    assert "first_workout_date" in streak_data, "Missing NEW field: first_workout_date"
    assert streak_data["first_workout_date"] is not None, "first_workout_date should not be null for demo account"
    # Verify ISO date format
    try:
        datetime.fromisoformat(streak_data["first_workout_date"])
    except ValueError:
        raise AssertionError(f"first_workout_date has invalid ISO date format: {streak_data['first_workout_date']}")
    print(f"✅ first_workout_date={streak_data['first_workout_date']} (ISO date, correct)")
    
    # ========================================================================
    # STEP 3: Verify calendar day annotations
    # ========================================================================
    print("\n[STEP 3] Verify calendar day annotations (streak_len, streak_start, streak_end)...")
    
    calendar = streak_data["calendar"]
    assert isinstance(calendar, list), f"calendar should be a list, got {type(calendar)}"
    assert len(calendar) > 0, "calendar should not be empty"
    
    # Collect all days with trained=true
    trained_days = []
    for week in calendar:
        assert "days" in week, "Week missing 'days'"
        for day in week["days"]:
            if day.get("trained"):
                trained_days.append(day)
    
    print(f"  Found {len(trained_days)} trained days in calendar")
    
    # Verify each trained day has new fields
    for day in trained_days:
        assert "streak_len" in day, f"Trained day {day['date']} missing 'streak_len'"
        assert "streak_start" in day, f"Trained day {day['date']} missing 'streak_start'"
        assert "streak_end" in day, f"Trained day {day['date']} missing 'streak_end'"
        assert isinstance(day["streak_len"], int), f"streak_len should be int, got {type(day['streak_len'])}"
        assert isinstance(day["streak_start"], bool), f"streak_start should be bool, got {type(day['streak_start'])}"
        assert isinstance(day["streak_end"], bool), f"streak_end should be bool, got {type(day['streak_end'])}"
    
    print(f"✅ All trained days have streak_len, streak_start, streak_end fields")
    
    # Find days with streak_len >= 2 (part of a series)
    series_days = [d for d in trained_days if d["streak_len"] >= 2]
    print(f"  Found {len(series_days)} days in series (streak_len>=2)")
    
    # Group by streak_len to find series
    from collections import defaultdict
    series_by_len = defaultdict(list)
    for day in series_days:
        series_by_len[day["streak_len"]].append(day)
    
    print(f"  Series found: {dict(series_by_len)}")
    
    # Verify each series has exactly one streak_start=true and one streak_end=true
    for length, days in series_by_len.items():
        start_count = sum(1 for d in days if d["streak_start"])
        end_count = sum(1 for d in days if d["streak_end"])
        
        # Note: days might be from different series with same length
        # So we need to check that each series has at least one start and one end
        assert start_count >= 1, f"Series with length {length} has no streak_start=true"
        assert end_count >= 1, f"Series with length {length} has no streak_end=true"
    
    print(f"✅ Each series has at least one day with streak_start=true and one with streak_end=true")
    
    # Verify isolated trained days have streak_len=1
    isolated_days = [d for d in trained_days if d["streak_len"] == 1]
    print(f"  Found {len(isolated_days)} isolated trained days (streak_len=1)")
    assert len(isolated_days) == 3, f"Expected 3 isolated days, got {len(isolated_days)}"
    print(f"✅ Isolated trained days have streak_len=1 (correct)")
    
    # ========================================================================
    # STEP 4: Verify weeks param clamp
    # ========================================================================
    print("\n[STEP 4] Verify weeks param clamp...")
    
    # weeks=1 -> calendar length 1
    resp1 = requests.get(
        f"{BACKEND_URL}/stats/{DEMO_TELEGRAM_ID}/streak",
        params={"weeks": 1},
        headers=headers
    )
    assert resp1.status_code == 200, f"weeks=1 failed: {resp1.status_code}"
    data1 = resp1.json()
    assert len(data1["calendar"]) == 1, f"Expected calendar length 1 for weeks=1, got {len(data1['calendar'])}"
    print(f"✅ weeks=1 -> calendar length 1 (correct)")
    
    # weeks=100 -> calendar length 26 (clamped)
    resp100 = requests.get(
        f"{BACKEND_URL}/stats/{DEMO_TELEGRAM_ID}/streak",
        params={"weeks": 100},
        headers=headers
    )
    assert resp100.status_code == 200, f"weeks=100 failed: {resp100.status_code}"
    data100 = resp100.json()
    assert len(data100["calendar"]) == 26, f"Expected calendar length 26 for weeks=100, got {len(data100['calendar'])}"
    print(f"✅ weeks=100 -> calendar length 26 (clamped, correct)")
    
    # weeks=26 -> calendar length 26
    resp26 = requests.get(
        f"{BACKEND_URL}/stats/{DEMO_TELEGRAM_ID}/streak",
        params={"weeks": 26},
        headers=headers
    )
    assert resp26.status_code == 200, f"weeks=26 failed: {resp26.status_code}"
    data26 = resp26.json()
    assert len(data26["calendar"]) == 26, f"Expected calendar length 26 for weeks=26, got {len(data26['calendar'])}"
    print(f"✅ weeks=26 -> calendar length 26 (correct)")
    
    # ========================================================================
    # STEP 5: Auth tests
    # ========================================================================
    print("\n[STEP 5] Auth tests...")
    
    # 5a: NO Authorization header -> 401 or 403
    print("\n[STEP 5a] GET /api/stats/992689326272/streak WITHOUT Authorization header...")
    no_auth_resp = requests.get(
        f"{BACKEND_URL}/stats/{DEMO_TELEGRAM_ID}/streak",
        params={"weeks": 12}
    )
    assert no_auth_resp.status_code in [401, 403], f"Expected 401 or 403 without auth, got {no_auth_resp.status_code}"
    print(f"✅ Without Authorization header -> {no_auth_resp.status_code} (correct)")
    
    # 5b: Register a fresh throwaway user
    print("\n[STEP 5b] Register a fresh throwaway user...")
    import random
    throwaway_email = f"throwaway_{random.randint(1000000000, 9999999999)}@example.com"
    throwaway_password = "password123"
    
    register_resp = requests.post(
        f"{BACKEND_URL}/auth/register",
        json={"email": throwaway_email, "password": throwaway_password, "name": "Throwaway User"}
    )
    assert register_resp.status_code == 200, f"Register failed: {register_resp.status_code} {register_resp.text}"
    register_data = register_resp.json()
    throwaway_token = register_data["token"]
    throwaway_tg = register_data["user"]["telegram_id"]
    print(f"✅ Registered throwaway user: telegram_id={throwaway_tg}")
    
    # 5c: Throwaway user tries to access demo user's streak -> 403
    print("\n[STEP 5c] Throwaway user tries to access demo user's streak...")
    throwaway_headers = {"Authorization": f"Bearer {throwaway_token}"}
    stranger_resp = requests.get(
        f"{BACKEND_URL}/stats/{DEMO_TELEGRAM_ID}/streak",
        params={"weeks": 12},
        headers=throwaway_headers
    )
    assert stranger_resp.status_code == 403, f"Expected 403 for stranger access, got {stranger_resp.status_code}"
    print(f"✅ Stranger access -> 403 (correct)")
    
    # ========================================================================
    # STEP 6: Empty user case
    # ========================================================================
    print("\n[STEP 6] Empty user case (freshly registered user with no workouts)...")
    
    empty_resp = requests.get(
        f"{BACKEND_URL}/stats/{throwaway_tg}/streak",
        params={"weeks": 12},
        headers=throwaway_headers
    )
    assert empty_resp.status_code == 200, f"Empty user streak failed: {empty_resp.status_code} {empty_resp.text}"
    empty_data = empty_resp.json()
    
    assert empty_data["current_streak"] == 0, f"Expected current_streak=0 for empty user, got {empty_data['current_streak']}"
    assert empty_data["best_streak"] == 0, f"Expected best_streak=0 for empty user, got {empty_data['best_streak']}"
    assert empty_data["streaks"] == [], f"Expected streaks=[] for empty user, got {empty_data['streaks']}"
    assert empty_data["this_month"] == 0, f"Expected this_month=0 for empty user, got {empty_data['this_month']}"
    assert empty_data["avg_per_week"] == 0, f"Expected avg_per_week=0 for empty user, got {empty_data['avg_per_week']}"
    assert empty_data["first_workout_date"] is None, f"Expected first_workout_date=null for empty user, got {empty_data['first_workout_date']}"
    
    print(f"✅ Empty user: current_streak=0, best_streak=0, streaks=[], this_month=0, avg_per_week=0, first_workout_date=null (correct)")
    
    # ========================================================================
    # GENERAL ASSERTIONS
    # ========================================================================
    print("\n[GENERAL ASSERTIONS]")
    
    # Verify all IDs are UUID strings (36 chars)
    # (No IDs in streak response, skip)
    
    # Verify all datetimes are ISO strings
    for s in streaks:
        assert "T" in s["start"] or "-" in s["start"], f"start should be ISO date: {s['start']}"
        assert "T" in s["end"] or "-" in s["end"], f"end should be ISO date: {s['end']}"
    
    if streak_data["first_workout_date"]:
        assert "T" in streak_data["first_workout_date"] or "-" in streak_data["first_workout_date"], \
            f"first_workout_date should be ISO date: {streak_data['first_workout_date']}"
    
    print(f"✅ All datetimes are ISO strings")
    
    # Verify no MongoDB _id leaks
    def check_no_id_leaks(obj, path=""):
        if isinstance(obj, dict):
            assert "_id" not in obj, f"MongoDB _id leak at {path}"
            for k, v in obj.items():
                check_no_id_leaks(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                check_no_id_leaks(item, f"{path}[{i}]")
    
    check_no_id_leaks(streak_data, "streak_data")
    print(f"✅ No MongoDB _id leaks")
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n" + "="*80)
    print("✅✅✅ ALL STREAK REDESIGN TESTS PASSED")
    print("="*80)
    print("\nSUMMARY:")
    print("  ✅ Login with demo account successful")
    print("  ✅ GET /api/stats/992689326272/streak?weeks=12 returns 200")
    print("  ✅ OLD fields unchanged: telegram_id, current_streak, best_streak, total_workouts, active_days, weekly_goal, trained_this_week, week, calendar")
    print("  ✅ Expected values: current_streak=2, best_streak=5, total_workouts=13, active_days=13")
    print("  ✅ NEW field 'streaks': 3 items with lengths [2, 3, 5] (recent-first)")
    print("  ✅ First streak (length 2) has is_current=true")
    print("  ✅ Last streak (length 5) has is_best=true")
    print("  ✅ Only ONE streak has is_best=true")
    print("  ✅ NEW metrics: this_month>=1, avg_per_week>0, first_workout_date is ISO date")
    print("  ✅ Calendar day annotations: all trained days have streak_len, streak_start, streak_end")
    print("  ✅ Series days (streak_len>=2) have correct start/end markers")
    print("  ✅ Isolated days have streak_len=1")
    print("  ✅ weeks param clamp: weeks=1->1, weeks=100->26, weeks=26->26")
    print("  ✅ Auth: no token->401/403, stranger token->403")
    print("  ✅ Empty user: current_streak=0, best_streak=0, streaks=[], this_month=0, avg_per_week=0, first_workout_date=null")
    print("  ✅ All datetimes are ISO strings")
    print("  ✅ No MongoDB _id leaks")
    print("\n" + "="*80)


if __name__ == "__main__":
    try:
        test_streak_redesign()
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        raise
