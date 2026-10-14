"""LLM 工厂模块 - 支持多模型切换"""

import os
import time
from typing import Optional
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from .config import get_settings


def setup_langsmith():
    """设置 LangSmith 追踪"""
    settings = get_settings()

    if settings.langchain_tracing_v2 and settings.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        print(f"[LangSmith] 已启用追踪，项目: {settings.langchain_project}")
    else:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ.pop("LANGCHAIN_API_KEY", None)
        print("[LangSmith] 未启用追踪")


# 启动时设置 LangSmith
setup_langsmith()


class LLMFactory:
    """LLM 工厂类，支持动态切换不同的 LLM 提供商"""

    _instances: dict = {}

    @classmethod
    def get_llm(
        cls,
        provider: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> BaseChatModel:
        """获取 LLM 实例"""
        settings = get_settings()
        provider = provider or settings.llm_provider

        print(f"\n{'='*60}")
        print(f"[LLM] 创建 LLM 实例")
        print(f"[LLM] Provider: {provider}")
        print(f"[LLM] Temperature: {temperature}, MaxTokens: {max_tokens}")
        print(f"{'='*60}")

        cache_key = f"{provider}_{temperature}_{max_tokens}"
        if cache_key in cls._instances:
            print(f"[LLM] 使用缓存的实例")
            return cls._instances[cache_key]

        llm = cls._create_llm(provider, settings, temperature, max_tokens, **kwargs)
        cls._instances[cache_key] = llm

        print(f"[LLM] LLM 实例创建成功")
        print(f"{'='*60}\n")
        return llm

    @classmethod
    def _create_llm(
        cls,
        provider: str,
        settings,
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> BaseChatModel:
        """创建 LLM 实例"""

        if provider == "deepseek":
            api_key = settings.deepseek_api_key
            if not api_key:
                raise ValueError("DeepSeek API Key 未配置，请检查 .env 文件中的 DEEPSEEK_API_KEY")

            print(f"[LLM] DeepSeek 配置:")
            print(f"[LLM]   Base URL: {settings.deepseek_base_url}")
            print(f"[LLM]   Model: {settings.deepseek_model}")
            print("[LLM]   API Key: 已配置")

            return ChatOpenAI(
                model=settings.deepseek_model,
                api_key=api_key,
                base_url=settings.deepseek_base_url,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

        elif provider == "aliyun":
            api_key = settings.aliyun_dashscope_api_key
            if not api_key:
                raise ValueError("阿里云百炼 API Key 未配置，请检查 .env 文件中的 ALIYUN_DASHSCOPE_API_KEY")

            print(f"[LLM] 阿里云百炼配置:")
            print(f"[LLM]   Base URL: https://dashscope.aliyuncs.com/compatible-mode/v1")
            print(f"[LLM]   Model: {settings.aliyun_model}")
            print("[LLM]   API Key: 已配置")

            return ChatOpenAI(
                model=settings.aliyun_model,
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

        elif provider == "openai":
            api_key = settings.openai_api_key
            if not api_key:
                raise ValueError("OpenAI API Key 未配置，请检查 .env 文件中的 OPENAI_API_KEY")

            print(f"[LLM] OpenAI 配置:")
            print(f"[LLM]   Base URL: {settings.openai_base_url}")
            print(f"[LLM]   Model: {settings.openai_model}")
            print("[LLM]   API Key: 已配置")

            return ChatOpenAI(
                model=settings.openai_model,
                api_key=api_key,
                base_url=settings.openai_base_url,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

        else:
            raise ValueError(f"不支持的 LLM 提供商: {provider}")

    @classmethod
    def get_available_providers(cls) -> list:
        """获取可用的 LLM 提供商列表"""
        settings = get_settings()
        providers = []

        if settings.deepseek_api_key:
            providers.append({"name": "deepseek", "model": settings.deepseek_model})
        if settings.aliyun_dashscope_api_key:
            providers.append({"name": "aliyun", "model": settings.aliyun_model})
        if settings.openai_api_key:
            providers.append({"name": "openai", "model": settings.openai_model})

        return providers


def get_llm(provider: Optional[str] = None, **kwargs) -> BaseChatModel:
    """获取 LLM 实例的便捷函数"""
    return LLMFactory.get_llm(provider, **kwargs)


async def invoke_llm_with_logging(llm: BaseChatModel, prompt: str, provider: str = "unknown") -> str:
    """调用LLM并打印详细日志"""
    print(f"\n{'='*60}")
    print(f"[LLM Invoke] 开始调用 LLM")
    print(f"[LLM Invoke] Provider: {provider}")
    print(f"[LLM Invoke] Prompt 长度: {len(prompt)} 字符")
    print(f"[LLM Invoke] Prompt 内容:")
    print(f"{'-'*40}")
    print(prompt[:1000] if len(prompt) > 1000 else prompt)
    if len(prompt) > 1000:
        print(f"... (剩余 {len(prompt) - 1000} 字符)")
    print(f"{'-'*40}")
    print(f"{'='*60}")

    start_time = time.time()

    try:
        response = await llm.ainvoke(prompt)
        elapsed_time = time.time() - start_time

        print(f"\n{'='*60}")
        print(f"[LLM Invoke] LLM 响应成功")
        print(f"[LLM Invoke] 耗时: {elapsed_time:.2f} 秒")
        print(f"[LLM Invoke] 响应类型: {type(response).__name__}")
        print(f"[LLM Invoke] 响应长度: {len(response.content)} 字符")
        print(f"[LLM Invoke] 响应内容:")
        print(f"{'-'*40}")
        print(response.content[:500] if len(response.content) > 500 else response.content)
        if len(response.content) > 500:
            print(f"... (剩余 {len(response.content) - 500} 字符)")
        print(f"{'-'*40}")
        print(f"{'='*60}\n")

        return response.content

    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"[LLM Invoke] LLM 调用失败")
        print(f"[LLM Invoke] 耗时: {elapsed_time:.2f} 秒")
        print(f"[LLM Invoke] 错误: {str(e)}")
        print(f"{'='*60}\n")
        raise
