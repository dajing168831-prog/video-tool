"""商品短剧 · 出片质检的执行层：抽帧 → 视觉模型打分 → 交给 7 维合同。

**绝不自动跑**：只有主人在界面上点「评这段」才走这里（一次视觉调用，很小但计费）。
合同与判分在 `drama_quality.py`（纯函数，零调用），两件事分开：
  · 纯逻辑 = 可单测、可复算；
  · 这一层 = 会花钱、会碰 ffmpeg，坏了大不了重跑。

抽帧存成 `IMAGES_DIR/<pid>/qc<段号>-<i>.jpg`（**扁平文件名**，走现有图服务），
主人能直接看见模型到底看了哪几帧 —— 看不见的评分不可信。
"""
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from app.core.config import settings
from app.services import deepseek_chat, media

#: 一段抽几帧。5 秒的镜头 6 帧够看出闪烁/穿帮；再多对模型没增量。
FRAMES = 6
#: 抽帧宽高上限（短边），720p 输出不缩放；高清成片压下来省 token
MAX_SIDE = 720


def frames(video: Path, out_dir: Path, tag: str, *, n: int = FRAMES) -> list[Path]:
    """按时间**均匀**抽 n 帧（首尾各留半格，避开转场黑帧）。"""
    exe = media.ffmpeg_path()
    if not exe:
        raise RuntimeError("找不到 ffmpeg，无法抽帧")
    dur = media.probe_duration(video)
    if not dur or dur <= 0:
        raise RuntimeError("读不出这段视频的时长，无法抽帧")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        p = out_dir / f"{tag}-{i}.jpg"
        proc = subprocess.run(
            [exe, "-y", "-hide_banner", "-loglevel", "error",
             "-ss", f"{t:.3f}", "-i", str(video),
             "-frames:v", "1", "-vf", f"scale=-2:{MAX_SIDE}",
             str(p)],
            capture_output=True, text=True, errors="ignore", timeout=60,
        )
        if proc.returncode == 0 and p.exists() and p.stat().st_size > 0:
            paths.append(p)
    if not paths:
        raise RuntimeError("一帧都没抽出来（这段文件可能是坏的）")
    return paths


def _data_url(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def assess(video: Path, *, shot: dict, frames_dir: Path, tag: str,
           video_shot: bool = True, key_shot: bool = False,
           refs: list[tuple[str, Path]] | None = None) -> dict:
    """抽帧 + 调一次视觉模型，返回 `{"raw": ..., "frames": [文件名], "model": ...}`。

    `refs` = 评分时一并递过去的**参考图** `[(用途, 路径)]`（商品图、人物图…）。
    出处：clipforge `quality/route.ts:148-171` —— 不给参考图，
    「主体一致」只能靠模型猜商品/人物本来长什么样。

    模型说不出 JSON 就抛 `ValueError`（由调用方转成人话，**不静默给个假分**）。
    """
    from app.services import drama_quality  # 同层，避免循环 import 风险

    key = (settings.deepseek_api_key or "").strip()
    if not key:
        raise RuntimeError("没有配置 VT_DEEPSEEK_API_KEY，无法评分")
    paths = frames(video, frames_dir, tag)
    ref_items = [(label, p) for label, p in (refs or []) if p and p.exists()]
    prompt = drama_quality.build_prompt(
        shot, video=video_shot, key_shot=key_shot,
        n_frames=len(paths), refs=[label for label, _ in ref_items])
    content: list[dict] = [{"type": "text", "text": prompt}]
    content += [{"type": "image_url", "image_url": {"url": _data_url(p)}} for p in paths]
    content += [{"type": "image_url", "image_url": {"url": _data_url(p)}}
                for _, p in ref_items]
    body = {
        "model": settings.deepseek_model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
        "stream": False,
    }
    data = deepseek_chat.post(body, key=key)
    try:
        text = data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"评分模型返回结构不对：{str(data)[:200]}") from e
    raw = drama_quality.parse(text)
    return {
        "raw": raw,
        "frames": [p.name for p in paths],
        "refs": [label for label, _ in ref_items],
        "model": settings.deepseek_model,
    }
