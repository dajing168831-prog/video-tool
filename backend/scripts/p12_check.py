"""P12 验收：风格参考（A9，图 + 视频）。

零模型调用、不花钱。每条都指到官方出处或本机实测，不写"看着像对"的断言。

  S1  归一化与签名   —— 新增两个字段**空着不许进签名**（否则历史出片全部失配）
  S2  图片编号       —— `style_ref` 只能追加在最后（插队会让历史提示词的图号全错）
  S3  2.5 职责行     —— 每个素材一句，风格图的排他集是"主体、构图、场景内容"
  S4  2.5 编辑目标   —— 风格句在目标句里；**风格不计入「目标对象数量」**
  S5  2.0 句式       —— `seedance-20-guide.md:20/:26/:228`
  S6  H3 写法        —— 风格是 `<Subject N>`，**不是**独立的 `<Video N>` 定义行
  S7  分诊           —— 用风格视频时整片强制走 video（静帧吃不到视频参考）
  S8  时长预算       —— 母版片段 + 风格片段 ≤ 型号上限；放不下**出片前**拦
  S9  只有开关没文件 —— 不写 `@视频2`（防指向不存在的素材）+ 出片前拦住
  S10 接线与界面     —— 请求体追加参考视频、前端两行入口、字段真的传进请求

官方出处：
  · `seedance-25-guide.md:49/:966/:117`　2.5 支持风格参考（图/视频）、≤10 段总 ≤30s
  · `seedance-20-guide.md:20/:26/:204-206/:228/:987`　2.0 句式、三个维度、总 ≤15s
  · `sd25-pe:360/:556-558/:568`　2.5 职责行 / 范围闭环 / 排他句
  · H3 `ref-en.txt:46/:68/:78-86/:88`　Subject 覆盖 Styles、风格素材写进 Subject
  · `mm-docs:8273`　H3 参考视频 ≤3 段、单段 [2,15]s、总 ≤15s、单文件 ≤50MB

跑法：python scripts/p12_check.py --model volc20|volc25|h3
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import clone_store, edit_spec, model_specs, triage, video_edit  # noqa: E402

FRONT = ROOT.parent / "frontend" / "app" / "src"
DIAG = FRONT / "pages" / "clone" / "diagnose.vue"
REQ = FRONT / "api" / "request.js"
API = ROOT / "app" / "api" / "clone.py"

V25 = "doubao-seedance-2-5-260628"
V20 = "doubao-seedance-2-0-260128"
H3 = "MiniMax-H3"

rows: list[tuple[str, bool, str]] = []

# 🚦 必须点名型号（2026-10-26）：一轮只跑一家。
from _model_gate import sel_or_exit as _sel_or_exit
SEL = _sel_or_exit()


def chk(name: str, ok, detail: str = "") -> None:
    rows.append((name, bool(ok), detail if not ok else ""))


def spec_of(chg: dict) -> dict:
    return edit_spec.normalize(chg)


def prompt(ch: str, chg: dict, slots: list[str], *, model: str = "",
           style_video: bool = False) -> str:
    return edit_spec.compile_prompt(ch, spec_of(chg), slots=slots, model=model,
                                    style_video=style_video)


P25_PLAIN = prompt("volc", {"person": True}, ["person"], model=V25)
P25_IMG = prompt("volc", {"person": True, "style_ref": True},
                 ["person", "style_ref"], model=V25)
P25_VID = prompt("volc", {"person": True, "style_video": True, "style_ref": True},
                 ["person"], model=V25, style_video=True)
P20_PLAIN = prompt("volc", {"person": True}, ["person"], model=V20)
P20_IMG = prompt("volc", {"person": True, "style_ref": True},
                 ["person", "style_ref"], model=V20)
P20_VID = prompt("volc", {"person": True, "style_video": True},
                 ["person"], model=V20, style_video=True)
H3_PLAIN = prompt("minimax", {"person": True}, ["person"], model=H3)
H3_IMG = prompt("minimax", {"person": True, "style_ref": True},
                ["person", "style_ref"], model=H3)
H3_VID = prompt("minimax", {"person": True, "style_video": True},
                ["person"], model=H3, style_video=True)


# ---------------------------------------------------------------------------
# S1 归一化与签名

d = edit_spec.defaults()["change"]
chk("S1 默认两个开关都是关", d["style_ref"] is False and d["style_video"] is False,
    f"{d['style_ref']!r}/{d['style_video']!r}")

n_img = spec_of({"style_ref": True})["change"]
chk("S1 只传图 → style_ref 开、style_video 关",
    n_img["style_ref"] is True and n_img["style_video"] is False,
    f"{n_img['style_ref']}/{n_img['style_video']}")

n_both = spec_of({"style_ref": True, "style_video": True})["change"]
chk("S1 两个都传 → 视频胜、图被关（互斥只留一个来源）",
    n_both["style_video"] is True and n_both["style_ref"] is False,
    f"{n_both['style_ref']}/{n_both['style_video']}")

sig_plain = edit_spec.sig_change({"person": True})
chk("S1 空的新字段不进签名（老记录不会失配）",
    "style_ref" not in sig_plain and "style_video" not in sig_plain, str(sig_plain))
chk("S1 老记录的签名 == 显式传了两个 False 的签名",
    edit_spec.sig_change({"person": True, "style_ref": False,
                          "style_video": False}) == sig_plain, "")
chk("S1 真开了就进签名（改了风格必须重画）",
    edit_spec.sig_change({"person": True, "style_ref": True}).get("style_ref") is True, "")

# ---------------------------------------------------------------------------
# S2 图片编号只能往后追加

chk("S2 style_ref 排在 SLOT_ORDER 最后", edit_spec.SLOT_ORDER[-1] == "style_ref",
    str(edit_spec.SLOT_ORDER))
chk("S2 槽位名有中文标签", edit_spec.SLOT_LABEL.get("style_ref") == "风格参考",
    edit_spec.SLOT_LABEL.get("style_ref", ""))

slots1 = [s for s, _ in edit_spec.ref_order(spec_of({"person": True, "style_ref": True}))]
idx1 = edit_spec.image_index(slots1)
chk("S2 单人+风格图 → 风格图是图片2（人物还是图片1，历史图号不动）",
    slots1 == ["person", "style_ref"] and idx1["style_ref"] == 2,
    f"{slots1} {idx1}")

# 🩸 2026-10-26：「大头照 + 全身照」派生槽已删除（台账 D48，一人一张）。
# 这条改成**防回退**：风格图永远紧跟在人物图后面，不许再有第三个槽位插进来。
chk("S2 只有一张人物图 → 风格图就是图片2（没有派生槽）",
    slots1 == ["person", "style_ref"] and idx1["style_ref"] == 2,
    f"{slots1} {idx1}")

# ---------------------------------------------------------------------------
# S3 2.5 职责行 / 排他句

if SEL == "volc25":
    chk("S3 2.5 风格图有自己的职责行（`sd25-pe:568` 句式）",
        "@图片2用于整体画面的色调、光影和质感，不采用其中的主体、构图和场景内容。" in P25_IMG,
        P25_IMG)
    chk("S3 2.5 风格视频的职责行（`sd25-pe:360` 的排他集多运镜和节奏）",
        "@视频2用于整体画面的色调、光影和质感，不采用其中的主体、构图、场景内容、运镜和节奏。"
        in P25_VID, P25_VID)
    chk("S3 2.5 有风格参考时不再写「光线和色调不变」（自相矛盾）",
        "光线和色调" not in P25_IMG and "光线和色调" not in P25_VID, P25_IMG)
    chk("S3 2.5 没有风格参考时照旧保留「光线和色调」",
        "光线和色调" in P25_PLAIN, P25_PLAIN)

STILL_STYLE = edit_spec.still_prompt(
    spec_of({"person": True, "style_ref": True}), ["person", "style_ref"],
    fallback="一个人站在门口")
STILL_PLAIN = edit_spec.still_prompt(
    spec_of({"person": True}), ["person"], fallback="一个人站在门口")
chk("S3 静帧重绘（图生图）也带风格句，图号对得上（图三）",
    "画面风格参考图三的色调、光影和质感，不采用图三里的主体和构图" in STILL_STYLE,
    STILL_STYLE)
chk("S3 静帧有风格参考时开头不说「光线不变」（同一句自相矛盾）",
    "光线" not in STILL_STYLE and "光线" in STILL_PLAIN, STILL_STYLE)

# ---------------------------------------------------------------------------
# S4 2.5 编辑目标 + 目标对象数量

if SEL == "volc25":
    # 🩸 2026-10-28：动词从「改成」改成「替换为」—— `sd25-pe:271` 明说
    #   「"转换、调整、修改、**改成**、重构"等动词本身不构成视频编辑」，
    #   能当编辑动作写的只有模板 `:561` 与已填示例（`:584`、`sd25-guide:1205`）。
    chk("S4 2.5 编辑目标里有风格句（`sd25-pe:561` 的一句话目标）",
        "只把整体画面风格替换为@图片2的色调、光影和质感" in P25_IMG, P25_IMG)
    chk("S4 2.5 风格视频走 @视频2 同句",
        "只把整体画面风格替换为@视频2的色调、光影和质感" in P25_VID, P25_VID)
    m = re.search(r"全片目标对象数量为(\d+)", P25_IMG)
    chk("S4 2.5 风格**不计入**「目标对象数量」（只有人物那 1 个）",
        bool(m) and m.group(1) == "1", m.group(0) if m else "没找到数量句")
    chk("S4 2.5 范围闭环仍是官方逐字（`sd25-pe:556-558`）",
        "除以上明确修改对象外，@视频1中其他可见人物、道具和背景元素保持原样，不参与替换或删除。"
        in P25_IMG, "")

# ---------------------------------------------------------------------------
# S5 2.0 句式

if SEL == "volc20":
    # 🩸 2026-10-27 判据更新（实现先改，判据跟上）：
    #   · 风格句改成**官方组合任务原句**「参考<素材N>的[参考维度]」。
    #     旧判据守的「整体画面风格参考@图片2…」是我们自造的写法，
    #     2.0 六份资料零命中（见 `edit_spec.py:1696` 的注释）。
    #   · 兜底包按 sd2-pe `:129` + 3.2 表折叠成短句「高清电影质感」
    #     （见 `volc20_compile._volc20_boilerplate` 的注释）。
    chk("S5 2.0 风格图句（`:228` 的「参考<素材N>的[维度]」→ 取色调光影质感）",
        "参考@图片2的色调、光影和质感，不采用其中的主体、构图和场景内容"
        in P20_IMG, P20_IMG)
    chk("S5 2.0 风格视频句（`:20` 提取风格 + `:26` 参考视频N）",
        "参考@视频2的色调、光影和质感，不采用其中的主体、构图、场景内容、运镜和节奏"
        in P20_VID, P20_VID)
    chk("S5 2.0 有风格参考时不写「光线和色调不变」",
        "光线和色调" not in P20_IMG and "光线和色调" not in P20_VID, P20_IMG)
    # 🩸 原判据判的是「光线和色调」——2.0 的保留句已换成 LAS `las_cn.md:405`
    #    的「保留原视频动作、位置、互动、镜头和背景」，判据跟着换。
    chk("S5 2.0 没有风格参考时照旧保留",
        "保留原视频动作、位置、互动、镜头和背景" in P20_PLAIN, P20_PLAIN)
    chk("S5 2.0 官方兜底包仍挂着（画质/稳定/水印，不是风格句能省的）",
        "高清电影质感" in P20_IMG and "不要生成水印" in P20_IMG, P20_IMG)

# ---------------------------------------------------------------------------
# S6 H3：风格是 Subject，不是 Video

if SEL == "h3":
    chk("S6 H3 风格图写成 `<Subject N> is the visual style shown in <Picture 2>`"
        "（`ref-en:46` Styles 归 Subject、`:68` 风格图不单独建 Picture）",
        re.search(r"<Subject \d+> is the visual style shown in <Picture 2>", H3_IMG) is not None,
        H3_IMG)
    chk("S6 H3 风格视频也从 `<Subject N>` 出发（`ref-en:88`）",
        re.search(r"<Subject \d+> is the visual style shown in <Video 2>", H3_VID) is not None,
        H3_VID)
    chk("S6 H3 没有独立的 `<Video 2> is …` 定义行（`ref-en:78-86` Video 只管整片关系）",
        re.search(r"(?m)^\s*<Video 2>\s+is\b", H3_VID) is None, H3_VID)
    chk("S6 H3 有 retention_analysis 的 attribute_transfer 一行",
        re.search(r"<Subject \d+> \(the whole target video\): attribute_transfer", H3_IMG)
        is not None, H3_IMG)
    chk("S6 H3 detailed_description 说的是「被替换」不是「保持原风格」",
        "Its visual style, color grade and lighting are replaced by <Subject 3>" in H3_IMG
        and "It keeps the visual style" not in H3_IMG, "")
    chk("S6 H3 没有风格参考时照旧写 keep 原风格",
        "It keeps the visual style, color grade and lighting of <Video 1>" in H3_PLAIN, "")

# ---------------------------------------------------------------------------
# S7 分诊：风格视频 → 整片走 video

SHOTS = [
    {"i": 1, "start": 0.0, "end": 3.0, "dur": 3.0, "motion": 0.05},
    {"i": 2, "start": 3.0, "end": 6.0, "dur": 3.0, "motion": 0.02},
    {"i": 3, "start": 6.0, "end": 9.0, "dur": 3.0, "motion": 0.10},
]
base = triage.decide(SHOTS, audio_mode="tts")
chk("S7 前提：低运动量的镜头本来会走静帧",
    set(base.values()) == {"still"}, str(base))
forced = triage.decide(SHOTS, audio_mode="tts", force_video=True)
chk("S7 风格视频 → 全部走 video（静帧发不出参考视频）",
    set(forced.values()) == {"video"}, str(forced))
picked = triage.decide(SHOTS, picks=[1], audio_mode="tts", force_video=True)
chk("S7 只勾了第 1 镜：第 1 镜 video，其余 keep（用户的选择优先）",
    picked == {1: "video", 2: "keep", 3: "keep"}, str(picked))

# ---------------------------------------------------------------------------
# S8 时长预算（官方总时长上限）

chk("S8 型号表里有总时长上限，且 2.5=30 / 2.0=15 / H3=15",
    (model_specs.volc(V25)["ref_video_total_sec"] == 30
     and model_specs.volc(V20)["ref_video_total_sec"] == 15
     and model_specs.minimax(H3)["ref_video_total_sec"] == 15), "")

c13, e13 = video_edit.style_video_budget("volc", V20, [(0.0, 13.0)])
chk("S8 2.0 + 13 秒母版段 → 拦下（15 秒装不下 13+2）", c13 == 0.0 and bool(e13),
    f"{c13} {e13}")
chk("S8 拦下的话说清楚了退路（改用参考图 / 换 2.5）",
    "风格参考图" in e13 and "30" in e13, e13)
c12, e12 = video_edit.style_video_budget("volc", V20, [(0.0, 12.0)])
chk("S8 2.0 + 12 秒母版段 → 放行，且总时长不超 15",
    not e12 and c12 > 0 and 12.0 + c12 <= 15.0, f"{c12} {e12}")

c28, e28 = video_edit.style_video_budget("volc", V25, [(0.0, 28.0)])
chk("S8 2.5 + 28 秒母版段 → 拦下（30 秒装不下 28+2）", c28 == 0.0 and bool(e28),
    f"{c28} {e28}")
c27, e27 = video_edit.style_video_budget("volc", V25, [(0.0, 27.0)])
chk("S8 2.5 + 27 秒母版段 → 放行，且总时长不超 30",
    not e27 and 27.0 + c27 <= 30.0, f"{c27} {e27}")

ch13, eh13 = video_edit.style_video_budget("minimax", H3, [(0.0, 13.0)])
ch12, eh12 = video_edit.style_video_budget("minimax", H3, [(0.0, 12.0)])
chk("S8 H3 跟 2.0 同口径（15 秒）：13 秒拦、12 秒放",
    ch13 == 0.0 and bool(eh13) and not eh12 and ch12 > 0, f"{ch13}/{ch12}")

cmulti, emulti = video_edit.style_video_budget(
    "volc", V20, [(0.0, 5.0), (5.0, 12.5), (12.5, 14.0)])
# 最长一段 7.5s（不是三段加起来 14s —— 加起来的话 15 秒必炸）；放得下就截满 3 秒
chk("S8 多段时按**最长的一段**算（最长 7.5s → 截满 3s，不是把段长加起来）",
    not emulti and abs(cmulti - video_edit.STYLE_CLIP_SEC) < 1e-6, f"{cmulti} {emulti}")

# ---------------------------------------------------------------------------
# S9 只有开关没有文件

p_no_file = prompt("volc", {"person": True, "style_video": True}, ["person"],
                   model=V25, style_video=False)
chk("S9 开关开着但视频没到 → 不写 @视频2（不指向不存在的素材）",
    "@视频2" not in p_no_file, p_no_file)
p_no_img = prompt("volc", {"person": True, "style_ref": True}, ["person"], model=V25)
chk("S9 开关开着但图没发出去 → 不写图片风格句",
    "整体画面风格改成" not in p_no_img and "@图片2" not in p_no_img, p_no_img)

lack_img = edit_spec.missing_material(spec_of({"style_ref": True}), {})
chk("S9 缺风格图 → 出片前拦住并说清后果",
    bool(lack_img) and "风格参考图" in lack_img, str(lack_img))
lack_vid = edit_spec.missing_material(spec_of({"style_video": True}), {},
                                      style_video=False)
chk("S9 缺风格视频 → 出片前拦住并说清后果",
    bool(lack_vid) and "风格参考视频" in lack_vid, str(lack_vid))
ok_vid = edit_spec.missing_material(spec_of({"style_video": True}), {}, style_video=True)
chk("S9 文件到位就不拦", ok_vid is None, str(ok_vid))

# ---------------------------------------------------------------------------
# S10 接线与界面

chk("S10 视频槽位存在且只认 style", clone_store.REF_VIDEO_SLOTS == ("style",),
    str(clone_store.REF_VIDEO_SLOTS))
try:
    clone_store.ref_video_path("0" * 32, "nope")
    raise AssertionError("未知槽位居然没报错")
except ValueError:
    chk("S10 未知视频槽位报错（防路径穿越/拼错名）", True)
chk("S10 对外视图带 ref_videos（前端据此显示已上传）",
    "ref_videos" in (clone_store.public.__doc__ or "")
    or '"ref_videos"' in (ROOT / "app" / "services" / "clone_store.py").read_text(
        encoding="utf-8"), "")

api_src = API.read_text(encoding="utf-8")
chk("S10 后端有上传 / 删除 / 预览三条路由",
    '"/clone/{cid}/style-video"' in api_src
    and '@router.delete("/clone/{cid}/style-video")' in api_src
    and '"/clone/{cid}/file/ref-video"' in api_src, "")
chk("S10 型号表把 ref_video_total_sec 下发给前端（数字只有一份）",
    '"ref_video_total_sec"' in api_src, "")

diag = DIAG.read_text(encoding="utf-8")
chk("S10 界面 edit 里有 style_ref / style_video 两个字段",
    "style_ref: false" in diag and "style_video: false" in diag, "")
chk("S10 界面有两个上传入口（图走 chooseRef、视频走 uploadStyleVideo）",
    "chooseRef('style_ref'" in diag and "uploadStyleVideo" in diag, "")
chk("S10 界面上传后按文件回填开关（没有勾选框）",
    "this.edit.style_video = rv" in diag and "this.edit.style_ref = ri" in diag, "")
chk("S10 界面提示写着时长上限与互斥",
    "styleVideoHint" in diag and "二选一" in diag, "")
chk("S10 「换什么」判定认这两个字段（否则只有风格时按钮是灰的）",
    "e.style_ref || e.style_video" in diag, "")

# 🩸 请求模型必须**声明**这些字段：pydantic 默认丢掉未声明的键，
# `body.edit.model_dump()` 里没有 → 前端传上来等于没传（2026-10-25 实测过一次）
from app.api.clone import EditIn  # noqa: E402

modeled = EditIn(**{"style_ref": True, "style_video": True,
                    "wardrobe_ids": ["P1"], "speaker_ids": ["P2"],
                    "product_target": "白色的杯子"}).model_dump()
chk("S10 请求模型认得两个风格字段（丢键 = 静默不生效）",
    modeled.get("style_ref") is True and modeled.get("style_video") is True, str(modeled))
chk("S10 请求模型也不吞换装/说话人/产品定位（A5/A7/C3 同一个坑）",
    modeled.get("wardrobe_ids") == ["P1"] and modeled.get("speaker_ids") == ["P2"]
    and modeled.get("product_target") == "白色的杯子", str(modeled))

req = REQ.read_text(encoding="utf-8")
chk("S10 请求层有上传/删除 + 预览地址",
    "cloneUploadStyleVideo" in req and "cloneDeleteStyleVideo" in req
    and "file/ref-video" in req, "")

# 🩸 2026-10-26 L3：原来的判据是「`video_edit.py` 里有这句 ref_videos=…」——
# 那是**文本判据**，代码一搬走就假红（实际请求是对的）。
# 改成**行为判据**：真的调一次提交，抓模型接口收到的参数。
import tempfile as _tf
from unittest import mock as _mock

from app.services import ark as _ark_mod
from app.services import minimax as _mm_mod
from app.services import video_edit as _ve_mod
from app.services.models import h3 as _h3_ad
from app.services.models import volc20 as _v20_ad

_tmpbase = ROOT / "data" / "tmp"
_tmpbase.mkdir(parents=True, exist_ok=True)
_tmp = Path(_tf.mkdtemp(prefix="p12s10_", dir=str(_tmpbase)))
_style = _tmp / "style.mp4"
_style.write_bytes(b"x")
_cap: dict = {}


def _plan(ch: str, model: str) -> dict:
    return {"resolution": "720p", "model": model, "ch": ch}


_ctx = lambda ch, model: {
    "seg": _style, "prompt": "p", "out": _style, "refs": [],
    "audio": None, "style_clip": _style, "cid": "c", "work": _tmp, "n": 1,
    "plan": _plan(ch, model), "dur": 5.0, "ch": ch, "ingest": {},
}

with _mock.patch.object(_ark_mod, "edit_video",
                        lambda p, **kw: _cap.update(volc=kw)), \
        _mock.patch.object(_mm_mod, "reference_video",
                           lambda s, **kw: _cap.update(h3=kw)), \
        _mock.patch.object(_ve_mod, "_public_url",
                           lambda s, c: "https://cdn/style.mp4"), \
        _mock.patch.object(_ve_mod, "_write_request", lambda *a, **k: None), \
        _mock.patch.object(_ve_mod, "_gen_duration", lambda d, m: 5):
    try:
        from app.services import ark_ingest as _ing
        with _mock.patch.object(_ing, "available", lambda: False):
            _v20_ad._submit(_ctx("volc", "doubao-seedance-2-0-mini-260615"))
    except Exception as e:  # noqa: BLE001
        _cap["volc_err"] = repr(e)
    try:
        _h3_ad._submit(_ctx("minimax", "MiniMax-H3"))
    except Exception as e:  # noqa: BLE001
        _cap["h3_err"] = repr(e)

chk("S10 火山真的把参考视频塞进了请求（公网 URL）",
    _cap.get("volc", {}).get("ref_videos") == ["https://cdn/style.mp4"],
    str(_cap.get("volc_err") or _cap.get("volc", {}).get("ref_videos")))
chk("S10 H3 真的把参考视频塞进了请求（本地 Path 走上传）",
    _cap.get("h3", {}).get("ref_videos") == [_style],
    str(_cap.get("h3_err") or _cap.get("h3", {}).get("ref_videos")))
chk("S10 两家都真的调到了自己的接口（提交逻辑确实在各自文件里）",
    "volc" in _cap and "h3" in _cap, str(list(_cap)))
chk("S10 截风格片段走重编码（实测 copy 切 2.0s 出来 2.067s）",
    "exact=True, audio=False" in
    (_ve_mod.__file__ and Path(_ve_mod.__file__).read_text(encoding="utf-8")), "")
ark = (ROOT / "app" / "services" / "ark.py").read_text(encoding="utf-8")
mm = (ROOT / "app" / "services" / "minimax.py").read_text(encoding="utf-8")
chk("S10 ark.edit_body 接受 ref_videos 并按 reference_video 追加",
    "ref_videos: list[str] | None = None" in ark and 'for u in (ref_videos or [])' in ark, "")
chk("S10 minimax.reference_video 接受 ref_videos",
    "ref_videos: list[Path] | None = None" in mm
    and "for extra in (ref_videos or []):" in mm, "")

# ---------------------------------------------------------------------------

bad = [r for r in rows if not r[1]]
for name, ok, detail in rows:
    print(("  ok   " if ok else "  FAIL ") + name + (f"  [{detail[:200]}]" if not ok else ""))
print(f"\n{len(rows) - len(bad)}/{len(rows)} 通过（零模型调用）")
sys.exit(1 if bad else 0)
