"""LLM 驱动的 Supervisor：一次规划工具组合，随后按计划执行。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List

from ...core.llm import get_llm
from ...models.schemas import AgentState, AgentStep, NodeType


def _candidates(state: AgentState) -> List[str]:
    attempted = set(state.attempted_tools)
    candidates: List[str] = []
    if "poi_search" not in attempted:
        candidates.append("poi_search")
    if state.start_date and "weather" not in attempted:
        candidates.append("weather")
    if state.travel_days > 1 and "不住" not in state.accommodation and "hotel" not in attempted:
        candidates.append("hotel")
    if "rag_retrieve" not in attempted:
        candidates.append("rag_retrieve")
    return candidates


def _parse_plan(content: str, allowed: List[str]) -> tuple[List[str], str]:
    match = re.search(r"\{[\s\S]*\}", content)
    if match:
        try:
            payload = json.loads(match.group(0))
            raw_actions = payload.get("actions", [])
            if not isinstance(raw_actions, list):
                raw_actions = [payload.get("action", "")]
            actions = []
            for item in raw_actions:
                action = str(item)
                if action in allowed and action not in actions:
                    actions.append(action)
            if actions:
                # RAG 会综合实时工具结果，因此必须放在实时查询之后。
                if "poi_search" in actions and "rag_retrieve" in actions:
                    actions.remove("rag_retrieve")
                    actions.append("rag_retrieve")
                return actions, str(payload.get("reason", "模型根据当前目标规划工具组合"))
        except json.JSONDecodeError:
            pass
    return allowed, "模型输出不可解析，采用完整安全候选计划"


async def supervisor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    agent_state = AgentState(**state)
    candidates = _candidates(agent_state)

    if agent_state.itinerary is not None:
        action, reason = "validate", "候选行程已生成，进入约束校验"
    elif agent_state.planned_tools:
        remaining = [tool for tool in agent_state.planned_tools if tool in candidates]
        if remaining:
            action, reason = remaining[0], "按 Supervisor 已生成的工具计划继续执行"
        else:
            action, reason = "planner", "计划内工具已执行完毕，生成候选行程"
    elif candidates:
        tool_plan = list(candidates)
        reason = "按缺失信息优先级规划工具组合"
        try:
            llm = get_llm(agent_state.llm_provider, temperature=0, max_tokens=260)
            response = await llm.ainvoke(
                "你是旅行规划 Agent 的 Supervisor。请从候选工具中选择需要执行的工具组合，"
                "并给出执行顺序。不要遗漏生成可执行行程所需的信息，仅返回 JSON。\n"
                f"用户目标: {agent_state.free_text_input or '生成可执行旅行计划'}\n"
                f"偏好: {agent_state.preferences}\n预算: {agent_state.budget}\n"
                f"候选工具: {candidates}\n"
                '{"actions":["工具1","工具2"],"reason":"组合与顺序理由"}'
            )
            tool_plan, reason = _parse_plan(str(response.content), candidates)
        except Exception as exc:
            reason = f"LLM Supervisor 降级为完整规则计划: {exc}"
        agent_state.planned_tools = tool_plan
        action = tool_plan[0] if tool_plan else "planner"
    else:
        action, reason = "planner", "没有待执行工具，直接生成候选行程"

    agent_state.next_action = action
    agent_state.decision_iterations += 1
    if action not in {"planner", "validate"} and action not in agent_state.attempted_tools:
        agent_state.attempted_tools.append(action)
    agent_state.decision_log.append(
        {"iteration": agent_state.decision_iterations, "action": action, "reason": reason}
    )
    agent_state.steps.append(
        AgentStep(
            node=NodeType.SUPERVISOR.value,
            status="completed",
            output={
                "action": action,
                "reason": reason,
                "candidates": candidates,
                "tool_plan": agent_state.planned_tools,
            },
        )
    )
    agent_state.current_node = NodeType.SUPERVISOR.value
    agent_state.updated_at = datetime.now()
    return agent_state.model_dump(mode="json")


def route_supervisor(state: Dict[str, Any]) -> str:
    action = str(state.get("next_action") or "planner")
    return action if action in {
        "poi_search", "weather", "hotel", "rag_retrieve", "planner", "validate"
    } else "planner"
