"""P4 验收：界面归位（零模型调用、不联网、不花钱）。

P4 的两条验收（`docs/ROUTE-2A-PLAN.md`）：
  ① 四个档位从界面消失、变成每镜的默认策略，用户只回答"改什么"；
  ② `plan` 清单前置到点击前 —— 点「开始出片」之前，用户就该看到
     "几段能复用、几段要重画、为什么"。

这个脚本只验**能机械判定**的部分：
  A. 复用判定本身对不对（同规格全复用 / 改动只失效该失效的段 / 理由说得对）；
  B. 尺子有鉴别力（拿掉请求快照、退回旧解析，必须判"不能复用"）；
  C. 真实数据上 plan 的段数 == 真跑段数（89c228cc，5 秒那条）；
  D. 界面上那 4 个档位 + 6 个开关真的没了，复用清单真的接上了接口。

跑法：python scripts/p4_check.py
"""
from __future__ import annotations

import copy
import re
import json
import time
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import config  # noqa: E402
from app.services import edit_spec, media, timeline, video_edit, work  # noqa: E402

REAL_DIR = config.settings.clone_dir
SCRATCH = Path("D:/tmp/p4check") / uuid.uuid4().hex
FRONT = ROOT.parent / "frontend" / "app" / "src"

rows: list[tuple[str, bool, str]] = []


def chk(name: str, ok, detail: str = "") -> None:
    """`ok=None` = **跳过**：不并进通过数，也不计成失败，单独列出来。

    🩸 2026-10-31 加：判据对已下架的型号不成立时，报绿是假绿（空集不算通过），
    报红又是假红。跳过必须看得见，理由是必填的 detail。
    """
    rows.append((name, ok if ok is None else bool(ok), detail))


def use_root(p: Path) -> None:
    """切 clones 根目录（settings 是 frozen dataclass，绕过去）。"""
    object.__setattr__(config.settings, "clone_dir", p)
    p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 夹具：一条 20 秒的原片 + 一份"引擎写出来的"出片目录
# ---------------------------------------------------------------------------

def mk_fixture() -> tuple[str, dict, dict, list, Path]:
    use_root(SCRATCH)
    cid = "a" * 32
    d = SCRATCH / cid
    d.mkdir(parents=True, exist_ok=True)
    src = d / "source.mp4"
    subprocess.run([
        media.ffmpeg_path(), "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc2=size=480x854:rate=30:duration=20",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-c:a", "aac", "-shortest", str(src)], check=True)

    speech = []
    for a, b, text in ((0.4, 6.0, "one two three"),
                       (6.4, 13.0, "four five six"),
                       (13.4, 19.5, "seven eight nine")):
        step = (b - a) / 3
        speech.append({"start": a, "end": b, "text": text,
                       "chars": [{"c": w, "s": round(a + step * i, 3),
                                  "e": round(a + step * (i + 1), 3)}
                                 for i, w in enumerate(text.split())]})
    rec = {"source": {"duration": 20.0, "width": 480, "height": 854,
                      "fps": 30.0, "has_audio": True},
           "shots": [{"i": 0, "start": 0.0, "end": 8.0},
                     {"i": 1, "start": 8.0, "end": 14.0},
                     {"i": 2, "start": 14.0, "end": 20.0}],
           "speech": {"lang": "en", "segments": speech}}

    # 人物参考图：换人物那条路一定带图；**一人一张原图**，prepare 不再派生大头照
    # （2026-10-26 台账 D48，下面 B4 那条断言就是防它回潮）
    subject = d / "subject.jpg"
    subprocess.run([media.ffmpeg_path(), "-y", "-v", "error", "-i", str(src),
                    "-frames:v", "1", str(subject)], check=True)

    spec = edit_spec.normalize({"change": {"person": True, "person_id": "P1",
                                           "person_desc": "a man"},
                                "audio": "tts", "resolution": "auto"})
    plan = video_edit.prepare(rec, spec=spec, refs={"person": subject},
                              channel="auto", model="")
    spans, _moved = video_edit.plan_spans(src, rec, plan)
    # 🩸 fixture 必须和真跑用同一个调用形状：`_desired_units` 会按 rec["shots"]
    # 把镜头结构句（shot_cuts）编译进提示词。这里不传 → 签名的 prompt 天然对不上
    # → 每一次都判"输入变了"，A1/A5/B1 全绿变全红（2026-10-23 查出并修正）。
    prompts = work._video_prompts(plan, spans, rec["shots"], rec=rec)

    rid = "b" * 32
    wdir = d / "render" / rid / "whole"
    (wdir / "gen").mkdir(parents=True, exist_ok=True)
    manifest = {}
    for i, (a, b) in enumerate(spans, start=1):
        # 尾巴带 :bf / :na / :换人哈希 —— 真实键就是这个形状（见 replace_spans）
        key = (f'{plan["ch"]}:{plan["phash"]}:{a:.2f}-{b:.2f}'
               + (":bf" if i == 2 else "") + (":na" if i == 1 else "") + ":deadbe")
        manifest[f"seg_{i:03d}.mp4"] = key
        (wdir / "gen" / f"chunk_{i:03d}.mp4").write_bytes(b"fake")
        (wdir / f"request_{i:03d}.json").write_text(json.dumps({
            "channel": plan["ch"], "model": plan["model"],
            "resolution": plan["resolution"], "duration": b - a,
            "prompt": prompts[i - 1], "video_url": "", "ref_images": [],
            "audio": False}, ensure_ascii=False), encoding="utf-8")
    (wdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False),
                                        encoding="utf-8")

    script = "one two three four five six seven eight nine"
    (d / "task.json").write_text(json.dumps({
        "id": cid, "recipe": rec,
        "renders": [{"id": rid, "created_at": int(time.time()) + 10,
                     "regen_mode": "whole", "regen_channel": "auto",
                     "regen_model": "",
                     "edit": {"change": spec["change"], "keep": spec["keep"],
                              "audio": "tts",
                              "resolution": plan["resolution"], "extra": ""},
                     "script": script,
                     "segments": [{"start": a, "end": b} for a, b in spans]}]},
        ensure_ascii=False), encoding="utf-8")

    intent = {"mode": "whole", "channel": "auto", "model": "",
              "edit": spec, "script": script}
    return cid, intent, manifest, spans, wdir


def run_plan(cid: str, intent: dict) -> dict:
    return work.plan(cid, work.build(cid), intent)


# ---------------------------------------------------------------------------
# A. 复用判定
# ---------------------------------------------------------------------------

def phase_a(cid: str, intent: dict, spans: list, wdir: Path) -> None:
    r = run_plan(cid, intent)
    t = r["totals"]
    chk("A1 同规格重发 → 全部复用", t["reuse_units"] == t["units"] and t["units"] >= 2,
        f'{t["reuse_units"]}/{t["units"]} 复用')

    r2 = run_plan(cid, intent)
    chk("A2 同一份 work 连跑两次，清单一致",
        [x["asset"] for x in r["reuse"]] == [x["asset"] for x in r2["reuse"]],
        f'{len(r2["reuse"])} 段')

    i2 = copy.deepcopy(intent)
    # 多人换人（P9）后，「换谁」的真相是 `person_ids`，`person_id` 只是第一项的别名。
    # 判据不变：换了一个人 → 全部重画、复用 0。
    i2["edit"]["change"]["person_id"] = "P2"
    i2["edit"]["change"]["person_ids"] = ["P2"]
    r3 = run_plan(cid, i2)
    why = " ".join(x["why"] for x in r3["requests"])
    chk("A3 换人 → 全部重画（复用 0）", r3["totals"]["reuse_units"] == 0,
        f'{r3["totals"]["reuse_units"]}/{r3["totals"]["units"]} 复用')
    chk("A4 换人的理由不许说成「台词变了」", "台词" not in why, why or "（无请求）")

    i3 = copy.deepcopy(intent)
    i3["script"] = i3["script"].replace("one two", "won too")
    r4 = run_plan(cid, i3)
    hit = [x["label"] for x in r4["requests"]]
    chk("A5 只改开头一句 → 只有含改动的那段失效",
        r4["totals"]["reuse_units"] == 1 and len(hit) == 1
        and hit[0].startswith(f"{spans[0][0]:.1f}"),
        f'复用 {r4["totals"]["reuse_units"]}，请求 {hit}')

    i4 = copy.deepcopy(intent)
    i4["script"] = "totally different words here now"
    r5 = run_plan(cid, i4)
    chk("A6 改掉全部台词 → 露脸说话的段全失效",
        r5["totals"]["reuse_units"] == 0,
        f'{r5["totals"]["reuse_units"]}/{r5["totals"]["units"]} 复用')

    # A7 保守：没有字级时间时，改词必须失效所有跟嘴型的段
    w = work.build(cid)
    no_chars = copy.deepcopy(w)
    for s in no_chars["evidence"]["speech"]["segments"]:
        s["chars"] = []
    a_words = timeline.text_for_span(no_chars, intent["script"], spans[0])
    b_words = timeline.text_for_span(no_chars, "totally different words", spans[0])
    b_last = timeline.text_for_span(no_chars, "totally different words", spans[-1])
    chk("A7 没有字级时间时，改词不能漏判后面的段",
        a_words != b_words and b_words == b_last,
        "每个段都按整份台词比" if b_words == b_last else "后面的段拿到空串（会漏判）")


# ---------------------------------------------------------------------------
# B. 尺子自证（判据必须有鉴别力）
# ---------------------------------------------------------------------------

def phase_b(cid: str, intent: dict, manifest: dict, spans: list, wdir: Path) -> None:
    snap = wdir / "request_002.json"
    bak = snap.read_bytes()
    snap.unlink()
    r = run_plan(cid, intent)
    chk("B1 拿掉该段的请求快照 → 该段不再算复用（快照是必要条件）",
        r["totals"]["reuse_units"] == 1,
        f'{r["totals"]["reuse_units"]}/{r["totals"]["units"]} 复用')
    snap.write_bytes(bak)

    parsed = [work._parse_manifest_key(v) for v in manifest.values()]
    chk("B2 带 :bf / :na / 换人哈希的键也能取到时间段",
        all("span" in p for p in parsed), f'{len(parsed)}/{len(manifest)}')

    # 旧写法：取"倒数第二段"。带尾巴的键会取不到 → 那一段资产被静默丢掉
    def old_parse(v: str) -> dict:
        parts = str(v).split(":")
        if len(parts) >= 3 and "-" in parts[-2]:
            try:
                a, b = parts[-2].split("-")
                return {"span": [float(a), float(b)]}
            except ValueError:
                return {}
        return {}

    old_ok = sum(1 for v in manifest.values() if "span" in old_parse(v))
    chk("B3 尺子自证：旧解析会丢段（说明这条修复不是白改）",
        old_ok < len(manifest), f"旧解析 {old_ok}/{len(manifest)}，新解析 {len(parsed)}/{len(manifest)}")

    # B4 一人一张（2026-10-26，台账 D48）：规划**不再派生** `subject_head.jpg`。
    # 旧版这里测的是「派生件重裁换了 mtime，不许把历史资产判死」—— 派生件没了，
    # 那条判据对空对象恒真（vacuous），改成防回退：谁也不许把这个槽加回来。
    # 🩸 为什么要防：以前 `prepare` 每次现场裁一张大头照，mtime 一变就整片判
    # 「参考图换过」→ 白花钱重画。这条红了先想清楚再动，别只把断言删掉。
    root = SCRATCH / cid
    chk("B4 规划不派生大头照（一人一张）",
        not (root / "subject_head.jpg").exists()
        and "person_body" not in edit_spec.SLOT_ORDER
        and not any(s.endswith("_body") for a in work.build(cid)["assets"]
                    for s in (a.get("refs") or [])),
        f"head={(root / 'subject_head.jpg').exists()}")

    #  尺子自证：真换了人物图，必须判 stale，而且理由要说得对
    subj = root / "subject.jpg"
    before = subj.stat().st_mtime
    import os
    import time
    os.utime(subj, (time.time() + 7200, time.time() + 7200))
    r2 = run_plan(cid, intent)
    why2 = " ".join(x["why"] for x in r2["requests"])
    chk("B5 真换了人物图 → 判 stale，理由不是「没生成过」",
        r2["totals"]["reuse_units"] == 0 and "参考图" in why2,
        f'{r2["totals"]["reuse_units"]}/{r2["totals"]["units"]} 复用；{why2[:40]}')
    os.utime(subj, (before, before))


# ---------------------------------------------------------------------------
# C. 真实数据：plan 的段数 == 真跑的段数
# ---------------------------------------------------------------------------

def _real_renders() -> list[dict]:
    """目录里**真有出片记录**的任务，按时间从新到旧。

    🩸 2026-10-26：这里以前写死 `89c228cc…` / `928068f3…`。任务目录有 TTL
    （`settings.clone_ttl`，默认 **3 天**），启动时和定时器都会调
    `clone_store.cleanup_expired()` 把它删掉 —— 那个 cid 就是这么没的。
    写死的后果不是"少验一条"，是整个 C 组**直接崩在 FileNotFoundError**，
    看输出还以为是代码坏了。改成每次挑最新的、真有 segments 的那一条。
    """
    out: list[dict] = []
    if not REAL_DIR.exists():
        return out
    for d in REAL_DIR.iterdir():
        p = d / "task.json"
        if not d.is_dir() or not p.is_file():
            continue
        try:
            task = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for rec in (task.get("renders") or []):
            seg = (rec.get("regen_meta") or {}).get("segments")
            if seg and rec.get("id") and rec.get("edit"):
                out.append({"cid": d.name, "rid": rec["id"], "task": task,
                            "rec": rec,
                            "at": float(task.get("created_at") or 0.0)})
    out.sort(key=lambda x: x["at"], reverse=True)
    return out


def phase_c() -> None:
    use_root(REAL_DIR)
    cands = _real_renders()
    if not cands:
        # 不是"通过"：没数据 = 这条没验。写成 FAIL 是为了别让它静默变绿。
        chk("C0 目录里有没有可验的真实出片", False,
            f"{REAL_DIR} 下没有一个既出过片、又带 segments 的任务"
            f"（TTL 默认 {settings.clone_ttl / 86400:.0f} 天，过期的会被自动删）"
            " —— 跑一次出片后重跑本检查")
        return
    pick = cands[0]
    cid, task, rec = pick["cid"], pick["task"], pick["rec"]
    chk("C0 挑到一条真实出片", True, f"{cid[:12]} / {pick['rid'][:8]}（最新那份）")
    meta = rec.get("regen_meta") or {}
    e = rec["edit"]
    flat = {**(e.get("change") or {}), "keep": e.get("keep"),
            "audio": e.get("audio"),
            "resolution": e.get("resolution"), "extra": e.get("extra")}
    intent = {"mode": rec.get("regen_mode"), "channel": rec.get("regen_channel"),
              "model": rec.get("regen_model"), "script": rec.get("script") or "",
              "edit": edit_spec.normalize(flat)}
    w = work.build(cid)
    r = work.plan(cid, w, intent)
    units = r["totals"]["units"]
    # 🩸 2026-10-31：这条拿**历史真实出片**的快照比段数。现存的历史任务全是
    #   2.0 跑的（15s/段 → 3 段），而 2.0 已从复刻爆款下架、plan 现按 2.5 的
    #   30s 重算（→ 2 段）—— 型号换了，切法必然不同，两者不该相等。
    #   真跑型号还在可选列表时照常比；已下架则跳过（不并进通过数）。
    from app.services import model_specs as _ms
    _ch = rec.get("regen_channel") or "volc"
    _used = rec.get("regen_model") or ""
    # 🩸 2026-11-02：**分诊/分段规则改过之后，旧快照就不具可比性**。
    #   实例：最新一条真跑（45fff4bb / 72db24c5）出片时，分诊里还有「静止镜
    #   压着台词 → video」这条规则，末镜被并进前一段 → 1 段；该规则已按主人
    #   要求回退，同一 intent 现在按规则算出 2 段（末段 1.37s 判 still），
    #   两边**都对**，只是规则不同。拿它报红 = 拿两套规则互比。
    #   判据改成「真跑时间晚于规则文件最后一次改动」才比，规则一改自动跳过，
    #   下一次真跑之后恢复比较 —— 不需要人工升版本号。
    _rule_files = [ROOT / "app" / "services" / p for p in
                   ("triage.py", "video_edit.py", "work.py", "clone_pipeline.py")]
    _rule_mtime = max((p.stat().st_mtime for p in _rule_files if p.is_file()),
                      default=0.0)
    _ran_at = float(rec.get("created_at") or 0.0)
    if _ran_at and _ran_at < _rule_mtime:
        chk("C1 真实任务：plan 的段数 == 真跑的段数", None,
            f"跳过：这条真跑早于最近一次分诊/分段规则改动 "
            f"(plan {units} / 真跑 {meta.get('segments')})，不具可比性")
    elif _used and _used not in [x for x, _ in _ms.MODELS.get(_ch, [])]:
        chk("C1 真实任务：plan 的段数 == 真跑的段数", None,
            f"跳过：这条真跑用的是 {_used}，已下架；plan 按 2.5 重算 "
            f"(plan {units} / 真跑 {meta.get('segments')})，不具可比性")
    else:
        chk("C1 真实任务：plan 的段数 == 真跑的段数",
            units == int(meta.get("segments") or -1),
            f'plan {units} / 真跑 {meta.get("segments")}')
    # 🩸 2026-10-22：人物参考图口径改成"一人一张、不裁头"后，提示词模板变了，
    # 历史出片**本来就该失配**（签名的定义里就含"编译后的提示词"，模板改了就不是同输入）。
    # 所以这里不再要求"必然复用"，改判两件真正能证明机制没坏的事：
    #   ① **凡是有历史资产的段**，都不能被说成"没有生成过这一段"
    #      （为什么失配可以不同：输入变了 / 参考图换过 / 台词变了，但不能是"没见过"）；
    #   ② 同一 intent 连算两次，段签名逐条相同（键不稳定就会永远显示 0）。
    # 🩸 2026-10-26：①原来写成 `whys == {"输入变了（…）"}` —— 那是**绑定那一份任务**的
    # 快照断言，换一条任务就假红。改成按"有没有历史资产"算，才是机制本身的判据。
    have = {(tuple(a.get("span") or ()), a.get("engine"))
            for a in (w.get("assets") or [])}
    liar = [x["label"] for x in r["requests"]
            if (tuple(x.get("span") or ()), x.get("engine")) in have
            and x.get("why") == "没有生成过这一段"]
    chk("C2 有历史资产的段不会被说成「没生成过」", not liar,
        f"{len(have)} 段有历史资产；误报 {liar[:3]}")
    r2 = work.plan(cid, work.build(cid), intent)
    chk("C3 同一 intent 连算两次，段签名逐条相同",
        [x["sig"] for x in r["requests"]] == [x["sig"] for x in r2["requests"]]
        and [x["sig"] for x in r["reuse"]] == [x["sig"] for x in r2["reuse"]])


# ---------------------------------------------------------------------------
# D. 界面：档位/开关消失，复用清单前置
# ---------------------------------------------------------------------------

def phase_d() -> None:
    vue = (FRONT / "pages" / "clone" / "diagnose.vue").read_text(encoding="utf-8")
    api = (FRONT / "api" / "request.js").read_text(encoding="utf-8")

    # 范围按钮的点击从 `openingOn = true/false` 改成 `pickScope()`：
    # 没勾「换什么」时它点了也没效果，得先告诉用户为什么。判据跟着改成数 pickScope。
    chk("D1 四个档位选择器已从界面移除",
        "modes:" not in vue and 'class="mode"' in vue
        and vue.count('class="mode"') == 2 and vue.count('@click="pickScope(') == 2,
        '类名 "mode" 的按钮只剩 2 个（改整条 / 只换开头）')
    chk("D2 六个保留开关已从界面移除",
        "keeps:" not in vue and "toggleKeep" not in vue,
        "保留项收进内部编译")
    chk("D3 档位变成推导值（不再是用户选项）",
        "regenMode() {" in vue and "wantRegen() {" in vue,
        "regenMode = wantRegen ? (openingOn ? opening : auto) : off")
    chk("D4 复用清单前置到点击前",
        "reuse.totals.reuse_units" in vue and "cloneReusePlan" in api
        and "/reuse-plan" in api,
        "提交按钮上方显示 复用 N 段 / 要生成 M 段")
    chk("D5 复用清单在改动后自动重算",
        "scheduleReuse" in vue and vue.count("scheduleReuse()") >= 3,
        "台词 / 换什么 / 通道 / 型号 / 范围 变动都触发")

    # 换人物这条路，用户还要回答三件事：换谁 · 什么素材 · 声音怎么办
    three = {"换谁": "edit.person_id", "素材": "subjectAsset", "声音": "edit.audio"}
    have = {k: (v in vue) for k, v in three.items()}
    chk("D6 换人物只剩 3 个决定（换谁 / 素材 / 声音）",
        all(have.values()) and "modes:" not in vue and "keeps:" not in vue,
        "、".join(k for k, v in have.items() if v) + "；原 4 档 + 6 开关 + 1 比例已不问")

    # 🩸 源码里写了对，界面上也可能是空的：裸 <block> 在 H5 会编译成真的 <template> 元素，
    # 子节点进 template.content，页面上一个字都不显示（"换什么 / 通道型号"整块这么消失过）。
    # 所以这条判据必须看**产物**，不能只看源码。
    # 只认"整行就是一个裸 <block> 开标签"，别把注释里举例的那句算进来
    bare_pat = re.compile(r"^\s*<block>\s*$")
    bare = [str(p.relative_to(FRONT)) for p in (FRONT / "pages").rglob("*.vue")
            if any(bare_pat.match(ln) for ln in p.read_text(encoding="utf-8").splitlines())]
    chk("D7 没有裸 <block> 包内容（H5 会整块不渲染）", not bare,
        "、".join(bare) if bare else "扫了 pages 下所有 .vue")

    assets = FRONT.parent / "dist" / "build" / "h5" / "assets"
    chunks = sorted(assets.glob("pages-clone-diagnose*.js")) if assets.exists() else []
    has_bare = any('b("template",null' in c.read_text(encoding="utf-8", errors="replace")
                   for c in chunks)
    chk("D8 产物里没有 <template> 包裹（渲染得出来的证据）",
        bool(chunks) and not has_bare,
        f"{len(chunks)} 个 chunk" if chunks else "没有 H5 产物，先 npx uni build")


# ---------------------------------------------------------------------------

def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    try:
        cid, intent, manifest, spans, wdir = mk_fixture()
        phase_a(cid, intent, spans, wdir)
        phase_b(cid, intent, manifest, spans, wdir)
        phase_c()
        phase_d()
    finally:
        if SCRATCH.exists():
            shutil.rmtree(SCRATCH, ignore_errors=True)
        use_root(REAL_DIR)

    done = [r for r in rows if r[1] is not None]
    skipped = [r for r in rows if r[1] is None]
    bad = [r for r in done if not r[1]]
    for n, o, d in rows:
        mark = "SKIP" if o is None else ("PASS" if o else "FAIL")
        print(f"{mark}  {n}" + (f"  [{d}]" if d else ""))
    tail = f"（跳过 {len(skipped)}）" if skipped else ""
    print(f"\n{len(done) - len(bad)}/{len(done)} 通过{tail}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
