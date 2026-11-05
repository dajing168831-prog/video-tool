"""作品文档（work.json）：把一次出片从"目录里的一堆文件"变成可校验、可复用的文档。

为什么要有这一层
----------------
现在每次出片的输入和产物散在三处：`task.json` 的 recipe、`render/<rid>/` 下的
请求快照与分段文件、以及各引擎自己的 `manifest.json`。结果是：

- 没人能回答"这段画面为什么复用/为什么重画"——只能靠翻目录猜；
- 改一个输入，到底影响哪几段，出片前算不出来；
- 同一个提示词重跑靠各引擎各自的 key，跨引擎对不齐。

这里把三处收束成一份文档：**源 + 证据 + 资产 + 决策**。资产带 sha 和语义签名，
plan 只做两件事——算出这次"要哪些请求"，以及"哪些已有资产能直接复用"。

边界（P1）
----------
- 只做本地计算：不调任何模型、不上传、不花钱。
- 复用的粒度：**视频段按整段**（whole/auto 的 span）；静帧按整镜。
- 词的粒度：按**句段**。每段带 `lip`（画面是否跟着嘴型走）：
  跟嘴型的段，台词一变就要重画；空镜/背影的段，改词只换声音。
- 词级时间来自 ASR 的字级时间戳（`timeline.project`），没有时退回按段均分。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.services import clone_store, edit_spec, timeline

WORK_VERSION = 2

# 参考图槽位 → 任务目录里的文件名。顺序与 edit_spec.SLOT_ORDER 一致。
# 人物槽按最大人数生成（person → subject.jpg，personN → ref_personN.jpg）。
_REF_FILE = {
    "person": "subject.jpg",
    # `*_body` = 旧版"大头照/全身照"派生的第二张，2026-10-22 起不再生成。
    # 键留着只为读得懂老任务的目录，别删（删了老资产会当成"参考图换了"）。
    "person_body": "subject_head.jpg",
    "product": "ref_product.jpg",
    "scene": "ref_scene.jpg",
    "wardrobe": "ref_wardrobe.jpg",
}
for _i in range(2, edit_spec.MAX_PERSONS + 1):
    _REF_FILE[f"person{_i}"] = f"ref_person{_i}.jpg"
for _i in range(2, edit_spec.MAX_WARDROBE + 1):
    _REF_FILE[f"wardrobe{_i}"] = f"ref_wardrobe{_i}.jpg"


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def sha256_file(p: Path) -> str:
    """文件内容哈希。读 1MB 块，别把整条视频读进内存。"""
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canon(obj) -> str:
    """规范化 JSON：键排序、不留空格、中文不转义 —— 同样的内容永远同一个串。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sig(key: dict) -> str:
    return hashlib.sha256(_canon(key).encode("utf-8")).hexdigest()[:16]


def _num(x, nd: int = 3) -> float:
    return round(float(x), nd)


def _sha1_file(p: Path) -> str:
    h = hashlib.sha1()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _span(a, b) -> list[float]:
    """时间段统一保留两位小数。

    引擎写 manifest 时只到 0.01 秒（`0.00-5.01`），plan 算出来是 `5.014`。
    不统一精度，同一段在两边签名不同，永远命不中缓存。
    """
    return [_num(a, 2), _num(b, 2)]


# ---------------------------------------------------------------------------
# 收集现有产物
# ---------------------------------------------------------------------------

def _ref_files(cid: str, change: dict) -> dict[str, Path]:
    """这次真正会发给模型的参考图（槽位 → 文件）。

    只列"勾了 + 文件在"的槽位：勾了没图的槽位在编译时只会退化成文字描述，
    不该算进资产签名里（否则用户补一张图，历史资产的签名会莫名其妙全变）。
    """
    from app.services import edit_spec

    root = clone_store.task_dir(cid)
    out: dict[str, Path] = {}
    for slot in edit_spec.SLOT_ORDER:
        if not change.get(slot):
            continue
        p = root / _REF_FILE[slot]
        if p.exists():
            out[slot] = p
        body = slot + "_body"
        if body in _REF_FILE:
            head = root / _REF_FILE[body]
            # 🩸 2026-10-26 起不再派生大头照（台账 D48，一人一张）。这一段只为**老任务
            # 目录**里还躺着的 `subject_head.jpg` 保留：它只进资产签名，不会被发出去
            # （`ref_plan` 只走 SLOT_ORDER，而 `person_body` 已不在其中）。
            if head.exists():
                out[body] = head
    return out


def _load_inventory(cid: str) -> dict | None:
    """读视觉盘点的**缓存**（不调用模型）。

    盘点是花钱的，plan 里绝不能因为"想算得更准"再调一次。
    缓存对不上当前原片（sha1 不同）就当没有 —— 宁可少复用，不可错复用。
    """
    d = clone_store.task_dir(cid) / "inventory"
    if not d.is_dir():
        return None
    src = clone_store.source_path(cid)
    if not src.exists():
        return None
    want = _sha1_file(src)
    for p in sorted(d.glob("*.json")):
        inv = _load_json(p)
        if isinstance(inv, dict) and (inv.get("_meta") or {}).get("video_sha1") == want:
            return inv
    return None


def _video_prompts(plan: dict, spans: list, shots: list | None = None,
                   audio_ref: bool | None = None,
                   rec: dict | None = None) -> list[str]:
    """按段复编译提示词 —— 和真跑（`video_edit._gen_spans`）走同一套输入。

    🩸 这一条不能省：资产签名里如果只放"换了什么"，不放**编译后的提示词**，
    提示词模板一改（比如去掉「体型」两个字），旧资产会被误判成"同输入"，
    结果是用户以为复用了，画面其实是上一版模板生成的。

    `audio_ref` 传 None = 跟着 plan 走；预览时如果原片根本没音轨 / 这一段的音频
    短于 2s，就必须传 False —— 那一段真跑时不会喂音频，提示词里也不该出现
    `<Audio 1>` / `@音频1`。

    🩸 2026-10-31 修「预览 ≠ 实发」：以前这里只传 `shot_cuts`，真跑还传
    `shot_lines`（台词）、`frame_people`（这一段画面里有谁）、`boundary_pic`
    （边界帧图号）—— 少三个输入 ⇒ 预览看到的句子和发出去的**不是同一句**
    （2026-10-24 实测：预览「其中的人物」/ 实发「画面中央的人物（…）」）。
    现在把 `rec` 传进来，按 `_gen_spans` 的同一套规则补齐。

    ⚠️ 唯一算不准的是 `boundary_pic`：真跑要**取到尾帧**才带边界帧，取帧失败会
    退化成不带。这里按"取帧成功"估算；预览和实发在这一个点上仍可能差一句。
    彻底消除要等提示词落盘（单一真相源），那时预览直接读文件。
    """
    from app.services import models, video_edit

    acts = video_edit._span_plan(plan, spans)
    ad = models.adapter_for(model=plan.get("model") or "", channel=plan.get("ch") or "")
    n_refs = len(plan.get("ordered") or [])
    out = []
    prev_generated = False
    for n, sp in enumerate(spans, 1):
        a, b = float(sp[0]), float(sp[1])
        act, target = acts.get((a, b), ("", None))
        if act == "keep":
            # 这一段真跑时直接留原片（不发请求）。清单仍与 spans 一一对应，
            # 提示词按 `_span_prompt` 的老行为给 `plan["prompt"]` 占位。
            prev_generated = False
        # 镜头结构句也进签名：真跑（`_gen_spans`）带 shot_cuts，这里不带就成了
        # "签名算的和实际发的不一样"，切点不同的两条片会被误判成同输入
        cuts = None
        if shots is not None:
            cuts = [round(float(s["start"]) - a, 3) for s in shots
                    if a + 0.15 < float(s["start"]) < b - 0.15]
        # 逐句台词 / 这一段画面里有谁 / 边界帧图号 —— 三个都和真跑同规则
        seg_lines = video_edit._span_lines(rec, a, b, cuts) if rec else None
        frame_ppl = None
        if rec and plan.get("inventory"):
            from app.services import vision_plan as _vp

            frame_ppl = _vp.people_in(plan.get("inventory"), a, b)
        # 边界帧：上一段是重画的、紧挨着、且切点不在原片镜头切换上（同 `_gen_spans`）
        adjacent = (n >= 2 and prev_generated
                    and abs(float(spans[n - 2][1]) - a) < 1e-3
                    and not video_edit._at_shot_cut(rec, a))
        bf_pic = (n_refs + 1) if (adjacent and bool(ad.caps.boundary_pic)) else 0
        prev_generated = True
        try:
            out.append(video_edit._span_prompt(
                plan, target, drop_person=(act == "text"),
                audio_ref=audio_ref, boundary_pic=bf_pic, shot_cuts=cuts,
                shot_lines=seg_lines, frame_people=frame_ppl,
                # 🩸 2026-11-05：只传**这一段**的镜头表（时间轴从 0 起）。
                #   以前传整片的，H3 的【画面过程说明】在第 1 段（0–7.083s）里
                #   写「0-1 秒…25-30 秒」，模型收到 7 秒素材却被告知 30 秒的戏。
                shot_desc=video_edit._span_shots(plan.get("inventory"), a, b)))
        except Exception:  # noqa: BLE001
            out.append("")
    return out


_SPAN_PART = re.compile(r"^\d+(?:\.\d+)?-\d+(?:\.\d+)?$")


def _parse_manifest_key(v: str) -> dict:
    """解析引擎写的 manifest 值。

    引擎写的键是 `<通道>:<提示词哈希>:<起-止>[可选的 :bf / :na / :换人哈希]`
    （`video_edit.replace_spans` 里拼的），所以**时间段固定在第 3 段**。
    🩸 以前按 `parts[-2]` 取：只要这一段带了边界帧（`:bf`）、没音轨（`:na`）
    或指定了换谁（`:who`），尾巴多一段就取不到时间段，这段资产被**静默丢掉** ——
    而"指定换谁"正好是换人物那条路的常态。按形状找，不按位置猜。
    """
    out: dict = {"raw": v}
    for part in str(v).split(":")[1:]:
        if _SPAN_PART.match(part):
            a, b = part.split("-")
            out.update(engine="keep" if str(v).startswith("orig:") else "video",
                       span=[_num(a, 2), _num(b, 2)])
            break
    return out


def _scan_assets(cid: str, task: dict, work: dict | None = None) -> list[dict]:
    """把 render/ 下已经存在的产物登记成资产。

    每个资产记四样东西：**哪一段（span）、走哪条引擎、什么输入（key）、产物文件（sha）**。
    后续 plan 只比 key —— key 一样就复用，不一样就重新要。
    """
    root = clone_store.task_dir(cid)
    rroot = root / "render"
    if not rroot.exists():
        return []
    by_id = {r.get("id"): r for r in (task.get("renders") or [])}
    source_sha = sha256_file(clone_store.source_path(cid))
    out: list[dict] = []

    inv = _load_inventory(cid)
    for rdir in sorted(p for p in rroot.iterdir() if p.is_dir()):
        rid = rdir.name
        rec = by_id.get(rid) or {}
        edit = rec.get("edit") or {}
        change = edit.get("change") or {}
        refs = _ref_files(cid, change)
        # 🩸 参考图若在出片之后被换过，这份资产就不能算"同输入" —— 标 stale，
        #    宁可多花一次钱，也不要把旧画面当成新输入的产物。
        #    `person_body`（大头照）是**派生文件**：由 subject.jpg 裁出来的，
        #    重裁一次就换 mtime，内容却没变 → 会把它当"换了参考图"，从此永久不复用。
        #    它的来源 subject.jpg 已经在 person 槽位里比过，派生件不再单独比。
        #    🩸 2026-10-26 起不再派生大头照了（台账 D48）—— 这里只为**老任务目录**
        #    里还躺着的 `subject_head.jpg` 保留，别以为现在还会生成它。
        created = float(rec.get("created_at") or 0)
        stale_refs = sorted(k for k, p in refs.items() if not k.endswith("_body")
                            and created and p.stat().st_mtime > created)

        for mode_dir in sorted(p for p in rdir.iterdir() if p.is_dir()):
            manifest = _load_json(mode_dir / "manifest.json")
            if not isinstance(manifest, dict):
                continue
            # 同名分段 → 对应的请求快照。序号一致（seg_001 ↔ request_001）。
            for name, raw in manifest.items():
                meta = _parse_manifest_key(raw)
                if "span" not in meta:
                    continue
                n = "".join(ch for ch in Path(name).stem if ch.isdigit())
                req = _load_json(mode_dir / f"request_{n or '001'}.json") or {}
                out_file = _asset_output(mode_dir, n)
                # 这段画面是不是"跟着嘴型走"：决定改词后它还作不作数。
                # 证据不全时按"是"处理 —— 少复用一次，好过让新台词对着旧口型。
                lip = (timeline.lip_dependent(work, meta["span"], inv)
                       if work and work.get("evidence") else True)
                script = (str(rec.get("script") or "")
                          if edit.get("audio") != "original" else "")
                words = (timeline.text_for_span(work or {}, script, meta["span"])
                         if script and lip else "")
                key = {
                    "source": source_sha,
                    "span": meta["span"],
                    "engine": meta["engine"],
                    "channel": str(req.get("channel") or rec.get("regen_channel") or ""),
                    "model": str(req.get("model") or rec.get("regen_model") or ""),
                    "resolution": str(req.get("resolution") or edit.get("resolution") or ""),
                    "audio": str(edit.get("audio") or ""),
                    "voice": str(rec.get("tts_voice") or ""),
                    "change": _canon_change(change),
                    "extra": str(edit.get("extra") or ""),
                    "refs": {k: sha256_file(v) for k, v in sorted(refs.items())},
                    # 编译后的提示词也进签名：模板改了，旧产物就不算同输入
                    "prompt": hashlib.sha256(
                        str(req.get("prompt") or "").encode("utf-8")).hexdigest()[:16]
                    if req.get("prompt") else "?",
                    # 文案只对**口型依赖**的段生效：空镜/背影改词，画面照样能复用
                    "words": words,
                    "lip": bool(lip),
                }
                out.append({
                    "id": f"{rid[:8]}:{Path(name).stem}",
                    "render": rid,
                    "mode": mode_dir.name,
                    "engine": meta["engine"],
                    "span": meta["span"],
                    "lip": bool(lip),
                    "sig": _sig(key),
                    "key": key,
                    "output": str(out_file) if out_file else "",
                    "sha256": sha256_file(out_file) if out_file and out_file.exists() else "",
                    "stale_refs": stale_refs,
                })
    return out


def _asset_output(mode_dir: Path, n: str) -> Path | None:
    """资产对应的**产物文件**：优先模型原始输出（gen/），退回拼装后的分段。"""
    gen = mode_dir / "gen"
    if gen.is_dir():
        cands = sorted(gen.glob(f"*{n}*.mp4")) or sorted(gen.glob("*.mp4"))
        if cands:
            return cands[0]
    for pat in (f"seg_{n}.mp4", f"piece_{n}.mp4", "*.mp4"):
        cands = sorted(mode_dir.glob(pat))
        if cands:
            return cands[0]
    return None


def _load_json(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# build / load / save
# ---------------------------------------------------------------------------

def build(cid: str) -> dict:
    """从现有任务目录生成作品文档（只读现有文件，不调模型）。"""
    task = clone_store.load(cid)
    if not task:
        raise FileNotFoundError(f"任务不存在：{cid}")
    rec = task.get("recipe") or {}
    src = clone_store.source_path(cid)
    if not src.exists():
        raise FileNotFoundError(f"找不到原片：{src}")

    shots = [
        {
            "i": int(s.get("i", n)),
            "start": _num(s.get("start", 0)),
            "end": _num(s.get("end", 0)),
            "dur": _num(s.get("dur", float(s.get("end", 0)) - float(s.get("start", 0)))),
            "motion": s.get("motion"),
            "keyframe": s.get("keyframe") or "",
        }
        for n, s in enumerate(rec.get("shots") or [])
    ]
    speech = rec.get("speech") or {}
    work = {
        "version": WORK_VERSION,
        "id": cid,
        "source": {
            "path": src.name,
            "sha256": sha256_file(src),
            "duration": _num((rec.get("source") or {}).get("duration", 0)),
            "width": int((rec.get("source") or {}).get("width") or 0),
            "height": int((rec.get("source") or {}).get("height") or 0),
            "fps": float((rec.get("source") or {}).get("fps") or 0),
            "has_audio": bool((rec.get("source") or {}).get("has_audio")),
        },
        "evidence": {
            "shots": shots,
            "speech": {
                "lang": speech.get("lang") or "",
                "segments": speech.get("segments") or [],
            },
        },
        "decisions": [
            {
                "render": r.get("id"),
                "mode": r.get("regen_mode"),
                "change": (r.get("edit") or {}).get("change"),
                "audio": (r.get("edit") or {}).get("audio"),
                "resolution": (r.get("edit") or {}).get("resolution"),
                "model": r.get("regen_model"),
                "spans": r.get("segments"),
                "replaced_shots": r.get("replaced_shots"),
            }
            for r in (task.get("renders") or [])
        ],
        "assets": [],
        "script": str((task.get("renders") or [{}])[-1].get("script") or "")
        if task.get("renders") else "",
    }
    # 资产要知道"这一段说不说话、露不露脸"，才能判改词后还作不作数
    work["assets"] = _scan_assets(cid, task, work)
    return work


def save(cid: str, work: dict) -> Path:
    p = clone_store.task_dir(cid) / "work.json"
    p.write_text(json.dumps(work, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def load(cid: str) -> dict | None:
    return _load_json(clone_store.task_dir(cid) / "work.json")


# ---------------------------------------------------------------------------
# check：只校验"引用是否成立"，不判断创作好坏
# ---------------------------------------------------------------------------

def check(cid: str, work: dict) -> list[dict]:
    issues: list[dict] = []

    def add(level: str, code: str, msg: str, where: str = "") -> None:
        issues.append({"level": level, "code": code, "msg": msg, "where": where})

    src = clone_store.source_path(cid)
    if not src.exists():
        add("error", "source_missing", f"原片不存在：{src}")
    elif sha256_file(src) != work["source"].get("sha256"):
        add("error", "source_drift", "原片内容与 work.json 记录的不一致（被替换过）")

    total = float(work["source"].get("duration") or 0)
    for s in work["evidence"]["shots"]:
        if s["end"] <= s["start"]:
            add("error", "shot_span", f"镜头 {s['i']} 的结束不大于开始", f"shot:{s['i']}")
        if total and s["end"] > total + 0.05:
            add("warn", "shot_out_of_bounds", f"镜头 {s['i']} 超出原片时长", f"shot:{s['i']}")

    for seg in work["evidence"]["speech"].get("segments") or []:
        a, b = float(seg.get("start", 0)), float(seg.get("end", 0))
        if b <= a:
            add("error", "speech_span", "语音段的结束不大于开始", f"speech:{a}")
        for ch in seg.get("chars") or []:
            t0, t1 = float(ch.get("s", 0)), float(ch.get("e", 0))
            if t1 < t0 or t0 < a - 0.05 or t1 > b + 0.05:
                add("warn", "char_out_of_segment",
                    f"字「{ch.get('c', '')}」的时间不在所属语音段内", f"speech:{a}")

    seen = set()
    for a in work.get("assets") or []:
        aid = a.get("id", "")
        if aid in seen:
            add("error", "asset_dup", f"资产 id 重复：{aid}", aid)
        seen.add(aid)
        if a.get("sig") != _sig(a.get("key") or {}):
            add("error", "asset_sig", "资产的签名与 key 对不上（文件被改过）", aid)
        f = a.get("output")
        if not f:
            add("error", "asset_no_output", "资产没有产物文件", aid)
        elif not Path(f).exists():
            add("error", "asset_missing", f"产物文件不存在：{f}", aid)
        elif a.get("sha256") and sha256_file(Path(f)) != a["sha256"]:
            add("error", "asset_drift", "产物文件内容与记录不一致", aid)
        a0, a1 = (a.get("span") or [0, 0])[:2]
        if total and (a1 <= a0 or a1 > total + 0.05):
            add("error", "asset_span", f"资产时间段不合法：[{a0}, {a1}]", aid)
        if a.get("stale_refs"):
            add("warn", "asset_stale_refs",
                f"参考图在出片后被换过（{','.join(a['stale_refs'])}），这份资产不再算同输入", aid)
    return issues


# ---------------------------------------------------------------------------
# plan：这次要哪些请求、哪些已有资产可以直接用
# ---------------------------------------------------------------------------

def _desired_units(cid: str, work: dict, intent: dict) -> list[dict]:
    """算出这次要动的单元（引擎 + 时间段）。全部走现有决策代码，不另算一套。"""
    from app.services import assemble, clone_pipeline, edit_spec, video_edit

    task = clone_store.load(cid)
    rec = (task or {}).get("recipe") or {}
    mode = (intent.get("mode") or "whole").strip().lower()
    spec = edit_spec.normalize(intent.get("edit") or intent)
    channel = intent.get("channel") or "auto"
    model = intent.get("model") or ""
    subject = clone_store.subject_path(cid)
    refs = {}
    for slot in clone_store.REF_SLOTS:
        p = clone_store.ref_path(cid, slot)
        if p.exists():
            refs[slot] = p
    src = clone_store.source_path(cid)
    inv = _load_inventory(cid)

    # 风格参考视频（A9）：复用的提示词必须和真跑时逐字一致，差一句就会被判成
    # "输入变了" → 用户能看到可复用的段全变成 0。
    _sv = None
    if (spec.get("change") or {}).get("style_video"):
        _p = clone_store.ref_video_path(cid, "style")
        _sv = _p if _p.exists() else None

    if mode == "whole":
        plan = video_edit.prepare(rec, prompt="", spec=spec, refs=refs,
                                  subject_image=subject if subject.exists() else None,
                                  channel=channel, model=model, inventory=inv,
                                  style_video=_sv)
        spans, _ = video_edit.plan_spans(src, rec, plan)
        prompts = _video_prompts(plan, spans, rec.get("shots") or [], rec=rec)
        return [{"engine": "video", "span": _span(a, b), "shots": [], "prompt": p,
                 **_resolved(plan)}
                for (a, b), p in zip(spans, prompts)]

    if mode == "shots":
        picks = intent.get("shots") or assemble.pick_shots(
            rec.get("shots") or [], float(intent.get("ratio") or 0), 99)
        by_i = {int(s["i"]): s for s in (rec.get("shots") or [])}
        return [{"engine": "still",
                 "span": _span(by_i[i]["start"], by_i[i]["end"]), "shots": [i]}
                for i in picks if i in by_i]

    # auto：分诊的全部决策都在 _auto_decision 里，preview 和真跑共用同一份
    d = clone_pipeline._auto_decision(
        src, rec, spec=spec, regen_prompt="", regen_shots=intent.get("shots") or None,
        regen_channel=channel, regen_model=model,
        subject_image=subject if subject.exists() else None, subject_asset="",
        refs=refs, inventory=inv,
    )
    prompts = _video_prompts(d["plan"], d["spans"], rec.get("shots") or [], rec=rec)
    return [{"engine": "video", "span": _span(a, b), "shots": [], "prompt": p,
             **_resolved(d["plan"])}
            for (a, b), p in zip(d["spans"], prompts)]


def _resolved(plan: dict) -> dict:
    """把 `_prepare` 算出来的**实际**通道 / 型号 / 分辨率带上。

    🩸 复用判定必须比"真跑发出去的东西"，不能比用户那句"自动"：
    界面上通道留空 = auto、分辨率留空 = auto，而资产里记的是 `minimax` /
    `MiniMax-H3-Max` / `480P`。拿"auto"去比，永远是 0 段复用 —— 面板就成了
    摆设（2026-10-22 实测：同一个规格重发，2 段全被算成要重画）。
    """
    return {
        "channel": str(plan.get("ch") or ""),
        "model": str(plan.get("model") or ""),
        "resolution": str(plan.get("resolution") or ""),
    }


def _canon_change(change: dict | None) -> dict:
    """签名里比"换什么"用的规范化摘要。

    🩸 多人换人加了 `person_ids / person2 … person12` 这些字段。如果原样进签名，
    所有历史出片记录都会因为"多了几个空字段"被判成输入变了 —— 面板从此永远
    显示 0 段可复用（老记录里根本没有这几个键）。空值一律不参与比较：
    等价于"这次没有第 N 个人"。
    """
    return edit_spec.sig_change(change)


def _unit_key(intent: dict, spec: dict, unit: dict, source_sha: str,
              refs: dict, lip: bool, words: str) -> dict:
    """一个单元的**语义输入指纹**。

    台账、plan、验收都读这一份 —— 三处各写一份，迟早出现"plan 说能复用、
    真跑又生成了一遍"。
    """
    return {
        "source": source_sha,
        "span": unit["span"],
        "engine": unit["engine"],
        "channel": str(unit.get("channel") or intent.get("channel") or ""),
        "model": str(unit.get("model") or intent.get("model") or ""),
        "resolution": str(unit.get("resolution") or spec.get("resolution") or "auto"),
        "audio": str(spec.get("audio") or ""),
        # 音色变了，念出来的声音就变了 —— 同台词换音色也得重配、重对口型。
        # （引擎那边的键带的是配音文件的哈希；这里只能拿音色 ID 当代理，
        #  两处覆盖的是同一件事：口型跟着"这条配音"走。）
        "voice": str(intent.get("voice") or ""),
        "change": _canon_change(spec.get("change")),
        "extra": str(spec.get("extra") or ""),
        "refs": {k: sha256_file(v) for k, v in sorted(refs.items())},
        "words": words,
        "lip": bool(lip),
        # 静帧引擎（P0）拿不到编译后的提示词 → 用 "?" 占位，永远不命中复用。
        # 宁可多花一次，也不要把"看起来一样"当成"同输入"。
        "prompt": hashlib.sha256(
            str(unit.get("prompt") or "").encode("utf-8")).hexdigest()[:16]
        if unit.get("prompt") else "?",
    }


def plan(cid: str, work: dict | None, intent: dict) -> dict:
    """出片前的复用判定：**零成本、不调模型**。

    intent 和出片参数同形（mode / edit / channel / model / shots / ratio），
    这样"预览说几段"和"真跑几段"不可能飘开。
    """
    from app.services import edit_spec

    work = work or build(cid)
    spec = edit_spec.normalize(intent.get("edit") or intent)
    change = spec.get("change") or {}
    refs = _ref_files(cid, change)
    source_sha = sha256_file(clone_store.source_path(cid))
    script = str(intent.get("script") or "") if spec.get("audio") != "original" else ""
    inv = _load_inventory(cid)

    assets = [a for a in (work.get("assets") or []) if not a.get("stale_refs")]
    reuse, requests = [], []
    for n, u in enumerate(_desired_units(cid, work, intent)):
        # 改词只影响**口型依赖**的段：空镜/背影的台词变了，画面照样复用
        lip = (timeline.lip_dependent(work, u["span"], inv)
               if work.get("evidence") else True)
        uwords = (timeline.text_for_span(work, script, u["span"])
                  if script and lip else "")
        key = _unit_key(intent, spec, u, source_sha, refs, lip, uwords)
        sig = _sig(key)
        hit = next((a for a in assets if a["sig"] == sig), None)
        # unit / label 是给界面看的：用户要能认出"第几段、哪一秒到哪一秒"，
        # 只给个签名等于没说
        tag = {"unit": n, "label": f"{u['span'][0]:.1f}–{u['span'][1]:.1f}s",
               "span": u["span"], "engine": u["engine"], "lip": bool(lip)}
        if hit:
            reuse.append({**tag, "asset": hit["id"], "sig": sig})
        else:
            same = [a for a in assets
                    if a["span"] == u["span"] and a["engine"] == u["engine"]]
            if not same:
                # 有这一段、但被判成"参考图换过"的资产：不能跟"从没生成过"说成一样，
                # 用户听完只会去重跑一遍，还是不复用
                stale = [a for a in (work.get("assets") or [])
                         if a["span"] == u["span"] and a["engine"] == u["engine"]
                         and a.get("stale_refs")]
                if stale:
                    slots = sorted({s for a in stale for s in (a["stale_refs"] or [])})
                    why = f"参考图在这之后被换过（{','.join(slots)}），旧画面不算同输入"
                else:
                    why = "没有生成过这一段"
            # 🩸 只有**这一段该念的词真的和资产里不一样**才说"台词变了"。
            # 拿"有词"当条件会让换人物也报成台词变了 —— 用户照着这句去改台词，
            # 改完发现画面还是重新生成，就再也不信这张清单了。
            elif lip and any(a["key"].get("words") != uwords for a in same):
                why = "台词变了，且这一段跟嘴型"
            else:
                why = "输入变了（参考图 / 型号 / 提示词等）"
            requests.append({**tag, "sig": sig, "why": why})

    def secs(items):
        return _num(sum(b - a for a, b in (x["span"] for x in items)))

    return {
        "mode": (intent.get("mode") or "whole"),
        "source_sha": source_sha,
        "reuse": reuse,
        "requests": requests,
        "totals": {
            "units": len(reuse) + len(requests),
            "reuse_units": len(reuse), "request_units": len(requests),
            "reuse_seconds": secs(reuse), "request_seconds": secs(requests),
        },
        "granularity": {"words": "segment", "shots": "unit"},
    }
