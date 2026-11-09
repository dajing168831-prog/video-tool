"""G3 趋势话题 —— 「今天该发什么」（零 Key）。

出处：clipforge `src/lib/trends.ts:1-323` + `src/app/api/trends/route.ts`：
  · `:69-84` Google Trends 每日 RSS 解析（只处理 `<item>`，跳过频道头；CDATA + 实体）
  · `:105-131` 抖音热搜 JSON（`data.word_list[]`，`word` + `hot_value`）
  · `:134-152` 头条热榜 JSON（`data[]`，`Title` + `HotValue`）
  · `:158-179` 国内优先：抖音拿不到 ≥5 条才退头条
  · `:186-217` 标题关键词分类（10 类，先具体后泛化；未命中只在「全部」里显示）
  · `:230-255` 每日一条：按 persona 关键词命中数打分，全不中回榜首并标 `matched=false`
  · `:260-292` 10 分钟 TTL 缓存，**空结果不缓存**（临时失败要能马上重试）

我们的差异：
  1. 只用标准库/httpx 重写（工程里没有 Node 运行时），解析函数保持纯函数、可单测。
  2. `persona` 由界面传：默认取当前项目的受众（`product.audience`）——竞品让用户手填。
  3. 分类结果随每条话题一起返回（竞品在前端分类），前端只做筛不重复实现规则。
  4. 抓取失败一律返回空列表 + `error` 字段（不抛 500）：这是「锦上添花」的入口，
     挂了不该把整页拖红。
"""
from __future__ import annotations

import re
import threading
import time

import httpx

CACHE_TTL_MS = 10 * 60 * 1000
TIMEOUT = 12.0

DOUYIN_URL = ("https://www.douyin.com/aweme/v1/web/hot/search/list/"
              "?device_platform=webapp&aid=6383")
TOUTIAO_URL = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
GOOGLE_RSS = "https://trends.google.com/trending/rss?geo={geo}"

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

TREND_CATEGORY_IDS = ("ent", "food", "tech", "game", "sports",
                      "fashion", "car", "pets", "life", "society")

#: 匹配顺序 ≠ 展示顺序：先具体垂类，泛化的「社会」最后兜底（`trends.ts:199-215`）
_RULES = [
    ("game", r"游戏|手游|端游|电竞|KPL|LPL|S赛|赛季|皮肤|联动|公测|内测|开服|停服|原神|王者荣耀|和平精英|崩坏|CODM|steam|主机|switch|PS5"),
    ("sports", r"比赛|夺冠|冠军|决赛|半决赛|球队|球员|足球|篮球|男篮|女篮|男足|女足|排球|女排|乒乓|羽毛球|网球|游泳|田径|马拉松|奥运|世界杯|亚运|斯诺克|CBA|NBA|健身|瑜伽|骑行"),
    ("car", r"汽车|新车|电车|新能源车|电动车|续航|充电桩|召回|试驾|车展|特斯拉|比亚迪|蔚来|理想汽车|小鹏|问界|驾照|违章|油价"),
    ("tech", r"手机|芯片|人工智能|大模型|AI|发布会|iPhone|苹果|华为|小米|三星|荣耀|OPPO|vivo|机器人|无人机|卫星|火箭|航天|算力|操作系统|App|互联网|程序员|数码"),
    ("food", r"奶茶|咖啡|美食|好吃|吃播|探店|餐厅|火锅|烧烤|小吃|零食|月饼|粽子|螺蛳粉|预制菜|外卖|食品|饮料|白酒|啤酒|茶饮"),
    ("fashion", r"穿搭|时尚|时装|秀场|美妆|口红|粉底|护肤|化妆|发型|美甲|香水|包包|球鞋|潮牌"),
    ("pets", r"小猫|小狗|猫咪|狗狗|宠物|大熊猫|熊猫|动物园|萌宠"),
    ("ent", r"电影|影片|电视剧|综艺|演唱会|音乐节|巡演|官宣|恋情|塌房|番位|主演|票房|首映|开播|收官|大结局|预告|定档|杀青|颁奖|红毯|出道|复出|专辑|新歌|MV|演员|导演|明星|爱豆|粉丝|应援"),
    ("life", r"立秋|立春|立夏|立冬|节气|天气|台风|暴雨|降雨|降温|高温|寒潮|旅游|景区|门票|放假|假期|调休|春运|高铁|机票|地铁"),
    ("society", r"警方|通报|调查|事故|遇难|坠|案|判|法院|检方|涉嫌|被拘|被抓|回应|致歉|道歉|辟谣|谣言|作弊|违规|处罚|罚款|地震|洪水|山洪|泥石流|爆炸|火灾|失联|救援|寻人|欠薪|维权|进出口|贸易"),
]
_RULES_COMPILED = [(cid, re.compile(rx, re.I)) for cid, rx in _RULES]

_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


# --------------------------------------------------------------------------- 纯函数
def format_hot_value(n) -> str:
    """11504605 → 1150万；170276700 → 1.7亿（`trends.ts:105-113`）。"""
    try:
        v = float(n)
    except (TypeError, ValueError):
        return ""
    if v != v or v <= 0:
        return ""
    if v >= 1e8:
        yi = v / 1e8
        return f"{round(yi) if yi >= 10 else round(yi * 10) / 10}亿"
    if v >= 1e4:
        return f"{round(v / 1e4)}万"
    return str(round(v))


def _to_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    elif isinstance(v, str):
        try:
            n = float(v)
        except ValueError:
            return None
    else:
        return None
    return n if n == n and n > 0 else None


def _strip_cdata(s: str) -> str:
    m = re.search(r"<!\[CDATA\[([\s\S]*?)\]\]>", s)
    return m.group(1) if m else s


def _decode_xml(s: str) -> str:
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&#39;", "'"), ("&apos;", "'"), ("&quot;", '"')):
        s = s.replace(a, b)
    return s


def _first_tag(xml: str, tag: str):
    # 标签可能带命名空间前缀（如 ht:approx_traffic），正则里要转义
    m = re.search(rf"<{re.escape(tag)}[^>]*>([\s\S]*?)</{re.escape(tag)}>", xml, re.I)
    return _decode_xml(_strip_cdata(m.group(1))).strip() if m else None


def parse_trends_rss(xml: str) -> list[dict]:
    """Google Trends RSS → 话题（`trends.ts:69-84`）。"""
    out: list[dict] = []
    for block in re.split(r"<item>", xml or "", flags=re.I)[1:]:
        body = re.split(r"</item>", block, flags=re.I)[0]
        title = _first_tag(body, "title")
        if not title:
            continue
        out.append({"title": title,
                    "traffic": _first_tag(body, "ht:approx_traffic") or "",
                    "context": _first_tag(body, "ht:news_item_title") or "",
                    "source": "google"})
    return out


def parse_douyin_hot_search(data) -> list[dict]:
    """抖音热搜（`trends.ts:118-131`）。"""
    lst = ((data or {}).get("data") or {}).get("word_list") if isinstance(data, dict) else None
    out: list[dict] = []
    for raw in (lst if isinstance(lst, list) else []):
        if not isinstance(raw, dict):
            continue
        word = raw.get("word")
        if not isinstance(word, str) or not word.strip():
            continue
        hot = _to_number(raw.get("hot_value"))
        out.append({"title": word.strip(), "hot_value": hot,
                    "traffic": format_hot_value(hot) if hot else "",
                    "rank": len(out) + 1, "source": "douyin"})
    return out


def parse_toutiao_hot_board(data) -> list[dict]:
    """头条热榜（`trends.ts:134-152`）。"""
    lst = data.get("data") if isinstance(data, dict) else None
    out: list[dict] = []
    for raw in (lst if isinstance(lst, list) else []):
        if not isinstance(raw, dict):
            continue
        title = raw.get("Title")
        if not isinstance(title, str) or not title.strip():
            continue
        hot = _to_number(raw.get("HotValue"))
        out.append({"title": title.strip(), "hot_value": hot,
                    "traffic": format_hot_value(hot) if hot else "",
                    "rank": len(out) + 1, "source": "toutiao"})
    return out


def classify_title(title: str) -> str | None:
    """标题 → 分类 id；未命中返回 None（只在「全部」里出现）。"""
    s = title or ""
    for cid, rx in _RULES_COMPILED:
        if rx.search(s):
            return cid
    return None


def pick_daily(topics: list[dict], persona: str) -> dict | None:
    """按 persona 关键词命中数挑一条，全不中回榜首并标 `matched=false`（`trends.ts:230-255`）。"""
    if not topics:
        return None
    kws = [k.strip().lower() for k in re.split(r"[\s,，、;；]+", persona or "") if k.strip()]
    best, best_score = None, 0
    for t in topics:
        title = str(t.get("title") or "").lower()
        score = sum(1 for k in kws if k in title)
        if score > best_score or (
                score == best_score and score > 0 and best
                and int(t.get("rank") or 999) < int(best.get("rank") or 999)):
            best, best_score = t, score
    if best and best_score > 0:
        return {"topic": best, "matched": True, "score": best_score}
    top = sorted(topics, key=lambda t: int(t.get("rank") or 999))[0]
    return {"topic": top, "matched": False, "score": 0}


def normalize_geo(geo) -> str:
    g = str(geo or "").strip()
    return g.upper() if re.fullmatch(r"[a-z]{2}", g, re.I) else "US"


def normalize_limit(limit) -> int:
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return 20
    return min(n, 50) if n > 0 else 20


# --------------------------------------------------------------------------- 缓存与抓取
def _is_empty(value) -> bool:
    if isinstance(value, list):
        return not value
    if isinstance(value, dict):
        topics = value.get("topics")
        return isinstance(topics, list) and not topics
    return False


def cached(key: str, fetcher, *, ttl_ms: int = CACHE_TTL_MS, now=None):
    """10 分钟 TTL；**空结果不入缓存**（`trends.ts:260-292`）。"""
    clock = now or (lambda: int(time.time() * 1000))
    with _lock:
        hit = _cache.get(key)
        if hit and clock() - hit[0] < ttl_ms:
            return hit[1]
    value = fetcher()
    if not _is_empty(value):
        with _lock:
            _cache[key] = (clock(), value)
    return value


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _fetch_json(url: str, headers: dict) -> object | None:
    try:
        r = httpx.get(url, headers={"User-Agent": BROWSER_UA, **headers},
                      timeout=TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return None
        return r.json()
    except (httpx.HTTPError, ValueError):
        return None


def fetch_domestic() -> dict:
    """国内优先：抖音 ≥5 条就用抖音，否则退头条；两者都空返回空列表。"""
    douyin = parse_douyin_hot_search(_fetch_json(
        DOUYIN_URL, {"Referer": "https://www.douyin.com/"}))
    if len(douyin) >= 5:
        return {"source": "douyin", "topics": douyin}
    toutiao = parse_toutiao_hot_board(_fetch_json(TOUTIAO_URL, {}))
    if toutiao:
        return {"source": "toutiao", "topics": toutiao}
    return {"source": "douyin", "topics": douyin}


def fetch_google(geo: str = "US") -> list[dict]:
    g = normalize_geo(geo)
    try:
        r = httpx.get(GOOGLE_RSS.format(geo=g), headers={"User-Agent": BROWSER_UA},
                      timeout=TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return []
        return parse_trends_rss(r.text)
    except httpx.HTTPError:
        return []


def topics_with_category(topics: list[dict]) -> list[dict]:
    out = []
    for t in topics:
        row = dict(t)
        row["category"] = classify_title(str(row.get("title") or ""))
        out.append(row)
    return out


def build_trends(*, source: str = "", geo: str = "", limit=20,
                 persona: str = "") -> dict:
    """接口主入口：国内 / Google 两路，返回分类后的话题与「今日一条」。"""
    n = normalize_limit(limit)
    src = (source or "").strip().lower()
    if src == "cn" or (not src and not geo):
        got = cached("cn", fetch_domestic)
        topics = list(got.get("topics") or [])
        out_source = got.get("source") or "douyin"
        used_geo = ""
    else:
        used_geo = normalize_geo(geo)
        topics = cached(f"geo:{used_geo}", lambda: fetch_google(used_geo))
        out_source = "google"
    topics = topics_with_category(topics)[:n]
    pick = pick_daily(topics, persona) if topics else None
    return {"source": out_source, "geo": used_geo, "count": len(topics),
            "topics": topics, "categories": list(TREND_CATEGORY_IDS),
            "pick": pick,
            "error": "" if topics else "上游暂时没返回话题（过一会儿再试）"}
