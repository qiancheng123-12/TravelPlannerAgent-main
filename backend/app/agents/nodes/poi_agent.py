"""POI 搜索 Agent 节点"""

import json
import re
from typing import Dict, Any, List
from langchain_core.prompts import ChatPromptTemplate

from ...core.llm import get_llm
from ...services.amap_service import get_amap_service
from ...models.schemas import AgentState, AgentStep, NodeType


# POI 搜索 Agent 的系统提示
POI_AGENT_PROMPT = """你是一个专业的景点搜索助手。

你的任务是:
1. 根据用户指定的城市和偏好，搜索相关的景点信息
2. 返回景点的名称、地址、坐标等详细信息
3. 确保景点信息准确、丰富

当前任务:
- 城市: {city}
- 旅行偏好: {preferences}
- 额外要求: {free_text_input}

请返回 JSON，不要添加其他文字：
{{"keywords": ["关键词1", "关键词2", "关键词3"], "reason": "简短理由"}}
"""


def _parse_search_plan(content: str, fallback: List[str]) -> tuple[List[str], str]:
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return fallback[:3], "模型未返回 JSON，使用用户偏好"
    try:
        payload = json.loads(match.group(0))
        keywords = [
            str(item).strip()
            for item in payload.get("keywords", [])
            if str(item).strip()
        ]
        return (keywords or fallback)[:3], str(payload.get("reason", ""))
    except (json.JSONDecodeError, AttributeError):
        return fallback[:3], "JSON 解析失败，使用用户偏好"


async def poi_search_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    POI 搜索节点

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    agent_state = AgentState(**state)

    # 记录步骤开始
    step = AgentStep(
        node=NodeType.POI_SEARCH.value,
        status="running",
        input={
            "city": agent_state.city,
            "preferences": agent_state.preferences
        }
    )

    try:
        # 1. 使用 LLM 把自然语言偏好转成高德可用的搜索关键词。
        fallback_keywords = agent_state.preferences or ["景点", "旅游"]
        search_keywords = fallback_keywords[:3]
        decision_reason = "使用用户偏好"
        try:
            llm = get_llm(agent_state.llm_provider, temperature=0.2, max_tokens=300)
            prompt = ChatPromptTemplate.from_template(POI_AGENT_PROMPT)
            response = await (prompt | llm).ainvoke({
                "city": agent_state.city,
                "preferences": ", ".join(agent_state.preferences) if agent_state.preferences else "景点",
                "free_text_input": agent_state.free_text_input or "无",
            })
            search_keywords, decision_reason = _parse_search_plan(
                str(response.content), fallback_keywords
            )
        except Exception as exc:
            # 关键词规划失败不应阻断实时 POI 搜索。
            decision_reason = f"LLM 关键词规划降级: {exc}"

        # 3. 调用高德地图 API 搜索 POI
        amap = get_amap_service()
        all_pois = []
        for keyword in search_keywords[:3]:
            pois = await amap.search_poi(keyword, agent_state.city, citylimit=True)
            all_pois.extend(pois)

        # 去重
        seen = set()
        unique_pois = []
        for poi in all_pois:
            if poi.name not in seen:
                seen.add(poi.name)
                unique_pois.append(poi)

        # 4. 更新状态
        step.status = "completed"
        step.output = {
            "pois_count": len(unique_pois),
            "keywords_used": search_keywords,
            "decision_reason": decision_reason,
        }
        step.duration_ms = 0  # TODO: 计算实际耗时

        agent_state.pois = unique_pois[:20]  # 最多保留20个
        agent_state.steps.append(step)
        agent_state.current_node = NodeType.POI_SEARCH.value
        agent_state.updated_at = datetime.now()

        return agent_state.model_dump(mode="json")

    except Exception as e:
        step.status = "failed"
        step.error = str(e)
        agent_state.errors.append(f"POI搜索失败: {str(e)}")
        agent_state.steps.append(step)
        return agent_state.model_dump(mode="json")


# 导入 datetime
from datetime import datetime
