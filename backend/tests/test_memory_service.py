import json

import pytest

from app.services.memory_service import LongTermMemoryService, SQLiteMemoryService


@pytest.mark.asyncio
async def test_sqlite_conversation_survives_restart(tmp_path):
    database = tmp_path / "memory.sqlite3"
    first = SQLiteMemoryService(str(database))
    await first.initialize()
    memory = await first.load_conversation("user-1", "session-1")
    await first.append_message(memory, "user", "我喜欢历史文化")
    memory.set_preference("dialogue_slots", {"city": "北京"})
    await first.save_session_state(memory)
    await first.close()

    second = SQLiteMemoryService(str(database))
    await second.initialize()
    restored = await second.load_conversation("user-1", "session-1")
    assert "我喜欢历史文化" in restored.get_history_str()
    assert restored.get_preference("dialogue_slots") == {"city": "北京"}
    await second.close()


@pytest.mark.asyncio
async def test_memory_facts_are_upserted_and_isolated(tmp_path):
    repository = SQLiteMemoryService(str(tmp_path / "profile.sqlite3"))
    await repository.initialize()
    await repository.set_memory_enabled("user-1", True)

    first = await repository.upsert_fact(
        "user-1", "transportation", "交通偏好", "地铁", "用户偏好地铁", 0.8, "s1"
    )
    updated = await repository.upsert_fact(
        "user-1", "transportation", "交通偏好", "自驾", "用户偏好自驾", 0.95, "s2"
    )
    assert first["memory_id"] == updated["memory_id"]
    assert updated["value"] == "自驾"
    assert len(await repository.list_facts("user-1")) == 1
    assert await repository.list_facts("user-2") == []
    await repository.close()


def test_rule_fallback_extracts_only_explicit_preferences():
    extracted = LongTermMemoryService._fallback_candidates("我喜欢自然风光，以后出行偏好自驾")
    assert {item["key"] for item in extracted} == {"interests", "transportation"}
    assert LongTermMemoryService._fallback_candidates("明天去杭州") == []


@pytest.mark.asyncio
async def test_trip_history_can_be_restored_and_deleted(tmp_path):
    repository = SQLiteMemoryService(str(tmp_path / "trip-history.sqlite3"))
    await repository.initialize()
    plan = {
        "city": "杭州",
        "start_date": "2026-10-08",
        "end_date": "2026-10-10",
        "days": [],
        "weather_info": [],
        "overall_suggestions": "测试历史行程",
        "budget": None,
    }
    await repository.record_trip("user-trip", "session-trip", plan)
    trips = await repository.list_trips("user-trip")
    assert len(trips) == 1

    restored = await repository.get_trip("user-trip", trips[0]["trip_id"])
    assert restored["plan"] == plan
    with pytest.raises(KeyError):
        await repository.get_trip("another-user", trips[0]["trip_id"])

    assert await repository.delete_trip("user-trip", trips[0]["trip_id"]) is True
    assert await repository.list_trips("user-trip") == []
    await repository.close()


@pytest.mark.asyncio
async def test_multiple_trips_in_one_chat_are_kept_separately(tmp_path):
    repository = SQLiteMemoryService(str(tmp_path / "multi-trip.sqlite3"))
    await repository.initialize()
    shanghai = {
        "city": "上海",
        "start_date": "2026-10-09",
        "end_date": "2026-10-13",
        "days": [],
    }
    beijing = {
        "city": "北京",
        "start_date": "2026-10-23",
        "end_date": "2026-10-27",
        "days": [],
    }

    await repository.record_trip("user-multi", "same-chat", shanghai)
    await repository.record_trip("user-multi", "same-chat", beijing)
    await repository.record_trip("user-multi", "same-chat", {**shanghai, "budget": 5000})

    trips = await repository.list_trips("user-multi")
    assert len(trips) == 2
    assert {trip["city"] for trip in trips} == {"上海", "北京"}
    shanghai_row = next(trip for trip in trips if trip["city"] == "上海")
    restored = await repository.get_trip("user-multi", shanghai_row["trip_id"])
    assert restored["plan"]["budget"] == 5000
    await repository.close()


@pytest.mark.asyncio
async def test_clearing_profile_does_not_delete_trip_history(tmp_path):
    repository = SQLiteMemoryService(str(tmp_path / "separated-memory.sqlite3"))
    await repository.initialize()
    await repository.set_memory_enabled("user-separated", True)
    await repository.upsert_fact(
        "user-separated", "pace", "行程节奏", "轻松", "用户偏好轻松行程", 0.9, "session-1"
    )
    await repository.record_trip(
        "user-separated",
        "session-1",
        {"city": "杭州", "start_date": "2026-10-09", "end_date": "2026-10-10", "days": []},
    )

    assert await repository.clear_profile("user-separated") == 1
    assert await repository.list_facts("user-separated") == []
    assert len(await repository.list_trips("user-separated")) == 1
    await repository.close()


@pytest.mark.asyncio
async def test_legacy_trip_results_can_be_imported_without_duplicates(tmp_path):
    repository = SQLiteMemoryService(str(tmp_path / "legacy.sqlite3"))
    await repository.initialize()
    results = tmp_path / "saved_results"
    results.mkdir()
    plan = {
        "city": "宁波",
        "start_date": "2026-10-04",
        "end_date": "2026-10-05",
        "days": [],
    }
    (results / "valid.json").write_text(
        json.dumps({"session_id": "legacy-session", "result": plan}, ensure_ascii=False),
        encoding="utf-8",
    )
    (results / "incomplete.json").write_text(
        json.dumps({"session_id": "unfinished", "result": None}),
        encoding="utf-8",
    )

    first = await repository.import_legacy_trips("legacy-user", results)
    second = await repository.import_legacy_trips("legacy-user", results)

    assert first == {"imported": 1, "skipped": 1}
    assert second == {"imported": 1, "skipped": 1}
    trips = await repository.list_trips("legacy-user")
    assert len(trips) == 1
    restored = await repository.get_trip("legacy-user", trips[0]["trip_id"])
    assert restored["plan"] == plan
    await repository.close()
