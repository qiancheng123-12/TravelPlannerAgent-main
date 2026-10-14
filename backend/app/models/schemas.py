"""数据模型定义"""

from typing import List, Optional, Union, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# ===========================================
# 枚举类型
# ===========================================

class LLMProvider(str, Enum):
    DEEPSEEK = "deepseek"
    ALIYUN = "aliyun"
    OPENAI = "openai"


class TripStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEED_CONFIRM = "need_confirm"  # Human-in-the-loop


class NodeType(str, Enum):
    SUPERVISOR = "supervisor"
    ROUTER = "router"
    POI_SEARCH = "poi_search"
    WEATHER = "weather"
    HOTEL = "hotel"
    RAG_RETRIEVE = "rag_retrieve"
    PLANNER = "planner"
    HUMAN_REVIEW = "human_review"
    VALIDATE = "validate"
    CONFLICT_RESOLVER = "conflict_resolver"


# ===========================================
# 基础数据模型
# ===========================================

class Location(BaseModel):
    """地理位置"""
    longitude: float = Field(..., description="经度")
    latitude: float = Field(..., description="纬度")


class POI(BaseModel):
    """兴趣点"""
    id: str = Field(default="", description="POI ID")
    name: str = Field(..., description="名称")
    address: str = Field(default="", description="地址")
    location: Optional[Location] = Field(default=None, description="坐标")
    category: Optional[str] = Field(default=None, description="类别")
    rating: Optional[float] = Field(default=None, description="评分")
    tel: Optional[str] = Field(default=None, description="电话")
    ticket_price: Optional[int] = Field(default=0, description="门票价格")
    visit_duration: Optional[int] = Field(default=120, description="建议游览时长(分钟)")
    description: Optional[str] = Field(default=None, description="描述")
    image_url: Optional[str] = Field(default=None, description="图片URL")


class Weather(BaseModel):
    """天气信息"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_weather: str = Field(default="", description="白天天气")
    night_weather: str = Field(default="", description="夜间天气")
    day_temp: Union[int, str] = Field(default=0, description="白天温度")
    night_temp: Union[int, str] = Field(default=0, description="夜间温度")
    wind_direction: str = Field(default="", description="风向")
    wind_power: str = Field(default="", description="风力")


class Hotel(BaseModel):
    """酒店信息"""
    name: str = Field(..., description="酒店名称")
    address: str = Field(default="", description="地址")
    location: Optional[Location] = Field(default=None, description="坐标")
    price_range: str = Field(default="", description="价格范围")
    rating: Union[float, str] = Field(default="", description="评分")
    type: str = Field(default="", description="酒店类型")
    estimated_cost: int = Field(default=0, description="预估费用")


class Meal(BaseModel):
    """餐饮信息"""
    type: str = Field(..., description="类型: breakfast/lunch/dinner")
    name: str = Field(..., description="名称")
    address: Optional[str] = Field(default=None, description="地址")
    description: Optional[str] = Field(default=None, description="描述")
    estimated_cost: int = Field(default=0, description="预估费用")


class Attraction(BaseModel):
    """景点信息（行程中的景点）"""
    name: str = Field(..., description="名称")
    address: str = Field(..., description="地址")
    location: Location = Field(..., description="坐标")
    visit_duration: int = Field(default=120, description="游览时长(分钟)")
    description: str = Field(default="", description="描述")
    category: Optional[str] = Field(default=None, description="类别")
    ticket_price: int = Field(default=0, description="门票价格")


class DayPlan(BaseModel):
    """单日行程"""
    date: str = Field(..., description="日期")
    day_index: int = Field(..., description="第几天(从0开始)")
    description: str = Field(..., description="当日描述")
    transportation: str = Field(default="", description="交通方式")
    accommodation: str = Field(default="", description="住宿")
    hotel: Optional[Hotel] = Field(default=None, description="推荐酒店")
    attractions: List[Attraction] = Field(default_factory=list, description="景点列表")
    meals: List[Meal] = Field(default_factory=list, description="餐饮列表")


class Budget(BaseModel):
    """预算信息"""
    total_attractions: int = Field(default=0, description="景点门票总费用")
    total_hotels: int = Field(default=0, description="酒店总费用")
    total_meals: int = Field(default=0, description="餐饮总费用")
    total_transportation: int = Field(default=0, description="交通总费用")
    total: int = Field(default=0, description="总费用")


class TripPlan(BaseModel):
    """旅行计划"""
    city: str = Field(..., description="城市")
    origin: str = Field(default="", description="出发地")
    guests: int = Field(default=1, ge=1, le=20, description="出行人数")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    days: List[DayPlan] = Field(default_factory=list, description="每日行程")
    weather_info: List[Weather] = Field(default_factory=list, description="天气信息")
    overall_suggestions: str = Field(default="", description="总体建议")
    budget: Optional[Budget] = Field(default=None, description="预算信息")


# ===========================================
# 请求模型
# ===========================================

class TripRequest(BaseModel):
    """旅行规划请求"""
    session_id: str = Field(default="", description="会话ID")
    user_id: str = Field(default="", description="稳定用户ID")
    city: str = Field(..., description="目的地城市")
    origin: str = Field(..., min_length=1, description="出发地")
    guests: int = Field(default=1, ge=1, le=20, description="出行人数")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    travel_days: int = Field(..., ge=1, le=30, description="旅行天数")
    transportation: str = Field(default="公共交通", description="交通方式")
    accommodation: str = Field(default="经济型酒店", description="住宿偏好")
    preferences: List[str] = Field(default_factory=list, description="旅行偏好")
    free_text_input: Optional[str] = Field(default="", description="额外要求")
    llm_provider: Optional[str] = Field(default=None, description="指定LLM提供商")
    budget: Optional[List[int]] = Field(default=None, description="预算范围 [最小值, 最大值]")


class ChatMessage(BaseModel):
    """聊天消息"""
    session_id: str = Field(..., description="会话ID")
    user_id: str = Field(default="", description="稳定用户ID，用于跨会话长期记忆")
    message: str = Field(..., description="消息内容")
    message_type: str = Field(default="text", description="消息类型")
    llm_provider: Optional[str] = Field(default=None, description="LLM提供商")


class UserFeedback(BaseModel):
    """用户反馈 (Human-in-the-loop)"""
    session_id: str = Field(..., description="会话ID")
    action: Literal["approve", "modify", "reject"] = Field(
        ..., description="动作: approve/modify/reject"
    )
    modifications: Optional[Dict[str, Any]] = Field(default=None, description="修改内容")
    comment: Optional[str] = Field(default=None, description="评论")


# ===========================================
# 响应模型
# ===========================================

class TripPlanResponse(BaseModel):
    """旅行计划响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[TripPlan] = Field(default=None, description="旅行计划")
    status: TripStatus = Field(default=TripStatus.PENDING, description="状态")


class AgentStep(BaseModel):
    """Agent 执行步骤"""
    node: str = Field(..., description="节点名称")
    status: str = Field(..., description="状态")
    input: Optional[Dict[str, Any]] = Field(default=None, description="输入")
    output: Optional[Dict[str, Any]] = Field(default=None, description="输出")
    duration_ms: Optional[int] = Field(default=None, description="耗时(毫秒)")
    error: Optional[str] = Field(default=None, description="错误信息")


class StreamingResponse(BaseModel):
    """流式响应"""
    session_id: str = Field(..., description="会话ID")
    step: int = Field(..., description="步骤序号")
    node: str = Field(..., description="当前节点")
    status: TripStatus = Field(..., description="状态")
    message: str = Field(default="", description="消息")
    data: Optional[Dict[str, Any]] = Field(default=None, description="数据")
    thought: Optional[str] = Field(default=None, description="Agent 思考过程")
    steps: List[AgentStep] = Field(default_factory=list, description="执行步骤列表")


class ChatResponse(BaseModel):
    """聊天响应"""
    session_id: str = Field(..., description="会话ID")
    user_id: str = Field(default="", description="用户ID")
    response: str = Field(..., description="响应内容")
    trip_plan: Optional[TripPlan] = Field(default=None, description="旅行计划(如果有)")
    intent: str = Field(default="general", description="LLM 识别的用户意图")
    slots: Dict[str, Any] = Field(default_factory=dict, description="当前会话已收集槽位")
    missing_slots: List[str] = Field(default_factory=list, description="仍缺失的关键槽位")
    quick_replies: List[str] = Field(default_factory=list, description="建议快捷回复")
    status: str = Field(default="completed", description="对话编排状态")
    agent_trace: List[Dict[str, Any]] = Field(default_factory=list, description="Agent 决策轨迹")


class MemorySettingsUpdate(BaseModel):
    enabled: bool = Field(..., description="是否允许助手写入和召回长期记忆")


class MemoryFactUpdate(BaseModel):
    value: Any = Field(..., description="修改后的偏好值")
    summary: Optional[str] = Field(default=None, max_length=300, description="可选的人类可读摘要")


class MemoryTripSave(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128, description="行程所属会话ID")
    plan: Dict[str, Any] = Field(..., description="需要补写到历史记录的完整行程")


# ===========================================
# Agent 状态模型 (LangGraph State)
# ===========================================

class AgentState(BaseModel):
    """Agent 状态 - LangGraph 使用"""
    # 基本信息
    session_id: str = Field(default="", description="会话ID")
    user_id: str = Field(default="", description="稳定用户ID")
    city: str = Field(default="", description="城市")
    origin: str = Field(default="", description="出发地")
    guests: int = Field(default=1, ge=1, le=20, description="出行人数")
    start_date: str = Field(default="", description="开始日期")
    end_date: str = Field(default="", description="结束日期")
    travel_days: int = Field(default=1, description="旅行天数")
    transportation: str = Field(default="公共交通", description="交通方式")
    accommodation: str = Field(default="经济型酒店", description="住宿偏好")
    preferences: List[str] = Field(default_factory=list, description="旅行偏好")
    free_text_input: str = Field(default="", description="额外要求")
    budget: Optional[List[int]] = Field(default=None, description="预算范围 [最小值, 最大值]")

    # Agent 输出
    pois: List[POI] = Field(default_factory=list, description="POI列表")
    weather: List[Weather] = Field(default_factory=list, description="天气信息")
    hotels: List[Hotel] = Field(default_factory=list, description="酒店列表")
    rag_context: str = Field(default="", description="RAG 检索得到的旅行知识上下文")
    rag_sources: List[str] = Field(default_factory=list, description="RAG 知识来源")
    itinerary: Optional[TripPlan] = Field(default=None, description="行程计划")

    # 执行状态
    current_node: str = Field(default="", description="当前节点")
    status: TripStatus = Field(default=TripStatus.PENDING, description="状态")
    steps: List[AgentStep] = Field(default_factory=list, description="执行步骤")
    errors: List[str] = Field(default_factory=list, description="错误列表")

    # Human-in-the-loop
    need_human_review: bool = Field(default=False, description="是否需要人工审核")
    human_feedback: Optional[str] = Field(default=None, description="人工反馈")
    review_comment: str = Field(default="", description="人工审核备注")

    # 自主决策循环：Supervisor 每轮根据上下文选择下一个工具。
    next_action: str = Field(default="", description="Supervisor 选择的下一动作")
    attempted_tools: List[str] = Field(default_factory=list, description="已尝试工具")
    planned_tools: List[str] = Field(default_factory=list, description="Supervisor 一次性生成的工具执行计划")
    decision_log: List[Dict[str, Any]] = Field(default_factory=list, description="决策与理由")
    decision_iterations: int = Field(default=0, description="自主决策轮数")
    conflicts: List[Dict[str, Any]] = Field(default_factory=list, description="行程约束冲突")
    resolution_attempts: int = Field(default=0, description="冲突修复次数")
    validation_passed: bool = Field(default=False, description="约束校验是否通过")

    # 元数据
    llm_provider: str = Field(default="deepseek", description="LLM提供商")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class KnowledgeIngestResponse(BaseModel):
    document_id: str
    filename: str
    chunks: int
    characters: int
    pages: int = 0
    native_pages: int = 0
    ocr_pages: int = 0
    extraction_mode: str = "native"
    average_ocr_confidence: Optional[float] = None
    status: str = "indexed"


class BookingQuoteRequest(BaseModel):
    session_id: str
    city: str
    check_in: str
    check_out: str
    guests: int = Field(default=1, ge=1, le=20)
    hotel_name: Optional[str] = None
    max_price: Optional[int] = Field(default=None, ge=0)


class BookingHoldRequest(BaseModel):
    session_id: str
    offer_id: str
    guest_name: str = Field(min_length=1, max_length=80)
    contact_phone: str = Field(min_length=5, max_length=30)


class BookingConfirmRequest(BaseModel):
    session_id: str
    hold_id: str
    user_confirmed: bool = False
