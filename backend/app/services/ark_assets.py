"""火山方舟素材库（管控面）：把素材变成 `asset://<id>`。

为什么必须走这条路：
    Seedance 不收**直接上传**的真人脸参考图/视频 —— 提交即 400
    `InputImageSensitiveContentDetected.PrivacyInformation`。
    素材库里的资产是**入库时统一审一次**的，之后每次生成不再逐次做人脸拦截。

鉴权走 **V4 签名（AK/SK）**，不是 API Key：
    Bearer API Key 只对数据面（/api/v3）有效；
    素材库是管控面 `ark.cn-beijing.volcengineapi.com`，只能用 AK/SK 签。

额度：官方 50 素材 + 50 组，**全账号共享**。回收见 ark_ingest。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)

HOST = "ark.cn-beijing.volcengineapi.com"
SERVICE = "ark"
REGION = "cn-beijing"
VERSION = "2024-01-01"
CONTENT_TYPE = "application/json"
BASE = f"https://{HOST}/"


class ArkAssetError(RuntimeError):
    pass


def _cfg():
    from app.core.config import settings

    return settings


def available() -> bool:
    s = _cfg()
    return bool(getattr(s, "ark_asset_enabled", True)
                and (s.volc_access_key or "").strip()
                and (s.volc_secret_key or "").strip())


# ---------------------------------------------------------------------------
# V4 签名


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _canonical_query(params: dict) -> str:
    """按 key 升序；值做 RFC3986 编码（空格 %20，不是 +）。"""
    items = sorted((str(k), str(v)) for k, v in params.items())
    return "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}"
                    for k, v in items)


def sign_headers(method: str, params: dict, body: bytes,
                 *, ak: str, sk: str,
                 now: datetime | None = None) -> dict:
    """算出一次管控面请求要带的鉴权头。纯函数，可离线自检。"""
    now = now or datetime.now(timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short = x_date[:8]
    payload_hash = _sha256_hex(body)

    # 参与签名的头**必须和实际发出去的一字不差**。官方 SDK（SignerV4）把
    # Content-Type / Content-Md5 / Host / 所有 X-* 全收进签名集，我们照抄：
    # 少签 content-type 时管控面校验不过，回的就是 401 SignatureDoesNotMatch。
    signed = ["content-type", "host", "x-content-sha256", "x-date"]
    # 规范头块每行以 \n 结尾，拼进 CanonicalRequest 时**还会再加一个 \n**
    # → 最后一行头与 SignedHeaders 之间是空行。这是 V4 的原文规定，别"顺手修掉"。
    canonical_headers = (
        f"content-type:{CONTENT_TYPE}\n"
        f"host:{HOST}\n"
        f"x-content-sha256:{payload_hash}\n"
        f"x-date:{x_date}\n"
    )
    canonical_request = "\n".join([
        method.upper(),
        "/",
        _canonical_query(params),
        canonical_headers,
        ";".join(signed),
        payload_hash,
    ])

    scope = f"{short}/{REGION}/{SERVICE}/request"
    string_to_sign = "\n".join([
        "HMAC-SHA256",
        x_date,
        scope,
        _sha256_hex(canonical_request.encode("utf-8")),
    ])

    k = _hmac(sk.encode("utf-8"), short)
    k = _hmac(k, REGION)
    k = _hmac(k, SERVICE)
    k = _hmac(k, "request")
    signature = hmac.new(k, string_to_sign.encode("utf-8"),
                         hashlib.sha256).hexdigest()

    return {
        "Host": HOST,
        "Content-Type": CONTENT_TYPE,
        "X-Date": x_date,
        "X-Content-Sha256": payload_hash,
        "Authorization": (
            f"HMAC-SHA256 Credential={ak}/{scope}, "
            f"SignedHeaders={';'.join(signed)}, Signature={signature}"
        ),
    }


def _call(action: str, body: dict, *, timeout: float = 60) -> dict:
    s = _cfg()
    if not available():
        raise ArkAssetError(
            "素材库未配置：请设置 VT_VOLC_ACCESS_KEY / VT_VOLC_SECRET_KEY"
            "（管控面只能 AK/SK 签名）"
        )
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    params = {"Action": action, "Version": VERSION}
    headers = sign_headers("POST", params, raw,
                           ak=s.volc_access_key.strip(),
                           sk=s.volc_secret_key.strip())
    url = f"{BASE}?{_canonical_query(params)}"
    # 管控面有 QPM 频率限制（实测连发 8 个 CreateAsset 就撞到
    # 429 QuotaWriteQPMExceeded）。撞到就退避重试，别把一次正常出片误判成失败。
    for attempt in range(3):
        with httpx.Client(timeout=timeout) as c:
            r = c.post(url, headers=headers, content=raw)
        if r.status_code != 429:
            break
        if attempt == 2:
            break
        wait = 15.0 * (attempt + 1)
        log.warning("%s 被限流（429），%.0fs 后重试", action, wait)
        time.sleep(wait)
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        data = {}
    meta = (data.get("ResponseMetadata") or {}) if isinstance(data, dict) else {}
    err = meta.get("Error") or {}
    if r.status_code != 200 or err:
        code = str(err.get("Code") or "")
        hint = ""
        if code == "SignatureDoesNotMatch":
            # 签名算法已与官方 SDK 对齐过，走到这里基本就是 AK/SK 本身的问题
            hint = ("｜签名算法与官方 SDK 一致，这通常是 AK/SK 本身不对："
                    "确认两者是控制台同一对、SK 没被重置或复制残缺")
        raise ArkAssetError(
            f"{action} 失败 HTTP {r.status_code}: "
            f"{code} {err.get('Message') or r.text[:200]}{hint}"
        )
    return data.get("Result") or {}


def _find_id(obj) -> str:
    """结果里 Id 的位置各家文档写法不一，递归找，不猜形状。"""
    if isinstance(obj, dict):
        for k in ("Id", "id", "AssetId", "GroupId"):
            if isinstance(obj.get(k), str) and obj[k]:
                return obj[k]
        for v in obj.values():
            got = _find_id(v)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_id(v)
            if got:
                return got
    return ""


def _find_status(obj) -> str:
    if isinstance(obj, dict):
        for k in ("Status", "status", "State", "state"):
            if isinstance(obj.get(k), str):
                return obj[k]
        for v in obj.values():
            got = _find_status(v)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_status(v)
            if got:
                return got
    return ""


# ---------------------------------------------------------------------------
# 业务动作


def create_group(name: str, description: str = "clone temp") -> str:
    # GroupType 目前官方只开放 AIGC（私域虚拟人像素材组）。
    # 不写它也能建，但官方示例和 SDK 都带，带上更保险。
    res = _call("CreateAssetGroup",
                {"Name": name[:64], "Description": description,
                 "GroupType": "AIGC",
                 "ProjectName": _cfg().ark_asset_project})
    gid = _find_id(res)
    if not gid:
        raise ArkAssetError(f"建素材组没拿到 Id: {res}")
    return gid


def create_asset(group_id: str, url: str, kind: str = "Image",
                 name: str = "") -> str:
    body = {"GroupId": group_id, "URL": url,
            "AssetType": "Video" if kind.lower() == "video" else "Image",
            "ProjectName": _cfg().ark_asset_project}
    if name:
        body["Name"] = name[:64]
    res = _call("CreateAsset", body)
    aid = _find_id(res)
    if not aid:
        raise ArkAssetError(f"入库没拿到 Id: {res}")
    return aid


def list_groups(page: int = 1, size: int = 20,
                group_type: str = "AIGC") -> dict:
    """列素材组。`Filter.GroupType` 是**必填**（只传空 Filter 会被 400 拒）。

    用途：核对账号里还剩多少额度、排查"组是不是真删掉了"。
    """
    return _call("ListAssetGroups", {
        "Filter": {"GroupType": group_type},
        "PageNumber": page,
        "PageSize": size,
    })


def list_assets(group_id: str, page: int = 1, size: int = 20) -> dict:
    """列某个组里的素材（同样要带 Filter.GroupType）。"""
    return _call("ListAssets", {
        "Filter": {"GroupType": "AIGC", "GroupIds": [group_id]},
        "PageNumber": page,
        "PageSize": size,
    })


def get_asset(asset_id: str) -> str:
    return _find_status(_call("GetAsset", {"Id": asset_id}))


def _find_error(obj) -> str:
    """把火山返回的 Error{Code,Message} 提出来。

    🩸 为什么要有这个：`Status=Failed` 本身不说明任何事。2026-10-23 那次
    出片失败，日志里只有「素材处理失败（Failed）」，完全看不出是**版权拦截**
    （InputVideoSensitiveContentDetected.PolicyViolation）—— 白查一轮。
    """
    if isinstance(obj, dict):
        err = obj.get("Error") or obj.get("error")
        if isinstance(err, dict):
            code = str(err.get("Code") or err.get("code") or "")
            msg = str(err.get("Message") or err.get("message") or "")
            if code or msg:
                return f"{code} {msg}".strip()
        for v in obj.values():
            got = _find_error(v)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_error(v)
            if got:
                return got
    return ""


def wait_active(asset_id: str, *, timeout: float = 300,
                poll: float = 5.0) -> str:
    """轮询到 Active。视频处理慢，官方不承诺 SLA，所以给足超时。"""
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        detail = _call("GetAsset", {"Id": asset_id})
        st = _find_status(detail)
        if st:
            last = st
        low = (st or "").lower()
        if low == "active":
            return st
        if low in ("failed", "error"):
            # 🩸 必须带上 Error.Code/Message：只看 Status=Failed 查不出任何原因
            why = _find_error(detail)
            raise ArkAssetError(
                f"素材 {asset_id} 处理失败（{st}）：{why}" if why
                else f"素材 {asset_id} 处理失败（{st}）")
        time.sleep(poll)
    raise ArkAssetError(f"素材 {asset_id} 等 Active 超时（最后状态 {last}）")


def delete_group(group_id: str) -> None:
    _call("DeleteAssetGroup", {"Id": group_id})


def delete_asset(asset_id: str) -> None:
    _call("DeleteAsset", {"Id": asset_id})
