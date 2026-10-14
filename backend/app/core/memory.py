"""会话记忆聚合对象。

对象本身只负责给对话引擎提供同步读写接口；真正的持久化由
``services.memory_service.SQLiteMemoryService`` 完成。
"""

from typing import List, Optional, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

class ConversationMemory:
    """对话记忆管理"""

    def __init__(
        self,
        session_id: str,
        max_history: int = 10,
        user_id: str = "",
        history: Optional[List[BaseMessage]] = None,
        preferences: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化对话记忆

        Args:
            session_id: 会话 ID
            max_history: 最大历史消息数
        """
        self.session_id = session_id
        self.user_id = user_id
        self.max_history = max_history
        self._history: List[BaseMessage] = list(history or [])
        self._user_preferences: Dict[str, Any] = dict(preferences or {})

    def add_message(self, message: BaseMessage) -> None:
        """添加消息到历史"""
        self._history.append(message)
        # 保持历史记录在限制内
        if len(self._history) > self.max_history * 2:
            self._history = self._history[-self.max_history * 2:]

    def add_user_message(self, content: str) -> None:
        """添加用户消息"""
        self.add_message(HumanMessage(content=content))

    def add_ai_message(self, content: str) -> None:
        """添加 AI 消息"""
        self.add_message(AIMessage(content=content))

    def get_history(self) -> List[BaseMessage]:
        """获取对话历史"""
        return self._history.copy()

    def get_history_str(self) -> str:
        """获取对话历史的字符串表示"""
        lines = []
        for msg in self._history:
            role = "用户" if isinstance(msg, HumanMessage) else "助手"
            lines.append(f"{role}: {msg.content}")
        return "\n".join(lines)

    def set_preference(self, key: str, value: Any) -> None:
        """设置用户偏好"""
        self._user_preferences[key] = value

    def get_preference(self, key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        return self._user_preferences.get(key, default)

    def get_all_preferences(self) -> Dict[str, Any]:
        """获取所有用户偏好"""
        return self._user_preferences.copy()

    def clear(self) -> None:
        """清空记忆"""
        self._history.clear()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "history": [
                {"role": "user" if isinstance(m, HumanMessage) else "ai", "content": m.content}
                for m in self._history
            ],
            "preferences": self._user_preferences
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationMemory":
        """从字典反序列化"""
        memory = cls(data["session_id"], user_id=data.get("user_id", ""))
        for msg in data.get("history", []):
            if msg["role"] == "user":
                memory.add_user_message(msg["content"])
            else:
                memory.add_ai_message(msg["content"])
        memory._user_preferences = data.get("preferences", {})
        return memory
