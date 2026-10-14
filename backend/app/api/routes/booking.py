"""OTA 沙箱交易闭环 API。"""

from fastapi import APIRouter, HTTPException

from ...models.schemas import BookingConfirmRequest, BookingHoldRequest, BookingQuoteRequest
from ...services.ota_service import get_ota_service

router = APIRouter(prefix="/booking", tags=["OTA 沙箱预订"])


@router.post("/quotes")
async def get_quotes(request: BookingQuoteRequest):
    try:
        offers = await get_ota_service().quote(request.model_dump())
        return {"mode": get_ota_service().mode, "offers": offers, "count": len(offers)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OTA 报价失败: {exc}") from exc


@router.post("/holds")
async def hold_offer(request: BookingHoldRequest):
    try:
        hold = await get_ota_service().hold(request.model_dump())
        return {"mode": get_ota_service().mode, "hold": hold, "requires_confirmation": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/confirm")
async def confirm_booking(request: BookingConfirmRequest):
    try:
        booking = await get_ota_service().confirm(
            request.session_id, request.hold_id, request.user_confirmed
        )
        return {"mode": get_ota_service().mode, "booking": booking}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{booking_id}")
async def get_booking(booking_id: str):
    try:
        return await get_ota_service().get_booking(booking_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{booking_id}/cancel")
async def cancel_booking(booking_id: str):
    try:
        return await get_ota_service().cancel(booking_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
