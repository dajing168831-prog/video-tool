# -*- coding: utf-8 -*-
"""H3（MiniMax）Ref2VA 六段式提示词尺子 —— 零费用、零模型调用。

为什么单独一把：三家**平级**，各按各的官方标准（主人 2026-10-26 明确）。
H3 的正文是官方 `h3-prompt-writing` skill 的 `references/ref-en.txt`
（`D:/tmp/official/h3/ref-en.txt`，341 行）：六段 + 四类标签 + 固定的关系标记。
2.0/2.5 的规则一条都不能搬过来（`<主体N>` 与 `<Subject N>` 不是一回事，
中文模板与英文六段也不是一回事）。

用法：
    python scripts/ruler_h3.py --calib     # 官方语料校准（红必须 0）
    python scripts/ruler_h3.py --probes    # 每条规则一对正反样本
    python scripts/ruler_h3.py --current   # 量我们现在编译出来的
    python scripts/ruler_h3.py --history   # 量历史真提交过的 H3 请求
    python scripts/ruler_h3.py --sweep     # 多变数组合（生产形状）

官方完整 Ref2VA 示例只有 **1 份**（ref-en §7），校准样本少 —— 输出里如实写 1/1，
不许拿"空集通过"充数。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACK))
sys.path.insert(0, str(BACK / "scripts"))
REF_EN = Path("D:/tmp/official/h3/ref-en.txt")
CLONE = BACK / "data" / "clone"

H3_MODEL = "MiniMax-H3"

# 🩸 规则本体在 app 里（生产要 import），这里只剩测试代码。
from app.services.models.h3_ref import (  # noqa: F401
    SECTIONS,
    VISIBLE_MARKS,
    AUDIO_MARKS,
    TASK_TYPES,
    fields,
    genre_of,
    _split_sentences,
    RULES,
    QUOTES,
    check,
    ctx_for,
)
def official_prompts() -> list[tuple[str, str, dict]]:
    """官方语料（`D:/tmp/harvest_h3_samples.py` 捞的，去重后 2 份）：

      ① README 的 API 响应示例 —— `[video editing + audio reference + audio reuse]`
         = **编辑母版**，和我们换人/换配音的用法同构；
      ② `ref-en` §7 —— `[reference generation + audio reference]`，纯参考生成。

    整仓只有这 2 份完整 Ref2VA 示例（8 个风格 skill 里没有六段式），
    所以校准分母就是 2 —— 输出里如实写，不拿空集充数。
    """
    idx = Path("D:/tmp/official/h3/official/index.json")
    out = []
    if idx.exists():
        for r in json.loads(idx.read_text(encoding="utf-8")):
            p = (idx.parent / f"{r['sha8']}.txt").read_text(encoding="utf-8")
            edit = "video editing" in (r.get("task_types") or "")
            audio = None
            if edit:
                audio = "reuse" if "audio reuse" in r["task_types"] else "reference"
            tag = "README API 响应示例" if edit else "ref-en §7 完整示例"
            out.append((f"{tag}〔{r['task_types']}〕", p,
                        ctx_for(p, edit_master=edit, audio=audio)))
    if out:
        return out
    # 兜底：索引不在就直接读 ref-en §7（少一份也要能跑）
    txt = REF_EN.read_text(encoding="utf-8")
    i = txt.find("## 7. Complete Example")
    blocks = re.findall(r"```text\n(.*?)```", txt[i:], re.S) if i >= 0 else []
    return [(f"ref-en §7 完整示例 #{k + 1}", b, ctx_for(b))
            for k, b in enumerate(blocks)]


def show(title: str, rows: list[tuple]) -> int:
    print("=" * 78)
    print(title)
    n_red = 0
    for name, p, ctx in rows:
        vs = check(p, ctx)
        red = [v for v in vs if v[1] == "红"]
        n_red += len(red)
        mark = "红" if red else ("黄" if vs else "绿")
        print(f"\n  [{mark}] {name}")
        for v in vs:
            print(f"      {v[1]} {v[0]} {v[2]} ← {v[3]}｜{v[4][0][:90]}")
    print(f"\n{n_red} 条红")
    return n_red


def calib() -> int:
    rows = official_prompts()
    n_red = 0
    for name, p, ctx in rows:
        g = genre_of(p)
        vs = check(p, ctx)
        red = [v for v in vs if v[1] == "红"]
        n_red += len(red)
        print(f"\n[{g}] {name}（适用 {len(RULES)} 条规则）")
        for v in vs:
            print(f"   {v[1]} {v[0]} {v[2]} ← {v[3]}｜{v[4][0][:90]}")
    print(f"\n官方语料校准：{len(rows)} 条，红 {n_red} 条"
          f"（{len(rows) * len(RULES)} 条规则-示例判定）")
    if not rows:
        print("!! 一份官方示例都没抽到 —— 不许当通过")
        return 2
    return 0 if n_red == 0 else 1


# ---------------------------------------------------------------- 正反样本
GOOD = """subject_definitions:
<Video 1> is the source video being edited: it provides the original shot structure, camera movement, on-screen action, cuts and timing.
<Audio 1> is the synchronized audio track of <Video 1>, providing the original ambience and speech.
<Subject 1> is the person in <Picture 1>, with the face, hairstyle, body type and clothing shown there.
<Subject 2> is the person on the left in <Video 1>, and is replaced by <Subject 1>.

summary:
[video editing + audio reuse] The target video is an edited version of <Video 1>. <Subject 2> in <Video 1> is replaced by <Subject 1>.

retention_analysis:
<Subject 1> (every shot where <Subject 2> appears): attribute_transfer - the face, hairstyle, body type and clothing of <Subject 1> stay identical to <Picture 1>.
<Subject 2> (every shot where it appears): partially_preserved - its screen position, action and timing follow <Video 1>, while its identity is replaced by <Subject 1>.
<Video 1> (shot structure, camera, timing): partially_preserved - action, camera and timing follow <Video 1>.
<Audio 1>: partially_copy - the original room tone and speech are reused in the target video.

detailed_description:
The target video is an edited version of <Video 1>. It keeps the visual style, color grade and lighting of <Video 1>.
[Shot 1] <Subject 2> in <Video 1> is replaced by <Subject 1>, who speaks with the same timing. <Subject 1> (S1) says, <d>[Chinese] 我来了.</d>
[Shot 2] At 00:03.000, the shot cuts to a close-up of <Subject 1> (S1), who keeps speaking.

overall_soundscape:
The room tone and ambience from <Audio 1> continue throughout the video.

non_diegetic_music:
N/A"""

PROBES = [
    # E18 坏样本：画面描述里出现官方点名的抽象词（好样本 = GOOD，零命中）
    ("E18", GOOD.replace("It keeps the visual style, color grade and lighting of <Video 1>.",
                         "It keeps the visual style, color grade and lighting of "
                         "<Video 1> for a cinematic look."), GOOD),
    ("E1", GOOD.replace("overall_soundscape:\nThe room tone and ambience from <Audio 1> continue throughout the video.\n\n", ""), GOOD),
    ("E2", GOOD.replace("[video editing + audio reuse] ", ""), GOOD),
    ("E3", GOOD.replace("[video editing + audio reuse]", "[reference generation]"), GOOD),
    ("E4", GOOD.replace("The target video is an edited version of <Video 1>. <Subject 2>",
                        "<Subject 2>"), GOOD),
    ("E5", GOOD.replace("[Shot 2] At 00:03.000,", "[Shot 2]"), GOOD),
    # 🩸 2026-10-30 真机假红回归：`retention_analysis` 里写 `(appears in [Shot 2], [Shot 3])`
    #   是官方示例的写法（`ref-en:325`），不是镜头标题。旧版扫全文 → 这行被判"缺时间戳"，
    #   模型花钱改一轮还是红。这条钉住：好样本里带这种标注**不许响**。
    ("E5", GOOD.replace("[Shot 2] At 00:03.000,", "[Shot 2]"),
     GOOD.replace("<Audio 1>: partially_copy",
                  "<Subject 3> (appears in [Shot 1], [Shot 2], [Shot 3]): "
                  "fully_preserved - kept.\n<Audio 1>: partially_copy")),
    ("E6", GOOD.replace("partially_preserved - its screen position",
                        "mostly_kept - its screen position"), GOOD),
    ("E7", GOOD.replace("partially_preserved - its screen position",
                        "partially_preserved - (S1) screen position"), GOOD),
    ("E8", GOOD.replace("<Subject 1> (S1) says", "<Subject 7> (S7) says"), GOOD),
    ("E9", GOOD.replace("<Subject 2> is the person on the left in <Video 1>, and is replaced by <Subject 1>.",
                        "<Subject 2> is the person on the left in <Video 1>, and is replaced by <Subject 1>.\n"
                        "<Subject 3> is the person on the left in <Video 1>, and is replaced by <Subject 1>."),
     GOOD),
    ("E10", GOOD.replace(" <Subject 1> (S1) says, <d>[Chinese] 我来了.</d>", " <d>[Chinese] 我来了.</d>"), GOOD),
    ("E11", GOOD.replace("<d>[Chinese] 我来了.</d>", "<d>[Chinese] 我来了</d>"), GOOD),
    ("E12", GOOD.replace("The room tone and ambience from <Audio 1> continue throughout the video.",
                         "安静的室内环境声贯穿全片。"), GOOD),
    ("E13", GOOD.replace("The target video is an edited version of <Video 1>. It keeps the visual style, color grade and lighting of <Video 1>.\n[Shot 1]",
                         "[Shot 1]"), GOOD),
    # 声明了 audio reuse 却没有 <Audio 1> 定义 = 指着不存在的素材
    ("E14", GOOD.replace("<Audio 1> is the synchronized audio track of <Video 1>, providing the original ambience and speech.\n",
                         ""), GOOD),
    # 说话人写成「<Video 1> 里那个人」= 未定义主体 + 默认画内（ref-en:266）
    ("E15", GOOD.replace("<Subject 1> (S1) says",
                         "the person in <Video 1> (S1) says"), GOOD),
    # 切点倒退：多插一个时间更早的 [Shot 3]（base-en:86「strictly increasing」）
    ("E16", GOOD.replace(
        "[Shot 2] At 00:03.000, the shot cuts to a close-up of <Subject 1> (S1), "
        "who keeps speaking.",
        "[Shot 2] At 00:03.000, the shot cuts to a close-up of <Subject 1> (S1), "
        "who keeps speaking.\n[Shot 3] At 00:02.500, the shot cuts back to the "
        "wide shot."), GOOD),
    # 环境声写 5 句（base-en:154 上限 4 句）
    ("E17", GOOD.replace(
        "The room tone and ambience from <Audio 1> continue throughout the video.",
        "The room tone continues. The ambience continues. A chair creaks once. "
        "A cup is set down. A page turns."), GOOD),
    # 台词里带 emoji（ref-en:274「remove … emoji」）
    ("E19", GOOD.replace("<d>[Chinese] 我来了.</d>", "<d>[Chinese] 我来了🙂.</d>"), GOOD),
    # 台词里抄进了我们自己的闭合标签 → `<d>` 提前闭合
    ("E20", GOOD.replace("<d>[Chinese] 我来了.</d>", "<d>[Chinese] 我来了</d>.</d>"), GOOD),
    # 台词丢了语言标签（base-en:129「include only the language tag and …」）
    ("E21", GOOD.replace("<d>[Chinese] 我来了.</d>", "<d>我来了.</d>"), GOOD),
    # attribute_transfer 自指：属性来源与被替换对象同号（ref-en:167 "different"）
    ("E22", GOOD.replace("clothing of <Subject 1> stay identical",
                         "clothing of <Subject 2> stay identical"), GOOD),
    # 说话句与 `<d>` 之间没有分隔标点（黄；官方示例 4/4 都有 `,`/`:`）
    ("E23", GOOD.replace("<Subject 1> (S1) says, <d>",
                         "<Subject 1> (S1) says <d>"), GOOD),
    # 🩸 2026-10-30 真机漏出来：agent 交了 9,927 字符，ref 尺子一条长度判据都没有。
    #   `text` ≤7000 是接口硬限制（`api-create:407`），超了 API 直接拒。
    ("E24", GOOD + " extra words." * 600, GOOD),
]


def probes() -> int:
    ok = 0
    for rid, bad, good in PROBES:
        # 🩸 坏样本必须**真的**和好样本不同：`str.replace` 锚串写错时会静默空转，
        # 两边一样 → 规则看着"好样本不响"其实根本没被测到（假绿）。
        if bad == good:
            print(f"!! {rid}  坏样本和好样本一模一样 —— 锚串失效，这条没测到")
            continue
        ctx = ctx_for(bad, edit_master=True, audio="reuse")
        ctx_g = ctx_for(good, edit_master=True, audio="reuse")
        fired_bad = any(v[0] == rid for v in check(bad, ctx))
        fired_good = any(v[0] == rid for v in check(good, ctx_g))
        hit = fired_bad and not fired_good
        ok += 1 if hit else 0
        print(f"{'ok ' if hit else '!! '}{rid}  坏样本{'响' if fired_bad else '哑'} / "
              f"好样本{'误响' if fired_good else '不响'}")
    print(f"\n规则自证：{ok}/{len(PROBES)}")
    return 0 if ok == len(PROBES) else 1


# ---------------------------------------------------------------- 当前输出
def _people(n: int, pos: str) -> list[dict]:
    # 🩸 `missing` = 盘点没给方位（`position` 空串）。2.0/2.5 的穷举都带这一档，
    #   H3 原来没有 —— 而 `ref-en:246` 要求首次清晰出现时写 position，
    #   没有方位时编译器退化成什么形状，正是最该被量的一档。
    posmap = {"clash": ["center"] * n,
              "unique": ["left", "right", "center", "top", "bottom"][:n],
              "missing": [""] * n}
    descs = ["a heavier-set man with hair in a topknot",
             "a young woman with an elaborate updo",
             "a young man in a grey robe",
             "an old man in a dark cloak",
             "a girl in a green dress"]
    return [{"id": f"P{i + 1}", "present": True, "position": posmap[pos][i],
             "desc_en": descs[i], "desc_zh": "",
             "appearances": [{"start": 0.0, "end": 5.0}]} for i in range(n)]


def ctx_audio(chg: dict, audio_ref: bool) -> str | None:
    """原声到底还在不在 —— 只认生产的两条真值，不许我在尺子里手填：

      `video_edit._audio_track`：`original` 模式喂的是**原片整轨**，所以
        「原声还在」= `audio == "original"` **且** 音轨真的传了（`audio_ref`）。
        片源没音轨时 `audio_ref=False`，这时写 `audio reuse` 就是谎报。
      `clone_pipeline.py:305`：「tts 模式原片声音一概不要」。
    """
    mode = (chg.get("audio") or "tts").strip().lower()
    if mode == "original":
        return "reuse" if audio_ref else None
    if audio_ref:
        return "reference"
    return None


def current_cases() -> list[tuple]:
    from app.services import edit_spec

    one = [[{"start": 0.5, "end": 1.8, "text": "我来了", "lang": "zh",
             "speaker": "P1"}]]

    def case(name, chg, n=2, pos="clash", picks=(0,), **kw):
        frame = _people(n, pos)
        picked = [dict(frame[i]) for i in picks]
        slots = ["person" if k == 0 else f"person{k + 1}" for k in range(len(picks))]
        text = edit_spec.compile_prompt(
            "minimax", edit_spec.normalize(chg), model=H3_MODEL,
            source_people=picked, desc_by_id={p["id"]: {"zh": p["desc_zh"],
                                                        "en": p["desc_en"]} for p in frame},
            slots=slots, **kw)
        return (name, text, ctx_for(text, edit_master=True,
                                    audio=ctx_audio(chg, bool(kw.get("audio_ref")))))

    rows = [
        case("单人·换人（默认 tts）", {"person": True, "person_ids": ["P1"]},
             n=1, pos="unique"),
        case("单人·换人（原声保留）", {"person": True, "audio": "original",
                                      "person_ids": ["P1"]}, n=1, pos="unique",
             audio_ref=True),
        case("双人·同方位·换第 1 个", {"person": True, "person_ids": ["P1"]}),
        case("双人·方位唯一·换第 1 个", {"person": True, "person_ids": ["P1"]},
             pos="unique"),
        case("双人·全换", {"person": True, "person_ids": ["P1", "P2"]},
             picks=(0, 1)),
        case("换配音（音色参考）", {"person": True, "audio": "tts",
                                    "person_ids": ["P1"]},
             n=1, pos="unique", audio_ref=True, shot_lines=one),
        case("原声保留 + 换配音", {"person": True, "audio": "original",
                                   "person_ids": ["P1"]},
             n=1, pos="unique", audio_ref=True, shot_lines=one),
        # 🩸 2026-10-29（A2 结构指纹）：上面 7 条**全是单镜**，产出里没有
        #   `[Shot 2] At 00:03.000` —— 而 E5（首个镜头不带时码）/ E16（切点递增）
        #   正好只管多镜。官方 Ref2VA 示例本身就是多镜的。
        #   用例不覆盖 = 真实出片那条路没被 `--current` 量过。
        case("双镜·换人（切点 3.0s）", {"person": True, "person_ids": ["P1"]},
             n=1, pos="unique", shot_cuts=[3.0]),
    ]
    return rows


# ---------------------------------------------------------------- 历史请求
def history() -> int:
    """量**已经提交过**的 H3 请求（钱已花，红只作回溯，不是当前判定）。

    `audio` 给 None：历史请求里看不出当时用户选的是哪个音轨模式，
    拿不准就跳过 E3，不猜。
    """
    rows = []
    for f in sorted(CLONE.glob("*/render/*/triage/request_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        m = str(d.get("model") or "")
        if "h3" not in m.lower() and "minimax" not in m.lower():
            continue
        cid = f.parts[-5]
        rows.append((f"{cid[:8]}/{f.parts[-3][:8]}", d["prompt"],
                     ctx_for(d["prompt"], edit_master=None, audio=None)))
    print("（这 19 条是**已提交**的旧请求 —— 红只作回溯，改不了也已经付过钱）")
    n_red = show("历史真提交过的 H3 请求", rows)
    tally: dict[str, int] = {}
    for _name, p, ctx in rows:
        for v in check(p, ctx):
            if v[1] == "红":
                tally[f"{v[0]} {v[2]}"] = tally.get(f"{v[0]} {v[2]}", 0) + 1
    if tally:
        print("\n按规则汇总：")
        for k, n in sorted(tally.items()):
            print(f"  {n:>2} 条  {k}")
    return n_red


# ---------------------------------------------------------------- 多变数
def sweep_cases() -> list[tuple]:
    one = [[{"start": 0.5, "end": 1.8, "text": "我来了", "lang": "zh", "speaker": "P1"}]]
    two = [[{"start": 0.5, "end": 1.5, "text": "我来了", "lang": "zh", "speaker": "P1"},
            {"start": 2.0, "end": 3.2, "text": "别找我", "lang": "zh", "speaker": "P2"}]]
    return [
        ("单人·换人", {"person": True, "person_ids": ["P1"]}, 1, "unique", (0,), {}),
        ("双人·同方位·换第 1 个", {"person": True, "person_ids": ["P1"]}, 2, "clash", (0,), {}),
        ("双人·方位唯一", {"person": True, "person_ids": ["P1"]}, 2, "unique", (0,), {}),
        ("双人·全换", {"person": True, "person_ids": ["P1", "P2"]}, 2, "clash", (0, 1), {}),
        ("三人·全换", {"person": True, "person_ids": ["P1", "P2", "P3"]}, 3, "clash",
         (0, 1, 2), {}),
        ("单人·1 切点", {"person": True, "person_ids": ["P1"]}, 1, "unique", (0,),
         {"shot_cuts": [3.0]}),
        ("双人·2 切点", {"person": True, "person_ids": ["P1"]}, 2, "unique", (0,),
         {"shot_cuts": [3.0, 6.9]}),
        ("单人·换配音单句", {"person": True, "audio": "tts", "person_ids": ["P1"]},
         1, "unique", (0,), {"audio_ref": True, "shot_lines": one}),
        ("双人·两人各说一句", {"person": True, "audio": "tts",
                              "person_ids": ["P1", "P2"]}, 2, "unique", (0, 1),
         {"audio_ref": True, "shot_lines": two}),
        ("单人·换装", {"person": True, "wardrobe": True, "person_ids": ["P1"],
                       "wardrobe_ids": ["P1"]}, 1, "unique", (0,),
         {"_slots_extra": ["wardrobe"]}),
        # 🩸 2026-10-26（D39 复核历史红）：**首帧延续**以前不在扫描里 ——
        # 历史上那 4 条红（E5 无 `[Shot 1]` / E6 用 `keyframe completion` 当关系标记）
        # 全出自这条路径（2026-10-22 的 a47631b0），修完却没有任何用例守着。
        ("双人·首帧延续", {"person": True, "person_ids": ["P1", "P2"]}, 2, "unique",
         (0, 1), {"boundary_pic": 3}),
        # 🩸 D31：原声保留（喂了原片整轨）→ 前缀要挂 `audio reuse`（`ref-en:145`）
        ("单人·原声保留", {"person": True, "audio": "original",
                           "person_ids": ["P1"]}, 1, "unique", (0,),
         {"audio_ref": True}),
        # 🩸 阴性对照：片源本身没音轨 → 不许写 `audio reuse`（没东西可复用）
        ("单人·原声模式但无音轨", {"person": True, "audio": "original",
                                   "person_ids": ["P1"]}, 1, "unique", (0,), {}),
    ]


def sweep() -> int:
    from app.services import edit_spec

    n_red = 0
    for name, chg, n, pos, picks, kw in sweep_cases():
        frame = _people(n, pos)
        picked = [dict(frame[i]) for i in picks]
        slots = ["person" if k == 0 else f"person{k + 1}" for k in range(len(picks))]
        slots += list(kw.pop("_slots_extra", []))
        text = edit_spec.compile_prompt(
            "minimax", edit_spec.normalize(chg), model=H3_MODEL,
            source_people=picked,
            desc_by_id={p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]}
                        for p in frame}, slots=slots, **kw)
        ctx = ctx_for(text, edit_master=True,
                      audio=ctx_audio(chg, bool(kw.get("audio_ref"))))
        vs = check(text, ctx)
        red = [v for v in vs if v[1] == "红"]
        n_red += len(red)
        print(f"\n  [{'红' if red else ('黄' if vs else '绿')}] {name}")
        for v in vs:
            print(f"      {v[1]} {v[0]} {v[2]} ← {v[3]}｜{v[4][0][:90]}")
    print(f"\n多变数扫描（H3）：{len(sweep_cases())} 个组合（零模型调用）")
    print(f"  红 {n_red} 条")
    return 0 if n_red == 0 else 1


# ---------------------------------------------------------------- 多维穷举
# 🩸 2026-10-29：H3 原来只有 `--sweep` 的 13 个组合，而尺子有 23 条规则 ——
#   13 个组合摊不满 23 条规则，大部分规则**从来没有被真实产出量过**，
#   `--sweep` 全绿是"没喂够"，不是"经得起推敲"。
#   这一节照 2.0/2.5 的口径补：一次只动一个变量，看产出有没有破口。

_PLACEHOLDER = re.compile(r"<[^<>]{1,24}>")
_LABEL_OK = re.compile(
    r"<(?:(?:Video|Picture|Subject|Audio)\s*\d+|d|/?d)>|</d>")


def _struct(p: str) -> list[str]:
    """结构判据：不许把模板占位符/自造标签发出去。

    🩸 只查这一件事 —— 六段齐全/顺序由 E1 管，不在这里重复报。
    """
    bad = []
    for m in _PLACEHOLDER.finditer(p):
        s = m.group(0)
        if _LABEL_OK.fullmatch(s):
            continue
        bad.append(f"残留占位符/未定义标签 {s}")
        if len(bad) >= 3:
            break
    return bad


def _picmap(p: str, slots) -> list[str]:
    """`<Picture N>` 与真正发出去的张数必须对得上（2.5 的 W1 同款）。

    🩸 两个方向都查：引用了没发的图 = 模型拿不到素材只能瞎编；
    发了却没提 = 用户白传一张图，钱花了没效果。
    """
    n_pic = sum(1 for s in slots if not str(s).startswith("audio"))
    used = {int(x) for x in re.findall(r"<Picture\s*(\d+)>", p)}
    bad = []
    over = sorted(x for x in used if x > n_pic)
    if over:
        bad.append(f"引用了没发出去的 <Picture {over[0]}>（本次只发 {n_pic} 张）")
    miss = sorted(set(range(1, n_pic + 1)) - used)
    if miss and n_pic:
        bad.append(f"发了 {n_pic} 张图，<Picture {miss[0]}> 一次都没提")
    return bad


def _mk(name, chg, *, n=1, pos="unique", picks=(0,), slots_extra=(),
        audio_ref=False, **kw):
    """编译一条 H3 提示词，连同判据要用的上下文一起打包。

    编译抛 `EditError`（欠素材/欠输入）不算破口 —— 那是生产闸的正确行为，
    这里返回 `text=None` 让 `_judge` 记成「闸拦」。
    """
    from app.services import edit_spec

    frame = _people(n, pos)
    picked = [dict(frame[i]) for i in picks]
    slots = ["person" if k == 0 else f"person{k + 1}" for k in range(len(picks))]
    slots += list(slots_extra)
    spec = edit_spec.normalize(chg)
    # 🩸 生产路径上 `video_edit._prepare` 会先跑 `pre_compile`：H3 把中文自由文本
    #   **翻译成英文**再编译。穷举零费用零联网，翻不了；等价做法是直接跑那道
    #   兜底闸 —— 翻不出来就该拦，拦住了记「闸拦」，拦不住才是中文漏进正文的破口。
    from app.services.models import h3_compile
    try:
        h3_compile.require_english_extra(spec)
    except Exception as e:  # noqa: BLE001
        return (name, None, f"{type(e).__name__}: {e}", frame, slots)
    try:
        text = edit_spec.compile_prompt(
            "minimax", spec, model=H3_MODEL,
            source_people=picked,
            desc_by_id={p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]}
                        for p in frame},
            slots=slots, audio_ref=audio_ref, **kw)
    except Exception as e:  # noqa: BLE001
        return (name, None, f"{type(e).__name__}: {e}", frame, slots)
    ctx = ctx_for(text, edit_master=True, audio=ctx_audio(chg, audio_ref))
    return (name, text, ctx, frame, slots)


def _judge(rows, title: str, *, expect=None) -> tuple[int, int, int]:
    """跑一组，返回 (破口数, 闸拦数, 组合数)。

    口径与 2.0/2.5 一致：**尺子红 / 结构失败** = 破口；
    编译阶段就被 EditError 拦住 = 正确行为，单列不计数（但不能悄悄算绿）。
    """
    from app.services import video_edit
    from app.services.models import h3_compile

    n_bad = n_gate = 0
    seen = set()
    for name, text, ctx, frame, slots in rows:
        if text is None:
            n_gate += 1
            continue
        seen.add(text)
        red = [v for v in check(text, ctx) if v[1] == "红"]
        bad = _struct(text) + _picmap(text, slots)
        if red or bad:
            blocked = False
            try:
                video_edit.require_identifiable_h3(
                    {"people": frame}, slots, locator=h3_compile.h3_orig_locator)
            except video_edit.EditError:
                blocked = True
            if blocked:
                n_gate += 1
                continue
            n_bad += 1
            print(f"\n  [破口] {name}")
            for v in red:
                print(f"      {v[1]} {v[0]} {v[2]} ← {v[3]}｜{str(v[4][0])[:70]}")
            for b in bad:
                print(f"      ✗ {b}")
            print(f"         {text[:160]}")
    if expect is not None and len(rows) != expect:
        print(f"  ✗ {title}：跑了 {len(rows)} 条，期望 {expect} 条（空集不算通过）")
        n_bad += 1
    print(f"  {'✅' if n_bad == 0 else '❌'} {title}：{len(rows)} 条"
          f"（破口 {n_bad} / 闸拦 {n_gate} / 去重后 {len(seen)} 种输出）")
    return n_bad, n_gate, len(rows)


def _e1_person() -> list[tuple]:
    """E1 换人主路径：人数 × 方位形态 × 勾选子集。"""
    rows, seen = [], set()
    for n in (1, 2, 3, 4):
        for pos in ("unique", "clash", "missing"):
            for picks in ((0,), tuple(range(n)), (0, n - 1)):
                picks = tuple(dict.fromkeys(picks))
                if (n, pos, picks) in seen:
                    continue
                seen.add((n, pos, picks))
                frame = _people(n, pos)
                ids = [frame[i]["id"] for i in picks]
                rows.append(_mk(f"n={n}·{pos}·{'+'.join(ids)}",
                                {"person": True, "person_ids": ids},
                                n=n, pos=pos, picks=picks))
    return rows


def _e2_matrix() -> list[tuple]:
    """E2 改动面全幂集（8 个开关，风格参考图与风格参考视频互斥）。"""
    keys = ["person", "product", "scene", "wardrobe", "style",
            "style_ref", "style_video", "extra"]
    rows = []
    for mask in range(1 << len(keys)):
        on = {k for i, k in enumerate(keys) if mask >> i & 1}
        if "style_ref" in on and "style_video" in on:
            continue
        chg: dict = {}
        slots_extra: list = []
        kw: dict = {}
        if "person" in on:
            chg.update(person=True, person_ids=["P1"])
        if "product" in on:
            chg.update(product=True, product_desc="a white ceramic cup")
            slots_extra.append("product")
        if "scene" in on:
            chg.update(scene=True, scene_desc="a rainy neon street at night")
            slots_extra.append("scene")
        if "wardrobe" in on:
            chg.update(wardrobe=True, wardrobe_ids=["P1"])
            slots_extra.append("wardrobe")
        if "style" in on:
            chg["style"] = "anime"
        if "style_ref" in on:
            chg["style_ref"] = True
            slots_extra.append("style_ref")
        if "style_video" in on:
            chg["style_video"] = True
            kw["style_video"] = True
        if "extra" in on:
            chg["extra"] = "add a small orange cat on the chair"
        # 🩸 只有勾了换人才传人物槽位：`_mk` 是按 `picks` 造槽位的，
        #   勾选里没有 person 却塞一个 person 槽 → 会发出一张提示词从不引用的图，
        #   `_picmap` 当场判「发了却没提」（第一版就是这么报了一片假红）。
        rows.append(_mk("+".join(sorted(on)) or "(空规格)", chg,
                        n=2, pos="unique",
                        picks=(0,) if "person" in on else (),
                        slots_extra=slots_extra, **kw))
    return rows


def _e3_audio() -> list[tuple]:
    """E3 音轨模式 × 有没有音轨 × 台词形态（含语种）。"""
    def lines(lang: str, text: str):
        return [[{"start": 0.5, "end": 1.8, "text": text,
                  "lang": lang, "speaker": "P1"}]]

    two = [[{"start": 0.5, "end": 1.5, "text": "我来了", "lang": "zh",
             "speaker": "P1"},
            {"start": 2.0, "end": 3.2, "text": "别找我", "lang": "zh",
             "speaker": "P2"}]]
    shapes = [("无台词", None), ("中文单句", lines("zh", "我来了")),
              ("英文单句", lines("en", "I am here")),
              ("日文单句", lines("ja", "私はここにいる")),
              ("两人各一句", two)]
    rows = []
    for mode in ("tts", "original", "mix"):
        for ref in (False, True):
            for label, ln in shapes:
                kw = {"audio_ref": ref}
                if ln is not None:
                    kw["shot_lines"] = ln
                chg = {"person": True, "person_ids": ["P1"], "audio": mode}
                rows.append(_mk(f"{mode}·音轨{'有' if ref else '无'}·{label}",
                                chg, n=2, pos="unique", picks=(0,), **kw))
    return rows


def _e4_cuts() -> list[tuple]:
    """E4 段内切点：0/1/2/3 刀（E5 首镜无时码、E16 切点严格递增）。"""
    return [_mk(f"切点 {len(cuts)} 刀" if cuts else "无切点",
                {"person": True, "person_ids": ["P1"]},
                n=1, pos="unique", picks=(0,), shot_cuts=list(cuts))
            for cuts in ((), (3.0,), (3.0, 6.9), (3.0, 6.9, 9.5))]


def _e12_extra() -> list[tuple]:
    """E12 用户补充说明矩阵：内容 × 形态。"""
    bodies = ["add a small orange cat on the chair",
              "把背景换成雨夜街道",
              "add {a ringing phone} on the desk",
              "add <a red door> in the wall",
              "add a cat\nand a dog",
              "【原视频职责】乱写的内容",
              "add a cat. Add a dog."]
    rows = []
    for i, b in enumerate(bodies):
        for person in (False, True):
            chg = {"extra": b}
            if person:
                chg.update(person=True, person_ids=["P1"])
            rows.append(_mk(f"extra#{i}·{'含换人' if person else '纯补充'}",
                            chg, n=2, pos="unique",
                            picks=(0,) if person else ()))
    return rows


def _e13_freetext() -> list[tuple]:
    """E13 其余自由文本源：场景/产品/盘点英文描述。"""
    rows = [
        _mk("场景·普通", {"scene": True, "scene_desc": "a rainy neon street"},
            n=1, pos="unique", picks=(), slots_extra=["scene"]),
        _mk("场景·多行", {"scene": True, "scene_desc": "a rainy street\nat night"},
            n=1, pos="unique", picks=(), slots_extra=["scene"]),
        _mk("场景·中英文混", {"scene": True, "scene_desc": "雨夜街道，neon"},
            n=1, pos="unique", picks=(), slots_extra=["scene"]),
        _mk("产品·普通", {"product": True, "product_desc": "a white cup"},
            n=1, pos="unique", picks=(), slots_extra=["product"]),
        _mk("产品·多逗号", {"product": True,
                            "product_desc": "a white cup, with a gold handle"},
            n=1, pos="unique", picks=(), slots_extra=["product"]),
        _mk("产品·带括号", {"product": True, "product_desc": "a {white} cup"},
            n=1, pos="unique", picks=(), slots_extra=["product"]),
    ]
    # 盘点描述只给中文 → H3 读 desc_en，这一档要看它退化成什么
    for label, zh, en in (("英文描述", "", "a man in a white shirt"),
                          ("中文描述", "穿白衬衫的男人", ""),
                          ("空描述", "", "")):
        frame = _people(2, "clash")
        frame[0] = dict(frame[0], desc_zh=zh, desc_en=en)
        frame[1] = dict(frame[1], desc_zh=zh, desc_en=en)
        from app.services import edit_spec
        try:
            text = edit_spec.compile_prompt(
                "minimax", edit_spec.normalize({"person": True,
                                                "person_ids": ["P1"]}),
                model=H3_MODEL, source_people=[dict(frame[0])],
                desc_by_id={p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]}
                            for p in frame},
                slots=["person"])
        except Exception as e:  # noqa: BLE001
            rows.append((f"描述·{label}", None, f"{type(e).__name__}: {e}",
                         frame, ["person"]))
            continue
        rows.append((f"描述·{label}", text,
                     ctx_for(text, edit_master=True, audio=None), frame, ["person"]))
    return rows


def _e7_ablation() -> int:
    """单变量消融：每个开关打开后，产出必须真的变样（否则开关没落点）。"""
    from app.services import edit_spec

    def text_of(chg, slots, **kw):
        return edit_spec.compile_prompt(
            "minimax", edit_spec.normalize(chg), model=H3_MODEL,
            source_people=_people(2, "unique")[:1], slots=list(slots), **kw)

    P1 = {"person": True, "person_ids": ["P1"]}
    # 🩸 「原声」这一档必须**两边都喂音轨**：不喂音轨时 `reuse_audio` 本来就该是
    #   False（片源没声音可复用），tts 和 original 编出来一模一样是对的。
    #   第一版只给开关侧传 audio_ref，于是报了一条"没落点"的假红。
    # 每条 = (说明, 打开这个开关要加什么, 关闭时的编译参数, 槽位)
    # 加进去的键按归属自动分流：规格键进 `change`，其余（shot_cuts/boundary_pic/
    # audio_ref）进 `compile_prompt` 的关键字参数。
    _SPEC_KEYS = {"product", "product_desc", "scene", "scene_desc",
                  "style", "audio", "extra", "wardrobe"}
    cases = [
        ("切点", {"shot_cuts": [3.0]}, {}, ["person"]),
        ("首帧", {"boundary_pic": 2}, {}, ["person"]),
        ("产品", {"product": True, "product_desc": "a white cup"}, {},
         ["person", "product"]),
        ("场景", {"scene": True, "scene_desc": "a rainy street"}, {},
         ["person", "scene"]),
        ("风格词", {"style": "anime"}, {}, ["person"]),
        ("原声", {"audio": "original"}, {"audio_ref": True}, ["person"]),
        ("补充说明", {"extra": "add a cat"}, {}, ["person"]),
    ]
    n = 0
    for label, add, base_kw, slots in cases:
        on_chg, on_kw = dict(P1), dict(base_kw)
        for k, v in add.items():
            (on_chg if k in _SPEC_KEYS else on_kw)[k] = v
        try:
            before = text_of(P1, slots, **base_kw)
            after = text_of(on_chg, slots, **on_kw)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ 消融 {label} 编译失败：{e}")
            n += 1
            continue
        if after == before:
            print(f"  ✗ 消融 {label}：开关打开后产出**一个字都没变**（没落点）")
            n += 1
    print(f"  {'✅' if n == 0 else '❌'} E7 单变量消融：{len(cases)} 个开关（无落点 {n}）")
    return n


def exhaustive() -> int:
    print("=" * 78)
    print("MiniMax H3 多维度穷举（全部本地编译，零模型调用、零费用）\n")
    tot_bad = tot_gate = tot_n = 0
    for rows, title, exp in (
            (_e1_person(), "E1 换人主路径（n × 方位 × 勾选子集）", 27),
            (_e2_matrix(), "E2 改动面全幂集（8 开关，风格图×风格视频互斥）", 192),
            (_e3_audio(), "E3 音轨 × 有无音轨 × 台词形态", 30),
            (_e4_cuts(), "E4 段内切点", 4),
            (_e12_extra(), "E12 用户补充说明矩阵", 14),
            (_e13_freetext(), "E13 其余自由文本源", 9)):
        b, g, n = _judge(rows, title, expect=exp)
        tot_bad += b
        tot_gate += g
        tot_n += n
    tot_bad += _e7_ablation()
    print("\n" + "=" * 78)
    print(f"总账：{tot_n} 个编辑组合 + 单变量消融｜破口 {tot_bad} 条 / "
          f"闸拦 {tot_gate} 条（闸拦 = 正确拦截，不算破口）")
    return 0 if tot_bad == 0 else 1


def main() -> int:
    from _model_lock import guard
    guard("h3")
    if "--calib" in sys.argv:
        return calib()
    if "--probes" in sys.argv:
        return probes()
    if "--current" in sys.argv:
        return 0 if show("现在我们编译出来的 H3 输出", current_cases()) == 0 else 1
    if "--history" in sys.argv:
        return history()
    if "--sweep" in sys.argv:
        return sweep()
    if "--exhaustive" in sys.argv:
        return exhaustive()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
