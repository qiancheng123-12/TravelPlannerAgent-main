"""LangChain Tools - 高德地图工具集"""

from typing import Type, Optional, List
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from ...services.amap_service import get_amap_service


# ===========================================
# Tool Input Schemas
# ===========================================

class SearchPOIInput(BaseModel):
    """搜索 POI 工具输入"""
    keywords: str = Field(..., description="搜索关键词，如'景点'、'博物馆'")
    city: str = Field(..., description="城市名称")
    citylimit: bool = Field(default=True, description="是否限制在城市范围内")


class GetWeatherInput(BaseModel):
    """获取天气工具输入"""
    city: str = Field(..., description="城市名称")


class SearchHotelInput(BaseModel):
    """搜索酒店工具输入"""
    city: str = Field(..., description="城市名称")
    hotel_type: str = Field(default="酒店", description="酒店类型，如'经济型酒店'、'豪华酒店'")


class GeocodeInput(BaseModel):
    """地理编码工具输入"""
    address: str = Field(..., description="地址")
    city: Optional[str] = Field(default=None, description="城市")


# ===========================================
# Tools
# ===========================================

class SearchPOITool(BaseTool):
    """搜索 POI 工具"""

    name: str = "search_poi"
    description: str = "搜索指定城市的景点、餐厅、商场等兴趣点(POI)。输入关键词和城市名称，返回相关POI列表。"
    args_schema: Type[BaseModel] = SearchPOIInput

    async def _arun(self, keywords: str, city: str, citylimit: bool = True) -> str:
        """异步执行"""
        amap = get_amap_service()
        pois = await amap.search_poi(keywords, city, citylimit)

        if not pois:
            return f"未找到 {city} 的 {keywords} 相关信息"

        result = f"找到 {len(pois)} 个 {keywords} 相关的POI:\n\n"
        for i, poi in enumerate(pois[:10], 1):
            result += f"{i}. {poi.name}\n"
            result += f"   地址: {poi.address}\n"
            result += f"   坐标: ({poi.location.longitude}, {poi.location.latitude})\n"
            if poi.rating:
                result += f"   评分: {poi.rating}\n"
            result += "\n"

        return result

    def _run(self, keywords: str, city: str, citylimit: bool = True) -> str:
        """同步执行"""
        import asyncio
        return asyncio.run(self._arun(keywords, city, citylimit))


class GetWeatherTool(BaseTool):
    """获取天气工具"""

    name: str = "get_weather"
    description: str = "获取指定城市的天气预报信息。输入城市名称，返回未来几天的天气情况。"
    args_schema: Type[BaseModel] = GetWeatherInput

    async def _arun(self, city: str) -> str:
        """异步执行"""
        amap = get_amap_service()
        weathers = await amap.get_weather(city)

        if not weathers:
            return f"未找到 {city} 的天气信息"

        result = f"{city} 天气预报:\n\n"
        for w in weathers:
            result += f"日期: {w.date}\n"
            result += f"白天: {w.day_weather} {w.day_temp}°C\n"
            result += f"夜间: {w.night_weather} {w.night_temp}°C\n"
            result += f"风向: {w.wind_direction} 风力: {w.wind_power}级\n\n"

        return result

    def _run(self, city: str) -> str:
        """同步执行"""
        import asyncio
        return asyncio.run(self._arun(city))


class SearchHotelTool(BaseTool):
    """搜索酒店工具"""

    name: str = "search_hotel"
    description: str = "搜索指定城市的酒店信息。输入城市名称和酒店类型，返回酒店列表。"
    args_schema: Type[BaseModel] = SearchHotelInput

    async def _arun(self, city: str, hotel_type: str = "酒店") -> str:
        """异步执行"""
        amap = get_amap_service()
        hotels = await amap.search_hotels(city, hotel_type)

        if not hotels:
            return f"未找到 {city} 的 {hotel_type} 相关酒店"

        result = f"找到 {len(hotels)} 家 {hotel_type}:\n\n"
        for i, hotel in enumerate(hotels[:5], 1):
            result += f"{i}. {hotel.name}\n"
            result += f"   地址: {hotel.address}\n"
            if hotel.rating:
                result += f"   评分: {hotel.rating}\n"
            result += "\n"

        return result

    def _run(self, city: str, hotel_type: str = "酒店") -> str:
        """同步执行"""
        import asyncio
        return asyncio.run(self._arun(city, hotel_type))


class GeocodeTool(BaseTool):
    """地理编码工具"""

    name: str = "geocode"
    description: str = "将地址转换为经纬度坐标。输入地址，返回坐标信息。"
    args_schema: Type[BaseModel] = GeocodeInput

    async def _arun(self, address: str, city: Optional[str] = None) -> str:
        """异步执行"""
        amap = get_amap_service()
        location = await amap.geocode(address, city)

        if not location:
            return f"无法解析地址: {address}"

        return f"地址 '{address}' 的坐标: 经度 {location.longitude}, 纬度 {location.latitude}"

    def _run(self, address: str, city: Optional[str] = None) -> str:
        """同步执行"""
        import asyncio
        return asyncio.run(self._arun(address, city))


# ===========================================
# Tool Collection
# ===========================================

def get_amap_tools() -> List[BaseTool]:
    """获取所有高德地图工具"""
    return [
        SearchPOITool(),
        GetWeatherTool(),
        SearchHotelTool(),
        GeocodeTool()
    ]
