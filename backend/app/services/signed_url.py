"""给外部模型拉原片用的临时签名链接。

为什么需要：火山 Seedance 2.5 的 edit 任务只收**公网 URL**当参考视频
（图能收 base64，视频不收）。原片在我们本机/内网，必须开一个短期可访问的地址。

不做成完全公开的原因：复刻素材是客户上传的内容，公开就是泄露。
签名覆盖 (cid, 片段名, 过期时间)，泄露一个链接也只能拿到那一条（段）片子，
且默认两小时后失效。
"""
from __future__ import annotations

import hashlib
import hmac
import time

from app.core.config import settings


def _secret() -> bytes:
    s = (settings.url_secret or "").strip()
    if not s:
        # 没单独配就退回用平台 key 派生 —— 换 key 会让旧链接失效，可接受
        s = (settings.ark_api_key or "").strip() or "video-tool-local-dev"
    return s.encode("utf-8")


def sign(cid: str, exp: int, seg: str = "") -> str:
    msg = f"{cid}:{int(exp)}:{seg or ''}".encode("utf-8")
    return hmac.new(_secret(), msg, hashlib.sha256).hexdigest()[:24]


def _build(cid: str, seg: str, ttl: int | None) -> str:
    base = (settings.public_base_url or "").strip().rstrip("/")
    if not base:
        return ""
    exp = int(time.time()) + int(ttl if ttl is not None else settings.source_url_ttl)
    q = f"exp={exp}&sig={sign(cid, exp, seg)}"
    if seg:
        return f"{base}/api/clone/{cid}/file/seg/{seg}?{q}"
    return f"{base}/api/clone/{cid}/file/ref?{q}"


def make(cid: str, *, ttl: int | None = None, seg: str = "") -> str:
    """整片或指定切段的临时 URL；没配 public_base_url 就返回空串。"""
    return _build(cid, seg, ttl)


def verify(cid: str, exp: int, sig: str, seg: str = "") -> bool:
    if not exp or exp < time.time():
        return False
    return hmac.compare_digest(sign(cid, exp, seg), (sig or ""))
