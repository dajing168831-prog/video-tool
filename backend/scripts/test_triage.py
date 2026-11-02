"""逐镜分诊的自检（纯逻辑 + 真 ffmpeg 算运动量，不花钱）。

验的是"1:1 复刻"的核心判断：
  - 用户没勾的镜头一律保留原片（这才是真正的 1:1）
  - 勾了的镜头一律把原片片段喂给模型（video），**没有静帧这条岔路**
  - 短镜头要合并/撑到模型能收的 4 秒，又不能超过通道上限

🩸 2026-11-02 主人拍板删掉了「静止镜头走静帧重绘」那一档：
运动量阈值 1.2 是自造的（出处那篇 hypit 文档只讲原则、没有数值），
实测真实素材能低到 0.28，判成静止的那一镜走另一条链路、造型对不上。

运行：python scripts/test_triage.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import scene, triage  # noqa: E402
from app.services.media import ffmpeg_path  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def shot(i, start, dur, motion):
    return {"i": i, "start": round(start, 3), "end": round(start + dur, 3),
            "dur": dur, "motion": motion}


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    print("== 分诊规则 ==")
    shots = [
        shot(0, 0.0, 3.0, 0.2),          # 产品静物：基本不动
        shot(1, 3.0, 3.0, 12.0),         # 跳舞：动
        shot(2, 6.0, 3.0, 0.4),          # 空镜：基本不动
        shot(3, 9.0, 3.0, 18.0),         # 运镜：动
    ]
    d = triage.decide(shots)
    check("不勾 → 全保留原片", set(d.values()), {"video"})
    check("汇总", triage.summary(d), {"keep": 0, "still": 0, "video": 4})

    # 🩸 运动量不再影响走法：0.2 的画面勾了也是 video
    d_mix = triage.decide(shots, picks=[0, 2])
    check("勾了低运动量镜头 → 仍走 video", d_mix[0], "video")
    check("没勾的高运动量镜头 → 保留原片", d_mix[1], "keep")
    check("勾了空镜 → 仍走 video（不再走静帧）", d_mix[2], "video")

    d2 = triage.decide(shots, picks=[1])
    check("只勾 1 时 0 保留", d2[0], "keep")
    check("只勾 1 时 1 走 video", d2[1], "video")
    check("只勾 1 时 3 保留", d2[3], "keep")
    check("只勾 1 的汇总", triage.summary(d2), {"keep": 3, "still": 0, "video": 1})

    print("== 区间合并 ==")
    # 只有 1 是 video，0 和 2 保留原片：应该只出一段
    spans = triage.video_spans(shots, d2, limit=30, total=12)
    check("只有勾选的镜头进视频区间", len(spans), 1)
    check("保留原片的镜头不进视频区间", (spans[0][0], spans[0][1]), (3.0, 7.0))

    adj = [
        shot(0, 0.0, 3.0, 12.0),
        shot(1, 3.0, 3.0, 14.0),
        shot(2, 6.0, 3.0, 18.0),
    ]
    adj_d = triage.decide(adj)
    sp = triage.video_spans(adj, adj_d, limit=30, total=9)
    check("相邻镜头合成一段", len(sp), 1)
    check("合起来的区间", (sp[0][0], round(sp[0][1], 2)), (0.0, 9.0))

    sp15 = triage.video_spans(adj, adj_d, limit=15, total=9)
    check("上限 15s 时仍是 1 段", len(sp15), 1)

    long_shots = [shot(i, i * 10.0, 10.0, 15.0) for i in range(4)]
    long_d = triage.decide(long_shots)
    sp30 = triage.video_spans(long_shots, long_d, limit=30, total=40)
    check("40s 动作戏按 30s 上限切 2 段", len(sp30), 2)
    check("段末到片尾", round(sp30[-1][1], 1), 40.0)

    # 🩸 2026-10-22 实测（任务 a47631b0）：0–11.7 走廊两个主角，11.7 硬切到
    # 楼梯空镜（换了一批人）。上限 15s 时切点必须落在 11.7 这个镜头边界上；
    # 按 15s 硬切会把切点包进请求里，模型在新场景继续套用旧主体。
    cut_shots = [shot(0, 0.0, 11.7, 15.0), shot(1, 11.7, 16.333, 12.0)]
    cut_d = triage.decide(cut_shots)
    spc = triage.video_spans(cut_shots, cut_d, limit=15, total=28.033)
    check("切点落在原片镜头边界上", round(spc[0][1], 3), 11.7)
    check("第二镜超上限 → 均分成三段", len(spc), 3)
    check("最后一段到片尾", round(spc[-1][1], 3), 28.033)
    check("每段都在 4–15s 内", all(4 - 1e-6 <= b - a <= 15 + 1e-6 for a, b in spc), True)

    # 🩸 同一任务的第二刀：24.433 是软切（`scene._hist_cuts` 补回来的）。
    # 按边界切完只剩 3.6s，低于 4s 下限 —— 旧写法退回均分，切点回到 19.867，
    # 最后一段又横跨 24.433，等于白切。新写法保住边界，起点往回借到 24.033。
    cut2 = [shot(0, 0.0, 11.7, 15.0), shot(1, 11.7, 12.733, 12.0),
            shot(2, 24.433, 3.6, 12.0)]
    sp2 = triage.video_spans(cut2, triage.decide(cut2), limit=15, total=28.033)
    check("第二刀也钉在镜头边界上", round(sp2[1][1], 3), 24.433)
    check("尾巴靠起点往回借到下限", [round(a, 3) for a, _ in sp2],
          [0.0, 11.7, 24.033])
    check("最后一段正好 4s", round(sp2[2][1] - sp2[2][0], 3), 4.0)
    check("段长都在 4–15s 内", all(4 - 1e-6 <= b - a <= 15 + 1e-6 for a, b in sp2), True)

    print("== 真 ffmpeg 运动量（只用于报告，不参与分诊）==")
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="triage_"))
    try:
        ff = ffmpeg_path()
        static_v = work / "static.mp4"
        moving_v = work / "moving.mp4"
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "color=c=navy:s=320x240:d=3:r=25",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(static_v)],
                       check=True, capture_output=True)
        # testsrc2 自带随时间变化的测试图案 = 有运动
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=3",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(moving_v)],
                       check=True, capture_output=True)

        m_static = scene.motion(static_v, 0.2, 2.8)
        m_move = scene.motion(moving_v, 0.2, 2.8)
        check("静止画面运动量≈0", m_static < 0.5, True)
        check("移动画面运动量明显更大", m_move > max(m_static + 1, 1.2), True)
        print(f"       （实测 静止={m_static} 运动={m_move}；两者分诊结果相同）")
        check("静止画面勾了也走 video",
              triage.decide([shot(0, 0.0, 3.0, m_static)], [0])[0], "video")
        check("移动画面勾了走 video",
              triage.decide([shot(0, 0.0, 3.0, m_move)], [0])[0], "video")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
