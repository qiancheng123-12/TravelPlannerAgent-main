"""旅行规划 API：所有规划请求统一经过 LangGraph 工作流。"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse as FastAPIStreamingResponse
from langgraph.types import Command

from ...agents.graph import get_graph
from ...models.schemas import AgentState, TripRequest, TripStatus, UserFeedback
from ...services.memory_service import get_memory_service

router = APIRouter(prefix="/trip", tags=["旅行规划"])
RESULTS_DIR = Path(__file__).resolve().parents[2] / "saved_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

NODE_META = {
    "supervisor": (1, "Supervisor 正在选择下一工具"),
    "poi_search": (2, "正在检索实时景点"),
    "weather": (3, "正在查询天气"),
    "hotel": (4, "正在推荐住宿"),
    "rag_retrieve": (5, "正在检索 Chroma 旅行知识库"),
    "planner": (6, "正在生成行程"),
    "human_review": (7, "正在处理人工审核"),
    "validate": (7, "正在校验预算与时间约束"),
    "conflict_resolver": (7, "正在自主修复行程冲突"),
}


def _safe_session_id(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)
    if not safe:
        raise HTTPException(status_code=400, detail="session_id 无效")
    return safe[:128]


def _result_path(session_id: str) -> Path:
    return RESULTS_DIR / f"{_safe_session_id(session_id)}.json"


def _graph_config(session_id: str) -> Dict[str, Any]:
    return {"configurable": {"thread_id": _safe_session_id(session_id)}}


def _initial_state(request: TripRequest, session_id: str) -> Dict[str, Any]:
    return AgentState(
        session_id=session_id,
        user_id=request.user_id or f"anonymous-{session_id}",
        city=request.city,
        origin=request.origin,
        guests=request.guests,
        start_date=request.start_date,
        end_date=request.end_date,
        travel_days=request.travel_days,
        transportation=request.transportation,
        accommodation=request.accommodation,
        preferences=request.preferences,
        free_text_input=request.free_text_input or "",
        budget=request.budget,
        llm_provider=request.llm_provider or "deepseek",
        status=TripStatus.PROCESSING,
    ).model_dump(mode="json")


def _save_trip_state(session_id: str, state: Dict[str, Any]) -> None:
    payload = {
        "session_id": session_id,
        "updated_at": datetime.now().isoformat(),
        "status": state.get("status", TripStatus.PENDING.value),
        "rag_sources": state.get("rag_sources", []),
        "steps": state.get("steps", []),
        "errors": state.get("errors", []),
        "decision_log": state.get("decision_log", []),
        "conflicts": state.get("conflicts", []),
        "result": state.get("itinerary"),
    }
    temporary = _result_path(session_id).with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, _result_path(session_id))


def _load_trip_state(session_id: str) -> Dict[str, Any]:
    path = _result_path(session_id)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _without_interrupts(result: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in result.items() if key != "__interrupt__"}


def _create_sse_event(
    session_id: str,
    step: int,
    node: str,
    status: str,
    message: str,
    data: Dict[str, Any] | None = None,
) -> str:
    event = {
        "session_id": session_id,
        "step": step,
        "node": node,
        "status": status,
        "message": message,
        "data": data or {},
    }
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/plan")
async def create_trip_plan(request: TripRequest):
    """同步执行工作流，生成草稿后在 Human-in-the-loop 节点暂停。"""
    session_id = request.session_id or str(uuid.uuid4())
    graph = get_graph()
    try:
        result = await graph.ainvoke(
            _initial_state(request, session_id),
            config=_graph_config(session_id),
        )
        state = _without_interrupts(result)
        _save_trip_state(session_id, state)
        if state.get("itinerary"):
            await get_memory_service().record_trip(
                state.get("user_id") or f"anonymous-{session_id}",
                session_id,
                state["itinerary"],
            )
        return {
            "success": True,
            "message": "旅行计划已生成，请审核后确认",
            "data": state.get("itinerary"),
            "status": state.get("status", TripStatus.NEED_CONFIRM.value),
            "session_id": session_id,
            "need_human_review": state.get("need_human_review", True),
            "rag_sources": state.get("rag_sources", []),
            "agent_trace": state.get("decision_log", []),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"生成失败: {exc}") from exc


@router.post("/plan/stream")
async def create_trip_plan_stream(request: TripRequest):
    """以 SSE 输出每个真实 LangGraph 节点的执行结果。"""
    session_id = request.session_id or str(uuid.uuid4())

    async def event_generator():
        graph = get_graph()
        config = _graph_config(session_id)
        latest_state = _initial_state(request, session_id)
        yield _create_sse_event(session_id, 1, "init", "running", "LangGraph 工作流已启动")

        try:
            async for update in graph.astream(
                latest_state,
                config=config,
                stream_mode="updates",
            ):
                if "__interrupt__" in update:
                    continue
                for node, node_state in update.items():
                    if not isinstance(node_state, dict):
                        continue
                    latest_state.update(node_state)
                    step, default_message = NODE_META.get(node, (0, f"{node} 已完成"))
                    status = "completed"
                    data: Dict[str, Any] = {}
                    if node == "rag_retrieve":
                        data = {"sources": latest_state.get("rag_sources", [])}
                    elif node == "planner":
                        data = {
                            "itinerary": latest_state.get("itinerary"),
                            "rag_sources": latest_state.get("rag_sources", []),
                        }
                    elif node in {"supervisor", "validate", "conflict_resolver"}:
                        data = {
                            "agent_trace": latest_state.get("decision_log", []),
                            "conflicts": latest_state.get("conflicts", []),
                        }
                    yield _create_sse_event(
                        session_id,
                        step,
                        node,
                        status,
                        default_message,
                        data,
                    )

            snapshot = await graph.aget_state(config)
            if snapshot.values:
                latest_state.update(snapshot.values)
            _save_trip_state(session_id, latest_state)
            if latest_state.get("itinerary"):
                await get_memory_service().record_trip(
                    latest_state.get("user_id") or f"anonymous-{session_id}",
                    session_id,
                    latest_state["itinerary"],
                )

            if snapshot.next:
                yield _create_sse_event(
                    session_id,
                    7,
                    "human_review",
                    TripStatus.NEED_CONFIRM.value,
                    "行程草稿已生成，请审核",
                    {
                        "itinerary": latest_state.get("itinerary"),
                        "rag_sources": latest_state.get("rag_sources", []),
                        "need_human_review": True,
                    },
                )
            else:
                yield _create_sse_event(
                    session_id,
                    8,
                    "complete",
                    latest_state.get("status", TripStatus.COMPLETED.value),
                    "旅行规划工作流已完成",
                    {"itinerary": latest_state.get("itinerary")},
                )
        except Exception as exc:
            latest_state["status"] = TripStatus.FAILED.value
            latest_state.setdefault("errors", []).append(str(exc))
            _save_trip_state(session_id, latest_state)
            yield _create_sse_event(
                session_id,
                0,
                "error",
                TripStatus.FAILED.value,
                f"执行失败: {exc}",
            )

    return FastAPIStreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feedback")
async def submit_feedback(feedback: UserFeedback):
    """使用同一 thread_id 恢复 LangGraph interrupt。"""
    graph = get_graph()
    if feedback.action == "modify" and not feedback.modifications:
        raise HTTPException(status_code=400, detail="modify 操作必须提供 modifications")
    config = _graph_config(feedback.session_id)
    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="未找到对应的规划会话")
    if not snapshot.next:
        raise HTTPException(status_code=409, detail="该会话当前不在等待审核")

    try:
        result = await graph.ainvoke(
            Command(
                resume={
                    "action": feedback.action,
                    "comment": feedback.comment or "",
                    "modifications": feedback.modifications or {},
                }
            ),
            config=config,
        )
        state = _without_interrupts(result)
        _save_trip_state(feedback.session_id, state)
        return {
            "success": True,
            "message": f"反馈已处理: {feedback.action}",
            "status": state.get("status"),
            "data": state.get("itinerary"),
            "need_human_review": state.get("need_human_review", False),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"反馈处理失败: {exc}") from exc


@router.get("/status/{session_id}")
async def get_trip_status(session_id: str):
    graph = get_graph()
    snapshot = await graph.aget_state(_graph_config(session_id))
    if snapshot.values:
        state = snapshot.values
        return {
            "session_id": session_id,
            "status": state.get("status", TripStatus.PENDING.value),
            "current_node": state.get("current_node", ""),
            "steps": state.get("steps", []),
            "errors": state.get("errors", []),
            "need_human_review": bool(snapshot.next),
            "rag_sources": state.get("rag_sources", []),
            "agent_trace": state.get("decision_log", []),
        }

    saved = _load_trip_state(session_id)
    if not saved:
        raise HTTPException(status_code=404, detail="未找到对应的规划会话")
    return {
        "session_id": session_id,
        "status": saved.get("status", TripStatus.PENDING.value),
        "current_node": "",
        "steps": saved.get("steps", []),
        "errors": saved.get("errors", []),
        "need_human_review": saved.get("status") == TripStatus.NEED_CONFIRM.value,
        "rag_sources": saved.get("rag_sources", []),
        "agent_trace": saved.get("decision_log", []),
    }


@router.get("/result/{session_id}")
async def get_trip_result(session_id: str):
    graph = get_graph()
    snapshot = await graph.aget_state(_graph_config(session_id))
    if snapshot.values:
        state = snapshot.values
        return {
            "success": True,
            "message": "获取成功",
            "data": state.get("itinerary"),
            "status": state.get("status", TripStatus.PENDING.value),
            "need_human_review": bool(snapshot.next),
            "rag_sources": state.get("rag_sources", []),
            "agent_trace": state.get("decision_log", []),
        }

    saved = _load_trip_state(session_id)
    if not saved:
        raise HTTPException(status_code=404, detail="未找到对应的规划结果")
    return {
        "success": True,
        "message": "获取成功",
        "data": saved.get("result"),
        "status": saved.get("status", TripStatus.PENDING.value),
        "need_human_review": saved.get("status") == TripStatus.NEED_CONFIRM.value,
        "rag_sources": saved.get("rag_sources", []),
        "agent_trace": saved.get("decision_log", []),
    }
