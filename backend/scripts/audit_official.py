# -*- coding: utf-8 -*-
"""拿**官方标准**去量历史真跑过的每一条提示词（零费用，不调模型）。

🩸 这个工具存在的理由（主人 2026-10-25 定的口径）：
    「不要老是看我们自己跑成功的，有可能刚好走运抽卡抽出来了。」
    ⇒ 判据只能是官方原文，不能是"我们哪条跑成了"。

🩸 **一条硬规矩：一个型号一把尺，绝不串用。**
    · `doubao-seedance-2-0-*` → 《Seedance 2.0 提示词指南》 + 官方 skill `sd2-pe`
    · `doubao-seedance-2-5-*` → 官方 skill `sd25-pe`
    · `MiniMax-H3*`            → 官方 skill `h3-prompt-writing`（`ref-en.txt`）
    2.0 的"必须写 <主体N>"拿来量 2.5 就是错的 —— 2.5 的模板是五段式，
    H3 是六段英文；尺子挂错，红的一律不算数。

用法：
    python scripts/audit_official.py --model volc20            # 汇总表
    python scripts/audit_official.py --model volc20 --detail   # 每条违规都带原句
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BACK = Path(__file__).resolve().parents[1]
if str(BACK) not in sys.path:
    sys.path.insert(0, str(BACK))
ROOT = BACK / "data" / "clone"
EDIT_WORDS = ("编辑", "替换", "修改", "改成", "替换成")
POS_ZH = {
    "top-left": "画面左上", "top": "画面上方", "top-right": "画面右上",
    "left": "画面左侧", "center": "画面中央", "right": "画面右侧",
    "bottom-left": "画面左下", "bottom": "画面下方", "bottom-right": "画面右下",
}


# ---------------------------------------------------------------- 读数

def load_reqs() -> list[dict]:
    out = []
    for f in sorted(ROOT.glob("*/render/*/triage/request_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or not d.get("prompt"):
            continue
        cid = f.parts[-5]
        inv = sorted((ROOT / cid / "inventory").glob("*.json"))
        people: list = []
        shots: list = []
        if inv:
            try:
                d0 = json.loads(inv[0].read_text(encoding="utf-8"))
                people = d0.get("people") or []
                shots = d0.get("shots") or []
            except Exception:
                people = []
        d["_file"] = str(f.relative_to(ROOT))
        d["_cid"] = cid
        d["_rid"] = f.parts[-3]
        d["_people"] = people
        d["_shots"] = shots
        out.append(d)
    return out


# ---------------------------------------------------------------- 2.0

def audit_sd20(r: dict) -> list[tuple[str, str, str]]:
    """返回 [(规则, 严重度, 原句)]。出处全部 《Seedance 2.0 提示词指南》/ sd2-pe。"""
    p = r["prompt"]
    v: list[tuple[str, str, str]] = []
    n_people = len(r["_people"])
    multi = n_people >= 2

    # E1 编辑意图词（API 硬要求，缺了会判成参考任务）
    if not any(w in p for w in EDIT_WORDS):
        v.append(("E1 缺编辑意图词", "红", p[:60]))

    # E2 官方 sd20-guide:56 —— 编辑任务禁止「参考<视频N>」
    for m in re.finditer(r"参考@?视频\s*1", p):
        v.append(("E2 写了「参考@视频1」", "红", p[max(0, m.start() - 30):m.end() + 30]))

    # E3 官方 sd20-guide:39 —— 修改元素句式「严格编辑<视频N>，将其中的…」
    if "@视频1" not in p:
        v.append(("E3 没写 @视频1 指代原片", "红", p[:60]))

    # E4 官方 sd20-guide:109 —— 多主体必须分别定义、用标签区分。
    # 🩸 触发条件是「**提示词里点名了 ≥2 个换人对象**」，不是「盘点里有几个人」：
    # 一条产品片盘点出 12 个人（背景人群），硬套「12 个人都要标签」会把
    # 所有多人群像片全判红 —— 那不是官方口径，是尺子造出来的假问题。
    # 🩸 数的是**不同的换人对象**，不是"替换为"出现几次。
    # 两个假红都栽在这一点上：
    #   · 「把产品替换为@图片2中的产品」也是"替换为" → 单人片判成多人片；
    #   · D23 的范围句「每一镜里的人物都替换为@图片1中的人物，切镜之后…同样替换」
    #     → 同一个人被数了两次。
    # 所以取**去重后的图号**。
    targets = set(re.findall(r"替换为\s*@?图片\s*(\d+)\s*中的人物", p))
    if len(targets) >= 2 and "<主体" not in p:
        v.append((f"E4 点名 {len(targets)} 个换人对象却没用标签", "红", p[:90]))

    # E5 官方 sd20-guide:95 —— 定义要带 2–3 个静态特征
    for m in re.finditer(r"将([^。；]{0,40}?)定义为<主体(\d+)>", p):
        body = m.group(1)
        if re.fullmatch(r"@?图片\d+(、@?图片\d+)*中的人物", body.strip()):
            v.append((f"E5 <主体{m.group(2)}> 定义没带特征",
                      "黄", m.group(0)))

    # E6 官方 sd20-guide:121 —— 同一分句内同一图号重复 ≥3 次 = 冗余
    for cl in re.split(r"[；。]", p):
        pics = re.findall(r"@图片(\d+)", cl)
        for n in set(pics):
            if pics.count(n) >= 3:
                v.append((f"E6 @图片{n} 同句出现 {pics.count(n)} 次",
                          "黄", cl.strip()))

    # E7 sd2-pe:72 —— 多人画面里「将其中的X替换为」的 X 必须**唯一指认得人**。
    # 🩸 判的是"唯不唯一"，不是"长得像不像坏句子"：
    #   · 「人物」且在场 ≥2                → 没有任何指认
    #   · 「画面X的人物」且 X 上站着 ≥2 人 → 撞车，等于没写（D24 现场）
    #   · 「画面X的人物」且只有 1 人       → **合法**（`3f91496d` 画面下方/画面中央
    #     分别指向不同的人，这不是缺陷 —— 成对样本，尺子不许把它判红）
    if multi:
        pos_count: dict[str, int] = {}
        for pp in r["_people"]:
            k = POS_ZH.get(str(pp.get("position") or ""), "")
            if k:
                pos_count[k] = pos_count.get(k, 0) + 1
        for m in re.finditer(r"将其中的(.{0,30}?)替换为", p):
            obj = m.group(1).strip()
            bad = ""
            if obj == "人物":
                bad = "没写任何指认"
            else:
                for k, n in pos_count.items():
                    if obj == f"{k}的人物" and n > 1:
                        bad = f"{k}上有 {n} 个人，撞车"
            if bad:
                v.append((f"E7 宾语「{obj}」指认不到人（{bad}）", "红", m.group(0)))
    return v


# ---------------------------------------------------------------- 2.5

SECTIONS_25 = ("【编辑目标】", "【原视频职责】", "【目标素材职责】",
               "【编辑对象与范围】", "【时间线继承】")


def audit_sd25(r: dict) -> list[tuple[str, str, str]]:
    """出处两份，缺一不可：
        · 官方 skill `sd25-pe`（模板/原则）
        · 官方指南 `D:/tmp/official/sd25/guide.md`（编辑类写法 / 常见问题 / 案例）
    🩸 2026-10-25 补：上一版尺子**只用了一 skill**，没读 2.5 指南（1357 行），
    等于把 2.5 量浅了。
    """
    p = r["prompt"]
    v: list[tuple[str, str, str]] = []
    # S1 sd25-pe:559-576 —— 编辑模板五段齐全
    miss = [s for s in SECTIONS_25 if s not in p]
    if miss:
        v.append((f"S1 缺段 {''.join(miss)}", "红", " / ".join(SECTIONS_25)))
    # S2 sd25-pe:552-555 —— 必须有范围闭环
    if "保持原样，不参与替换或删除" not in p and "不新增未指定对象" not in p:
        v.append(("S2 缺范围闭环句", "红", p[:80]))
    # S3 sd25-pe:561 —— 「只把<原对象>替换为<目标>」（动词跟正式示例，见
    # `volc25_compile._CL25.wardrobe_verb`：示例 5/5 用「替换为」）
    if "只把" not in p:
        v.append(("S3 缺「只把…替换为」句式", "黄", p[:80]))
    # S4 sd25-pe:77 原则 8 —— 不得自动加画质包/水印/Logo/字幕
    for w in ("不要生成水印", "不要生成 Logo", "电影质感"):
        if w in p:
            v.append((f"S4 自动加了「{w}」（原则 8 禁止）", "红", p[:80]))

    # ---- 以下来自 2.5 官方指南 `seedance-25-guide.md` ----
    # S6 sd25-guide:189/:193 —— 编辑类要「明确需要修改的范围和内容」，官方示例用**方位**
    # 指认人：「把视频1中**右侧**的亚洲女生改为图片1中的黑人女生」。
    # 🩸 注意：2.5 官方**不要求** 2.0 那套 `<主体N>`。两边机制不同，不许串用。
    if len(r["_people"]) >= 2:
        pos_count: dict[str, int] = {}
        for pp in r["_people"]:
            k = POS_ZH.get(str(pp.get("position") or ""), "")
            if k:
                pos_count[k] = pos_count.get(k, 0) + 1
        for m in re.finditer(r"只?把(.{0,30}?)替换为", p):
            obj = m.group(1).strip()
            bad = ""
            if obj in ("人物", "角色"):
                bad = "没写任何指认"
            else:
                for k, n in pos_count.items():
                    if obj == f"{k}的人物" and n > 1:
                        bad = f"{k}上有 {n} 个人，撞车"
            if bad:
                v.append((f"S6 宾语「{obj}」指认不到人（{bad}）", "红", m.group(0)))

    # S5 sd25-guide:435 —— 多人物视频要「按人物**首次出场顺序**上传参考素材，
    # 并同步调整提示词中的图片、音频编号」。这条 2.0/H3 都没有，是 2.5 独有。
    # 能从提交记录判的就判，判不了必须明确写「未验证」，**不许算成通过**。
    if len(r["_people"]) >= 2:
        first: dict[str, float] = {}
        for pp in r["_people"]:
            ap = pp.get("appearances") or []
            if ap:
                first[str(pp.get("position") or "")] = float(ap[0].get("start") or 0)
        pairs = re.findall(r"把(画面[^\s，；。]{2,4})的人物替换为@?图片\s*(\d+)", p)
        if len(pairs) >= 2:
            seq = [(n, first.get(pos, -1)) for pos, n in pairs]
            if any(t < 0 for _, t in seq):
                v.append(("S5 首次出场顺序 未验证（盘点缺出场时间）", "灰", ""))
            elif [t for _, t in seq] != sorted(t for _, t in seq):
                v.append((f"S5 图片编号没按首次出场顺序（{seq}）", "红", ""))
        else:
            v.append(("S5 首次出场顺序 未验证（提示词里没有可对应的方位）",
                      "灰", ""))
    return v


# ---------------------------------------------------------------- H3

SECTIONS_H3 = ("subject_definitions", "summary", "retention_analysis",
               "detailed_description", "overall_soundscape",
               "non_diegetic_music")


def audit_h3(r: dict) -> list[tuple[str, str, str]]:
    """出处：官方 skill `h3-prompt-writing` → `references/ref-en.txt`。"""
    p = r["prompt"]
    v: list[tuple[str, str, str]] = []
    # H1 ref-en:13 —— 六段按顺序
    pos = [p.find(s) for s in SECTIONS_H3]
    miss = [s for s, i in zip(SECTIONS_H3, pos) if i < 0]
    if miss:
        v.append((f"H1 缺段 {','.join(miss)}", "红", " / ".join(SECTIONS_H3)))
    elif pos != sorted(pos):
        v.append(("H1 六段顺序乱了", "黄", " / ".join(SECTIONS_H3)))
    # H2 ref-en:16-22 —— 每张参考图都要有落点
    used = set(re.findall(r"<Picture (\d+)>", p))
    sent = len(r.get("ref_images") or [])
    for i in range(1, sent + 1):
        if str(i) not in used:
            v.append((f"H2 发了 <Picture {i}> 但提示词里没引用", "红", ""))
    # H3 ref-en:39 —— 可复用主体用 <Subject N>
    if len(r["_people"]) >= 2 and "<Subject " not in p:
        v.append(("H3 多人却没用 <Subject N>", "红", p[:90]))
    # H4 ref-en:7 —— 每镜要写构图/主体外观与位置。
    # 🩸 只有原片**真有多镜**才要求逐镜标记：单镜片写一个 [Shot 1] 是多余的
    # （官方要的是"每个镜头都写清楚"，不是"必须出现 Shot 字样"）。
    # 实测假黄：`2239b2a2/e6bfd247` 原片单镜，被判"没有逐镜描述"。
    if len(r["_shots"]) >= 2 and "[Shot " not in p:
        v.append((f"H4 原片 {len(r['_shots'])} 镜却没有逐镜描述", "黄", p[:90]))

    # H5 ref-en:231 + :246 —— 标签一经分配，要在「首次出现处、以及角色生效处」
    # 继续使用；每个重要 <Subject N> 在 detailed_description 里都得有落点。
    head = p.split("detailed_description", 1)[0]
    body = p.split("detailed_description", 1)[1] if "detailed_description" in p \
        else ""
    defined = [f"<Subject {n}>" for n in dict.fromkeys(
        re.findall(r"<Subject (\d+)>", head))]
    for lab in defined:
        if lab not in body:
            v.append((f"H5 {lab} 定义后从未在逐镜里出现（ref-en:246）",
                      "黄", ""))
    return v


# ---------------------------------------------------------------- 派尺子

def pick_ruler(r: dict):
    """🩸 一把尺对一个型号。对不上就明说不知道，绝不拿别家的尺子凑。"""
    ch = (r.get("channel") or "").strip()
    m = (r.get("model") or "").strip()
    if ch == "volc" and "-2-0" in m:
        return "SD2.0", audit_sd20
    if ch == "volc" and "-2-5" in m:
        return "SD2.5", audit_sd25
    if ch == "minimax":
        return "H3", audit_h3
    return "?", None


# ---------------------------------------------------------------- 尺子自证
# 🩸 每条探针都**成对**：一条已知好、一条已知坏、一条"看着像坏其实合法"。
# 只有"红/绿都出得来"才说明尺子有鉴别力；全绿或全红都等于没装。

SELFTEST = [
    # (样本, 期望, 说明)
    ("7fb73ecf/052dcbf0", "green", "已知好：单人，真机 0–11.2s 换人成功"),
    ("2239b2a2/295079ce", "green", "假红陷阱：单人+换产品+换场景，不是多换人"),
    ("6c51196b/3949eb3f", "red", "已知坏：双人同标 center，整片一帧没换"),
    ("3dd514aa/2ccd2fdb", "red", "真多对象：点名换 2 个人却没定义标签"),
    ("3f91496d/e87b78ed", "noE7", "看着像坏其实合法：画面下方/画面中央 各只有 1 人"),
]


def selftest() -> int:
    reqs = {f"{r['_cid'][:8]}/{r['_rid'][:8]}": r for r in load_reqs()}
    ok = 0
    for key, want, why in SELFTEST:
        r = reqs.get(key)
        if r is None:
            print(f"!! {key} 样本不在（数据被删了？）")
            continue
        name, fn = pick_ruler(r)
        vs = fn(r)
        red = [x[0] for x in vs if x[1] == "红"]
        got = "red" if red else "green"
        if want == "noE7":
            hit = got == "green" and not any("E7" in x for x in red)
        else:
            hit = got == want
        ok += 1 if hit else 0
        print(f"{'ok ' if hit else '!! '}{key}  期望 {want:5s} 实得 {got:5s}"
              f"  —— {why}")
        if red:
            print(f"      红项：{'; '.join(red)}")
    print(f"\n尺子自证：{ok}/{len(SELFTEST)} 通过")
    return 0 if ok == len(SELFTEST) else 1


# ---------------------------------------------------------------- 闭环：量「现在的输出」
# 🩸 尺子最有用的用法不是回审历史，是**反过来当生成规格**：
# 每条判据对应提示词里必须有/绝不能有的一句话。所以直接量 `compile_prompt`
# 现在产出的东西 —— 全绿才算"知道怎么写了"，红的就是还没落地的规则。

def current_cases() -> list[dict]:
    """用一份假盘点（两人）把各型号各形态编译一遍。零费用。"""
    from app.services import edit_spec

    P1 = {"id": "P1", "present": True, "position": "center",
          "desc_zh": "体型偏胖的男子，黑色头发束成发髻，身着浅青绿色古装",
          "desc_en": "a heavier-set man with hair in a topknot",
          "appearances": [{"start": 0.0, "end": 6.0}]}
    P2 = {"id": "P2", "present": True, "position": "center",
          "desc_zh": "年轻女子，黑色长发梳成古装高髻，身着广袖古装",
          "desc_en": "a young woman with an elaborate updo",
          "appearances": [{"start": 2.0, "end": 8.0}]}
    P1L, P2R = dict(P1, position="left"), dict(P2, position="right")
    LINES = [[{"start": 0.4, "end": 1.8, "text": "真好看", "lang": "zh",
               "speaker": ""}]]

    def one(name, ch, model, chg, ppl, slots, **kw):
        spec = edit_spec.normalize(chg)
        p = edit_spec.compile_prompt(ch, spec, model=model,
                                     source_people=ppl, slots=slots, **kw)
        return {"channel": ch, "model": model, "prompt": p,
                "duration": 8.0, "ref_images": list(range(len(slots))),
                "_people": ppl, "_shots": [1, 2], "_cid": name,
                "_rid": name, "_file": f"<current:{name}>"}

    M20, M25 = "doubao-seedance-2-0-mini-260615", "doubao-seedance-2-5-260628"
    return [
        one("2.0 单人", "volc", M20, {"person": True, "person_ids": ["P1"]},
            [P1], ["person"]),
        one("2.0 双人只换一个", "volc", M20,
            {"person": True, "person_ids": ["P1"]}, [P1, P2], ["person"]),
        one("2.0 双人只换一个+方位唯一", "volc", M20,
            {"person": True, "person_ids": ["P1"]}, [P1L, P2R], ["person"]),
        one("2.0 双人全换", "volc", M20,
            {"person": True, "person_ids": ["P1", "P2"]}, [P1, P2],
            ["person", "person2"]),
        one("2.0 双人全换+方位", "volc", M20,
            {"person": True, "person_ids": ["P1", "P2"]}, [P1L, P2R],
            ["person", "person2"]),
        one("2.0 单人+产品", "volc", M20,
            {"person": True, "product": True, "person_ids": ["P1"]},
            [P1], ["person", "product"]),
        one("2.0 单人+切点", "volc", M20,
            {"person": True, "person_ids": ["P1"]}, [P1], ["person"],
            shot_cuts=[3.0, 6.9]),
        one("2.5 单人", "volc", M25, {"person": True, "person_ids": ["P1"]},
            [P1], ["person"]),
        one("2.5 双人只换一个", "volc", M25,
            {"person": True, "person_ids": ["P1"]}, [P1, P2], ["person"]),
        one("2.5 双人全换", "volc", M25,
            {"person": True, "person_ids": ["P1", "P2"]}, [P1, P2],
            ["person", "person2"]),
        one("H3 单人", "minimax", "", {"person": True, "person_ids": ["P1"]},
            [P1], ["person"]),
        one("H3 双人只换一个", "minimax", "",
            {"person": True, "person_ids": ["P1"]}, [P1, P2], ["person"]),
        one("H3 双人全换", "minimax", "",
            {"person": True, "person_ids": ["P1", "P2"]}, [P1, P2],
            ["person", "person2"]),
    ]


def audit_current() -> int:
    red_total = 0
    for r in current_cases():
        name, fn = pick_ruler(r)
        if fn is None:
            print(f"?? 认不出型号：{r['model']}")
            continue
        vs = fn(r)
        red = [x for x in vs if x[1] == "红"]
        yellow = [x for x in vs if x[1] == "黄"]
        gray = [x for x in vs if x[1] == "灰"]
        red_total += len(red)
        mark = "红" if red else "黄" if yellow else "灰" if gray else "绿"
        print(f"[{mark}] {r['_cid']}  （{name} 尺子）")
        for rule, sev, ev in vs:
            print(f"      · {sev} {rule}")
    print(f"\n今日输出：{red_total} 条红")
    return 0 if red_total == 0 else 1


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一次只跑一家。
    from _model_gate import sel_or_exit
    sel_or_exit()

    if "--selftest" in sys.argv:
        return selftest()
    if "--current" in sys.argv:
        return audit_current()
    detail = "--detail" in sys.argv
    reqs = load_reqs()
    buckets: dict[str, list] = {}
    for r in reqs:
        name, fn = pick_ruler(r)
        buckets.setdefault(name, []).append((r, fn))

    for name in ("SD2.0", "SD2.5", "H3", "?"):
        rows = buckets.get(name) or []
        if not rows:
            continue
        print("=" * 78)
        # 🩸 绿必须是"量过且合规"，不是"根本没有可比对象"（空集恒真）。
        # 所以先报分母：这批里有多少条真在做换人。
        # 「在换人」的写法每家不一样：火山是「中的人物」，H3 是英文 "replaced by"
        def _is_pp(r: dict) -> bool:
            p = r["prompt"]
            return "中的人物" in p or "replaced by" in p

        n_pp = sum(1 for r, _ in rows if _is_pp(r))
        print(f"{name}  —— 共 {len(rows)} 条请求，其中真在换人的 {n_pp} 条"
              f"（尺子：{name} 自己的官方文档）")
        bad = 0
        for r, fn in rows:
            if fn is None:
                print(f"  ?? 认不出型号：{r.get('model')}  {r['_file']}")
                continue
            vs = fn(r)
            red = [x for x in vs if x[1] == "红"]
            yellow = [x for x in vs if x[1] == "黄"]
            if red:
                bad += 1
            # 灰 = 这条判据**没验证**（数据不足），既不算红也不算绿
            mark = ("红" if red else "黄" if yellow else
                    "灰" if vs else "绿")
            print(f"\n  [{mark}] {r['_cid'][:8]}/{r['_rid'][:8]}  "
                  f"{r.get('model')}  {r.get('duration')}s  "
                  f"在场{len(r['_people'])}人")
            for rule, sev, ev in vs:
                line = f"      · {sev} {rule}"
                if detail and sev == "红":
                    line += f"\n          原句：{ev[:150]}"
                print(line)
            if not vs:
                print("      · 绿 未发现违反该型号官方标准的地方")
        print(f"\n  → {name}: {bad}/{len(rows)} 条有红")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
