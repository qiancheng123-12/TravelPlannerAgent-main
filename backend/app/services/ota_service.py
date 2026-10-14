"""OTA 沙箱适配层：报价 -> 锁单 -> 用户确认 -> 模拟出票。"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx

from ..core.config import get_settings


class OTASandboxService:
    def __init__(self):
        self.settings = get_settings()
        self._offers: Dict[str, Dict[str, Any]] = {}
        self._holds: Dict[str, Dict[str, Any]] = {}
        self._bookings: Dict[str, Dict[str, Any]] = {}

    @property
    def mode(self) -> str:
        return "remote_sandbox" if self.settings.ota_sandbox_base_url else "mock_sandbox"

    async def quote(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.settings.ota_sandbox_base_url:
            result = await self._remote("POST", "/offers/search", payload)
            return list(result.get("offers", []))

        city = payload["city"]
        hotel_hint = payload.get("hotel_name") or f"{city}中心酒店"
        seed = int(hashlib.sha1(f"{city}:{payload['check_in']}".encode()).hexdigest()[:6], 16)
        base = 260 + seed % 240
        names = [hotel_hint, f"{city}舒适酒店", f"{city}精选酒店"]
        offers = []
        for index, name in enumerate(dict.fromkeys(names)):
            price = base + index * 80
            if payload.get("max_price") and price > payload["max_price"]:
                continue
            offer_id = f"offer_{uuid.uuid4().hex[:12]}"
            offer = {
                "offer_id": offer_id,
                "provider": "YuanYou OTA Sandbox",
                "hotel_name": name,
                "room_name": "高级大床房" if index == 0 else "标准双床房",
                "check_in": payload["check_in"],
                "check_out": payload["check_out"],
                "guests": payload.get("guests", 1),
                "currency": "CNY",
                "total_price": price,
                "refundable": index != 2,
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            }
            self._offers[offer_id] = offer
            offers.append(offer)
        return offers

    async def hold(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.settings.ota_sandbox_base_url:
            return await self._remote("POST", "/orders/hold", payload)
        offer = self._offers.get(payload["offer_id"])
        if not offer:
            raise ValueError("报价不存在或已过期，请重新查询")
        hold_id = f"hold_{uuid.uuid4().hex[:12]}"
        hold = {
            "hold_id": hold_id,
            "session_id": payload["session_id"],
            "offer": offer,
            "guest_name": payload["guest_name"],
            "contact_phone_masked": self._mask_phone(payload["contact_phone"]),
            "status": "held",
            "payment_required": False,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            "confirmation_message": f"将以 ¥{offer['total_price']} 预订 {offer['hotel_name']}，请确认。",
        }
        self._holds[hold_id] = {**hold, "contact_phone": payload["contact_phone"]}
        return {key: value for key, value in hold.items() if key != "contact_phone"}

    async def confirm(self, session_id: str, hold_id: str, user_confirmed: bool) -> Dict[str, Any]:
        if not user_confirmed:
            return {
                "status": "awaiting_user_confirmation",
                "hold_id": hold_id,
                "message": "尚未得到明确确认，系统不会创建订单。",
            }
        if self.settings.ota_sandbox_base_url:
            return await self._remote("POST", "/orders/confirm", {
                "session_id": session_id, "hold_id": hold_id, "user_confirmed": True,
            })
        hold = self._holds.get(hold_id)
        if not hold or hold["session_id"] != session_id:
            raise ValueError("锁单不存在或不属于当前会话")
        expires_at = datetime.fromisoformat(hold["expires_at"])
        if expires_at < datetime.now(timezone.utc):
            hold["status"] = "expired"
            raise ValueError("锁单已过期，请重新报价")

        idempotency_key = hashlib.sha256(f"{session_id}:{hold_id}".encode()).hexdigest()[:20]
        existing = next((item for item in self._bookings.values() if item["idempotency_key"] == idempotency_key), None)
        if existing:
            return existing
        booking_id = f"book_{uuid.uuid4().hex[:12]}"
        booking = {
            "booking_id": booking_id,
            "sandbox": True,
            "status": "confirmed",
            "idempotency_key": idempotency_key,
            "confirmation_code": f"YY{uuid.uuid4().hex[:8].upper()}",
            "offer": hold["offer"],
            "guest_name": hold["guest_name"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": "OTA 沙箱订单已确认（未发生真实支付）。",
        }
        hold["status"] = "confirmed"
        self._bookings[booking_id] = booking
        return booking

    async def get_booking(self, booking_id: str) -> Dict[str, Any]:
        if self.settings.ota_sandbox_base_url:
            return await self._remote("GET", f"/orders/{booking_id}", None)
        booking = self._bookings.get(booking_id)
        if not booking:
            raise ValueError("订单不存在")
        return booking

    async def cancel(self, booking_id: str) -> Dict[str, Any]:
        if self.settings.ota_sandbox_base_url:
            return await self._remote("POST", f"/orders/{booking_id}/cancel", {})
        booking = await self.get_booking(booking_id)
        booking["status"] = "cancelled"
        booking["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        return booking

    async def _remote(self, method: str, path: str, payload: Dict[str, Any] | None) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.ota_sandbox_api_key}"}
        async with httpx.AsyncClient(timeout=self.settings.ota_sandbox_timeout) as client:
            response = await client.request(
                method,
                f"{self.settings.ota_sandbox_base_url.rstrip('/')}{path}",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _mask_phone(phone: str) -> str:
        return f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else "***"


_ota_service = OTASandboxService()


def get_ota_service() -> OTASandboxService:
    return _ota_service
