"""天气查询 Agent 节点"""

from typing import Dict, Any
from datetime import datetime

from ...services.amap_service import get_amap_service
from ...models.schemas import AgentState, AgentStep, NodeType, TripStatus


async def weather_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    天气查询节点

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    agent_state = AgentState(**state)

    step = AgentStep(
        node=NodeType.WEATHER.value,
        status="running",
        input={"city": agent_state.city}
    )

    try:
        amap = get_amap_service()
        weather_data = await amap.get_weather(agent_state.city)

        step.status = "completed"
        step.output = {"days": len(weather_data)}
        step.duration_ms = 0

        agent_state.weather = weather_data
        agent_state.steps.append(step)
        agent_state.current_node = NodeType.WEATHER.value
        agent_state.updated_at = datetime.now()

        return agent_state.model_dump(mode="json")

    except Exception as e:
        step.status = "failed"
        step.error = str(e)
        agent_state.errors.append(f"天气查询失败: {str(e)}")
        agent_state.steps.append(step)
        return agent_state.model_dump(mode="json")
