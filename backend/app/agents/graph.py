"""LangGraph 1.x 旅行规划工作流。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes.hotel_agent import hotel_node
from .nodes.human_review import human_review_node
from .nodes.planner_agent import planner_node
from .nodes.poi_agent import poi_search_node
from .nodes.rag_agent import rag_retrieve_node
from .nodes.weather_agent import weather_node
from .nodes.supervisor import route_supervisor, supervisor_node
from .nodes.constraints import conflict_resolver_node, route_after_validation, validate_itinerary_node
from ..core.config import get_settings


class GraphState(TypedDict, total=False):
    """可被 LangGraph checkpoint 序列化的完整状态。"""

    session_id: str
    user_id: str
    city: str
    origin: str
    guests: int
    start_date: str
    end_date: str
    travel_days: int
    transportation: str
    accommodation: str
    preferences: List[str]
    free_text_input: str
    budget: Optional[List[int]]
    pois: List[Dict[str, Any]]
    weather: List[Dict[str, Any]]
    hotels: List[Dict[str, Any]]
    rag_context: str
    rag_sources: List[str]
    itinerary: Optional[Dict[str, Any]]
    current_node: str
    status: str
    steps: List[Dict[str, Any]]
    errors: List[str]
    need_human_review: bool
    human_feedback: Optional[str]
    review_comment: str
    llm_provider: str
    created_at: str
    updated_at: str
    next_action: str
    attempted_tools: List[str]
    planned_tools: List[str]
    decision_log: List[Dict[str, Any]]
    decision_iterations: int
    conflicts: List[Dict[str, Any]]
    resolution_attempts: int
    validation_passed: bool


def create_trip_planner_graph(checkpointer=None):
    """创建 Supervisor 自主选工具、校验并修复冲突的循环工作流。"""
    workflow = StateGraph(GraphState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("poi_search", poi_search_node)
    workflow.add_node("weather", weather_node)
    workflow.add_node("hotel", hotel_node)
    workflow.add_node("rag_retrieve", rag_retrieve_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("validate", validate_itinerary_node)
    workflow.add_node("conflict_resolver", conflict_resolver_node)

    workflow.add_edge(START, "supervisor")
    workflow.add_conditional_edges("supervisor", route_supervisor)
    workflow.add_edge("poi_search", "supervisor")
    workflow.add_edge("weather", "supervisor")
    workflow.add_edge("hotel", "supervisor")
    workflow.add_edge("rag_retrieve", "supervisor")
    workflow.add_edge("planner", "supervisor")
    workflow.add_conditional_edges("validate", route_after_validation)
    workflow.add_edge("conflict_resolver", "validate")
    workflow.add_edge("human_review", END)
    # 无参数只用于隔离单元测试；应用运行时由 initialize_graph 注入 SQLite。
    return workflow.compile(checkpointer=checkpointer or InMemorySaver())


_graph_instance = None
_checkpoint_connection = None


async def initialize_graph():
    """使用 AsyncSqliteSaver 初始化可跨重启恢复的 LangGraph。"""
    global _graph_instance, _checkpoint_connection
    if _graph_instance is not None:
        return _graph_instance

    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    database_path = Path(settings.langgraph_checkpoint_path)
    if not database_path.is_absolute():
        database_path = backend_root / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)

    _checkpoint_connection = await aiosqlite.connect(str(database_path))
    checkpointer = AsyncSqliteSaver(_checkpoint_connection)
    await checkpointer.setup()
    _graph_instance = create_trip_planner_graph(checkpointer)
    return _graph_instance


async def close_graph() -> None:
    global _graph_instance, _checkpoint_connection
    _graph_instance = None
    if _checkpoint_connection is not None:
        await _checkpoint_connection.close()
        _checkpoint_connection = None


def get_graph():
    """返回由 FastAPI lifespan 初始化的持久化图实例。"""
    if _graph_instance is None:
        raise RuntimeError("LangGraph 尚未初始化，请通过 FastAPI lifespan 启动应用")
    return _graph_instance
