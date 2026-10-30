"""阿里云 OSS 上传：本地文件 → 公网 URL。

为什么要有这一步：火山 Seedance 的视频参考**只收公网可访问的 URL**
（图能收 base64、视频不收）。素材在我们本机/内网，必须先传到一个
公网能拉的地方 —— 我们自己的 OSS。

链路（和原机大鲸那套一致）：
    本地文件 → PUT 到 dajinggl-img → https://img.dajing.vip/uploads/...

不引 oss2 SDK：只用 PUT 一个动作，签名算法十几行，少一个依赖少一份升级风险。
签名走 OSS V1（HMAC-SHA1），和 oss2 默认一致。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import mimetypes
import time
from email.utils import formatdate
from pathlib import Path

import httpx

log = logging.getLogger(__name__)


class OssError(RuntimeError):
    pass


def _cfg():
    from app.core.config import settings

    return settings


def available() -> bool:
    s = _cfg()
    return bool(
        (s.oss_access_key_id or "").strip()
        and (s.oss_access_key_secret or "").strip()
        and (s.oss_bucket or "").strip()
        and (s.oss_endpoint or "").strip()
    )


def _object_key(path: Path, prefix: str | None = None) -> str:
    """uploads/20261021/<时间戳>-<原名>：带日期目录，方便按天清理。"""
    p = Path(path)
    day = time.strftime("%Y%m%d")
    stem = p.stem[:40]
    suffix = p.suffix or ".bin"
    # 去掉中文和空格，避免 URL 需要转义
    safe = "".join(c for c in stem if c.isascii() and (c.isalnum() or c in "-_")) or "file"
    prefix = (prefix if prefix is not None else (_cfg().oss_prefix or "uploads/")).strip("/")
    name = f"{safe}-{int(time.time() * 1000)}{suffix}"
    return f"{prefix}/{day}/{name}" if prefix else f"{day}/{name}"


def _canonical_oss_headers(headers: dict) -> str:
    """把 x-oss-* 头按名字排序拼成规范串。

    阿里云 V1 签名里，**只要发了 x-oss- 开头的头，就必须算进签名**，
    漏一个就是 403 SignatureDoesNotMatch。
    """
    items = sorted((k.lower(), str(v).strip()) for k, v in headers.items()
                   if k.lower().startswith("x-oss-"))
    return "".join(f"{k}:{v}\n" for k, v in items)


def _sign(method: str, key: str, content_type: str, date: str,
          ak_id: str, ak_secret: str, bucket: str,
          headers: dict | None = None) -> str:
    resource = f"/{bucket}/{key}"
    string_to_sign = (
        f"{method}\n\n{content_type}\n{date}\n"
        f"{_canonical_oss_headers(headers or {})}{resource}"
    )
    digest = hmac.new(ak_secret.encode("utf-8"), string_to_sign.encode("utf-8"),
                      hashlib.sha1).digest()
    return f"OSS {ak_id}:{base64.b64encode(digest).decode()}"


def upload(path: Path, *, prefix: str | None = None, timeout: float = 300) -> str:
    """上传一个文件，返回公网 URL。OSS 没配就抛错（不静默降级）。"""
    s = _cfg()
    if not available():
        raise OssError(
            "OSS 未配置：需要 VT_OSS_ACCESS_KEY_ID / VT_OSS_ACCESS_KEY_SECRET "
            "/ VT_OSS_BUCKET / VT_OSS_ENDPOINT"
        )
    p = Path(path)
    if not p.exists():
        raise OssError(f"文件不存在：{p}")

    key = _object_key(p, prefix=prefix)
    endpoint = s.oss_endpoint.strip().lstrip("https://").lstrip("http://").strip("/")
    bucket = s.oss_bucket.strip()
    url = f"https://{bucket}.{endpoint}/{key}"

    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    date = formatdate(usegmt=True)
    headers = {
        "Content-Type": ctype,
        "Date": date,
        # 一年缓存；key 里带毫秒时间戳，不会互相覆盖
        "x-oss-cache-control": "public, max-age=31536000",
    }
    # 默认不发 ACL：桶或 CDN 已经能读，发这个反而要求 RAM 用户有
    # oss:PutObjectAcl 权限，没有就是 403。桶是私有的再打开这个开关。
    acl = (s.oss_acl or "").strip()
    if acl:
        headers["x-oss-object-acl"] = acl
    headers["Authorization"] = _sign(
        "PUT", key, ctype, date,
        s.oss_access_key_id.strip(), s.oss_access_key_secret.strip(),
        bucket, headers,
    )

    data = p.read_bytes()
    t0 = time.time()
    with httpx.Client(timeout=timeout) as c:
        r = c.put(url, content=data, headers=headers)
    if r.status_code not in (200, 201):
        raise OssError(f"OSS 上传失败 HTTP {r.status_code}: {r.text[:300]}")

    base = (s.oss_public_base or f"https://{bucket}.{endpoint}").strip().rstrip("/")
    public = f"{base}/{key}"
    log.info("上传 OSS %s (%.1fKB, %.1fs) -> %s",
             p.name, len(data) / 1024, time.time() - t0, public)
    return public


def check() -> dict:
    """连通性自检：传一个 1KB 的探测对象，再删掉需要的权限。"""
    import tempfile

    if not available():
        return {"ok": False, "error": "未配置"}
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, dir=".") as f:
        f.write(b"video-tool oss probe")
        tmp = Path(f.name)
    try:
        url = upload(tmp, prefix="probe")
        with httpx.Client(timeout=30) as c:
            got = c.get(url)
        return {"ok": got.status_code == 200, "url": url, "status": got.status_code}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}
    finally:
        tmp.unlink(missing_ok=True)
