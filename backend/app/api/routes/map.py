"""地图服务 API 路由"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from typing import Optional

from ...services.amap_service import get_amap_service

router = APIRouter(prefix="/map", tags=["地图服务"])


@router.get("/poi")
async def search_poi(
    keywords: str = Query(..., description="搜索关键词"),
    city: str = Query(..., description="城市")
):
    """搜索 POI"""
    amap = get_amap_service()
    pois = await amap.search_poi(keywords, city)

    return {
        "success": True,
        "data": [poi.model_dump() for poi in pois]
    }


@router.get("/weather")
async def get_weather(city: str = Query(..., description="城市")):
    """获取天气"""
    amap = get_amap_service()
    weather = await amap.get_weather(city)

    return {
        "success": True,
        "data": [w.model_dump() for w in weather]
    }


@router.get("/hotels")
async def search_hotels(
    city: str = Query(..., description="城市"),
    hotel_type: str = Query(default="酒店", description="酒店类型")
):
    """搜索酒店"""
    amap = get_amap_service()
    hotels = await amap.search_hotels(city, hotel_type)

    return {
        "success": True,
        "data": [h.model_dump() for h in hotels]
    }


@router.get("/staticmap")
async def get_static_map(
    city: str = Query(..., description="城市"),
    markers: Optional[str] = Query(default=None, description="标记点")
):
    """获取静态地图图片（用于导出）"""
    amap = get_amap_service()

    image_data = await amap.get_static_map(city, markers)

    return Response(
        content=image_data,
        media_type="image/png"
    )


@router.get("/geocode")
async def geocode(
    address: str = Query(..., description="地址"),
    city: Optional[str] = Query(default=None, description="城市")
):
    """地理编码"""
    amap = get_amap_service()
    location = await amap.geocode(address, city)

    if not location:
        raise HTTPException(status_code=404, detail="无法解析地址")

    return {
        "success": True,
        "data": location.model_dump()
    }
