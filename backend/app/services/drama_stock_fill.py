"""B4 补完：自动配画面（联网搜库 + 降级阶梯 + 诚实标注）。

出处（竞品 `src/lib/stock-fill.ts` / `src/lib/stock-matcher.ts`）：
  · `stock-matcher.ts:21-39` broadenQuery：原词搜不到就逐级放宽
    （最后两个词 → 最后一个词 → 主题锚 → 通用兜底词），**找不到才往下走**
  · `stock-matcher.ts:38-50` fallbackLevelOf：original / narrowed / universal 三档诚实标注
  · `stock-fill.ts:68-108` searchShotCandidates：整条阶梯跑一遍，记下「哪一句搜到的」
  · `stock-matcher.ts:100-165` scoreCandidate：命中词 ×10、竖屏 +5、横屏 −3、已用过 −8、
    同源（同作者）+6、时长够填满槽位 +3
  · `stock-matcher.ts:186-221` continuityGroups：共享实体词的镜头归一组，后面的镜头偏向同源
  · `stock-fill/route.ts:60-...` 整次填充共享一个 usedIds（跨镜不重复）

我们的差异（都写在下面代码里）：
  1. **查询是中文**：竞品分镜带英文 `stockKeywords`，我们没有。阶梯改成中文版
     —— 原文 → 按动词切出主要名词块（中文没空格，切在动词上）→ 商品名当主题锚 → 英文通用兜底。
     中文子串匹配的方向与 B4 一致（素材标题/标签当关键词，去镜头描述里找）。
  2. **默认配「图片参考画面」，不配视频**：我们的视频素材是「当这一镜的画面」（会切碎 AI 段、
     段数变多＝更多钱），不能自动替主人做这个决定。要视频得显式传 `media_type="video"`。
  3. **通用兜底不硬塞**：竞品的 universal 档是「保底一定有画面」；我们的图片是**喂给 AI 的场景参考**，
     塞一张不相关的「abstract background」会直接污染这一镜的提示词 —— 所以 universal 档默认
     **只报告不绑定**（`allow_universal=True` 才绑），并在结果里标出来。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.services import drama_materials, drama_stock

#: 通用兜底词（`stock-matcher.ts:10`，原样照抄）
UNIVERSAL_FALLBACKS = ("abstract background", "lifestyle", "nature", "light")

#: 中文切分用的动词/虚词（我们的适配：中文没有空格，名词块靠这些词断开）
_BREAK_WORDS = (
    "放下", "抽出", "拿起", "递给", "举起", "放进", "抬头", "低头", "转身", "点头", "摇头",
    "打开", "合上", "走开", "靠近", "离开", "擦", "拿", "走", "说", "看", "笑", "推", "拉",
    "站", "坐", "躺", "喝", "吃", "穿", "戴", "倒", "挤", "撕", "抹", "拍", "指", "闻",
    "把", "被", "在", "的", "了", "着", "很", "就", "都", "也", "还", "又", "正", "刚",
    "她", "他", "它", "我", "你", "我们", "他们", "然后", "接着", "已经", "正在", "开始", "继续",
)
#: 运镜/景别词不是内容，不参与检索（`NON_ENTITY_TERMS`，`stock-matcher.ts:186-190`）
_GENERIC = ("镜头", "特写", "中景", "近景", "远景", "全景", "画面", "慢动作", "俯拍", "仰拍",
            "跟拍", "固定", "缓推", "快推", "拉远", "平移", "摇镜")

_CJK = re.compile(r"[㐀-鿿]")


def _clean(text: str) -> str:
    """去标点与运镜词，压缩空白。"""
    s = str(text or "")
    for g in _GENERIC:
        s = s.replace(g, " ")
    return re.sub(r"\s+", " ", re.sub(r"[^\w㐀-鿿]+", " ", s)).strip()


def _split_parts(text: str) -> list[str]:
    """按动词/虚词把中文句子切成词块（中文没有空格，只能这样断句）。"""
    s = _clean(text)
    if not s:
        return []
    pattern = "|".join(re.escape(w) for w in sorted(_BREAK_WORDS, key=len, reverse=True))
    return [p.strip() for p in re.split(pattern, s) if len(p.strip()) >= 2]


def main_terms(text: str) -> str:
    """中文主要名词块：在动词/虚词处断开，取最长的一段（≥2 字）。

    这是竞品 `stock-matcher.ts:26-27`「取最后两个词 / 最后一个词」的中文对应 ——
    中文没有空格，只能靠动词断句。断不出比原文更短的块就返回空串（不硬造）。
    """
    s = _clean(text)
    parts = _split_parts(text)
    if not parts:
        return ""
    best = max(parts, key=len)
    return "" if best == s else best


def shot_keywords(shot: dict) -> list[str]:
    """这一镜自带的英文检索词（竞品 `stockKeywords`，最多 3 个）。

    出处：竞品 `script-engine/generator.ts:210-212`（LLM 输出 `searchTerms` 或
    `stockKeywords`，清洗后取前 3 个）+ `stock-matcher.ts:54-57`（`shotQuery` 优先用它）。
    """
    raw = (shot or {}).get("stock_keywords")
    if raw is None:
        raw = (shot or {}).get("stockKeywords")
    if raw is None:
        raw = (shot or {}).get("searchTerms")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(k).strip() for k in raw if str(k).strip()][:3]


def candidate_on_topic(cand: dict, keywords: list[str]) -> bool:
    """候选标题/标签必须命中检索词之一，否则**不绑** —— 宁可留空让商品图兜底。

    出处：竞品 `stock-matcher.ts:100-139` 把「命中词数」当打分权重；这里把权重变成
    门槛。🩸 2026-11-07 实测：keyless 源按 `beer glass foam table` 返回一张 18 世纪
    版画（标题 `The Last Drop`，一个词都没命中）—— 只按「有没有结果」绑，会把废画面
    直接塞进成片，比空着更糟。
    """
    text = " ".join([str(cand.get("title") or ""),
                     " ".join(str(t) for t in (cand.get("tags") or []))]).strip()
    if not text:
        return False        # 没有任何可判定的文字 → 不算对题
    groups = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    if not groups:
        return False
    # 🩸 用**整组命中**而不是「命中组里任意一个词」：实测镜 1 的
    # `holding bottle` 靠 `holding` 一个泛用词就把「老头抱挂钟」放了进来。
    # 一组 = 一次检索的完整词，组内每个词都要在标题/标签里出现才算这组命中。
    hay = text.lower()
    for g in groups:
        toks = [t for t in re.split(r"[^0-9a-z㐀-鿿]+", g.lower()) if len(t) >= 2]
        if toks and all(t in hay for t in toks):
            return True
    return False


def query_ladder(description: str, subject: str = "",
                 keywords: list[str] | None = None) -> list[tuple[str, str]]:
    """降级阶梯：[(query, level)]，按顺序尝试。

    level 口径与竞品 `fallbackLevelOf`（`stock-matcher.ts:47-51`）一致：
    原文命中 = original；缩短/主题锚命中 = narrowed；通用兜底命中 = universal。

    🩸 分镜带英文检索词时**只用它**（竞品 `shotQuery` 语义：有 stockKeywords 就不用
    description）—— 中文长描述在 keyless 素材源（Openverse/Wikimedia）上实测 0 命中。
    """
    kw = " ".join([str(k).strip() for k in (keywords or []) if str(k).strip()])
    original = _clean(kw or description)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(q: str, level: str) -> None:
        k = str(q or "").strip().lower()
        if not k or k in seen:
            return
        seen.add(k)
        out.append((str(q).strip(), level))

    add(original, "original")
    if kw:
        # 英文检索词的放宽：最后两个词 → 最后一个词（`broadenQuery`，`stock-matcher.ts:21-39`）
        words = kw.split()
        if len(words) > 2:
            add(" ".join(words[-2:]), "narrowed")
        if len(words) > 1:
            add(words[-1], "narrowed")
    else:
        add(main_terms(description), "narrowed")
    if subject:
        add(_clean(subject), "narrowed")
    for u in UNIVERSAL_FALLBACKS:
        add(u, "universal")
    return out


def level_of(original: str, matched: str) -> str:
    """这一镜最后是按哪一档搜到的（`stock-matcher.ts:47-51`）"""
    m = str(matched or "").strip().lower()
    if m == _clean(original).lower():
        return "original"
    return "universal" if m in {u.lower() for u in UNIVERSAL_FALLBACKS} else "narrowed"


def orientation_of(c: dict) -> str:
    w, h = int(c.get("width") or 0), int(c.get("height") or 0)
    if not w or not h:
        return ""
    return drama_stock.orientation_of(w, h)


def author_key(c: dict) -> str:
    """同源键 = 源 + 作者；占位作者不算（`stock-matcher.ts:196-210`）"""
    author = str(c.get("author") or "").strip().lower()
    source = str(c.get("source") or "").lower()
    if not author or author == source or author in ("unknown", "internet archive"):
        return ""
    return f"{source}:{author}"


def score_candidate(shot_text: str, cand: dict, *, prefer_portrait: bool = True,
                    used_ids: set | None = None, same_source: set | None = None,
                    slot_sec: float = 0) -> int:
    """单条候选打分（`stock-matcher.ts:100-139`，权重逐条照抄）。

    🩸 中文方向与 B4 一致：素材标题/标签当关键词（wanted），去镜头描述（hay）里找
    —— `match_score(text, query)` 里 text 是 hay。
    """
    cand_text = " ".join([str(cand.get("title") or ""),
                          " ".join(str(t) for t in (cand.get("tags") or []))]).strip()
    overlap = drama_materials.match_score(shot_text, cand_text) if cand_text else 0
    score = overlap * 10
    if prefer_portrait:
        o = orientation_of(cand)
        if o == "portrait":
            score += 5
        elif o == "landscape":
            score -= 3
    if cand.get("media_type") == "video" and slot_sec and (cand.get("duration_sec") or 0) >= slot_sec:
        score += 3
    if used_ids and f"{cand.get('source')}:{cand.get('id')}" in used_ids:
        score -= 8
    if same_source:
        k = author_key(cand)
        if k and k in same_source:
            score += 6
    return score


def pick_best(shot_text: str, candidates: list[dict], **opts) -> dict | None:
    """打分取最高；同分保留先出现的（`stock-matcher.ts:150-163`）"""
    best, best_score = None, None
    for c in candidates:
        s = score_candidate(shot_text, c, **opts)
        if best_score is None or s > best_score:
            best, best_score = c, s
    return best


def entity_terms(text: str) -> set[str]:
    """实体词：≥2 个汉字（或 ≥3 个字母）且不是运镜词（`stock-matcher.ts:177-194`）。

    🩸 中文要按动词先断句，否则整句会被当成一个「实体词」，两镜永远归不到一组。
    """
    out = set()
    for chunk in _split_parts(text):
        for t in re.split(r"[^\w㐀-鿿]+", chunk):
            if not t or t in _GENERIC:
                continue
            if _CJK.search(t):
                if len(t) >= 2:
                    out.add(t)
            elif len(t) >= 3:
                out.add(t)
    return out


def continuity_groups(shots: list[dict]) -> list[list[int]]:
    """共享实体词的镜头归一组（并查集，`stock-matcher.ts:212-221`）"""
    parent = list(range(len(shots)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    first: dict[str, int] = {}
    for i, s in enumerate(shots):
        for t in entity_terms(str(s.get("description") or "")):
            if t in first:
                parent[find(i)] = find(first[t])
            else:
                first[t] = i
    groups: dict[int, list[int]] = {}
    for i, s in enumerate(shots):
        groups.setdefault(find(i), []).append(int(s.get("id") or i + 1))
    return list(groups.values())


# ---------------------------------------------------------------- 下载进素材库

def store_candidate(mat_dir: Path, cand: dict) -> tuple[dict, bool]:
    """把候选下载进素材库并写好出处。返回 (素材行, 是否重复)。

    素材名 = sha256 文件名（`drama_materials.store`），原创名取候选标题；
    作者/许可/出处页/来源写进 sidecar —— B5 授权清单与发布门禁直接读得到。
    """
    incoming = mat_dir / ".incoming"
    base = f"{drama_stock._safe_base(cand.get('source') or 'stock')}-{drama_stock._safe_base(str(cand.get('id') or ''))}"
    path, _size = drama_stock.download(cand, incoming, base)
    title = re.sub(r"[\\/]", "-", str(cand.get("title") or "").strip())[:120] or base
    provenance = {
        "author": str(cand.get("author") or "")[:drama_materials.MAX_NAME_LEN],
        "license": str(cand.get("license") or "")[:drama_materials.MAX_NAME_LEN],
        "source_url": str(cand.get("page_url") or "")[:drama_materials.MAX_NAME_LEN],
        "provider": str(cand.get("source") or ""),
    }
    tags = []
    for t in (cand.get("tags") or [])[:drama_materials.MAX_TAGS]:
        t = str(t).strip()[:drama_materials.MAX_TAG_LEN]
        if t and t not in tags:
            tags.append(t)
    try:
        with path.open("rb") as fh:
            result = drama_materials.store(mat_dir, f"{title}{path.suffix.lower()}", fh)
        row = drama_materials.update_meta(mat_dir, result["material"]["name"],
                                          tags=tags or None, provenance=provenance)
        return row, bool(result["duplicate"])
    finally:
        path.unlink(missing_ok=True)
        try:
            incoming.rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------- 自动配画面

def _bindings(doc: dict, key: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for item in (doc.get(key) or []):
        try:
            out[int(item.get("shot_id"))] = str(item.get("material") or "")
        except (TypeError, ValueError):
            continue
    return out


def _save_bindings(doc: dict, key: str, mapping: dict[int, str]) -> None:
    doc[key] = [{"shot_id": sid, "material": name} for sid, name in sorted(mapping.items())
                if name]


def auto_fill(doc: dict, mat_dir: Path, *, media_type: str = "image", source: str = "all",
              force: bool = False, per_page: int = 8, allow_universal: bool = False,
              keys: dict | None = None, max_shots: int = 0) -> dict:
    """逐镜自动配画面（联网）。会改 `doc` 的 `shot_materials` / `shot_clips`。

    - `media_type="image"`（默认）→ 绑定 `shot_materials`（当参考画面，不改出片段数）
    - `media_type="video"` → 绑定 `shot_clips`（当这一镜的画面；**段数会变多，前端要先警告**）
    - 已经绑过的镜头默认跳过（`force=True` 才重配）
    - 通用兜底档默认不绑（见文件头第 3 条）
    """
    if media_type not in ("image", "video"):
        raise ValueError("media_type 只能是 image / video")
    bind_key = "shot_clips" if media_type == "video" else "shot_materials"
    shots = [s for s in ((doc.get("storyboard_json") or {}).get("shots") or []) if isinstance(s, dict)]
    shots = [dict(s, id=int(s.get("id") or i + 1)) for i, s in enumerate(shots)]
    bound = _bindings(doc, bind_key)
    other_bound = _bindings(doc, "shot_clips" if bind_key == "shot_materials" else "shot_materials")
    subject = str(((doc.get("product") or {}).get("name"))
                  or ((doc.get("topic") or {}).get("text"))
                  or "").strip()

    todo = []
    skipped = []
    for s in shots:
        sid = int(s["id"])
        if sid in bound and not force:
            skipped.append({"shot_id": sid, "reason": "已配过"})
            continue
        if sid in other_bound:
            skipped.append({"shot_id": sid, "reason": "这一镜已经是实拍画面（素材当画面），不再配参考图"
                            if bind_key == "shot_materials" else "这一镜已配参考画面，先解绑再换"})
            continue
        todo.append(s)
    if max_shots:
        todo = todo[:max_shots]

    used_ids: set[str] = set()
    used_materials: set[str] = set()
    same_source_by_group: dict[int, set] = {}
    group_of = {}
    for gi, g in enumerate(continuity_groups(shots)):
        for sid in g:
            group_of[sid] = gi

    results, unmatched = [], []
    for s in todo:
        sid = int(s["id"])
        text = str(s.get("description") or "").strip()
        slot = float(s.get("duration") or 0)
        group_sources = same_source_by_group.setdefault(group_of.get(sid, sid), set())

        kws = shot_keywords(s)
        picked, matched_query, matched_level = None, "", ""
        for q, lv in query_ladder(text, subject, kws):
            if lv == "universal" and not allow_universal:
                # 这一档本来就不绑（见文件头第 3 条）→ 别联网白搜，4 档阶梯全跑一遍很慢
                continue
            try:
                res = drama_stock.search_all(q, media_type=media_type, per_page=per_page,
                                             orientation="portrait", keys=keys, mat_dir=mat_dir)
                cands = [c for c in (res.get("candidates") or [])
                         if c.get("media_type") == media_type and c.get("download_url")]
                if kws:
                    # 只认标题/标签命中检索词的候选（见 `candidate_on_topic`）
                    cands = [c for c in cands if candidate_on_topic(c, kws)]
            except Exception:
                continue
            if not cands:
                continue
            matched_query, matched_level = q, level_of(text, q)
            # 跨镜去重：先只在「没用过的候选」里挑；全用过就走下一档，别把同一份素材绑两次
            fresh = [c for c in cands if f"{c.get('source')}:{c.get('id')}" not in used_ids]
            if not fresh:
                continue
            picked = pick_best(text, fresh, used_ids=used_ids, same_source=group_sources,
                               slot_sec=slot)
            if picked is not None and matched_level == "universal" and not allow_universal:
                # 通用兜底不硬塞：这一镜就到这里（见文件头第 3 条）
                picked = None
                break
            if picked is not None:
                break

        if not picked:
            reason = ("只搜到通用兜底词条（可能不贴题），没绑" if matched_level == "universal"
                      else "没搜到贴题的素材")
            unmatched.append({"shot_id": sid, "query": text, "matched_query": matched_query,
                              "level": matched_level, "reason": reason})
            continue
        try:
            row, duplicate = store_candidate(mat_dir, picked)
        except Exception as e:  # noqa: BLE001
            unmatched.append({"shot_id": sid, "query": matched_query,
                              "reason": f"下载失败：{str(e)[:80]}"})
            continue
        name = row["name"]
        if name in used_materials:
            # 内容相同（同一张图 / 同一条视频）：跨镜不再重复用
            unmatched.append({"shot_id": sid, "query": matched_query,
                              "reason": "搜到的和前面某一镜是同一份素材"})
            continue
        used_materials.add(name)
        used_ids.add(f"{picked.get('source')}:{picked.get('id')}")
        k = author_key(picked)
        if k:
            group_sources.add(k)
        bound[sid] = name
        results.append({
            "shot_id": sid, "material": name, "source": picked.get("source"),
            "title": picked.get("title") or "", "author": picked.get("author") or "",
            "license": picked.get("license") or "", "query": matched_query,
            "level": matched_level, "duplicate": duplicate,
            "score": score_candidate(text, picked, used_ids=None, same_source=group_sources,
                                     slot_sec=slot),
        })

    _save_bindings(doc, bind_key, bound)
    return {
        "media_type": media_type,
        "binding": bind_key,
        "filled": len(results),
        "total": len(todo),
        "skipped": skipped,
        "unmatched": unmatched,
        "results": results,
        "levels": {lv: sum(1 for r in results if r["level"] == lv)
                   for lv in ("original", "narrowed", "universal")},
        "allow_universal": bool(allow_universal),
    }
