"""编辑任务请求体自检 —— 逐字段核对**真正发给火山的 body**，不发网络请求。

出处（2026-10-21 抓自官方）：
    POST /api/v3/contents/generations/tasks  https://www.volcengine.com/docs/82379/1520757
    Seedance 2.5 任务类型与限制              https://www.volcengine.com/docs/82379/2607688
逐项对的是：
    - 2.5 编辑任务：omni_reference_task_type=edit / duration=-1 / ratio=adaptive
    - 2.0 系列：没有 omni_reference_task_type，duration 同样只能是 -1
      （API 参考「duration = -1 适配规则」：2.0 由模型在 [4,15] 里自己挑整数秒）
    - generate_audio 默认 true → 我们必须显式关掉（音轨永远来自 TTS 或原片）
    - content 顺序：text → reference_video → reference_image…（@图片N 就是这个顺序）

运行：python scripts/test_ark_edit_body.py --model volc20|volc25|h3
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import ark  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一次只跑一家。
    from _model_gate import sel_or_exit
    sel_or_exit()

    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="arkbody_"))
    img = work / "p.jpg"
    img.write_bytes(b"\xff\xd8\xff\xd9")     # 只为拼 data URI，不解码

    print("== 2.5 编辑任务 ==")
    b = ark.edit_body("编辑@视频1，把人物替换为@图片1中的人物",
                      video_url="https://x.test/seg.mp4", ref_images=[img],
                      model="doubao-seedance-2-5-260628", resolution="1080p",
                      duration=10.4)
    check("型号原样", b["model"], "doubao-seedance-2-5-260628")
    check("显式任务类型", b.get("omni_reference_task_type"), "edit")
    check("duration 只能 -1", b.get("duration"), -1)
    check("ratio 只能 adaptive", b.get("ratio"), "adaptive")
    check("分辨率照传", b["resolution"], "1080p")
    check("不打角标", b["watermark"], False)
    check("不生成音频（默认 true，必须显式关）", b["generate_audio"], False)
    # 官方 seedance-25-guide.md:81「建议 output_format 使用 mov 格式」
    # + :339「MOV 在编辑任务中更好地保持颜色与亮度一致性、声画一致性」
    check("2.5 编辑任务要 mov", b.get("output_format"), "mov")

    print("== 2.0 系列：没有 omni 参数，时长向上取整 ==")
    # 🩸 2.0 的输出时长只能是整数秒：给 -1 就由模型"自己挑"，5.503s 的段会回来 5s，
    # 拼接时只能冻住最后一帧补时长。给 ceil 就一定 ≥ 原段，多的裁掉（裁尾巴看不出来）。
    # 官方 2.0 编辑示例本身就是显式给 duration=5，不是 -1。
    for mid in ("doubao-seedance-2-0-260128",
                "doubao-seedance-2-0-fast-260128",
                "doubao-seedance-2-0-mini-260615"):
        b = ark.edit_body("严格编辑@视频1，把人物替换为@图片1中的人物",
                          video_url="https://x.test/seg.mp4", ref_images=[img],
                          model=mid, duration=10.4)
        check(f"{mid} 不发 omni_reference_task_type", "omni_reference_task_type" in b, False)
        # output_format 是 2.5 才有的建议项，2.0 系列文档没有 → 不替它做决定
        check(f"{mid} 不发 output_format", "output_format" in b, False)
        check(f"{mid} duration 向上取整", b.get("duration"), 11)
        check(f"{mid} ratio 给 adaptive", b.get("ratio"), "adaptive")
    # 超出型号区间就夹到 [4,15]；没给时长（老调用方）才退回 -1
    for raw, want in ((20, 15), (1.2, 4), (0, -1)):
        b = ark.edit_body("x", video_url="u", model="doubao-seedance-2-0-260128",
                          duration=raw)
        check(f"2.0 传 {raw} → {want}", b["duration"], want)
    b = ark.edit_body("x", video_url="u", model="doubao-seedance-2-0-260128")
    check("没给时长 → -1（交给模型）", b["duration"], -1)

    print("== content 顺序与 role ==")
    b = ark.edit_body("p", video_url="https://x.test/seg.mp4",
                      ref_images=[img, "asset-2026abc"],
                      model="doubao-seedance-2-5-260628")
    c = b["content"]
    check("第一项是文本", c[0]["type"], "text")
    check("文本就是提示词原文", c[0]["text"], "p")
    check("第二项是参考视频", c[1]["type"], "video_url")
    check("视频 role", c[1]["role"], "reference_video")
    check("视频用公网 URL", c[1]["video_url"]["url"], "https://x.test/seg.mp4")
    check("参考图数量", len(c) - 2, 2)
    check("图片 role", c[2]["role"], "reference_image")
    check("本机图转 base64", c[2]["image_url"]["url"].startswith("data:image/"), True)
    check("素材 ID 自动补 asset://", c[3]["image_url"]["url"], "asset://asset-2026abc")

    print("== 口型参考音频（data URI，不用上传）==")
    wav = work / "a.wav"
    wav.write_bytes(b"RIFF....WAVE")          # 只为拼 data URI，不解码
    b = ark.edit_body("p", video_url="https://x.test/seg.mp4", ref_images=[img],
                      ref_audio=wav, model="doubao-seedance-2-0-mini-260615")
    c = b["content"]
    check("音频排在参考图之后", c[-1]["type"], "audio_url")
    check("音频 role", c[-1]["role"], "reference_audio")
    check("音频走 base64 而非公网 URL",
          c[-1]["audio_url"]["url"].startswith("data:audio/wav;base64,"), True)
    b2 = ark.edit_body("p", video_url="u", model="doubao-seedance-2-0-mini")
    check("不给音频就一项都不加",
          any(x.get("type") == "audio_url" for x in b2["content"]), False)

    print("== generate_audio 默认关 ==")
    b = ark.edit_body("p", video_url="u", model="doubao-seedance-2-0-260128")
    check("不传也是关", b["generate_audio"], False)

    print("== 图片生成：参考图是数组（图一/图二）==")
    # 官方图片生成 API：`image` 收 string 或 string[]，提示词用「图一/图二」指代。
    # 🩸 静帧重绘换人时少发人物图 = 模型只能按文字凭空造脸。
    ib = ark.image_body("把图一人物换成图二", image_urls=["data:image/jpeg;base64,AA",
                                                          "data:image/jpeg;base64,BB"])
    check("两张参考图都在", len(ib["image"]), 2)
    check("顺序=原片帧在前", ib["image"][0].endswith("AA"), True)
    check("不传参考图就没有 image 字段",
          "image" in ark.image_body("只写文字"), False)
    check("空列表也不加", "image" in ark.image_body("x", image_urls=[]), False)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
