"""MiniMax H3 客户端：视频生成 + 素材上传。

H3 是全模态模型（文本 / 图 / 视频 / 音频进，出**带原生音轨**的视频）。
对我们的用途只有一个：拿原片当参考视频，把主体换掉，动作和运镜跟着原片走。

两个和火山不一样的工程点，踩之前先看：
  1) **域名**：国内站 api.minimaxi.com，海外站 api.minimax.io。
     同一把 key 打海外站会直接 401 invalid api key（实测过），别乱换。
  2) **素材要先上传**：请求体上限 64MB，官方明确建议大文件走
     `mm_file://{file_id}` 而不是 base64 —— 本地文件必须先 POST /v1/files/upload。

接口：
  POST /v1/files/upload                      purpose=video_generation_input
  POST /v2/video_generation                  建任务，拿 task_id
  GET  /v2/query/video_generation/{task_id}  轮询
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

# 参考视频/音频的单段范围（官方 OpenAPI：「单段时长 [2, 15] s；总时长 ≤ 15 s；个数 ≤ 3」）
# ⚠️ 这是**输入素材**的时长，不是生成时长 —— 生成时长 H3 是 4~15s、H3-Max 是 5~15s，
#    要查 model_specs，别拿这两个常量当生成时长用。
MAX_CLIP_SECONDS = 15.0
# 单文件大小上限（官方「输入媒体限制」，2026-10-28 复核）：
#   图片 ≤ 30 MB · 视频 ≤ 50 MB · 音频 ≤ 15 MB
# 🩸 以前只查了音频。文件超限时接口照样会拒，但那是在**上传之后**——
#   大文件传上去再失败，时间白花；这几条一律在设计时就拦。
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
# 文件有效期 7 天，过了要重传
FILE_TTL_NOTE = "mm_file:// 引用 7 天后过期"


class MinimaxError(RuntimeError):
    """带结构的错误：`detail` 放**平台返回的完整对象**（含敏感类型等字段）。

    🩸 2026-10-23：轮询只取 `task.error`（code + message），把同级的
    `input_sensitive` / `output_sensitive` / `output_sensitive_type` 全丢了
    —— 官方错误表只说 "Please change your input content"，
    没有类型就查不出到底哪类内容踩线。
    """

    def __init__(self, msg: str, detail: dict | None = None):
        super().__init__(msg)
        self.detail = detail or {}


def _cfg():
    from app.core.config import settings

    return settings


def _key() -> str:
    k = (_cfg().minimax_api_key or "").strip()
    if not k:
        raise MinimaxError("MiniMax 未配置：请设置 VT_MINIMAX_API_KEY")
    return k


def _base() -> str:
    return (_cfg().minimax_base or "https://api.minimaxi.com").rstrip("/")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_key()}"}


def available() -> bool:
    return bool((_cfg().minimax_api_key or "").strip())


def _audio_len(path: Path) -> float:
    """音轨时长，只为打日志。探不到就返回 0，不影响出片。"""
    try:
        from app.services import scene

        return float(scene.probe(Path(path)).get("duration") or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


# ---------------------------------------------------------------------------
# 上传


def upload_file(path: Path, purpose: str = "video_generation_input") -> str:
    """把本地文件传到 MiniMax，返回 file_id（调用侧拼成 mm_file://{id}）。

    purpose 必须是 video_generation_input，否则生成接口不认这个 file_id。
    """
    p = Path(path)
    if not p.exists():
        raise MinimaxError(f"文件不存在：{p}")
    url = f"{_base()}/v1/files/upload"
    with p.open("rb") as f:
        files = {"file": (p.name, f, "application/octet-stream")}
        data = {"purpose": purpose}
        with httpx.Client(timeout=300) as c:
            r = c.post(url, headers=_headers(), files=files, data=data)
    if r.status_code != 200:
        raise MinimaxError(f"上传失败 HTTP {r.status_code}: {r.text[:300]}")
    body = r.json() or {}
    base = body.get("base_resp") or {}
    if base.get("status_code") not in (0, None):
        raise MinimaxError(f"上传被拒：{base.get('status_msg')}")
    fid = (body.get("file") or {}).get("file_id")
    if not fid:
        raise MinimaxError(f"上传没拿到 file_id: {r.text[:200]}")
    log.info("MiniMax 上传 %s (%.1fMB) -> %s", p.name, p.stat().st_size / 1024 / 1024, fid)
    return str(fid)


# ---------------------------------------------------------------------------
# 生成


def _load_tid(out: Path, body: dict) -> str:
    from app.services.ark import _load_tid as _load
    return _load(out, body)


def _save_tid(out: Path, tid: str, body: dict) -> None:
    from app.services.ark import _save_tid as _save
    _save(out, tid, body)


def _is_dead(detail: dict | None) -> bool:
    from app.services.ark import _is_dead as _dead
    return _dead(detail)


def _poll_download(task_id: str, out: Path, *, timeout: float,
                   poll: float) -> Path:
    """轮询任务号 → 下载成片。建任务和"重启后接着取"共用这一条。"""
    t0 = time.time()
    video_url = ""
    while time.time() - t0 < timeout:
        time.sleep(poll)
        with httpx.Client(timeout=60) as c:
            q = c.get(f"{_base()}/v2/query/video_generation/{task_id}",
                      headers=_headers())
        if q.status_code != 200:
            log.warning("查询任务 %s 失败 HTTP %s", task_id, q.status_code)
            continue
        task = (q.json() or {}).get("task") or {}
        st = task.get("status")
        if st == "succeeded":
            video_url = (task.get("content") or {}).get("url") or ""
            if not video_url:
                raise MinimaxError(f"任务成功但没有视频地址: {q.text[:300]}")
            log.info("MiniMax 任务 %s 完成，用时 %.0fs，用量 %s",
                     task_id, time.time() - t0, task.get("usage"))
            break
        if st in ("failed", "cancelled"):
            # 🩸 整个 task 对象一起带上：官方查询接口会带
            # input_sensitive / output_sensitive / output_sensitive_type，
            # 只留 error.code 等于把"哪类内容踩线"这条线索扔掉。
            detail = {"step": "poll_task", "task_id": task_id, "status": st,
                      "task": task,
                      "error": task.get("error") or {},
                      "output_sensitive": task.get("output_sensitive"),
                      "input_sensitive": task.get("input_sensitive"),
                      "output_sensitive_type": task.get("output_sensitive_type"),
                      "input_sensitive_type": task.get("input_sensitive_type")}
            log.error("MiniMax 任务 %s 失败 完整返回=%s", task_id,
                      __import__("json").dumps(task, ensure_ascii=False,
                                               default=str)[:2000])
            raise MinimaxError(f"任务 {task_id} 状态 {st}: {task.get('error')}",
                               detail=detail)
    if not video_url:
        raise MinimaxError(f"任务 {task_id} 超时（{timeout:.0f}s）")

    with httpx.Client(timeout=600, follow_redirects=True) as c:
        v = c.get(video_url)
    if v.status_code != 200:
        raise MinimaxError(f"下载成片失败 HTTP {v.status_code}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(v.content)
    log.info("MiniMax 成片 %s (%.1fMB)", out.name, len(v.content) / 1024 / 1024)
    return out


def request_extra(spec: dict) -> dict:
    """按型号取「额外生成选项」—— 只转发参数表里写的东西，不认识字段含义。

    🩸 官方 create 页 `extra` 段：**只有 `MiniMax-H3-Max` 有**这个对象，
    其它三档没有该字段（`additionalProperties: false`，乱传会被拒）。
    所以"哪个型号有"由 `model_specs` 声明，这里不做型号判断。
    """
    ex = spec.get("request_extra") or {}
    return dict(ex) if isinstance(ex, dict) else {}


def generate_video(
    content: list[dict],
    *,
    out: Path,
    duration: int = 6,
    resolution: str = "",
    ratio: str = "adaptive",
    model: str = "",
    timeout: float = 1800,
    poll: float = 8.0,
) -> Path:
    """通用入口：content 自己拼，这里只负责建任务 → 轮询 → 下载。

    model 留空才回落到配置默认 —— 界面选了 H3 Max 就按 Max 的档位收口，
    别让 4 秒 / 2K 这种 Max 不支持的参数被硬塞过去。
    """
    from app.services import model_specs

    cfg = _cfg()
    model = (model or "").strip() or cfg.minimax_video_model
    # 官方四档各不一样（`h3-models`）：H3 4–15s/768P·2K；Highspeed 4–15s/768P；
    # Lite 4–15s/480P·768P 且**不收 adaptive**；Max 5–15s/480P·768P。
    # 一套写死会让某档收到它不收的 4s、2K 或 adaptive。
    spec = model_specs.minimax(model)
    dur = max(int(spec["min_sec"]), min(int(spec["max_sec"]), int(duration)))
    res = resolution or spec["default_resolution"]
    if res not in spec["resolutions"]:
        log.warning("%s 不支持 %s，退回 %s", model, res, spec["default_resolution"])
        res = spec["default_resolution"]
    # 🩸 2026-10-28：官方 create 页 ratio 段「`MiniMax-H3-Lite` 暂不支持 adaptive，
    #   需显式指定具体比例」。走到这里还是 adaptive = 调用方没算，直接拦
    #   （`reference_video` 已经会算；这条是给别的调用路径兜底，宁可不发也不发错）。
    ratio = ensure_ratio(spec, ratio)
    body = {
        "model": model,
        "content": content,
        "duration": dur,
        "resolution": res,
        "ratio": ratio,
    }
    # 型号自己声明了额外选项才带 `extra`（当前只有 H3-Max 有，见 `request_extra`）
    _ex = request_extra(spec)
    if _ex:
        body["extra"] = _ex
    # 进程被杀/重启后，先用上次落盘的任务号去取，别重新提交（重提交=重新花钱）
    old = _load_tid(out, body)
    if old:
        try:
            log.info("接着上次提交的 MiniMax 任务 %s 取结果（不重新提交）", old)
            return _poll_download(old, out, timeout=timeout, poll=poll)
        except MinimaxError as e:
            if not _is_dead(getattr(e, "detail", None)):
                raise
            log.warning("上次的 MiniMax 任务 %s 已失效，重新提交", old)

    from app.services import retry

    with httpx.Client(timeout=120) as c:
        r = retry.post(c, f"{_base()}/v2/video_generation",
                       headers=_headers(), json=body)
    if r.status_code == 429:
        raise MinimaxError("MiniMax 并发/频率超了（429）。多人同时出片时会这样，等一两分钟再跑这一条")
    if r.status_code != 200:
        raise MinimaxError(f"创建任务失败 HTTP {r.status_code}: {r.text[:300]}")
    j = r.json() or {}
    # 审核类拒绝会以 HTTP 200 + base_resp 非 0 返回（没有 task_id）：
    # 不先认这个，用户只会看到「没拿到 task_id」，根本不知道是素材被拦
    base = j.get("base_resp") or {}
    code = base.get("status_code")
    if code not in (0, None):
        smsg = str(base.get("status_msg") or "")
        hint = ""
        if code in (1026, 1027) or "sensitive" in smsg.lower() or "审核" in smsg:
            hint = (
                "｜这是内容审核拦的，不是参数错。换输入素材或改提示词；"
                "或把换画面方式改成「逐镜分诊」，静态镜只喂一帧。被拒的请求不扣费。"
            )
        raise MinimaxError(f"创建任务被拒（{code}）：{smsg}{hint}")
    task_id = (j.get("task") or {}).get("id") or j.get("task_id")
    if not task_id:
        raise MinimaxError(f"创建任务没拿到 task_id: {r.text[:200]}")

    t0 = time.time()
    _save_tid(out, task_id, body)
    return _poll_download(task_id, out, timeout=timeout, poll=poll)


MAX_REF_IMAGES = 9      # 官方「输入媒体限制」：首帧 ≤1、尾帧 ≤1、**参考图 ≤9**
MAX_REF_VIDEOS = 3      # 视频 ≤3 个；单段 [2,15]s、总 ≤15s
MAX_REF_AUDIOS = 3      # 音频 ≤3 个；单段 [2,15]s、总 ≤15s
MAX_AUDIO_BYTES = 15 * 1024 * 1024   # 音频单文件 ≤15 MB


def check_limits(*, n_images: int = 0, n_videos: int = 0, n_audios: int = 0,
                 audio_bytes: int = 0, image_bytes: int = 0,
                 video_bytes: int = 0) -> None:
    """发之前先数一遍素材 —— 官方硬上限，超了直接说清楚，别拿一次 400 换。

    出处：MiniMax 开放平台《创建视频生成任务》「输入媒体限制」
    （`https://platform.minimax.cn/docs/api-reference/video-generation-v2-create`）：
      图片 **参考图 ≤ 9**（另：首帧 ≤1、尾帧 ≤1，我们不单列这种角色）
      视频 ≤ 3 个，单段 [2,15]s，总 ≤15s，单文件 ≤50 MB
      音频 ≤ 3 个，单段 [2,15]s，总 ≤15s，**单文件 ≤ 15 MB**
    模型手册（`README.zh-CN.md:85`）与 API 文档在「≤9 / ≤3 / ≤3」上一致；
    「所有输入合计 ≤12 个文件」只在手册里出现、API 文档没有，**不按它卡**。

    🩸 为什么必须有这道：`model_specs.minimax()["max_ref_images"]` 从 2026-10-21
    起就写着 9，但**全工程没有任何消费者** —— 只是记在表里。实测最坏形状
    （4 人各换装 + 产品 + 场景 + 风格图）`ref_plan` 会出 **11 张**，照样提交。
    """
    if n_images > MAX_REF_IMAGES:
        raise MinimaxError(
            f"H3 一次最多 {MAX_REF_IMAGES} 张参考图，这次要发 {n_images} 张 —— "
            f"官方「输入媒体限制」硬上限，超了接口会直接拒。请减少换人/换装/素材数量。")
    if n_videos > MAX_REF_VIDEOS:
        raise MinimaxError(f"H3 一次最多 {MAX_REF_VIDEOS} 段参考视频，这次要发 {n_videos} 段")
    if n_audios > MAX_REF_AUDIOS:
        raise MinimaxError(f"H3 一次最多 {MAX_REF_AUDIOS} 段参考音频，这次要发 {n_audios} 段")
    if audio_bytes > MAX_AUDIO_BYTES:
        raise MinimaxError(
            f"参考音频 {audio_bytes / 1024 / 1024:.1f} MB 超过官方上限 15 MB")
    # 官方「输入媒体限制」：图片单文件 ≤30 MB、视频单文件 ≤50 MB（2026-10-28 复核）。
    # 传的是**最大那个文件**的大小，报错里带实际值 —— 只报"超了"没法定位是哪张。
    if image_bytes > MAX_IMAGE_BYTES:
        raise MinimaxError(
            f"参考图 {image_bytes / 1024 / 1024:.1f} MB 超过官方上限 30 MB")
    if video_bytes > MAX_VIDEO_BYTES:
        raise MinimaxError(
            f"参考视频 {video_bytes / 1024 / 1024:.1f} MB 超过官方上限 50 MB")


#: 官方 create 页 `ratio` 的枚举值（多模态参考场景可用）。
_RATIOS = (("21:9", 21 / 9), ("16:9", 16 / 9), ("4:3", 4 / 3),
           ("1:1", 1.0), ("3:4", 3 / 4), ("9:16", 9 / 16))


def ensure_ratio(spec: dict, ratio: str) -> str:
    """这一档收不收 `adaptive`；不收就必须是显式比例。

    官方 create 页 `ratio` 段：「多模态参考生视频…`MiniMax-H3-Lite` **暂不支持
    adaptive**，需显式指定具体比例」。纯函数，好判据（不联网、不花钱）。
    """
    if ratio == "adaptive" and not spec.get("ratio_adaptive", True):
        raise MinimaxError(
            f"{spec.get('label') or '这个型号'} 不支持 adaptive 比例："
            f"请显式指定 16:9 / 9:16 / 1:1 等具体比例")
    return ratio


def ratio_from_size(width: float, height: float) -> str:
    """宽高比 → 最接近的官方枚举值。取不到就返回空串（由调用方决定回退）。"""
    if not width or not height:
        return ""
    ar = float(width) / float(height)
    return min(_RATIOS, key=lambda kv: abs(kv[1] - ar))[0]


def ratio_for_video(path: Path) -> str:
    """素材实际宽高比 → 官方枚举值。

    🩸 2026-10-28：`MiniMax-H3-Lite` 官方「暂不支持 `adaptive`，需显式指定具体比例」
    （create 页 `ratio` 段）。我们参考类任务写死 adaptive ⇒ 这一档必然被拒。
    这里按素材比例算一个 —— 与 adaptive 本来会做的判断等价。
    读不到宽高时回落 16:9（横屏最常见），并留一条 warning，别静默。
    """
    try:
        from app.services import scene

        info = scene.probe(Path(path))
        w, h = float(info.get("width") or 0), float(info.get("height") or 0)
    except Exception as e:  # noqa: BLE001
        log.warning("读不到素材宽高（%s）", e)
        w = h = 0
    r = ratio_from_size(w, h)
    if not r:
        log.warning("素材宽高取不到，比例按 16:9 提交（Lite 不接受 adaptive，必须给一个）")
        r = "16:9"
    return r


def reference_video(
    video: Path,
    *,
    prompt: str,
    out: Path,
    subject_image: Path | None = None,
    ref_images: list[Path] | None = None,
    ref_audio: Path | None = None,
    ref_videos: list[Path] | None = None,
    duration: int = 6,
    resolution: str = "",
    model: str = "",
    timeout: float = 1800,
) -> Path:
    """参考视频换主体：原片出动作/运镜，参考图出身份/产品/场景。

    这是"换人保动作"的官方用法 —— 参考视频负责动作、构图、节奏，
    参考图负责长相和素材。

    🩸 指代写法**分两套，别互相清洗**（2026-10-28 复核）：
      · 我们发的是 **Ref2VA 六段式**（`h3_compile` 编译），标签语法由官方
        `ref-en:31` 规定：`<Picture N>` / `<Video N>` / `<Audio N>` /
        `<Subject N>`，且 `h3-skill:38` 要求**每个段落里写法保持一致**。
        `<d>` 更是词表里的特殊 token（`h3-readme:130`）。
      · API 页那几条单行示例写的是「人物参考视频1的动作…人物参考图1 图2」
        （`mm-docs` 全能参考段），那是**散句里顺手指代**，不是结构化提示词的
        标签语法。以前这里写成"不带 @、不带尖括号，那是别家的写法"——
        **那句话是错的**：`<Picture N>` 正是官方 Ref2VA 的写法。
    真要改这套标签，先改 `ref-en` 的依据，别在这里剥括号。
    **编号顺序 = content 数组里的顺序**，所以这里不排序、不去重。

    `ref_audio` = 这一段的口型要跟着走的那条音轨（官方「全能参考生成」的音频入口）。
    🩸 这是**口型对齐的唯一手段**：H3 不给音频就按自己的理解生成一套说话动作，
    场景模型从参考视频里也不去读那条被我们丢掉的音轨（官方 skill 2.5 节原文：
    "An ordinary reference video does not create <Audio N> merely because the file
    contains sound."）。官方输入条件：音频 ≤3 段、单段 [2,15]s、总 ≤15s、单个 ≤15MB。
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise MinimaxError("提示词不能为空")

    items0: list[Path] = list(ref_images or [])
    if subject_image is not None:
        items0.append(subject_image)
    def _max_size(paths) -> int:
        """这一组素材里最大的那个文件有多大（0 = 都取不到）。"""
        sizes = [Path(x).stat().st_size for x in paths if x and Path(x).exists()]
        return max(sizes) if sizes else 0

    check_limits(n_images=len(items0),
                 n_videos=1 + len(ref_videos or []),
                 n_audios=1 if ref_audio is not None else 0,
                 audio_bytes=(Path(ref_audio).stat().st_size
                              if ref_audio is not None and Path(ref_audio).exists()
                              else 0),
                 image_bytes=_max_size(items0),
                 video_bytes=_max_size([video, *(ref_videos or [])]))

    vid = upload_file(video)
    content: list[dict] = [{"type": "text", "text": prompt}]
    content.append({
        "type": "video_url",
        "video_url": {"url": f"mm_file://{vid}"},
        "role": "reference_video",
    })
    # 额外参考视频（风格参考 A9）：官方 ≤3 段、单段 [2,15]s、**总 ≤15s**、
    # 单文件 ≤50MB（`mm-docs:8273`）。总时长由 `video_edit.style_video_budget`
    # 在提交前算好，这里只管按顺序追加 —— 第 1 条永远是编辑母版。
    for extra in (ref_videos or []):
        ev = upload_file(extra)
        content.append({
            "type": "video_url",
            "video_url": {"url": f"mm_file://{ev}"},
            "role": "reference_video",
        })
    items: list[Path] = list(ref_images or [])
    if subject_image is not None:
        items.append(subject_image)
    for p in items:
        img = upload_file(p)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"mm_file://{img}"},
            "role": "reference_image",
        })
    # 音频放在最后：官方 skill 2.5 节点明「<Audio N> 与 <Video N> 各自独立编号」，
    # 所以它排在第几不影响画面素材的标号。
    if ref_audio is not None:
        au = upload_file(ref_audio)
        content.append({
            "type": "audio_url",
            "audio_url": {"url": f"mm_file://{au}"},
            "role": "reference_audio",
        })
        log.info("口型参考音频 %s (%.1fs)", Path(ref_audio).name,
                 min(MAX_CLIP_SECONDS, max(0.0, _audio_len(ref_audio))))
    # 🩸 Lite 不收 adaptive（官方 create 页 ratio 段）⇒ 这一档按素材比例显式给。
    from app.services import model_specs as _ms
    _spec = _ms.minimax(model or _cfg().minimax_video_model)
    _ratio = "adaptive" if _spec.get("ratio_adaptive", True) else ratio_for_video(video)
    return generate_video(
        content, out=out, duration=duration, resolution=resolution,
        ratio=_ratio, model=model, timeout=timeout,
    )
