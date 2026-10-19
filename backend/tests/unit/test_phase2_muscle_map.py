"""Unit-тесты Фазы 2: карта мышц — нормализация весов мышц и агрегатор
объёма/подходов (офлайн, без БД)."""
from server import (
    MUSCLE_CANON,
    _build_muscle_map,
)
from seed import MUSCLE_VIEWS, normalize_muscle_weights


# --- normalize_muscle_weights -------------------------------------------------

def test_primary_gets_full_weight():
    w = normalize_muscle_weights(["chest"], [])
    assert w == {"chest": 1.0}


def test_secondary_gets_half():
    w = normalize_muscle_weights(["chest"], ["triceps", "shoulders"])
    assert w["chest"] == 1.0
    assert w["triceps"] == 0.5


def test_legacy_legs_expansion():
    w = normalize_muscle_weights(["legs"], [])
    assert w["quads"] == 1.0
    assert abs(w["hamstrings"] - 0.6) < 1e-9
    assert abs(w["glutes"] - 0.6) < 1e-9


def test_legacy_back_and_shoulders_and_core():
    w = normalize_muscle_weights(["back"], ["core"])
    assert w["lats"] == 1.0
    assert w["upper_back"] == 1.0
    assert w["abs"] == 0.5          # secondary core: 1.0 * 0.5
    assert abs(w["obliques"] - 0.3) < 1e-9  # 0.6 * 0.5

    s = normalize_muscle_weights(["shoulders"], [])
    assert s["front_delts"] == 1.0
    assert s["side_delts"] == 1.0
    assert s["rear_delts"] == 1.0


def test_unknown_keys_dropped():
    assert normalize_muscle_weights(["spinarius"], []) == {}
    assert normalize_muscle_weights([], []) == {}
    assert normalize_muscle_weights(None, None) == {}


def test_sum_accumulates_duplicate_groups():
    w = normalize_muscle_weights(["chest", "chest"], [])
    assert abs(w["chest"] - 2.0) < 1e-9


def test_all_output_keys_are_canon():
    w = normalize_muscle_weights(["legs", "back", "shoulders", "core"], MUSCLE_CANON)
    assert set(w) <= set(MUSCLE_CANON)


# --- _build_muscle_map ----------------------------------------------------------

def _ex(slug, primary, secondary=None, ex_id=None):
    return {
        "id": ex_id or f"id-{slug}",
        "slug": slug,
        "muscle_groups": primary,
        "secondary_groups": secondary or [],
    }


def _session(sid, exercises):
    return {"id": sid, "exercises": exercises}


def _bench_exercise(weight=100, reps=10, sets=3):
    """Жим лёжа: 3 подхода, все выполнены."""
    return {
        "status": "done",
        "exercise_id": "id-bench-press",
        "exercise_slug": "bench-press",
        "set_logs": [
            {"done": True, "weight": weight, "reps": reps} for _ in range(sets)
        ],
    }


CATALOG = {
    "by_id": {
        "id-bench-press": _ex("bench-press", ["chest"], ["triceps", "shoulders"]),
        "id-back-squat": _ex("back-squat", ["legs"], ["glutes", "core"]),
    },
    "by_slug": {
        "bench-press": _ex("bench-press", ["chest"], ["triceps", "shoulders"]),
        "back-squat": _ex("back-squat", ["legs"], ["glutes", "core"]),
    },
}


def test_empty_period_all_regions_neutral():
    agg = _build_muscle_map([], {}, {})
    assert set(agg["regions"]) == set(MUSCLE_CANON)
    for m, r in agg["regions"].items():
        assert r["volume_kg"] == 0
        assert r["working_sets"] == 0
        assert r["sessions"] == 0
        assert r["intensity_0_1"] == 0.0
    assert agg["totals"] == {"volume": 0, "sets": 0, "sessions": 0}
    assert agg["imbalance"] == []


def test_volume_distribution_primary_and_secondary():
    sessions = [_session("s1", [_bench_exercise(weight=100, reps=10, sets=3)])]
    agg = _build_muscle_map(sessions, CATALOG["by_id"], CATALOG["by_slug"])
    # Объём упражнения = 100*10*3 = 3000
    assert agg["regions"]["chest"]["volume_kg"] == 3000
    assert agg["regions"]["triceps"]["volume_kg"] == 1500   # secondary 0.5
    # shoulders → каждая дельта 1.0 × 0.5 (secondary)
    for delt in ("front_delts", "side_delts", "rear_delts"):
        assert agg["regions"][delt]["volume_kg"] == 1500
    assert agg["regions"]["chest"]["working_sets"] == 3
    assert agg["regions"]["triceps"]["working_sets"] == 2  # round(3 * 0.5)
    assert agg["regions"]["chest"]["sessions"] == 1
    assert agg["totals"]["volume"] == 3000 * (1 + 0.5 + 3 * 0.5)
    assert agg["totals"]["sets"] == 3 + 2 + 3 * 2  # chest + triceps + 3 delts


def test_intensity_normalized_to_max_region():
    sessions = [_session("s1", [_bench_exercise()])]
    agg = _build_muscle_map(sessions, CATALOG["by_id"], CATALOG["by_slug"])
    assert agg["regions"]["chest"]["intensity_0_1"] == 1.0
    assert 0 < agg["regions"]["triceps"]["intensity_0_1"] < 1.0


def test_legacy_session_without_set_logs_uses_tonnage():
    ex = {
        "status": "done",
        "exercise_slug": "back-squat",
        "tonnage": 6000,
        "sets_scheme": [{"weight": 100, "sets": 3, "reps": 5}, {"weight": 90, "sets": 3, "reps": 5}],
    }
    agg = _build_muscle_map([_session("s2", [ex])], CATALOG["by_id"], CATALOG["by_slug"])
    assert agg["regions"]["quads"]["volume_kg"] == 6000
    assert agg["regions"]["quads"]["working_sets"] == 2  # число строк sets_scheme
    assert agg["regions"]["hamstrings"]["working_sets"] == 1  # round(2*0.6)


def test_skipped_and_undone_sets_ignored():
    ex = {
        "status": "in_progress",
        "exercise_id": "id-bench-press",
        "set_logs": [{"done": False, "weight": 100, "reps": 10}],
    }
    agg = _build_muscle_map([_session("s3", [ex])], CATALOG["by_id"], CATALOG["by_slug"])
    assert agg["regions"]["chest"]["volume_kg"] == 0


def test_imbalance_flags_overweight_region():
    # Много жима + немного squat'а: chest > 1.75*медианы → imbalance
    sessions = [_session("s4", [_bench_exercise(weight=100, reps=10, sets=10), {
        "status": "done",
        "exercise_id": "id-back-squat",
        "set_logs": [{"done": True, "weight": 50, "reps": 5}],
    }])]
    agg = _build_muscle_map(sessions, CATALOG["by_id"], CATALOG["by_slug"])
    assert "chest" in agg["imbalance"]


def test_unknown_exercise_ignored():
    ex = {"status": "done", "exercise_slug": "alien-exercise",
          "set_logs": [{"done": True, "weight": 100, "reps": 10}]}
    agg = _build_muscle_map([_session("s5", [ex])], {}, {})
    assert agg["totals"] == {"volume": 0, "sets": 0, "sessions": 0}


def test_sessions_counted_across_workouts():
    sessions = [
        _session("a", [_bench_exercise(sets=1)]),
        _session("b", [_bench_exercise(sets=1)]),
    ]
    agg = _build_muscle_map(sessions, CATALOG["by_id"], CATALOG["by_slug"])
    assert agg["regions"]["chest"]["sessions"] == 2
    assert agg["totals"]["sessions"] == 2


def test_views_shape():
    assert set(MUSCLE_VIEWS) == {"front", "back"}
    assert "chest" in MUSCLE_VIEWS["front"]
    assert "lats" in MUSCLE_VIEWS["back"]
    assert set(MUSCLE_VIEWS["front"]) | set(MUSCLE_VIEWS["back"]) == set(MUSCLE_CANON)
