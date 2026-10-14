"""SQLite + Chroma 长期记忆服务。

SQLite 是事实来源，保存会话、消息、用户画像和历史行程；Chroma 只负责
对用户画像做语义召回。即使 Embedding 服务临时不可用，聊天记录和画像
仍会可靠落盘，并自动降级为 SQLite 最近记忆。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
from langchain_core.messages import AIMessage, HumanMessage

from ..core.config import get_settings
from ..core.llm import get_llm
from ..core.memory import ConversationMemory
from .embedding_service import get_vector_store


ALLOWED_MEMORY_KEYS = {
    "interests": "兴趣偏好",
    "transportation": "交通偏好",
    "accommodation": "住宿偏好",
    "budget": "预算习惯",
    "dietary": "饮食偏好",
    "pace": "行程节奏",
    "companions": "同行人偏好",
    "accessibility": "无障碍与体力需求",
    "avoidances": "不喜欢或需要避开的内容",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_identity(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_:@.\-]", "_", (value or "").strip())[:128]
    return cleaned or fallback


class SQLiteMemoryService:
    """应用级异步记忆仓库。"""

    def __init__(self, database_path: Optional[str] = None):
        settings = get_settings()
        backend_root = Path(__file__).resolve().parents[2]
        configured = Path(database_path or settings.memory_database_path)
        if not configured.is_absolute():
            configured = backend_root / configured
        configured.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = configured
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._connection is not None:
            return
        self._connection = await aiosqlite.connect(str(self.database_path))
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                memory_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                state_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES conversations(session_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

            CREATE TABLE IF NOT EXISTS memory_facts (
                memory_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                category TEXT NOT NULL,
                value_json TEXT NOT NULL,
                summary TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.8,
                source_session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, memory_key),
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_memory_facts_user ON memory_facts(user_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS trip_history (
                trip_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                city TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                plan_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_trip_history_user ON trip_history(user_id, updated_at DESC);
            """
        )
        await self._connection.commit()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    def _db(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("长期记忆数据库尚未初始化")
        return self._connection

    async def _ensure_user_and_conversation(self, user_id: str, session_id: str) -> tuple[str, str]:
        user_id = _safe_identity(user_id, f"anonymous-{session_id}")
        session_id = _safe_identity(session_id, "session")
        now = _utc_now()
        db = self._db()
        await db.execute(
            "INSERT INTO users(user_id, created_at, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET updated_at=excluded.updated_at",
            (user_id, now, now),
        )
        # session_id 一旦归属某用户，就不允许被另一个 user_id 接管。
        cursor = await db.execute("SELECT user_id FROM conversations WHERE session_id=?", (session_id,))
        existing = await cursor.fetchone()
        if existing and existing["user_id"] != user_id:
            raise PermissionError("该会话不属于当前用户")
        await db.execute(
            "INSERT INTO conversations(session_id, user_id, created_at, updated_at) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at",
            (session_id, user_id, now, now),
        )
        await db.commit()
        return user_id, session_id

    async def load_conversation(self, user_id: str, session_id: str, max_history: int = 10) -> ConversationMemory:
        async with self._lock:
            user_id, session_id = await self._ensure_user_and_conversation(user_id, session_id)
            db = self._db()
            cursor = await db.execute(
                "SELECT state_json FROM conversations WHERE session_id=? AND user_id=?",
                (session_id, user_id),
            )
            row = await cursor.fetchone()
            try:
                state = json.loads(row["state_json"] or "{}") if row else {}
            except json.JSONDecodeError:
                state = {}
            cursor = await db.execute(
                "SELECT role, content FROM ("
                "SELECT id, role, content FROM messages WHERE session_id=? AND user_id=? "
                "ORDER BY id DESC LIMIT ?"
                ") ORDER BY id ASC",
                (session_id, user_id, max_history * 2),
            )
            rows = await cursor.fetchall()
        history = [
            HumanMessage(content=item["content"])
            if item["role"] == "user"
            else AIMessage(content=item["content"])
            for item in rows
        ]
        return ConversationMemory(
            session_id=session_id,
            user_id=user_id,
            max_history=max_history,
            history=history,
            preferences=state,
        )

    async def append_message(self, memory: ConversationMemory, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("不支持的消息角色")
        if role == "user":
            memory.add_user_message(content)
        else:
            memory.add_ai_message(content)
        async with self._lock:
            db = self._db()
            await db.execute(
                "INSERT INTO messages(session_id, user_id, role, content, created_at) VALUES(?, ?, ?, ?, ?)",
                (memory.session_id, memory.user_id, role, content, _utc_now()),
            )
            await db.execute(
                "UPDATE conversations SET updated_at=? WHERE session_id=? AND user_id=?",
                (_utc_now(), memory.session_id, memory.user_id),
            )
            await db.commit()

    async def save_session_state(self, memory: ConversationMemory) -> None:
        async with self._lock:
            db = self._db()
            await db.execute(
                "UPDATE conversations SET state_json=?, updated_at=? WHERE session_id=? AND user_id=?",
                (
                    json.dumps(memory.get_all_preferences(), ensure_ascii=False),
                    _utc_now(),
                    memory.session_id,
                    memory.user_id,
                ),
            )
            await db.commit()

    async def get_history(self, user_id: str, session_id: str) -> List[Dict[str, str]]:
        async with self._lock:
            user_id, session_id = await self._ensure_user_and_conversation(user_id, session_id)
            cursor = await self._db().execute(
                "SELECT role, content FROM ("
                "SELECT id, role, content FROM messages WHERE session_id=? AND user_id=? "
                "ORDER BY id DESC LIMIT 200"
                ") ORDER BY id ASC",
                (session_id, user_id),
            )
            rows = await cursor.fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    async def clear_conversation(self, user_id: str, session_id: str) -> None:
        async with self._lock:
            user_id, session_id = await self._ensure_user_and_conversation(user_id, session_id)
            db = self._db()
            await db.execute("DELETE FROM messages WHERE session_id=? AND user_id=?", (session_id, user_id))
            await db.execute(
                "UPDATE conversations SET state_json='{}', updated_at=? WHERE session_id=? AND user_id=?",
                (_utc_now(), session_id, user_id),
            )
            await db.commit()

    async def memory_enabled(self, user_id: str) -> bool:
        async with self._lock:
            db = self._db()
            cursor = await db.execute("SELECT memory_enabled FROM users WHERE user_id=?", (user_id,))
            row = await cursor.fetchone()
        return bool(row["memory_enabled"]) if row else True

    async def set_memory_enabled(self, user_id: str, enabled: bool) -> None:
        async with self._lock:
            now = _utc_now()
            db = self._db()
            await db.execute(
                "INSERT INTO users(user_id, memory_enabled, created_at, updated_at) VALUES(?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET memory_enabled=excluded.memory_enabled, updated_at=excluded.updated_at",
                (_safe_identity(user_id, "anonymous"), int(enabled), now, now),
            )
            await db.commit()

    async def upsert_fact(
        self,
        user_id: str,
        memory_key: str,
        category: str,
        value: Any,
        summary: str,
        confidence: float,
        source_session_id: str,
    ) -> Dict[str, Any]:
        user_id = _safe_identity(user_id, "anonymous")
        memory_key = _safe_identity(memory_key, "preference")
        memory_id = hashlib.sha1(f"{user_id}:{memory_key}".encode("utf-8")).hexdigest()
        now = _utc_now()
        async with self._lock:
            db = self._db()
            await db.execute(
                """
                INSERT INTO memory_facts(
                    memory_id, user_id, memory_key, category, value_json, summary,
                    confidence, source_session_id, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, memory_key) DO UPDATE SET
                    category=excluded.category,
                    value_json=excluded.value_json,
                    summary=excluded.summary,
                    confidence=excluded.confidence,
                    source_session_id=excluded.source_session_id,
                    updated_at=excluded.updated_at
                """,
                (
                    memory_id,
                    user_id,
                    memory_key,
                    category,
                    json.dumps(value, ensure_ascii=False),
                    summary,
                    max(0.0, min(1.0, float(confidence))),
                    source_session_id,
                    now,
                    now,
                ),
            )
            await db.commit()
        return await self.get_fact(user_id, memory_id)

    async def get_fact(self, user_id: str, memory_id: str) -> Dict[str, Any]:
        async with self._lock:
            cursor = await self._db().execute(
                "SELECT * FROM memory_facts WHERE user_id=? AND memory_id=?",
                (user_id, memory_id),
            )
            row = await cursor.fetchone()
        if not row:
            raise KeyError("记忆不存在")
        return self._fact_from_row(row)

    async def list_facts(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        async with self._lock:
            cursor = await self._db().execute(
                "SELECT * FROM memory_facts WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            )
            rows = await cursor.fetchall()
        return [self._fact_from_row(row) for row in rows]

    @staticmethod
    def _fact_from_row(row: aiosqlite.Row) -> Dict[str, Any]:
        try:
            value = json.loads(row["value_json"])
        except json.JSONDecodeError:
            value = row["value_json"]
        return {
            "memory_id": row["memory_id"],
            "key": row["memory_key"],
            "category": row["category"],
            "value": value,
            "summary": row["summary"],
            "confidence": row["confidence"],
            "source_session_id": row["source_session_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    async def delete_fact(self, user_id: str, memory_id: str) -> bool:
        async with self._lock:
            db = self._db()
            cursor = await db.execute(
                "DELETE FROM memory_facts WHERE user_id=? AND memory_id=?",
                (user_id, memory_id),
            )
            await db.commit()
        if cursor.rowcount:
            try:
                await asyncio.to_thread(get_vector_store().delete_user_preference, memory_id)
            except Exception as exc:
                print(f"[Memory] 删除 Chroma 偏好失败，SQLite 已删除: {exc}")
        return bool(cursor.rowcount)

    async def clear_profile(self, user_id: str) -> int:
        facts = await self.list_facts(user_id)
        async with self._lock:
            db = self._db()
            await db.execute("DELETE FROM memory_facts WHERE user_id=?", (user_id,))
            await db.commit()
        try:
            await asyncio.to_thread(get_vector_store().clear_user_preferences, user_id)
        except Exception as exc:
            print(f"[Memory] 清理 Chroma 偏好失败，SQLite 已清理: {exc}")
        return len(facts)

    async def record_trip(self, user_id: str, session_id: str, itinerary: Dict[str, Any]) -> None:
        if not itinerary:
            return
        user_id = _safe_identity(user_id, f"anonymous-{session_id}")
        session_id = _safe_identity(session_id, "session")
        city = str(itinerary.get("city", "")).strip()
        start_date = itinerary.get("start_date")
        end_date = itinerary.get("end_date")
        now = _utc_now()
        async with self._lock:
            db = self._db()
            # 一段多轮对话可能连续生成上海、北京等多份计划。同一目的地和日期
            # 视为同一行程的更新，不同目的地或日期则必须保留为独立历史记录。
            cursor = await db.execute(
                "SELECT trip_id FROM trip_history "
                "WHERE user_id=? AND session_id=? AND city=? "
                "AND IFNULL(start_date, '')=IFNULL(?, '') "
                "AND IFNULL(end_date, '')=IFNULL(?, '') LIMIT 1",
                (user_id, session_id, city, start_date, end_date),
            )
            existing = await cursor.fetchone()
            trip_identity = f"{city}:{start_date or ''}:{end_date or ''}"
            trip_id = (
                existing["trip_id"]
                if existing
                else hashlib.sha1(
                    f"{user_id}:{session_id}:{trip_identity}".encode("utf-8")
                ).hexdigest()
            )
            await db.execute(
                "INSERT INTO users(user_id, created_at, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET updated_at=excluded.updated_at",
                (user_id, now, now),
            )
            await db.execute(
                """
                INSERT INTO trip_history(
                    trip_id, user_id, session_id, city, start_date, end_date,
                    plan_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trip_id) DO UPDATE SET
                    city=excluded.city, start_date=excluded.start_date,
                    end_date=excluded.end_date, plan_json=excluded.plan_json,
                    updated_at=excluded.updated_at
                """,
                (
                    trip_id,
                    user_id,
                    session_id,
                    city,
                    start_date,
                    end_date,
                    json.dumps(itinerary, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            await db.commit()

    async def list_trips(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        async with self._lock:
            cursor = await self._db().execute(
                "SELECT trip_id, session_id, city, start_date, end_date, updated_at "
                "FROM trip_history WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_trip(self, user_id: str, trip_id: str) -> Dict[str, Any]:
        """读取属于当前用户的完整历史行程。"""
        async with self._lock:
            cursor = await self._db().execute(
                "SELECT trip_id, session_id, city, start_date, end_date, plan_json, updated_at "
                "FROM trip_history WHERE user_id=? AND trip_id=?",
                (user_id, trip_id),
            )
            row = await cursor.fetchone()
        if not row:
            raise KeyError("历史行程不存在")
        try:
            plan = json.loads(row["plan_json"])
        except json.JSONDecodeError as exc:
            raise ValueError("历史行程数据损坏") from exc
        return {
            "trip_id": row["trip_id"],
            "session_id": row["session_id"],
            "city": row["city"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "updated_at": row["updated_at"],
            "plan": plan,
        }

    async def delete_trip(self, user_id: str, trip_id: str) -> bool:
        """只删除历史行程记录，不影响该会话的聊天消息。"""
        async with self._lock:
            db = self._db()
            cursor = await db.execute(
                "DELETE FROM trip_history WHERE user_id=? AND trip_id=?",
                (user_id, trip_id),
            )
            await db.commit()
        return bool(cursor.rowcount)

    async def import_legacy_trips(
        self,
        user_id: str,
        results_directory: Optional[Path] = None,
    ) -> Dict[str, int]:
        """把旧版 saved_results JSON 行程迁移到当前用户的 SQLite 历史。

        迁移使用 ``user_id + session_id`` 生成稳定 trip_id，因此重复执行只会
        更新已有记录，不会创建重复行程。损坏文件或没有完整行程结果的中间
        状态文件会被跳过。
        """
        directory = results_directory or (Path(__file__).resolve().parents[1] / "saved_results")
        if not directory.exists():
            return {"imported": 0, "skipped": 0}

        imported = 0
        skipped = 0
        # 从旧到新导入，让最新文件最后更新，从而保持历史列表顺序直观。
        paths = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime)
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                plan = payload.get("result")
                session_id = str(payload.get("session_id") or path.stem)
                if not isinstance(plan, dict) or not str(plan.get("city") or "").strip():
                    skipped += 1
                    continue
                await self.record_trip(user_id, session_id, plan)
                imported += 1
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                skipped += 1

        return {"imported": imported, "skipped": skipped}


class LongTermMemoryService:
    """负责画像抽取、向量索引和相关记忆召回。"""

    def __init__(self, repository: SQLiteMemoryService):
        self.repository = repository

    async def retrieve_context(self, user_id: str, query: str, k: int = 5) -> str:
        if not await self.repository.memory_enabled(user_id):
            return ""
        summaries: List[str] = []
        try:
            documents = await asyncio.to_thread(
                get_vector_store().search_user_preferences, user_id, query, k
            )
            summaries = [document.page_content for document in documents]
        except Exception as exc:
            print(f"[Memory] 语义召回降级为 SQLite: {exc}")
        if not summaries:
            facts = await self.repository.list_facts(user_id, limit=k)
            summaries = [fact["summary"] for fact in facts]
        if not summaries:
            return ""
        return "\n".join(f"- {summary}" for summary in summaries)

    async def remember_turn(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
        provider: str,
    ) -> List[Dict[str, Any]]:
        if not await self.repository.memory_enabled(user_id):
            return []
        candidates = await self._extract_candidates(user_message, assistant_message, provider)
        stored = []
        for candidate in candidates:
            key = str(candidate.get("key", "")).strip()
            value = candidate.get("value")
            if key not in ALLOWED_MEMORY_KEYS or value in (None, "", []):
                continue
            category = ALLOWED_MEMORY_KEYS[key]
            summary = str(candidate.get("summary") or f"{category}：{value}")[:300]
            try:
                confidence = float(candidate.get("confidence", 0.8))
            except (TypeError, ValueError):
                confidence = 0.8
            fact = await self.repository.upsert_fact(
                user_id=user_id,
                memory_key=key,
                category=category,
                value=value,
                summary=summary,
                confidence=confidence,
                source_session_id=session_id,
            )
            stored.append(fact)
            try:
                await asyncio.to_thread(
                    get_vector_store().upsert_user_preference,
                    fact["memory_id"],
                    user_id,
                    key,
                    value,
                    summary,
                    confidence,
                )
            except Exception as exc:
                print(f"[Memory] Chroma 偏好索引失败，SQLite 已保存: {exc}")
        return stored

    async def update_fact(
        self, user_id: str, memory_id: str, value: Any, summary: Optional[str] = None
    ) -> Dict[str, Any]:
        current = await self.repository.get_fact(user_id, memory_id)
        updated = await self.repository.upsert_fact(
            user_id=user_id,
            memory_key=current["key"],
            category=current["category"],
            value=value,
            summary=(summary or f"{current['category']}：{value}")[:300],
            confidence=1.0,
            source_session_id=current.get("source_session_id") or "manual",
        )
        try:
            await asyncio.to_thread(
                get_vector_store().upsert_user_preference,
                updated["memory_id"],
                user_id,
                updated["key"],
                updated["value"],
                updated["summary"],
                updated["confidence"],
            )
        except Exception as exc:
            print(f"[Memory] 更新 Chroma 偏好失败，SQLite 已更新: {exc}")
        return updated

    async def _extract_candidates(
        self, user_message: str, assistant_message: str, provider: str
    ) -> List[Dict[str, Any]]:
        # 没有偏好表达时跳过额外模型调用，降低延迟和费用。
        preference_cues = (
            "喜欢", "偏好", "习惯", "不喜欢", "不要", "不吃", "过敏", "预算",
            "自驾", "公共交通", "地铁", "酒店", "民宿", "老人", "儿童", "孩子",
            "轻松", "紧凑", "轮椅", "行动不便",
        )
        if not any(cue in user_message for cue in preference_cues):
            return []
        prompt = f"""你是旅行助手的长期记忆提取器。只提取用户明确表达、未来多次旅行仍可能有用的稳定偏好。
不得保存日期、一次性目的地、姓名、电话、证件、账号、密钥、支付信息或助手自己推测的内容。
允许的 key 只有：{','.join(ALLOWED_MEMORY_KEYS)}。
相同 key 只输出一项；如用户明确改变偏好，输出新值用于覆盖旧值。

用户消息：{user_message}
助手回复：{assistant_message}

只返回 JSON：
{{"memories":[{{"key":"interests","value":["历史文化"],"summary":"用户喜欢历史文化景点","confidence":0.95}}]}}
没有值得长期保存的信息时返回 {{"memories":[]}}。"""
        try:
            llm = get_llm(provider, temperature=0, max_tokens=500)
            response = await llm.ainvoke(prompt)
            match = re.search(r"\{[\s\S]*\}", str(response.content))
            if not match:
                return self._fallback_candidates(user_message)
            payload = json.loads(match.group(0))
            memories = payload.get("memories", [])
            return memories if isinstance(memories, list) else []
        except Exception as exc:
            print(f"[Memory] LLM 偏好抽取失败，使用规则兜底: {exc}")
            return self._fallback_candidates(user_message)

    @staticmethod
    def _fallback_candidates(message: str) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        interests = [
            value for value in ("历史文化", "自然风光", "美食", "亲子", "摄影", "购物", "博物馆")
            if value in message
        ]
        if interests and any(cue in message for cue in ("喜欢", "偏好", "感兴趣")):
            candidates.append({
                "key": "interests", "value": interests,
                "summary": f"用户喜欢{'、'.join(interests)}相关体验", "confidence": 0.75,
            })
        for mode in ("自驾", "公共交通", "地铁", "打车", "步行"):
            if mode in message:
                candidates.append({
                    "key": "transportation", "value": mode,
                    "summary": f"用户偏好的出行方式是{mode}", "confidence": 0.72,
                })
                break
        if "不吃" in message or "过敏" in message:
            candidates.append({
                "key": "dietary", "value": message[:120],
                "summary": f"用户的饮食要求：{message[:100]}", "confidence": 0.7,
            })
        return candidates


_memory_service: Optional[SQLiteMemoryService] = None
_long_term_memory_service: Optional[LongTermMemoryService] = None


def get_memory_service() -> SQLiteMemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = SQLiteMemoryService()
    return _memory_service


def get_long_term_memory_service() -> LongTermMemoryService:
    global _long_term_memory_service
    if _long_term_memory_service is None:
        _long_term_memory_service = LongTermMemoryService(get_memory_service())
    return _long_term_memory_service
