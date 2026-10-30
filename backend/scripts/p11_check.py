"""P11 验收：视频延长（B5 第二期）。

零模型调用、不花钱；只用本机 ffmpeg 造两段纯色片验拼接。每条都按官方出处判：
  A. 请求体    —— 2.5 指南「有锁定：编辑/首尾帧/延长」：ratio=adaptive、时长用户定、
                  content.role=reference_video；触发词向前/向后延长
  B. 提示词    —— 2.0 指南「延长视频」句式「向后延长<视频N>，生成…」，
                  并明确**别写「参考<视频N>」**（会被判成参考任务）
  C. 接缝      —— 2.0 指南「延长视频衔接处跳变」：前段末删 6 帧、后段头删 1 帧；
                  2.5 指南明确拼接处无痕迹 → 不裁
  D. 拼接      —— 向前/向后顺序不能搞反；缺音轨的一段补静音，别整条没声
  E. 界面契约  —— 入口在结果页、进请求体、进度页认延长阶段、可选型号/清晰度
  F. 参考视频像素下限 —— 火山 r2v 的 [407696, 8295044]，不够就等比放大
  G. 型号 x 清晰度 —— 各型号只收自己的档位（2.0 极速/Mini ≤720p、H3 768P/2K）
  H. H3 续写 —— `[video continuation]` 六段式、<Video 1> 指代、参考片截到 ≤15s

跑法：python scripts/p11_check.py --model volc20|volc25|h3
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import ark, extend, media, model_specs, models, scene  # noqa: E402

FRONT = ROOT.parent / "frontend" / "app" / "src"
API = ROOT / "app" / "api" / "clone.py"
JOBS = ROOT / "app" / "services" / "clone_jobs.py"

rows: list[tuple[str, bool, str]] = []

# 🚦 必须点名型号（2026-10-26）：一轮只跑一家。空串 = 还没解析。
SEL = ""


def chk(name: str, ok, detail: str = "") -> None:
    rows.append((name, bool(ok), detail if not ok else ""))


V25 = "doubao-seedance-2-5-260628"
V20 = "doubao-seedance-2-0-260128"
H3 = "MiniMax-H3"
H3MAX = "MiniMax-H3-Max"


def body(**kw) -> dict:
    base = dict(prompt="向后延长@视频1，生成她转身走出门", video_url="https://x/a.mp4")
    base.update(kw)
    return ark.extend_body(**base)


def roles(b: dict) -> list[str]:
    return [c.get("role") or c.get("type") for c in b["content"]]


# ---------------------------------------------------------------------------
# A. 请求体


def phase_a() -> None:
    if SEL == "volc25":
        b = body(model=V25, duration=5)
        chk("A1 2.5 延长：ratio 必须 adaptive（比例锁待延长视频）",
            b["ratio"] == "adaptive", b.get("ratio"))
        chk("A2 2.5 延长：时长由用户定（传 12 就是 12，不像编辑只能 -1）",
            body(model=V25, duration=12)["duration"] == 12,
            str(body(model=V25, duration=12)["duration"]))
        chk("A3 参考视频带 role=reference_video（官方触发条件）",
            "reference_video" in roles(b), str(roles(b)))
        chk("A4 提示词在 content 里，且只有一个 text",
            sum(1 for c in b["content"] if c["type"] == "text") == 1, str(roles(b)))
        chk("A5 不带 omni_reference_task_type（那是编辑/参考任务用的）",
            "omni_reference_task_type" not in b, str(list(b)))
        chk("A6 2.5 单段上限 30s：传 99 收口到 30",
            body(model=V25, duration=99)["duration"] == int(model_specs.volc(V25)["max_sec"]),
            str(body(model=V25, duration=99)["duration"]))
        chk("A7b 各型号下限也要收口：2.5 传 2s → 4s（低于下限会被模型拒）",
            body(model=V25, duration=2)["duration"] == 4,
            str(body(model=V25, duration=2)["duration"]))
    if SEL == "volc20":
        chk("A7 2.0 单段上限 15s：传 99 收口到 15",
            body(model=V20, duration=99)["duration"] == 15,
            str(body(model=V20, duration=99)["duration"]))
    chk("A8 generate_audio 透传（延长段要不要声音）",
        body()["generate_audio"] is False
        and ark.extend_body(prompt="向后延长@视频1，生成a", video_url="u",
                            generate_audio=True)["generate_audio"] is True)
    for kw, label in (({"prompt": "", "video_url": "u"}, "空提示词"),
                      ({"prompt": "向后延长@视频1，生成a", "video_url": ""}, "空视频地址")):
        try:
            ark.extend_body(**kw)
            ok, msg = False, "没有报错"
        except ark.ArkError as e:
            ok, msg = True, str(e)[:60]
        chk(f"A9 {label} → 当场拦住", ok, msg)


# ---------------------------------------------------------------------------
# B. 提示词


def phase_b() -> None:
    """延长句式是 2.0 指南的写法（`向后延长<视频N>`），只在 2.0 轮跑。"""
    if SEL != "volc20":
        return
    _p = models.adapter_for(model=V20).extend_prompt
    back = _p("back", "她转身走出门")
    front = _p("front", "她从门外走进来")
    chk("B1 向后：官方句式「向后延长@视频1，生成…」",
        back.startswith("向后延长@视频1，生成"), back)
    chk("B2 向前：官方句式「向前延长@视频1，生成…」",
        front.startswith("向前延长@视频1，生成"), front)
    chk("B3 不写「参考@视频1」/「参考视频1」（2.0 指南明令，会被判成参考任务）",
        "参考@视频1" not in back and "参考视频1" not in back, back)
    chk("B4 内容两头的空白去掉",
        _p("back", "  她转身  ").endswith("生成她转身"),
        _p("back", "  她转身  "))


# ---------------------------------------------------------------------------
# C/D. 接缝与拼接（本机 ffmpeg，零模型）


def _mk(path: Path, color: str, seconds: float, *, audio: bool) -> None:
    ff = media.ffmpeg_path()
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d={seconds}:r=25"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError(f"造样本失败: {(proc.stderr or '')[-200:]}")


def _first_rgb(path: Path) -> tuple[int, int, int]:
    ff = media.ffmpeg_path()
    proc = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-vf", "select=eq(n\\,0)", "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    raw = proc.stdout or b""
    if len(raw) < 320 * 240 * 3:
        raise RuntimeError("取首帧失败")
    i = (120 * 320 + 160) * 3          # 中心像素
    return raw[i], raw[i + 1], raw[i + 2]


def phase_cd(tmp: Path) -> None:
    red, blue = tmp / "red.mp4", tmp / "blue.mp4"
    _mk(red, "red", 2.0, audio=False)
    _mk(blue, "blue", 2.0, audio=False)
    d_red = float(scene.probe(red)["duration"])
    d_blue = float(scene.probe(blue)["duration"])

    if SEL == "volc20":
        chk("C1 2.0 系列接缝：前段末删 6 帧、后段头删 1 帧（官方原话）",
            extend.seam_frames(V20) == (6, 1), str(extend.seam_frames(V20)))
        out20 = tmp / "back_20.mp4"
        meta = extend.stitch(red, blue, out20, model=V20)
        got = float(scene.probe(out20)["duration"])
        want = d_red + d_blue - 7 / 25.0
        chk("C3 2.0 拼接后总时长 = 两段相加 - 7 帧（6+1）",
            abs(got - want) < 0.15 and meta["cut_prev_frames"] == 6,
            f"got={got:.3f} want={want:.3f}")
        chk("C4 2.0 拼接结果带音轨（两段都没声 → 补静音，不是整条丢音轨）",
            scene.probe(out20)["has_audio"] is True, str(scene.probe(out20)))
        r, g, b = _first_rgb(out20)
        chk("D1 向后延长：成片开头还是原片（红在前）",
            r > 150 and b < 100, f"rgb={(r, g, b)}")
    elif SEL == "volc25":
        chk("C2 2.5 拼接处官方说无痕迹 → 不裁帧",
            extend.seam_frames(V25) == (0, 0), str(extend.seam_frames(V25)))
        out25 = tmp / "back_25.mp4"
        extend.stitch(red, blue, out25, model=V25)
        got25 = float(scene.probe(out25)["duration"])
        chk("C5 2.5 拼接后总时长 = 两段相加（不裁）",
            abs(got25 - (d_red + d_blue)) < 0.15,
            f"got={got25:.3f} want={d_red + d_blue:.3f}")
        front_out = tmp / "front.mp4"
        extend.stitch(blue, red, front_out, model=V25)   # run() 里 front 时新段在前
        r2, g2, b2 = _first_rgb(front_out)
        chk("D2 向前延长：成片开头是新段（蓝在前）",
            b2 > 150 and r2 < 100, f"rgb={(r2, g2, b2)}")

    src = (ROOT / "app" / "services" / "extend.py").read_text(encoding="utf-8")
    chk("D3 run() 里 front 的拼接顺序是「新段 + 原片」，back 是「原片 + 新段」",
        'if direction == "front":\n        seam = stitch(seg, base' in src,
        "顺序写反会把片子接反")


# ---------------------------------------------------------------------------
# E. 界面 / 接口契约（静态检查，零调用）


def phase_e() -> None:
    api = API.read_text(encoding="utf-8")
    jobs = JOBS.read_text(encoding="utf-8")
    result = (FRONT / "pages" / "clone" / "result.vue").read_text(encoding="utf-8")
    prog = (FRONT / "pages" / "clone" / "progress.vue").read_text(encoding="utf-8")
    req = (FRONT / "api" / "request.js").read_text(encoding="utf-8")

    chk("E1 接口 POST /clone/{cid}/extend 存在", '@router.post("/clone/{cid}/extend")' in api)
    chk("E2 请求体四个字段齐全（方向/秒数/内容/基于哪一版）",
        all(k in api for k in ("direction:", "seconds:", "content:", "base_render_id:")))
    # 🩸 判据要写「效果」不写「文件里有没有这句话」：以前这里 grep
    #    `known = {mid for …}`，代码一重构就假红，而实际校验是对的。
    from app.api import clone as _api
    chk("E3 型号在册才收：认得的放行、乱填的拒、跨通道点名也拒",
        _api.regen_model_error("乱填的型号") == "未知的模型"
        and _api.regen_model_error(V25) == ""
        and _api.regen_model_error(H3) == ""
        and _api.regen_model_error(H3, "volc") == "所选模型不属于该通道"
        and _api.regen_model_error(H3, "auto") == "",
        f'{_api.regen_model_error("乱填的型号")} | '
        f'{_api.regen_model_error(V25)} | {_api.regen_model_error(H3, "volc")}')
    chk("E4 后台任务 submit_extend + 执行体都在",
        "def submit_extend" in jobs and "def _extend(" in jobs)
    # 🩸 2026-10-28：延长**从前端下架**（结果页入口、cloneExtend 封装、
    #   型号/清晰度面板一起下线）。原 E5/E6/E9/E11/E12 五条还在要求这些入口，
    #   与 `p15_check.py:341` 的 S8「结果页**没有**延长入口」**互相矛盾** ——
    #   同一次回归里一边判红、一边判绿。下线与否由 S8 单点守，本文件不再重复判
    #   （保留后端 E4/E7/E8/E10：接口与版本识别仍在）。
    chk("E7 进度页认延长阶段（延长中 → 拼接中）",
        "kind === 'extend'" in prog and "生成延长段" in prog)
    chk("E8 版本列表能认出延长版本（kind 下发）",
        '"kind": r.get("kind") or "render"' in
        (ROOT / "app" / "services" / "clone_store.py").read_text(encoding="utf-8"))
    # （E9/E9b/E11/E12 随延长面板一起下线，见上一段的说明。）
    chk("E10 请求体字段名与后端一致（ExtendIn.model）",
        'model: str = Field("", description="型号 ID' in api
        and 'model=model_id' in api)


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# F. 参考视频像素下限（2026-10-24 实报错：836×480 被 2.5 拒单）


def phase_f(tmp: Path) -> None:
    """喂给模型的视频必须先过方舟的像素下限，否则接口 400。

    出处：接口报错原文 `the parameter video pixel count … must be greater than or
    equal to 407696 for model doubao-seedance-2-5 in r2v`；官方 API 文档
    `volc-api:333`「总像素数 [614×664=407696, 3326×2494=8295044]」同数。
    """
    # 门槛数字来自**型号自己的能力参数**（以前写死在 extend.py，现在各家自己声明）
    _c = models.adapter_for(model=V25).caps
    _lo, _hi = _c.extend_ref_min_px, _c.extend_ref_max_px
    small = tmp / "small.mp4"
    _mk(small, "red", 1.0, audio=False)
    d = scene.probe(small)
    px = int(d.get("width") or 0) * int(d.get("height") or 0)
    chk("F1 样本本身就低于下限（否则这条判据是空转）",
        px < _lo, f"{px} < {_lo}")

    out = extend.prep_ref(small, tmp / "small_ref.mp4", "back", V25)
    d2 = scene.probe(out)
    w2, h2 = int(d2.get("width") or 0), int(d2.get("height") or 0)
    chk("F2 低于下限 → 放大到达标", w2 * h2 >= _lo, f"{w2}x{h2}={w2*h2}")
    chk("F3 放大后既没超上限、也没把比例拉歪",
        w2 * h2 <= _hi
        and abs((w2 / h2) / (d["width"] / d["height"]) - 1) < 0.02,
        f"{w2}x{h2} vs {d['width']}x{d['height']}")

    big = tmp / "big.mp4"
    _mk(big, "blue", 1.0, audio=False)
    # 先把 big 放大到达标，再验"已达标就原样返回、不重编码"
    big_ok = extend.prep_ref(big, tmp / "big_ref.mp4", "back", V25)
    again = extend.prep_ref(big_ok, tmp / "big_ref2.mp4", "back", V25)
    chk("F4 已达标 → 原样返回（不白掉一遍画质）",
        again == big_ok and not (tmp / "big_ref2.mp4").exists(), str(again))


# ---------------------------------------------------------------------------
# G. 型号 x 清晰度（开放选型后新出的坑，纯计算零调用）


def phase_g() -> None:
    """选了 2.0 极速 / Mini 以后，不能把 1080p 塞过去。

    这两款官方只收 480p/720p；清晰度原本是"跟着待延长视频短边走"算的，
    1080p 的片子一路自动算出 1080p，换型号后就变成 400 拒单。
    """
    mini = "doubao-seedance-2-0-mini-260615"
    if SEL == "volc20":
        chk("G0 判据非空转：Mini 的档位里确实没有 1080p",
            "1080p" not in model_specs.volc(mini)["resolutions"],
            str(model_specs.volc(mini)["resolutions"]))
        chk("G2 2.0 Mini + 1080p 原片 → 收到它自己的默认档",
            extend.pick_resolution(mini, 1080, 1920)
            == model_specs.volc(mini)["default_resolution"],
            extend.pick_resolution(mini, 1080, 1920))
        chk("G3 显式要的档位型号不收（Mini + 1080p）→ 同样收到默认档",
            extend.pick_resolution(mini, 1080, 1920, "1080p") == "720p",
            extend.pick_resolution(mini, 1080, 1920, "1080p"))
    elif SEL == "volc25":
        chk("G1 2.5 + 1080p 竖屏原片 → 仍然是 1080p（不无缘无故降档）",
            extend.pick_resolution(V25, 1080, 1920) == "1080p",
            extend.pick_resolution(V25, 1080, 1920))
        chk("G4 型号收的档位就照用（2.5 + 显式 480p）",
            extend.pick_resolution(V25, 1080, 1920, "480p") == "480p",
            extend.pick_resolution(V25, 1080, 1920, "480p"))
        chk("G5 矮片子按短边判（2.5 + 848x480 → 720p，不是 1080p）",
            extend.pick_resolution(V25, 848, 480) == "720p",
            extend.pick_resolution(V25, 848, 480))
    else:
        # H3 的档位是 768P / 2K（H3-Max 反过来没有 2K）—— 火山的 1080p 它不认
        chk("G6 H3 + 1080p 原片 → 落它自己的默认档 768P",
            extend.pick_resolution(H3, 1080, 1920) == "768P",
            extend.pick_resolution(H3, 1080, 1920))
        chk("G7 H3 + 明确选 2K → 照用",
            extend.pick_resolution(H3, 1080, 1920, "2K") == "2K",
            extend.pick_resolution(H3, 1080, 1920, "2K"))
        chk("G8 H3-Max 不支持 2K → 落它的默认档",
            extend.pick_resolution(H3MAX, 1080, 1920, "2K")
            == model_specs.volc(H3MAX)["default_resolution"],
            extend.pick_resolution(H3MAX, 1080, 1920, "2K"))


# ---------------------------------------------------------------------------
# H. H3 续写（2026-10-24 主人「H3 也开」）

H3_SECS = ("subject_definitions:", "summary:", "retention_analysis:",
           "detailed_description:", "overall_soundscape:", "non_diegetic_music:")


def _mk_two_tone(path: Path, red_sec: float, blue_sec: float) -> None:
    """前段红、后段蓝：用来验"截的是哪一端"（红 15s + 蓝 5s，总共 20s）。"""
    ff = media.ffmpeg_path()
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", f"color=c=red:s=320x240:d={red_sec}:r=25",
           "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={blue_sec}:r=25",
           "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError(f"造双色样本失败: {(proc.stderr or '')[-200:]}")


def _last_rgb(path: Path) -> tuple[int, int, int]:
    """取最后一帧的中心像素（看"截到哪里结束"）。"""
    ff = media.ffmpeg_path()
    proc = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-sseof", "-0.5", "-i", str(path),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    raw = proc.stdout or b""
    frame = 320 * 240 * 3
    if len(raw) < frame:
        raise RuntimeError("取末帧失败")
    raw = raw[-frame:]
    i = (120 * 320 + 160) * 3
    return raw[i], raw[i + 1], raw[i + 2]


def phase_h(tmp: Path) -> None:
    """H3 续写（`[video continuation]` 六段式）：只在 H3 轮跑。"""
    if SEL != "h3":
        return
    _p = models.adapter_for(model=H3).extend_prompt
    back = _p("back", "她转身走进电梯")
    front = _p("front", "她从门外走进来")

    chk("H1 H3 续写用 `[video continuation]` 任务类型（官方 ref-en:137）",
        "[video continuation]" in back and "[video continuation]" in front, back[:80])
    chk("H2 六段齐全、顺序对",
        all(s in back for s in H3_SECS)
        and [back.index(s) for s in H3_SECS] == sorted(back.index(s) for s in H3_SECS))
    chk("H3 源片指代用 `<Video 1>`，且写成续写起点（ref-en:32/81）",
        "<Video 1> is the source video being continued" in back,
        back.splitlines()[1] if len(back.splitlines()) > 1 else "")
    chk("H4 不套火山句式（H3 没独立延长接口，靠任务类型声明）",
        "向后延长@" not in back and "向前延长@" not in back and "@视频1" not in back)
    chk("H5 不凭空造 <Picture>/<Subject> 标号（这次只有视频，没有图）",
        "<Picture" not in back and "<Subject" not in back)
    chk("H6 向前延写的是「接到 <Video 1> 开头」（方向不能反）",
        "ends where <Video 1> begins" in front
        and "immediately before <Video 1>" in front)
    chk("H7 用户写的内容原样进提示词",
        "她转身走进电梯" in back and "她从门外走进来" in front)
    chk("H8 不写配乐（只要环境音和物理音）",
        back.rstrip().endswith("N/A"))

    chk("H9 H3 参考片只收 15s（官方输入限制）",
        models.adapter_for(model=H3).caps.extend_ref_max_sec == 15.0,
        str(models.adapter_for(model=H3).caps.extend_ref_max_sec))
    chk("H10 H3 不按火山裁接缝（官方没给计帧规则 → 不裁）",
        extend.seam_frames(H3) == (0, 0), str(extend.seam_frames(H3)))
    chk("H11 火山 2.0 的 6+1 帧规则没被带歪",
        extend.seam_frames(V20) == (6, 1), str(extend.seam_frames(V20)))

    long_one = tmp / "long.mp4"
    _mk_two_tone(long_one, 15.0, 5.0)     # 20s：前 15s 红、后 5s 蓝
    back_ref = extend.prep_ref(long_one, tmp / "h3_back.mp4", "back", H3)
    front_ref = extend.prep_ref(long_one, tmp / "h3_front.mp4", "front", H3)
    d_back = float(scene.probe(back_ref)["duration"])
    d_front = float(scene.probe(front_ref)["duration"])
    chk("H12 超 15s 的源片：截到 15s",
        abs(d_back - 15.0) < 0.3 and abs(d_front - 15.0) < 0.3,
        f"back={d_back:.2f} front={d_front:.2f}")
    # 源片 20s（红 0–15、蓝 15–20）：
    #   向后延 = 5–20s → 末帧是蓝；向前延 = 0–15s → 末帧仍是红。
    #   两个都从红开始，只看首帧分不出来，所以判**末帧**。
    rb, _, bb = _last_rgb(back_ref)
    rf, _, bf = _last_rgb(front_ref)
    chk("H13 向后延截的是**结尾**（末帧已进后段：蓝）",
        bb > 150 and rb < 100, f"rgb={(rb, bb)}")
    chk("H14 向前延截的是**开头**（末帧仍在片头段：红）",
        rf > 150 and bf < 100, f"rgb={(rf, bf)}")

    short_one = tmp / "short.mp4"
    _mk(short_one, "red", 8.0, audio=False)
    same = extend.prep_ref(short_one, tmp / "h3_short.mp4", "back", H3)
    chk("H15 已经 ≤15s 就原样送（不白掉一遍画质）",
        same == short_one and not (tmp / "h3_short.mp4").exists(), str(same))


def main() -> int:
    global SEL
    from _model_gate import sel_or_exit
    SEL = sel_or_exit()

    tmp = Path(tempfile.mkdtemp(prefix="p11_", dir="D:/tmp"))
    try:
        phase_a()
        phase_b()
        phase_cd(tmp)
        phase_e()
        phase_f(tmp)
        phase_g()
        phase_h(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok = sum(1 for _, v, _ in rows if v)
    for name, v, detail in rows:
        print(f"  {'ok  ' if v else 'FAIL'} {name}" + (f"  [{detail[:180]}]" if detail else ""))
    print(f"\n{ok}/{len(rows)} 通过（零模型调用）")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
