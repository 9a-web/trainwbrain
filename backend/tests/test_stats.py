"""
TrainWithBrain — Stats module regression tests (B1..B11 + regression).
Tests authorization (IDOR), 1RM Epley, scope handling, streak fields,
consistency between /stats/{tg} and /streak, home widget access.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env parse (not overriding but ensuring tests run)
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

OWNER_EMAIL = "statsdemo@twb.dev"
OWNER_PW = "password123"
OWNER_TG = 961727460933
OWNER_PLAN_ID = "32a9362c-a8c5-4dd0-89ba-6d9717d0feef"

OTHER_EMAIL = "dbg1783466020@ex.com"
OTHER_PW = "password123"
OTHER_TG = 922324126010


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_token():
    return _login(OWNER_EMAIL, OWNER_PW)


@pytest.fixture(scope="module")
def other_token():
    return _login(OTHER_EMAIL, OTHER_PW)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ==================== B1 — IDOR / Auth on /stats/* ====================

STATS_PATHS = [
    f"/api/stats/{OWNER_TG}",
    f"/api/stats/{OWNER_TG}/detailed",
    f"/api/stats/{OWNER_TG}/exercise-progress",
    f"/api/stats/{OWNER_TG}/streak",
]


@pytest.mark.parametrize("path", STATS_PATHS)
def test_b1_stats_requires_auth_401(path):
    r = requests.get(f"{BASE_URL}{path}", timeout=15)
    assert r.status_code == 401, f"{path} expected 401, got {r.status_code} {r.text[:120]}"


@pytest.mark.parametrize("path", STATS_PATHS)
def test_b1_stats_forbids_other_user_403(path, other_token):
    r = requests.get(f"{BASE_URL}{path}", headers=_h(other_token), timeout=15)
    assert r.status_code == 403, f"{path} expected 403 for stranger, got {r.status_code} {r.text[:120]}"


@pytest.mark.parametrize("path", STATS_PATHS)
def test_b1_stats_owner_ok_200(path, owner_token):
    r = requests.get(f"{BASE_URL}{path}", headers=_h(owner_token), timeout=20)
    assert r.status_code == 200, f"{path} expected 200 for owner, got {r.status_code} {r.text[:200]}"


# ==================== B1 — Coach-gated routes ====================

def test_b1_coach_stats_requires_auth():
    # any coach_id / athlete_id — should be 401 without token
    url = f"{BASE_URL}/api/coach/{OTHER_TG}/clients/{OWNER_TG}/stats"
    r = requests.get(url, timeout=15)
    assert r.status_code == 401, f"expected 401, got {r.status_code}"


def test_b1_coach_stats_forbids_wrong_caller(other_token):
    # other_token belongs to OTHER_TG. Passing OWNER_TG as coach_id must be 403.
    url = f"{BASE_URL}/api/coach/{OWNER_TG}/clients/{OWNER_TG}/stats"
    r = requests.get(url, headers=_h(other_token), timeout=15)
    assert r.status_code == 403, f"expected 403 when caller != coach_id, got {r.status_code} {r.text[:200]}"


def test_b1_coach_exercise_progress_forbids_wrong_caller(other_token):
    # Actual route: /api/coach/{coach_id}/clients/{athlete_id}/exercise-progress
    url = f"{BASE_URL}/api/coach/{OWNER_TG}/clients/{OWNER_TG}/exercise-progress"
    r = requests.get(url, headers=_h(other_token), timeout=15)
    assert r.status_code == 403, f"expected 403, got {r.status_code}"


# ==================== B3 — Epley 1RM in /detailed ====================

def test_b3_detailed_epley_1rm(owner_token):
    r = requests.get(
        f"{BASE_URL}/api/stats/{OWNER_TG}/detailed",
        params={"plan_id": OWNER_PLAN_ID},
        headers=_h(owner_token),
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    orm = data.get("one_rep_max_est", [])
    assert isinstance(orm, list) and len(orm) > 0, "one_rep_max_est must be non-empty"
    # Ensure achieved differs from planned for at least one exercise
    diffs = [abs((x.get("achieved") or 0) - (x.get("planned") or 0)) for x in orm]
    assert max(diffs) > 0.1, f"achieved should differ from planned by Epley formula: {orm}"
    # Squat: planned ~200, achieved ~197.3 per spec
    squat = next((x for x in orm if "присед" in (x.get("exercise") or x.get("name") or "").lower()
                  or "squat" in (x.get("exercise") or x.get("name") or "").lower()), None)
    if squat:
        assert squat.get("planned") and abs(squat["planned"] - 200) < 5, f"squat planned ~200: {squat}"
        assert squat.get("achieved") and 190 <= squat["achieved"] <= 205, f"squat achieved ~197: {squat}"


# ==================== B4 — Scope all vs plan for exercise-progress ====================

def test_b4_exercise_progress_scope_all(owner_token):
    r = requests.get(
        f"{BASE_URL}/api/stats/{OWNER_TG}/exercise-progress",
        headers=_h(owner_token),
        timeout=20,
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("scope") == "all", f"scope must be 'all' without plan_id, got {data.get('scope')}"
    series = data.get("series") or []
    if series:
        lbl = series[0].get("label", "")
        # dd.mm date-format check (e.g. 22.06)
        parts = lbl.split(".")
        assert len(parts) == 2 and all(p.isdigit() for p in parts), f"label should be dd.mm, got {lbl!r}"


def test_b4_exercise_progress_scope_plan(owner_token):
    r = requests.get(
        f"{BASE_URL}/api/stats/{OWNER_TG}/exercise-progress",
        params={"plan_id": OWNER_PLAN_ID},
        headers=_h(owner_token),
        timeout=20,
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("scope") == "plan", f"scope must be 'plan' with plan_id, got {data.get('scope')}"
    series = data.get("series") or []
    if series:
        lbl = series[0].get("label", "")
        assert "Нед" in lbl or "нед" in lbl.lower(), f"plan scope label should be 'Нед N', got {lbl!r}"


# ==================== B5 — Only weighted exercises listed ====================

def test_b5_exercise_progress_only_weighted(owner_token):
    r = requests.get(
        f"{BASE_URL}/api/stats/{OWNER_TG}/exercise-progress",
        headers=_h(owner_token),
        timeout=20,
    )
    assert r.status_code == 200
    data = r.json()
    exs = data.get("exercises") or []
    assert len(exs) > 0, "expected some weighted exercises for demo user"
    # exercises must be pre-filtered by backend to weighted ones — no bodyweight/accessory 0-weight items
    # top-level series (for default exercise) must have weighted points
    series = data.get("series") or []
    assert len(series) > 0, "top-level series must be non-empty for default weighted exercise"
    for s in series:
        w = s.get("top_weight") or s.get("weight") or 0
        assert w > 0, f"series point has zero weight: {s}"


# ==================== B6/B7 — clamps and avg_per_week per microcycle ====================

def test_b6_b7_detailed_clamps_and_avg_per_week(owner_token):
    r = requests.get(
        f"{BASE_URL}/api/stats/{OWNER_TG}/detailed",
        params={"plan_id": OWNER_PLAN_ID},
        headers=_h(owner_token),
        timeout=20,
    )
    assert r.status_code == 200
    data = r.json()
    summary = data.get("summary") or {}
    completion_pct = summary.get("completion_pct")
    assert completion_pct is None or 0 <= completion_pct <= 100, f"completion_pct out of bounds: {completion_pct}"
    adherence = data.get("adherence") or {}
    vol_pct = adherence.get("volume_pct")
    assert vol_pct is None or 0 <= vol_pct <= 100, f"volume_pct out of bounds: {vol_pct}"
    apw = summary.get("avg_per_week")
    # 9 sessions / 3 weeks == 3.0
    assert apw is not None, "avg_per_week must be present"
    assert 2.0 <= apw <= 4.5, f"avg_per_week for microcycle must be ~3, got {apw}"


# ==================== B11 — /streak fields ====================

def test_b11_streak_fields(owner_token):
    r = requests.get(f"{BASE_URL}/api/stats/{OWNER_TG}/streak", headers=_h(owner_token), timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data.get("total_workouts") == 9, f"expected total_workouts=9, got {data.get('total_workouts')}"
    assert data.get("active_days") == 8, f"expected active_days=8, got {data.get('active_days')}"
    cal = data.get("calendar") or []
    assert isinstance(cal, list) and len(cal) > 0
    # find at least one day cell with count field
    found = False
    for week in cal:
        for day in (week.get("days") or []):
            if "count" in day:
                found = True
                break
        if found:
            break
    assert found, "calendar[].days[] must include 'count' field"


# ==================== B2 — /stats/{tg} short summary consistent with /streak ====================

def test_b2_short_stats_consistent_with_streak(owner_token):
    r1 = requests.get(f"{BASE_URL}/api/stats/{OWNER_TG}", headers=_h(owner_token), timeout=20)
    r2 = requests.get(f"{BASE_URL}/api/stats/{OWNER_TG}/streak", headers=_h(owner_token), timeout=20)
    assert r1.status_code == 200 and r2.status_code == 200
    a = r1.json()
    b = r2.json()
    # required fields
    for k in ("streak_days", "total_workouts", "active_days"):
        assert k in a, f"missing {k} in /stats short response: keys={list(a.keys())}"
    assert a["total_workouts"] == b.get("total_workouts"), f"total_workouts mismatch: {a['total_workouts']} vs {b.get('total_workouts')}"
    assert a["active_days"] == b.get("active_days"), f"active_days mismatch: {a['active_days']} vs {b.get('active_days')}"
    # streak_days should match current_streak from /streak
    cs = b.get("current_streak", b.get("streak_days"))
    assert a["streak_days"] == cs, f"streak_days mismatch: {a['streak_days']} vs {cs}"


# ==================== Regression: Home widget uses /stats/{tg} — auth works ====================

def test_regression_home_widget_short_stats(owner_token):
    r = requests.get(f"{BASE_URL}/api/stats/{OWNER_TG}", headers=_h(owner_token), timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("total_workouts") == 9
