"""Unit-тесты правки завершённой тренировки (офлайн, без БД/сети).

Проверяют, что:
  * статистика истории пересчитывается из исправленных упражнений
    (тоннаж/подходы не «залипают» на замороженном снимке финиша);
  * `_assert_session_mutable` по-прежнему блокирует прочие мутации
    завершённой сессии (подходы/действия), хотя правка упражнения
    (edit_session_exercise) теперь разрешена.
"""
import pytest
from fastapi import HTTPException

from server import _assert_session_mutable, _session_stats


def _ex(order, status, tonnage, sets=3, reps=5, weight=100, muscle="chest"):
    scheme = [{"weight": weight, "sets": sets, "reps": reps, "percent_1rm": 80}]
    return {
        "order": order,
        "status": status,
        "tonnage": tonnage,
        "muscle_group": muscle,
        "muscle_letter": "Г",
        "difficulty": "Средняя",
        "sets_scheme": scheme,
        "plan_sets_scheme": [dict(scheme[0])],
    }


def _finished(exs):
    return {
        "id": "s1",
        "status": "finished",
        "started_at": "2026-10-01T10:00:00+00:00",
        "finished_at": "2026-10-01T11:00:00+00:00",
        "exercises": exs,
    }


def test_stats_reflect_edited_tonnage_after_finish():
    before = _session_stats(_finished([_ex(0, "done", 1500, sets=3)]))
    after = _session_stats(_finished([_ex(0, "done", 3000, sets=6)]))

    assert before["tonnage"] == 1500
    assert after["tonnage"] == 3000
    assert before["sets_done"] == 3
    assert after["sets_done"] == 6
    assert after["tonnage"] != before["tonnage"]


def test_stats_ignore_skipped_exercise_tonnage():
    stats = _session_stats(_finished([_ex(0, "skipped", 9999), _ex(1, "done", 1000)]))
    assert stats["tonnage"] == 1000
    assert stats["skipped_count"] == 1


def test_assert_session_mutable_blocks_finished():
    with pytest.raises(HTTPException) as e:
        _assert_session_mutable({"status": "finished"})
    assert e.value.status_code == 409


def test_assert_session_mutable_allows_in_progress():
    _assert_session_mutable({"status": "in_progress"})
    _assert_session_mutable({})
