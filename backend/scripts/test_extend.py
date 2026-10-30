# -*- coding: utf-8 -*-
"""延长（B5）共用层行为判据 —— 零费用，不出片。

🩸 2026-10-27 主人：「2.0模型现在还有什么需要测试的」。
   查下来延长这条路**一个测试脚本都没有**（只有 `ruler_sd20` 的 D6 量提示词文本）。
   而 D6 用例里带着 `content=""`，尺子对它**报绿** —— 因为尺子只看句式前缀，
   不看「生成」后面有没有东西。实际产物是残句：

       向后延长@视频1，生成

   前端 `result.vue` 有拦，但接口公开，直接 POST 就是一条残句送出去、钱照扣。

本脚本只验**型号无关**的共用层（空内容拦截 / 方向归一 / 秒数夹取），
各家句式仍归各家自己的尺子（`ruler_sd20` / `ruler_sd25` / `ruler_h3`）。

用法： python scripts/test_extend.py --model volc20
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
if str(BACK) not in sys.path:
    sys.path.insert(0, str(BACK))
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _model_gate import sel_or_exit  # noqa: E402

MODEL = sel_or_exit(only="volc20")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_store as store  # noqa: E402
from app.services import extend as X  # noqa: E402
from app.services import models  # noqa: E402

_fail = 0
_n = 0


def check(name: str, got, want) -> None:
    global _fail, _n
    _n += 1
    ok = got == want
    if not ok:
        _fail += 1
    print(f"{'✅' if ok else '🔴'} {name}"
          + ("" if ok else f"\n     实际 {got!r} / 期望 {want!r}"))


def _run(**kw):
    """调一次 `extend.run`，把 `store.render_dir` 指到临时目录（零污染）。"""
    tmp = Path(tempfile.mkdtemp(prefix="ext_probe_", dir="D:/tmp/clone_diag"))
    old = store.render_dir
    store.render_dir = lambda cid, rid: (tmp / rid)  # noqa: ARG005
    try:
        return X.run(base=tmp / "没有这个文件.mp4", progress=None, **kw)
    finally:
        store.render_dir = old
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# 闸门键（`volc20`）不是型号 id —— `adapter_for` 认的是真实 id。
# 与 `ruler_sd20.SD_M` 同一个机型，保证两条尺子量的是同一条路。
MID = "doubao-seedance-2-0-mini-260615"


def main() -> int:
    common = dict(cid="__probe__", rid="r1", direction="back", seconds=5)

    # ---- 1. 空内容：必须拦在花钱之前 ----
    for label, c in (("空字符串", ""), ("纯空格", "   "),
                     ("换行+空格", "\n\t  ")):
        try:
            _run(content=c, model=MID, resolution="720p", with_audio=False,
                 **{k: v for k, v in common.items() if k != "base_override"})
            got = "没拦住"
        except RuntimeError as e:  # noqa: PERF203
            got = str(e)
        check(f"内容{label} → 当场拒绝", "续出来的这段里发生什么" in got, True)

    # ---- 2. 成对：有内容时**不是**被空校验拦的（走到下一步才失败）----
    try:
        _run(content="她转身走进电梯", model=MID, resolution="720p",
             with_audio=False,
             **{k: v for k, v in common.items() if k != "base_override"})
        got = "居然跑完了"
    except RuntimeError as e:
        got = str(e)
    except Exception as e:  # noqa: BLE001
        got = f"{type(e).__name__}: {e}"
    check("有内容 → 过了空校验（换别的错）",
          "续出来的这段里发生什么" not in got, True)

    # ---- 3. 秒数夹取：不许把越界值原样发出去 ----
    ok_all = True
    detail = []
    for s in (-5, 0, 3, 30, 999):
        try:
            sec = X.clamp_seconds(s, MID)
        except Exception as e:  # noqa: BLE001
            ok_all = False
            detail.append(f"{s}→崩 {e}")
            continue
        if not isinstance(sec, int) or sec <= 0:
            ok_all = False
            detail.append(f"{s}→{sec!r}")
    check("越界秒数都被夹进合法区间" + (f"（{detail}）" if detail else ""),
          ok_all, True)

    return _more()




def _mk(path: Path, seconds: float, *, w: int = 360, h: int = 640,
        audio: bool = True, color: str = "navy") -> Path:
    """造一段测试视频（纯本地 ffmpeg，零费用）。"""
    from app.services import media
    ff = media.ffmpeg_path()
    if not ff:
        raise SystemExit("找不到 ffmpeg")
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:d={seconds}:r=25"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                "-c:a", "aac", "-b:a", "128k"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    import subprocess
    p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    if p.returncode != 0 or not path.exists():
        raise SystemExit("造测试视频失败: " + (p.stderr or "")[-400:])
    return path


def _more() -> int:
    """2.0 专属的延长形状（接缝计帧 / 清晰度归一 / 真拼接）。"""
    from app.services import media, scene
    from app.services.models import base as MBase

    global _fail, _n
    print("\n-- 接缝与清晰度（2.0 口径）--")
    cap = models.adapter_for(model=MID).caps
    # 🩸 2.0 指南 §「延长视频衔接处跳变」：前段末尾删 6 帧、后段开头删 1 帧。
    #   2.5 明确拼接处无痕迹（不裁），H3 官方没给规则（不裁）——三家各自声明。
    check("2.0 接缝裁帧 = 前段 6 / 后段 1（`guide` 延长接缝章节）",
          tuple(cap.extend_seam), (6, 1))
    check("2.0 声明有「两段视频补全」能力", cap.extend_transition, True)

    # 🩸 mini 只收 480p/720p —— 拿 1080p 的片子去延长会**降档**，这是对的
    #   （收不到的档位不能硬发，否则 400）。判据要按每台机型自己的档位表写，
    #   不能拿全量机型的期望去量 mini。
    check("竖屏 1080×1920 → mini 最高只到 720p（降档，不硬发 1080p）",
          X.pick_resolution(MID, 1080, 1920), "720p")
    check("横屏 1920×1080 → 同上，都是 720p",
          X.pick_resolution(MID, 1920, 1080), "720p")
    check("竖屏 720×1280（按短边算，不是长边）", X.pick_resolution(MID, 720, 1280), "720p")
    # 🩸 官方指南对延长的 resolution **只字未提**（`seedance-20-guide.md` 零命中）——
    #   「480p 的源该给 480p 还是 720p」是我们自己的取舍，指不到出处,**不判**。
    #   能判的硬约束只有一个：**返回的档位必须在该机型收的列表里**（收不到的会 400）。
    _allowed = str(models.adapter_for(model=MID).specs_for(MID).get("resolutions"))
    _bad = [f"{w}x{h}→{X.pick_resolution(MID, w, h)}"
            for w, h in ((480, 640), (640, 480), (720, 1280), (1080, 1920),
                         (1920, 1080), (3840, 2160), (100, 100))
            if X.pick_resolution(MID, w, h).lower() not in _allowed.lower()]
    check("任何源尺寸都落回该机型收的档位（收不到的会 400）" +
          (f"：[{_bad}]" if _bad else ""), _bad, [])
    # 全量机型（非 mini）支持 1080p → 1080p 的源就该给 1080p
    _FULL = "doubao-seedance-2-0-260128"
    check("同族全量机型：1080p 的源 → 1080p（档位表里有就给）",
          X.pick_resolution(_FULL, 1080, 1920), "1080p")

    # 🩸 2026-10-28（主人：「2.0可是有3个分支的」）：三台机型各跑一遍矩阵。
    #   标准版有 1080p/4k、极速版和 Mini 只到 720p，**每台都必须落在自己的档位表里**。
    _M3 = ("doubao-seedance-2-0-260128",
           "doubao-seedance-2-0-fast-260128",
           "doubao-seedance-2-0-mini-260615")
    _ovf = []
    for _m in _M3:
        _al = [str(x).lower()
               for x in (models.adapter_for(model=_m).specs_for(_m)
                         .get("resolutions") or [])]
        for _w, _h in ((480, 640), (720, 1280), (1080, 1920), (2160, 3840),
                       (640, 480), (1920, 1080), (100, 100)):
            for _want in ("", "480p", "720p", "1080p", "4k", "768P"):
                _got = X.pick_resolution(_m, _w, _h, _want)
                if _al and _got.lower() not in _al:
                    _ovf.append(f"{_m.split('2-0-')[1]}/{_w}x{_h}/{_want or 'auto'}"
                                f"→{_got}")
    check("三台 × 7 种源尺寸 × 6 种点名 = 126 组，全部落在各自档位表里" +
          (f"：[{_ovf[:3]}]" if _ovf else ""), _ovf, [])
    check("标准版拿 1080p 源 → 1080p；极速/Mini → 720p（差档不许混）",
          [X.pick_resolution(m, 1080, 1920) for m in _M3],
          ["1080p", "720p", "720p"])
    check("三台的接缝裁帧都是 (6, 1)（家族级口径）",
          [tuple(X.seam_frames(m)) for m in _M3], [(6, 1)] * 3)
    check("三台的时长夹取一致（官方 4–15s）",
          [(X.clamp_seconds(1, m), X.clamp_seconds(99, m)) for m in _M3],
          [(4, 15)] * 3)
    r = X.pick_resolution(MID, 720, 1280, "480p")
    check("点名 480p 且在档位表里 → 原样", r.lower() in str(
        models.adapter_for(model=MID).specs_for(MID).get("resolutions")).lower(), True)
    r2 = X.pick_resolution(MID, 720, 1280, "768P")
    check("点名别家的档位写法（768P）→ 收回本家默认档，不硬发出去",
          r2.lower() != "768p", True)

    print("\n-- 像素门槛（2.0 的 pixel_floor，实测踩过）--")
    import tempfile
    _tmp0 = Path(tempfile.mkdtemp(prefix="ext_px_", dir="D:/tmp/clone_diag"))
    try:
        # 🩸 2026-10-24 实测：836×480 = 401,280 px，差 6,416 px（1.6%）就被 400 拒单。
        small = _mk(_tmp0 / "small.mp4", 1.5, w=836, h=480)
        info0 = scene.probe(small)
        check("造出来的源片确实低于门槛（前提）",
              int(info0["width"]) * int(info0["height"]) < cap.extend_ref_min_px, True)
        fixed = X.normalize_ref(small, _tmp0 / "fixed.mp4",
                                min_px=cap.extend_ref_min_px,
                                max_px=cap.extend_ref_max_px)
        fi = scene.probe(fixed)
        check("不够门槛 → 放大到门槛以上",
              int(fi["width"]) * int(fi["height"]) >= cap.extend_ref_min_px, True)
        check("放大后宽高都是偶数（编码要求）",
              int(fi["width"]) % 2 == 0 and int(fi["height"]) % 2 == 0, True)
        check("放大后仍有音轨", bool(fi.get("has_audio")), True)
        check("放大只调尺寸，时长不变",
              abs(float(fi["duration"]) - float(info0["duration"])) < 0.15, True)

        # 成对：已达标的片子必须**原样返回**（不重编码 = 不掉画质）
        ok_src = _mk(_tmp0 / "ok.mp4", 1.0, w=720, h=1280)
        same = X.normalize_ref(ok_src, _tmp0 / "never.mp4",
                               min_px=cap.extend_ref_min_px,
                               max_px=cap.extend_ref_max_px)
        check("已经达标 → 原样返回同一个文件（不重编码）", same, ok_src)
        check("原样返回时不写出新文件", (_tmp0 / "never.mp4").exists(), False)

        # 上限方向：太大要缩（极少见，但分支存在）
        big = _mk(_tmp0 / "big.mp4", 0.6, w=3840, h=2160)
        fixed2 = X.normalize_ref(big, _tmp0 / "fixed2.mp4",
                                 min_px=cap.extend_ref_min_px,
                                 max_px=cap.extend_ref_max_px)
        f2 = scene.probe(fixed2)
        check("超过上限 → 缩到上限以下",
              int(f2["width"]) * int(f2["height"]) <= cap.extend_ref_max_px, True)
    finally:
        import shutil
        shutil.rmtree(_tmp0, ignore_errors=True)

    print("\n-- 真拼接（ffmpeg，零 API 费用）--")
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="ext_stitch_", dir="D:/tmp/clone_diag"))
    try:
        a = _mk(tmp / "a.mp4", 3.0, color="navy")
        b = _mk(tmp / "b.mp4", 3.0, color="maroon")
        out = tmp / "out.mp4"
        seam = X.stitch(a, b, out, model=MID)
        ai, bi, oi = scene.probe(a), scene.probe(b), scene.probe(out)
        fps = float(ai.get("fps") or 25.0)
        cut_a, cut_b = cap.extend_seam
        want = (float(ai["duration"]) - cut_a / fps) + (float(bi["duration"]) - cut_b / fps)
        got = float(oi["duration"])
        check(f"拼接总时长 ≈ 两段 - 裁掉的 {(cut_a + cut_b)} 帧"
              f"（{got:.2f}s vs {want:.2f}s）", abs(got - want) < 0.25, True)
        check("拼出来的片子有音轨（缺则补静音）", bool(oi.get("has_audio")), True)
        check("拼出来是偶数宽高（编码要求）",
              int(oi["width"]) % 2 == 0 and int(oi["height"]) % 2 == 0, True)
        check("返回的裁剪帧数与型号声明一致",
              (seam["cut_prev_frames"], seam["cut_next_frames"]) == (cut_a, cut_b), True)

        # 成对：后一段故意没有音轨 —— 必须补静音，不能把整条音轨吃掉
        b2 = _mk(tmp / "b2.mp4", 2.0, color="green", audio=False)
        out2 = tmp / "out2.mp4"
        X.stitch(a, b2, out2, model=MID)
        oi2 = scene.probe(out2)
        check("后段没有音轨 → 补等长静音，成片仍有音轨",
              bool(oi2.get("has_audio")), True)
        check("补静音后总时长仍 ≈ 两段和",
              abs(float(oi2["duration"]) - (float(ai["duration"])
                  - cut_a / fps + float(scene.probe(b2)["duration"])
                  - cut_b / fps)) < 0.35, True)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 整条 run()（假 submit，真 ffmpeg）----
    print("\n-- 整条 run()：前后延长的拼接顺序（假 submit，不调 API）--")
    import types

    real_ad = models.adapter_for(model=MID)
    # 字段和方法都要带（`specs_for` / `compile_prompt` 是绑定的方法）
    base_fields = {k: getattr(real_ad, k) for k in dir(real_ad)
                   if not k.startswith("_")}

    for direction, first_should_be in (("back", "base"), ("front", "seg")):
        tmp = Path(tempfile.mkdtemp(prefix=f"ext_run_{direction}_",
                                    dir="D:/tmp/clone_diag"))
        seen: dict = {}

        # 🩸 2026-10-29：桩少了 `ref_images` —— 生产的 `extend_submit` 统一带这一个
        #   关键字（`extend.py:318` 恒传，2.0/2.5 的真实实现都有 `ref_images=()`），
        #   桩不跟就会 `TypeError: … unexpected keyword argument 'ref_images'`，
        #   两条用例天天红。补上并把收到的值记下来，顺手断言「2.0 不带参考图」。
        def _submit(*, prompt, ref_src, seg, model, resolution, seconds,
                    with_audio, cid, ref_images=(), _t=tmp):
            seen["prompt"] = prompt
            seen["ref_images"] = list(ref_images or [])
            _mk(Path(seg), float(seconds), color="green", audio=with_audio)

        fake = types.SimpleNamespace(**base_fields)
        fake.extend_submit = _submit
        old_for = X.models.adapter_for
        old_dir = store.render_dir
        try:
            X.models.adapter_for = lambda **kw: fake  # noqa: ARG005
            def _rd(cid, rid, _t=tmp):  # noqa: ARG001
                p = _t / rid
                p.mkdir(parents=True, exist_ok=True)
                return p
            store.render_dir = _rd
            base = _mk(tmp / "base.mp4", 2.0, w=720, h=1280, color="navy")
            res = X.run(cid="__probe__", rid="r1", direction=direction,
                        seconds=4, content="她转身走进电梯", base=base,
                        model=MID, resolution="720p", with_audio=False)
            out = tmp / "r1" / "out.mp4"
            oi = scene.probe(out)
            check(f"{direction}：成片写出来了", out.exists(), True)
            check(f"{direction}：没崩（返回 kind=extend）",
                  res.get("kind"), "extend")
            check(f"{direction}：提示词进了结果",
                  "延长@视频1" in str((res.get("extend") or {}).get("prompt")), True)
            # 🩸 官方时间顺序：向后延长 = 原片在前；向前延长 = 新段在前。
            #   顺序搞反，成片就是倒着的。
            seg_first_frame = tmp / "r1" / f"extend_{direction}.mp4"
            check(f"{direction}：新段文件是 extend_{direction}.mp4",
                  seg_first_frame.exists(), True)
            # 用时长验顺序：base 2s + 新段 4s - 裁 7 帧 ≈ 5.72s
            check(f"{direction}：总时长 ≈ 两段和 - 裁掉的接缝帧",
                  abs(float(oi["duration"]) - (2.0 + 4.0 - 7 / 25.0)) < 0.4, True)

            # 🩸 光验时长验不出"顺序反了"（反了时长一样）。抽首帧看颜色：
            #   base 是 navy（BGR 128,0,0）、新段是 green（BGR 0,128,0）。
            #   向后延长 → 首帧该是 navy；向前延长 → 首帧该是 green。
            def _first_rgb(video: Path) -> tuple:
                from app.services import media as _md
                png = video.with_suffix(".png")
                import subprocess as _sp
                _sp.run([_md.ffmpeg_path(), "-hide_banner", "-loglevel", "error",
                         "-y", "-ss", "0.2", "-i", str(video), "-frames:v", "1",
                         str(png)], capture_output=True)
                import cv2
                img = cv2.imread(str(png))
                return tuple(int(x) for x in img[img.shape[0] // 2,
                                                 img.shape[1] // 2])

            bgr = _first_rgb(out)
            want_navy = (direction == "back")
            is_navy = bgr[0] > bgr[1]        # 蓝分量占优 = navy
            check(f"{direction}：首帧是"
                  f"{'原片（向后延长 = 原片在前）' if want_navy else '新段（向前延长 = 新段在前）'}"
                  f"（实测 BGR {bgr}）", is_navy, want_navy)
        except Exception as e:  # noqa: BLE001
            check(f"{direction}：run() 不崩", f"{type(e).__name__}: {e}", "")
        finally:
            X.models.adapter_for = old_for
            store.render_dir = old_dir
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n用例 {_n}，有问题 {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
