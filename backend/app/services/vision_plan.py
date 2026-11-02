"""视觉盘点：先看一遍原片，再决定「换谁」。

为什么要有这一步
----------------
一句「把@视频1中的人物替换为@图片1中的人物」在**单人**画面里够用；
一旦同框有 5 个人，这句话没有唯一解 —— 模型会按自己的理解挑一个，
甚至把所有脸都换掉。用户传一张人物图时，模型并不知道他要换哪一个。

所以出片前先让视觉模型把原片看一遍，数清：画面里有几个人、各自长什么样、
**在第几秒到第几秒出现**。得到这份清单之后：

    火山   「只把@视频1中穿红裙的女生替换为@图片1中的人物」（有明确指代）
    H3     写进 subject_definitions / retention_analysis（官方要求绑定标号）
    分段   某一段里目标没出现 → 这一刀不下换人指令，甚至直接留原片

数据来源与限制（火山方舟 Chat API 视频理解，2026-10-21 核对）
------------------------------------------------------------
* Chat API 直接收 `video_url`，带 `fps`（默认 1，可调 0.2–5）；
  官方按 fps 抽帧，并在每帧前插入 `[<秒> second]` 时间戳文本 ——
  "谁在第几秒出现"是模型原生能回答的，不需要我们自己抽帧。
* 传入方式：base64（视频 <50MB、请求体 <64MB）/ 公网 URL / Files API。
  **我们用 base64**：原片里是真人脸，不该为了识别再传一份到公网存储。
* 结构化输出走 `response_format=json_schema`（方舟支持，字段强约束）。
* 单视频最多 80k tokens、抽帧数 16–1280；30 秒 @fps=1 约 30 帧，很便宜。

降级
----
没配 key、超时、返回不是合法 JSON → 抛 `VisionError`，由调用方退回
"只写一句替换人物"的老行为。**盘点失败绝不能让出片失败**。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.services import clone_store

CHAT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

# base64 走请求体，官方上限：视频 <50MB 且请求体 <64MB。留点余量。
MAX_INLINE_MB = 40.0

# 盘点只用来"认人"，画质不重要；超过这个大小先压一遍，避免传大文件
SHRINK_MAX_SIDE = 640


class VisionError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# 输出结构（json_schema 强约束，字段全 required）

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["duration_s", "people", "products", "scenes", "shots", "notes"],
    "properties": {
        "duration_s": {"type": "number", "description": "视频总时长（秒）"},
        "people": {
            "type": "array",
            "description": "画面里出现过的所有人（同一人跨镜头合并成一个）",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "desc_zh", "desc_en", "position", "appearances",
                             "main", "face_visible"],
                "properties": {
                    "id": {"type": "string", "description": "P1、P2… 按首次出现排序"},
                    "desc_zh": {"type": "string",
                                "description": "中文外观描述，只写看得见的，如「穿红裙的长发女生」"},
                    "desc_en": {"type": "string",
                                "description": "同一描述的英文，如 the long-haired woman in a red dress"},
                    # 🩸 多人物换人时，两家官方的消歧手段都是「方位 + 外观」：
                    #   · 火山 sd2-pe:72 把"多人未指明谁在左/右"列为病灶，
                    #     :153 给的写法是 `@图片2 中的女生位于画面左侧`；
                    #   · MiniMax ref-en:246「At the first clear appearance …
                    #     describe its referenced characteristics, **position in
                    #     the frame**, and current action」。
                    # 没有这个字段，多人换人只能写出一模一样的「把人物换成图N里的人」。
                    "position": {
                        "type": "string",
                        "enum": ["top-left", "top", "top-right",
                                 "left", "center", "right",
                                 "bottom-left", "bottom", "bottom-right",
                                 "unknown"],
                        "description": ("这个人**第一次清晰出现**时在画面里的位置，"
                                        "按九宫格填：左右并排用 left / center / right，"
                                        "**上下分屏用 top / bottom**，角落用 "
                                        "top-left / top-right / bottom-left / bottom-right；"
                                        "看不出来或一直在移动就填 unknown"),
                    },
                    "appearances": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["start", "end"],
                            "properties": {
                                "start": {"type": "number"},
                                "end": {"type": "number"},
                            },
                        },
                    },
                    "main": {"type": "boolean",
                             "description": "是否是主角（出现时长最长 / 占据画面最大）"},
                    "face_visible": {"type": "boolean",
                                     "description": "是否至少有一段时间正脸朝向镜头"},
                },
            },
        },
        "products": {
            "type": "array",
            "description": "画面里作为主体展示的产品/物品（不是背景摆设）",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["desc_zh", "desc_en"],
                "properties": {
                    "desc_zh": {"type": "string"},
                    "desc_en": {"type": "string"},
                },
            },
        },
        "scenes": {
            "type": "array",
            "description": "出现过的场景/环境",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["desc_zh", "desc_en"],
                "properties": {
                    "desc_zh": {"type": "string"},
                    "desc_en": {"type": "string"},
                },
            },
        },
        # 🩸 逐镜画面描述**跟盘点在同一次调用里出**（2026-10-23 主人纠正）：
        # 上传参考视频时本来就已经把整条片子送进 2.1 看了一遍，再单独发一次
        # 多图请求等于同一条片子看两遍、付两次钱。H3 的 `detailed_description`
        # 要的逐镜正文（官方 `ref-en:7`）就从这里取。
        "shots": {
            "type": "array",
            "description": ("按画面里**明显的硬切**把整条视频逐镜分段，从 0 秒开始、"
                            "依次相接、覆盖到最后，不要合并也不要跳过"),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["start", "end", "en"],
                "properties": {
                    "start": {"type": "number", "description": "这一镜的起点（秒）"},
                    "end": {"type": "number", "description": "这一镜的终点（秒）"},
                    "en": {"type": "string",
                           "description": ("这一镜的英文画面描述：景别与构图、主体是什么/"
                                           "外观/在画面里的位置、画面里正在发生的动作、"
                                           "环境与光线、这一镜的运镜（固定/推/拉/摇/移/"
                                           "跟拍），一句、以句号结尾、不超过 45 个词；"
                                           "只写看得见的，不写台词、不写剧情、不写画质评价")},
                },
            },
        },
        "notes": {"type": "string",
                  "description": "影响换人的客观情况，如「22 秒后主角转身背对镜头」；没有就填空字符串"},
    },
}

_SYSTEM = (
    "你是视频画面盘点助手。你只描述**画面里看得见**的东西，不推测身份、姓名、"
    "职业、关系或情节。要求：\n"
    "1) 同一个人在不同镜头里按外观（发型、服装、体型、配饰）合并成一条；"
    "拿不准是不是同一个人时，宁可分成两条，并在 notes 里说明。\n"
    "2) 时间单位是秒，保留一位小数，必须落在视频总时长之内。\n"
    "3) 一个片段里出现多个人就都列出来；完全没人的镜头不要编造人物。\n"
    "4) main 只有一个：出现时间最长、占据画面最大的那个。\n"
    "5) desc 只写外观，不写情绪和剧情；中文和英文描述必须指同一个人。\n"
    "6) position 写这个人**第一次清晰出现**时在画面里的位置，按九宫格："
    "left / center / right（左右并排）、top / bottom（**上下分屏**）、"
    "以及 top-left / top-right / bottom-left / bottom-right（角落）；"
    "同一镜头里有多个人时靠它区分谁在哪一块；看不出来就写 unknown。\n"
    "7) shots 按画面里明显的硬切把整条视频逐镜切开：从 0 秒开始、首尾相接、"
    "覆盖到视频结束；每镜写一句英文画面描述，必须写到：景别与构图、主体是什么/"
    "外观/在画面里的位置、画面里正在发生的动作、环境与光线、这一镜的运镜"
    "（固定/推/拉/摇/移/跟拍）。只写看得见的东西。"
)

_ASK = ("请盘点这条视频：列出所有出现过的人物（含各自出现的时间段）、"
        "作为主体展示的产品、场景，以及逐镜的画面描述。")


# ---------------------------------------------------------------------------
# 可用性 / 缓存


def available() -> bool:
    return bool((settings.ark_api_key or "").strip()) and bool(settings.vision_enabled)


def _cache_dir(cid: str) -> Path:
    d = clone_store.task_dir(cid) / "inventory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def video_sha1(video: Path) -> str:
    h = hashlib.sha1()
    with Path(video).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# 🩸 输出结构版本。schema 加字段就要 +1：旧缓存里没有新字段，命中它等于
# 「改了没生效」——用户点"重新识别"也拿不到方位，提示词还是原来那两句。
_SCHEMA_VER = 4   # v4：盘点顺带产出逐镜画面描述 `shots`


def _cache_key(sha: str, fps: float, model: str) -> str:
    return hashlib.sha1(
        f"v{_SCHEMA_VER}|{sha}|{fps:.2f}|{model}".encode()).hexdigest()[:16]


def cache_path_current(cid: str, video: Path | None = None, *,
                       fps: float | None = None, model: str = "") -> Path:
    """**当前 schema 版本**对应的盘点缓存路径（只算路径，不读不写不联网）。

    用途：判断"这份片子在新版盘点口径下看过没有"。老版本的缓存文件名里的
    版本号不同 —— 拿它当判据，就不会把"旧口径的盘点"误当成"新口径已经跑过"，
    也不会在每次出片时重复补一盘（补过就会留下这个文件）。
    """
    video = Path(video) if video else clone_store.source_path(cid)
    fps = float(fps if fps is not None else settings.vision_fps)
    model = (model or settings.vision_model).strip()
    return _cache_dir(cid) / f"{_cache_key(video_sha1(video), fps, model)}.json"


def _load_cache(cid: str, key: str) -> dict | None:
    p = _cache_dir(cid) / f"{key}.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _save_cache(cid: str, key: str, data: dict) -> None:
    """原子写：先落临时文件再 replace —— 半截 JSON 比没有更糟。"""
    p = _cache_dir(cid) / f"{key}.json"
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# 调用


def _shrink(video: Path) -> Path:
    """压一份小样给模型看：长边 640、去音轨。盘点只认人，不需要原画质。

    为什么压而不是直接传原片：原片动辄几十 MB，base64 后撑爆请求体；
    而传公网 URL 又等于把真人素材再公开一份，不做。
    """
    from app.services.media import ffmpeg_path

    ff = ffmpeg_path()
    if not ff:
        return video
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="inv_", dir=str(settings.temp_dir))) / "small.mp4"
    args = [ff, "-y", "-loglevel", "error", "-i", str(video),
            "-vf", f"scale='min({SHRINK_MAX_SIDE},iw)':-2",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
            str(out)]
    try:
        subprocess.run(args, check=True, capture_output=True, timeout=300)
    except Exception as e:  # noqa: BLE001
        raise VisionError(f"压缩盘点样本失败：{e}") from e
    return out


def _inline(video: Path) -> str:
    """本地视频 → data URI。超过阈值先压小样。"""
    size_mb = video.stat().st_size / 1024 / 1024
    src = video
    if size_mb > MAX_INLINE_MB:
        src = _shrink(video)
        size_mb = src.stat().st_size / 1024 / 1024
        if size_mb > MAX_INLINE_MB:
            raise VisionError(
                f"视频压缩后仍有 {size_mb:.0f}MB，超过接口上限 {MAX_INLINE_MB:.0f}MB")
    b64 = base64.b64encode(src.read_bytes()).decode()
    return f"data:video/mp4;base64,{b64}"


def _call(video: Path, *, model: str, fps: float, timeout: float = 240) -> dict:
    key = (settings.ark_api_key or "").strip()
    if not key:
        raise VisionError("方舟未配置：请设置 VT_ARK_API_KEY")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": [
                {"type": "video_url", "video_url": {"url": _inline(video), "fps": fps}},
                {"type": "text", "text": _ASK},
            ]},
        ],
        # 方舟支持 json_schema 强约束：字段名和类型由接口保证，不靠提示词祈求
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "video_inventory", "schema": _SCHEMA},
        },
        "temperature": 0.1,
    }
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(CHAT_URL, json=payload,
                       headers={"Authorization": f"Bearer {key}",
                                "Content-Type": "application/json"})
    except httpx.HTTPError as e:
        raise VisionError(f"盘点请求失败：{e}") from e
    if r.status_code >= 400:
        raise VisionError(f"盘点接口 {r.status_code}：{r.text[:300]}")
    try:
        text = r.json()["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        raise VisionError(f"盘点响应结构异常：{e}") from e
    return parse(text)


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


# 九宫格：左右并排用 left/center/right，**上下分屏用 top/bottom**（我们自己的片子
# 就有上下分屏对比视频，只写左右会两个人一起判成 center）。
_POSITIONS = ("top-left", "top", "top-right",
              "left", "center", "right",
              "bottom-left", "bottom", "bottom-right",
              "unknown")


def _norm_position(v: Any) -> str:
    """方位归一：只认官方那四种写法，别的一律 unknown（不猜左右）。"""
    s = str(v or "").strip().lower()
    return s if s in _POSITIONS else "unknown"


def parse(raw: str) -> dict:
    """模型返回 → dict。去 ``` 围栏、去前后废话，再校验必备字段。"""
    s = _FENCE.sub("", (raw or "").strip())
    if not s:
        raise VisionError("盘点返回为空")
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        # 兜底：从第一个 { 到最后一个 } 之间再试一次
        a, b = s.find("{"), s.rfind("}")
        if a < 0 or b <= a:
            raise VisionError(f"盘点返回不是 JSON：{s[:200]}")
        try:
            data = json.loads(s[a:b + 1])
        except json.JSONDecodeError as e:
            raise VisionError(f"盘点返回无法解析：{e}") from e
    return normalize(data)


def normalize(data: Any) -> dict:
    """把模型返回收拾成稳定形状。缺字段补默认值，越界的秒数夹回范围。"""
    if not isinstance(data, dict):
        raise VisionError("盘点结果不是对象")

    def _num(x, default=0.0) -> float:
        try:
            return float(x)
        except (TypeError, ValueError):
            return float(default)

    dur = max(0.0, _num(data.get("duration_s"), 0.0))

    people: list[dict] = []
    for i, p in enumerate(data.get("people") or [], 1):
        if not isinstance(p, dict):
            continue
        apps: list[dict] = []
        for a in p.get("appearances") or []:
            if not isinstance(a, dict):
                continue
            s, e = _num(a.get("start")), _num(a.get("end"))
            s = max(0.0, min(s, dur or s))
            e = max(s, min(e, dur or e))
            if e - s > 0.05:
                apps.append({"start": round(s, 2), "end": round(e, 2)})
        if not apps:
            continue
        desc_zh = str(p.get("desc_zh") or "").strip()
        desc_en = str(p.get("desc_en") or "").strip()
        if not desc_zh and not desc_en:
            continue
        pid = str(p.get("id") or "").strip() or f"P{i}"
        people.append({
            "id": pid,
            "desc_zh": desc_zh or desc_en,
            "desc_en": desc_en or desc_zh,
            # 老盘点没有这个字段 → unknown，编译器退回原来的写法（不写方位）
            "position": _norm_position(p.get("position")),
            "appearances": apps,
            "main": bool(p.get("main")),
            "face_visible": bool(p.get("face_visible")),
        })

    # 🩸 官方《Seedance 2.5 指南》`:429-435`「角色对应错误」：
    # 「按人物**首次出场顺序**上传参考素材，并同步调整提示词中的图片、音频编号，
    # 确保每个角色与参考素材一一对应。」现象是「先出场的人物被其他参考角色替换」。
    # schema 里写了「P1、P2… 按首次出现排序」，但那是给模型的**提示**、不是保证
    # （文本约束 ≠ 效果）。这里机械按最早一次出现的 start 重排并重编 id：
    #   · `people[i]` 就是第 i 个人物槽位（`video_edit._person_ids_in_slots` 按这个对齐），
    #     数组顺序直接变成 @图片N 的编号顺序；
    #   · `desc_by_id` 按 id 建表，重编 id 后它自然跟着走。
    # 重排要在 main 判定之前/之后都行（main 是布尔字段，不看 id）。
    people.sort(key=lambda p: min((a["start"] for a in p["appearances"]),
                                  default=0.0))
    for _i, _p in enumerate(people, 1):
        _p["id"] = f"P{_i}"

    # main 必须唯一且存在：模型没标就按出现总时长挑最长的那条
    if people and not any(p["main"] for p in people):
        def total(p):
            return sum(a["end"] - a["start"] for a in p["appearances"])
        max(people, key=total)["main"] = True
    elif sum(1 for p in people if p["main"]) > 1:
        def total2(p):
            return sum(a["end"] - a["start"] for a in p["appearances"])
        keep = max((p for p in people if p["main"]), key=total2)
        for p in people:
            p["main"] = p is keep

    # 逐镜画面描述：秒数夹回视频范围，没描述或时长无效的镜直接丢。
    shots: list[dict] = []
    for x in data.get("shots") or []:
        if not isinstance(x, dict):
            continue
        en = str(x.get("en") or "").strip()
        if not en:
            continue
        s = max(0.0, _num(x.get("start")))
        e = _num(x.get("end"))
        if dur:
            e = min(e, dur)
        if e - s <= 0.05:
            continue
        shots.append({"start": round(s, 2), "end": round(e, 2), "en": en})
    shots.sort(key=lambda z: z["start"])

    def _items(key: str) -> list[dict]:
        out = []
        for x in data.get(key) or []:
            if not isinstance(x, dict):
                continue
            zh = str(x.get("desc_zh") or "").strip()
            en = str(x.get("desc_en") or "").strip()
            if zh or en:
                out.append({"desc_zh": zh or en, "desc_en": en or zh})
        return out

    return {
        "duration_s": round(dur, 2),
        "people": people,
        "products": _items("products"),
        "scenes": _items("scenes"),
        "shots": shots,
        "notes": str(data.get("notes") or "").strip(),
    }


def inventory(cid: str, video: Path | None = None, *, fps: float | None = None,
              model: str = "", refresh: bool = False) -> dict:
    """盘点一条片子。命中缓存直接返回，不重复花钱。

    返回的 dict 比模型原始返回多一个 `_meta`：model / fps / cached / video_sha1，
    前端要拿它显示"用哪个型号看的、是不是缓存"。
    """
    if not available():
        raise VisionError("视觉盘点未启用：需要 VT_ARK_API_KEY，且 VT_VISION_ENABLED 不为 0")

    video = Path(video) if video else clone_store.source_path(cid)
    if not video.exists():
        raise VisionError(f"找不到原片：{video}")

    fps = float(fps if fps is not None else settings.vision_fps)
    model = (model or settings.vision_model).strip()
    sha = video_sha1(video)
    key = _cache_key(sha, fps, model)

    if not refresh:
        hit = _load_cache(cid, key)
        if hit:
            hit.setdefault("_meta", {})
            hit["_meta"].update({"cached": True, "model": model, "fps": fps,
                                 "video_sha1": sha})
            return hit

    t0 = time.time()
    try:
        data = _call(video, model=model, fps=fps)
        used = model
    except VisionError as e:
        alt = (settings.vision_model_fallback or "").strip()
        if not alt or alt == model:
            raise
        log_msg = f"{model} 盘点失败，改用 {alt} 重试：{e}"
        import logging
        logging.getLogger(__name__).warning(log_msg)
        data = _call(video, model=alt, fps=fps)
        used = alt

    data["_meta"] = {
        "model": used,
        "fps": fps,
        "cached": False,
        "video_sha1": sha,
        "elapsed": round(time.time() - t0, 2),
    }
    _save_cache(cid, key, data)
    return data


# ---------------------------------------------------------------------------
# 给渲染侧用


def cached_only(cid: str) -> dict | None:
    """读缓存里的盘点结果，**绝不调模型、不花钱**。

    🩸 2026-10-27：任务详情接口每次打开页面都会调，它要用盘点去算"每句台词是
    谁说的"。如果那里走 `inventory()`，**没缓存时会当场花一次钱** ——
    打开一次详情页扣一次费，不行。所以这里只扫缓存目录。

    取 `inventory/` 下 **mtime 最新**的一份（用户点"重新识别"会写出新文件）。
    没有缓存 / 文件坏了 → 返回 None，调用方退回"分不出说话人"。

    🩸 这里**不走 `_cache_dir()`**：那个函数会 `mkdir`。一个"只读"函数如果在
    详情接口里被调用，id 一旦拼错就会在 `data/clone/` 下留下一个空任务目录
    （2026-10-27 实测踩到：传 8 位前缀建出了 `data/clone/494b1c28/`）。
    """
    d = clone_store.task_dir(cid) / "inventory"
    if not d.is_dir():
        return None
    for p in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict) and isinstance(data.get("people"), list):
            return data
    return None


def people_in(inv: dict | None, a: float, b: float, *, min_overlap: float = 0.15) -> list[dict]:
    """这一段时间里真正出现过的人（按重叠时长降序）。"""
    if not inv:
        return []
    out: list[tuple[float, dict]] = []
    for p in inv.get("people") or []:
        ov = 0.0
        for app in p.get("appearances") or []:
            ov += max(0.0, min(b, app["end"]) - max(a, app["start"]))
        if ov >= min_overlap:
            out.append((ov, p))
    out.sort(key=lambda x: (-x[0], not x[1].get("main")))
    return [p for _, p in out]


def target_in(inv: dict | None, a: float, b: float,
              person_id: str = "") -> dict | None:
    """这一段要不要换人：要换就返回被换的那个人，这一段没有就返回 None。

    person_id 是用户在盘点上点的那个人；不指定时 main 优先（默认主角），
    再退到这一段出现最久的人。
    """
    ps = people_in(inv, a, b)
    if not ps:
        return None
    pid = (person_id or "").strip()
    if pid:
        for p in ps:
            if p.get("id") == pid:
                return p
        return None
    for p in ps:
        if p.get("main"):
            return p
    return ps[0]


def targets_in(inv: dict | None, a: float, b: float,
               person_ids: list[str] | None = None) -> list[dict]:
    """这一段里出现了**哪几个**被选中的人（按传进来的顺序，只返回出现的那些）。

    多人换人靠它做逐段分诊：一段里出现两个人就换两个，出现一个就换一个，
    都没出现才留原片。不传 `person_ids`（或传空）= 老的单人语义：自动取主角。
    """
    want = [str(x).strip() for x in (person_ids or []) if str(x).strip()]
    if not want:
        p = target_in(inv, a, b)
        return [p] if p else []
    ps = people_in(inv, a, b)
    out = []
    for pid in want:
        for p in ps:
            if p.get("id") == pid:
                out.append(p)
                break
    return out


def summary(inv: dict | None) -> dict:
    """给前端画 chips 用的精简版（不带 desc_en 之外的大字段）。"""
    if not inv:
        return {"ready": False, "people": [], "products": [], "scenes": []}
    return {
        "ready": True,
        "duration_s": inv.get("duration_s", 0),
        "people": [{
            "id": p["id"],
            "desc_zh": p["desc_zh"],
            "desc_en": p["desc_en"],
            "main": bool(p.get("main")),
            "face_visible": bool(p.get("face_visible")),
            "appearances": p.get("appearances") or [],
        } for p in inv.get("people") or []],
        "products": inv.get("products") or [],
        "scenes": inv.get("scenes") or [],
        "notes": inv.get("notes") or "",
        "_meta": inv.get("_meta") or {},
    }


# ---------------------------------------------------------------------------
# 参考图里那个人长什么样 —— 官方要求主体定义要写具体特征
#
# 出处（两家都明写，本地原文）：
#   · MiniMax H3 ref-en `:37`（**正文**）：`subject_definitions` 要解释
#       "what its label denotes, its reference role, and **the main features
#       to follow**"；`:48-51` 的示例：
#       `<Subject 1> is the young woman in <Picture 1>, with long dark hair,
#        a blue cardigan, and a thin silver necklace.`
# 🩸 **只有 H3 用这份描述**：火山 2.0 / 2.5 的编辑示例 `<新特征>` 位只写图号
#   （2.0 `sd2-pe:126`「替换为 @图片1 中的面霜」；2.5 `sd25-guide:88`「修改为 @image1」），
#   指南 §1「定义主体」讲的是**生成任务**的 `<主体N>` 体系，不搬进编辑任务。

_DESC_SYSTEM = (
    "你是影视造型描述员。只看人物参考图，用最稳定的静态外观特征描述这个人，"
    "供视频模型在多镜头里认出并保持一致。"
)

#: 🩸 2026-11-01 改（主人：「你干什么老是跑去别的模型查资料」）。
#: 旧版写的是「2–3 个即可，宁少勿多」—— 那是 **Seedance 2.0** 的规范
#: （`sd20/skills/sd2-pe/references/guide.md:95`「使用 2–3 个清晰、稳定的静态特征…
#: 确保唯一可识别性」），H3 官方全库没有这一条。拿它喂 H3 的后果实测到了：
#: 视觉模型挑走最醒目的发髻和长裙，**把脸挤掉**（`subject_desc.json` 里没有一个字
#: 是五官）→ agent 无从写脸 → `retention_analysis` 只列发型服装 → 成片保留原脸，
#: bestSim 0.177。
#:
#: H3 的口径是 `ref-en.txt:37`「explain what its label denotes, its reference role,
#: and **the main features to follow**」——「要跟随的主要特征」，没有数量上限。
#: 对**人物参考图**，MiniMax 官方 H3 视频提示词模板把主特征写死为身份锚点：
#:   · `h3-video-prompt-template.md:20` `PLAYER 1 identity anchor. Lock exact face,
#:     hairstyle, glasses if present, **facial proportions**, body identity`
#:   · 同文件 `:42`（中文）「五官信息参考…**必须保留脸、人脸比例**、发型、眼镜（如有）、个人身份」
#:   · `co-op-game-intro-generator/SKILL.md:24` `only for identity mapping:
#:     recognizable **face silhouette**, hairstyle, glasses, **relative facial
#:     proportions**, and distinctive traits`
#:   · `music-video-subtitle-generator/SKILL.md:114` `character reference card:
#:     controls character identity, **facial aura**, hairstyle, clothing silhouette…`
#: 所以「脸」在这份清单里是**必填项**，不是可选。
_DESC_ASK = (
    "看这张人物参考图，写出**这个人要跟随的特征**，供视频模型在换人时认出并保持是同一个人。\n"
    "H3 官方把这种图的职责写死成一张清单（`music-video-subtitle-generator/SKILL.md:114`）："
    "「Character reference card: controls character **identity, facial aura, hairstyle, "
    "clothing silhouette, proportions, posture, and presence**」。逐项写：\n"
    "1. **identity / 面部（必写，任何情况下不能省）**：脸型轮廓 + 最显著的 1–2 个五官"
    "特征（眉眼/鼻/嘴的形状）；戴眼镜就写眼镜。官方换人模板把它写死成 "
    "「Lock exact face, hairstyle, glasses if present, facial proportions, body identity」"
    "（`h3-video-prompt-template.md:20`，中文版 `:42`「必须保留脸、人脸比例」）。\n"
    "2. **facial aura（面部气质，必写）**：这张脸给人的整体感觉，一个词就够 —— "
    "清冷 / 凌厉 / 温婉 / 英气 / 甜 / 憨。只写看得出来的，不要写「气质好」「漂亮」"
    "这种评价词。\n"
    "3. **hairstyle**：发型发色。\n"
    "4. **clothing silhouette（服装轮廓）**：写版型和轮廓（古风长裙 / 短外套 / 宽松 / "
    "贴身 / 高领），**不要**逐个写花纹、纽扣、刺绣、褶皱这些细节。\n"
    "5. **proportions（身体比例）与体型类别**：高矮胖瘦这一级就够 —— 官方 `:20` 要的是 "
    "body identity。**不要**写任何具体部位。\n"
    "6. **不要写**：背景、场景、光线、画风、画质、写实度、镜头、表情、动作、姿态、"
    "年龄评价。这张图**只负责角色**，场景和光照由原片负责 —— 官方 `:111`"
    "「Assign each reference image **one narrow job**」，`:24`"
    "「**Do not inherit** photographic realism, skin texture, real-world lighting, "
    "camera quality, or the original image style」。（姿态在复刻里一律跟随原片视频，"
    "所以这里不写。）\n"
    "7. 不设数量上限 —— 面部是必选项，其余按醒目程度写。\n"
    "8. desc_zh 用中文名词短语，desc_en 用英文名词短语；两个字段描述的是同一组特征。\n"
    "9. 另外单独给一个 gender 字段：male / female / unspecified。\n"
    "   看**这张图里的人本身**，不要按服装或场景推断；看不清就填 unspecified，"
    "**绝对不要猜**。"
)

#: 🩸 2026-11-01 加 `gender`：H3 官方 `base-en:129` 把**性别**列为说话人/主体身份
#: 的必要信息之一（"character type, age, gender, whether the person is on-screen…"）。
#: 以前这份描述只有发型/五官/衣服，于是 agent 写主体定义时只能沿用**原片那个人**的
#: 性别 —— 实测：上传的男性照片被写成 "female warrior"。
_DESC_SCHEMA = {
    "type": "object",
    "properties": {
        "desc_zh": {"type": "string"},
        "desc_en": {"type": "string"},
        "gender": {"type": "string", "enum": ["male", "female", "unspecified"]},
    },
    "required": ["desc_zh", "desc_en", "gender"],
}

#: 描述的版本号。改了提问/字段就加一 —— 老缓存会被当成过期重算
#: （不加的话，用户重传同一张图仍拿回没有 gender 的旧描述）。
#: v3（2026-11-01）：加了「面部必写」，旧的一批描述都把脸漏了，必须重算。
#: v4（2026-11-01）：按 H3 官方 character reference card 的六项重排（`music-video
#:   SKILL.md:114`：identity / facial aura / hairstyle / clothing silhouette /
#:   proportions / posture），并明确**不写**原图的背景/光照/画风（`:24`）。
#:   v3 只补了脸，缺 facial aura 和「不继承原图」两条。
_DESC_VERSION = 4


def _image_inline(image: Path) -> str:
    """本地图片 → data URI（参考图通常几 MB，直接内联）。"""
    suffix = image.suffix.lower().lstrip(".") or "jpeg"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(
        suffix, "jpeg")
    b64 = base64.b64encode(image.read_bytes()).decode()
    return f"data:image/{mime};base64,{b64}"


def describe_person(cid: str, image: Path, slot: str = "person") -> dict:
    """看一张人物参考图 → `{"desc_zh": …, "desc_en": …}`。

    `slot` 决定缓存落在哪个文件：`person` = 第一个人，`person2` = 第二个人……
    （`clone_store.subject_desc_path(cid, slot)`）。每个槽位**各存各的** ——
    混用一个文件会让第 2 个人拿到第 1 个人的描述。

    🩸 失败一律返回 `{}`，绝不抛：这只是给提示词加一句特征，
    **不能因为视觉调用失败就让用户传不了图、出不了片**。
    缓存按图片内容哈希，重传同一张图不会重复花钱。
    """
    empty: dict = {}
    try:
        p = Path(image)
        if not p.exists() or not available():
            return empty
        sha = hashlib.sha1(p.read_bytes()).hexdigest()
        cache = clone_store.subject_desc_path(cid, slot)
        if cache.exists():
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                # 换了参考图就必须重算：sha 对不上说明图不是同一张
                # 描述版本变了也要重算（老版本没有 gender 字段）
                if (data.get("desc_en") and data.get("_image_sha1") == sha
                        and data.get("_v") == _DESC_VERSION):
                    return data
            except Exception:  # noqa: BLE001
                pass

        key = (settings.ark_api_key or "").strip()
        if not key:
            return empty
        payload = {
            "model": settings.vision_model,
            "messages": [
                {"role": "system", "content": _DESC_SYSTEM},
                {"role": "user", "content": [
                    {"type": "image_url",
                     "image_url": {"url": _image_inline(p)}},
                    {"type": "text", "text": _DESC_ASK},
                ]},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "person_look", "schema": _DESC_SCHEMA},
            },
            "temperature": 0.1,
        }
        with httpx.Client(timeout=120) as c:
            r = c.post(CHAT_URL, json=payload,
                       headers={"Authorization": f"Bearer {key}",
                                "Content-Type": "application/json"})
        if r.status_code >= 400:
            raise VisionError(f"外貌描述接口 {r.status_code}：{r.text[:200]}")
        text = r.json()["choices"][0]["message"]["content"]
        s = _FENCE.sub("", (text or "").strip())
        a, b = s.find("{"), s.rfind("}")
        if a < 0 or b <= a:
            raise VisionError(f"外貌描述不是 JSON：{s[:120]}")
        data = json.loads(s[a:b + 1])
        zh = str(data.get("desc_zh") or "").strip().rstrip("。.")
        en = str(data.get("desc_en") or "").strip().rstrip(".")
        if not zh or not en:
            return empty
        gender = str(data.get("gender") or "").strip().lower()
        if gender not in ("male", "female", "unspecified"):
            # 模型没按枚举给 → 按"看不出"算，绝不替它猜一个
            gender = "unspecified"
        out = {"desc_zh": zh, "desc_en": en, "gender": gender,
               "_image_sha1": sha, "_model": settings.vision_model,
               "_v": _DESC_VERSION}
        cache.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        return out
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("人物参考图外貌描述失败（不影响后续）：%s", e)
        return empty


# ---------------------------------------------------------------------------
# 逐镜画面描述 —— 只给 H3 的 `detailed_description` 用
#
# 出处（官方两份都明写）：
#   · `ref-en:7`：「Make `detailed_description` **as detailed and explicit as
#     possible**. For each shot, clearly establish the current composition,
#     subject appearance and position, environment and lighting, actions and
#     state changes, camera movement, current sound, and the points where
#     referenced content actually appears or takes effect. **Avoid reducing the
#     description to a plot summary or a list of reference relationships.**」
#   · 官方 README 的 Ref2VA 完整案例：`[Shot 1]` 里把人物外观、服装、姿态、
#     环境、光线、背景、动作、结束状态全写了出来。
# 🩸 我们以前的 `detailed_description` 只有「follows it shot by shot, adding,
#    removing and reordering nothing」这种关系句，正是官方点名不许的写法。
# 🩸 只做**画面里客观看得见**的东西（景别/主体/动作/环境/光线）。不写台词、
#    不写「保持不变」，那是 retention_analysis 的活。


# ---------------------------------------------------------------------------
# 逐镜画面描述：**从盘点结果里取**，不再单独调一次视觉模型
#
# 🩸 2026-10-23 主人纠正：上传参考视频解析时，整条片子已经送进 2.1 看过一遍
# （`_call` → `video_inventory`），逐镜画面描述就该在那一次的返回里一起给出。
# 早先这里自己又发了一轮多图请求 —— 同一条片子看两遍、付两次钱。


def latest(cid: str) -> dict | None:
    """最近一次盘点结果（不看 key，取目录里最新的、且带 `shots` 的那份）。"""
    d = _cache_dir(cid)
    best: dict | None = None
    best_t = -1.0
    for p in d.glob("*.json"):
        try:
            t = p.stat().st_mtime
            if t <= best_t:
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict) and data.get("shots"):
            best, best_t = data, t
    return best


def describe_shots(cid: str, spans: list) -> list[str]:
    """给每个时间段取一句画面描述 → 长度 = len(spans)。

    `spans` 是渲染侧真正的镜头区间 `[(start, end), …]`；跟盘点自己切出来的
    镜不一定一一对应，所以按**时间重叠最多**的那条匹配，而不是按序号硬对。
    取不到就返回空串 —— 调用方退回关系句写法，绝不让用户出不了片。
    """
    if not spans:
        return []
    try:
        inv = latest(cid) or {}
        ref = [s for s in (inv.get("shots") or [])
               if isinstance(s, dict) and str(s.get("en") or "").strip()]
        if not ref:
            return [""] * len(spans)
        out: list[str] = []
        for a, b in spans:
            a, b = float(a), float(b)
            best_en, best_ov = "", 0.0
            for s in ref:
                ov = min(b, float(s["end"])) - max(a, float(s["start"]))
                if ov > best_ov:
                    best_ov, best_en = ov, str(s["en"]).strip()
            out.append(best_en)
        return out
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("逐镜画面描述不可用（退回关系句）：%s", e)
        return [""] * len(spans)
