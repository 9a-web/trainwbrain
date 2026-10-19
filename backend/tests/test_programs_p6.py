"""
TrainWithBrain — P6 «Импорт своих программ» tests.
Covers: templates CRUD + auth (401/403), share (stable code), public shared preview,
import (own/dup/404), AI status/generate/parse disabled state (503/400/401),
regression: plan creation from own template.
"""
import os
import re
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

DEMO_TEMPLATE_ID = "b85dbff0-ef78-48f6-805d-2a6417e912df"
DEMO_SHARE_CODE = "TWB-ZZB5ZS"


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


# ==================== Templates: auth / list / mine ====================

def test_templates_requires_auth_401():
    r = requests.get(f"{BASE_URL}/api/programs/templates", timeout=15)
    assert r.status_code == 401, f"expected 401, got {r.status_code} {r.text[:120]}"


def test_templates_list_returns_builtins_and_own(owner_token):
    r = requests.get(f"{BASE_URL}/api/programs/templates", headers=_h(owner_token), timeout=15)
    assert r.status_code == 200
    tpls = r.json()
    assert isinstance(tpls, list) and len(tpls) > 0
    builtins = [t for t in tpls if t.get("is_builtin")]
    mine = [t for t in tpls if not t.get("is_builtin") and t.get("owner_telegram_id") == OWNER_TG]
    assert len(builtins) >= 4, f"expected >=4 builtin templates, got {len(builtins)}"
    assert any(t.get("id") == DEMO_TEMPLATE_ID for t in mine), \
        f"demo owner template {DEMO_TEMPLATE_ID} not found in owner's templates"


# ==================== Templates: CRUD + 403 ====================

@pytest.fixture(scope="function")
def created_template(owner_token):
    """Create fresh template for the owner; cleanup at end."""
    payload = {
        "name": f"TEST_p6 tpl {uuid.uuid4().hex[:6]}",
        "description": "auto",
        "level": "beginner",
        "goal": "strength",
        "weeks": [
            {"week_index": 1, "days": [
                {"day_index": 1, "title": "День 1", "exercises": [
                    {"exercise_name": "Присед", "lift_group": "squat",
                     "target_sets": 3, "target_reps": "5",
                     "sets_scheme": [{"weight": 100, "sets": 3, "reps": 5}]}
                ]}
            ]}
        ],
    }
    r = requests.post(f"{BASE_URL}/api/programs/templates",
                      json=payload, headers=_h(owner_token), timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    doc = r.json()
    yield doc
    # teardown
    requests.delete(f"{BASE_URL}/api/programs/templates/{doc['id']}",
                    headers=_h(owner_token), timeout=15)


def test_create_template_source_constructor(created_template):
    assert created_template["source"] == "constructor"
    assert created_template["owner_telegram_id"] == OWNER_TG
    assert created_template["is_builtin"] is False
    assert created_template["weeks_count"] == 1
    assert created_template["days_per_week"] == 1


def test_patch_own_template_recounts(owner_token, created_template):
    tid = created_template["id"]
    weeks = [
        {"week_index": 1, "days": [
            {"day_index": 1, "title": "D1", "exercises": []},
            {"day_index": 3, "title": "D3", "exercises": []},
        ]},
        {"week_index": 2, "days": [
            {"day_index": 1, "title": "D1", "exercises": []},
        ]},
    ]
    r = requests.patch(f"{BASE_URL}/api/programs/templates/{tid}",
                       json={"name": "TEST_p6 renamed", "weeks": weeks},
                       headers=_h(owner_token), timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    d = r.json()
    assert d["name"] == "TEST_p6 renamed"
    assert d["weeks_count"] == 2
    assert d["days_per_week"] == 2

    # GET verify persisted
    g = requests.get(f"{BASE_URL}/api/programs/templates/{tid}",
                     headers=_h(owner_token), timeout=15)
    assert g.status_code == 200
    assert g.json()["name"] == "TEST_p6 renamed"
    assert g.json()["weeks_count"] == 2


def test_patch_other_users_template_403(other_token, created_template):
    tid = created_template["id"]
    r = requests.patch(f"{BASE_URL}/api/programs/templates/{tid}",
                       json={"name": "hax"}, headers=_h(other_token), timeout=15)
    assert r.status_code == 403


def test_patch_builtin_403(owner_token):
    # find any builtin
    r = requests.get(f"{BASE_URL}/api/programs/templates", headers=_h(owner_token), timeout=15)
    builtin = next(t for t in r.json() if t.get("is_builtin"))
    p = requests.patch(f"{BASE_URL}/api/programs/templates/{builtin['id']}",
                       json={"name": "hax"}, headers=_h(owner_token), timeout=15)
    assert p.status_code == 403


def test_delete_other_users_template_403(other_token, created_template):
    tid = created_template["id"]
    r = requests.delete(f"{BASE_URL}/api/programs/templates/{tid}",
                        headers=_h(other_token), timeout=15)
    assert r.status_code == 403


# ==================== Share: stable code ====================

def test_share_owner_returns_code_stable(owner_token):
    r1 = requests.post(f"{BASE_URL}/api/programs/templates/{DEMO_TEMPLATE_ID}/share",
                       headers=_h(owner_token), timeout=15)
    assert r1.status_code == 200, f"{r1.status_code} {r1.text[:200]}"
    d1 = r1.json()
    assert re.match(r"^TWB-[A-Z0-9]{6}$", d1["code"]), f"bad code format: {d1['code']}"
    assert d1["web_path"] == f"/import/{d1['code']}"
    # tg_link may be None if bot username not resolvable in this env
    if d1.get("tg_link"):
        assert "t.me/" in d1["tg_link"]
        assert d1["code"].replace("-", "_") in d1["tg_link"]

    # stable on repeat
    r2 = requests.post(f"{BASE_URL}/api/programs/templates/{DEMO_TEMPLATE_ID}/share",
                       headers=_h(owner_token), timeout=15)
    assert r2.status_code == 200
    assert r2.json()["code"] == d1["code"], "share code must be stable"


def test_share_non_owner_403(other_token):
    r = requests.post(f"{BASE_URL}/api/programs/templates/{DEMO_TEMPLATE_ID}/share",
                      headers=_h(other_token), timeout=15)
    assert r.status_code == 403


# ==================== Public shared preview ====================

def test_shared_preview_public_no_auth():
    r = requests.get(f"{BASE_URL}/api/programs/shared/{DEMO_SHARE_CODE}", timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    d = r.json()
    assert d["code"] == DEMO_SHARE_CODE
    assert d["name"]
    assert d["weeks_count"] and d["weeks_count"] >= 1
    assert d["exercises_count"] >= 1
    assert d["author_name"]


def test_shared_preview_includes_week1_and_forecast():
    """Публичный preview должен возвращать превью 1-й недели + прогноз."""
    r = requests.get(f"{BASE_URL}/api/programs/shared/{DEMO_SHARE_CODE}", timeout=15)
    assert r.status_code == 200
    d = r.json()
    # week1_days — список дней с упражнениями
    assert "week1_days" in d
    week1 = d["week1_days"]
    assert isinstance(week1, list) and len(week1) >= 1
    day = week1[0]
    assert "day_index" in day and "title" in day and "exercises" in day
    assert isinstance(day["exercises"], list) and len(day["exercises"]) >= 1
    ex = day["exercises"][0]
    for field in ("name", "muscle_group", "lift_group", "is_accessory",
                  "target_sets", "target_reps", "sets_scheme"):
        assert field in ex, f"missing {field} in exercise preview"
    # forecast — либо тоннаж, либо интенсивность
    assert "forecast" in d
    fc = d["forecast"]
    assert "is_percent_based" in fc
    if fc["is_percent_based"]:
        assert "weekly_intensity" in fc
    else:
        assert "weekly_tonnage" in fc
        assert isinstance(fc["weekly_tonnage"], list)
        assert all("week" in x and "tonnage" in x for x in fc["weekly_tonnage"])


def test_shared_preview_accepts_variants():
    # lowercase / no prefix / underscore
    for variant in [DEMO_SHARE_CODE.lower(), "twb_zzb5zs", "ZZB5ZS", "zzb5zs"]:
        r = requests.get(f"{BASE_URL}/api/programs/shared/{variant}", timeout=15)
        assert r.status_code == 200, f"variant {variant!r} -> {r.status_code} {r.text[:150]}"
        assert r.json()["code"] == DEMO_SHARE_CODE


def test_shared_preview_404_unknown():
    r = requests.get(f"{BASE_URL}/api/programs/shared/TWB-XXXXX9", timeout=15)
    assert r.status_code == 404


# ==================== Import ====================

def test_import_own_returns_own_true(owner_token):
    r = requests.post(f"{BASE_URL}/api/programs/import/{DEMO_SHARE_CODE}",
                      headers=_h(owner_token), timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("own") is True
    assert d.get("already_imported") is True


def test_import_by_other_creates_copy_then_dedup(other_token):
    r1 = requests.post(f"{BASE_URL}/api/programs/import/{DEMO_SHARE_CODE}",
                       headers=_h(other_token), timeout=15)
    assert r1.status_code == 200
    d1 = r1.json()
    tpl = d1["template"]
    assert tpl["owner_telegram_id"] == OTHER_TG
    assert tpl["source"] == "import"
    assert tpl["shared_from"] == DEMO_TEMPLATE_ID
    assert tpl.get("share_code") in (None, "")

    # Verify persisted in other user's list
    lst = requests.get(f"{BASE_URL}/api/programs/templates",
                       headers=_h(other_token), timeout=15).json()
    assert any(t.get("id") == tpl["id"] for t in lst)

    # Second import → dedup, same id
    r2 = requests.post(f"{BASE_URL}/api/programs/import/{DEMO_SHARE_CODE}",
                       headers=_h(other_token), timeout=15)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("already_imported") is True
    assert d2["template"]["id"] == tpl["id"], "second import must dedup, not duplicate"


def test_import_404_unknown_code(owner_token):
    r = requests.post(f"{BASE_URL}/api/programs/import/TWB-XXXXX9",
                      headers=_h(owner_token), timeout=15)
    assert r.status_code == 404


def test_import_requires_auth():
    r = requests.post(f"{BASE_URL}/api/programs/import/{DEMO_SHARE_CODE}", timeout=15)
    assert r.status_code == 401


# ==================== AI: status / validation / jobs ====================

def test_ai_status():
    r = requests.get(f"{BASE_URL}/api/ai/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "enabled" in d and "model" in d


def test_ai_generate_requires_auth():
    r = requests.post(f"{BASE_URL}/api/ai/program/generate",
                      json={"prompt": "some long enough prompt text"}, timeout=15)
    assert r.status_code == 401


def test_ai_parse_requires_auth():
    r = requests.post(f"{BASE_URL}/api/ai/program/parse",
                      json={"text": "a" * 50}, timeout=15)
    assert r.status_code == 401


def test_ai_questions_requires_auth():
    r = requests.post(f"{BASE_URL}/api/ai/program/questions",
                      json={"prompt": "some long enough prompt text"}, timeout=15)
    assert r.status_code == 401


def test_ai_generate_short_prompt_400(owner_token):
    r = requests.post(f"{BASE_URL}/api/ai/program/generate",
                      json={"prompt": "hi"}, headers=_h(owner_token), timeout=15)
    assert r.status_code == 400
    assert "минимум" in r.json().get("detail", "").lower() or "симв" in r.json().get("detail", "").lower()


def test_ai_questions_short_prompt_400(owner_token):
    r = requests.post(f"{BASE_URL}/api/ai/program/questions",
                      json={"prompt": "hi"}, headers=_h(owner_token), timeout=15)
    assert r.status_code == 400


def test_ai_job_requires_auth():
    r = requests.get(f"{BASE_URL}/api/ai/program/jobs/nonexistent", timeout=15)
    assert r.status_code == 401


def test_ai_job_not_found(owner_token):
    r = requests.get(f"{BASE_URL}/api/ai/program/jobs/{uuid.uuid4()}",
                     headers=_h(owner_token), timeout=15)
    assert r.status_code == 404


# ==================== Regression: create plan from own template ====================

def test_regression_plan_from_own_template(owner_token, created_template):
    tid = created_template["id"]
    r = requests.post(f"{BASE_URL}/api/plans",
                      json={"athlete_telegram_id": OWNER_TG, "template_id": tid,
                            "name": "TEST_p6 plan"},
                      headers=_h(owner_token), timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    plan = r.json()
    assert plan.get("source_template_id") == tid
    assert plan.get("weeks"), "weeks snapshot must be present"

    # cleanup — delete created plan
    requests.delete(f"{BASE_URL}/api/plans/{plan['id']}",
                    headers=_h(owner_token), timeout=15)


def test_regression_plan_from_builtin(owner_token):
    r = requests.get(f"{BASE_URL}/api/programs/templates", headers=_h(owner_token), timeout=15)
    builtin = next(t for t in r.json() if t.get("is_builtin"))
    p = requests.post(f"{BASE_URL}/api/plans",
                      json={"athlete_telegram_id": OWNER_TG, "template_id": builtin["id"],
                            "name": "TEST_p6 builtin plan",
                            "maxes": {"squat": 200, "bench": 130, "deadlift": 230}},
                      headers=_h(owner_token), timeout=15)
    assert p.status_code == 200, f"{p.status_code} {p.text[:300]}"
    plan = p.json()
    assert plan.get("weeks")

    # cleanup
    requests.delete(f"{BASE_URL}/api/plans/{plan['id']}",
                    headers=_h(owner_token), timeout=15)
