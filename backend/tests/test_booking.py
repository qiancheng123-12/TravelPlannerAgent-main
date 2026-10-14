import pytest

from app.services.ota_service import OTASandboxService


@pytest.mark.asyncio
async def test_ota_mock_requires_explicit_confirmation(monkeypatch):
    service = OTASandboxService()
    monkeypatch.setattr(service.settings, "ota_sandbox_base_url", "")
    offers = await service.quote({
        "session_id": "booking-test",
        "city": "北京",
        "check_in": "2026-10-01",
        "check_out": "2026-10-03",
        "guests": 1,
    })
    hold = await service.hold({
        "session_id": "booking-test",
        "offer_id": offers[0]["offer_id"],
        "guest_name": "测试用户",
        "contact_phone": "13800138000",
    })

    pending = await service.confirm("booking-test", hold["hold_id"], False)
    assert pending["status"] == "awaiting_user_confirmation"

    confirmed = await service.confirm("booking-test", hold["hold_id"], True)
    assert confirmed["status"] == "confirmed"
    assert confirmed["sandbox"] is True
    assert confirmed["confirmation_code"]

