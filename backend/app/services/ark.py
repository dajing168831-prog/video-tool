"""火山方舟（ARK）客户端：图片生成 + 视频生成。

为什么自己写而不引 SDK：这里只用两个接口，SDK 会带一堆依赖；
而且把"重试、超时、并发"握在手里，后面调队列才好办。

模型 ID 都走配置，不写死 —— 方舟的模型换代很快，换模型不该改代码。
"""
from __future__ import annotations

import base64
import logging
import math
import time
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

BASE = "https://ark.cn-beijing.volces.com/api/v3"
IMAGES = f"{BASE}/images/generations"
VIDEO_TASKS = f"{BASE}/contents/generations/tasks"

# 图生图时把参考图压到这个长边，太大又慢又贵，太小丢细节
REF_MAX_SIDE = 1536
# 🩸 视频参考图不能沿用 1536：官方限制是**边长 ≤6000**，而换人靠的就是参考图里的
# 脸。1536 会把 3024×4032 的全身照压成 1152×1536，脸从 213px 掉到 81px ——
# 属性（衣服/发型）比五官显眼，模型自然只搬衣服。官方没有 1536 这个数。
VIDEO_REF_MAX_SIDE = 6000


class ArkError(RuntimeError):
    """带结构的错误 —— `detail` 里放**原始响应**，上层直接落盘。

    🩸 2026-10-23：以前只抛一句话，火山返回的 code / message / request id
    全被 `[:400]` 截掉，查一次失败要翻日志、有时候日志还被重启覆盖了。
    """

    def __init__(self, msg: str, detail: dict | None = None):
        super().__init__(msg)
        self.detail = detail or {}


def _err_detail(raw: str, *, step: str, http: int = 0) -> dict:
    """从火山原始响应里抽出 code / message / request id。"""
    import json as _json
    import re as _re

    d: dict = {"step": step, "raw": raw}
    if http:
        d["http"] = http
    try:
        obj = _json.loads(raw)
        e = obj.get("error") or obj if isinstance(obj, dict) else {}
        if isinstance(e, dict):
            d["code"] = str(e.get("code") or "")
            msg = str(e.get("message") or "")
            if msg:
                d["message"] = msg
            m = _re.search(r"Request id:\s*([0-9A-Za-z\-]+)", msg)
            if m:
                d["request_id"] = m.group(1)
    except Exception:  # noqa: BLE001
        pass
    return d


def _key() -> str:
    from app.core.config import settings

    k = (settings.ark_api_key or "").strip()
    if not k:
        raise ArkError("方舟未配置：请设置 VT_ARK_API_KEY")
    return k


def _headers() -> dict:
    return {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"}


def _data_uri(path: Path, max_side: int = REF_MAX_SIDE) -> str:
    """把本地图片转成 data URI，顺带缩到合理尺寸。

    方舟接受公网 URL 或 base64；我们素材在本机，只能走 base64。
    """
    from app.services.media import ffmpeg_path
    import subprocess
    import tempfile

    src = Path(path)
    ff = ffmpeg_path()
    tmp = None
    if ff:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False,
                                         dir=str(src.parent)) as f:
            tmp = Path(f.name)
        proc = subprocess.run(
            [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
             "-vf", f"scale='min({max_side},iw)':-2", "-q:v", "3", str(tmp)],
            capture_output=True, text=True, errors="ignore", timeout=120,
        )
        if proc.returncode != 0 or not tmp.exists():
            tmp = None
            log.warning("参考图压缩失败，直接用原图: %s", (proc.stderr or '')[-200:])
    use = tmp or src
    try:
        if use.suffix.lower() in (".mp4", ".mov", ".mkv"):
            raise ArkError("参考图不能是视频，请先抽帧")
        raw = use.read_bytes()
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    fmt = "png" if use.suffix.lower() == ".png" else "jpeg"
    return f"data:image/{fmt};base64,{base64.b64encode(raw).decode()}"


# ---------------------------------------------------------------------------
# 图片


def image_body(prompt: str, *, model: str = "", size: str = "2K",
               image_urls: list[str] | None = None) -> dict:
    """拼图片生成请求体（单独拆出来，逐字段自检不用真发请求）。"""
    from app.core.config import settings

    body: dict = {
        "model": model or settings.ark_image_model,
        "prompt": prompt.strip(),
        "size": size,
        "response_format": "b64_json",
        # 不传 sequential_image_generation：不是所有模型都认这个参数，
        # 传了会直接 400（实测 seedream-5.0-flash 就不认）。默认就是单图。
    }
    urls = [u for u in (image_urls or []) if u]
    if urls:
        body["image"] = urls
    return body


def generate_image(prompt: str, *, out: Path, ref_image: Path | None = None,
                   ref_images: list[Path] | None = None,
                   model: str = "", size: str = "2K",
                   timeout: float = 240) -> Path:
    """文生图 / 图生图。给了 ref_image 就是图生图。

    图生图在这里的用途：拿原片某一帧当参考，保持构图、景别、光线不变，
    只把画面主体换掉 —— 这样人物不会跑形，也不会和原片节奏对不上。
    """
    if not (prompt or "").strip():
        raise ArkError("提示词不能为空")
    # 参考图可以是数组（官方图片生成 API：`image` 收 string 或 string[]）。
    # 顺序就是提示词里的「图一/图二」—— 换人时第一张是原片帧、第二张是人物图，
    # 少了人物图，模型只能按文字凭空造一张脸。
    items: list[Path] = []
    if ref_image is not None:
        items.append(Path(ref_image))
    items.extend(Path(x) for x in (ref_images or []))
    body = image_body(prompt, model=model, size=size,
                      image_urls=[_data_uri(x, VIDEO_REF_MAX_SIDE) for x in items])

    t0 = time.time()
    with httpx.Client(timeout=timeout) as c:
        r = c.post(IMAGES, headers=_headers(), json=body)
    if r.status_code != 200:
        raise ArkError(f"图片生成失败 HTTP {r.status_code}: {r.text[:300]}")
    data = r.json().get("data") or []
    if not data:
        raise ArkError(f"图片生成没有返回结果: {r.text[:300]}")
    item = data[0]
    raw = None
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        with httpx.Client(timeout=120) as c:
            raw = c.get(item["url"]).content
    if not raw:
        raise ArkError("图片结果里既没有 b64_json 也没有 url")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    log.info("生成图片 %s (%.1fKB, %.1fs)", out.name, len(raw) / 1024, time.time() - t0)
    return out


# ---------------------------------------------------------------------------
# 视频


def _find_video_url(obj, depth: int = 0) -> str:
    """在响应里递归找视频地址。

    方舟不同模型/版本返回的形状不一样：content 可能是 list 也可能是 dict，
    video_url 可能是字符串也可能是 {"url": ...}。与其猜形状，不如全找一遍。
    """
    if depth > 6:
        return ""
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("http") and (".mp4" in s.lower() or "/video" in s.lower()):
            return s
        return ""
    if isinstance(obj, dict):
        # 先认明确的字段名，避免抓到封面图
        for k in ("video_url", "url"):
            if k in obj:
                u = _find_video_url(obj[k], depth + 1)
                if u:
                    return u
        for k, v in obj.items():
            if k in ("cover_url", "poster_url", "thumbnail_url"):
                continue
            u = _find_video_url(v, depth + 1)
            if u:
                return u
        return ""
    if isinstance(obj, list):
        for v in obj:
            u = _find_video_url(v, depth + 1)
            if u:
                return u
    return ""


def generate_video(prompt: str, *, out: Path, model: str,
                   first_frame: Path | None = None,
                   last_frame: Path | None = None,
                   duration: int = 5, ratio: str = "16:9",
                   resolution: str = "720p", watermark: bool = False,
                   timeout: float = 900, poll: float = 4.0) -> Path:
    """图生视频 / 文生视频（异步任务：创建 → 轮询 → 下载）。

    `last_frame` = 官方「图生视频-首尾帧」（`volc-create.md:27/:241-243`）：
    同时给首帧和尾帧，模型只生成中间过渡。官方只有「首帧」和「首尾帧」两种，
    **没有单独的尾帧**，所以给了尾帧就必须给首帧。

    🩸 首帧 / 首尾帧 / 全模态参考**三种互斥，不可混用**（`volc-create.md:269`）——
    所以这条路径不能带 `reference_video`，编辑任务永远用不上尾帧。
    """
    if last_frame is not None and first_frame is None:
        raise ArkError("给了尾帧就必须给首帧：官方只有「首帧」和「首尾帧」，没有单独的尾帧")

    content: list[dict] = []
    if (prompt or "").strip():
        content.append({"type": "text", "text": prompt.strip()})
    if first_frame is not None:
        content.append({
            "type": "image_url",
            "image_url": {"url": _data_uri(Path(first_frame), VIDEO_REF_MAX_SIDE)},
            "role": "first_frame",
        })
    if last_frame is not None:
        # 顺序固定「先首后尾」：宽高比不一致时官方以首帧为主、尾帧自动裁剪
        # （`volc-create.md:247`），顺序本身不影响判定，但读起来和官方一致。
        content.append({
            "type": "image_url",
            "image_url": {"url": _data_uri(Path(last_frame), VIDEO_REF_MAX_SIDE)},
            "role": "last_frame",
        })
    if not content:
        raise ArkError("提示词和首帧至少要给一个")

    model_id = model
    # 🩸 Seedance 2.5 的首尾帧「默认且仅支持 adaptive」（`volc-create.md:505`）：
    # 传具体宽高比会被拒或表现异常。2.0 系列可以指定，不动它们。
    if last_frame is not None and str(ratio).lower() != "adaptive":
        from app.services import model_specs

        if model_specs.volc(model_id).get("edit_task_param"):
            log.warning("Seedance 2.5 的首尾帧只支持 adaptive，ratio %s → adaptive", ratio)
            ratio = "adaptive"

    body = {
        "model": model_id,
        "content": content,
        "duration": max(1, int(duration)),
        "ratio": ratio,
        "resolution": resolution,
        "watermark": watermark,
    }
    from app.services import retry

    # 上次已经提交过、请求一模一样 → 直接去取那个任务，不重复花钱
    old = _load_tid(out, body)
    if old:
        try:
            log.info("接着上次提交的任务 %s 取结果（不重新提交）", old)
            return _download_video(old, out, timeout=timeout, poll=poll)
        except ArkError as e:
            if not _is_dead(getattr(e, "detail", None)):
                raise
            log.warning("上次的任务 %s 已在平台侧失效，重新提交", old)

    with httpx.Client(timeout=60) as c:
        r = retry.post(c, VIDEO_TASKS, headers=_headers(), json=body)
    if r.status_code == 429:
        raise ArkError("火山并发/频率超了（429）。多人同时出片时会这样，等一两分钟再跑这一条")
    if r.status_code != 200:
        raise ArkError(f"创建视频任务失败 HTTP {r.status_code}: {r.text[:300]}")
    tid = (r.json() or {}).get("id")
    if not tid:
        raise ArkError(f"创建任务没拿到 id: {r.text[:200]}")
    _save_tid(out, tid, body)
    return _download_video(tid, out, timeout=timeout, poll=poll)


def _clone_root(out: Path) -> Path | None:
    """成片所在那一单的根目录（就是放着 `task.json` 的最近一层祖先）。"""
    for p in out.parents:
        if (p / "task.json").exists():
            return p
    return None


def _task_state(out: Path, body: dict) -> Path:
    """任务号落盘的位置。

    🩸 2026-10-26 第三次付代价：原来写死 `<out>.task.json`，而 `out` 在
    `render/<rid>/triage/gen/` 下 —— 重启后重跑会开**新单（新 rid）**，路径对不上，
    平台那边明明已经生成成功、任务号也存着，却只能重新提交、再花一遍钱
    （当次实测：`cgt-20261026182132-wqfw4` 18:25 成功，取不回来）。
    改成认**克隆目录 + 请求体指纹**：只要请求一模一样，跨单也能认领回来。
    没有克隆目录（脚本/测试的临时路径）时才退回旧位置。
    """
    root = _clone_root(out)
    if root is not None:
        return root / "cache" / "gen" / f"{_task_sig(body)}.json"
    return Path(str(out) + ".task.json")


def _task_sig(body: dict) -> str:
    import hashlib
    import json as _json

    raw = _json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _load_tid(out: Path, body: dict) -> str:
    """上一次已经提交、但还没取回结果的任务号。

    🩸 为什么必须有（2026-10-24 付过代价）：任务号原来只存在内存里，进程一重启
    （或被 kill）就丢了 —— 平台那边生成完也取不回来，只能重新提交、重新花钱。
    这里按**请求体的哈希**认领，请求变了（换提示词/换参考图）就不认旧号。
    """
    sig = _task_sig(body)
    # 新位置优先；旧位置也读一眼 —— 升级前提交、还挂在平台上的任务不至于白扔
    paths = [_task_state(out, body), Path(str(out) + ".task.json")]
    for p in dict.fromkeys(paths):
        try:
            if not p.exists():
                continue
            import json as _json

            d = _json.loads(p.read_text(encoding="utf-8")) or {}
            if str(d.get("sig") or "") != sig:
                continue
            tid = str(d.get("tid") or "")
            if tid:
                return tid
        except Exception as e:  # noqa: BLE001
            log.warning("读任务号失败（按没有处理）：%s", e)
    return ""


def _save_tid(out: Path, tid: str, body: dict) -> None:
    try:
        import json as _json

        p = _task_state(out, body)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_json.dumps({"tid": tid, "sig": _task_sig(body)},
                                 ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("写任务号失败（不影响这次生成）：%s", e)


def _is_dead(detail: dict | None) -> bool:
    """这个任务号在平台上已经废了（可以安全地重新提交）。"""
    return str((detail or {}).get("status") or "") in ("failed", "cancelled", "expired")


def last_frame_path(out: Path) -> Path:
    """平台返回的真实尾帧落盘位置（与成片同名，`.last.jpg`）。

    官方口径：尾帧是 jpeg、宽高与成片一致、无水印，URL **只保 24 小时**
    （2.5 `api-get.md:65`；2.0 同字段 `sd20/api-get.md:65`）——
    必须当场落盘，否则 24 小时后这条接缝素材就没了。
    """
    return out.with_suffix(".last.jpg")


def _http_url(v) -> str:
    """字段值可能是字符串，也可能是 `{"url": ...}` —— 两种都认。"""
    if isinstance(v, str):
        s = v.strip()
        return s if s.startswith("http") else ""
    if isinstance(v, dict):
        for k in ("url", "last_frame_url"):
            u = _http_url(v.get(k))
            if u:
                return u
    return ""


def _find_last_frame_url(obj, depth: int = 0) -> str:
    """在任务响应里找 `content.last_frame_url`（不同版本外层形状不一，递归找）。"""
    if depth > 6:
        return ""
    if isinstance(obj, dict):
        u = _http_url(obj.get("last_frame_url"))
        if u:
            return u
        for v in obj.values():
            u = _find_last_frame_url(v, depth + 1)
            if u:
                return u
    elif isinstance(obj, list):
        for v in obj:
            u = _find_last_frame_url(v, depth + 1)
            if u:
                return u
    return ""


def _save_last_frame(url: str, out: Path) -> Path | None:
    """下载平台尾帧。**失败只告警** —— 尾帧是加分项，不能让它把已付费的成片判失败。"""
    if not url:
        return None
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as c:
            r = c.get(url)
        if r.status_code != 200:
            log.warning("下载尾帧失败 HTTP %s（成片不受影响）", r.status_code)
            return None
        p = last_frame_path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)
        log.info("平台真实尾帧 %s (%.0fKB)", p.name, len(r.content) / 1024)
        return p
    except Exception as e:  # noqa: BLE001
        log.warning("下载尾帧失败（成片不受影响）：%s", e)
        return None


def _download_urls(out: Path, video_url: str, last_url: str, *, t0: float) -> Path:
    """下载成片 + （有就）下载尾帧。下载/落盘规则只此一处。"""
    with httpx.Client(timeout=600, follow_redirects=True) as c:
        v = c.get(video_url)
    if v.status_code != 200:
        raise ArkError(f"下载视频失败 HTTP {v.status_code}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(v.content)
    log.info("生成视频 %s (%.1fMB, %.0fs)", out.name,
             len(v.content) / 1024 / 1024, time.time() - t0)
    _save_last_frame(last_url, out)
    return out


def _download_video(tid: str, out: Path, *, timeout: float, poll: float) -> Path:
    """轮询任务号 → 下载成片（+ 尾帧）。generate_video 和 edit_video 共用。"""
    t0 = time.time()
    url, last_url = _poll_urls(tid, timeout=timeout, poll=poll)
    return _download_urls(out, url, last_url, t0=t0)


def _poll_urls(tid: str, *, timeout: float, poll: float) -> tuple[str, str]:
    """轮询到成功，返回 (视频地址, 尾帧地址)。没请求尾帧时第二个是空串。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(poll)
        with httpx.Client(timeout=60) as c:
            q = c.get(f"{VIDEO_TASKS}/{tid}", headers=_headers())
        if q.status_code != 200:
            log.warning("查询任务 %s 失败 HTTP %s", tid, q.status_code)
            continue
        d = q.json() or {}
        st = d.get("status")
        if st == "succeeded":
            # 返回结构在不同模型/版本下不一样（content 可能是 list、可能是 dict，
            # video_url 可能是字符串也可能是 {"url": ...}）—— 递归找，不猜形状。
            url = _find_video_url(d)
            if url:
                return url, _find_last_frame_url(d)
            raise ArkError(f"视频任务 {tid} 成功但找不到 video_url: {str(d)[:300]}")
        # expired = 超过 execution_expires_after 被平台终止；不认它就会一直空转到超时
        if st in ("failed", "cancelled", "expired"):
            import json as _json

            raw = _json.dumps(d, ensure_ascii=False, default=str)
            detail = _err_detail(raw, step="poll_task")
            detail.update({"task_id": tid, "status": st})
            log.error("视频任务 %s 状态 %s code=%s 原始=%s", tid, st,
                      detail.get("code") or "-", raw[:2000])
            raise ArkError(f"视频任务 {tid} 状态 {st}: {d.get('error')}",
                           detail=detail)
    raise ArkError(f"视频任务 {tid} 超时（{timeout:.0f}s）")


def _poll_video_url(tid: str, *, timeout: float, poll: float) -> str:
    """只要视频地址时的薄包装（保留旧调用点语义）。"""
    return _poll_urls(tid, timeout=timeout, poll=poll)[0]


# ---------------------------------------------------------------------------
# C17 云端任务恢复：只查/只取，**绝不重新提交**
# ---------------------------------------------------------------------------


def fetch_task(tid: str) -> dict:
    """查一次任务状态（不轮询、不下载、不提交）。

    返回 `{status, video_url, last_frame_url}`；`status` 是平台原值
    （submitted / running / succeeded / failed / cancelled / expired …）。
    """
    with httpx.Client(timeout=60) as c:
        r = c.get(f"{VIDEO_TASKS}/{tid}", headers=_headers())
    if r.status_code != 200:
        raise ArkError(f"查询任务状态失败 HTTP {r.status_code}（任务号 {tid}）")
    d = r.json() or {}
    st = str(d.get("status") or "")
    return {
        "status": st,
        "video_url": _find_video_url(d) if st == "succeeded" else "",
        "last_frame_url": _find_last_frame_url(d) if st == "succeeded" else "",
    }


def retrieve_task(tid: str, out: Path) -> dict:
    """领回**已提交**的任务结果：只查询 + 下载，绝不提交新任务、不花新钱。

    平台还在跑 → 原样返回状态；已经成功 → 下载成片（含尾帧）并落盘。
    """
    got = fetch_task(tid)
    if got["status"] != "succeeded":
        return got
    if not got["video_url"]:
        raise ArkError(f"任务 {tid} 显示成功，但响应里找不到 video_url")
    _download_urls(Path(out), got["video_url"], got["last_frame_url"], t0=time.time())
    return got


# ---------------------------------------------------------------------------
# 整片编辑（Seedance 2.5 的 edit 任务）


def _audio_uri(path: Path) -> str:
    """音频转 data URI。火山收 base64 音频（官方：`data:audio/<格式>;base64,…`），
    不像视频那样必须先传公网 URL —— 少一次上传、少一份素材额度。"""
    p = Path(path)
    if not p.exists():
        raise ArkError(f"音频文件不存在：{p}")
    if p.stat().st_size > 15 * 1024 * 1024:
        raise ArkError(f"音频超过 15MB 上限：{p.name}")
    raw = p.read_bytes()
    fmt = "wav" if p.suffix.lower() == ".wav" else "mpeg"
    return f"data:audio/{fmt};base64,{base64.b64encode(raw).decode()}"


def edit_body(
    prompt: str,
    *,
    video_url: str,
    ref_image: Path | None = None,
    ref_images: list | None = None,
    ref_asset: str = "",
    ref_audio: Path | None = None,
    ref_videos: list[str] | None = None,
    model: str = "",
    resolution: str = "720p",
    duration: float = 0.0,
    watermark: bool = False,
    generate_audio: bool = False,
) -> dict:
    """拼出编辑任务要 POST 的整个 body。

    单独拆出来是为了能**逐字段自检**：接口收了什么、按哪个型号的口径收，
    不用真发一次请求就能核对（自检脚本 `test_ark_edit_body.py` 就是这么用的）。
    """
    from app.core.config import settings
    from app.services import model_specs

    content: list[dict] = [
        {"type": "text", "text": prompt},
        {
            "type": "video_url",
            "video_url": {"url": video_url},
            "role": "reference_video",
        },
    ]
    # 额外参考视频（风格参考 A9）：官方 2.0 系列 视频 ≤3 段、2.5 ≤10 段，
    # 且**所有视频总时长** 2.0 ≤15s / 2.5 ≤30s（见 `video_edit.style_video_budget`）。
    # 第 1 条永远是编辑母版，后面的按调用方给的顺序追加。
    for u in (ref_videos or []):
        u = (u or "").strip()
        if u:
            content.append({"type": "video_url", "video_url": {"url": u},
                            "role": "reference_video"})
    # 参考图按调用方给的顺序追加 —— 提示词里的「@图片N」就是这个顺序的第 N 张，
    # 顺序错了模型就会拿错素材，所以这里不排序、不去重。
    # 列表项可以是 Path（本机图，转 base64）或 "asset://<id>" 字符串
    # （虚拟人像库 / 已授权真人素材，平台认可、不受"禁止上传真人脸"限制）。
    items: list = list(ref_images or [])
    if ref_image is not None:
        items.append(ref_image)
    if ref_asset:
        items.append(ref_asset.strip())
    for item in items:
        if isinstance(item, str):
            url = item if item.startswith("asset://") else f"asset://{item}"
        else:
            url = _data_uri(Path(item), VIDEO_REF_MAX_SIDE)
        content.append({
            "type": "image_url",
            "image_url": {"url": url},
            "role": "reference_image",
        })

    # 口型参考音频：与 MiniMax 同一条规则 —— 全新配音喂我们自己合成的配音轨，
    # `original` 模式下喂原片整条音轨（口型参考，不是当音色样本用；
    # 见 video_edit._audio_track 的说明）。
    # 🩸 2.0 系列也收这一项：`volc-create.md:35` 参考音频（0-3 个）支持编辑视频。
    # 2.0 系列单段 [2,15]s，2.5 单段 [2,30]s，挑音轨时已经按 15s 收口。
    if ref_audio is not None:
        content.append({
            "type": "audio_url",
            "audio_url": {"url": _audio_uri(Path(ref_audio))},
            "role": "reference_audio",
        })

    model_id = model or settings.ark_video_edit_model
    spec = model_specs.volc(model_id)
    body: dict = {
        "model": model_id,
        "content": content,
        "resolution": resolution,
        "watermark": watermark,
        # 官方 2.5 / 2.0 系列都认这个字段，默认 true
        "generate_audio": bool(generate_audio),
    }
    if spec["edit_task_param"]:
        # 2.5 才有的显式任务类型；编辑任务 duration 只能 -1、ratio 只能 adaptive
        body["omni_reference_task_type"] = "edit"
        body["duration"] = spec["edit_duration"]
        body["ratio"] = spec["edit_ratio"]
        # 🩸 官方 `seedance-25-guide.md:81`（视频编辑行的锁定说明）
        # 「**建议 output_format 使用 mov 格式**」；同篇 `:339` 差异点 4 给了理由：
        # 「Seedance 2.5 的输出支持 MOV 格式，在**延长/编辑任务中更好地保持
        # 颜色与亮度一致性、声画一致性**」。我们后续还要拼成片，一致性问题会累积。
        # 只给 2.5：2.0 系列文档没有这一项，不替它做决定。
        body["output_format"] = "mov"
    else:
        # 2.0 系列没有 omni_reference_task_type，任务类型靠提示词判定；
        # duration 官方支持具体秒数，也支持 -1（= 模型在 [4,15] 里自己挑**整数秒**）。
        # 🩸 这里给**向上取整**，不给 -1：
        #   2.0 的输出时长只能是整数秒，5.503s 的段由模型"自己挑"就会给 5s ——
        #   成片比原段短 0.5s，拼接时只能把最后一帧冻住补时长（实测 0.46s 静止）。
        #   给 ceil 就一定 ≥ 原段，多出来的直接裁掉：裁尾巴看不出来，冻帧看得出来。
        #   MiniMax 那条路（`_gen_duration`）本来就是 ceil，两边口径也就一致了。
        #   2.5 不能这么干：它的编辑任务官方明令 duration 只能是 -1。
        # ⚠️ 别再写成"显式传数值会判冲突"—— 那条因果是 2026-10-21 的误判，
        # 当时 5.503s 段失败的真因是切点带负 PTS 前置包（见 scene.cut_clip）。
        if duration and duration > 0:
            body["duration"] = max(4, min(15, math.ceil(duration)))
        else:
            body["duration"] = -1
        body["ratio"] = "adaptive"
    return body


def edit_video(
    prompt: str,
    *,
    video_url: str,
    out: Path,
    ref_image: Path | None = None,
    ref_images: list[Path] | None = None,
    ref_asset: str = "",
    ref_audio: Path | None = None,
    ref_videos: list[str] | None = None,
    model: str = "",
    resolution: str = "720p",
    duration: float = 0.0,
    # 默认不打「AI 生成」角标：成片是要直接发出去的
    watermark: bool = False,
    # 官方默认 true：模型会自己生成人声/音效/BGM。我们的音轨永远来自 TTS 或原片，
    # 生成出来的那条会被丢掉 —— 白花钱，而且让模型把算力分给声音。
    generate_audio: bool = False,
    timeout: float = 2400,
    poll: float = 6.0,
) -> Path:
    """在原视频上做编辑：换主体、增删对象、局部重绘。

    和 generate_video 的根本差别：
      generate_video 是"从一张首帧重新生成"，动作信息只有那一帧；
      edit_video 是"拿整段原片当编辑对象"，模型逐帧参考原片，
      所以输出的**宽高比、时长、动作、运镜、节奏都跟原片一致** —— 这才是 1:1。

    限制（官方，2026-10-21 抓自 /docs/82379/1520757 与 /docs/82379/2607688）：
      - 参考视频必须是**公网 URL**，不接受 base64
      - 2.5 编辑任务：单段 **4–30s**；ratio 只能是 adaptive；duration 只能是 -1；
        提示词里**必须**出现「编辑视频/增加/加上/删除/去掉/修改/替换/改成」之一
      - 2.0 系列编辑任务：输出时长 4~15 秒（`sd20.md:119`），只能整数秒；
        ratio 可 adaptive 或指定宽高比（`volc-create.md:506`）；
        没有 omni_reference_task_type（该字段只支持 2.5，`volc-create.md:442`），
        任务类型靠提示词判定
      - 参考视频本身的硬门槛：分辨率 480p/720p/1080p/4k、宽高比 [0.4,2.5]、
        总像素 [407696, 8295044]、帧率 [24,60]、单文件 ≤200MB
    """
    from app.core.config import settings

    prompt = (prompt or "").strip()
    if not prompt:
        raise ArkError("提示词不能为空")
    if not video_url:
        raise ArkError("edit 任务必须给参考视频的公网 URL")

    body = edit_body(
        prompt, video_url=video_url, ref_images=ref_images, ref_image=ref_image,
        ref_asset=ref_asset, ref_audio=ref_audio, ref_videos=ref_videos,
        model=model, resolution=resolution,
        duration=duration, watermark=watermark, generate_audio=generate_audio,
    )
    # 失败排查全靠这一行：哪些参数真的发出去了（URL 只记形态，不漏公网地址）
    log.info(
        "编辑任务请求 model=%s resolution=%s duration=%s ratio=%s refs=%d "
        "audio=%s video=%s",
        body.get("model"), body.get("resolution"), body.get("duration"),
        body.get("ratio"),
        sum(1 for x in body.get("content") or [] if x.get("type") == "image_url"),
        "有" if ref_audio is not None else "无",
        "asset://" if video_url.startswith("asset://") else "URL",
    )
    return _run_video_task(body, out, timeout=timeout, poll=poll, tag="编辑")


def _run_video_task(body: dict, out: Path, *, timeout: float, poll: float,
                    tag: str, want_last_frame: bool = False) -> Path:
    """建任务 → 轮询 → 下载。编辑和延长走的是同一个接口，只有 body 不同。

    `want_last_frame` 只加在**真正发出去的 payload** 上，不进 `body` ——
    `_task_sig` 认的是 `body`，这样升级前已提交、还挂在平台上的任务仍能按旧指纹
    领回来（避免为了一个新开关把在飞任务作废、重新付一次钱）。
    代价：领回来的旧任务没请求过尾帧，这次就拿不到尾帧（下次新任务才有）。
    """
    from app.services import retry

    # 进程被杀/重启后，先用上次落盘的任务号去取，别重新提交（重提交=重新花钱）
    old = _load_tid(out, body)
    if old:
        try:
            log.info("接着上次提交的%s任务 %s 取结果（不重新提交）", tag, old)
            return _download_video(old, out, timeout=timeout, poll=poll)
        except ArkError as e:
            if not _is_dead(getattr(e, "detail", None)):
                raise
            log.warning("上次的%s任务 %s 已在平台侧失效，重新提交", tag, old)

    payload = {**body, "return_last_frame": True} if want_last_frame else body
    with httpx.Client(timeout=120) as c:
        r = retry.post(c, VIDEO_TASKS, headers=_headers(), json=payload)
    if r.status_code == 429:
        raise ArkError("火山并发/频率超了（429）。多人同时出片时会这样，等一两分钟再跑这一条")
    if r.status_code != 200:
        # 完整响应体进 detail（不截断），消息里只放前 400 字符给界面看
        detail = _err_detail(r.text, step="create_task", http=r.status_code)
        log.error("创建%s任务失败 HTTP %s code=%s request_id=%s 原始=%s",
                  tag, r.status_code, detail.get("code") or "-",
                  detail.get("request_id") or "-", r.text[:2000])
        raise ArkError(f"创建{tag}任务失败 HTTP {r.status_code}: {r.text[:400]}",
                       detail=detail)
    tid = (r.json() or {}).get("id")
    if not tid:
        raise ArkError(f"创建任务没拿到 id: {r.text[:200]}",
                       detail=_err_detail(r.text, step="create_task",
                                          http=r.status_code))

    _save_tid(out, tid, body)
    t0 = time.time()
    url, last_url = _poll_urls(tid, timeout=timeout, poll=poll)
    # ⚠️ 2.5 编辑任务要的是 mov 容器（`edit_body` 的 `output_format`），但这里
    # 不管后缀 —— `out` 由调用方定，一直是 `chunk_XXX.mp4`，文件里装的其实是
    # mov。**不用转封装**：下游（`_normalize` / `_fit_segment` / `assemble`）
    # 全部交给 ffmpeg，它按内容探测容器，不看后缀；最终成片是重新编码的 mp4。
    # 只有"把中间产物直接甩给浏览器"时才需要在意，而那条路不存在。
    # 下载/落盘只走 `_download_urls` 一处：起任务和领旧任务（`_download_video`）
    # 两条路的成片、尾帧规则必须一样，别再各自写一份（尾帧漏下过一次）。
    return _download_urls(out, url, last_url, t0=t0)


def extend_body(
    prompt: str,
    *,
    video_url: str,
    ref_images: list | None = None,
    ref_asset: str = "",
    model: str = "",
    resolution: str = "720p",
    duration: int = 5,
    watermark: bool = False,
    generate_audio: bool = False,
) -> dict:
    """视频延长任务的请求体。

    官方口径（2.5 指南「有锁定：编辑/首尾帧/延长」表）：
      - 宽高比**锁定**为待延长视频的比例 → `ratio` 必须 `adaptive`
      - **时长支持用户自定义**（与编辑任务相反，编辑只能 -1）
      - 触发条件：`content.role` = reference_image / reference_video / reference_audio
        + 提示词里出现「向前/向后延长、延续、续写」之一
      - 建议输出 MOV，画面/声音衔接更稳
    2.0 指南「延长视频」同节：句式「向前/向后延长<视频N>，生成…」，
    并明确**别写「参考<视频N>」**，否则会被判成参考任务。
    """
    from app.core.config import settings
    from app.services import model_specs

    prompt = (prompt or "").strip()
    if not prompt:
        raise ArkError("延长任务的提示词不能为空")
    if not video_url:
        raise ArkError("延长任务必须给待延长视频的公网 URL")

    content: list[dict] = [
        {"type": "text", "text": prompt},
        {"type": "video_url", "video_url": {"url": video_url},
         "role": "reference_video"},
    ]
    for item in list(ref_images or []) + ([ref_asset] if ref_asset else []):
        if isinstance(item, str):
            url = item if item.startswith("asset://") else f"asset://{item}"
        else:
            url = _data_uri(Path(item), VIDEO_REF_MAX_SIDE)
        content.append({"type": "image_url", "image_url": {"url": url},
                        "role": "reference_image"})

    model_id = model or settings.ark_video_edit_model
    spec = model_specs.volc(model_id)
    body: dict = {
        "model": model_id,
        "content": content,
        "resolution": resolution,
        "watermark": watermark,
        "generate_audio": bool(generate_audio),
        # 延长任务：比例锁定待延长视频，时长由用户定
        "ratio": "adaptive",
        "duration": max(2, int(round(duration))),
    }
    # 延长段按各型号自己的时长区间收口（2.0 4–15s / 2.5 4–30s）：
    # 下限也得管 —— 2.5 送 2s 会被模型直接拒掉
    lo = max(2, int(round(float(spec.get("min_sec") or 2))))
    body["duration"] = max(lo, min(int(body["duration"]), int(spec["max_sec"])))
    return body


def extend_video(
    prompt: str,
    *,
    video_url: str,
    out: Path,
    ref_images: list | None = None,
    ref_asset: str = "",
    model: str = "",
    resolution: str = "720p",
    duration: int = 5,
    watermark: bool = False,
    generate_audio: bool = False,
    timeout: float = 2400,
    poll: float = 6.0,
) -> Path:
    body = extend_body(
        prompt, video_url=video_url, ref_images=ref_images, ref_asset=ref_asset,
        model=model, resolution=resolution, duration=duration,
        watermark=watermark, generate_audio=generate_audio,
    )
    log.info("延长任务请求 model=%s resolution=%s duration=%s refs=%d",
             body["model"], body["resolution"], body["duration"],
             sum(1 for x in body["content"] if x.get("type") == "image_url"))
    return _run_video_task(body, out, timeout=timeout, poll=poll, tag="延长")


def transition_body(
    prompt: str,
    *,
    video_a: str,
    video_b: str,
    model: str = "",
    resolution: str = "720p",
    duration: int = 4,
    watermark: bool = False,
    generate_audio: bool = False,
) -> dict:
    """两段视频补全间隙（无缝转场）的请求体。

    官方口径：
      - 2.5 能力清单 `seedance-25-guide.md:69`「视频无缝转场 - 输入两段视频，
        模型生成补全间隙实现无缝转场」；示例句式 `:1337`
      - 2.0 叫「轨道补齐」（`seedance-20-guide.md:988-1000`）：≤3 段、总时长 ≤15s
      - 它属于**全模态参考生视频**（`volc-create.md:25/:35`），不是编辑：
        `:458` 明说 `omni_reference_task_type=reference` 时 `ratio`/`duration` 无特殊限制。
        🩸 不显式声明的话模型可能按编辑任务判定 → `ratio` 必须 adaptive、`duration` 必须 -1
        的那套限制会打架（`:460`）。
      - 输出时长下限 4 秒（`:588` 2.5 是 [4,30]、2.0 系列 [4,15]），短于它接缝吃不下
    """
    from app.core.config import settings
    from app.services import model_specs

    prompt = (prompt or "").strip()
    if not prompt:
        raise ArkError("转场任务的提示词不能为空")
    for tag, u in (("@视频1", video_a), ("@视频2", video_b)):
        if not (u or "").strip():
            raise ArkError(f"转场任务必须给{tag}的公网 URL")

    # 顺序就是提示词里的编号：第 1 段 = @视频1，第 2 段 = @视频2。
    content: list[dict] = [
        {"type": "text", "text": prompt},
        {"type": "video_url", "video_url": {"url": video_a.strip()},
         "role": "reference_video"},
        {"type": "video_url", "video_url": {"url": video_b.strip()},
         "role": "reference_video"},
    ]

    model_id = model or settings.ark_video_edit_model
    spec = model_specs.volc(model_id)
    lo = max(4, int(round(float(spec.get("min_sec") or 4))))
    hi = int(spec["max_sec"])
    body: dict = {
        "model": model_id,
        "content": content,
        "resolution": resolution,
        "watermark": watermark,
        "generate_audio": bool(generate_audio),
        # 接缝两侧的片段跟原片同规格，比例交给模型自适应最稳
        "ratio": "adaptive",
        "duration": max(lo, min(int(round(duration)), hi)),
    }
    if spec["edit_task_param"]:
        # 只有 2.5 认这个字段（`volc-create.md:442`）；2.0 系列靠提示词判定
        body["omni_reference_task_type"] = "reference"
        body["output_format"] = "mov"
    return body


def transition_video(
    prompt: str,
    *,
    video_a: str,
    video_b: str,
    out: Path,
    model: str = "",
    resolution: str = "720p",
    duration: int = 4,
    watermark: bool = False,
    generate_audio: bool = False,
    timeout: float = 2400,
    poll: float = 6.0,
) -> Path:
    body = transition_body(
        prompt, video_a=video_a, video_b=video_b, model=model,
        resolution=resolution, duration=duration, watermark=watermark,
        generate_audio=generate_audio,
    )
    log.info("转场任务请求 model=%s resolution=%s duration=%s（两段参考视频）",
             body["model"], body["resolution"], body["duration"])
    return _run_video_task(body, out, timeout=timeout, poll=poll, tag="转场")


def omni_body(
    prompt: str,
    *,
    ref_images: list[str] | None = None,
    model: str = "",
    resolution: str = "720p",
    duration: int = 5,
    ratio: str = "9:16",
    watermark: bool = False,
    generate_audio: bool = True,
) -> dict:
    """**全模态参考生视频**的请求体：从零生成，参考图锁人物/商品/场景。

    和 `edit_body`（改原片）、`transition_body`（两段之间补缝）都不同 ——
    这条没有待编辑视频，画面完全由提示词 + 参考图决定。

    官方口径（`volc-create.md:25/:35`）：
      · 属于「全模态参考生视频」；`:458` 明说 `omni_reference_task_type=reference`
        时 `ratio` / `duration` 无特殊限制（不显式声明可能被按编辑任务判定，
        那套要求 `ratio=adaptive`、`duration=-1`，会打架 `:460`）。
      · `omni_reference_task_type` 只有 2.5 认（`:442`），2.0 系列靠提示词判定。

    参考图顺序就是提示词里的 `@图片N` 编号：数组第 1 张 = @图片1，绝不重排。
    """
    from app.core.config import settings
    from app.services import model_specs

    prompt = (prompt or "").strip()
    if not prompt:
        raise ArkError("出片提示词不能为空")

    content: list[dict] = [{"type": "text", "text": prompt}]
    for u in (ref_images or []):
        u = (u or "").strip()
        if not u:
            continue
        content.append({
            "type": "image_url",
            "image_url": {"url": u},
            "role": "reference_image",
        })

    # 用**单独的**配置项：商品短剧要 30s 单次 + 多张 `reference_image`，
    # 只有 2.5 给得出来，和复刻线的 edit 任务不是一套参数。
    model_id = model or settings.ark_video_film_model
    spec = model_specs.volc(model_id)
    lo = max(1, int(round(float(spec.get("min_sec") or 4))))
    hi = int(spec.get("max_sec") or 15)
    body: dict = {
        "model": model_id,
        "content": content,
        "resolution": resolution,
        "watermark": watermark,
        "generate_audio": bool(generate_audio),
        "ratio": ratio,
        "duration": max(lo, min(int(round(duration)), hi)),
    }
    # 显式声明任务类型 —— 只有 2.5 认。判据是 `edit_duration == -1`
    # （2.5 的编辑任务只支持 duration=-1、ratio=adaptive 这套，`volc-create.md:442/:460`）。
    # 🩸 不能用 `edit_task_param`：1.0-pro-fast 在表里也是 True。
    if spec.get("edit_duration") == -1:
        body["omni_reference_task_type"] = "reference"
        body["output_format"] = "mov"
    return body


def omni_video(
    prompt: str,
    *,
    out: Path,
    ref_images: list[str] | None = None,
    model: str = "",
    resolution: str = "720p",
    duration: int = 5,
    ratio: str = "9:16",
    watermark: bool = False,
    generate_audio: bool = True,
    timeout: float = 2400,
    poll: float = 6.0,
) -> Path:
    body = omni_body(
        prompt, ref_images=ref_images, model=model, resolution=resolution,
        duration=duration, ratio=ratio, watermark=watermark,
        generate_audio=generate_audio,
    )
    log.info("全模态参考生视频 model=%s resolution=%s duration=%s ratio=%s 参考图=%d 音轨=%s",
             body["model"], body["resolution"], body["duration"], body["ratio"],
             sum(1 for x in body["content"] if x.get("type") == "image_url"),
             body["generate_audio"])
    # 让平台把**真实尾帧**一起返回：jpeg、与成片同宽高、无水印，24 小时内必须取走
    # （2.5 `api-get.md:65`；2.0 同字段 `sd20/api-get.md:65`；创建参数
    #  `api-create-task.md:707` / `sd20/api-create.md:612`，默认 false）。
    # 官方给的用法就是「上一段尾帧作为下一段首帧，连续生成多段」。
    return _run_video_task(body, out, timeout=timeout, poll=poll, tag="出片",
                           want_last_frame=True)
