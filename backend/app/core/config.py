"""核心配置模块"""

from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """应用配置"""

    # 应用信息
    app_name: str = "LangGraph 智能旅行助手"
    app_version: str = "2.0.0"
    debug: bool = False

    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS 配置
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # LLM 配置
    llm_provider: str = "deepseek"  # deepseek / aliyun / openai

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 阿里云百炼
    aliyun_dashscope_api_key: str = ""
    aliyun_model: str = "qwen-plus"
    aliyun_embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # OpenAI
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4-turbo-preview"

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "trip-planner-agent"

    # 高德地图
    amap_api_key: str = ""

    # 向量数据库
    chroma_persist_directory: str = "./data/chroma"
    embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "local"  # local / aliyun / openai

    # 扫描版 PDF OCR：普通 PDF 仍优先读取文字层，仅对异常页面执行 OCR。
    ocr_enabled: bool = True
    ocr_dpi: int = 200
    ocr_min_chars: int = 30
    ocr_bad_char_ratio: float = 0.10

    # 持久化记忆：SQLite 保存聊天、用户画像和 LangGraph checkpoint。
    memory_database_path: str = "./data/travel_memory.sqlite3"
    langgraph_checkpoint_path: str = "./data/langgraph_checkpoints.sqlite3"

    # OTA 沙箱。未配置地址时使用内置可重复演示的 mock sandbox。
    ota_sandbox_base_url: str = ""
    ota_sandbox_api_key: str = ""
    ota_sandbox_timeout: float = 15.0

    # Unsplash
    unsplash_access_key: str = ""

    # 日志
    log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore"
    }

    def get_cors_origins_list(self) -> List[str]:
        """获取 CORS origins 列表"""
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings
