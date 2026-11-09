"""商品短剧 · 出片参考图地址解析（真人脸必须走素材库）。

为什么需要：
    火山 Seedance **不收直接上传的真人脸参考图**，提交即 400
    `InputImageSensitiveContentDetected.PrivacyInformation`（官方错误码
    `backend/data/official/sd20/pull-2026-11-04/error-codes.md:43`）。
    定妆图、带模特/真人的商品图、AI 生成的写实九宫格，都会踩这一条。

做法（和复刻线同一条路，只是这边判完再决定）：
    1. 本地 YuNet 判有没有脸（`face_check`，零费用、不联网）
    2. 有脸 / 判断不了 → 先入火山素材库换 `asset://<id>`（`ark_ingest.prepare_image`：
       按 sha1 + 项目缓存、额度不够 LRU 回收、闲置组自动清理）
    3. 没脸 → 原样用公网 URL，不占素材库额度

🩸 为什么入库失败要**直接拦住**，不退回公网 URL：
    退回 = 一定 400，钱不一定花但任务必败，而且报错是火山的「可能含真人」，
    和真实原因（入库失败/配额满）对不上。宁可现在就说清。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable


class RefBlocked(RuntimeError):
    """这张参考图不能直传，且没能换成 asset://。"""


def resolve(path: Path, cid: str, *, public_url: Callable[[Path], str],
            faces: int | None = None) -> str:
    """返回可直接放进请求 content 的地址：要么公网 URL，要么 asset://。

    `faces` 可注入（测试用）；None = 现场检测。
    """
    from app.services import face_check

    p = Path(path)
    if faces is None:
        try:
            faces = face_check.detect_faces(p)
        except Exception:  # noqa: BLE001  判不了按有脸处理（漏一张就是一次 400）
            faces = -1
    if faces == 0:
        return public_url(p)

    from app.services import ark_ingest

    if not ark_ingest.available():
        raise RefBlocked(
            f"参考图「{p.name}」含真人，火山不收直传；素材库没配"
            "（VT_VOLC_ACCESS_KEY / VT_VOLC_SECRET_KEY），先别花钱"
        )
    asset = ""
    try:
        asset = ark_ingest.prepare_image(p, cid)
    except Exception as e:  # noqa: BLE001
        raise RefBlocked(f"参考图「{p.name}」入库异常，先别花钱：{e}") from e
    if not asset:
        raise RefBlocked(
            f"参考图「{p.name}」含真人，但入素材库失败（可能审核没过或额度满），"
            "先别花钱；换一张没有真人的图，或稍后重试"
        )
    return asset
