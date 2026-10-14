"""酒店推荐 Agent 节点"""

from typing import Dict, Any
from datetime import datetime

from ...services.amap_service import get_amap_service
from ...models.schemas import AgentState, AgentStep, NodeType, TripStatus


async def hotel_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    酒店推荐节点

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    agent_state = AgentState(**state)

    step = AgentStep(
        node=NodeType.HOTEL.value,
        status="running",
        input={
            "city": agent_state.city,
            "accommodation": agent_state.accommodation
        }
    )

    try:
        amap = get_amap_service()
        hotels = await amap.search_hotels(agent_state.city, agent_state.accommodation)

        step.status = "completed"
        step.output = {"hotels_count": len(hotels)}
        step.duration_ms = 0

        agent_state.hotels = hotels
        agent_state.steps.append(step)
        agent_state.current_node = NodeType.HOTEL.value
        agent_state.updated_at = datetime.now()

        return agent_state.model_dump(mode="json")

    except Exception as e:
        step.status = "failed"
        step.error = str(e)
        agent_state.errors.append(f"酒店搜索失败: {str(e)}")
        agent_state.steps.append(step)
        return agent_state.model_dump(mode="json")
