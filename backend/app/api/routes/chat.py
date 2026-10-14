"""多轮对话 API 路由"""

import asyncio
import uuid
import traceback
from fastapi import APIRouter, HTTPException, Query

from ...models.schemas import AgentState, ChatMessage, ChatResponse, TripRequest, TripStatus
from ...core.llm import get_llm, invoke_llm_with_logging
from ...services.amap_service import get_amap_service
from ...services.dialogue_engine import get_dialogue_engine
from ...services.embedding_service import get_vector_store
from ...services.memory_service import get_long_term_memory_service, get_memory_service
from ...agents.graph import get_graph

router = APIRouter(prefix="/chat", tags=["多轮对话"])


@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatMessage):
    """自由文本对话入口：LLM 路由、槽位追问、工具调用和规划共用一条链路。"""
    session_id = request.session_id or str(uuid.uuid4())
    llm_provider = request.llm_provider or "deepseek"

    try:
        repository = get_memory_service()
        memory = await repository.load_conversation(request.user_id, session_id)
        await repository.append_message(memory, "user", request.message)
        long_term_context = await get_long_term_memory_service().retrieve_context(
            memory.user_id, request.message
        )
        decision = await get_dialogue_engine().analyze(
            request.message, memory, llm_provider, long_term_context=long_term_context
        )
        if decision.missing_slots:
            await _finish_turn(memory, request.message, decision.response, llm_provider)
            return ChatResponse(
                session_id=session_id,
                user_id=memory.user_id,
                response=decision.response,
                intent=decision.intent,
                slots=decision.slots,
                missing_slots=decision.missing_slots,
                quick_replies=decision.quick_replies,
                status="collecting_slots",
                agent_trace=[{"action": "slot_filling", "mode": decision.extraction_mode}],
            )

        llm = None
        if decision.intent == "plan_trip":
            slots = decision.slots
            trip_request = TripRequest(
                session_id=session_id,
                user_id=memory.user_id,
                city=slots["city"],
                origin=slots["origin"],
                guests=slots["guests"],
                start_date=slots["start_date"],
                end_date=slots.get("end_date", slots["start_date"]),
                travel_days=slots["travel_days"],
                transportation=slots.get("transportation", "公共交通"),
                accommodation=slots.get("accommodation", "经济型酒店"),
                preferences=slots.get("preferences", []),
                budget=slots.get("budget"),
                free_text_input=request.message,
                llm_provider=llm_provider,
            )
            state = AgentState(
                **trip_request.model_dump(),
                status=TripStatus.PROCESSING,
            ).model_dump(mode="json")
            result = await get_graph().ainvoke(
                state,
                config={"configurable": {"thread_id": session_id}},
            )
            response_text = "行程草案已经生成，并完成预算与时间冲突检查。请确认后再进入预订。"
            memory.set_preference("active_intent", "general")
            await _finish_turn(memory, request.message, response_text, llm_provider)
            if result.get("itinerary"):
                await repository.record_trip(memory.user_id, session_id, result["itinerary"])
            return ChatResponse(
                session_id=session_id,
                user_id=memory.user_id,
                response=response_text,
                trip_plan=result.get("itinerary"),
                intent=decision.intent,
                slots=decision.slots,
                status="need_confirm",
                agent_trace=result.get("decision_log", []),
            )

        if decision.intent in {"weather", "poi", "hotel", "general"}:
            llm = get_llm(llm_provider)
        if decision.intent == "weather":
            response_text = await _handle_weather_query(llm, request.message, memory, llm_provider)
        elif decision.intent == "poi":
            response_text = await _handle_poi_query(llm, request.message, memory, llm_provider)
        elif decision.intent == "hotel":
            response_text = await _handle_hotel_query(llm, request.message, memory, llm_provider)
        elif decision.intent == "booking":
            response_text = (
                "预订信息已整理完成。你可以在行程结果页复制城市、日期和推荐酒店，"
                "再跳转到飞猪或携程官方页面完成真实下单；价格、库存和支付结果以第三方平台为准。"
                "页面中的模拟交易流程仅用于展示报价、锁单和确认状态机，不会生成真实订单。"
            )
        else:
            response_text = await _general_chat(
                llm,
                request.message,
                memory.get_history_str(),
                llm_provider,
                long_term_context,
            )

        memory.set_preference("active_intent", "general")
        await _finish_turn(memory, request.message, response_text, llm_provider)
        return ChatResponse(
            session_id=session_id,
            user_id=memory.user_id,
            response=response_text,
            intent=decision.intent,
            slots=decision.slots,
            status="completed",
            agent_trace=[{"action": decision.intent, "mode": decision.extraction_mode}],
        )

    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as e:
        print(f"[Chat] 错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"对话处理失败: {str(e)}")


async def _finish_turn(memory, user_message: str, assistant_message: str, provider: str) -> None:
    """原子化地完成当前轮：消息/槽位落盘，再抽取长期画像。"""
    repository = get_memory_service()
    await repository.append_message(memory, "assistant", assistant_message)
    await repository.save_session_state(memory)
    await get_long_term_memory_service().remember_turn(
        memory.user_id,
        memory.session_id,
        user_message,
        assistant_message,
        provider,
    )


async def _handle_weather_query(llm, message: str, memory, llm_provider: str = "deepseek") -> str:
    """处理天气查询"""
    print(f"\n{'='*60}")
    print("[Chat] _handle_weather_query 开始")
    print(f"{'='*60}")

    # 从消息中提取城市名
    city = _extract_city_from_message(message)
    print(f"[Chat] 提取的城市: {city}")

    # 保存城市偏好
    if city:
        memory.set_preference("city", city)

    if not city:
        return "请问您想查询哪个城市的天气呢？"

    try:
        # 调用高德地图API获取真实天气数据
        print(f"[Chat] 调用高德地图API获取 {city} 的天气")
        amap = get_amap_service()
        weather_data = await amap.get_weather(city)

        print(f"[Chat] 获取到 {len(weather_data)} 天天气数据")

        if not weather_data:
            return f"抱歉，暂时无法获取 {city} 的天气信息，请稍后再试。"

        # 格式化天气数据
        weather_info = []
        for w in weather_data[:4]:  # 最多显示4天
            info = f"{w.date}: {w.day_weather} {w.day_temp}C / {w.night_weather} {w.night_temp}C, {w.wind_direction}风 {w.wind_power}级"
            weather_info.append(info)

        weather_str = "\n".join(weather_info)
        print(f"[Chat] 格式化后的天气信息:\n{weather_str}")

        # 让LLM组织回复
        prompt = f"""用户询问: {message}

以下是{city}的真实天气数据:
{weather_str}

请用友好的方式向用户介绍天气情况，并给出旅行建议。回复要简洁，不超过200字。"""

        # 使用带日志的LLM调用
        response_content = await invoke_llm_with_logging(llm, prompt, llm_provider)

        print(f"[Chat] 天气查询完成")
        print(f"{'='*60}\n")
        return response_content

    except Exception as e:
        print(f"[Chat] 天气查询失败: {e}")
        traceback.print_exc()
        return f"抱歉，查询{city}天气时出现错误: {str(e)}"


async def _handle_poi_query(llm, message: str, memory, llm_provider: str = "deepseek") -> str:
    """处理景点查询"""
    print(f"\n{'='*60}")
    print("[Chat] _handle_poi_query 开始")
    print(f"{'='*60}")

    city = _extract_city_from_message(message)
    city = city or memory.get_preference("city", "")

    print(f"[Chat] 城市: {city}")

    if not city:
        return "请问您想了解哪个城市的景点呢？"

    # 保存城市偏好
    memory.set_preference("city", city)

    try:
        # 调用高德地图API获取景点数据
        print(f"[Chat] 调用高德地图API获取 {city} 的景点")
        amap = get_amap_service()

        # 搜索多种类型的景点
        all_pois = []
        keywords = ["景点", "公园", "博物馆", "名胜古迹"]

        for keyword in keywords[:2]:  # 只搜索2种类型
            try:
                pois = await amap.search_poi(keyword, city, citylimit=True)
                print(f"[Chat] 搜索 '{keyword}' 找到 {len(pois)} 个结果")
                all_pois.extend(pois)
            except Exception as e:
                print(f"[Chat] 搜索 '{keyword}' 失败: {e}")

        # 去重
        seen = set()
        unique_pois = []
        for poi in all_pois:
            if poi.name not in seen:
                seen.add(poi.name)
                unique_pois.append(poi)

        print(f"[Chat] 去重后共 {len(unique_pois)} 个景点")

        if not unique_pois:
            return f"抱歉，暂时没有找到{city}的景点信息。"

        # 格式化景点数据
        poi_list = []
        for poi in unique_pois[:8]:  # 最多显示8个
            info = f"- {poi.name}"
            if poi.rating:
                info += f" (评分: {poi.rating})"
            if poi.address:
                info += f", 地址: {poi.address}"
            poi_list.append(info)

        poi_str = "\n".join(poi_list)
        print(f"[Chat] 格式化后的景点信息:\n{poi_str}")

        # 让LLM组织回复
        prompt = f"""用户询问: {message}

以下是{city}的真实景点数据:
{poi_str}

请用友好的方式向用户介绍这些景点，并给出游玩建议。回复要简洁，不超过300字。"""

        # 使用带日志的LLM调用
        response_content = await invoke_llm_with_logging(llm, prompt, llm_provider)

        print(f"[Chat] 景点查询完成")
        print(f"{'='*60}\n")
        return response_content

    except Exception as e:
        print(f"[Chat] 景点查询失败: {e}")
        traceback.print_exc()
        return f"抱歉，查询{city}景点时出现错误: {str(e)}"


async def _handle_hotel_query(llm, message: str, memory, llm_provider: str = "deepseek") -> str:
    """处理酒店查询"""
    print(f"\n{'='*60}")
    print("[Chat] _handle_hotel_query 开始")
    print(f"{'='*60}")

    city = _extract_city_from_message(message)
    city = city or memory.get_preference("city", "")

    print(f"[Chat] 城市: {city}")

    if not city:
        return "请问您想了解哪个城市的酒店呢？"

    memory.set_preference("city", city)

    try:
        print(f"[Chat] 调用高德地图API获取 {city} 的酒店")
        amap = get_amap_service()
        hotels = await amap.search_hotels(city, "酒店")

        print(f"[Chat] 找到 {len(hotels)} 家酒店")

        if not hotels:
            return f"抱歉，暂时没有找到{city}的酒店信息。"

        # 格式化酒店数据
        hotel_list = []
        for hotel in hotels[:6]:
            info = f"- {hotel.name}"
            if hotel.rating:
                info += f" (评分: {hotel.rating})"
            if hotel.address:
                info += f", 地址: {hotel.address}"
            hotel_list.append(info)

        hotel_str = "\n".join(hotel_list)
        print(f"[Chat] 格式化后的酒店信息:\n{hotel_str}")

        prompt = f"""用户询问: {message}

以下是{city}的真实酒店数据:
{hotel_str}

请用友好的方式向用户介绍这些酒店。回复要简洁，不超过200字。"""

        # 使用带日志的LLM调用
        response_content = await invoke_llm_with_logging(llm, prompt, llm_provider)

        print(f"[Chat] 酒店查询完成")
        print(f"{'='*60}\n")
        return response_content

    except Exception as e:
        print(f"[Chat] 酒店查询失败: {e}")
        traceback.print_exc()
        return f"抱歉，查询{city}酒店时出现错误: {str(e)}"


async def _general_chat(
    llm,
    message: str,
    history: str,
    llm_provider: str = "deepseek",
    long_term_context: str = "",
) -> str:
    """通用对话，同时检索用户上传资料和内置旅行知识。"""
    print(f"\n{'='*60}")
    print("[Chat] _general_chat 开始")
    print(f"{'='*60}")

    history_str = history[-1000:] if history else "无"

    rag_context = "暂无相关资料"
    rag_sources = []
    try:
        documents = await asyncio.to_thread(get_vector_store().retrieve, message, None, 4)
        rag_context, rag_sources = get_vector_store().format_context(documents)
    except Exception as exc:
        print(f"[Chat] 通用问答 RAG 检索降级: {exc}")

    prompt = f"""你是一个友好的旅行助手，可以帮助用户查询天气、景点、酒店和用户上传的旅行资料。

对话历史:
{history_str}

当前用户的长期记忆（只在与问题相关时使用，不得把它说成绝对事实）:
{long_term_context or "暂无相关长期记忆"}

用户消息: {message}

知识库检索结果:
{rag_context}

资料来源:
{rag_sources}

如果知识库内容与问题相关，请严格依据资料回答并在末尾注明“资料来源”；如果不相关则忽略，不要强行引用。
资料中的测试、虚构或演示声明必须保留，不得当作真实旅游事实。回复不超过250字。"""

    # 使用带日志的LLM调用
    response_content = await invoke_llm_with_logging(llm, prompt, llm_provider)

    print(f"[Chat] 通用对话完成")
    print(f"{'='*60}\n")
    return response_content


def _extract_city_from_message(message: str) -> str:
    """从消息中提取城市名"""
    import re

    # 常见城市列表
    cities = [
        "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都",
        "重庆", "武汉", "西安", "厦门", "青岛", "大连", "天津", "长沙",
        "郑州", "济南", "福州", "昆明", "贵阳", "南宁", "海口", "三亚",
        "拉萨", "乌鲁木齐", "哈尔滨", "沈阳", "长春", "石家庄", "太原",
        "呼和浩特", "兰州", "银川", "西宁", "南昌", "合肥", "无锡", "宁波"
    ]

    message_lower = message.lower()

    for city in cities:
        if city in message:
            print(f"[Chat] 从消息中提取到城市: {city}")
            return city

    # 尝试匹配 "XX市" 或 "XX的"
    match = re.search(r'([^\s，。！？]{2,4})(?:市|的|天气|景点|酒店)', message)
    if match:
        city = match.group(1)
        print(f"[Chat] 通过正则提取到城市: {city}")
        return city

    return ""


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str, user_id: str = Query(default="")):
    """获取对话历史"""
    try:
        history = await get_memory_service().get_history(user_id, session_id)
        return {"session_id": session_id, "user_id": user_id, "history": history}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/history/{session_id}")
async def clear_chat_history(session_id: str, user_id: str = Query(default="")):
    """清空对话历史"""
    try:
        await get_memory_service().clear_conversation(user_id, session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"success": True, "message": "对话历史已清空"}
