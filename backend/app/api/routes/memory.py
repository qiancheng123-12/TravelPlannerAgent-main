"""用户长期记忆管理 API。"""

from fastapi import APIRouter, HTTPException

from ...models.schemas import MemoryFactUpdate, MemorySettingsUpdate, MemoryTripSave
from ...services.memory_service import get_long_term_memory_service, get_memory_service


router = APIRouter(prefix="/memory", tags=["长期记忆"])


@router.get("/profile/{user_id}")
async def get_memory_profile(user_id: str):
    repository = get_memory_service()
    return {
        "user_id": user_id,
        "enabled": await repository.memory_enabled(user_id),
        "facts": await repository.list_facts(user_id),
        "trips": await repository.list_trips(user_id),
    }


@router.patch("/profile/{user_id}/settings")
async def update_memory_settings(user_id: str, payload: MemorySettingsUpdate):
    await get_memory_service().set_memory_enabled(user_id, payload.enabled)
    return {"success": True, "enabled": payload.enabled}


@router.patch("/profile/{user_id}/facts/{memory_id}")
async def update_memory_fact(user_id: str, memory_id: str, payload: MemoryFactUpdate):
    try:
        fact = await get_long_term_memory_service().update_fact(
            user_id, memory_id, payload.value, payload.summary
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="记忆不存在") from exc
    return {"success": True, "fact": fact}


@router.delete("/profile/{user_id}/facts/{memory_id}")
async def delete_memory_fact(user_id: str, memory_id: str):
    deleted = await get_memory_service().delete_fact(user_id, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"success": True}


@router.post("/profile/{user_id}/trips")
async def save_memory_trip(user_id: str, payload: MemoryTripSave):
    """将浏览器仍保留的当前行程补写进 SQLite 历史。"""
    if not str(payload.plan.get("city") or "").strip():
        raise HTTPException(status_code=422, detail="行程缺少目的地")
    repository = get_memory_service()
    await repository.record_trip(user_id, payload.session_id, payload.plan)
    trips = await repository.list_trips(user_id)
    saved = next(
        (
            trip for trip in trips
            if trip["session_id"] == payload.session_id
            and trip["city"] == str(payload.plan.get("city") or "").strip()
            and (trip.get("start_date") or "") == (payload.plan.get("start_date") or "")
            and (trip.get("end_date") or "") == (payload.plan.get("end_date") or "")
        ),
        None,
    )
    return {"success": True, "trip": saved}


@router.get("/profile/{user_id}/trips/{trip_id}")
async def get_memory_trip(user_id: str, trip_id: str):
    try:
        trip = await get_memory_service().get_trip(user_id, trip_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="历史行程不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return trip


@router.delete("/profile/{user_id}/trips/{trip_id}")
async def delete_memory_trip(user_id: str, trip_id: str):
    deleted = await get_memory_service().delete_trip(user_id, trip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="历史行程不存在")
    return {"success": True}


@router.post("/profile/{user_id}/trips/import-legacy")
async def import_legacy_memory_trips(user_id: str):
    repository = get_memory_service()
    result = await repository.import_legacy_trips(user_id)
    return {
        "success": True,
        **result,
        "trips": await repository.list_trips(user_id),
    }


@router.delete("/profile/{user_id}")
async def clear_memory_profile(user_id: str):
    deleted = await get_memory_service().clear_profile(user_id)
    return {"success": True, "deleted": deleted}
