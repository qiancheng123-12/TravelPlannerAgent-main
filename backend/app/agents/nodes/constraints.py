"""复杂场景的约束校验与自主冲突修复节点。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ...models.schemas import AgentState, AgentStep, NodeType


async def validate_itinerary_node(state: Dict[str, Any]) -> Dict[str, Any]:
    agent_state = AgentState(**state)
    conflicts = []
    plan = agent_state.itinerary

    if plan:
        if agent_state.budget and len(agent_state.budget) == 2 and plan.budget:
            ceiling = agent_state.budget[1]
            actual = plan.budget.total
            if actual > ceiling:
                conflicts.append({
                    "type": "budget_exceeded",
                    "severity": "high",
                    "actual": actual,
                    "limit": ceiling,
                })

        seen = set()
        for day in plan.days:
            duration = sum(item.visit_duration for item in day.attractions)
            if len(day.attractions) > 3 or duration > 540:
                conflicts.append({
                    "type": "day_overbooked",
                    "severity": "medium",
                    "day_index": day.day_index,
                    "attractions": len(day.attractions),
                    "minutes": duration,
                })
            duplicates = [item.name for item in day.attractions if item.name in seen]
            if duplicates:
                conflicts.append({
                    "type": "duplicate_attraction",
                    "severity": "low",
                    "day_index": day.day_index,
                    "names": duplicates,
                })
            seen.update(item.name for item in day.attractions)

    agent_state.conflicts = conflicts
    agent_state.validation_passed = not conflicts
    agent_state.steps.append(
        AgentStep(
            node=NodeType.VALIDATE.value,
            status="completed" if not conflicts else "needs_resolution",
            output={"passed": not conflicts, "conflicts": conflicts},
        )
    )
    agent_state.decision_log.append({
        "iteration": agent_state.decision_iterations,
        "action": "validate",
        "reason": "约束校验通过" if not conflicts else f"发现 {len(conflicts)} 个冲突",
    })
    agent_state.current_node = NodeType.VALIDATE.value
    agent_state.updated_at = datetime.now()
    return agent_state.model_dump(mode="json")


async def conflict_resolver_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """按冲突类型选择不同修复工具，可重复回到校验节点形成闭环。"""
    agent_state = AgentState(**state)
    plan = agent_state.itinerary
    applied = []

    if plan:
        for conflict in agent_state.conflicts:
            conflict_type = conflict.get("type")
            if conflict_type == "day_overbooked":
                day = next((d for d in plan.days if d.day_index == conflict.get("day_index")), None)
                if day:
                    kept, minutes = [], 0
                    for attraction in day.attractions:
                        if len(kept) < 3 and minutes + attraction.visit_duration <= 540:
                            kept.append(attraction)
                            minutes += attraction.visit_duration
                    day.attractions = kept
                    applied.append("压缩单日景点，保留时间可执行性")
            elif conflict_type == "duplicate_attraction":
                day = next((d for d in plan.days if d.day_index == conflict.get("day_index")), None)
                if day:
                    duplicate_names = set(conflict.get("names", []))
                    day.attractions = [a for a in day.attractions if a.name not in duplicate_names]
                    applied.append("移除跨日重复景点")
            elif conflict_type == "budget_exceeded" and plan.budget:
                limit = int(conflict.get("limit", plan.budget.total))
                current = max(int(conflict.get("actual", plan.budget.total)), 1)
                ratio = min(1.0, limit / current)
                plan.budget.total_attractions = int(plan.budget.total_attractions * ratio)
                plan.budget.total_hotels = int(plan.budget.total_hotels * ratio)
                plan.budget.total_meals = int(plan.budget.total_meals * ratio)
                plan.budget.total_transportation = int(plan.budget.total_transportation * ratio)
                plan.budget.total = sum([
                    plan.budget.total_attractions, plan.budget.total_hotels,
                    plan.budget.total_meals, plan.budget.total_transportation,
                ])
                applied.append("按预算上限重新分配交通、住宿、餐饮与门票")

        if applied:
            plan.overall_suggestions += "\n冲突修复：" + "；".join(dict.fromkeys(applied)) + "。"
        agent_state.itinerary = plan

    agent_state.resolution_attempts += 1
    agent_state.conflicts = []
    agent_state.steps.append(
        AgentStep(
            node=NodeType.CONFLICT_RESOLVER.value,
            status="completed",
            input={"attempt": agent_state.resolution_attempts},
            output={"strategies": list(dict.fromkeys(applied))},
        )
    )
    agent_state.decision_log.append({
        "iteration": agent_state.decision_iterations,
        "action": "conflict_resolver",
        "reason": "；".join(dict.fromkeys(applied)) or "未找到可自动修复项，交由人工审核",
    })
    agent_state.current_node = NodeType.CONFLICT_RESOLVER.value
    agent_state.updated_at = datetime.now()
    return agent_state.model_dump(mode="json")


def route_after_validation(state: Dict[str, Any]) -> str:
    if state.get("conflicts") and int(state.get("resolution_attempts", 0)) < 2:
        return "conflict_resolver"
    return "human_review"
