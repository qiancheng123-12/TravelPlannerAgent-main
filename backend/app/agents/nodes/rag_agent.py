"""RAG 检索节点：把实时 POI 和旅行知识检索结果交给规划 Agent。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict

from ...models.schemas import AgentState, AgentStep, NodeType
from ...services.embedding_service import get_vector_store


async def rag_retrieve_node(state: Dict[str, Any]) -> Dict[str, Any]:
    agent_state = AgentState(**state)
    step = AgentStep(
        node=NodeType.RAG_RETRIEVE.value,
        status="running",
        input={"city": agent_state.city, "pois_count": len(agent_state.pois)},
    )

    try:
        store = get_vector_store()
        poi_payload = [poi.model_dump(mode="json") for poi in agent_state.pois]
        if poi_payload:
            await asyncio.to_thread(store.add_poi_knowledge, agent_state.city, poi_payload)

        budget_text = ""
        if agent_state.budget and len(agent_state.budget) == 2:
            budget_text = f"预算{agent_state.budget[0]}到{agent_state.budget[1]}元"
        query = " ".join(
            part
            for part in [
                agent_state.city,
                "旅行规划",
                "、".join(agent_state.preferences),
                agent_state.transportation,
                agent_state.accommodation,
                budget_text,
                agent_state.free_text_input,
            ]
            if part
        )
        documents = await asyncio.to_thread(store.retrieve, query, 5)
        context, sources = store.format_context(documents)
        agent_state.rag_context = context
        agent_state.rag_sources = sources
        step.status = "completed"
        step.output = {
            "retrieved_count": len(documents),
            "sources": sources,
        }
    except Exception as exc:
        # RAG 失败时保留主流程可用，同时把降级原因展示给答辩演示与日志。
        agent_state.rag_context = "知识库暂时不可用，请仅依据实时地图和天气数据规划。"
        agent_state.rag_sources = []
        step.status = "failed"
        step.error = str(exc)
        agent_state.errors.append(f"RAG 检索降级: {exc}")

    agent_state.steps.append(step)
    agent_state.current_node = NodeType.RAG_RETRIEVE.value
    agent_state.updated_at = datetime.now()
    return agent_state.model_dump(mode="json")
