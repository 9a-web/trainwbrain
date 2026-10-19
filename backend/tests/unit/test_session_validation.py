"""Unit-тесты валидации входа для по-подходного логирования (без БД/сети)."""
import math

import pytest
from fastapi import HTTPException

from server import SetLogReq


def test_valid_weight_and_reps_pass():
    r = SetLogReq(weight=100.5, reps=8).validated()
    assert r.weight == 100.5
    assert r.reps == 8


def test_negative_weight_rejected():
    with pytest.raises(HTTPException) as e:
        SetLogReq(weight=-1).validated()
    assert e.value.status_code == 400


def test_too_large_weight_rejected():
    with pytest.raises(HTTPException) as e:
        SetLogReq(weight=5000).validated()
    assert e.value.status_code == 400


def test_nan_and_inf_weight_rejected():
    with pytest.raises(HTTPException):
        SetLogReq(weight=float("nan")).validated()
    with pytest.raises(HTTPException):
        SetLogReq(weight=float("inf")).validated()


def test_reps_bounds():
    with pytest.raises(HTTPException):
        SetLogReq(reps=-1).validated()
    with pytest.raises(HTTPException):
        SetLogReq(reps=10_000).validated()
    assert SetLogReq(reps=0).validated().reps == 0


def test_none_fields_allowed():
    r = SetLogReq(done=True).validated()
    assert r.weight is None and r.reps is None
