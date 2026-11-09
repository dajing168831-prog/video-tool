"""静图运镜（免费快剪用）—— 逐字照竞品 `lib/video-composer/motions.ts` + `easing.ts`。

为什么要有这一层：免费快剪的画面是**商品图/素材图**，不是视频。图片直接进 ffmpeg
会变成一张死画面（观感像 PPT），竞品给每张图套一个 `zoompan` 运镜（缓慢放大 /
肯伯恩斯等），免费成片才有「在动」的感觉。滤镜表达式必须与竞品逐字一致，
不然同一份素材出来的观感就对不上。

出处对照：
  · `motions.ts:16-75` 五个运镜的 zoompan 表达式
  · `easing.ts:12-22` easeOut = `(1-pow(1-p,2))`（先快后慢，收得自然）
  · `compose/route.ts:109-123` `defaultMotion(shot)`：按镜头类型给默认运镜
"""
from __future__ import annotations

#: 与竞品一致的帧率（`motions.ts` 里每个滤镜都写死 30）
FPS = 30
DEFAULT_MOTION = "ken_burns"


def _ease_out(p: str) -> str:
    """竞品 `easing.ts:14`：二次缓出。"""
    return f"(1-pow(1-{p},2))"


def _interpolate(frames: int, v0: float, v1: float) -> str:
    """竞品 `easing.ts:36-40`：`v0 + (v1-v0) * easeOut(on/frames)`。"""
    f = max(1, int(frames))
    p = f"(on/{f})"
    return f"({v0}+({round(v1 - v0, 6)})*{_ease_out(p)})"


def _zoompan(z: str, x: str, y: str, frames: int, w: int, h: int) -> str:
    return (f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:"
            f"s={w}x{h}:fps={FPS}")


def motion_filter(key: str, width: int, height: int, duration: float) -> str:
    """按运镜 id 生成 zoompan 表达式；认不出的 id 回落肯伯恩斯（绝不丢这一段）。"""
    frames = max(1, int(round(float(duration) * FPS)))
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    key = str(key or "").strip()

    if key == "zoom_in_slow":
        return _zoompan(_interpolate(frames, 1, 1.5), cx, cy, frames, width, height)
    if key == "zoom_out_slow":
        return _zoompan(_interpolate(frames, 1.5, 1), cx, cy, frames, width, height)
    if key == "pan_left":
        return _zoompan("1.3", f"{cx}+on*(iw/zoom/{frames}*0.3)", cy, frames, width, height)
    if key == "pan_right":
        return _zoompan("1.3", f"{cx}-on*(iw/zoom/{frames}*0.3)", cy, frames, width, height)
    if key == "static":
        return _zoompan("1", cx, cy, frames, width, height)
    if key == "bounce":
        # 竞品 `motions.ts:66-70`：前 30% 弹入 → 30%~50% 回落 → 之后 1.4 稳住
        f = frames
        z = (f"if(lt(on,{f * 30 // 100}),1+on*0.02,"
             f"if(lt(on,{f * 50 // 100}),1.6-(on-{f * 30 // 100})*0.01,1.4))")
        return _zoompan(z, cx, cy, frames, width, height)
    # ken_burns（含所有认不出的写法）：缓慢放大 + 轻微平移
    return _zoompan(_interpolate(frames, 1, 1.3),
                    f"{cx}+on*(iw*0.00046)", cy, frames, width, height)


def motion_for_shot(shot: dict) -> str:
    """这一镜的默认运镜。

    竞品按 `shot.type`（hook/product_reveal/demo/cta）分配；我们的分镜没有这个枚举
    （只有 `purpose` 自由文本），所以**不硬套**——有 `motion` 字段就用，
    没有一律 `ken_burns`（竞品 `motions.ts:86` 的 DEFAULT_MOTION 也是它）。
    """
    key = str((shot or {}).get("motion") or "").strip()
    return key if key else DEFAULT_MOTION
