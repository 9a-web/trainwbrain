"""Unit-тесты чистых хелперов аутентификации (без БД/сети)."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from auth import (
    hash_password,
    verify_password,
    validate_telegram_init_data,
    synthetic_telegram_id,
    new_session_token,
    session_expiry,
)

BOT_TOKEN = "123456:TEST_TOKEN"


def _make_init_data(bot_token: str, user: dict) -> str:
    data = {
        "auth_date": str(int(time.time())),
        "query_id": "AAExampleQuery",
        "user": json.dumps(user),
    }
    check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


def test_password_hash_roundtrip():
    h = hash_password("s3cret-password")
    assert h != "s3cret-password"
    assert verify_password("s3cret-password", h)
    assert not verify_password("wrong", h)


def test_verify_password_handles_bad_hash():
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_telegram_init_data_valid():
    user = {"id": 42, "first_name": "Иван", "username": "ivan"}
    parsed = validate_telegram_init_data(_make_init_data(BOT_TOKEN, user), BOT_TOKEN)
    assert parsed is not None
    assert json.loads(parsed["user"])["id"] == 42


def test_telegram_init_data_bad_token_rejected():
    user = {"id": 42, "first_name": "Иван"}
    init = _make_init_data(BOT_TOKEN, user)
    assert validate_telegram_init_data(init, "999:WRONG") is None


def test_telegram_init_data_tampered_rejected():
    user = {"id": 42, "first_name": "Иван"}
    init = _make_init_data(BOT_TOKEN, user).replace("id%22%3A+42", "id%22%3A+43")
    assert validate_telegram_init_data(init, BOT_TOKEN) is None


def test_telegram_init_data_empty_inputs():
    assert validate_telegram_init_data("", BOT_TOKEN) is None
    assert validate_telegram_init_data("x=1", "") is None


def test_expired_init_data_rejected():
    user = {"id": 1, "first_name": "A"}
    data = {
        "auth_date": str(int(time.time()) - 10_000),
        "user": json.dumps(user),
    }
    check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    assert validate_telegram_init_data(urlencode(data), BOT_TOKEN, max_age_sec=60) is None


def test_session_token_unique_and_opaque():
    a, b = new_session_token(), new_session_token()
    assert a != b and len(a) > 20


def test_synthetic_telegram_id_range():
    for _ in range(50):
        assert synthetic_telegram_id() >= 900_000_000_000


def test_session_expiry_is_future():
    from datetime import datetime, timezone
    assert session_expiry() > datetime.now(timezone.utc)
