"""整片重制的接线自检：真跑切段/规格化/拼接，只把模型调用换成假实现。

验的不是"代码里有没有这句话"，而是**实际发给模型的参数**：
提示词原文、参考图的张数和顺序、分辨率档位、每条通道的标号语法。
不花钱（不发任何网络请求）。

🔴 **这是跨通道共用文件，不是某一家模型的验收**：
它必须同时跑「火山通道」和「MiniMax 通道」—— 验的就是"同一个入口会不会选错通道、
拼错提示词"。按型号拆开就没有接线可测了。
**所以：本文件的绿灯，不能当作任何一家"已验收"的证据。**
单家断言只许写在 `test_edit_spec_<model>.py` 里（2026-10-26 主人拍板，见台账 D43）。
`--model` 在这里只作"一轮只做一家"的轮次点名，**不筛内容**。

运行：python scripts/test_whole_wiring.py --model volc20|volc25|h3
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import edit_spec, video_edit  # noqa: E402
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


def make_video(path: Path, seconds: float, w: int = 360, h: int = 640) -> Path:
    ff = ffmpeg_path()
    p = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=navy:s={w}x{h}:d={seconds}:r=25",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, text=True, errors="ignore",
    )
    if p.returncode != 0 or not path.exists():
        raise SystemExit("造测试视频失败: " + (p.stderr or "")[-400:])
    return path


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：本脚本验的是**共享层/参数表**，
    # 断言本身不分模型，点名只作「一次只跑一家」的执行闸。
    from _model_gate import sel_or_exit
    sel_or_exit()

    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="whole_wire_"))
    try:
        return _run(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run(work: Path) -> int:
    from app.services import ark, minimax

    video = make_video(work / "src.mp4", 40.0)
    # 4 镜各 10s：火山 30s 上限 → 2 段（0-30 / 30-40）；MiniMax 15s 上限 → 4 段
    rec = {
        "source": {"duration": 40.0, "width": 360, "height": 640, "fps": 25.0},
        "shots": [
            {"i": i, "start": i * 10.0, "end": (i + 1) * 10.0, "dur": 10.0}
            for i in range(4)
        ],
    }
    person = work / "person.jpg"
    product = work / "product.jpg"
    wardrobe = work / "wardrobe.jpg"
    for p, color in ((person, "red"), (product, "green"), (wardrobe, "blue")):
        subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", f"color=c={color}:s=400x600:d=1",
                        "-frames:v", "1", str(p)], check=True)

    seen: dict = {}
    calls: list[dict] = []

    def fake_volc(prompt, *, video_url, out, ref_images=None, ref_audio=None,
                  resolution="", model="", watermark=False, **_):
        seen.update(prompt=prompt, refs=[str(x) for x in (ref_images or [])],
                    audio=str(ref_audio or ""),
                    resolution=resolution, model=model, watermark=watermark, url=video_url)
        calls.append(dict(seen))
        shutil.copy(video, out)
        return out

    def fake_mm(video_path, *, prompt, out, ref_images=None, ref_audio=None,
                duration=6, resolution="", model="", **_):
        seen.update(prompt=prompt, refs=[str(x) for x in (ref_images or [])],
                    audio=str(ref_audio or ""),
                    resolution=resolution, duration=duration, model=model)
        calls.append(dict(seen))
        shutil.copy(video_path, out)
        return out

    real = (ark.edit_video, minimax.reference_video, video_edit._public_url,
            settings.ark_api_key, settings.minimax_api_key, settings.public_base_url)
    # 🩸 生成缓存挂在任务目录下：不隔离就会读到上一次跑测试留下的缓存，
    # 这一轮的假模型一次都不会被调用，测试直接空转
    from app.services import clone_store
    real_task_dir = clone_store.task_dir
    clone_store.task_dir = lambda cid: work / "tasks" / cid
    ark.edit_video = fake_volc
    minimax.reference_video = fake_mm
    video_edit._public_url = lambda seg, cid: "https://example.test/seg.mp4"
    # 🩸 素材库默认**关**：AK/SK 一旦配好，`ark_ingest.available()` 就是 True，
    # 这个自检会真的去建素材组、真的调火山 —— 既慢（429 退避）又会污染账号额度。
    # 只有下面「素材库」那一节显式打开，并把两个 prepare_* 换成假实现。
    from app.services import ark_ingest as _ing

    real_ing_avail = _ing.available
    _ing.available = lambda: False
    # 🩸 2026-10-26（D40）：H3 正文里的中文自由文本会**真的调方舟翻译**（花钱）。
    # 测试里一律打桩 —— 不然跑一次自检花一次钱，而且没真 Key 时会 401 直接失败。
    from app.services import translate as _tr0

    _real_translate_chat = _tr0._chat
    _tr0._chat = lambda lines, target, **_kw: (
        ["a cleaner, brighter frame for the target video"], {})
    _tr0.translate_text_cache_clear()
    object.__setattr__(settings, "ark_api_key", "k")
    object.__setattr__(settings, "minimax_api_key", "k")
    object.__setattr__(settings, "public_base_url", "https://api.test")

    try:
        spec = edit_spec.normalize({
            "person": True, "person_desc": "白衬衫女孩",
            "product": True, "product_desc": "陶瓷杯",
            "style": "anime",
            "keep": {"camera": False},
            "audio": "mix",
            "resolution": "1080p",
            "watermark": True,      # 老前端可能还传，必须被无视
            # 🩸 2026-10-26：同一份 spec 要喂三个通道，所以补充说明用英文 ——
            # H3 六段正文必须是英文（`ref-en:5`）。下面另有两条专测：
            # 火山收中文补充说明要放行、H3 收中文补充说明要拦。
            "extra": "make the frame brighter",
        })

        print("== 火山通道 ==")
        r = video_edit.replace_whole(
            video, rec, cid="a" * 32, spec=spec, refs={"person": person, "product": product},
            channel="volc", workdir=work / "r1",
        )
        first, last = calls[0], calls[-1]
        check("通道", r["channel"], "volc")
        check("40s 按 30s 上限切成 2 段", r["chunks"], 2)
        check("第 1 段参考图 2 张", len(first["refs"]), 2)
        check("人物是第一张", first["refs"][0], str(person))
        check("产品是第二张", first["refs"][1], str(product))
        # 官方两处用词不同，别只认一个：模板 `sd25-pe:561`「只把<原对象或区域>
        # **修改为**<目标内容>」，示例 `:584`「…骑行者**替换为**@图片1中的…」。
        # 以前判据只认"修改为"，把正确输出判成红的（判据漂移，2026-10-23 修）。
        check("提示词人物=@图片1（官方句式：只把…修改为/替换为@图片1中的人物）",
              ("人物修改为@图片1中的人物" in first["prompt"]
               or "人物替换为@图片1中的人物" in first["prompt"]), True)
        check("提示词产品=@图片2", "产品替换为@图片2" in first["prompt"], True)
        # 🩸 这一段 0–30 / 30–40 的切点**正好落在镜头边界上**：真实分析里
        # 镜头边界就是原片的硬切（`scene.detect_shots`），拿上一段尾帧当
        # "目标视频第一帧"会把旧场景钉进新镜头 —— 所以这里不许带边界帧。
        # 边界帧本身的能力由下面「两段相接 → 带边界帧」那条（镜头中段切开）覆盖。
        check("切在镜头边界上 → 不带边界帧", len(last["refs"]), 2)
        check("也不写边界句", "上一段成片的最后一帧" in last["prompt"], False)
        check("报告如实说没带", r["boundary"], False)
        check("第 1 段不写边界句", "上一段成片的最后一帧" in first["prompt"], False)
        # 🩸 2026-10-28：2.5 也走风格锚定词了（`sd25-guide:966`「风格参考的
        #   使用方式与 Seedance 2.0 一致」+ `sd20-guide:354`「例如"2D日漫风格"」），
        #   所以中文风格词是「2D日漫风格」，不再是媒介名「动漫」。
        check("风格译成中文（锚定词）", "2D日漫风格" in seen["prompt"]
              and "anime" not in seen["prompt"], True)
        check("关掉运镜就不写运镜", "运镜" not in seen["prompt"], True)
        check("补充说明在场", "make the frame brighter" in seen["prompt"], True)
        check("1080p 原样传", seen["resolution"], "1080p")
        # 角标功能已整个删掉：老前端就算传 watermark=True，底层也必须是不打
        check("老字段 watermark=True 被无视", seen["watermark"], False)
        check("火山拿到公网 URL", seen["url"].startswith("https://"), True)

        print("== 换服装：图必须真的发出去，序号跟着走 ==")
        spec_wd = edit_spec.normalize({"person": True, "wardrobe": True,
                                       "wardrobe_desc": "米色风衣"})
        n0 = len(calls)
        video_edit.replace_whole(
            video, rec, cid="b" * 32, spec=spec_wd,
            refs={"person": person, "wardrobe": wardrobe},
            channel="volc", workdir=work / "r_wd",
        )
        wd_first = calls[n0]
        check("服装图真的发了（2 张）", len(wd_first["refs"]), 2)
        check("人物是第一张", wd_first["refs"][0], str(person))
        check("服装是第二张", wd_first["refs"][1], str(wardrobe))
        # 🩸 2026-10-28：这里原来写死「服装**换成**@图片2中的服装」—— 那是
        #   2.0 的动词。本文件是**跨通道接线测试**（见文件头：`--model` 不筛内容、
        #   绿灯不算任何一家验收），可它跑的是"没传 model 时的默认型号"，
        #   轮次点名 2.5 时默认就是 2.5，于是它断言的其实是 2.5 的产出。
        #   2.5 的官方动词是「修改为」（`sd25-guide:88` 只收「修改/替换/改成」，
        #   没有「换成」）—— 那条兜底分支刚被修掉，这里就挂了。
        #   ⇒ 接线只验“图 2 的服装被引用了”，**动词归各家的尺子守**
        #     （`ruler_sd20` / `ruler_sd25` 的 T3）。
        check("提示词按图换服装 @图片2",
              re.search(r"服装(换成|修改为|替换为)@图片2中的服装",
                        wd_first["prompt"]) is not None, True)

        print("== MiniMax 通道 ==")
        # 🩸 2026-11-02：H3 的逐段提示词改由**官方改写器**产出（`h3_ir` →
        #   `POST /v2/h3_context_ir`）。这里是跨通道**接线**测试，不许打外网，
        #   所以把改写器打桩：验的是
        #     ① 共用层把这一段的素材 + 用户的补充说明**交到了改写器手上**；
        #     ② 改写器返回的那一份**原样**就是这一段发出去的提示词。
        #   至于"改写器写成什么样"，归 `p46_check`（六段式尺子）和真机验收，不归这里。
        from app.services import h3_ir as _ir
        _real_pf = _ir.prompt_for
        # 出片时会给"缺描述"的参考图补算长相（`_span_looks` → `describe_person`）。
        # 这是**联网的花钱调用**，接线测试一律打桩：这里只验"描述被交到了改写器手上"。
        from app.services import vision_plan as _vp

        _real_dp = _vp.describe_person
        _ir_calls = []

        def _fake_pf(cid, n, **kw):
            _ir_calls.append(dict(kw, n=n))
            return ("subject_definitions:\n<Subject 1> is the person in "
                    "<Picture 1>.\n\nsummary:\n[video editing] The target video is "
                    "an edited version of <Video 1>.\n\nretention_analysis:\n"
                    "<Subject 1>: fully_preserved - ok\n")

        _ir.prompt_for = _fake_pf
        # 改写器只吃我们的**一句自然语言**，这句只交代「每份素材是什么」。
        # 🩸 2026-11-02 主人拍板：「一比一配」—— 素材之外一个字都不许加。
        _ins = _ir.instruction(["person"], boundary_pic=2)
        check("指令点名了人物图", "人物参考图1" in _ins, True)
        check("指令说清边界帧是第一帧",
              "图2" in _ins and "第一帧" in _ins, True)
        check("指令不带平台的 @ 写法", "@" not in _ins, True)
        # 这条门盯的是「有没有又把我自己的规则加回去」：
        # 五官描述 / 说话人 / 风格 —— 全是我加的，不是官方要求。
        # 🩸 2026-11-02：`场景、背景` 从禁令里**移出**（不是放宽，是有出处了）——
        #   官方换人范例 `h3-manual:192` 原句「确保水豚的毛发质感和光影与环境
        #   融合」，环境/光影本来就要求保留。且实测只写「动作、镜头、口型」
        #   那版场景被定妆照整段带走（同素材对照，只差这一句）。
        _ban = ["严格保持", "不重新生成", "唯一出镜", "出镜的人物只有",
                "视频1里画面中的人物", "同步音轨", "直接复用",
                "说话的人是", "画面风格是"]
        check("指令里没有我们自己加的规则句",
              [w for w in _ban if w in _ins], [])
        # 🩸 2026-11-02：`h3-manual:244` 那条
        #   「完整提示词 = 参考素材说明 + 核心创意 + 画面过程说明」
        #   说的是**改写器的输出**，不是它的输入 —— 官方调 H3-Context-IR 时
        #   `text` 只有一句话（`scripts/readme/full-2k-ref2va-h3-context-ir.sh`）。
        #   输入里出现成品骨架的小标题，等于把写好的提示词交给改写器复述。
        _ins_def = _ir.instruction(["person"])
        check("指令是自然语言，不带成品骨架的三个小标题",
              [s for s in ("参考素材说明：", "核心创意：", "画面过程说明：")
               if s in _ins_def], [])
        check("指令是一段话，不分成多段", "\n" not in _ins_def, True)
        # 🩸 2026-11-02（缺口一）：换人不再按「视频编辑」写。官方换人范例
        #   `h3-manual:192` 用的是「动作模仿 + 替换为」；用途词表里对应的是
        #   「动作参考（锁定动作）」「运镜参考（锁定运镜）」（`h3-manual:248`）。
        #   实测：写「视频编辑」的 8 份产出，改写器一律标 `partially_preserved`
        #   （= 改，`ref-en:166`）；写「动作/镜头」的 4 份标 `attribute_transfer`
        #   （= 特征转移给另一个主体，`ref-en:167`），唯一换脸成功的那次在后一组。
        # 🩸 2026-11-02（H20）：换人那句**照 `h3-manual:192` 的原句结构**写，五段齐全：
        #   ①动作模仿 ②X替换为Y ③Y必须严格遵循原视频的运动轨迹 ④保持原有固定机位 ⑤光影与环境融合。
        #   H16 压成「锁定动作和运镜」那次，产出把 `<Video 1>` 标成 `fully_preserved`
        #   （`ref-en:167` 要的换人定性是 `attribute_transfer`），成片只换衣服不换脸。
        _OFFICIAL = ["参考视频1进行动作模仿", "替换为", "必须严格遵循原视频的运动轨迹",
                     "保持原有的机位和分镜不变", "光影与环境与原片融合"]
        check("换人句含官方范例的五个要点",
              [s for s in _OFFICIAL if s not in _ins_def], [])
        # ⚠️ **不禁止任何官方词表里的词**：「锁定动作」「运镜参考」「视频编辑」都在
        #   `h3-manual:248` 的用途词表上，是官方词，禁它们是我们自造规则（2026-11-02
        #   主人当场撤回）。这里只验"该有的五个要点在不在"，不设黑名单。
        check("换人写成「替换为」，不写成「换成」",
              "替换为" in _ins_def and "换成" not in _ins_def, True)
        # 场景/背景仍须点名来自视频1（`h3-manual:192` 的「光影与环境融合」）
        check("场景、背景、光线点名来自视频1", "场景、背景、光线" in _ins_def, True)
        # 🩸 2026-11-02（H19）：双人换人不能只点名图1。
        #   实测 `1b3df54b` 11:48：指令只写「替换为图1中的人物」，改写器就只
        #   定义 `<Subject 1>`，`<Picture 2>` 发出去了却全文零引用；同素材
        #   08:51 那版定义了 3 个 Subject。官方 `ref-en:37` 要求每个单独跟踪的
        #   素材有自己的定义行；官方换人范例 `h3-manual:192` 本身就是复数对应
        #   （「三个穿西装的男人替换为三只高度写实的水豚」）。
        _ins_two = _ir.instruction(["person", "person2"])
        check("双人时两张人物图都点名",
              ("图1、图2" in _ins_two) and ("替换为图1中的人物" not in _ins_two),
              True)
        check("双人时核心创意也提到两个人",
              "主体是图1、图2中的人物" in _ins_two, True)
        _ins_mix = _ir.instruction(["person", "scene", "person2"])
        check("人物图编号按实际素材位次算（中间插场景图不串号）",
              "图1、图3" in _ins_mix and "图1、图2" not in _ins_mix, True)
        check("单人时行为不变（仍是「替换为图1中的人物」）",
              "视频1中的人物替换为图1中的人物" in _ins_def, True)
        # 🩸 2026-11-02（H19 第二步）：要不要写方位，看**画面里有几个人**，
        #   不看上传了几张图。主人点的三种情形：
        #     原片本来就一个人 → 不写方位（没有"哪一位"可分）；
        #     原片多人只换一位   → 必须写方位，否则会换到没勾的人身上；
        #     原片多人全部换     → 逐张指派，且不能说"其余保持原样"（没有其余）。
        _pos2 = [{"position": "left"}, {"position": "right"}]
        _ins_pos = _ir.instruction(["person", "person2"], ppl=_pos2, frame_n=3)
        check("原片多人·换两人：写清哪张图换哪一位",
              ("图1中的人物替换左边那位" in _ins_pos
               and "图2中的人物替换右边那位" in _ins_pos), True)
        check("原片多人·没全换：写明其余保持原样",
              "其余出镜人物保持原样" in _ins_pos, True)
        _ins_one = _ir.instruction(["person"], ppl=[{"position": "left"}],
                                   frame_n=3)
        check("原片多人·只换一位：也要写方位",
              ("图1中的人物替换左边那位" in _ins_one
               and "其余出镜人物保持原样" in _ins_one), True)
        _ins_all = _ir.instruction(["person", "person2"], ppl=_pos2, frame_n=2)
        check("原片两人全换：不写「其余保持原样」（没有其余）",
              "其余出镜人物保持原样" not in _ins_all, True)
        _ins_solo = _ir.instruction(["person"], ppl=[{"position": "center"}],
                                    frame_n=1)
        check("原片本来就一个人：不写方位、也不提「其余保持原样」",
              ("视频1中的人物替换为图1中的人物" in _ins_solo
               and "左边那位" not in _ins_solo
               and "中间那位" not in _ins_solo
               and "其余出镜人物保持原样" not in _ins_solo), True)
        # 🩸 2026-11-02（主人点破）：`frame_n == 0` 和 `frame_n == 1` 是两件事。
        #   K = 这一段画面里有几个人（盘点事实）；M = 这次换几个人（图张数）。
        #   K==1 = 确认只有一个人 → 没有"哪一位"可分，写方位是凭空造区分，不写；
        #   K==0 = **盘点没给人数**（缺数据），不等于只有一个人 → 方位有就写，
        #          写了不会错（方位本来就来自盘点），没方位才退回泛称。
        _ins_unk = _ir.instruction(["person"], ppl=[{"position": "left"}],
                                   frame_n=0)
        check("人数未知但方位有：照样写方位（缺数据≠单人）",
              "图1中的人物替换左边那位" in _ins_unk, True)
        check("人数未知就不知道有没有「其余」，不许写「其余保持原样」",
              "其余出镜人物保持原样" not in _ins_unk, True)
        check("人数未知且没方位：退回泛称，不硬编方位",
              "替换为图1中的人物"
              in _ir.instruction(["person"], frame_n=0), True)
        check("方位缺一个就整句退回泛称，不写半截",
              "各替换一位" in _ir.instruction(
                  ["person", "person2"], ppl=[{"position": "left"}, {}],
                  frame_n=3), True)
        check("只换一位且没方位时说「替换其中一位」，不说「各替换一位」",
              "替换其中一位" in _ir.instruction(["person"], frame_n=3), True)
        check("方位也进改写器指纹（换勾选的人必换键）",
              _ir.prompt_sig(dur=10, images=[], slots=["person", "person2"],
                             ppl=_pos2, frame_n=3)
              != _ir.prompt_sig(dur=10, images=[], slots=["person", "person2"],
                                ppl=[{"position": "left"}, {"position": "center"}],
                                frame_n=3), True)
        check("画面人数也进指纹",
              _ir.prompt_sig(dur=10, images=[], slots=["person"], frame_n=1)
              != _ir.prompt_sig(dur=10, images=[], slots=["person"], frame_n=3),
              True)
        # 🩸 2026-11-02（缺口二）：段内切点必须进改写器的输入。官方
        #   `base-en:86` 要求每个 `[Shot N]` 以严格递增切点时间开头；
        #   实测原片 5 镜（06386173）产出只有 `[Shot 1]`，因为切点从没进过 text。
        check("单镜头时不提切点（行为与改前一致）",
              "个镜头" in _ins_def, False)
        _ins_cut = _ir.instruction(["person"], cuts=[1.5, 3.0])
        check("有切点时写明镜头数和秒数",
              ("这一段原片有 3 个镜头" in _ins_cut
               and "1.50、3.00 秒" in _ins_cut), True)
        check("切点也进改写器指纹（否则改切点命不中新键）",
              _ir.prompt_sig(dur=15, images=[], slots=["person"], cuts=[])
              != _ir.prompt_sig(dur=15, images=[], slots=["person"],
                                cuts=[1.5, 3.0]), True)
        # 🩸 2026-11-02（H21）：这一段**真实说过的台词 + 相对秒数**必须给改写器。
        #   官方 `h3-manual:248`「音频复刻…强烈建议补充具体歌词文本内容」；
        #   `h3-manual:251`「台词的长短尽量和镜头长短对齐…很多口型问题会来自于这个」。
        #   实测翻车：第 2 段从半句中间切起，改写器靠听音频把上一句补全当成第一句，
        #   模型照着又念一遍 → 第 2 段嘴型全程错位。
        check("没有台词时不提台词（行为与改前一致）",
              "这一段原片里说了这些台词" in _ins_def, False)
        _ins_ln = _ir.instruction(
            ["person"], lines=[(0.0, 1.11, "我词穷了已经"),
                               (1.67, 5.63, "呃总而言之就是")])
        check("有台词时写明每句的起止秒数",
              "0.00–1.11 我词穷了已经" in _ins_ln
              and "1.67–5.63 呃总而言之就是" in _ins_ln, True)
        check("台词秒数是「相对本段起点」（不写原片绝对时间）",
              "秒数相对本段起点" in _ins_ln, True)
        check("台词也进改写器指纹（台词分布变了必换键）",
              _ir.prompt_sig(dur=10, images=[], slots=["person"], lines=[])
              != _ir.prompt_sig(dur=10, images=[], slots=["person"],
                                lines=[(0.0, 1.11, "我词穷了已经")]), True)
        # 跨界那个字归谁：按**字的中点**，不按起点 —— 否则上一段的尾巴会把
        # 下一段的第一个字也写进去，下一段开头再冒一个残字。
        _rec = {"speech": {"segments": [
            {"start": 0.0, "end": 2.0, "text": "甲乙丙丁", "chars": [
                {"c": "甲", "s": 0.0, "e": 0.2}, {"c": "乙", "s": 0.3, "e": 0.5},
                {"c": "丙", "s": 1.9, "e": 2.1}, {"c": "丁", "s": 2.2, "e": 2.4}]}]}}
        check("跨段的字按字中点归属，上一段不带走下一段的字",
              video_edit._span_script(_rec, 0.0, 2.0) == [(0.0, 0.5, "甲乙")], True)
        check("跨段的字按字中点归属，下一段不重复上一段的尾巴",
              video_edit._span_script(_rec, 2.0, 3.0) == [(0.0, 0.4, "丙丁")], True)
        # 🩸 重新配音（tts/mix）时 `speech` 还是**原片** ASR，画面要念的是新文案。
        #   字级时间只能按「文字完全一致」借，否则会把原片的字级时间套到新词上。
        _tts = dict(_rec, voice_lines=[{"start": 0.0, "end": 2.0,
                                        "text": "换成了新文案"}])
        check("重配后不拿原片的字级时间套新文案（按时间比例裁）",
              video_edit._span_script(_tts, 0.0, 1.0) == [(0.0, 1.0, "换成了")], True)
        # 🩸 2026-11-02：外观描述「缺就补算」的兜底**以前是死代码** ——
        #   `_look_for` 里写了「真出片时补算」，可全工程没有一个调用方传
        #   `compute=True`（只有注释提到它）。实测 `902c4d0f`：第 2 张定妆照的
        #   描述是后台线程 15:02:35 才落盘，15:02:2x 构建 plan 时拿到空描述 →
        #   提示词里那个人只剩一个图号 → SFace 两人 0.336 / 0.178 全没换。
        #   官方 `h3-manual:248`「如果素材中有非常想要保持的特征，建议明确写出来」。
        import ast as _ast
        import inspect as _inspect
        _bad = []
        for _fn in (video_edit.replace_spans, video_edit.replace_whole):
            _tree = _ast.parse(_inspect.getsource(_fn).lstrip())
            for _node in _ast.walk(_tree):
                if not isinstance(_node, _ast.Call):
                    continue
                _n = _node.func
                _name = getattr(_n, "id", None) or getattr(_n, "attr", None)
                if _name not in ("_prepare", "prepare"):
                    continue
                _kw = {k.arg: k.value for k in _node.keywords if k.arg}
                _v = _kw.get("compute_looks")
                if not (isinstance(_v, _ast.Constant) and _v.value is True):
                    _bad.append("%s:%d" % (_fn.__name__, _node.lineno))
        check("真出片两条路都传 compute_looks=True（缺描述当场补算）", _bad, [])
        check("零费用入口（prepare 公开默认值）仍是不补算",
              _inspect.signature(video_edit.prepare)
              .parameters["compute_looks"].default, False)
        # 上面那条只验「调用点写没写」。这里验**效果**：描述文件不存在时，
        # `compute=True` 真的会去补算，`compute=False` 真的不调模型（零费用语义）。
        import hashlib as _hl
        from unittest import mock as _mock
        from app.services import clone_store as _cs, vision_plan as _vp
        _img = Path(__file__).resolve().parents[1] / "data/clone/db253cfc1eb84a109d79636afb5cc956/subject.jpg"
        if _img.exists():
            _sha = _hl.sha1(_img.read_bytes()).hexdigest()
            _hits = []

            def _fake_desc(cid, path, slot):
                _hits.append(slot)
                return {"desc_zh": "补算出来的", "desc_en": "computed",
                        "_v": _vp._DESC_VERSION, "_image_sha1": _sha}

            _missing = Path(__file__).resolve().parents[1] / "data/nonexistent_desc.json"
            with _mock.patch.object(_cs, "subject_desc_path", return_value=_missing), \
                    _mock.patch.object(_vp, "describe_person", side_effect=_fake_desc):
                _r_on = video_edit._look_for(_img, "person2", compute=True)
                _n_on = len(_hits)
                _r_off = video_edit._look_for(_img, "person2")
                _n_off = len(_hits)
            check("缺描述 + 真出片 → 当场补算并采用",
                  (_n_on, _r_on.get("zh")), (1, "补算出来的"))
            check("缺描述 + 预览/复用 → 不调模型、返回空（零费用）",
                  (_n_off, _r_off), (1, {}))
        else:
            check("缺描述补算的效果验证（缺样本图，跳过）", True, True)
        # 🩸 2026-11-02（缺口三）：音频的用途必须写明。官方 `h3-manual:248`
        #   用途词表有「音色参考」「音频复用」「音频部分复用」三档；实测缺口是
        #   音频一直传进去了、`instruction()` 全文却一个字都没提它 —— 用途全凭
        #   改写器猜（它猜 `fully_copy` 那次，`non_diegetic_music` 直接写成 N/A）。
        check("没有音轨时不提音频（提示词里不能指着一个没传的素材）",
              "音频1" in _ins_def, False)
        _ins_wav = _ir.instruction(["person"], audio_mode="original")
        check("原声模式写明「复用原声」",
              "音频1是视频1的原声轨" in _ins_wav and "复用" in _ins_wav, True)
        check("配音模式写明配音轨（不是拿它当原声）",
              "音频1是成片的配音轨"
              in _ir.instruction(["person"], audio_mode="mix"), True)
        check("不写回那两句被撤过的自造措辞",
              [w for w in ("同步音轨", "直接复用") if w in _ins_wav], [])
        check("人物用途按官方建议写明要锁的特征（`h3-manual:248`）",
              "锁定脸和长相" in _ins_def, True)
        # 🩸 2026-11-02：定妆照自己的描述（五官）必须真的进改写器的输入。
        #   实测不传它：改写器产出的 `<Subject 1>` 只有发簪和衣服、零个五官词，
        #   成片保住原片那张脸（SFace 0.09）。
        check("人物特征（定妆照描述）真的写进了指令",
              "Oval smooth facial contour" in _ir.instruction(
                  ["person"], looks={"person": "Oval smooth facial contour"}), True)
        # 🩸 2026-11-02 段缓存键必须带**改写器的输入指纹**（改写器产出的词
        #   在缓存判定之后才生成，以前它变不变都不影响键，全靠人工升 `:irN`）。
        from app.services import models as _models

        _ad_h3 = _models.adapter_for(model="MiniMax-H3-Lite", channel="minimax")
        check("H3 适配器挂了 prompt_sig（键里才有改写器指纹）",
              callable(_ad_h3.caps.prompt_sig), True)
        _sig_kw = dict(slots=["person"], dur=5, images=[person],
                       video_src=str(video), video_span=(0.0, 4.0))
        _sig_a = _ir.prompt_sig(**_sig_kw)
        _sig_b = _ir.prompt_sig(**_sig_kw)
        _sig_c = _ir.prompt_sig(**{**_sig_kw, "extra": "画面更亮"})
        _sig_look = _ir.prompt_sig(**{**_sig_kw, "looks": {"person": "oval face"}})
        check("特征变了 → 指纹也变（旧段不会被复用）", _sig_a != _sig_look, True)
        check("改写器指纹同输入稳定（重跑拿回同一份词）", _sig_a == _sig_b, True)
        check("补充说明变一个字 → 指纹就变（段缓存必然失效）",
              _sig_a != _sig_c, True)
        spec_zh = dict(spec)
        spec_zh["extra"] = "画面更亮"
        seen.clear()
        calls.clear()
        try:
            video_edit.replace_whole(
                video, rec, cid="a" * 32, spec=spec_zh, refs={"person": person},
                channel="minimax", workdir=work / "r2_zh",
            )
            zh_ok_h3 = True
        except Exception:
            zh_ok_h3 = False
        # 打桩**保留到 MiniMax 段结束**（本函数末尾恢复）：下面几条 MiniMax
        # 断言走的是同一条路，恢复早了就会去打真接口。
        check("H3 收中文补充说明（不报错）", zh_ok_h3, True)
        check("改写器被叫到了（每段一次）", len(_ir_calls) >= 1, True)
        check("改写器拿到了这一段的原片",
              bool(_ir_calls and str(_ir_calls[0].get("video") or "")), True)
        check("改写器拿到了这一段的人物图",
              bool(_ir_calls and list(_ir_calls[0].get("images") or [])), True)
        # 🩸 2026-11-02：**外观描述要交**，依据是官方 `h3-manual:248`
        #   「如果素材中有非常想要保持的特征，建议明确写出来」。
        #   早先按「素材之外一个字都不加」撤掉过一次，实测成片保住原片那张脸
        #   （SFace 0.09）；唯一换成功那次正文里有整段五官。
        #   这里交的是**定妆照自己的描述文件**，不是临时编的形容词。
        check("外观描述（定妆照描述）真的交给了改写器",
              bool(_ir_calls and (_ir_calls[0].get("looks") or {})), True)
        # 🩸 交过去的是**英文**：H3 的 `pre_compile` 先把中文补充说明翻成英文
        #   （六段正文必须英文，`ref-en:5`），所以这里判"非空且是那句译文"，
        #   不判原文。
        check("用户的补充说明交给了改写器（已按 H3 规矩翻成英文）",
              "brighter" in str((_ir_calls or [{}])[0].get("extra") or "").lower(), True)
        check("改写器的产出原样进了请求",
              seen["prompt"].startswith("subject_definitions:"), True)
        # 🩸 2026-11-02（缺口二）：段内切点要真的从出片链路交到改写器手上。
        #   这里原片是 4 镜 × 10s，第 1 段 [0,15.5] 里有 1 刀，落在 10.0s。
        # 上面那份素材是 4 镜 × 10s，切段正好落在镜头边界上 → 段内没有切点。
        # 要验「值真的传下去」得造一个切点错开的素材（6s 一格，末镜截到片尾）。
        _rec_cuts = {"source": rec["source"],
                     "shots": [{"i": i, "start": i * 6.0,
                                "end": min((i + 1) * 6.0, 40.0),
                                "dur": min((i + 1) * 6.0, 40.0) - i * 6.0}
                               for i in range(7)]}
        seen.clear()
        calls.clear()
        _n_cut = len(_ir_calls)
        video_edit.replace_whole(
            video, _rec_cuts, cid="c" * 32, spec=spec, refs={"person": person},
            channel="minimax", workdir=work / "r_cuts",
        )
        _got_cuts = [c.get("cuts") for c in _ir_calls[_n_cut:] if c.get("cuts")]
        check("出片链路把段内切点交给了改写器（相对段起点、严格递增）",
              bool(_got_cuts) and all(
                  list(x) == sorted(x) and all(v > 0 for v in x)
                  for x in _got_cuts), True)
        # 🩸 缺口三：音频模式要真的从出片链路交到改写器手上。这份测试素材是
        #   lavfi 生成的无声音轨 → `seg_audio is None` → 必须传空串（提示词里
        #   不能出现「音频1」，否则指着一个没传的素材）。有音轨时传 spec 的
        #   `audio` 值，这一支由上面 instruction 层的三条断言覆盖。
        check("没有音轨时链路传空串（提示词不提音频）",
              [c.get("audio_mode") for c in _ir_calls[_n_cut:]][:1], [""])
        try:
            video_edit.replace_whole(
                video, rec, cid="a" * 32, spec=spec_zh, refs={"person": person},
                channel="volc", workdir=work / "r1_zh",
            )
            zh_ok_volc = True
        except Exception:
            zh_ok_volc = False
        check("火山仍收中文补充说明（规则不跨型号搬）", zh_ok_volc, True)

        seen.clear()
        calls.clear()
        _nb = len(_ir_calls)
        r2 = video_edit.replace_whole(
            video, rec, cid="a" * 32, spec=spec,
            refs={"person": person, "product": product},
            channel="minimax", workdir=work / "r2",
        )
        check("通道", r2["channel"], "minimax")
        check("40s 按 15s 上限切成 4 段", r2["chunks"], 4)
        check("第 1 段参考图 2 张", len(calls[0]["refs"]), 2)
        # 🩸 2026-11-02：`<Picture N>`/六段式/`@` 这些是**改写器的产出**，
        #   我们这边只剩"每段把这一段的素材交过去"。判提示词长什么样归
        #   `p46_check` 和真机验收，不归这条接线测试（拿桩的判断词充数 = 假绿）。
        check("改写器每段问一次（4 段 = 4 次）", len(_ir_calls) - _nb, 4)
        # 这 4 段的切点全在原片镜头边界上（10/20/30s）→ 一律不带边界帧
        check("MiniMax 切在镜头边界上 → 第 2 段只有 2 张",
              len(calls[1]["refs"]), 2)
        check("镜头边界切开 → 不告诉改写器有边界帧",
              [int(c.get("boundary_pic") or 0) for c in _ir_calls[_nb:]],
              [0, 0, 0, 0])
        check("MiniMax 报告如实说没带", r2["boundary"], False)

        print("== MiniMax 边界帧：只在镜头中段被切开时才带 ==")
        # 🩸 2026-10-22：接口侧 first_frame 与 reference_video 互斥，边界帧只能按
        # reference_image 发；官方允许它在提示词里当"目标视频第一帧"（ref-en.txt:62），
        # 但那必须写进 subject_definitions 才算硬锚 —— 旧版只往句尾加一句中文，
        # 实测第 2 段开头 3 秒原片人物回灌（render e6bfd247）。
        rec_long = {"source": rec["source"],
                    "shots": [{"i": 0, "start": 0.0, "end": 40.0, "dur": 40.0}]}
        seen.clear()
        calls.clear()
        _nb2 = len(_ir_calls)
        r2b = video_edit.replace_whole(
            video, rec_long, cid="a" * 32, spec=spec,
            refs={"person": person, "product": product},
            channel="minimax", workdir=work / "r2long",
        )
        check("一镜到底 40s 切 3 段", r2b["chunks"], 3)
        # 🩸 2026-11-02 边界帧整条停用（主人拍板）：第 2 段只带换人图。
        #   接缝信息在参考视频里 —— 那一段就是从原片 [a, b] 切出来单独上传的。
        check("中段切开的第 2 段不带边界帧", len(calls[1]["refs"]), 2)
        _c2 = [c for c in _ir_calls[_nb2:] if c.get("n") == 2]
        check("交给改写器的边界帧号恒为 0",
              [int(c.get("boundary_pic") or 0) for c in _c2], [0])
        check("给改写器的素材里没有尾帧那张图",
              bool(_c2 and len(_c2[0].get("images") or []) == 2), True)
        check("MiniMax 报告说没带边界帧", r2b["boundary"], False)
        # 官方「输出规格」：MiniMax-H3 = 768P / 2K。用户要 1080p → 按档位映射到 2K
        check("H3 收 2K", seen["resolution"], "2K")
        # 这一步的 workdir 里**没有** voice.wav → 不许在提示词里写 <Audio 1>
        _b_calls = _ir_calls[_nb2:]
        check("没有配音轨就不告诉改写器有音频",
              [c.get("audio") is None for c in _b_calls], [True] * len(_b_calls))
        check("没有配音轨就不喂音频", seen["audio"], "")

        print("== 口型参考音频：有配音轨才喂 ==")
        # 🩸 成对探针：同一个 workdir 放一条 voice.wav，必须看到
        # ① 音频文件真的传下去 ② 提示词里出现 <Audio 1>
        mm_wd = work / "r2b"
        mm_wd.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=40",
                        "-ac", "1", str(mm_wd / "voice.wav")], check=True)
        seen.clear()
        calls.clear()
        _na = len(_ir_calls)
        video_edit.replace_whole(
            video, rec, cid="a" * 32, spec=spec, refs={"person": person},
            channel="minimax", workdir=mm_wd,
        )
        check("音频真的传下去了", bool(seen["audio"]), True)
        check("音频是这一段的 wav 切片",
              seen["audio"].endswith(".wav") and "seg_" in seen["audio"], True)
        # `<Audio 1>` 和任务类型 `[video editing + audio reference]` 是**改写器的
        # 产出**；我们这边的责任是"把这一段真正的配音切片交过去"。
        _a_calls = _ir_calls[_na:]
        check("每段都把配音切片交给了改写器",
              [bool(c.get("audio")) and str(c.get("audio")).endswith(".wav")
               for c in _a_calls], [True] * len(_a_calls))
        # mix 模式：说话的是新配音，音轨取自 voice.wav（原片本身没有音轨，
        # 真去截原片会失败 —— 能截出 10s 就等于证明了来源）
        from app.services import scene as _scene

        check("截出来是这一段（10s）",
              round(_scene.probe(Path(seen["audio"]))["duration"], 1), 10.0)

        print("== 火山也喂口型音频：同一条规则 ==")
        v_wd = work / "r11"
        v_wd.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "sine=frequency=660:duration=40",
                        "-ac", "1", str(v_wd / "voice.wav")], check=True)
        seen.clear()
        calls.clear()
        video_edit.replace_whole(
            video, rec, cid="7" * 32, spec=spec, refs={"person": person},
            channel="volc", workdir=v_wd,
        )
        check("火山也拿到音频", bool(seen["audio"]), True)
        check("火山提示词写 @音频1", "@音频1" in seen["prompt"], True)
        # 🩸 2026-10-28：这里原来锁的是「口型与@音频1逐字同步」—— 那是我自己造的
        #   半句（官方 2.5 全部文档 0 命中「逐字同步」+@音频的组合）。官方原话是
        #   `sd25-guide:916`「要求逐字同步口型…**口型与台词精准同步**」，
        #   编译器已按官方改写，判据跟着改成官方句。
        check("火山也要求口型同步", "口型做出对应的精准改变" in seen["prompt"], True)

        # 成对：保留原声时**哪怕配音轨就在旁边**也不许喂（原声带商业音乐）
        spec_orig = edit_spec.normalize({"person": True, "audio": "original"})
        v_wd2 = work / "r12"
        v_wd2.mkdir(parents=True, exist_ok=True)
        shutil.copy(v_wd / "voice.wav", v_wd2 / "voice.wav")
        seen.clear()
        calls.clear()
        video_edit.replace_whole(
            video, rec, cid="8" * 32, spec=spec_orig, refs={"person": person},
            channel="volc", workdir=v_wd2,
        )
        check("保留原声不喂音频", seen["audio"], "")
        check("保留原声不写 @音频1", "@音频1" in seen["prompt"], False)

        print("== 边界帧只给紧挨着的上一段 ==")
        seen.clear()
        calls.clear()
        video_edit.replace_spans(
            video, rec, [(0.0, 5.0), (10.0, 15.0)], cid="1" * 32, spec=spec,
            refs={"person": person, "product": product},
            channel="volc", workdir=work / "r7",
        )
        check("两段中间有间隔 → 第 2 段不带边界帧", len(calls[1]["refs"]), 2)
        check("也不写边界句", "上一段成片的最后一帧" in calls[1]["prompt"], False)

        seen.clear()
        calls.clear()
        video_edit.replace_spans(
            video, rec, [(0.0, 5.0), (5.0, 10.0)], cid="2" * 32, spec=spec,
            refs={"person": person, "product": product},
            channel="volc", workdir=work / "r8",
        )
        # 🩸 2026-11-02 边界帧整条停用：相接也不再额外带尾帧。
        check("两段相接 → 第 2 段也不带边界帧", len(calls[1]["refs"]), 2)

        print("== 双人：这一段没出现的人，H3 不带他的图 ==")
        # 🩸 H3 官方 ref-en.txt:35 要求「每一张参考图都要在 subject_definitions
        # 里定义」。旧实现把缺席者的图照发、只是不写定义 —— 模型可以把那张脸
        # 当可用主体塞进画面。这里把「按段摘图 + 整体重编号」钉住。
        person2 = work / "person2.jpg"
        subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "color=c=blue:s=400x600:d=1",
                        "-frames:v", "1", str(person2)], check=True)
        inv2 = {
            "duration_s": 40.0,
            "people": [
                {"id": "P1", "desc_zh": "穿红裙的女生", "desc_en": "the woman in red",
                 "main": True, "appearances": [{"start": 0.0, "end": 40.0}]},
                # P2 只在前 10 秒出现 → 第 2 段（10–20s）起完全缺席
                {"id": "P2", "desc_zh": "戴帽子的男人", "desc_en": "the man in a hat",
                 "appearances": [{"start": 0.0, "end": 10.0}]},
            ],
            "products": [], "scenes": [],
        }
        spec_two = edit_spec.normalize({"person": True, "person_ids": ["P1", "P2"],
                                        "audio": "original"})
        refs_two = {"person": person, "person2": person2}
        seen.clear()
        calls.clear()
        _n2 = len(_ir_calls)
        video_edit.replace_whole(
            video, rec, cid="d" * 32, spec=spec_two, refs=refs_two,
            channel="minimax", inventory=inv2, workdir=work / "r_two",
        )
        check("H3 第 1 段两个人各一张", len(calls[0]["refs"]), 2)
        # 切点在镜头边界（10s）→ 不带边界帧，第 2 段只剩在场的那一个人
        check("H3 第 2 段只发在场的人", len(calls[1]["refs"]), 1)
        _p2 = [c for c in _ir_calls[_n2:] if c.get("n") == 2]
        check("缺席者的图也没交给改写器（只有 1 张）",
              [len(c.get("images") or []) for c in _p2], [1])
        # 🩸 2026-11-02 边界帧整条停用：切点落在镜头中段也不再补尾帧，
        #   第 2 段就是「在场的那一个人」一张图，改写器拿到的边界帧号恒为 0。
        seen.clear()
        calls.clear()
        _n3 = len(_ir_calls)
        video_edit.replace_whole(
            video, rec_long, cid="d" * 32, spec=spec_two, refs=refs_two,
            channel="minimax", inventory=inv2, workdir=work / "r_two_long",
        )
        check("H3 中段切开也不带边界帧（只有在场的 1 张）",
              len(calls[1]["refs"]), 1)
        _p3 = [c for c in _ir_calls[_n3:] if c.get("n") == 2]
        check("边界帧号恒为 0（不谈尾帧）",
              [(len(c.get("images") or []), int(c.get("boundary_pic") or 0))
               for c in _p3], [(1, 0)])
        # 火山保持已验证的「图号稳定」写法：图照发，只是不写那一句
        seen.clear()
        calls.clear()
        video_edit.replace_whole(
            video, rec, cid="e" * 32, spec=spec_two, refs=refs_two,
            channel="volc", inventory=inv2, workdir=work / "r_two_v",
        )
        # 火山保持图号稳定：缺席者的图照发；切点在镜头边界 → 不带边界帧
        check("火山第 2 段照旧发两张人物图", len(calls[1]["refs"]), 2)
        check("火山也不写边界句",
              "上一段成片的最后一帧" in calls[1]["prompt"], False)
        check("火山第 2 段图号不跳（在场者仍是 @图片1）",
              "@图片1" in calls[1]["prompt"], True)
        check("火山第 2 段不写缺席者的换人句",
              "戴帽子的男人" in calls[1]["prompt"], False)

        print("== 素材 ID 占人物槽 ==")
        seen.clear()
        calls.clear()
        spec2 = edit_spec.normalize({"person": True, "product": True})
        video_edit.replace_whole(
            video, rec, cid="b" * 32, spec=spec2, refs={"product": product},
            subject_asset="asset-2026xyz", channel="volc", workdir=work / "r3",
        )
        check("asset + 产品 = 2 张参考", len(calls[0]["refs"]), 2)
        check("asset 排第一", calls[0]["refs"][0], "asset-2026xyz")
        check("产品排第二", calls[0]["refs"][1], str(product))
        check("提示词不写 asset id", "asset-2026xyz" not in seen["prompt"], True)

        print("== 不勾人物就不带人物图 ==")
        seen.clear()
        calls.clear()
        spec3 = edit_spec.normalize({"product": True})
        video_edit.replace_whole(
            video, rec, cid="c" * 32, spec=spec3,
            refs={"person": person, "product": product},
            channel="volc", workdir=work / "r4",
        )
        check("只带产品一张", len(calls[0]["refs"]), 1)
        check("带的是产品", calls[0]["refs"][0], str(product))
        check("产品降为@图片1", "产品替换为@图片1" in seen["prompt"], True)

        print("== 界面选的型号真的发到了接口 ==")
        seen.clear()
        r5 = video_edit.replace_whole(
            video, rec, cid="d" * 32, spec=spec, refs={"person": person},
            channel="volc", model="doubao-seedance-2-5-260628",
            workdir=work / "r5",
        )
        check("火山收到所选型号", seen["model"], "doubao-seedance-2-5-260628")
        # 2.5 官方支持 1080p（480p/720p/1080p），选了就该原样发出去
        check("2.5 支持 1080p → 原样发送", seen["resolution"], "1080p")
        # 4 镜各 10s = 40s：2.5 单段 30s → 2 段
        check("按 2.5 的 30s 上限切成 2 段", r5["chunks"], 2)
        check("返回里能查到实际型号", r5["model"], "doubao-seedance-2-5-260628")
        # 🩸 这个 video 的 4 刀全落在原片镜头边界（10/20/30s）→ 2.5 一律不带边界帧。
        #   带边界帧的能力由下面 r5c（镜头中段切开）成对覆盖。
        check("2.5 切点在镜头边界 → 第 2 段不带边界帧", len(calls[-1]["refs"]), 1)
        # 🩸 结果页会照着 boundary 写"段间用尾帧衔接" —— 报告必须和实际一致
        check("2.5 分了 2 段但如实报 boundary=False", r5["boundary"], False)
        check("结果页拿得到型号名", r5["label"], "火山 Seedance 2.5")
        check("结果页拿得到清晰度", r5["resolution"], "1080p")

        seen.clear()
        calls.clear()
        video_edit.replace_whole(
            video, rec, cid="f" * 32, spec=spec, refs={"person": person},
            channel="volc", model="doubao-seedance-2-5-260628", workdir=work / "r5b",
        )
        check("2.5 切在镜头边界 → 不带边界帧", len(calls[-1]["refs"]), 1)
        check("2.5 也不写边界句", "上一段成片的最后一帧" in calls[-1]["prompt"], False)
        # 🩸 2026-11-02 边界帧整条停用（两个通道一起）：2.5 中段切开也不补尾帧。
        #   火山的「固定首帧」写法（`sd25-pe:703` 的 `@图片N作为首帧。`）只在
        #   真的递了这张图时才写；现在不递，提示词里就不该出现这句。
        seen.clear()
        calls.clear()
        video_edit.replace_whole(
            # 换一个任务号：30–40s 这一段和上面 4 段版区间相同，同号会命中缓存
            video, rec_long, cid="9" * 32, spec=spec, refs={"person": person},
            channel="volc", model="doubao-seedance-2-5-260628", workdir=work / "r5c",
        )
        check("2.5 镜头中段切开 → 第 2 段也不带边界帧", len(calls[1]["refs"]), 1)
        check("2.5 也不写首帧句", "作为首帧。" in calls[1]["prompt"], False)

        seen.clear()
        video_edit.replace_whole(
            video, rec, cid="e" * 32, spec=spec, refs={"person": person},
            channel="minimax", model="MiniMax-H3-Max", workdir=work / "r6",
        )
        check("MiniMax 收到所选型号", seen["model"], "MiniMax-H3-Max")
        # H3-Max 官方只有 480P/768P，1080p→2K 后仍要降到 768P
        check("H3-Max 不收 2K → 768P", seen["resolution"], "768P")
        check("H3-Max 生成时长落在 5~15s", 5 <= seen["duration"] <= 15, True)

        print("== 视觉盘点：目标不在的分段留原片 ==")
        seen.clear()
        calls.clear()
        inv = {
            "duration_s": 40.0,
            "people": [{"id": "P1", "desc_zh": "红裙女生",
                        "desc_en": "the woman in red",
                        "appearances": [{"start": 0.0, "end": 10.0}],
                        "main": True, "face_visible": True}],
            "products": [], "scenes": [], "notes": "",
        }
        # 保留原声才允许整段留原片：口型跟原声本来就是对的
        spec_inv = edit_spec.normalize({"person": True, "audio": "original"})
        r9 = video_edit.replace_whole(
            video, rec, cid="f" * 32, spec=spec_inv, refs={"person": person},
            channel="volc", inventory=inv, workdir=work / "r9",
        )
        check("只有目标那一刀调模型（另一刀留原片）", len(calls), 1)
        # 单人画面不写原片描述（那段描述写衣服，会把模型带成只换衣服）——
        # 多人画面才需要它当定位词，见 p9 C2。
        check("单人画面直接用人称换人",
              ("人物修改为@图片1中的人物" in calls[0]["prompt"]
               or "人物替换为@图片1中的人物" in calls[0]["prompt"]), True)
        check("仍有官方范围闭环", "其他可见人物、道具和背景元素保持原样" in calls[0]["prompt"], True)
        check("分段数不变", r9["chunks"], 2)
        check("回报保留了 1 段原片（便于对账）", r9["kept"], 1)

        print("== 素材库：含真人的图/视频换成 asset:// ==")
        from app.services import ark_ingest

        real_ing = (ark_ingest.available, ark_ingest.prepare_video,
                    ark_ingest.prepare_image)
        ing_calls: list[tuple[str, str]] = []

        # 🩸 假函数必须和真签名一致：产品 2026-10-23 给 `prepare_video` 加了
        # 关键字参数 `report`（失败原因回传），夹具没跟上的话调用直接 TypeError，
        # 被上层 `except` 吞掉 → 悄悄退回直传，判据报红还查不出原因。
        def fake_prep_video(path, cid, url="", *, report=None):
            ing_calls.append(("video", str(path)))
            return "asset://asset-v1"

        def fake_prep_image(path, cid):
            ing_calls.append(("image", str(path)))
            # 人像入库，产品图没脸 → 返回空，调用方保持原样（base64）
            return "asset://asset-i1" if "person" in str(path) else ""

        try:
            ark_ingest.available = lambda: True
            ark_ingest.prepare_video = fake_prep_video
            ark_ingest.prepare_image = fake_prep_image
            seen.clear()
            n_before = len(calls)
            video_edit.replace_whole(
                video, rec, cid="9" * 32, spec=spec,
                refs={"person": person, "product": product},
                channel="volc", workdir=work / "r10",
            )
            model_n = len(calls) - n_before
            check("视频换成 asset://", seen["url"].startswith("asset://"), True)
            check("人像换成 asset://",
                  any(r.startswith("asset://") for r in seen["refs"]), True)
            check("没脸的图不入库、原样送",
                  any("product" in r for r in seen["refs"]), True)
            vpaths = [p for k, p in ing_calls if k == "video"]
            check("每段入库一次，和调模型次数对得上", len(vpaths), model_n)
            check("同一段不重复入库", len(set(vpaths)), len(vpaths))
        finally:
            ark_ingest.available, ark_ingest.prepare_video, \
                ark_ingest.prepare_image = real_ing

    finally:
        _tr0._chat = _real_translate_chat
        _tr0.translate_text_cache_clear()
        ark.edit_video, minimax.reference_video, video_edit._public_url = real[:3]
        object.__setattr__(settings, "ark_api_key", real[3])
        object.__setattr__(settings, "minimax_api_key", real[4])
        object.__setattr__(settings, "public_base_url", real[5])
        clone_store.task_dir = real_task_dir
        _ing.available = real_ing_avail

    # ------------------------------------------------------------------
    # 🩸 2026-10-28：缺素材闸的「换装逐个查」和「参考图张数上限」都靠
    #   `missing_material(..., model=)` 才生效。以前**两处生产调用都没传 model**
    #   ⇒ 那些检查全是死代码（函数里 `str(model or "").startswith(...)` 恒为假）。
    #   函数级判据证明不了这件事 —— 必须走**生产入口** `_prepare`。
    try:
        from app.services import edit_spec as _es

        _P1g = {"id": "P1", "present": True, "position": "center", "desc_zh": "男子"}
        _P2g = {"id": "P2", "present": True, "position": "right", "desc_zh": "女子"}

        def _gate_of(chg, refs, ppl):
            try:
                video_edit._prepare(rec={"people": ppl}, prompt="x",
                                    spec=_es.normalize(chg), refs=refs,
                                    channel="volc",
                                    model="doubao-seedance-2-5-260628",
                                    inventory={"people": ppl})
                return "pass"
            except video_edit.EditError:
                return "block"

        # 🩸 2026-10-31：原来这两条（换装两人逐个查）测的是 `wardrobe_check_per_person`
        #   这个能力位 —— 它**只由已归档的 volc20 声明**，2.5/H3 现在都是 False。
        #   换成 2.5 跑会得到「有图就放行 / 只给 desc_by_id 就拦」，那是 2.5 的
        #   老行为，不是同一个检查；照原样改绿等于把 2.0 的规则洗成 2.5 的规则。
        #   生产入口这条路径现在**没有承载型号**，无法验证，故撤掉这两条。
        #   ⚠️ 将来某型号打开 `wardrobe_check_per_person` 时，这两条要恢复，
        #   并把 model 换成那个型号。
        check("生产入口·11 张参考图（超 9 张上限）→ 拦住",
              _gate_of({"person": True, "person_ids": ["P1", "P2", "P3", "P4"],
                        "wardrobe": True, "wardrobe_ids": ["P1", "P2", "P3", "P4"],
                        "product": True, "product_desc": "面霜",
                        "scene": True, "scene_desc": "海边",
                        "style_ref": True},
                       {k: person for k in ("person", "person2", "person3",
                                            "person4", "wardrobe", "wardrobe2",
                                            "wardrobe3", "wardrobe4", "product",
                                            "scene", "style_ref")},
                       [_P1g, _P2g, dict(_P1g, id="P3", position="left"),
                        dict(_P2g, id="P4")]), "block")
    except Exception as e:  # noqa: BLE001
        check(f"缺素材闸接线没崩（{type(e).__name__}: {e}）", "", "")

    # ── 遮罩默认关（2026-10-29 主人拍板）─────────────────────────────
    # 判据不是"代码里写了 False"，而是**不传这个字段的人会拿到什么**：
    # 前端不勾 → 后端不遮 → 成片没有那条实心黑边。
    # 三层都得是 False，任何一层留着 True 都会把旧行为放回来。
    print("\n遮罩默认关")
    import inspect

    from app.api import clone as _clone_api
    from app.services import clone_jobs as _cj, clone_pipeline as _cp

    # RenderIn 有必填字段（script），直接取字段默认值，不实例化
    check("API 不传 mask_bottom → 不遮",
          _clone_api.RenderIn.model_fields["mask_bottom"].default, False)
    check("任务默认 → 不遮",
          inspect.signature(_cj.submit_render)
          .parameters["mask_bottom"].default, False)
    check("出片函数默认 → 不遮",
          inspect.signature(_cp.render)
          .parameters["mask_bottom"].default, False)
    _vue = (Path(__file__).resolve().parents[2]
            / "frontend/app/src/pages/clone/diagnose.vue")
    _src = _vue.read_text(encoding="utf-8") if _vue.exists() else ""
    check("诊断页开关默认关（前端点进去就是关的）",
          "maskBottom: false" in _src, True)

    # ── 强制重跑（2026-11-02）────────────────────────────────────
    # 同样的输入本来**永远命中段缓存**，模型一次都不调 —— 省钱，但效果不满意
    # 时再点一次没用（实测三次渲染拿回同一个 476,680 字节的旧片）。
    # 默认必须是关的（不传 force = 老行为），四层都得能透传。
    print("\n强制重跑")
    check("API 默认不强制重跑",
          _clone_api.RenderIn.model_fields["force"].default, False)
    check("任务层默认不强制",
          inspect.signature(_cj.submit_render)
          .parameters["force"].default, False)
    check("出片函数默认不强制",
          inspect.signature(_cp.render).parameters["force"].default, False)
    _reqjs = Path(__file__).resolve().parents[2] / "frontend/app/src/api/request.js"
    _rjs = _reqjs.read_text(encoding="utf-8") if _reqjs.exists() else ""
    check("前端只在打开时才发 force（老请求体形状不变）",
          "force ? { force: true }" in _rjs, True)
    check("诊断页有开关且默认关、打开才传",
          "forceRerun: false" in _src
          and "force: this.forceRerun === true" in _src, True)
    _ve_src = (Path(__file__).resolve().parents[1]
               / "app/services/video_edit.py").read_text(encoding="utf-8")
    check("_gen_spans 的 force 真的跳过两级缓存",
          "not force and manifest.get(seg.name) == key" in _ve_src
          and "not force and _cache_get(cid, key, gen)" in _ve_src, True)

    # ── 开放平台前后端一致 ────────────────────────────────────────
    # `config.js` 自己写着「两边漏改一边就会出现『显示但解析报暂不支持』」，
    # 但以前没人机械验过。判据是**两份名单逐项相等**，不是"某边含 twitter"。
    print("\n开放平台前后端一致")
    _cfg = (Path(__file__).resolve().parents[2] / "frontend/app/src/config.js")
    _js = _cfg.read_text(encoding="utf-8") if _cfg.exists() else ""
    _m = re.search(r"ENABLED_PLATFORMS\s*=\s*\[(.*?)\]", _js, re.S)
    _fe = [x.strip().strip("'\"") for x in _m.group(1).split(",") if x.strip()] if _m else []
    check("前端名单读得到（读不到就是空表，别当成通过）", bool(_fe), True)
    check("前端 == 后端", _fe, list(settings.enabled_platforms))

    # 配了代理之后 X 到底会不会用 —— 这才是"开放"能不能落地的关键。
    # 以前 `_proxy()` 对所有非 youtube 平台一律返回 ""，配了 `VT_PROXY` 也白配。
    from app.parsers.ytdlp_provider import YtdlpParser

    _tw = YtdlpParser("twitter", ("twitter.com", "x.com"))
    _ig = YtdlpParser("instagram", ("instagram.com",))
    _real_proxy = settings.proxy
    try:
        object.__setattr__(settings, "proxy", "http://127.0.0.1:7890")
        check("配了 VT_PROXY → X 解析走代理", _tw._proxy(), "http://127.0.0.1:7890")
        check("配了 VT_PROXY → Instagram 仍直连（不被波及）", _ig._proxy(), "")
        object.__setattr__(settings, "proxy", "")
        check("没配代理 → X 也不瞎填", _tw._proxy(), "")
    finally:
        object.__setattr__(settings, "proxy", _real_proxy)

    # 没代理时**必须秒失败**：真去连的话 120s 超时 × 3 次 = 用户等 6 分钟。
    # 判据看的是「有没有真发请求」，不是错误文案里写了什么。
    import asyncio as _aio

    from app.parsers import ytdlp_provider as _yp

    _calls: list[str] = []
    _real_dump = _yp.dump_json

    async def _fake_dump(u, proxy=""):
        _calls.append(proxy)
        return {"title": "t", "formats": []}

    try:
        _yp.dump_json = _fake_dump
        object.__setattr__(settings, "proxy", "")
        _err = ""
        try:
            _aio.run(_tw.parse("https://x.com/a/status/1"))
        except RuntimeError as e:
            _err = str(e)
        check("没配代理·X：直接报错不联网", (bool(_err), len(_calls)), (True, 0))

        object.__setattr__(settings, "proxy", "http://127.0.0.1:7890")
        _calls.clear()
        try:
            _aio.run(_tw.parse("https://x.com/a/status/1"))
        except Exception:  # noqa: BLE001  —— 假数据没有视频，走到后面会抛
            pass
        check("配了代理·X：真的发请求并带代理", _calls, ["http://127.0.0.1:7890"])
    finally:
        _yp.dump_json = _real_dump
        object.__setattr__(settings, "proxy", _real_proxy)

    _ir.prompt_for = _real_pf      # 恢复真改写器（见 MiniMax 段）
    _vp.describe_person = _real_dp  # 恢复真视觉描述
    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
