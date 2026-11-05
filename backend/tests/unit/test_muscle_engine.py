"""Тесты движка разбора мышц (контракт muscle_load_v1)."""
import json

import muscle_engine as me


def _evidence(exercises, bodyweight=80.0):
    return {"session_id": "s1", "title": "Тест", "date": "2026-01-01",
            "bodyweight_kg": bodyweight, "exercises": exercises}


def _exercise(name, weights, sets, primary=None, secondary=None):
    return {
        "name": name,
        "weights": weights,
        "primary": primary or [],
        "secondary": secondary or [],
        "sets": sets,
    }


def test_contract_keys_and_clamp():
    ev = _evidence([
        _exercise("Жим лёжа", {"chest": 1.0, "triceps": 0.5},
                  [{"w": 80, "reps": 5, "pct": 82}] * 5),
    ])
    out = me.build_rules(ev)
    assert out["version"] == me.CONTRACT_VERSION
    assert out["engine"] == "rules"
    assert set(out["muscles"]) == set(me.MUSCLES)
    for m in me.MUSCLES:
        v = out["muscles"][m]
        assert 0.0 <= v["load_0_1"] <= 1.0
        assert isinstance(v["sets"], int) and isinstance(v["mechanical_kg"], int)
    assert out["muscles"]["chest"]["load_0_1"] > out["muscles"]["triceps"]["load_0_1"]
    assert out["muscles"]["calves"]["load_0_1"] == 0.0
    assert "chest" in out["focus"]


def test_empty_session_is_safe():
    out = me.build_rules(_evidence([]))
    assert out["totals"]["volume_kg"] == 0
    assert out["focus"] == []
    assert out["warnings"]


def test_intensity_curves():
    assert me.intensity_from_percent(90) == 1.0
    assert me.intensity_from_percent(50) <= 0.3
    assert me.intensity_from_percent(None) is None
    assert me.intensity_from_reps(3) == 1.0
    assert me.intensity_from_reps(30) < 0.5


def test_higher_intensity_gives_higher_load():
    light = me.build_rules(_evidence([
        _exercise("Жим", {"chest": 1.0}, [{"w": 60, "reps": 10, "pct": 60}] * 4),
    ]))
    heavy = me.build_rules(_evidence([
        _exercise("Жим", {"chest": 1.0}, [{"w": 60, "reps": 10, "pct": 88}] * 4),
    ]))
    assert heavy["muscles"]["chest"]["load_0_1"] >= light["muscles"]["chest"]["load_0_1"]
    assert heavy["totals"]["hard_sets"] > light["totals"]["hard_sets"]


def test_bodyweight_exercise_gets_load():
    out = me.build_rules(_evidence([
        _exercise("Подтягивания", {"lats": 1.0, "biceps": 0.5},
                  [{"w": 0, "reps": 8, "pct": None}] * 4),
    ], bodyweight=80.0))
    assert out["muscles"]["lats"]["load_0_1"] > 0
    assert out["muscles"]["lats"]["mechanical_kg"] > 0


def test_antagonist_gap_is_reported():
    out = me.build_rules(_evidence([
        _exercise("Жим лёжа", {"chest": 1.0, "front_delts": 0.5, "triceps": 0.5},
                  [{"w": 90, "reps": 5, "pct": 85}] * 6),
    ]))
    assert "chest" in out["balance"]["over"] or out["muscles"]["chest"]["load_0_1"] >= 0.8
    assert any("тяг" in w for w in out["warnings"])


def test_ai_payload_validation_drops_unknown_and_clamps_delta():
    base = me.build_rules(_evidence([
        _exercise("Жим", {"chest": 1.0, "triceps": 0.5}, [{"w": 80, "reps": 6, "pct": 80}] * 5),
    ]))
    raw = {
        "muscles": {
            "chest": {"load_0_1": 0.99, "why": "жим 5×6"},
            "biceps": {"load_0_1": 0.9},
            "hacker_muscle": {"load_0_1": 1.0},
        },
        "summary": "Грудь хорошо",
        "focus": ["chest", "unknown"],
        "balance": {"over": ["chest"], "under": ["lats"]},
        "warnings": ["нет тяг"],
    }
    out = me.validate_ai_payload(raw, base)
    assert out is not None
    assert out["engine"] == "ai"
    assert "hacker_muscle" not in out["muscles"]
    assert out["focus"] == ["chest"]
    base_chest = base["muscles"]["chest"]["load_0_1"]
    assert out["muscles"]["chest"]["load_0_1"] <= min(1.0, base_chest + 0.2) + 1e-9
    # biceps не был нагружен базой — ИИ не может его «включить» больше чем на 0.2
    assert out["muscles"]["biceps"]["load_0_1"] <= 0.2
    assert out["muscles"]["chest"]["why"] == "жим 5×6"


def test_ai_payload_rejects_garbage():
    base = me.build_rules(_evidence([]))
    assert me.validate_ai_payload("не json", base) is None
    assert me.validate_ai_payload({"muscles": {}}, base) is None
    assert me.merge_ai_response("```json\n{\"muscles\": {\"chest\": {\"load_0_1\": 0.5}}}\n```",
                                base, "deepseek-chat")["model"] == "deepseek-chat"


def test_ai_messages_contain_canon_and_protocol():
    ev = _evidence([_exercise("Жим", {"chest": 1.0}, [{"w": 80, "reps": 5, "pct": 80}])])
    base = me.build_rules(ev)
    msgs = me.ai_messages(ev, base)
    assert msgs[0]["role"] == "system"
    for m in me.MUSCLES:
        assert m in msgs[0]["content"]
    assert "Жим" in msgs[1]["content"]
    assert json.dumps(base["focus"], ensure_ascii=False) in msgs[1]["content"]
