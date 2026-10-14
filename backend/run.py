"""启动脚本。

始终从本文件所在的 backend 目录加载应用，避免 Windows 上同时存在旧项目
进程或同名 ``app`` 包时误加载其他代码。
"""

import os
import sys
from pathlib import Path

import uvicorn


BACKEND_ROOT = Path(__file__).resolve().parent
os.chdir(BACKEND_ROOT)
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402


if __name__ == "__main__":
    settings = get_settings()

    print(f"[BOOT] 后端代码目录: {BACKEND_ROOT}")
    print(f"[BOOT] 持久化记忆: {BACKEND_ROOT / settings.memory_database_path}")

    uvicorn.run(
        "app.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        timeout_keep_alive=300
    )
