"""行程规划 Agent 节点 - 主 Agent"""

import json
from typing import Dict, Any
from datetime import datetime, timedelta
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from ...core.llm import get_llm
from ...models.schemas import (
    AgentState, AgentStep, NodeType, TripStatus,
    TripPlan, DayPlan, Attraction, Meal, Location, Hotel, Budget
)


PLANNER_AGENT_PROMPT = """你是一个专业的旅行规划师。

根据以下信息，生成一份详细的旅行计划。

## 基本信息
- 城市: {city}
- 出发地: {origin}
- 日期范围: {start_date} 至 {end_date}
- 旅行天数: {travel_days} 天
- 出行人数: {guests} 人
- 交通方式: {transportation}
- 住宿偏好: {accommodation}
- 用户偏好: {preferences}
- 预算范围: {budget}
- 额外要求: {free_text_input}

## 可用景点 (POI)
{pois_info}

## 天气预报
{weather_info}

## 可用酒店
{hotels_info}

## RAG 知识库检索结果
{rag_context}

## 任务要求
1. 从可用景点中选择合适的景点，每天安排 2-3 个
2. 使用景点列表中提供的真实坐标
3. 为每天安排早餐、午餐、晚餐
4. 推荐合适的酒店
5. 计算详细预算（景点、酒店、餐饮、交通）
6. 在总体建议中吸收 RAG 知识，但不要虚构知识库没有提供的事实

请严格按照以下 JSON 格式输出，不要添加任何其他内容:

{{
  "city": "城市名称",
  "start_date": "开始日期",
  "end_date": "结束日期",
  "days": [
    {{
      "date": "日期",
      "day_index": 0,
      "description": "当日行程描述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {{
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {{"longitude": 0, "latitude": 0}},
        "price_range": "价格范围",
        "rating": "评分",
        "type": "酒店类型",
        "estimated_cost": 300
      }},
      "attractions": [
        {{
          "name": "景点名称",
          "address": "景点地址",
          "location": {{"longitude": 0, "latitude": 0}},
          "visit_duration": 120,
          "description": "景点描述",
          "category": "景点类别",
          "ticket_price": 60
        }}
      ],
      "meals": [
        {{"type": "breakfast", "name": "早餐名称", "description": "描述", "estimated_cost": 30}},
        {{"type": "lunch", "name": "午餐名称", "description": "描述", "estimated_cost": 50}},
        {{"type": "dinner", "name": "晚餐名称", "description": "描述", "estimated_cost": 80}}
      ]
    }}
  ],
  "weather_info": [],
  "overall_suggestions": "总体建议",
  "budget": {{
    "total_attractions": 0,
    "total_hotels": 0,
    "total_meals": 0,
    "total_transportation": 0,
    "total": 0
  }}
}}
"""


async def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    行程规划节点 - 主 Agent

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    agent_state = AgentState(**state)

    step = AgentStep(
        node=NodeType.PLANNER.value,
        status="running",
        input={
            "pois_count": len(agent_state.pois),
            "weather_count": len(agent_state.weather),
            "hotels_count": len(agent_state.hotels)
        }
    )

    try:
        # 准备上下文信息
        pois_info = _format_pois(agent_state.pois)
        weather_info = _format_weather(agent_state.weather)
        hotels_info = _format_hotels(agent_state.hotels)

        # 调用 LLM 生成行程
        llm = get_llm(agent_state.llm_provider, temperature=0.7)

        prompt = ChatPromptTemplate.from_template(PLANNER_AGENT_PROMPT)
        chain = prompt | llm

        response = await chain.ainvoke({
            "city": agent_state.city,
            "origin": agent_state.origin,
            "start_date": agent_state.start_date,
            "end_date": agent_state.end_date,
            "travel_days": agent_state.travel_days,
            "guests": agent_state.guests,
            "transportation": agent_state.transportation,
            "accommodation": agent_state.accommodation,
            "preferences": ", ".join(agent_state.preferences) if agent_state.preferences else "无特殊偏好",
            "budget": (
                f"{agent_state.budget[0]} - {agent_state.budget[1]} 元"
                if agent_state.budget and len(agent_state.budget) == 2
                else "无明确限制"
            ),
            "free_text_input": agent_state.free_text_input or "无",
            "pois_info": pois_info,
            "weather_info": weather_info,
            "hotels_info": hotels_info,
            "rag_context": agent_state.rag_context or "暂无补充知识",
        })

        # 解析 JSON 响应
        trip_plan = _parse_response(response.content, agent_state)
        trip_plan.origin = agent_state.origin
        trip_plan.guests = agent_state.guests
        if not trip_plan.weather_info:
            trip_plan.weather_info = agent_state.weather

        step.status = "completed"
        step.output = {"plan_generated": True}
        step.duration_ms = 0

        agent_state.itinerary = trip_plan
        agent_state.steps.append(step)
        agent_state.current_node = NodeType.PLANNER.value
        agent_state.status = TripStatus.NEED_CONFIRM  # 需要用户确认
        agent_state.need_human_review = True
        agent_state.updated_at = datetime.now()

        return agent_state.model_dump(mode="json")

    except Exception as e:
        step.status = "failed"
        step.error = str(e)
        agent_state.errors.append(f"行程规划失败: {str(e)}")
        agent_state.steps.append(step)

        # 尝试生成 fallback 计划
        agent_state.itinerary = _create_fallback_plan(agent_state)
        if agent_state.itinerary:
            agent_state.status = TripStatus.NEED_CONFIRM
            agent_state.need_human_review = True

        return agent_state.model_dump(mode="json")


def _format_pois(pois: list) -> str:
    """格式化 POI 信息"""
    if not pois:
        return "暂无景点信息"

    lines = []
    for i, poi in enumerate(pois[:15], 1):
        lines.append(f"{i}. {poi.name}")
        lines.append(f"   地址: {poi.address}")
        lines.append(f"   坐标: ({poi.location.longitude}, {poi.location.latitude})")
        if poi.rating:
            lines.append(f"   评分: {poi.rating}")
        lines.append("")

    return "\n".join(lines)


def _format_weather(weather: list) -> str:
    """格式化天气信息"""
    if not weather:
        return "暂无天气信息"

    lines = []
    for w in weather:
        lines.append(f"{w.date}: {w.day_weather} {w.day_temp}°C / {w.night_weather} {w.night_temp}°C")

    return "\n".join(lines)


def _format_hotels(hotels: list) -> str:
    """格式化酒店信息"""
    if not hotels:
        return "暂无酒店信息"

    lines = []
    for i, h in enumerate(hotels[:5], 1):
        lines.append(f"{i}. {h.name} - {h.address}")
        if h.rating:
            lines.append(f"   评分: {h.rating}")

    return "\n".join(lines)


def _parse_response(response: str, state: AgentState) -> TripPlan:
    """解析 LLM 响应"""
    # 提取 JSON
    json_str = response

    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        if end > start:
            json_str = response[start:end].strip()
    elif "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        if end > start:
            json_str = response[start:end].strip()

    # 查找 JSON 对象
    if "{" in json_str:
        start = json_str.find("{")
        brace_count = 0
        end = start
        for i, char in enumerate(json_str[start:], start):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        json_str = json_str[start:end]

    data = json.loads(json_str)
    return TripPlan(**data)


def _create_fallback_plan(state: AgentState) -> TripPlan:
    """创建 fallback 计划"""
    start_date = datetime.strptime(state.start_date, "%Y-%m-%d")

    # 使用真实 POI 数据
    attractions = []
    max_attractions = max(3, state.travel_days * 3)
    for poi in state.pois[:max_attractions]:
        if not poi.location:
            continue
        attractions.append(Attraction(
            name=poi.name,
            address=poi.address,
            location=poi.location,
            visit_duration=120,
            description=f"{state.city}推荐景点",
            category=poi.category or "景点"
        ))

    if not attractions:
        attractions = [Attraction(
            name=f"{state.city}市中心景点",
            address=f"{state.city}市中心",
            location=Location(longitude=116.4, latitude=39.9),
            visit_duration=120,
            description="推荐景点"
        )]

    selected_hotel = state.hotels[0] if state.hotels else None
    days = []
    for i in range(state.travel_days):
        current_date = start_date + timedelta(days=i)
        day_attractions = attractions[i * 3:(i + 1) * 3]
        if not day_attractions and i == 0:
            day_attractions = attractions[:3]
        days.append(DayPlan(
            date=current_date.strftime("%Y-%m-%d"),
            day_index=i,
            description=f"第{i+1}天 - {state.city}游览",
            transportation=state.transportation,
            accommodation=state.accommodation,
            hotel=selected_hotel,
            attractions=day_attractions,
            meals=[
                Meal(type="breakfast", name="早餐", description="当地特色早餐", estimated_cost=30),
                Meal(type="lunch", name="午餐", description="当地特色午餐", estimated_cost=50),
                Meal(type="dinner", name="晚餐", description="当地特色晚餐", estimated_cost=80)
            ]
        ))

    hotel_cost = 0
    meal_cost = 160 * state.travel_days
    attraction_cost = sum(
        item.ticket_price or 0
        for day in days
        for item in day.attractions
    )
    if state.hotels:
        hotel_cost = (state.hotels[0].estimated_cost or 0) * max(0, state.travel_days - 1)
    transportation_cost = 60 * state.travel_days

    plan = TripPlan(
        city=state.city,
        origin=state.origin,
        guests=state.guests,
        start_date=state.start_date,
        end_date=state.end_date,
        days=days,
        weather_info=state.weather,
        overall_suggestions=(
            f"这是{state.city}的{state.travel_days}天旅行计划。"
            "当前使用了降级模板，请在出发前核验开放时间与实时交通。"
        ),
        budget=Budget(
            total_attractions=attraction_cost,
            total_hotels=hotel_cost,
            total_meals=meal_cost,
            total_transportation=transportation_cost,
            total=attraction_cost + hotel_cost + meal_cost + transportation_cost,
        ),
    )
    return plan
