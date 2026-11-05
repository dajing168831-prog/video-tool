"""整片重制的接线自检：真跑切段/规格化/拼接，只把模型调用换成假实现。

验的不是"代码里有没有这句话"，而是**实际发给模型的参数**：
提示词原文、参考图的张数和顺序、分辨率档位、每条通道的标号语法。
不花钱（不发任何网络请求）。

🔴 **这是跨通道共用文件，不是某一家模型的验收**：
验的是"同一个入口会不会选错通道、拼错提示词"。
🧊 2026-11-03 复刻下架 H3：MiniMax 那半段（576 行）随执行链一起删了
（`backend/_archive/h3_clone/`），现在只跑火山通道。
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
    from app.services import ark

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

    # 🧊 2026-11-03：`fake_mm`（MiniMax 出片桩）随 H3 下架删除。
    real = (ark.edit_video, video_edit._public_url,
            settings.ark_api_key, settings.public_base_url)
    # 🩸 生成缓存挂在任务目录下：不隔离就会读到上一次跑测试留下的缓存，
    # 这一轮的假模型一次都不会被调用，测试直接空转
    from app.services import clone_store
    real_task_dir = clone_store.task_dir
    clone_store.task_dir = lambda cid: work / "tasks" / cid
    ark.edit_video = fake_volc
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
        # 🧊 2026-11-03：`rec_long` 原来定义在 MiniMax 段，那段随 H3 下架删了，
        #   这里补回（40s 单镜 → 火山按 30s 上限切 2 段，验第 2 段不带边界帧）。
        rec_long = {"source": rec["source"],
                    "shots": [{"i": 0, "start": 0.0, "end": 40.0, "dur": 40.0}]}
        seen.clear()
        calls.clear()
        video_edit.replace_whole(
            # 换一个任务号：30–40s 这一段和上面 4 段版区间相同，同号会命中缓存
            video, rec_long, cid="9" * 32, spec=spec, refs={"person": person},
            channel="volc", model="doubao-seedance-2-5-260628", workdir=work / "r5c",
        )
        check("2.5 镜头中段切开 → 第 2 段也不带边界帧", len(calls[1]["refs"]), 1)
        check("2.5 也不写首帧句", "作为首帧。" in calls[1]["prompt"], False)

        # 🧊 2026-11-03：`MiniMax 收到所选型号 / H3-Max 不收 2K` 这几条随 H3 下架删除。

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

        def fake_prep_image(path, cid, *, report=None):
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
        ark.edit_video, video_edit._public_url = real[:2]
        object.__setattr__(settings, "ark_api_key", real[2])
        object.__setattr__(settings, "public_base_url", real[3])
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

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
