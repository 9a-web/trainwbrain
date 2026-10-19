"""
TrainWithBrain — AI parse-photo (Gemini vision → DeepSeek structure) tests.
Covers:
  - /api/ai/status vision fields
  - POST /api/ai/program/parse-photo auth (401), validation (0/9 files, non-image)
  - E2E: 1 JPG → job_id → GET /ai/program/jobs/{id} → done + valid template (cleanup)
  - Regression: /api/ai/program/generate short prompt (DeepSeek/RouterAI)
  - Regression: /api/ai/program/refine on generated template
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

USER_EMAIL = "streakdemo@twb.dev"
USER_PW = "password123"
TEST_JPG = "/tmp/workout_test.jpg"

JOB_TIMEOUT_S = 180  # up to 3 min for AI pipelines
POLL_INTERVAL = 3


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _poll_job(job_id, tok, timeout=JOB_TIMEOUT_S):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/ai/program/jobs/{job_id}",
                         headers=_h(tok), timeout=20)
        assert r.status_code == 200, f"job poll failed: {r.status_code} {r.text[:200]}"
        last = r.json()
        st = last.get("status")
        if st in ("done", "error"):
            return last
        time.sleep(POLL_INTERVAL)
    raise AssertionError(f"job {job_id} timed out; last={last}")


def _cleanup_template(tid, tok):
    if not tid:
        return
    try:
        requests.delete(f"{BASE_URL}/api/programs/templates/{tid}",
                        headers=_h(tok), timeout=15)
    except Exception:
        pass


@pytest.fixture(scope="module")
def token():
    return _login(USER_EMAIL, USER_PW)


# ==================== AI status (public) ====================

def test_ai_status_returns_dual_provider():
    r = requests.get(f"{BASE_URL}/api/ai/status", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("enabled") is True
    assert d.get("model") == "deepseek/deepseek-v4-flash"
    assert d.get("vision_enabled") is True
    assert d.get("vision_model") == "gemini-flash-latest"


# ==================== parse-photo validation ====================

def test_parse_photo_requires_auth():
    with open(TEST_JPG, "rb") as f:
        r = requests.post(f"{BASE_URL}/api/ai/program/parse-photo",
                          files=[("files", ("w.jpg", f, "image/jpeg"))], timeout=20)
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"


def test_parse_photo_no_files_returns_400(token):
    # FastAPI's File(...) enforces presence; try with an empty upload list
    r = requests.post(f"{BASE_URL}/api/ai/program/parse-photo",
                      headers=_h(token), files=[], timeout=20)
    # Either FastAPI validation 422 (missing form field) or endpoint's 400 body
    assert r.status_code in (400, 422), f"unexpected {r.status_code}: {r.text[:200]}"


def test_parse_photo_too_many_files_returns_400(token):
    with open(TEST_JPG, "rb") as f:
        data = f.read()
    files = [("files", (f"p{i}.jpg", data, "image/jpeg")) for i in range(9)]
    r = requests.post(f"{BASE_URL}/api/ai/program/parse-photo",
                      headers=_h(token), files=files, timeout=30)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    assert "8" in r.text  # "не более 8 фото"


def test_parse_photo_non_image_returns_400(token):
    r = requests.post(f"{BASE_URL}/api/ai/program/parse-photo",
                      headers=_h(token),
                      files=[("files", ("plan.txt", b"just some text", "text/plain"))],
                      timeout=20)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    body = r.text.lower()
    assert ("изображ" in body) or ("image" in body)


# ==================== parse-photo E2E ====================

def test_parse_photo_e2e_creates_template(token):
    """Upload 1 JPG → get job_id → poll to done → validate template → delete."""
    with open(TEST_JPG, "rb") as f:
        data = f.read()
    r = requests.post(f"{BASE_URL}/api/ai/program/parse-photo",
                      headers=_h(token),
                      files=[("files", ("workout.jpg", data, "image/jpeg"))],
                      timeout=30)
    assert r.status_code == 200, f"submit failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert "job_id" in body, body
    assert body.get("status") in ("pending", "running", "done"), body
    job_id = body["job_id"]

    result = _poll_job(job_id, token, timeout=JOB_TIMEOUT_S)
    assert result.get("status") == "done", f"job did not finish OK: {result}"
    tpl = result.get("template")
    assert isinstance(tpl, dict), f"no template: {result}"
    tid = tpl.get("id")
    try:
        assert isinstance(tid, str) and len(tid) > 0
        assert isinstance(tpl.get("name"), str) and len(tpl["name"]) > 0
        weeks = tpl.get("weeks") or []
        assert isinstance(weeks, list) and len(weeks) >= 1, f"weeks missing: {tpl}"
        days = weeks[0].get("days") or []
        assert isinstance(days, list) and len(days) >= 1, f"days missing: {weeks[0]}"
        exs = days[0].get("exercises") or []
        assert isinstance(exs, list) and len(exs) >= 1, f"exercises missing: {days[0]}"
    finally:
        _cleanup_template(tid, token)


# ==================== regression: generate ====================

def test_ai_generate_short_prompt_works(token):
    """Regression: DeepSeek text generation still works via RouterAI."""
    payload = {"prompt": "база 3 дня в неделю, 2 недели, приседаю 100кг"}
    r = requests.post(f"{BASE_URL}/api/ai/program/generate",
                      headers=_h(token), json=payload, timeout=30)
    assert r.status_code == 200, f"submit failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert "job_id" in body, body
    job_id = body["job_id"]
    result = _poll_job(job_id, token, timeout=JOB_TIMEOUT_S)
    assert result.get("status") == "done", f"generate failed: {result}"
    tpl = result.get("template")
    assert isinstance(tpl, dict) and isinstance(tpl.get("weeks"), list) and len(tpl["weeks"]) >= 1
    tid = tpl.get("id")

    # ============ regression: refine ============
    try:
        rpayload = {"template_id": tid, "feedback": "убери становую тягу"}
        r2 = requests.post(f"{BASE_URL}/api/ai/program/refine",
                           headers=_h(token), json=rpayload, timeout=30)
        assert r2.status_code == 200, f"refine submit failed: {r2.status_code} {r2.text[:300]}"
        rb = r2.json()
        assert "job_id" in rb, rb
        result2 = _poll_job(rb["job_id"], token, timeout=JOB_TIMEOUT_S)
        assert result2.get("status") == "done", f"refine failed: {result2}"
        tpl2 = result2.get("template")
        assert isinstance(tpl2, dict), tpl2
        # refine keeps same id
        assert tpl2.get("id") == tid, f"refine changed id: {tid} -> {tpl2.get('id')}"
    finally:
        _cleanup_template(tid, token)
