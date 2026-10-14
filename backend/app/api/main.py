"""FastAPI 主应用"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from ..core.config import get_settings
from ..core.llm import setup_langsmith  # 显式导入以确保LangSmith设置
from .routes import trip, chat, map, config, knowledge, booking, memory
from ..agents.graph import close_graph, initialize_graph
from ..services.memory_service import get_memory_service

# 启动时设置 LangSmith
setup_langsmith()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    settings = get_settings()

    # 启动时先连接持久化层，随后所有接口都共享同一连接。
    await get_memory_service().initialize()
    await initialize_graph()

    # 启动时
    print("\n" + "=" * 60)
    print(f"[START] {settings.app_name} v{settings.app_version}")
    print("=" * 60)
    print(f"LLM Provider: {settings.llm_provider}")
    print(f"DeepSeek API Key: {'已配置' if settings.deepseek_api_key else '未配置'}")
    print(f"阿里云 API Key: {'已配置' if settings.aliyun_dashscope_api_key else '未配置'}")
    print(f"高德地图 API Key: {'已配置' if settings.amap_api_key else '未配置'}")
    print(f"LangSmith 追踪: {'已启用' if settings.langchain_tracing_v2 else '未启用'}")
    if settings.langchain_tracing_v2:
        print(f"LangSmith 项目: {settings.langchain_project}")
    print(f"CORS Origins: {settings.get_cors_origins_list()}")
    print("=" * 60 + "\n")

    yield

    # 关闭时
    await close_graph()
    await get_memory_service().close()
    print("\n[STOP] 应用正在关闭...\n")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="""
## LangGraph 智能旅行助手

基于 LangGraph 和 LangChain 构建的多 Agent 协作旅行规划系统。

### 核心特性
- LLM 对话中枢：自由文本意图识别与多轮 Slot Filling
- 自主 Agent：Supervisor 动态选工具并循环解决预算/时间冲突
- Human-in-the-loop：关键决策点用户确认
- 多轮对话：支持追问和行程调整
- Agent 可观测性：集成 LangSmith
- 记忆系统：保存用户偏好
- 完整 RAG ETL：PDF/Word 上传、扫描 PDF OCR、语义切块、Embedding、向量+BM25混合检索
- 预订交接：复制结构化信息并跳转第三方官方平台，由用户完成真实交易
- OTA 模拟器：仅用于验证报价、锁单、确认、查询与取消状态机

### Agent 流程
```
Supervisor -> 动态工具 -> 规划 -> 约束校验 <-> 冲突修复 -> 用户审核 -> 第三方平台交接
```
        """,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # CORS 配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(trip.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(map.router, prefix="/api")
    app.include_router(config.router, prefix="/api")
    app.include_router(knowledge.router, prefix="/api")
    app.include_router(booking.router, prefix="/api")
    app.include_router(memory.router, prefix="/api")

    # 根路由
    @app.get("/")
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "running",
            "docs": "/docs"
        }

    # 健康检查
    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


app = create_app()
