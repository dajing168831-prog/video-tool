"""素材授权清单（B5）—— 把每一件素材的出处/作者/许可聚成一份可交付的证明。

出处：竞品 `src/lib/asset-credits.ts:1-247`（许可分级 / 署名行 / 清单 / Markdown 报告）、
      `src/app/api/project/[id]/credits/route.ts`（导出接口）。

为什么要有（竞品文件头 `:3-7`）：免费工具不给商用许可证明 —— 投流审核会因为「素材来源不明」
拒掉视频或封号。所以清单本身是**交付物**，不是备注。

抄的规则（逐条有出处）：
  · 三档风险 `ok / attribution / review`（`:10`、`:75-93`）
  · **NC / ND 一律 review**：非商用与禁演绎都不能进投流（`:79-81`）
  · PD / PDM / CC0 → ok 免署名（`:82-84`）；Pexels / Pixabay → ok 免署名（`:86`）
  · Coverr → 需署名（`:88`）；CC BY / BY-SA → 需署名（`:90`）；其余（GFDL、自定义条款）→ review（`:92`）
  · 署名行「作者 · 许可 · 链接」（`:96-100`）
  · 自有素材 / AI 素材 = ok 免署名（`:104-125`）
  · 汇总：需署名数 / 需复核数 / `commercialSafe = 需复核 == 0`（`:177-184`）
  · Markdown 报告三段：需附署名 / 需人工复核 / 全部素材（`:195-247`）

字段名与**已有的发布门禁**（`drama_compliance.gate_from_credits`）对齐：camelCase 的
`shotId / requiresAttribution / attributionLine / note.zh`、`summary.needsAttribution`。
门禁是先写的，这里跟着它走 —— 免得同一份清单两套键名。

我们的差异：
  · 我们没有 stock 资产表，所以「第三方」的唯一来源是**主动申报了许可/作者的东西**：
    素材库里的导入素材、以及登记了出处的 BGM。没申报的一律算自有（与竞品 local 素材一致）。
    🩸 BGM 这条与竞品刻意不同：竞品的曲子是 stock 曲库下载、自带 sidecar 出处，所以「许可不明」是真风险；
    我们的是使用者自己传的文件，没申报就默认自有 —— 否则每首自备 BGM 都会让发布门禁报 warn。
  · AI 素材按**出片段**列（每段一条），不是逐镜；我们的段就是出片单元。
  · `shotId=None` 表示「素材库里还没挂到分镜」；`-1` 留给 BGM（与竞品一致）。
"""
from __future__ import annotations

import re

RISK_OK = "ok"
RISK_ATTRIBUTION = "attribution"
RISK_REVIEW = "review"

VIDEO_EXT = re.compile(r"\.(mp4|webm|mov|mkv|avi)$", re.I)
AUDIO_EXT = re.compile(r"\.(mp3|m4a|aac|ogg|opus|wav|flac)$", re.I)

#: NC / ND 的判定（`asset-credits.ts:79-81`）—— 前后都不能紧挨字母，避免 "since"/"and" 误伤
_NC = re.compile(r"(^|[^a-z])nc([^a-z]|$)")
_ND = re.compile(r"(^|[^a-z])nd([^a-z]|$)")
#: CC BY / BY-SA（`:90`）
_BY = re.compile(r"(^|[^a-z])by([^a-z]|$)|cc[- ]by")

NOTE_REVIEW = {"zh": "许可不明或含 NC/ND 限制，商用投流前请人工确认或替换",
               "en": "Unclear or NC/ND-restricted license; confirm or replace before commercial ads"}
NOTE_ATTRIBUTION = {"zh": "CC 署名类许可：可商用，发布时需附署名（下方给出可直接复制的署名行）",
                    "en": "CC attribution license: commercial use OK, credit required"}
NOTE_FREE = {"zh": "可免署名商用", "en": "Commercial use without attribution"}
NOTE_OWN = {"zh": "自有素材（上传/商品图），无需第三方授权",
            "en": "Own material (upload/product image); no third-party license needed"}
NOTE_AI = {"zh": "AI 生成素材（发布时保持 AIGC 标识合规即可）",
           "en": "AI-generated material (keep the AIGC disclosure compliant when publishing)"}
NOTE_BGM_REVIEW = {"zh": "BGM 许可不明，投流前请人工确认", "en": "BGM license unclear; confirm before running ads"}
NOTE_BGM_ATTR = {"zh": "BGM 为 CC 署名类许可，发布时需附署名",
                 "en": "BGM is CC-attribution licensed; credit required"}
NOTE_BGM_FREE = {"zh": "BGM 可免署名商用", "en": "BGM: commercial use without attribution"}


def classify_license(license: str | None) -> tuple[str, bool]:
    """许可 → (风险档, 是否需署名)。`classifyLicense`（`asset-credits.ts:75-93`）"""
    l = (license or "").strip().lower()
    if not l or l == "unknown":
        return RISK_REVIEW, False
    if _NC.search(l):
        return RISK_REVIEW, False
    if _ND.search(l):
        return RISK_REVIEW, False
    if "public domain" in l or l == "pdm" or "cc0" in l or l == "pd":
        return RISK_OK, False
    if l in ("pexels", "pixabay"):
        return RISK_OK, False
    if l == "coverr":
        return RISK_ATTRIBUTION, True
    if _BY.search(l):
        return RISK_ATTRIBUTION, True
    return RISK_REVIEW, False


def attribution_line(*, author: str | None = None, license: str | None = None,
                     source_url: str | None = None) -> str:
    """「作者 · 许可 · 链接」—— 可直接粘进发布文案（`asset-credits.ts:96-100`）"""
    parts = [(author or "").strip() or "Unknown author",
             (license or "").strip() or "License unknown"]
    if (source_url or "").strip():
        parts.append(source_url.strip())
    return " · ".join(parts)


def _kind(file_path: str | None) -> str:
    """按扩展名判素材种类（`asset-credits.ts:59-67`）"""
    if not file_path:
        return "unknown"
    if VIDEO_EXT.search(file_path):
        return "video"
    if AUDIO_EXT.search(file_path):
        return "audio"
    return "image"


def _where(item: dict) -> str:
    """清单里这一项属于哪 —— 素材库 / BGM / 分镜 N。"""
    sid = item.get("shotId")
    if sid is None:
        return "素材库"
    return "BGM" if int(sid) < 0 else f"分镜 {int(sid) + 1}"


def own_item(shot_id: int | None, name: str, provider: str = "local") -> dict:
    """自有素材（上传/商品图）—— 免第三方授权（`asset-credits.ts:104-114`）"""
    return {
        "shotId": shot_id,
        "kind": _kind(name),
        "origin": "own",
        "provider": provider or "local",
        "requiresAttribution": False,
        "risk": RISK_OK,
        "note": dict(NOTE_OWN),
    }


def ai_item(shot_id: int | None, name: str, provider: str = "") -> dict:
    """AI 生成素材 —— 免授权，但发布要保持 AIGC 标识合规（`:115-125`）"""
    item = {
        "shotId": shot_id,
        "kind": _kind(name),
        "origin": "ai",
        "requiresAttribution": False,
        "risk": RISK_OK,
        "note": dict(NOTE_AI),
    }
    if provider:
        item["provider"] = provider
    return item


def third_party_item(shot_id: int | None, name: str, *, author: str = "", license: str = "",
                     source_url: str = "", provider: str = "") -> dict:
    """申报了出处的导入素材 —— 按许可分级（`:126-146`）"""
    risk, needs = classify_license(license)
    item = {
        "shotId": shot_id,
        "kind": _kind(name),
        "origin": "stock",
        "requiresAttribution": needs,
        "risk": risk,
        "note": dict(NOTE_REVIEW if risk == RISK_REVIEW
                     else NOTE_ATTRIBUTION if needs else NOTE_FREE),
    }
    if provider:
        item["provider"] = provider
    if author:
        item["author"] = author
    if license:
        item["license"] = license
    if source_url:
        item["sourceUrl"] = source_url
    if needs:
        item["attributionLine"] = attribution_line(author=author, license=license,
                                                   source_url=source_url)
    return item


def build_manifest(project_name: str, assets: list[dict], bgm: dict | None = None) -> dict:
    """清单主体。`assets` 每项：{shot_id, type, provider, name, author, license, source_url}

    `type` 取 own / ai / stock（stock = 申报了第三方出处）。`shot_id=None` = 素材库。
    """
    items: list[dict] = []
    for a in assets:
        t = str(a.get("type") or "own")
        raw_sid = a.get("shot_id")
        sid = None if raw_sid is None else int(raw_sid)
        name = str(a.get("name") or "")
        if t == "ai":
            items.append(ai_item(sid, name, str(a.get("provider") or "")))
        elif t == "stock":
            items.append(third_party_item(
                sid, name,
                author=str(a.get("author") or ""), license=str(a.get("license") or ""),
                source_url=str(a.get("source_url") or ""), provider=str(a.get("provider") or ""),
            ))
        else:
            items.append(own_item(sid, name, str(a.get("provider") or "local")))

    bgm_item = None
    if bgm:
        risk, needs = classify_license(str(bgm.get("license") or ""))
        bgm_item = {
            "shotId": -1,
            "kind": "audio",
            "origin": "stock",
            "requiresAttribution": needs,
            "risk": risk,
            "note": dict(NOTE_BGM_REVIEW if risk == RISK_REVIEW
                         else NOTE_BGM_ATTR if needs else NOTE_BGM_FREE),
        }
        for src, dst in (("author", "author"), ("license", "license"), ("source_url", "sourceUrl")):
            if bgm.get(src):
                bgm_item[dst] = str(bgm[src])
        if needs:
            bgm_item["attributionLine"] = attribution_line(
                author=bgm.get("author"), license=bgm.get("license"),
                source_url=bgm.get("source_url"))

    all_items = items + ([bgm_item] if bgm_item else [])
    manifest = {
        "project": project_name,
        "items": items,
        "summary": {
            "total": len(all_items),
            "needsAttribution": sum(1 for i in all_items if i["requiresAttribution"]),
            "needsReview": sum(1 for i in all_items if i["risk"] == RISK_REVIEW),
            "commercialSafe": all(i["risk"] != RISK_REVIEW for i in all_items),
        },
    }
    if bgm_item:
        manifest["bgm"] = bgm_item
    return manifest


KIND_LABEL = {"image": "图片", "video": "视频", "audio": "音频", "unknown": "素材"}


def render_markdown(m: dict) -> str:
    """Markdown 报告（`asset-credits.ts:195-247`，结构一致）"""
    s = m.get("summary") or {}
    lines: list[str] = []
    lines.append(f"# 素材授权清单 — {m.get('project') or ''}")
    lines.append("")
    lines.append(f"共 {s.get('total', 0)} 项素材：需署名 {s.get('needsAttribution', 0)} 项，"
                 f"需人工复核 {s.get('needsReview', 0)} 项。")
    lines.append("✅ 未发现商用限制素材（NC/ND/未知许可为 0）。" if s.get("commercialSafe")
                 else "⚠️ 存在需人工复核的素材，投流前请确认或替换（见下方标注）。")
    lines.append("")

    rows = list(m.get("items") or []) + ([m["bgm"]] if m.get("bgm") else [])
    attributions = [r for r in rows if r.get("attributionLine")]
    if attributions:
        lines.append("## 需附署名（可直接复制到发布文案/简介）")
        for a in attributions:
            lines.append(f"- {a['attributionLine']}")
        lines.append("")

    reviews = [r for r in rows if r.get("risk") == RISK_REVIEW]
    if reviews:
        lines.append("## 需人工复核")
        for r in reviews:
            lines.append(f"- {_where(r)}: {r.get('license') or '许可未知'}"
                         + (f" · {r['sourceUrl']}" if r.get("sourceUrl") else ""))
        lines.append("")

    lines.append("## 全部素材")
    for r in rows:
        bits = [_where(r), KIND_LABEL.get(r.get("kind"), r.get("kind") or "素材")]
        for key in ("provider", "author", "license", "sourceUrl"):
            if r.get(key):
                bits.append(str(r[key]))
        note = (r.get("note") or {}).get("zh") or ""
        lines.append(f"- {' · '.join(bits)} — {note}")
    lines.append("")
    return "\n".join(lines)
