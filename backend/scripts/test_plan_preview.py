"""出片预览自检：**全程不调 TTS / 图 / 视频模型，不联网、不花钱**。

验的是：
  - 预览能给出成片合同（时长 / 帧数 / 48000Hz 采样数）
  - 文案明显太短会被提前标 blocked，而不是等出片才报错
  - 保留原声时不需要文案
  - 没有配单价时明确说"未知"，不拿记忆里的价格凑数

运行：python scripts/test_plan_preview.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_pipeline  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


REC = {
    "source": {"duration": 6.0, "fps": 25.0, "width": 360, "height": 640,
               "has_audio": True},
    "shots": [{"i": 0, "start": 0.0, "end": 6.0, "text": "你好世界",
               "motion": 0.0}],
    "speech": {"lang": "zh", "segments": [
        {"start": 0.0, "end": 6.0, "text": "你好世界"}]},
}

GOOD = "我们今天给大家介绍一款非常好用的产品它的价格很实惠而且效果特别明显"


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    print("== 正常文案：给出成片合同 ==")
    r = clone_pipeline.preview_render(
        Path("unused.mp4"), REC, script=GOOD,
        edit_spec={"audio": "tts"},
    )
    check("预览通过", r["ok"], True)
    check("没有拦下原因", r["blocked"], "")
    check("画面不动", r["change"]["mode"], "none")
    c = r["contract"]
    check("目标时长", c["duration"], 6.0)
    check("帧数 = 6s×25fps", c["frames"], 150)
    check("采样率", c["audio_sample_rate"], 48000)
    check("采样数 = 6s×48000", c["audio_samples"], 288000)
    p = r["price"]
    check("单价未配置时金额为 None", p["amount"] if not p["known"] else "known", None)
    check("报价按请求分组", [g["key"] for g in p["groups"]], ["tts"])
    check("未知的分组继续可见", p["unknown"], ["tts"])

    print("== 只配了视频单价：仍不给总额 ==")
    import dataclasses
    import app.core.config as cfg
    old = cfg.settings
    cfg.settings = dataclasses.replace(old, price_video_per_sec=0.5)
    try:
        r4 = clone_pipeline.preview_render(
            Path("unused.mp4"), REC, script=GOOD, edit_spec={"audio": "tts"},
        )
        check("部分已知不算已知", r4["price"]["known"], False)
        check("总额仍为 None", r4["price"]["amount"], None)
        check("缺的是配音", r4["price"]["unknown"], ["tts"])
        check("已配的单价照常显示", r4["price"]["groups"][0]["rate"], 0.0)
    finally:
        cfg.settings = old

    print("== 全部单价配齐：才给总额 ==")
    cfg.settings = dataclasses.replace(
        old, price_tts_per_1k_chars=5.0, price_video_per_sec=0.5)
    try:
        r5 = clone_pipeline.preview_render(
            Path("unused.mp4"), REC, script=GOOD, edit_spec={"audio": "tts"},
        )
        check("全部已知才算已知", r5["price"]["known"], True)
        check("总额=千字单价×字数",
              r5["price"]["amount"],
              round(r5["price"]["groups"][0]["units"] * 5.0, 2))
    finally:
        cfg.settings = old

    print("== 文案太短：提前标 blocked ==")
    r2 = clone_pipeline.preview_render(
        Path("unused.mp4"), REC, script="你好",
        edit_spec={"audio": "tts"},
    )
    check("不通过", r2["ok"], False)
    check("说明了原因", "可调范围" in r2["blocked"], True)

    print("== 换人物没给图：出片前就拦下 ==")
    # 🩸 没图时提示词只能拿 person_desc 当目标，而诊断页填的是**原片那个人**
    # 的描述 → 「替换为他自己」。实测 2026-10-21 那条 12s 火山片连人都没换。
    r6 = clone_pipeline.preview_render(
        Path("unused.mp4"), REC, script=GOOD,
        edit_spec={"change": {"person": True}},
    )
    check("预览不通过", r6["ok"], False)
    check("说清楚缺的是人物照片", "人物照片" in r6["blocked"], True)

    print("== 保留原声：不需要文案 ==")
    r3 = clone_pipeline.preview_render(
        Path("unused.mp4"), REC, script=None,
        edit_spec={"audio": "original"},
    )
    check("预览通过", r3["ok"], True)
    check("声音模式", r3["audio"]["mode"], "original")
    check("配音秒数=原片", r3["audio"]["voice_seconds"], 6.0)

    # 🩸 2026-10-31：这组原来用 2.0 Mini 触发「中文 ≤500 字」的建议。
    #   2.0 已从**复刻爆款**下架（主人拍板）⇒ 这条预览入口只会拿到 2.5，
    #   而 2.5 官方 skill 明写「不设置固定字数上限」（`sd25-pe:522`，参数表
    #   `prompt_advised` 留空）⇒ 长提示词**不该**再出这条提醒。
    #   判据跟着型号走：短/长都给空，且长提示词照样放行（超字不拦）。
    print("== 提示词建议字数：2.5 不设固定上限 → 不提示、不拦 ==")
    _short = {"audio": "original",
              "change": {"product": True, "product_desc": "白色陶瓷面霜罐"}}
    r7 = clone_pipeline.preview_render(
        Path("unused.mp4"), REC, script=None, edit_spec=_short,
        refs={"product": Path("nope.jpg")},
        regen_channel="volc", regen_model="doubao-seedance-2-5-260628",
    )
    check("短提示词：不给提醒（成对的下半）", r7.get("prompt_advice"), "")

    _long = "身材高大的中年男人，穿着深蓝色工装夹克和灰色长裤，短寸头，戴黑框眼镜，" * 16
    _big = {"audio": "original",
            "change": {"person": True, "person_ids": ["P1"],
                       "person_desc": _long,
                       "product": True, "product_desc": "白色陶瓷面霜罐",
                       "scene": True,
                       "scene_desc": "夜晚的城市天台，远处有霓虹灯招牌"},
            "extra": _long}
    r8 = clone_pipeline.preview_render(
        Path("unused.mp4"), REC, script=None, edit_spec=_big,
        refs={s: Path("nope.jpg") for s in ("person", "product", "scene")},
        subject_image=Path("nope2.jpg"),
        regen_channel="volc", regen_model="doubao-seedance-2-5-260628",
    )
    # 成对的上半：2.5 不设固定上限 ⇒ 再长也不给建议字数提醒
    check("长提示词：2.5 无固定字数上限 → 不给提醒", r8.get("prompt_advice"), "")
    check("长提示词照样放行（超字不拦）", r8["ok"], True)
    check("提醒不进 warnings（前端确认框只显示 warnings[0]，会被挤掉）",
          any("建议中文" in w for w in r8.get("warnings") or []), False)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
