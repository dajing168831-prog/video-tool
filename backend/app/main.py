"""视频工具后端入口。

启动：
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8911
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.clone import router as clone_router
from app.api.drama import router as drama_router
from app.api.prompt import router as prompt_router
from app.api.routes import router
from app.core.config import settings
from app.services import clone_jobs, clone_store
from app.services.storage import cleanup_expired

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="Video Tool API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(clone_router, prefix="/api")
app.include_router(prompt_router, prefix="/api")
app.include_router(drama_router, prefix="/api")


@app.on_event("startup")
async def _startup():
    log = logging.getLogger(__name__)
    removed = cleanup_expired()
    log.info("启动清理：删除 %d 个过期解析目录", removed)
    removed = clone_store.cleanup_expired(settings.clone_ttl)
    log.info("启动清理：删除 %d 个过期复刻目录", removed)
    fixed = clone_jobs.recover()
    if fixed:
        log.warning("启动恢复：%d 个复刻任务被标记为中断", fixed)
    _start_janitor()


# 过期清理只在启动时跑一次的话，多人连着测几天，磁盘只涨不降 ——
# 每人的上传原片 + 切段 + 成片都在 data/clone 下堆着。这里补一个常驻的钟。
_JANITOR_EVERY = 3600.0     # 一小时扫一次，够用且不会打断正在跑的任务


def _start_janitor() -> None:
    if getattr(_start_janitor, "_started", False):
        return
    _start_janitor._started = True  # type: ignore[attr-defined]

    def loop() -> None:
        log = logging.getLogger(__name__)
        while True:
            time.sleep(_JANITOR_EVERY)
            try:
                n1 = cleanup_expired()
                n2 = clone_store.cleanup_expired(settings.clone_ttl)
                if n1 or n2:
                    log.info("定时清理：解析 %d 个 / 复刻 %d 个", n1, n2)
            except Exception:  # noqa: BLE001
                # 清理失败不该影响出片，记下来继续下一轮
                log.exception("定时清理失败")

    threading.Thread(target=loop, name="janitor", daemon=True).start()


@app.get("/")
async def root():
    return {"code": 200, "biz_code": 0, "msg": "Video Tool API", "data": {"docs": "/docs"}}
