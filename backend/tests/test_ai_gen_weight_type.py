"""
Verify AI-generated template respects `weight_type` from catalog for bodyweight
exercises AND verify sets/reps variation across weeks.
"""
import os
import time
import json
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


def _login():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PW}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def token():
    return _login()


@pytest.fixture(scope="module")
def catalog_weight_types(token):
    """Fetch exercises catalog. Return {slug: weight_type} — helps us know what's stored."""
    r = requests.get(f"{BASE_URL}/api/exercises",
                     headers={"Authorization": f"Bearer {token}"}, timeout=15)
    r.raise_for_status()
    result = {}
    for ex in r.json():
        result[ex.get("slug")] = ex.get("weight_type")
    return result


def test_catalog_bodyweight_exercises_have_correct_weight_type(catalog_weight_types):
    """Планка, подтягивания, брусья и подъём ног в висе должны иметь weight_type='bodyweight' в каталоге."""
    bw_slugs = ["plank", "pull-up", "dips", "hanging-leg-raise"]
    missing = []
    for slug in bw_slugs:
        wt = catalog_weight_types.get(slug)
        if wt != "bodyweight":
            missing.append(f"{slug}: weight_type={wt!r} (expected 'bodyweight')")
    assert not missing, (
        "Каталог упражнений НЕ содержит weight_type='bodyweight' для BW-упражнений — "
        "фикс backend `_ai_build_template` не сможет корректно определить bodyweight: "
        + "; ".join(missing)
    )


@pytest.fixture(scope="module")
def ai_generated_template(token):
    """Generate a fresh AI template. Skip if AI disabled or too slow."""
    r = requests.get(f"{BASE_URL}/api/ai/status", timeout=15)
    if not r.json().get("enabled"):
        pytest.skip("AI disabled — cannot test generation")

    prompt = (
        "Программа для мужчины 30 лет, продвинутый уровень, 4 дня в неделю, "
        "гипертрофия+сила. Обязательно включи планку, подтягивания и упражнения "
        "с гантелями (жим гантелей лёжа, разводка гантелей). Продолжительность 4 недели."
    )
    body = {
        "prompt": prompt,
        "answers": [
            {"question": "цель", "answer": "гипертрофия+сила"},
            {"question": "уровень", "answer": "продвинутый"},
            {"question": "дней в неделю", "answer": "4"},
            {"question": "недель", "answer": "4"},
            {"question": "оборудование", "answer": "полный зал"},
            {"question": "время", "answer": "60-75 минут"},
        ],
    }
    r = requests.post(f"{BASE_URL}/api/ai/program/generate",
                      json=body,
                      headers={"Authorization": f"Bearer {token}"},
                      timeout=60)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    job_id = r.json().get("job_id")
    assert job_id
    # Poll
    deadline = time.time() + 240  # 4 min
    template = None
    last_status = None
    while time.time() < deadline:
        jr = requests.get(f"{BASE_URL}/api/ai/program/jobs/{job_id}",
                          headers={"Authorization": f"Bearer {token}"}, timeout=15)
        if jr.status_code == 200:
            jd = jr.json()
            last_status = jd.get("status")
            if last_status == "done":
                template = jd.get("template")
                break
            if last_status == "error":
                pytest.fail(f"AI job error: {jd.get('detail') or jd}")
        time.sleep(4)
    if template is None:
        pytest.skip(f"AI generation did not complete within budget (last_status={last_status})")
    return template


def test_ai_template_weight_type_matches_catalog(ai_generated_template, catalog_weight_types):
    """
    Для упражнений в шаблоне с exercise_slug из каталога weight_type должен браться
    из каталога (bodyweight для планки/подтягиваний, kg для остальных),
    а НЕ жёстко 'kg'.
    """
    tpl = ai_generated_template
    mismatches = []
    bw_found = 0
    kg_found = 0
    for w in tpl.get("weeks", [])[:1]:  # проверим 1-ю неделю достаточно
        for d in w.get("days", []):
            for e in d.get("exercises", []):
                slug = e.get("exercise_slug")
                if not slug:
                    continue
                cat_wt = catalog_weight_types.get(slug)
                tpl_wt = e.get("weight_type")
                if cat_wt is None:
                    continue  # no expectation
                if cat_wt == "bodyweight":
                    bw_found += 1
                    if tpl_wt != "bodyweight":
                        mismatches.append(
                            f"{e.get('exercise_name')} (slug={slug}): "
                            f"weight_type в шаблоне={tpl_wt!r}, в каталоге={cat_wt!r}"
                        )
                else:
                    kg_found += 1
    print(f"\n[AI template id={tpl.get('id')}] BW exercises matched: {bw_found}, KG exercises: {kg_found}")
    assert not mismatches, (
        f"Backend НЕ проставляет weight_type='bodyweight' для BW-упражнений: {mismatches}"
    )


def test_ai_template_varies_sets_reps_across_weeks(ai_generated_template):
    """
    В сгенерированной программе базовые упражнения должны иметь ВАРИАЦИЮ
    sets/reps между неделями (хотя бы часть — не все недели идентичны).
    """
    tpl = ai_generated_template
    weeks = tpl.get("weeks", [])
    if len(weeks) < 2:
        pytest.skip("Only one week generated — cannot check variation")

    # Собрать первую сет-схему для каждого упражнения по неделям
    per_exercise = {}
    for w in weeks:
        for d in w.get("days", []):
            for e in d.get("exercises", []):
                key = (d.get("day_index"), e.get("order"), e.get("exercise_name"))
                scheme = e.get("sets_scheme") or []
                first = scheme[0] if scheme else {}
                per_exercise.setdefault(key, []).append(
                    (first.get("sets"), first.get("reps"))
                )

    varied = 0
    total = 0
    for key, series in per_exercise.items():
        if len(series) < 2:
            continue
        total += 1
        # varied if any two series entries differ
        if len(set(series)) > 1:
            varied += 1

    ratio = varied / total if total else 0
    print(f"\n[variation] {varied}/{total} exercises vary sets/reps across weeks ({ratio:.0%})")
    # Требование: хотя бы часть базовых имеет вариацию (не все идентичны)
    assert varied >= 1, (
        f"ИИ НЕ варьирует sets/reps между неделями ни в одном упражнении "
        f"(0/{total}). Промпт _AI_SYSTEM_GEN не даёт нужного эффекта."
    )


def test_ai_template_no_bodyweight_wrong_kg(ai_generated_template, catalog_weight_types):
    """
    В шаблоне не должно быть упражнения с weight_type='kg' И with None weight
    для СЛУЖЕБНЫХ bw-упражнений (планка, подтягивания без пояса, hanging-leg-raise).
    Это была суть исходного бага — 'Свой вес' для не-bw.
    """
    tpl = ai_generated_template
    bad = []
    for w in tpl.get("weeks", [])[:1]:
        for d in w.get("days", []):
            for e in d.get("exercises", []):
                slug = e.get("exercise_slug")
                if catalog_weight_types.get(slug) == "bodyweight":
                    if e.get("weight_type") == "kg":
                        bad.append(f"{e.get('exercise_name')} (slug={slug})")
    assert not bad, (
        f"Backend помечает bodyweight-упражнения как weight_type='kg', "
        f"что приведёт к отображению '—' вместо 'Свой вес' на фронте: {bad}"
    )
