import pytest

from app.agents.nodes.constraints import conflict_resolver_node, validate_itinerary_node
from app.models.schemas import AgentState


@pytest.mark.asyncio
async def test_budget_conflict_is_detected_and_resolved():
    state = AgentState(
        city="北京", start_date="2026-10-01", end_date="2026-10-01",
        travel_days=1, budget=[0, 1000],
        itinerary={
            "city": "北京", "start_date": "2026-10-01", "end_date": "2026-10-01",
            "days": [], "weather_info": [], "overall_suggestions": "测试",
            "budget": {
                "total_attractions": 400, "total_hotels": 600,
                "total_meals": 300, "total_transportation": 200, "total": 1500,
            },
        },
    ).model_dump(mode="json")

    checked = await validate_itinerary_node(state)
    assert checked["conflicts"][0]["type"] == "budget_exceeded"

    fixed = await conflict_resolver_node(checked)
    rechecked = await validate_itinerary_node(fixed)
    assert rechecked["validation_passed"] is True
    assert rechecked["itinerary"]["budget"]["total"] <= 1000
