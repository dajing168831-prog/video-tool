# -*- coding: utf-8 -*-
"""复刻「逐段编辑指令」的 **H3 版** 判据 —— 零费用，全程 `post` 桩，不调模型。

和 `p30_check`（火山 2.5 那套）平级、**不共用断言**：两家模板不通用
（2.5 = 中文正文 + 五段标记；H3 = 英文 Ref2VA 六段式 + `<Picture N>`）。

验六件事：
  1. **分派**：H3 的适配器挂的是 `h3_agent`，2.5 挂的是 `clone_agent`，不是同一个；
  2. **规格书**：H3 版用 `<Picture N>` 写、并要求"写指令用英文"；
     默认那版（2.5）仍写 `@图片N` —— 两家互不污染；
  3. **硬闸有鉴别力**：每条规则一对「好样本放行 / 坏样本必红」；
     并且台词里的中文**不许**误伤（`<d>` 内保留原语言是官方允许的）；
  4. **签名**：同输入稳、换图/换型号就变、出片时的 `voice_lines` 不影响；
  5. **落盘互不相认**：`h3` 写的文件 2.5 不认，2.5 写的 H3 不认；
  6. **交付 → 落盘 → 命中缓存**；模型连交两次不合格 → 抛错（调用方回落代码编译）。

用法： python scripts/p46_check.py --model h3
"""
from __future__ import annotations

import json
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

sel_or_exit(only="h3")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_agent as A25  # noqa: E402
from app.services import clone_brief as B  # noqa: E402
from app.services import h3_agent as A  # noqa: E402
from app.services import models  # noqa: E402

_n = _fail = 0


def check(name: str, got, want) -> None:
    global _n, _fail
    _n += 1
    ok = got == want
    if not ok:
        _fail += 1
    print(f"{'✅' if ok else '🔴'} {name}"
          + ("" if ok else f"\n     实际 {got!r} / 期望 {want!r}"))


# ---------------------------------------------------------------- fixture

REC = {
    "source": {"duration": 20.0, "width": 1080, "height": 1920, "fps": 30.0},
    "shots": [
        {"i": 0, "start": 0.0, "end": 8.0},
        {"i": 1, "start": 8.0, "end": 14.0},
        {"i": 2, "start": 14.0, "end": 20.0},
    ],
    "voice_lines": [],
    "speech": {"lang": "zh", "segments": [
        {"start": 1.0, "end": 3.0, "text": "第一句台词"},
        {"start": 15.0, "end": 17.0, "text": "第二句台词"},
    ]},
}

INV = {
    "people": [
        {"id": "P1", "main": True, "desc_zh": "画面中央的男性，黑色短发，深色外套",
         "desc_en": "a man in the center, short black hair, dark jacket",
         "appearances": [{"start": 0.0, "end": 20.0}]},
    ],
    "_meta": {},
}

SPEC = {
    "change": {"person": True, "person_ids": ["P1"]},
    "audio": "original",
    "resolution": "auto",
}

PLAN = {
    "ch": "minimax",
    "model": "MiniMax-H3",
    "spec": SPEC,
    "inventory": INV,
    "slots": ["person"],
    "ordered": ["D:/tmp/p1.jpg"],
    "audio_ref": True,
    "person_ids": ["P1"],
    "person_asset": "",
    "look": {},
    "looks": {},
}

SPANS = [(0.0, 10.0), (10.0, 20.0)]

#: 合格样本 = **照官方 Ref2VA 骨架填槽位**（`ref-en:307-338` 的完整案例形态），
#: 不是自己编的格式。六段齐全、标号全定义、关系标记用官方固定值。
GOOD = """subject_definitions:
<Video 1> is the source video being edited: it provides the original shot structure, camera movement, on-screen action, cuts and timing.
<Subject 1> is the man in <Picture 1>, with short black hair and a dark jacket. The scene, background, lighting, and image style must not be inherited from <Picture 1>; they come from <Video 1>.
<Subject 2> is the man in the center of <Video 1>, and is replaced by <Subject 1>.
<Audio 1> is the synchronized audio track of <Video 1> and is reused in the target video.

summary:
[video editing + audio reuse] The target video is an edited version of <Video 1>. <Subject 2> is replaced by <Subject 1>, while the background, props and timing stay unchanged.

retention_analysis:
<Video 1> (cut and pacing structure): fully_preserved - the shot order, camera movement and cut times are retained.
<Subject 1> (every shot where <Subject 2> appears): attribute_transfer - the face, hairstyle, body type and clothing of <Subject 1> stay identical to <Picture 1> and replace those of <Subject 2>.
<Subject 2> (every shot where they appear): partially_preserved - their screen position, action and timing follow <Video 1>, while their identity is replaced by <Subject 1>.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.

detailed_description:
The target video is in a realistic live-action style with the same framing and lighting as <Video 1>.
[Shot 1] The shot opens on <Subject 2>, the man in the center of <Video 1>, walking forward. <Subject 1> replaces his face, hairstyle, body type and clothing while his position, action and timing follow <Video 1>. The original audio <Audio 1> continues unchanged.
[Shot 2] At 00:08.000, the shot cuts to a closer view of the same man, and the camera movement of <Video 1> is preserved.

overall_soundscape:
The ambience and physical sounds of <Audio 1> continue throughout the target video.

non_diegetic_music:
N/A"""


def red_of(brief: dict, prompt: str) -> list[str]:
    return A.check(brief, [{"index": 1, "prompt": prompt}, {"index": 2, "prompt": prompt}])


def main() -> int:
    brief = B.build(PLAN, REC, SPANS)

    print("== ① 分派：两家各挂各的 agent ==")
    ad_h3 = models.adapter_for(model="MiniMax-H3")
    ad_25 = models.adapter_for(model="doubao-seedance-2-5-260628")
    check("H3 的 agent 是 h3_agent", ad_h3.agent is not None and ad_h3.agent() is A, True)
    check("2.5 的 agent 是 clone_agent",
          ad_25.agent is not None and ad_25.agent() is A25, True)
    check("两家不是同一份实现", ad_h3.agent() is ad_25.agent(), False)
    check("H3 四档都走 H3 的 agent",
          all(models.adapter_for(model=m).agent() is A
              for m in ("MiniMax-H3", "MiniMax-H3-Max",
                        "MiniMax-H3-Lite", "MiniMax-H3-Highspeed")), True)

    print("\n== ② 规格书：标号随家变，事实只有一份 ==")
    t_h3 = A.brief_text(brief)
    t_25 = B.as_text(brief)
    check("H3 版用 <Picture 1> 写图号", "<Picture 1>" in t_h3, True)
    check("H3 版不用 @图片N", "@图片" in t_h3, False)
    check("H3 版音频写成 <Audio 1>", "<Audio 1>" in t_h3, True)
    check("默认版（2.5）仍是 @图片1", "@图片1" in t_25, True)
    # 那句「写指令用 X」只在盘点给了逐镜画面时才出现 —— 造一份带 look 的规格书来验。
    b2 = dict(brief, segments=[dict(brief["segments"][0], look="a man walks in")])
    check("H3 版要求写英文", "写指令用英文" in A.brief_text(b2), True)
    check("默认版（2.5）仍要求写中文", "写指令用中文" in B.as_text(b2), True)
    check("两家看到的事实一样（段数）",
          t_h3.count("### 第 ") == t_25.count("### 第 ") == len(SPANS), True)

    # 🩸 目标长什么样：H3 要写"要跟随的主要特征"，不给就会瞎编
    #   （2026-11-01 实测：上传的男性照片被写成 "female warrior"）。
    b3 = A.as_brief(dict(PLAN, looks={"person": {"en": "short black hair, a grey T-shirt"}}),
                    REC, SPANS)
    check("换人参考图的外观进了 H3 规格书",
          "short black hair, a grey T-shirt" in A.brief_text(b3), True)
    check("这段只给 H3（2.5 的正文里没有）",
          "short black hair" in B.as_text(b3), False)
    check("目标外观变了 → H3 签名跟着变", A.signature(b3) != A.signature(brief), True)

    # 🩸 性别：官方 `base-en:129` 把 gender 列为主体身份信息之一。
    #   不给 → agent 只能沿用原片那个人的性别（实测把男性照片写成 female warrior）。
    look_m = {"en": "short black hair, a black T-shirt", "gender": "male"}
    b4 = A.as_brief(dict(PLAN, looks={"person": look_m}), REC, SPANS)
    check("看得出的性别写进规格书", "（男性）" in A.brief_text(b4), True)
    b5 = A.as_brief(dict(PLAN, looks={"person": dict(look_m, gender="unspecified")}),
                    REC, SPANS)
    check("看不出时明说「看不出」，不猜",
          "（性别看不出）" in A.brief_text(b5)
          and "（男性）" not in A.brief_text(b5), True)
    b6 = A.as_brief(dict(PLAN, looks={"person": {"en": "short black hair"}}), REC, SPANS)
    check("老描述没有性别字段 → 也不编一个", "（男性）" in A.brief_text(b6), False)

    # 🩸 2026-11-01 主人：「上传了定妆图和没定妆图肯定有区别的，绝对不能混一起。」
    #   有图 → 外观交给 <Picture N>（`ref-en:57`）；没图 → 外观来自原片本身（`ref-en:314`）。
    #   这两条路必须各说各的，不是同一段话换个主语。
    t_has = A.brief_text(b3)                       # 有定妆图 + 有外观描述
    t_nop = A.brief_text(                          # 没勾换人 = 压根没有定妆图
        A.as_brief(dict(PLAN, slots=[], ordered=[], looks={}, person_ids=[],
                        spec={"audio": "original",
                              "change": {"person": False}}), REC, SPANS))
    # 🩸 2026-11-01 反转：旧断言是「不写五官」—— 那是自造规则。
    #   官方 `h3-video-prompt-template.md:20` 明写 `Lock exact face, hairstyle,
    #   glasses if present, facial proportions, body identity`（中文版 `:42`
    #   「必须保留脸、人脸比例」），`ref-en:37` 要的是 main features to follow。
    #   换人时脸不写 = 模型没有锚点，只会照原片那张脸继续走（实测 bestSim 0.177）。
    def _look_rule_ok(text: str) -> bool:
        """换人那段必须覆盖官方 character reference card 的四件事：

        · `music-video/SKILL.md:114`：identity / **facial aura** / hairstyle /
          **clothing silhouette** / proportions / posture —— 面部气质和服装轮廓
          是 v3 时漏掉的两项（v3 只补了脸）；
        · `co-op/SKILL.md:24`：**Do not inherit** 原图的光照/画风/写实度。
        """
        return all([
            "换人参考图里那个人" in text,
            "<Picture N>" in text,
            "面部气质" in text,
            "服装轮廓" in text,
            "Do not inherit" in text,
            "不要把五官/脸型写进" not in text,
        ])

    check("有定妆图 → 覆盖角色卡六项（含面部气质/服装轮廓）+ 明说**不继承**原图",
          _look_rule_ok(t_has), True)
    # 成对探针：v3 那版（只补了脸、没有面部气质和「不继承」）必须被判红。
    check("反向对照：v3 措辞（只写脸，缺气质/轮廓/不继承）必须被判红",
          _look_rule_ok("换人参考图里那个人，外观交给 <Picture N>，"
                        "写脸型轮廓和最显著的 1–2 个五官特征。"), False)
    check("没有定妆图 → 明说外观来自原片，且不出现换人参考图那段",
          "本单**没有**定妆参考图" in t_nop, True)
    check("两条路不串味：没图的规格书里没有换人参考图那段",
          "换人参考图里那个人" in t_nop, False)

    print("\n== ③ 硬闸：好样本放行 ==")
    check("合格样本 0 红", A.check(brief, [{"index": 1, "prompt": GOOD},
                                          {"index": 2, "prompt": GOOD}]), [])
    check("台词里的中文不误伤（官方允许 <d> 保留原语言）",
          A.check(brief, [{"index": 1, "prompt": GOOD.replace(
              "<Audio 1> continues unchanged.",
              '<Audio 1> continues unchanged, and he says, <d>[Chinese] 你好</d>.')},
              {"index": 2, "prompt": GOOD}]), [])

    # 🩸 换人的写法交给 skill 自己定，这里**不设**换人专属闸。
    #   2026-11-01 曾设过「subject_definitions 必须写 `is replaced by`」的闸，
    #   那个句式是自造的（官方 `ref-en` / `base-en` / skill references 四份
    #   文件里 0 次出现），而且逼 agent 把原片那个人的外观写进提示词。
    #   换人样本仍要过**其余全部**格式闸 —— 这条守着"别误伤"。
    check("换人样本（GOOD）放行",
          A.check(b3, [{"index": 1, "prompt": GOOD},
                       {"index": 2, "prompt": GOOD}]), [])

    print("\n== ③ 硬闸：坏样本必红（成对探针）==")
    # 🩸 `ref-en:278`：retention_analysis 里不写 (Sx)。成对验：好样本放行、坏样本必红。
    ret_bad = GOOD.replace("<Audio 1>: fully_copy -", "<Audio 1> (S1): fully_copy -")
    check("retention 里写了 (S1) → 红（官方 :278）",
          any("(Sx)" in r or "说话人号" in r for r in red_of(b3, ret_bad)), True)
    check("retention 没写 (Sx) → 不误伤（GOOD 本身）",
          any("说话人号" in r for r in red_of(
              b3, [{"index": 1, "prompt": GOOD}, {"index": 2, "prompt": GOOD}])), False)
    check("少一段 → 报段数不对",
          any("段数对不上" in r for r in A.check(
              brief, [{"index": 1, "prompt": GOOD}])), True)
    check("缺 detailed_description → 红",
          any("缺段" in r and "detailed_description" in r for r in red_of(
              brief, GOOD.replace("detailed_description:", "画面描述:"))), True)
    check("六段顺序错 → 红",
          any("顺序不对" in r for r in red_of(
              brief, GOOD.replace("subject_definitions:", "@@TMP@@")
              .replace("summary:", "subject_definitions:")
              .replace("@@TMP@@", "summary:"))), True)
    check("正文写中文 → 红",
          any("正文里有中文" in r for r in red_of(
              brief, GOOD.replace("[Shot 1] The shot opens",
                                  "[Shot 1] 镜头从"))), True)
    check("用了没定义的 <Subject 3> → 红",
          any("没定义的标号" in r for r in red_of(
              brief, GOOD.replace("<Audio 1> continues unchanged.",
                                  "<Audio 1> continues unchanged. <Subject 3> smiles."))), True)
    check("retention 缺 <Audio 1> 那行 → 红",
          any("缺 <Audio 1> 那一行" in r for r in red_of(
              brief, GOOD.replace(
                  "<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target "
                  "video's complete final audio track.\n", ""))), True)
    check("关系标记不是官方固定值 → 红",
          any("关系标记不是官方固定值" in r for r in red_of(
              brief, GOOD.replace("fully_copy - ", "keep_as_is - "))), True)
    check("引用不存在的图号 → 红",
          any("不存在的图号" in r for r in red_of(
              brief, GOOD.replace("<Picture 1>", "<Picture 9>", 1))), True)

    # 🩸 2026-11-01 实测：不写「参考图只管角色」那句那一版，脸换对了、**场景整间被搬走**
    #   （古风庭院顶掉了原片的明亮客厅）。成对：GOOD 里有这句 → 0 红（上面已验）；
    #   拿掉 → 必须红；改词（must not → should not）→ 也必须红（要的是原样，不是"意思到了"）。
    _iso = (" The scene, background, lighting, and image style must not be inherited "
            "from <Picture 1>; they come from <Video 1>.")
    check("那句「参考图只管角色」在 GOOD 里（成对的下半）", _iso in GOOD, True)
    check("删掉那句 → 红",
          any("参考图只管角色" in r for r in red_of(b3, GOOD.replace(_iso, ""))), True)
    check("把那句改写（must not → should not）→ 红",
          any("参考图只管角色" in r for r in red_of(
              b3, GOOD.replace("must not be inherited", "should not be inherited"))), True)
    check("summary 缺官方那句「edited version of <Video 1>」→ 红",
          any("缺官方那句话" in r for r in red_of(
              brief, GOOD.replace(" The target video is an edited version of "
                                  "<Video 1>.", ""))), True)
    check("任务类型不是 video editing → 红",
          any("`video editing`" in r for r in red_of(
              brief, GOOD.replace("[video editing + audio reuse]",
                                  "[reference generation]"))), True)
    check("带原片音轨却没 <Audio 1> → 红",
          any("<Audio 1>" in r for r in red_of(
              brief, GOOD.replace("<Audio 1>", "the original audio"))), True)
    check("残留占位符 → 红",
          any("占位符" in r for r in red_of(
              brief, GOOD.replace("the man in the center", "<原对象>", 1))), True)
    check("空的一段 → 红",
          any("第 2 段是空的" in r for r in A.check(
              brief, [{"index": 1, "prompt": GOOD}, {"index": 2, "prompt": "  "}])), True)

    print("\n== ④ 签名 ==")
    s1 = A.signature(brief)
    check("同输入两次签名相同", A.signature(B.build(PLAN, REC, SPANS)), s1)
    check("换参考图 → 签名变",
          A.signature(B.build(dict(PLAN, ordered=["D:/tmp/p2.jpg"]), REC, SPANS)) != s1, True)
    check("换型号 → 签名变",
          A.signature(B.build(dict(PLAN, model="MiniMax-H3-Max"), REC, SPANS)) != s1, True)
    check("与 2.5 的签名算法互不相干（同一份规格书也不同）",
          A25.signature(B.build(dict(PLAN, model="doubao-seedance-2-5-260628"),
                                REC, SPANS)) != s1, True)
    rec_render = dict(REC, voice_lines=[
        {"start": 1.0, "end": 3.0, "text": "第一句台词", "speaker": "P1"}])
    check("出片时 rec 多出 voice_lines → 签名不变",
          A.signature(B.build(PLAN, rec_render, SPANS)), s1)

    print("\n== ⑤ 交付 → 落盘 → 命中缓存（桩，零费用）==")
    from app.services import clone_store as store

    tmp = Path(tempfile.mkdtemp(prefix="p46_", dir="D:/tmp"))
    old_dir = store.task_dir
    store.task_dir = lambda cid: (tmp / cid)  # noqa: ARG005
    calls = {"n": 0}

    def stub(msgs):
        calls["n"] += 1
        segs = [{"index": 1, "prompt": GOOD}, {"index": 2, "prompt": GOOD}]
        return {"choices": [{"message": {"role": "assistant", "content": None,
                                         "tool_calls": [{
                                             "id": "c1", "type": "function",
                                             "function": {
                                                 "name": "deliver_segments",
                                                 "arguments": json.dumps(
                                                     {"segments": segs},
                                                     ensure_ascii=False)}}]}}],
                "usage": {"total_tokens": 10}}

    try:
        d1 = A.generate("t1", PLAN, REC, SPANS, post=stub)
        check("agent 交付 2 段", len(d1["segments"]), 2)
        check("落盘带 agent 标记", d1["agent"], "h3")
        check("落盘文件存在", store.prompts_path("t1").is_file(), True)
        check("第一次调用 = 1 次", calls["n"], 1)
        d2 = A.generate("t1", PLAN, REC, SPANS, post=stub)
        check("同输入再跑 → 命中缓存，不再调模型", (calls["n"], d2["sig"]), (1, d1["sig"]))
        got = A.cached("t1", PLAN, REC, SPANS) or {}
        check("出片路径读得到（2 段）", sorted(got), [1, 2])

        # 🩸 互不相认：同一份文件，2.5 的读取器必须拒收
        check("2.5 的 cached 拒收 H3 写的文件", A25.cached("t1", PLAN, REC, SPANS), None)
        p = store.prompts_path("t1")
        d = json.loads(p.read_text(encoding="utf-8"))
        p.write_text(json.dumps(dict(d, agent="sd25"), ensure_ascii=False),
                     encoding="utf-8")
        check("标成 sd25 的文件，H3 也不认", A.cached("t1", PLAN, REC, SPANS), None)

        A.generate("t1", PLAN, REC, SPANS, post=stub, force=True)
        check("force=True → 重新调模型", calls["n"], 2)

        def bad_stub(msgs):
            segs = [{"index": 1, "prompt": "随便写一句"}, {"index": 2, "prompt": "随便写一句"}]
            return {"choices": [{"message": {"role": "assistant", "content": None,
                                             "tool_calls": [{
                                                 "id": "c1", "type": "function",
                                                 "function": {
                                                     "name": "deliver_segments",
                                                     "arguments": json.dumps(
                                                         {"segments": segs},
                                                         ensure_ascii=False)}}]}}],
                    "usage": {"total_tokens": 10}}

        raised = ""
        try:
            A.generate("t2", PLAN, REC, SPANS, post=bad_stub)
        except A.CloneAgentError as e:
            raised = str(e)
        check("连交两次不合格 → 抛错（调用方回落代码编译）",
              "没通过校验" in raised, True)
    finally:
        store.task_dir = old_dir
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{_n - _fail}/{_n} 通过")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
