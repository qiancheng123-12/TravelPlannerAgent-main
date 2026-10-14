import json

import pytest
from langgraph.types import Command

from app.agents import graph as graph_module
from app.agents.nodes.planner_agent import _parse_response
from app.models.schemas import AgentState, TripStatus


def test_planner_accepts_numeric_hotel_rating():
    state = AgentState(
        city="成都",
        start_date="2026-10-26",
        end_date="2026-10-26",
        travel_days=1,
    )
    payload = {
        "city": "成都",
        "start_date": "2026-10-26",
        "end_date": "2026-10-26",
        "days": [{
            "date": "2026-10-26",
            "day_index": 0,
            "description": "成都一日游",
            "hotel": {
                "name": "测试酒店",
                "address": "成都",
                "rating": 4.6,
                "estimated_cost": 320,
            },
            "attractions": [],
            "meals": [],
        }],
        "weather_info": [],
        "overall_suggestions": "测试",
        "budget": None,
    }

    plan = _parse_response(json.dumps(payload, ensure_ascii=False), state)

    assert plan.days[0].hotel is not None
    assert plan.days[0].hotel.rating == 4.6


@pytest.mark.asyncio
async def test_graph_pauses_and_resumes_human_review(monkeypatch):
    async def passthrough(state):
        return dict(state)

    async def fake_rag(state):
        updated = dict(state)
        updated["rag_context"] = "雨天优先室内景点"
        updated["rag_sources"] = ["天气与备选方案（测试知识库）"]
        return updated

    async def fake_planner(state):
        updated = dict(state)
        updated["itinerary"] = {
            "city": state["city"],
            "start_date": state["start_date"],
            "end_date": state["end_date"],
            "days": [],
            "weather_info": [],
            "overall_suggestions": "测试行程",
            "budget": None,
        }
        updated["status"] = TripStatus.NEED_CONFIRM.value
        updated["need_human_review"] = True
        return updated

    monkeypatch.setattr(graph_module, "poi_search_node", passthrough)
    monkeypatch.setattr(graph_module, "weather_node", passthrough)
    monkeypatch.setattr(graph_module, "hotel_node", passthrough)
    monkeypatch.setattr(graph_module, "rag_retrieve_node", fake_rag)
    monkeypatch.setattr(graph_module, "planner_node", fake_planner)

    graph = graph_module.create_trip_planner_graph()
    config = {"configurable": {"thread_id": "test-review-thread"}}
    initial = AgentState(
        session_id="test-review-thread",
        city="北京",
        start_date="2026-09-12",
        end_date="2026-09-13",
        travel_days=2,
        status=TripStatus.PROCESSING,
    ).model_dump(mode="json")

    draft = await graph.ainvoke(initial, config=config)
    assert "__interrupt__" in draft
    assert draft["itinerary"]["city"] == "北京"

    final = await graph.ainvoke(
        Command(resume={"action": "approve", "comment": "测试通过"}),
        config=config,
    )
    assert final["status"] == TripStatus.COMPLETED.value
    assert final["need_human_review"] is False
    assert final["rag_sources"]
