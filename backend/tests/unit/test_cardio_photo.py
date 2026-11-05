"""Offline tests for the cardio photo endpoint contract."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

import server


@pytest.mark.asyncio
async def test_cardio_photo_rejects_non_dict_vision_result():
    upload = UploadFile(file=__import__("io").BytesIO(b"image"), filename="console.jpg", headers={"content-type": "image/jpeg"})
    with patch.object(server, "_rate_limit"), patch.object(server, "_assert_can_log_permission"), \
         patch.object(server, "_ai_chat_vision", new=AsyncMock(return_value="[]")), \
         patch.object(server, "_extract_json", return_value=[]):
        with pytest.raises(HTTPException) as exc:
            await server.cardio_parse_photo(upload, {"telegram_id": 1})
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_cardio_photo_does_not_calculate_missing_calories():
    upload = UploadFile(file=__import__("io").BytesIO(b"image"), filename="console.jpg", headers={"content-type": "image/jpeg"})
    vision = {"type": "treadmill", "duration_sec": 1800, "distance_km": 3.0}
    with patch.object(server, "_rate_limit"), patch.object(server, "_assert_can_log_permission"), \
         patch.object(server, "_ai_chat_vision", new=AsyncMock(return_value="{}")), \
         patch.object(server, "_extract_json", return_value=vision), \
         patch.object(server, "cardio_kcal", side_effect=AssertionError("must not estimate in draft")):
        result = await server.cardio_parse_photo(upload, {"telegram_id": 1})
    assert result["confidence"] == "vision"
    assert result["draft"]["duration_sec"] == 1800
    assert "calories" not in result["draft"]
    assert result["draft"]["source"] == "photo"


@pytest.mark.asyncio
async def test_cardio_photo_empty_ocr_has_low_confidence():
    upload = UploadFile(file=__import__("io").BytesIO(b"image"), filename="console.jpg", headers={"content-type": "image/jpeg"})
    with patch.object(server, "_rate_limit"), patch.object(server, "_assert_can_log_permission"), \
         patch.object(server, "_ai_chat_vision", new=AsyncMock(return_value="{}")), \
         patch.object(server, "_extract_json", return_value={}):
        result = await server.cardio_parse_photo(upload, {"telegram_id": 1})
    assert result["confidence"] == "low"
    assert result["draft"] == {"source": "photo"}


@pytest.mark.asyncio
async def test_cardio_photo_reads_at_most_limit_plus_one():
    class LimitedUpload:
        filename = "console.jpg"
        content_type = "image/jpeg"

        async def read(self, size=-1):
            self.size = size
            return b"image"

    upload = LimitedUpload()
    with patch.object(server, "_rate_limit"), patch.object(server, "_assert_can_log_permission"), \
         patch.object(server, "_ai_chat_vision", new=AsyncMock(return_value="{}")), \
         patch.object(server, "_extract_json", return_value={}):
        await server.cardio_parse_photo(upload, {"telegram_id": 1})
    assert upload.size == 8 * 1024 * 1024 + 1
