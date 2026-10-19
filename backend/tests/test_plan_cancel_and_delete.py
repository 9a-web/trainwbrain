"""
Iter8 bugs 1 & 2 — backend tests:
  Bug 1: DELETE /api/programs/templates/{id} deactivates active/draft plans
         referencing that template. Response must include `plans_cancelled: N`.
  Bug 2: POST /api/plans/{plan_id}/cancel — sets status='completed',
         keeps sessions untouched, 403 if not owner, 404 if missing.
"""
import os
import uuid
import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

OWNER_EMAIL = "statsdemo@twb.dev"
OWNER_PW = "password123"
OWNER_TG = 961727460933

OTHER_EMAIL = "dbg1783466020@ex.com"
OTHER_PW = "password123"
OTHER_TG = 922324126010


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def owner_token():
    return _login(OWNER_EMAIL, OWNER_PW)


@pytest.fixture(scope="module")
def other_token():
    return _login(OTHER_EMAIL, OTHER_PW)


def _make_template(tok, name_suffix=""):
    payload = {
        "name": f"TEST_iter8_{uuid.uuid4().hex[:6]}{name_suffix}",
        "description": "iter8 test",
        "level": "beginner",
        "goal": "strength",
        "weeks": [
            {"week_index": 1, "days": [
                {"day_index": 1, "title": "D1", "exercises": [
                    {"exercise_name": "Присед", "lift_group": "squat",
                     "target_sets": 3, "target_reps": "5",
                     "sets_scheme": [{"weight": 100, "sets": 3, "reps": 5}]},
                ]}
            ]}
        ],
    }
    r = requests.post(f"{BASE_URL}/api/programs/templates",
                      json=payload, headers=_h(tok), timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    return r.json()


def _make_plan(tok, template_id, athlete_tg, name):
    r = requests.post(
        f"{BASE_URL}/api/plans",
        json={"athlete_telegram_id": athlete_tg, "template_id": template_id, "name": name},
        headers=_h(tok), timeout=15,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    return r.json()


# =============================================================
# Bug 1 — DELETE template must cascade-cancel active plans
# =============================================================

def test_delete_template_cancels_own_active_plan(other_token):
    """Use 'other' user so we don't touch statsdemo's active plan."""
    tpl = _make_template(other_token, "_bug1")
    tid = tpl["id"]

    # Create a plan referencing this template
    plan = _make_plan(other_token, tid, OTHER_TG, "TEST_iter8 bug1 plan")
    pid = plan["id"]
    assert plan.get("status") == "active"

    # Delete the template
    r = requests.delete(f"{BASE_URL}/api/programs/templates/{tid}",
                        headers=_h(other_token), timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    data = r.json()
    assert data.get("deleted") == 1
    assert data.get("plans_cancelled") == 1, f"expected 1 plan cancelled, got {data}"

    # Verify plan is now 'completed'
    g = requests.get(f"{BASE_URL}/api/plans/{pid}", headers=_h(other_token), timeout=15)
    assert g.status_code == 200
    assert g.json().get("status") == "completed"

    # Active plan endpoint must now return null
    a = requests.get(f"{BASE_URL}/api/plans/active/{OTHER_TG}",
                     headers=_h(other_token), timeout=15)
    assert a.status_code == 200
    # active plan may be null OR different plan; must NOT equal deleted one
    body = a.json()
    if body is not None:
        assert body.get("id") != pid, "cancelled plan must not be returned as active"

    # cleanup: delete the plan
    requests.delete(f"{BASE_URL}/api/plans/{pid}", headers=_h(other_token), timeout=15)


def test_delete_template_no_plans_returns_zero(other_token):
    tpl = _make_template(other_token, "_noplans")
    tid = tpl["id"]
    r = requests.delete(f"{BASE_URL}/api/programs/templates/{tid}",
                        headers=_h(other_token), timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("deleted") == 1
    assert data.get("plans_cancelled") == 0


# =============================================================
# Bug 2 — POST /plans/{plan_id}/cancel
# =============================================================

def test_cancel_plan_own(other_token):
    tpl = _make_template(other_token, "_bug2")
    plan = _make_plan(other_token, tpl["id"], OTHER_TG, "TEST_iter8 bug2 plan")
    pid = plan["id"]

    r = requests.post(f"{BASE_URL}/api/plans/{pid}/cancel",
                      headers=_h(other_token), timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    data = r.json()
    assert data.get("cancelled") is True
    assert data.get("status") == "completed"

    # Verify persisted
    g = requests.get(f"{BASE_URL}/api/plans/{pid}", headers=_h(other_token), timeout=15)
    assert g.status_code == 200
    assert g.json().get("status") == "completed"

    # active plan endpoint returns null (or another plan, not this one)
    a = requests.get(f"{BASE_URL}/api/plans/active/{OTHER_TG}",
                     headers=_h(other_token), timeout=15)
    assert a.status_code == 200
    body = a.json()
    if body is not None:
        assert body.get("id") != pid

    # Second cancel: already completed → cancelled:false, no error
    r2 = requests.post(f"{BASE_URL}/api/plans/{pid}/cancel",
                       headers=_h(other_token), timeout=15)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("cancelled") is False
    assert d2.get("status") == "completed"

    # Cleanup
    requests.delete(f"{BASE_URL}/api/programs/templates/{tpl['id']}",
                    headers=_h(other_token), timeout=15)
    requests.delete(f"{BASE_URL}/api/plans/{pid}", headers=_h(other_token), timeout=15)


def test_cancel_plan_403_not_owner(owner_token, other_token):
    # Create plan on other user
    tpl = _make_template(other_token, "_bug2_403")
    plan = _make_plan(other_token, tpl["id"], OTHER_TG, "TEST_iter8 bug2 403 plan")
    pid = plan["id"]

    # Owner (different user) tries to cancel — should get 403
    r = requests.post(f"{BASE_URL}/api/plans/{pid}/cancel",
                      headers=_h(owner_token), timeout=15)
    assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    # cleanup
    requests.delete(f"{BASE_URL}/api/programs/templates/{tpl['id']}",
                    headers=_h(other_token), timeout=15)
    requests.delete(f"{BASE_URL}/api/plans/{pid}",
                    headers=_h(other_token), timeout=15)


def test_cancel_plan_404_unknown(owner_token):
    r = requests.post(f"{BASE_URL}/api/plans/{uuid.uuid4()}/cancel",
                      headers=_h(owner_token), timeout=15)
    assert r.status_code == 404


def test_cancel_plan_requires_auth():
    r = requests.post(f"{BASE_URL}/api/plans/{uuid.uuid4()}/cancel", timeout=15)
    assert r.status_code == 401


def test_cancel_preserves_sessions(other_token):
    """After cancel, existing sessions for the plan must remain in DB."""
    tpl = _make_template(other_token, "_sess")
    plan = _make_plan(other_token, tpl["id"], OTHER_TG, "TEST_iter8 sess plan")
    pid = plan["id"]

    # Start a session on any workout day the plan has (week 1, day 1)
    s = requests.post(
        f"{BASE_URL}/api/sessions/start",
        json={"plan_id": pid, "athlete_telegram_id": OTHER_TG,
              "week": 1, "day": 1},
        headers=_h(other_token), timeout=15,
    )
    session_id = None
    if s.status_code == 200:
        session_id = s.json().get("id")

    # Cancel plan
    r = requests.post(f"{BASE_URL}/api/plans/{pid}/cancel",
                      headers=_h(other_token), timeout=15)
    assert r.status_code == 200
    assert r.json().get("cancelled") is True

    # If we created a session, verify it still exists
    if session_id:
        g = requests.get(f"{BASE_URL}/api/sessions/{session_id}",
                         headers=_h(other_token), timeout=15)
        assert g.status_code == 200, "session must remain after plan cancel"
        assert g.json().get("plan_id") == pid

    # cleanup
    requests.delete(f"{BASE_URL}/api/programs/templates/{tpl['id']}",
                    headers=_h(other_token), timeout=15)
    requests.delete(f"{BASE_URL}/api/plans/{pid}",
                    headers=_h(other_token), timeout=15)
