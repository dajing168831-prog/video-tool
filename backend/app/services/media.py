"""媒体处理：下载 / 探测 / 抽音频。

本机只有 ffmpeg（剪映自带），没有 ffprobe —— 所以时长从 ffmpeg -i 的 stderr 里解析。
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from pathlib import Path

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

_KNOWN_FFMPEG = [
    # winget 装的完整版（含 libass/libx264，字幕合成必须用这个）
    r"C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages",
    r"C:\Users\Administrator\Desktop\Jianying6.01\6.0.1.11779\ffmpeg.exe",
]
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _winget_ffmpeg() -> str | None:
    """winget 的包目录带哈希，版本会变 —— 用 glob 找，不写死路径。"""
    base = Path(_KNOWN_FFMPEG[0])
    if not base.exists():
        return None
    hits = sorted(base.glob("Gyan.FFmpeg*/ffmpeg*/bin/ffmpeg.exe"))
    return str(hits[-1]) if hits else None


def ffmpeg_path() -> str | None:
    if settings.ffmpeg and Path(settings.ffmpeg).exists():
        return settings.ffmpeg
    found = shutil.which("ffmpeg")
    if found:
        return found
    winget = _winget_ffmpeg()
    if winget:
        return winget
    for p in _KNOWN_FFMPEG[1:]:
        if Path(p).exists():
            return p
    return None


def ffprobe_path() -> str | None:
    """ffprobe 与 ffmpeg 同目录（完整版才有）。剪映的没有 ffprobe。"""
    exe = ffmpeg_path()
    if not exe:
        return None
    p = Path(exe).with_name("ffprobe.exe")
    return str(p) if p.exists() else (shutil.which("ffprobe") or None)


# CDN 防盗链：不同平台要求不同 Referer，写错就是 403
_REFERER_BY_HOST = [
    ("xhscdn.com", "https://www.xiaohongshu.com/"),
    ("xiaohongshu.com", "https://www.xiaohongshu.com/"),
    ("douyin", "https://www.douyin.com/"),
    ("douyinvod.com", "https://www.douyin.com/"),
    ("zjcdn.com", "https://www.douyin.com/"),
    ("kuaishou", "https://www.kuaishou.com/"),
    ("kwimgs.com", "https://www.kuaishou.com/"),
    ("kwaicdn.com", "https://www.kuaishou.com/"),
    ("yximgs.com", "https://www.kuaishou.com/"),
    ("hdslb.com", "https://www.bilibili.com/"),
    ("bilivideo.com", "https://www.bilibili.com/"),
    ("bilibili.com", "https://www.bilibili.com/"),
    ("tiktok", "https://www.tiktok.com/"),
    ("cdninstagram.com", "https://www.instagram.com/"),
    ("fbcdn.net", "https://www.instagram.com/"),
    ("twimg.com", "https://x.com/"),
    ("ytimg.com", "https://www.youtube.com/"),
    ("googlevideo.com", "https://www.youtube.com/"),
]


def _referer_for(url: str) -> str | None:
    """按域名给 Referer。匹配不到就不带 —— 带错 Referer 比不带更容易 403。"""
    for key, ref in _REFERER_BY_HOST:
        if key in url:
            return ref
    return None


async def download(url: str, dest: Path, *, max_bytes: int | None = None) -> int:
    """流式下载到 dest，返回字节数。超过上限立即中止。"""
    limit = max_bytes or settings.max_video_bytes
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
        ),
    }
    ref = _referer_for(url)
    if ref:
        headers["Referer"] = ref
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=settings.http_timeout
    ) as client:
        async with client.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(1024 * 256):
                    total += len(chunk)
                    if total > limit:
                        raise RuntimeError(f"文件超过上限 {limit / 1024 / 1024:.0f}MB")
                    f.write(chunk)
    return total


async def ytdlp_download(url: str, dest: Path, *, max_height: int = 1080,
                         proxy: str = "") -> int:
    """用 yt-dlp 下载（能处理分轨音视频合并、平台签名）。

    Instagram / Twitter / YouTube 走这里；直链会过期或需要特定请求头，
    交给 yt-dlp 比我们自己拼请求头稳。
    """
    import sys

    exe = ffmpeg_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fmt = (
        f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]"
        f"/b[height<={max_height}]/b"
    )
    cmd = [
        sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-playlist",
        "-f", fmt, "--merge-output-format", "mp4",
        "-o", str(dest), url,
    ]
    if proxy:
        cmd += ["--proxy", proxy]
    if exe:
        cmd += ["--ffmpeg-location", str(Path(exe).parent)]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=1800)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("下载超时（超过 30 分钟）") from None
    if proc.returncode != 0 or not dest.exists():
        msg = (err or b"").decode("utf-8", "ignore").strip().splitlines()
        raise RuntimeError((msg[-1] if msg else "yt-dlp 下载失败")[:300])
    size = dest.stat().st_size
    if size > settings.max_video_bytes:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"文件超过上限 {settings.max_video_bytes / 1024 / 1024:.0f}MB")
    return size


def probe_duration(path: Path) -> float | None:
    """用 ffmpeg -i 解析时长（秒）。"""
    exe = ffmpeg_path()
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-hide_banner", "-i", str(path)],
            capture_output=True, text=True, errors="ignore", timeout=30,
        )
        m = _DURATION_RE.search(proc.stderr or "")
        if not m:
            return None
        h, mnt, sec = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return h * 3600 + mnt * 60 + sec
    except Exception as e:  # noqa: BLE001
        log.warning("probe_duration 失败: %s", e)
        return None


#: 模型侧能直接解码的图片采样格式。
#: 官方 `sd25-guide:679`：标准 JPEG 只有 4:2:0 / 4:2:2 / 4:4:4；非常规、非对称的
#: 色度采样（Y 分量 2x2、Cb 1x1、Cr 2x1）超出解码范围，模型侧报
#: `invalid image: heic: decode failed`。**ffprobe 却读得出宽高** ——
#: 于是我们放行，用户等到出片才炸（钱和时间都白花）。
JPEG_SAFE_PIX_FMTS = frozenset({
    "yuvj420p", "yuvj422p", "yuvj444p",     # JPEG 全范围（yuvj* 专供 JPEG）
    "yuv420p", "yuv422p", "yuv444p",
    "rgb24", "bgr24", "gray", "ya8", "rgba", "bgra", "pal8",
})


def jpeg_needs_normalize(pix_fmt: str) -> bool:
    """空串不判（探测不出格式的本来就该在上一步被拒）。"""
    return bool(pix_fmt) and pix_fmt not in JPEG_SAFE_PIX_FMTS


def normalize_jpeg(src: Path, dest: Path) -> bool:
    """把采样格式不标准的图转成标准 JPEG（yuvj420p）。返回是否成功。

    `-q:v 2` 是 mjpeg 的高质量档（1 最好、31 最差），避免重编码把参考图压糊
    —— 这张图要拿去锁脸的。只在**格式不标准**时才走这条路，正常图不动。
    """
    exe = ffmpeg_path()
    if not exe:
        return False
    try:
        proc = subprocess.run(
            [exe, "-y", "-v", "error", "-i", str(src),
             "-pix_fmt", "yuvj420p", "-q:v", "2", str(dest)],
            capture_output=True, text=True, errors="ignore", timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("图片转码失败 %s: %s", src.name, e)
        return False
    if proc.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        log.warning("图片转码失败 %s: %s", src.name, (proc.stderr or "")[:200])
        return False
    return True


_ARIAL = Path(r"C:\Windows\Fonts\arial.ttf")


def contact_sheet(src: Path, out: Path, *, cols: int = 5, rows: int = 6,
                  width: int = 240, duration: float | None = None) -> Path:
    """把整条片子压成一张带时间戳的网格图（联系表）。

    一眼看完"第几秒发生了什么"，用来和分诊表/配方对账。
    采样点按 时长/(格子数) 均分 —— 几十秒的片子也只是一张图；
    要逐帧看是另一个需求（hypit 的 `tiles --every-frame`），不在这里做。
    """
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("没有 ffmpeg，生成不了联系表")
    cols, rows = max(1, int(cols)), max(1, int(rows))
    cells = cols * rows
    dur = float(duration or probe_duration(src) or 0)
    fps = max(cells / dur, 0.05) if dur > 0 else 1.0
    vf = f"fps={fps:.6f},scale={int(width)}:-2"
    # 时间戳用 drawtext 烧在每格左上角。Windows 上必须给字体文件，
    # 让 fontconfig 自己找字体会直接失败。路径里的冒号在滤镜串里要转义。
    if _ARIAL.exists():
        font = str(_ARIAL).replace("\\", "/").replace(":", r"\:")
        vf += (f",drawtext=fontfile='{font}':text='%{{pts\\:hms}}':x=6:y=6:"
               "fontcolor=white:fontsize=16:box=1:boxcolor=black@0.55:boxborderw=3")
    vf += f",tile={cols}x{rows}"
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-vf", vf, "-frames:v", "1", "-q:v", "3", str(out)],
        capture_output=True, text=True, errors="ignore", timeout=180,
    )
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"联系表生成失败: {(proc.stderr or '')[-300:]}")
    return out


async def extract_audio(src: Path, dest: Path) -> bool:
    """抽出音轨为 m4a(AAC)。成功返回 True。

    注意：本机 ffmpeg（剪映自带）不含 libmp3lame，故统一输出 AAC/m4a。
    先尝试 -c:a copy（无损、最快），失败再转码。
    """
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    dest.parent.mkdir(parents=True, exist_ok=True)

    async def _run(cmd: list[str]) -> bool:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            log.warning("抽音频失败: %s", (err or b"").decode("utf-8", "ignore")[:300])
            return False
        return dest.exists() and dest.stat().st_size > 0

    base = [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn"]
    # 1) 直接复制音轨
    if await _run(base + ["-c:a", "copy", str(dest)]):
        return True
    # 2) 转 AAC
    return await _run(base + ["-c:a", "aac", "-b:a", "192k", str(dest)])
