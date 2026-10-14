"""以 LLM 为中枢的自由文本意图识别与 Slot Filling。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from ..core.llm import get_llm


INTENT_REQUIRED_SLOTS = {
    "plan_trip": ["city", "origin", "start_date", "travel_days", "guests"],
    "weather": ["city"],
    "poi": ["city"],
    "hotel": ["city"],
    "booking": ["city", "start_date", "end_date"],
    "general": [],
}

SLOT_QUESTIONS = {
    "city": ("想去哪个城市或目的地？", ["北京", "成都", "杭州"]),
    "origin": ("从哪里出发？", ["北京出发", "上海出发", "杭州出发"]),
    "start_date": ("计划哪天出发？请告诉我具体日期。", ["本周六", "下周一", "2026-10-01"]),
    "travel_days": ("准备玩几天？", ["2天", "3天", "5天"]),
    "guests": ("一共几个人出行？", ["1人", "2人", "3人"]),
    "end_date": ("计划哪天退房或返程？", ["住1晚", "住2晚", "2026-10-03"]),
}

KNOWN_PLACES = [
    "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆", "武汉",
    "西安", "厦门", "青岛", "大连", "天津", "长沙", "昆明", "贵阳", "三亚", "拉萨",
    "哈尔滨", "沈阳", "长春", "兰州", "西宁", "南昌", "合肥", "无锡", "宁波", "桂林",
    "新疆", "西藏", "内蒙古", "云南", "四川", "青海", "甘肃",
]

@dataclass
class DialogueDecision:
    intent: str
    slots: Dict[str, Any]
    missing_slots: List[str] = field(default_factory=list)
    response: str = ""
    quick_replies: List[str] = field(default_factory=list)
    extraction_mode: str = "llm"


class DialogueEngine:
    """LLM 优先，确定性解析兜底；槽位状态存入会话记忆。"""

    async def analyze(
        self,
        message: str,
        memory,
        provider: str,
        long_term_context: str = "",
    ) -> DialogueDecision:
        previous = dict(memory.get_preference("dialogue_slots", {}))
        intent = str(memory.get_preference("active_intent", "general"))
        extracted: Dict[str, Any] = {}
        extraction_mode = "llm"

        fallback_intent, deterministic_slots = self._fallback_extract(message, intent)

        try:
            llm = get_llm(provider, temperature=0, max_tokens=500)
            response = await llm.ainvoke(
                self._prompt(message, memory.get_history_str(), previous, long_term_context)
            )
            payload = self._parse_json(str(response.content))
            candidate_intent = str(payload.get("intent", "general"))
            if candidate_intent in INTENT_REQUIRED_SLOTS:
                intent = candidate_intent
            extracted = payload.get("slots", {}) if isinstance(payload.get("slots"), dict) else {}
        except Exception:
            extraction_mode = "deterministic_fallback"
            intent = fallback_intent
            extracted = {}

        if intent == "general" and fallback_intent != "general":
            intent = fallback_intent

        # 已知目的地、正在追问出发地时，用户只回复一个地名，应解释为出发地。
        if previous.get("city") and not previous.get("origin"):
            bare_origin = re.fullmatch(
                r"\s*(?:从)?([\u4e00-\u9fff]{2,12}?)(?:出发|启程)?\s*",
                message,
            )
            if (
                deterministic_slots.get("city")
                and not re.search(r"(?:去|到|前往|飞往|目的地)", message)
            ):
                deterministic_slots["origin"] = deterministic_slots.pop("city")
            elif bare_origin:
                deterministic_slots["origin"] = bare_origin.group(1)

        # 出发地和人数必须来自用户当前表达，不能由模型自行补齐。
        for key in ("origin", "guests"):
            if key not in deterministic_slots:
                extracted.pop(key, None)

        llm_slots = {k: v for k, v in extracted.items() if v not in (None, "", [])}
        extracted = {**llm_slots, **deterministic_slots}
        slots = self._normalise_slots({**previous, **extracted})

        if slots.get("start_date") and slots.get("end_date") and not slots.get("travel_days"):
            try:
                start = datetime.strptime(slots["start_date"], "%Y-%m-%d").date()
                end = datetime.strptime(slots["end_date"], "%Y-%m-%d").date()
                slots["travel_days"] = max(1, (end - start).days + 1)
            except (ValueError, TypeError):
                pass
        elif slots.get("start_date") and slots.get("travel_days") and not slots.get("end_date"):
            try:
                start = datetime.strptime(slots["start_date"], "%Y-%m-%d").date()
                slots["end_date"] = (start + timedelta(days=int(slots["travel_days"]) - 1)).isoformat()
            except (ValueError, TypeError):
                pass

        memory.set_preference("dialogue_slots", slots)
        memory.set_preference("active_intent", intent)
        for key, value in slots.items():
            memory.set_preference(key, value)

        missing = self._missing_slots(intent, slots)
        if missing:
            question, replies = SLOT_QUESTIONS[missing[0]]
            known = self._known_summary(slots)
            response_text = f"好的{known}。{question}" if known else question
            return DialogueDecision(
                intent=intent,
                slots=slots,
                missing_slots=missing,
                response=response_text,
                quick_replies=replies,
                extraction_mode=extraction_mode,
            )

        return DialogueDecision(intent=intent, slots=slots, extraction_mode=extraction_mode)

    @staticmethod
    def _prompt(
        message: str,
        history: str,
        slots: Dict[str, Any],
        long_term_context: str = "",
    ) -> str:
        return f"""你是旅行助手的中枢路由模型。结合多轮上下文识别当前意图并抽取槽位。
意图只能是 plan_trip/weather/poi/hotel/booking/general。
槽位可包含 city,origin,start_date,end_date,travel_days,guests,budget,preferences,transportation,accommodation。
今天是 {date.today().isoformat()}。日期必须转成 YYYY-MM-DD；budget 输出 [最低,最高]；不知道的字段不要猜。
已有槽位: {json.dumps(slots, ensure_ascii=False)}
与当前消息相关的用户长期偏好: {long_term_context or "无"}
最近对话: {history[-1600:]}
当前消息: {message}
长期偏好可用于补充 preferences、transportation、accommodation、budget 等个性化字段，但不得用历史行程猜测本次城市、出发地、人数和日期。
只返回 JSON：{{"intent":"plan_trip","slots":{{}},"reason":"简述依据"}}"""

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            raise ValueError("LLM 未返回 JSON")
        return json.loads(match.group(0))

    def _fallback_extract(self, message: str, previous_intent: str) -> tuple[str, Dict[str, Any]]:
        lower = message.lower()
        route_origin, route_city = self._extract_origin_and_city(message)
        if any(word in lower for word in ["预订", "订房", "下单", "锁单", "支付"]):
            intent = "booking"
        elif (
            bool(route_origin and route_city)
            or
            any(word in lower for word in ["规划", "行程", "几日游", "旅游", "旅行", "怎么玩", "想去"])
            or re.search(r"[一二两三四五六七八九十\d]{1,3}\s*(?:日游|天游)", message)
        ):
            intent = "plan_trip"
        elif any(word in lower for word in ["天气", "气温", "下雨"]):
            intent = "weather"
        elif any(word in lower for word in ["酒店", "住宿", "住哪"]):
            intent = "hotel"
        elif any(word in lower for word in ["景点", "好玩", "去哪"]):
            intent = "poi"
        else:
            intent = previous_intent if previous_intent != "general" else "general"

        slots: Dict[str, Any] = {}
        origin, city = route_origin, route_city
        if city:
            slots["city"] = city
        if origin:
            slots["origin"] = origin

        dates = self._extract_dates(message)
        if dates:
            slots["start_date"] = dates[0]
        if len(dates) > 1:
            slots["end_date"] = dates[1]

        day_match = re.search(r"([一二两三四五六七八九十\d]{1,3})\s*(?:天(?:游|行程)?|日(?:游|行程))", message)
        if day_match:
            slots["travel_days"] = self._cn_number(day_match.group(1))

        budget_match = re.search(r"(?:预算|不超过|控制在)\s*(\d+)(?:\s*[-到至~]\s*(\d+))?\s*元?", message)
        if budget_match:
            first = int(budget_match.group(1))
            second = int(budget_match.group(2) or first)
            slots["budget"] = [0 if not budget_match.group(2) else first, second]
        preferences = [word for word in ["历史文化", "自然风光", "美食", "亲子", "摄影", "购物", "博物馆"] if word in message]
        if preferences:
            slots["preferences"] = preferences
        for mode in ["飞机", "高铁", "火车", "自驾", "公共交通", "地铁", "打车", "步行"]:
            if mode in message:
                slots["transportation"] = mode
                break

        guests = self._extract_guests(message)
        if guests:
            slots["guests"] = guests

        return intent, slots

    @staticmethod
    def _extract_origin_and_city(message: str) -> tuple[str, str]:
        places = sorted(KNOWN_PLACES, key=len, reverse=True)
        joined = "|".join(re.escape(place) for place in places)
        pair = re.search(
            rf"(?:从)?(?P<origin>{joined})(?:出发)?\s*(?:到|去|前往|飞往)\s*(?P<city>{joined})",
            message,
        )
        if pair:
            return pair.group("origin"), pair.group("city")

        origin_match = re.search(
            rf"(?:从(?P<from_origin>{joined})(?:出发)?|(?P<plain_origin>{joined})出发)",
            message,
        )
        generic_origin_match = re.fullmatch(
            r"\s*(?:从)?(?P<origin>[\u4e00-\u9fff]{2,12}?)(?:出发|启程)\s*",
            message,
        )
        destination_match = re.search(
            rf"(?:去|到|前往|飞往|目的地(?:是|为)?)(?P<city>{joined})",
            message,
        )
        origin = (
            (origin_match.group("from_origin") or origin_match.group("plain_origin"))
            if origin_match
            else (generic_origin_match.group("origin") if generic_origin_match else "")
        )
        if destination_match:
            return origin, destination_match.group("city")
        mentioned = [place for place in places if place in message and place != origin]
        return origin, mentioned[0] if mentioned else ""

    @staticmethod
    def _extract_city(message: str) -> str:
        return DialogueEngine._extract_origin_and_city(message)[1]

    @staticmethod
    def _extract_guests(message: str) -> int:
        if any(word in message for word in ("独自", "一个人", "单人")):
            return 1
        if any(word in message for word in ("情侣", "夫妻", "两口子")):
            return 2
        if "一家三口" in message:
            return 3
        match = re.search(r"([一二两三四五六七八九十\d]{1,3})\s*(?:个|位)?人", message)
        return DialogueEngine._cn_number(match.group(1)) if match else 0

    @staticmethod
    def _missing_slots(intent: str, slots: Dict[str, Any]) -> List[str]:
        return [name for name in INTENT_REQUIRED_SLOTS[intent] if not slots.get(name)]

    @staticmethod
    def _extract_dates(message: str) -> List[str]:
        results = []
        # 支持 2026-09-30、2026/9/30、9月30日、9.30 等常见输入。
        pattern = r"(?:(20\d{2})[年./\-])?(\d{1,2})[月./\-](\d{1,2})日?"
        for year, month, day in re.findall(pattern, message):
            target_year = int(year or date.today().year)
            try:
                value = date(target_year, int(month), int(day))
                if not year and value < date.today():
                    value = date(target_year + 1, int(month), int(day))
                results.append(value.isoformat())
            except ValueError:
                continue
        return results

    @staticmethod
    def _cn_number(value: str) -> int:
        if value.isdigit():
            return int(value)
        mapping = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        if value in mapping:
            return mapping[value]
        if value.startswith("十"):
            return 10 + mapping.get(value[1:], 0)
        if "十" in value:
            left, right = value.split("十", 1)
            return mapping.get(left, 1) * 10 + mapping.get(right, 0)
        return 0

    @staticmethod
    def _normalise_slots(slots: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {"city", "origin", "start_date", "end_date", "travel_days", "guests", "budget", "preferences", "transportation", "accommodation"}
        clean = {key: value for key, value in slots.items() if key in allowed and value not in (None, "", [])}

        # LLM 的结构化结果仍可能偶尔返回错误类型，进入 Pydantic 前统一修正。
        preferences = clean.get("preferences")
        if isinstance(preferences, str):
            clean["preferences"] = [
                item.strip()
                for item in re.split(r"[、,，;；/\s]+", preferences)
                if item.strip()
            ]
        elif isinstance(preferences, list):
            clean["preferences"] = [str(item).strip() for item in preferences if str(item).strip()]
        elif preferences is not None:
            clean.pop("preferences", None)

        budget = clean.get("budget")
        if isinstance(budget, str):
            numbers = [int(number) for number in re.findall(r"\d+", budget)]
            clean["budget"] = ([0, numbers[0]] if len(numbers) == 1 else numbers[:2]) if numbers else None
        elif isinstance(budget, (int, float)):
            clean["budget"] = [0, int(budget)]
        elif isinstance(budget, list):
            try:
                numbers = [int(value) for value in budget[:2]]
                clean["budget"] = [0, numbers[0]] if len(numbers) == 1 else sorted(numbers)
            except (TypeError, ValueError):
                clean.pop("budget", None)
        if clean.get("budget") is None:
            clean.pop("budget", None)

        # 模型有时不会遵守 YYYY-MM-DD 约束，例如直接返回“9.30”；
        # 用与用户输入相同的确定性解析器转成规划模型可接受的日期。
        for key in ("start_date", "end_date"):
            if key not in clean:
                continue
            value = str(clean[key]).strip()
            try:
                clean[key] = datetime.strptime(value, "%Y-%m-%d").date().isoformat()
            except ValueError:
                parsed = DialogueEngine._extract_dates(value)
                if parsed:
                    clean[key] = parsed[0]
                else:
                    clean.pop(key, None)

        if "travel_days" in clean:
            try:
                clean["travel_days"] = max(1, min(30, int(clean["travel_days"])))
            except (TypeError, ValueError):
                clean.pop("travel_days", None)
        if "guests" in clean:
            try:
                clean["guests"] = max(1, min(20, int(clean["guests"])))
            except (TypeError, ValueError):
                clean.pop("guests", None)
        return clean

    @staticmethod
    def _known_summary(slots: Dict[str, Any]) -> str:
        parts = []
        if slots.get("city"):
            parts.append(f"目的地是{slots['city']}")
        if slots.get("origin"):
            parts.append(f"从{slots['origin']}出发")
        if slots.get("start_date"):
            parts.append(f"{slots['start_date']}出发")
        if slots.get("travel_days"):
            parts.append(f"游玩{slots['travel_days']}天")
        if slots.get("guests"):
            parts.append(f"共{slots['guests']}人")
        return "，已记下" + "、".join(parts) if parts else ""


_dialogue_engine = DialogueEngine()


def get_dialogue_engine() -> DialogueEngine:
    return _dialogue_engine
