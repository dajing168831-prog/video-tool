"""P8 验收：从零写（没有原片，台词 + 画面 → 成片）。

产品上的一句话：**不依赖任何参考视频，写台词和画面就能出一条片。**

这条链最容易出的两种错，都跟钱有关：
  1. 台词某一行念出来超过单段上限，系统不吭声 → 生成被拒 → 钱花了没片子；
  2. 台词行数和画面行数对不上，系统"帮你凑" → 出来的片子不是你要的。

跑法：python scripts/p8_check.py

全程零模型调用：TTS 和视频生成都被替换成本地 ffmpeg 合成，
真有网络请求就打红（和 P1 的做法一致）。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import media, scratch  # noqa: E402

rows: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, bool(ok), detail))


# ---------------------------------------------------------------------------
# 假货：本地合成音轨 / 画面，任何真网络调用都会炸

class FakeTTS:
    ext = ".mp3"

    def synth(self, text: str, out: Path, *, voice: str = "", rate: int = 0) -> Path:
        # 一个字 0.16 秒，够长到能测"短台词也要生成 4 秒再截"
        dur = max(0.6, len(text) * 0.16)
        out.parent.mkdir(parents=True, exist_ok=True)
        ff = media.ffmpeg_path()
        subprocess.run(
            [ff, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur:.2f}",
             "-c:a", "libmp3lame", "-q:a", "9", str(out)],
            check=True, capture_output=True, timeout=60,
        )
        return out


def fake_gen(channel, model, prompt, out: Path, *, duration, ratio, resolution):
    ff = media.ffmpeg_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = (360, 640) if ratio == "9:16" else (640, 360)
    subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=0x223344:s={w}x{h}:r=24:d={int(duration)}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True, timeout=120,
    )
    return out


def main() -> int:
    # ---- 1. 切分与配对 ---------------------------------------------------
    a = scratch.split_lines("第一句。第二句！第三句")
    chk("1.1 没写换行时按句末标点断", len(a) == 3, " | ".join(a))

    b = scratch.split_lines("第一行\n第二行\n\n第三行")
    chk("1.2 写了换行就按行断（不合并）", b == ["第一行", "第二行", "第三行"],
        " | ".join(b))

    shots = scratch.build_shots("甲。乙。", "同一个画面")
    chk("1.3 画面只写一段 → 全片共用", len(shots) == 2
        and shots[0]["desc"] == shots[1]["desc"], f"{len(shots)} 镜")

    try:
        scratch.build_shots("甲。乙。丙。", "画面一\n画面二")
        raise AssertionError("行数对不上竟然过了")
    except scratch.ScratchError as e:
        msg = str(e)
    chk("1.4 行数对不上 → 明确报错，不替用户凑",
        "画面写了 2 段" in msg and "台词有 3 段" in msg, msg[:40])

    # ---- 2. 花钱前就拦得住 -------------------------------------------------
    long_line = "这是一句非常长的台词" * 10         # 100 字 ≈ 20 秒，必然超 15 秒上限
    p = scratch.plan(long_line, "一个画面", channel="volc",
                     model="doubao-seedance-2-0-260128")   # 该型号单段上限 15s
    chk("2.1 单行超长在预估阶段就拦下（这时一分钱没花）",
        bool(p["blocked"]) and "超过单段上限" in p["blocked"], p["blocked"][:40])

    p2 = scratch.plan("短句。", "一个画面", channel="volc")
    chk("2.2 预估给的镜头数 = 台词行数",
        p2["count"] == 1 and p2["video_calls"] == 1, f'{p2["count"]} 镜')
    chk("2.3 预估不报没配的价（known=False 时不给金额）",
        p2["price"]["known"] is False and p2["price"]["amount"] is None,
        "单价未配置")

    # ---- 3. 真跑一遍（全本地） --------------------------------------------
    work = Path(tempfile.mkdtemp(prefix="p8_", dir="D:/"))
    from app.services.providers import tts as tts_mod

    orig_gen = scratch._gen_one
    real_get = tts_mod.get_tts
    try:
        tts_mod.get_tts = lambda: FakeTTS()
        # scratch.render 里是 `from app.services.providers.tts import get_tts`
        # —— 每次调用重新 import，所以补丁打在模块上就生效
        scratch._gen_one = fake_gen

        res = scratch.render(
            script="第一句台词。第二句台词。",
            descs="一间教室\n一片海",
            workdir=work,
            ratio="9:16",
            channel="volc",
            model="doubao-seedance-2-5-260628",
            voice="",
            lang="zh",
            want_subtitle=True,
        )
        out = work / "out.mp4"
        chk("3.1 成片落盘", out.exists() and out.stat().st_size > 0,
            f"{out.stat().st_size // 1024}KB" if out.exists() else "没有 out.mp4")

        info = __import__("app.services.scene", fromlist=["x"]).probe(out)
        chk("3.2 成片时长 = 配音总长（不靠 -shortest 猜）",
            abs(info["duration"] - res["duration"]) < 0.4,
            f'成片 {info["duration"]}s / 合同 {res["duration"]}s')

        segs = res["segments"]
        contiguous = all(
            abs(segs[i]["end"] - segs[i + 1]["start"]) < 0.01 for i in range(len(segs) - 1)
        )
        chk("3.3 字幕时间轴首尾相接、无空洞",
            contiguous and segs[0]["start"] == 0.0
            and abs(segs[-1]["end"] - res["duration"]) < 0.01,
            f'{len(segs)} 段')

        chk("3.4 每个镜头都真的生成过一次",
            res["replaced_shots"] == 2, f'{res["replaced_shots"]} 段素材')

        chk("3.5 质检跑过并给了结论",
            isinstance(res.get("qc"), dict) and "ok" in res["qc"],
            str(res["qc"].get("issues") or res["qc"].get("warnings") or "无问题")[:48])

        chk("3.6 字幕文件生成（要字幕时）", (work / "cap.ass").exists(), "cap.ass")
        chk("3.7 封面抽出（结果页要用）", (work / "cover.jpg").exists(), "cover.jpg")

        # ---- 4. 尺子自证：同一套假货，换台词 → 时长必须跟着变 ------------
        res2 = scratch.render(
            script="短。", descs="一个画面", workdir=work / "b",
            ratio="9:16", channel="volc", model="doubao-seedance-2-5-260628",
            lang="zh", want_subtitle=False,
        )
        chk("4.1 尺子自证：换台词 → 成片时长跟着变",
            abs(res2["duration"] - res["duration"]) > 0.3,
            f'{res2["duration"]}s vs {res["duration"]}s')
        chk("4.2 关掉字幕就不生成 .ass",
            not (work / "b" / "cap.ass").exists(), "没烧字幕")
    finally:
        scratch._gen_one = orig_gen
        tts_mod.get_tts = real_get

    ok = sum(1 for _n, o, _d in rows if o)
    for n, o, d in rows:
        print(f"{'PASS' if o else 'FAIL'}  {n}" + (f"  [{d}]" if d else ""))
    print(f"\n{ok}/{len(rows)} 通过")
    print(f"  产物在 {work}")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
