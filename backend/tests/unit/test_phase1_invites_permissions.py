"""Unit-тесты Фазы 1: профили прав, слияние оверрайдов, tier-резолвер,
capabilities, _assert_admin, валидация инвайта при redeem (офлайн, без БД)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import server
from server import (
    PERMISSION_KEYS,
    _assert_admin,
    _default_permissions,
    _get_capabilities,
    _merge_permission_overrides,
    _resolve_access_tier,
    _validate_invite_for_redeem,
)


# --- _default_permissions ---------------------------------------------------

def test_standalone_default_all_true():
    perms = _default_permissions("standalone")
    assert set(perms) == set(PERMISSION_KEYS)
    assert all(v is True for v in perms.values())


def test_traincee_default_strength_readonly():
    perms = _default_permissions("coach_managed")
    assert perms["log_strength"] is False
    assert perms["manage_plan"] is False
    assert perms["ai_programs"] is False
    assert perms["log_cardio"] is True
    assert perms["log_nutrition"] is True
    assert perms["view_strength"] is True
    assert perms["view_goals"] is True


def test_default_permissions_covers_all_keys():
    for tier in ("coach_managed", "standalone"):
        assert set(_default_permissions(tier)) == set(PERMISSION_KEYS)


# --- _merge_permission_overrides --------------------------------------------

def test_merge_overrides_applies_valid_keys():
    base = _default_permissions("coach_managed")
    merged = _merge_permission_overrides(base, {"log_strength": True})
    assert merged["log_strength"] is True
    assert merged["manage_plan"] is False  # не задан — остался базовый


def test_merge_overrides_drops_unknown_keys():
    base = _default_permissions("coach_managed")
    merged = _merge_permission_overrides(base, {"hack_admin": True, "log_cardio": False})
    assert "hack_admin" not in merged
    assert merged["log_cardio"] is False


def test_merge_overrides_none_keeps_base():
    base = _default_permissions("standalone")
    assert _merge_permission_overrides(base, None) == base


# --- _resolve_access_tier ----------------------------------------------------

def test_explicit_tier_wins():
    assert _resolve_access_tier({"access_tier": "coach_managed", "roles": ["coach"]}) == "coach_managed"
    assert _resolve_access_tier({"access_tier": "standalone"}) == "standalone"


def test_legacy_coach_role_resolves_standalone():
    assert _resolve_access_tier({"roles": ["coach"]}) == "standalone"
    assert _resolve_access_tier({"roles": ["admin"]}) == "standalone"


def test_legacy_coach_link_resolves_managed():
    assert _resolve_access_tier({"coach_telegram_id": 42}) == "coach_managed"


def test_default_resolves_standalone():
    assert _resolve_access_tier({}) == "standalone"
    assert _resolve_access_tier(None) == "standalone"


# --- _get_capabilities --------------------------------------------------------

def test_capabilities_managed_with_admin_override():
    user = {
        "roles": ["athlete"],
        "access_tier": "coach_managed",
        "permissions": {"log_strength": True},
        "onboarded_at": "2026-10-01T00:00:00+00:00",
        "coach_telegram_id": 77,
    }
    caps = _get_capabilities(user)
    assert caps["access_tier"] == "coach_managed"
    assert caps["permissions"]["log_strength"] is True  # оверрайд
    assert caps["permissions"]["manage_plan"] is False  # базовый
    assert caps["onboarded"] is True
    assert caps["coach_telegram_id"] == 77
    assert "athlete" in caps["roles"]


def test_capabilities_fresh_user_not_onboarded():
    caps = _get_capabilities({"roles": ["athlete"]})
    assert caps["onboarded"] is False
    assert caps["access_tier"] == "standalone"


def test_capabilities_coach_is_always_onboarded():
    caps = _get_capabilities({"roles": ["coach"]})
    assert caps["onboarded"] is True


def test_capabilities_roles_always_include_athlete():
    caps = _get_capabilities({"roles": []})
    assert caps["roles"] == ["athlete"]


def test_capabilities_client_preview_keeps_permissions():
    caps = _get_capabilities({"roles": ["coach"], "active_mode": "client"})
    assert caps["active_mode"] == "client"
    assert caps["client_preview"] is True
    # Предпросмотр — только UI: права тренера не урезаются.
    assert caps["permissions"]["log_strength"] is True
    assert caps["access_tier"] == "standalone"


def test_capabilities_defaults_and_unknown_mode():
    caps = _get_capabilities({"roles": ["athlete"]})
    assert caps["active_mode"] == "athlete"
    assert caps["client_preview"] is False
    assert _get_capabilities({"roles": ["athlete"], "active_mode": "nope"})["active_mode"] == "athlete"


# --- _assert_admin -------------------------------------------------------------

def test_assert_admin_passes_for_admin():
    _assert_admin({"roles": ["admin", "athlete"]})


@pytest.mark.parametrize("roles", [["athlete"], ["coach"], []])
def test_assert_admin_rejects_non_admin(roles):
    with pytest.raises(HTTPException) as e:
        _assert_admin({"roles": roles})
    assert e.value.status_code == 403


def test_assert_admin_rejects_none():
    with pytest.raises(HTTPException) as e:
        _assert_admin(None)
    assert e.value.status_code == 403


# --- _validate_invite_for_redeem ------------------------------------------------

def _invite(**kw):
    base = {
        "id": "inv-1", "code": "TWB-ABC123", "kind": "coach_client",
        "status": "active", "uses": 0, "max_uses": 1, "expires_at": None,
    }
    base.update(kw)
    return base


def test_valid_invite_passes():
    inv = _validate_invite_for_redeem(_invite())
    assert inv["code"] == "TWB-ABC123"


def test_missing_invite_404():
    with pytest.raises(HTTPException) as e:
        _validate_invite_for_redeem(None)
    assert e.value.status_code == 404


def test_revoked_invite_rejected():
    with pytest.raises(HTTPException) as e:
        _validate_invite_for_redeem(_invite(status="revoked"))
    assert e.value.status_code == 400
    assert "отозван" in e.value.detail


def test_used_invite_rejected():
    with pytest.raises(HTTPException) as e:
        _validate_invite_for_redeem(_invite(uses=1, max_uses=1))
    assert e.value.status_code == 400
    assert "использован" in e.value.detail


def test_multi_use_invite_with_capacity_passes():
    inv = _validate_invite_for_redeem(_invite(uses=2, max_uses=3))
    assert inv["uses"] == 2


def test_expired_invite_rejected():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with pytest.raises(HTTPException) as e:
        _validate_invite_for_redeem(_invite(expires_at=past))
    assert e.value.status_code == 400
    assert "просрочен" in e.value.detail


def test_future_expiry_passes_and_naive_expiry_handled():
    future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    _validate_invite_for_redeem(_invite(expires_at=future))
    naive_future = (datetime.now(timezone.utc) + timedelta(days=7)).replace(tzinfo=None).isoformat()
    _validate_invite_for_redeem(_invite(expires_at=naive_future))


def test_bad_expiry_format_ignored():
    _validate_invite_for_redeem(_invite(expires_at="not-a-date"))


# --- switch_user_mode: режим «Клиент» ---------------------------------------


class _UsersCollection:
    def __init__(self, doc):
        self.doc = dict(doc)

    async def find_one(self, query, projection=None):
        if self.doc.get("telegram_id") != query.get("telegram_id"):
            return None
        return {k: v for k, v in self.doc.items() if k != "password_hash"}

    async def update_one(self, query, update):
        self.doc.update(update.get("$set") or {})
        return SimpleNamespace(matched_count=1)


@pytest.mark.asyncio
async def test_switch_mode_client_is_ui_only(monkeypatch):
    users = _UsersCollection({"telegram_id": 5, "roles": ["coach", "athlete"], "active_mode": "coach"})
    monkeypatch.setattr(server, "db", SimpleNamespace(users=users))

    updated = await server.switch_user_mode(
        5, server.ModeReq(mode="client"), current={"telegram_id": 5}
    )

    assert updated["active_mode"] == "client"
    assert users.doc["active_mode"] == "client"
    # Режим клиента не выдаёт и не отнимает роли и не создаёт инвайт.
    assert users.doc["roles"] == ["athlete", "coach"]
    assert "invite_code" not in users.doc


@pytest.mark.asyncio
async def test_switch_mode_rejects_unknown_and_foreign(monkeypatch):
    users = _UsersCollection({"telegram_id": 5, "roles": ["athlete"]})
    monkeypatch.setattr(server, "db", SimpleNamespace(users=users))

    with pytest.raises(HTTPException) as bad_mode:
        await server.switch_user_mode(5, server.ModeReq(mode="admin"), current={"telegram_id": 5})
    assert bad_mode.value.status_code == 400

    with pytest.raises(HTTPException) as foreign:
        await server.switch_user_mode(6, server.ModeReq(mode="client"), current={"telegram_id": 5})
    assert foreign.value.status_code == 403
