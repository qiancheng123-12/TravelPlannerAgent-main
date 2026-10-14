"""LangGraph interrupt 驱动的真实 Human-in-the-loop 审核节点。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict

from langgraph.types import interrupt

from ...models.schemas import AgentState, AgentStep, NodeType, TripPlan, TripStatus


def _deep_merge(original: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(original)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


async def human_review_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """暂停图执行，等待同一 session_id 的 approve/modify/reject 指令。"""
    agent_state = AgentState(**state)
    decision = interrupt(
        {
            "type": "trip_plan_review",
            "session_id": agent_state.session_id,
            "question": "请审核生成的旅行计划",
            "allowed_actions": ["approve", "modify", "reject"],
            "itinerary": (
                agent_state.itinerary.model_dump(mode="json")
                if agent_state.itinerary
                else None
            ),
            "rag_sources": agent_state.rag_sources,
        }
    )

    if not isinstance(decision, dict):
        decision = {"action": "reject", "comment": "无效的审核数据"}

    action = str(decision.get("action", "reject")).lower()
    comment = str(decision.get("comment") or "")
    modifications = decision.get("modifications") or {}
    step = AgentStep(
        node=NodeType.HUMAN_REVIEW.value,
        status="completed",
        input={"action": action, "comment": comment},
    )

    if action == "approve":
        agent_state.status = TripStatus.COMPLETED
        agent_state.need_human_review = False
        agent_state.human_feedback = "approved"
        step.output = {"approved": True}
    elif action == "modify" and isinstance(modifications, dict) and agent_state.itinerary:
        merged = _deep_merge(
            agent_state.itinerary.model_dump(mode="json"),
            modifications,
        )
        agent_state.itinerary = TripPlan.model_validate(merged)
        agent_state.status = TripStatus.COMPLETED
        agent_state.need_human_review = False
        agent_state.human_feedback = "modified"
        step.output = {"approved": True, "modified_fields": sorted(modifications)}
    elif action == "reject":
        agent_state.status = TripStatus.FAILED
        agent_state.need_human_review = False
        agent_state.human_feedback = "rejected"
        step.output = {"approved": False}
    else:
        agent_state.status = TripStatus.NEED_CONFIRM
        agent_state.need_human_review = True
        step.status = "failed"
        step.error = "审核动作无效，必须是 approve、modify 或 reject"

    agent_state.review_comment = comment
    agent_state.steps.append(step)
    agent_state.current_node = NodeType.HUMAN_REVIEW.value
    agent_state.updated_at = datetime.now()
    return agent_state.model_dump(mode="json")
