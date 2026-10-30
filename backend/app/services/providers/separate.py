"""人声分离：把原片音轨拆成「人声」和「可以留下的背景」。

为什么复刻项目必须有这一步：换了配音之后，原片的人声对白必须去掉，
但 BGM / 环境音 / 音效要留下 —— 这两件事在一条混好的音轨里是分不开的。
整轨垫在新配音下面，原对白就会一直在（只是变小），听感是"两个人在说话"。

火山 AI MediaKit 的 `separate-voice` 按**内容类型**分场景，这就是"视频要分类型"的由来：

  scene       输出
  Audio(默认) 2 轨：voice_audio_url + background_audio_url
  Music       2 轨：同上
  Drama       3 轨：voice + music + sfx
  Narrate     3 轨：voice + music + sfx

我们固定走 `Drama`（三轨）—— 三轨是两轨的超集（music + sfx 合起来就是 background）。
**这个判断曾经错得很贵**：唱歌的片子用 Narrate 会把歌声整条当 music 返回、voice 轨静音，
详见下面 `SCENE` 的注释和 OPEN-DEFECTS D15。

接口契约（官方文档）：
  POST {endpoint}/api/v1/tools/separate-voice   {"video_url": "...", "scene": "Drama"}
  GET  {endpoint}/api/v1/tasks/{task_id}        status -> completed / failed
  鉴权 Authorization: Bearer <MEDIAKIT_API_KEY>
  🩸 输入只收**公网可访问的 HTTP/HTTPS URL**，本地文件要先 oss.upload。
  🩸 输出的 URL 只有 24 小时有效期，必须当场下载落盘。
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

import httpx

from app.services.media import ffmpeg_path

log = logging.getLogger(__name__)

_SUBMIT = "/api/v1/tools/separate-voice"
_DONE = ("completed", "success", "succeeded")
_FAIL = ("failed", "error", "cancelled", "canceled")


class SeparateError(RuntimeError):
    pass


def _cfg():
    from app.core.config import settings

    key = (settings.mediakit_api_key or "").strip()
    endpoint = (settings.mediakit_endpoint or "").strip().rstrip("/")
    return key, endpoint


def available() -> bool:
    key, endpoint = _cfg()
    return bool(key and endpoint)


# 固定用 Drama。2026-10-25 真机实测（OPEN-DEFECTS D15，4 次付费调用）：
#   · 真人说话：Drama 和 Music 拆出的 voice 逐段几乎相同（±0.4 dB）→ Drama 没问题；
#   · 唱歌：Narrate 的 voice 轨是空的（-51 dB），整条原轨落进 music —— 原唱拆不出来；
#           Music 才把原唱拆进 voice，但它是 2 轨制，没有独立 sfx。
# 原来按"ASR 覆盖率 ≥60% → Narrate"选场景是错的：歌也会被 ASR 转出歌词（实测 94%），
# 于是被判成口播，分离出来的 voice 空、原唱留在背景里，代码还察觉不到。
SCENE = "Drama"


def _headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _dig(payload, *paths):
    """从可能包了一层的响应里取字段（官方文档里提交和任务详情的形状不一样）。"""
    for path in paths:
        cur = payload
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        if cur not in (None, ""):
            return cur
    return None


def separate(video_url: str, *, scene: str = "Drama",
             timeout: float = 900.0) -> dict:
    """提交分离任务并等它完成，返回各轨的下载地址。

    返回形如 {"voice": url, "music": url, "sfx": url, "background": url, "duration": s}
    —— 具体有哪些键取决于 scene。
    """
    key, endpoint = _cfg()
    if not key:
        raise SeparateError("未配置 MEDIAKIT_API_KEY（火山 AI MediaKit 的 API Key）")
    if not video_url.lower().startswith(("http://", "https://")):
        raise SeparateError("MediaKit 只收公网 URL，本地文件请先上传")

    body = {"video_url": video_url, "scene": scene, "output_format": "wav"}
    with httpx.Client(timeout=120.0) as c:
        r = c.post(endpoint + _SUBMIT, headers=_headers(key), json=body)
        if r.status_code == 401:
            raise SeparateError("MEDIAKIT_API_KEY 无效（401）")
        if r.status_code >= 400:
            raise SeparateError(f"提交分离任务失败 {r.status_code}: {r.text[:300]}")
        payload = r.json()
    task_id = _dig(payload, ("task_id",), ("result", "task_id"), ("data", "task_id"))
    if not task_id:
        raise SeparateError(f"提交成功但没拿到 task_id: {str(payload)[:300]}")
    log.info("人声分离已提交：scene=%s task=%s", scene, task_id)

    deadline = time.time() + timeout
    delay = 2.0
    while True:
        if time.time() > deadline:
            raise SeparateError(f"分离任务超时（{timeout:.0f}s）：{task_id}")
        time.sleep(delay)
        delay = min(delay * 1.3, 5.0)
        with httpx.Client(timeout=60.0) as c:
            q = c.get(f"{endpoint}/api/v1/tasks/{task_id}", headers=_headers(key))
        if q.status_code >= 400:
            raise SeparateError(f"查询任务失败 {q.status_code}: {q.text[:300]}")
        detail = q.json()
        status = str(_dig(detail, ("status",), ("result", "status"), ("data", "status")) or "").lower()
        if status in _FAIL:
            raise SeparateError(f"分离任务失败：{status} {str(detail)[:300]}")
        if status in _DONE:
            break

    res = _dig(detail, ("result",), ("data",), ()) or {}
    if not isinstance(res, dict):
        raise SeparateError(f"任务完成但没有结果体: {str(detail)[:300]}")
    out = {
        "voice": res.get("voice_audio_url") or "",
        "music": res.get("music_audio_url") or "",
        "sfx": res.get("sfx_audio_url") or "",
        "background": res.get("background_audio_url") or "",
        "duration": res.get("duration") or 0.0,
        "scene": scene,
        "task_id": task_id,
    }
    if not (out["background"] or out["music"] or out["sfx"]):
        raise SeparateError(f"任务完成但没有可用音轨: {str(res)[:300]}")
    log.info("人声分离完成：%s", {k: bool(v) for k, v in out.items() if k in
                                  ("voice", "music", "sfx", "background")})
    return out


def download(url: str, dest: Path, *, timeout: float = 300.0) -> Path:
    """下载分离出来的音轨。官方链接 24 小时过期，必须当场落盘。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=timeout, follow_redirects=True) as c:
        with c.stream("GET", url) as r:
            if r.status_code >= 400:
                raise SeparateError(f"下载音轨失败 {r.status_code}: {url[:120]}")
            with dest.open("wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
    if not dest.exists() or dest.stat().st_size == 0:
        raise SeparateError("下载到的音轨是空的")
    return dest


def merge(paths: list[Path], dest: Path,
          gains: list[float] | None = None) -> Path:
    """把多条轨合成一条底音轨。

    🩸 用 `normalize=0`：amix 默认会把每条轨除以输入数，music + sfx 合起来
    就比原片背景小一半。这里要的是**还原**原片的背景，不是重新做一次混音。

    `gains` 与 `paths` 等长，缺省全 1.0（保持"还原"语义）；换 BGM 时新音乐
    要压到配音下面，由调用方给一个小于 1 的增益。
    """
    paths = [p for p in paths if p and p.exists()]
    if not paths:
        raise SeparateError("没有可合并的音轨")
    if len(paths) == 1:
        return paths[0]
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    gs = list(gains or [])
    if len(gs) < len(paths):
        gs += [1.0] * (len(paths) - len(gs))
    args = [ff, "-hide_banner", "-loglevel", "error", "-y"]
    for p in paths:
        args += ["-i", str(p.resolve())]
    chains = "".join(
        f"[{i}:a]volume={float(gs[i]):.4f}[g{i}];" for i in range(len(paths))
    )
    mixin = "".join(f"[g{i}]" for i in range(len(paths)))
    args += ["-filter_complex",
             f"{chains}{mixin}amix=inputs={len(paths)}:duration=longest:normalize=0[aout]",
             "-map", "[aout]", "-c:a", "pcm_s16le", str(dest.resolve())]
    p = subprocess.run(args, capture_output=True, text=True, errors="ignore", timeout=300)
    if p.returncode != 0 or not dest.exists():
        raise SeparateError(f"合并底音轨失败: {(p.stderr or '')[-400:]}")
    return dest


def fit_loop(src: Path, dest: Path, seconds: float) -> Path:
    """把一段音乐循环（不够长）或裁掉尾巴（太长），做成=成片时长的音轨。

    换 BGM 用的：用户传的歌和原片几乎不可能一样长，直接贴会半路没声或者
    把成片拖长。`-stream_loop -1` 必须写在 `-i` **前面**，否则只循环不生效。
    """
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    dur = max(0.1, float(seconds or 0.0))
    args = [ff, "-hide_banner", "-loglevel", "error", "-y",
            "-stream_loop", "-1", "-i", str(Path(src).resolve()),
            "-t", f"{dur:.3f}", "-c:a", "pcm_s16le", str(Path(dest).resolve())]
    p = subprocess.run(args, capture_output=True, text=True, errors="ignore", timeout=300)
    if p.returncode != 0 or not dest.exists():
        raise SeparateError(f"BGM 循环对齐失败: {(p.stderr or '')[-400:]}")
    return dest
