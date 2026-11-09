"""原生感后期（E7）—— 让 AI 成片看起来像手机随手拍。

出处：clipforge `src/lib/video-composer/native-feel.ts:1-171`，**逐值照抄**：
  · 三档强度参数 `:47-61`（margin / 正弦振幅 / 噪点 / 饱和度 / 对比度 / 微旋转）
  · 低频叠层 `:64`（单频像机械摇摆，两层才像手抖）
  · 滤镜组装 `:72-110`（过扫 → 漂移裁切 → 颗粒 → 去精致调色 → 暗角 / 光晕 / 二压感）
  · 编码 `:134-171`（phoneCompress 时切 CRF 27，靠码率疤痕出「二压」质感）
  · 种子 → 相位 `:78`，**确定性**（没有随机数，同 seed 同结果，可 A/B）

为什么是「后期」而不是改生成：这一层只重跑合成片，不碰生成链、不花钱；
竞品同样把它做成 compose 之后的后处理。

🩸 这一层会**重新编码画面**（`-c:a copy`，音频不重编）。有声无画、纯图都会失败 —— 由调用方拦。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.media import ffmpeg_path, ffprobe_path

STRENGTHS = {
    "subtle": {"margin_ratio": 0.011, "amp_ratio": (0.62, 0.3), "noise": 5,
               "saturation": 0.95, "contrast": 0.985, "rotate": 0.0},
    "medium": {"margin_ratio": 0.02, "amp_ratio": (0.62, 0.3), "noise": 9,
               "saturation": 0.92, "contrast": 0.97, "rotate": 0.0},
    "strong": {"margin_ratio": 0.03, "amp_ratio": (0.62, 0.3), "noise": 12,
               "saturation": 0.9, "contrast": 0.96, "rotate": 0.0018},
}
DEFAULT_STRENGTH = "subtle"

#: 低频（竞品 `native-feel.ts:64`）
FREQ = {"x1": 1.3, "x2": 3.7, "y1": 1.1, "y2": 2.9}


def _fmt(n: float) -> str:
    return str(round(n * 100) / 100)


def build_native_feel_filter(width: int, height: int, *, strength: str = DEFAULT_STRENGTH,
                             seed: int = 0, grain: bool = True,
                             vignette: bool = False, halation: bool = False,
                             phone_compress: bool = False) -> str:
    """组装 `-filter_complex`（竞品 `native-feel.ts:72-110` 逐字）。输出标签固定 `[vout]`。"""
    p = STRENGTHS.get(strength) or STRENGTHS[DEFAULT_STRENGTH]
    mx = max(4, round(width * p["margin_ratio"]))
    my = max(4, round(height * p["margin_ratio"]))

    def ph(k: float) -> str:
        return _fmt(((seed * 0.61803 + k) % 1) * 6.2832)

    ax1 = round(mx * p["amp_ratio"][0])
    ax2 = round(mx * p["amp_ratio"][1])
    ay1 = round(my * p["amp_ratio"][0])
    ay2 = round(my * p["amp_ratio"][1])
    x = (f"{mx}+{ax1}*sin(t*{FREQ['x1']}+{ph(0.13)})"
         f"+{ax2}*sin(t*{FREQ['x2']}+{ph(0.41)})")
    y = (f"{my}+{ay1}*cos(t*{FREQ['y1']}+{ph(0.71)})"
         f"+{ay2}*sin(t*{FREQ['y2']}+{ph(0.29)})")

    parts = [f"scale={width + 2 * mx}:{height + 2 * my}"]
    if p["rotate"] > 0:
        parts.append(f"rotate='{p['rotate']}*sin(t*0.9+{ph(0.53)})':bilinear=1")
    parts.append(f"crop=w={width}:h={height}:x='{x}':y='{y}'")
    if phone_compress:
        pw = max(2, round((width * 2) / 3 / 2) * 2)
        phh = max(2, round((height * 2) / 3 / 2) * 2)
        parts.append(f"scale={pw}:{phh}:flags=bilinear")
        parts.append(f"scale={width}:{height}")
        parts.append("unsharp=5:5:0.6:5:5:0.0")
    if grain:
        parts.append(f"noise=alls={p['noise']}:allf=t")
    if phone_compress:
        parts.append("eq=saturation=1.12:contrast=1.05")
    else:
        parts.append(f"eq=saturation={p['saturation']}:contrast={p['contrast']}")
    if vignette:
        parts.append("vignette=angle=PI/8")
    body = f"[0:v]{','.join(parts)}[vout]"
    if not halation:
        return body
    glow = (f"[0:v]{','.join(parts)}[base];"
            "[base]split[hbase][hglow];"
            "[hglow]lutyuv=y='if(gt(val,200),val,0)',gblur=sigma=14:steps=4,"
            "curves=blue='0/0 1/0.85':green='0/0 1/0.92'[hg];"
            "[hbase][hg]blend=all_mode=screen[vout]")
    return glow


def probe_size(video: Path) -> tuple[int, int]:
    """读画面尺寸；失败回落 1080×1920（竞品 `native-feel.ts:113-131`）。"""
    fp = ffprobe_path()
    if not fp:
        return 1080, 1920
    try:
        p = subprocess.run(
            [fp, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, errors="ignore", timeout=60)
        w, h = (int(x) for x in (p.stdout or "").strip().split(",")[:2])
        if w > 0 and h > 0:
            return w, h
    except Exception:  # noqa: BLE001
        pass
    return 1080, 1920


def apply(video: Path, out: Path, *, strength: str = DEFAULT_STRENGTH, seed: int = 0,
          grain: bool = True, vignette: bool = False, halation: bool = False,
          phone_compress: bool = False) -> Path:
    """跑一遍原生感链 → 新 mp4（竞品 `native-feel.ts:134-171`）。"""
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    video, out = Path(video), Path(out)
    if not video.exists():
        raise RuntimeError("成片文件不存在")
    width, height = probe_size(video)
    vf = build_native_feel_filter(width, height, strength=strength, seed=seed,
                                  grain=grain, vignette=vignette,
                                  halation=halation, phone_compress=phone_compress)
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-filter_complex", vf, "-map", "[vout]", "-map", "0:a?",
         "-map_metadata", "0",
         "-c:v", "libx264", "-preset", "medium",
         "-crf", "27" if phone_compress else "20",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         "-c:a", "copy", str(out)],
        capture_output=True, text=True, errors="ignore", timeout=1800,
    )
    if p.returncode != 0 or not out.exists():
        out.unlink(missing_ok=True)
        raise RuntimeError(f"原生感处理失败：{(p.stderr or '')[-200:]}")
    return out
