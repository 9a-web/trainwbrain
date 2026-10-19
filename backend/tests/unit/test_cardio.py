"""Unit-тесты кардио-модуля (Фаза 3) — чистые хелперы, без БД/сети."""
import math

import pytest
from fastapi import HTTPException

from server import (
    CARDIO_MET,
    cardio_kcal,
    cardio_met,
    _clean_cardio_payload,
    _parse_hhmmss_pace,
    _avg_speed_kmh,
)


# --- MET ---------------------------------------------------------------------
def test_met_lookup_by_type_and_intensity():
    assert cardio_met("treadmill", "high") == 11.0
    assert cardio_met("walk", "low") == 2.8
    assert cardio_met("bike", "moderate") == 7.0


def test_met_fallbacks():
    # неизвестный тип → other, неизвестная интенсивность → moderate
    assert cardio_met("spaceship", "moderate") == CARDIO_MET["other"]["moderate"]
    assert cardio_met("treadmill", None) == CARDIO_MET["treadmill"]["moderate"]
    assert cardio_met(None, "weird") == CARDIO_MET["other"]["moderate"]


# --- Калории (MET-формула) ---------------------------------------------------
def test_kcal_formula_known_value():
    # 80 кг, 30 мин, MET 8.0 → 8.0*3.5*80/200*30 = 336
    assert cardio_kcal("treadmill", "moderate", 80, 1800) == 336


def test_kcal_zero_when_no_duration():
    assert cardio_kcal("bike", "high", 80, 0) == 0
    assert cardio_kcal("bike", "high", 80, None) == 0


def test_kcal_defaults_weight_when_missing():
    # без веса берём 75 кг по умолчанию
    assert cardio_kcal("rower", "moderate", None, 3600) == int(round(7.0 * 3.5 * 75 / 200 * 60))


def test_kcal_monotonic_in_duration_and_weight():
    a = cardio_kcal("bike", "moderate", 70, 600)
    b = cardio_kcal("bike", "moderate", 70, 1200)
    c = cardio_kcal("bike", "moderate", 90, 600)
    assert a < b
    assert a < c


# --- Темп --------------------------------------------------------------------
def test_pace_parsing():
    # 5 км за 35:00 → 07:00 /км
    assert _parse_hhmmss_pace(5.0, 2100) == "07:00"
    assert _parse_hhmmss_pace(0, 1800) is None
    assert _parse_hhmmss_pace(5.0, 0) is None


def test_avg_speed_kmh():
    # 10 км за 30 мин → 20 км/ч
    assert _avg_speed_kmh(10.0, 1800) == 20.0
    # 4.2 км за 30 мин → 8.4 км/ч
    assert _avg_speed_kmh(4.2, 1800) == 8.4
    assert _avg_speed_kmh(0, 1800) is None
    assert _avg_speed_kmh(5.0, 0) is None
    assert _avg_speed_kmh(None, None) is None


# --- Валидация ---------------------------------------------------------------
def test_clean_accepts_valid_payload():
    out = _clean_cardio_payload({
        "type": "Treadmill", "date": "2026-10-01", "duration_min": 30,
        "distance_km": 4.2, "avg_hr": 142, "max_hr": 168, "rpe": 6.5,
        "incline_percent": 6, "avg_speed_kmh": 8.4, "intensity": "moderate",
    })
    assert out["type"] == "treadmill"
    assert out["date"] == "2026-10-01"
    assert out["duration_sec"] == 1800
    assert out["distance_km"] == 4.2
    assert out["rpe"] == 6.5
    assert out["intensity"] == "moderate"


def test_clean_rejects_bad_type_and_intensity():
    with pytest.raises(HTTPException) as e:
        _clean_cardio_payload({"type": "swimming"})
    assert e.value.status_code == 400
    with pytest.raises(HTTPException):
        _clean_cardio_payload({"intensity": "extreme"})


def test_clean_rejects_out_of_range_hr_and_rpe():
    for bad in ({"avg_hr": 5}, {"avg_hr": 400}, {"rpe": 0}, {"rpe": 11}):
        with pytest.raises(HTTPException) as e:
            _clean_cardio_payload(bad)
        assert e.value.status_code == 400


def test_clean_rejects_negative_and_huge_duration():
    with pytest.raises(HTTPException):
        _clean_cardio_payload({"duration_sec": 0})
    with pytest.raises(HTTPException):
        _clean_cardio_payload({"duration_min": -5})
    with pytest.raises(HTTPException):
        _clean_cardio_payload({"duration_sec": 100000})


def test_clean_rejects_bad_distance_and_nan():
    with pytest.raises(HTTPException):
        _clean_cardio_payload({"distance_km": -1})
    with pytest.raises(HTTPException):
        _clean_cardio_payload({"distance_km": float("nan")})
    with pytest.raises(HTTPException):
        _clean_cardio_payload({"distance_km": 999})


def test_clean_rejects_bad_date():
    with pytest.raises(HTTPException):
        _clean_cardio_payload({"date": "not-a-date"})


def test_clean_partial_requires_at_least_one_field():
    with pytest.raises(HTTPException):
        _clean_cardio_payload({}, partial=True)
    # валидный частичный апдейт проходит
    assert _clean_cardio_payload({"notes": "ок"}, partial=True) == {"notes": "ок"}


def test_clean_truncates_notes():
    out = _clean_cardio_payload({"notes": "x" * 5000})
    assert len(out["notes"]) == 1000


def test_clean_explicit_null_clears_nullable_field():
    # смена дорожки на вело убирает наклон/дистанцию
    out = _clean_cardio_payload({"type": "bike", "incline_percent": None,
                                 "distance_km": None, "notes": None}, partial=True)
    assert out["type"] == "bike"
    assert out["incline_percent"] is None
    assert out["distance_km"] is None
    assert out["notes"] is None


def test_clean_null_for_required_field_is_ignored():
    # type/date/duration нельзя очистить — null игнорируется, поэтому
    # payload только из null-ов обязательных полей даёт 400 (нечего менять).
    with pytest.raises(HTTPException) as e:
        _clean_cardio_payload({"duration_sec": None, "date": None}, partial=True)
    assert e.value.status_code == 400
    # но null обязательного поля вместе с валидным полем не мешает
    out = _clean_cardio_payload({"duration_sec": None, "type": "bike"}, partial=True)
    assert out == {"type": "bike"}
