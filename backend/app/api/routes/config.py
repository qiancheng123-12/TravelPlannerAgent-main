"""系统配置 API 路由"""

from fastapi import APIRouter

from ...core.config import get_settings
from ...core.llm import LLMFactory

router = APIRouter(prefix="/config", tags=["系统配置"])


@router.get("/llm-providers")
async def get_llm_providers():
    """获取可用的 LLM 提供商列表"""
    providers = LLMFactory.get_available_providers()
    settings = get_settings()

    return {
        "current": settings.llm_provider,
        "available": providers
    }


@router.get("/settings")
async def get_public_settings():
    """获取公开的配置信息"""
    settings = get_settings()

    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "default_llm": settings.llm_provider,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "ota_mode": "remote_sandbox" if settings.ota_sandbox_base_url else "mock_sandbox",
        "features": ["llm_slot_filling", "agent_decision_loop", "hybrid_rag", "ota_booking"]
    }
