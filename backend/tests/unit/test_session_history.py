"""Unit-тесты истории тренировок и карты одной завершённой сессии."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import server
from server import _completed_sets_session, _history_item, session_muscle_map, sessions_history


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, spec):
        # Mongo applies sort keys from the last key to the first key.
        for key, direction in reversed(spec if isinstance(spec, list) else [(spec, 1)]):
            self.rows.sort(key=lambda row: row.get(key) or "", reverse=direction < 0)
        return self

    def skip(self, amount):
        self.rows = self.rows[amount:]
        return self

    def limit(self, amount):
        self.rows = self.rows[:amount]
        return self

    async def to_list(self, _length):
        return list(self.rows)


class FakeCollection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    async def find_one(self, query, projection=None, sort=None):
        matches = [
            row for row in self.rows
            if all(row.get(key) == value for key, value in query.items())
        ]
        if sort and matches:
            key, direction = sort[0]
            matches.sort(key=lambda row: row.get(key) or "", reverse=direction < 0)
        return dict(matches[0]) if matches else None

    def find(self, query, projection=None):
        def matches(row, key, value):
            parts = key.split(".")

            def walk(node, index):
                if index == len(parts):
                    return node == value
                part = parts[index]
                if isinstance(node, list):
                    return any(walk(item, index) for item in node)
                if isinstance(node, dict):
                    return part in node and walk(node[part], index + 1)
                return False

            return walk(row, 0)

        def match(row):
            for key, value in query.items():
                if isinstance(value, dict) and "$in" in value:
                    if row.get(key) not in value["$in"]:
                        return False
                elif not matches(row, key, value):
                    return False
            return True
        return FakeCursor([dict(row) for row in self.rows if match(row)])

    async def count_documents(self, query):
        return len(await self.find(query).to_list(None))


class FakeDB:
    def __init__(self, sessions, exercises=None, links=None):
        self.workout_sessions = FakeCollection(sessions)
        self.exercises = FakeCollection(exercises)
        self.coach_links = FakeCollection(links)
        self.diary_profiles = FakeCollection()


def _session(session_id="s1", athlete=101, status="finished"):
    return {
        "id": session_id,
        "athlete_telegram_id": athlete,
        "status": status,
        "mode": "plan",
        "date": "2026-06-01",
        "title": "Грудь",
        "finished_at": "2026-06-01T12:00:00+00:00",
        "created_at": "2026-06-01T11:00:00+00:00",
        "exercises": [{
            "order": 0,
            "exercise_id": "bench-id",
            "exercise_slug": "bench-press",
            "exercise_name": "Жим лёжа",
            "status": "done",
            "set_logs": [
                {"done": True, "skipped": False, "weight": 100, "reps": 5},
                {"done": False, "skipped": True, "weight": 100, "reps": 5},
                {"done": False, "skipped": False, "weight": 100, "reps": 5},
            ],
        }],
    }


def test_completed_sets_copy_keeps_only_done_sets():
    normalized = _completed_sets_session(_session())
    logs = normalized["exercises"][0]["set_logs"]
    assert len(logs) == 1
    assert logs[0]["done"] is True
    assert normalized["exercises"][0]["status"] == "done"


def test_completed_sets_copy_drops_exercises_without_done_sets():
    session = _session()
    session["exercises"].append({"status": "done", "set_logs": [{"done": False}]})
    normalized = _completed_sets_session(session)
    assert len(normalized["exercises"]) == 1


def test_history_item_does_not_expose_exercises_or_set_logs():
    item = _history_item(_session())
    assert item["id"] == "s1"
    assert item["date"] == "2026-06-01"
    assert "exercises" not in item
    assert "set_logs" not in item
    assert item["stats"]["tonnage"] == 500


@pytest.mark.asyncio
async def test_history_is_paginated_and_owner_only(monkeypatch):
    rows = [_session("s1"), _session("s2")]
    rows[1]["finished_at"] = "2026-06-02T12:00:00+00:00"
    monkeypatch.setattr(server, "db", FakeDB(rows))

    response = await sessions_history(athlete_id=None, athlete=None, page=1, page_size=1,
                                      current_user={"telegram_id": 101})
    assert response["total"] == 2
    assert response["pages"] == 2
    assert response["has_next"] is True
    assert response["items"][0]["id"] == "s2"
    assert "exercises" not in response["items"][0]


@pytest.mark.asyncio
async def test_history_skips_sessions_without_done_exercises(monkeypatch):
    empty = _session("empty")
    empty["exercises"] = [{"order": 0, "status": "skipped", "set_logs": []}]
    monkeypatch.setattr(server, "db", FakeDB([_session("s1"), empty]))

    response = await sessions_history(athlete_id=None, athlete=None, page=1, page_size=20,
                                      current_user={"telegram_id": 101})
    assert response["total"] == 1
    assert [item["id"] for item in response["items"]] == ["s1"]


@pytest.mark.asyncio
async def test_single_session_map_uses_done_sets_and_owner(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        server,
        "db",
        FakeDB([session], [{
            "id": "bench-id", "slug": "bench-press", "name": "Жим лёжа",
            "muscle_groups": ["chest"], "secondary_groups": ["triceps"],
            "is_builtin": True,
        }]),
    )

    response = await session_muscle_map("s1", current_user={"telegram_id": 101})
    assert response["session_id"] == "s1"
    # muscle_engine applies repetition intensity (5 reps => 0.95), so the
    # primary mechanical volume is 100 * 5 * 0.95 = 475 kg. The map totals
    # intentionally sum the distributed primary + secondary region volumes.
    assert response["totals"]["tonnage"] == 1427
    assert response["totals"]["sessions"] == 1
    assert response["regions"]["chest"]["volume_kg"] == 475
    assert response["regions"]["triceps"]["volume_kg"] == 238
    assert response["muscle_load"]["totals"]["volume_kg"] == 475
    assert response["muscle_load"]["version"] == "muscle_load_v1"


@pytest.mark.asyncio
async def test_single_session_map_rejects_unfinished_and_foreign(monkeypatch):
    unfinished = _session("active", status="in_progress")
    foreign = _session("foreign", athlete=202)
    monkeypatch.setattr(server, "db", FakeDB([unfinished, foreign]))

    with pytest.raises(HTTPException) as unfinished_error:
        await session_muscle_map("active", current_user={"telegram_id": 101})
    assert unfinished_error.value.status_code == 404

    with pytest.raises(HTTPException) as foreign_error:
        await session_muscle_map("foreign", current_user={"telegram_id": 101})
    assert foreign_error.value.status_code == 403


@pytest.mark.asyncio
async def test_active_coach_can_read_history_and_map(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        server,
        "db",
        FakeDB(
            [session],
            [{"id": "bench-id", "slug": "bench-press", "muscle_groups": ["chest"],
              "secondary_groups": [], "is_builtin": True}],
            [{"coach_telegram_id": 303, "athlete_telegram_id": 101, "status": "active"}],
        ),
    )
    history = await sessions_history(athlete_id=101, page=1, page_size=20,
                                     current_user={"telegram_id": 303})
    mapped = await session_muscle_map("s1", current_user={"telegram_id": 303})
    assert history["items"][0]["athlete_telegram_id"] == 101
    assert mapped["session_id"] == "s1"


@pytest.mark.asyncio
async def test_inactive_coach_is_denied(monkeypatch):
    monkeypatch.setattr(server, "db", FakeDB([_session()], links=[{
        "coach_telegram_id": 303, "athlete_telegram_id": 101, "status": "revoked",
    }]))
    with pytest.raises(HTTPException) as error:
        await sessions_history(athlete_id=101, current_user={"telegram_id": 303})
    assert error.value.status_code == 403
