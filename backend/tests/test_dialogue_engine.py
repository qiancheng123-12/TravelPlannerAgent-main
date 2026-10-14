import pytest

from app.core.memory import ConversationMemory
from app.services import dialogue_engine as module


@pytest.mark.asyncio
async def test_slot_filling_asks_only_for_missing_information(monkeypatch):
    def no_llm(*args, **kwargs):
        raise ValueError("offline")

    monkeypatch.setattr(module, "get_llm", no_llm)
    memory = ConversationMemory("slot-test")
    engine = module.DialogueEngine()

    first = await engine.analyze(
        "宁波到北京三日游，2个人",
        memory,
        "deepseek",
    )
    assert first.intent == "plan_trip"
    assert first.slots["origin"] == "宁波"
    assert first.slots["city"] == "北京"
    assert first.slots["guests"] == 2
    assert first.slots["travel_days"] == 3
    assert first.missing_slots == ["start_date"]

    second = await engine.analyze("10月1日出发", memory, "deepseek")
    assert not second.missing_slots
    assert second.slots["travel_days"] == 3
    assert second.slots["end_date"]


@pytest.mark.asyncio
async def test_dot_date_and_string_preferences_are_normalised(monkeypatch):
    def no_llm(*args, **kwargs):
        raise ValueError("offline")

    monkeypatch.setattr(module, "get_llm", no_llm)
    memory = ConversationMemory("dot-date-test")
    memory.set_preference("dialogue_slots", {"preferences": "自然风光、摄影"})
    engine = module.DialogueEngine()

    first = await engine.analyze("从上海到杭州西湖一日游，2人，自驾出行", memory, "deepseek")
    assert first.missing_slots == ["start_date"]
    assert first.slots["preferences"] == ["自然风光", "摄影"]

    second = await engine.analyze("9.30", memory, "deepseek")
    assert not second.missing_slots
    assert second.slots["start_date"].endswith("-09-30")
    assert second.slots["end_date"] == second.slots["start_date"]


@pytest.mark.asyncio
async def test_dialogue_asks_origin_and_guests_when_missing(monkeypatch):
    def no_llm(*args, **kwargs):
        raise ValueError("offline")

    monkeypatch.setattr(module, "get_llm", no_llm)
    memory = ConversationMemory("required-trip-facts")
    engine = module.DialogueEngine()

    first = await engine.analyze("帮我规划北京三日游", memory, "deepseek")
    assert first.missing_slots[0] == "origin"
    assert "从哪里出发" in first.response

    second = await engine.analyze("温州出发", memory, "deepseek")
    assert second.slots["city"] == "北京"
    assert second.slots["origin"] == "温州"
    assert second.missing_slots[0] == "start_date"

    third = await engine.analyze("10月10日出发", memory, "deepseek")
    assert third.missing_slots[0] == "guests"

    completed = await engine.analyze("两个人", memory, "deepseek")
    assert not completed.missing_slots
    assert completed.slots["guests"] == 2


@pytest.mark.asyncio
async def test_bare_unknown_city_is_accepted_while_asking_for_origin(monkeypatch):
    def no_llm(*args, **kwargs):
        raise ValueError("offline")

    monkeypatch.setattr(module, "get_llm", no_llm)
    memory = ConversationMemory("unknown-origin")
    engine = module.DialogueEngine()

    await engine.analyze("想去杭州玩", memory, "deepseek")
    result = await engine.analyze("温州", memory, "deepseek")

    assert result.slots["city"] == "杭州"
    assert result.slots["origin"] == "温州"
    assert result.missing_slots[0] == "start_date"
