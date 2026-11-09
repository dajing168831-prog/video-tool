"""A2 商品链接解析（JSON-LD → OpenGraph → Twitter Card → <title>）。

出处 `src/lib/product-ingest.ts:1-186`（逐条照抄）：
  · `:28-37` `decodeEntities`：**单遍扫描**，每个实体只解一次 ——
    链式 replace 会把上一步产出的 `&` 当成下一个实体的开头（`&amp;#39;` 该保持字面量）
  · `:44-54` `getMeta`：同时支持 `property=` 在前 / `content=` 在前两种写法；
    content 用**引号回引用** `(["'])((?:(?!\1).)*)\1`，否则 `content="Tom's Mug"` 会在撇号处截断
  · `:60-66` `toAbsolute`：相对地址按 base 补全，失败原样返回
  · `:70-100` JSON-LD：递归找 `@type=Product`（含数组与 `@graph`），坏 JSON 跳过不炸
  · `:106-126` 价格格式化：0 / 负数 / 非数字作废；已带货币符号或 `USD ` 前缀的不重复加；未知币种退成 `XXX `
  · `:128-137` JSON-LD 图片：字符串或 `{url}` 都认
  · `:142-186` 主解析：标题 `JSON-LD.name → og:title → twitter:title → <title>`；
    价格 `JSON-LD.offers → product:price:amount`；描述 `JSON-LD → og/twitter/description`；
    图片三路合并 → 绝对化 → 只留 http(s) → 去重

我们的差异：
  1. 能力表原写「微数据 → LLM 兜底」，但竞品源码里**没有**这两段（`product-ingest.ts` 到 `<title>` 就结束）。
     本实现照源码，**不编**微数据与 LLM 兜底；抓不到就返回空字段让用户手填（C10 不许编产品事实）。
  2. 抓取仍走原来的 SSRF 校验（只收公网 http/https）。
"""
from __future__ import annotations

import ipaddress
import json
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

#: 货币代码 → 符号（`product-ingest.ts:18-20`）
CURRENCY_SYMBOL = {
    "USD": "$", "CNY": "¥", "RMB": "¥", "EUR": "€", "GBP": "£", "JPY": "¥",
    "HKD": "HK$", "TWD": "NT$", "KRW": "₩", "AUD": "A$", "CAD": "C$",
}
NAMED_ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}
_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);")


class IngestError(ValueError):
    """抓取/解析失败（人话）。"""


def decode_entities(s: str) -> str:
    """单遍实体解码（`product-ingest.ts:28-37`）——链式替换会二次解码，这里不会。"""
    def one(m: re.Match) -> str:
        e = m.group(1)
        if e[0] == "#":
            try:
                code = int(e[2:], 16) if e[1] in "xX" else int(e[1:])
            except ValueError:
                return m.group(0)
            try:
                return chr(code)
            except (ValueError, OverflowError):
                return m.group(0)
        return NAMED_ENTITIES.get(e, m.group(0))

    return re.sub(r"\s+", " ", _ENTITY_RE.sub(one, s or "")).strip()


def _escape_re(s: str) -> str:
    return re.sub(r"([.*+?^${}()|\[\]\\])", r"\\\1", s)


def get_meta(html: str, keys: list[str]) -> str | None:
    """按顺序找第一个非空 meta（两种属性顺序都认，`product-ingest.ts:44-54`）。"""
    for key in keys:
        k = _escape_re(key)
        m = (re.search(
            rf"<meta[^>]+(?:property|name)=[\"']{k}[\"'][^>]*content=([\"'])((?:(?!\1).)*)\1",
            html, re.I)
            or re.search(
                rf"<meta[^>]+content=([\"'])((?:(?!\1).)*)\1[^>]*(?:property|name)=[\"']{k}[\"']",
                html, re.I))
        if m and m.group(2).strip():
            return decode_entities(m.group(2))
    return None


def to_absolute(url: str, base: str) -> str:
    """相对地址补全；像 `::::` 这种会被 JS 的 `new URL()` 判非法的，原样返回（`product-ingest.ts:60-66`）。"""
    if not url:
        return url
    first = url.split("/", 1)[0]
    if ":" in first and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url):
        return url
    try:
        return urljoin(base, url)
    except (TypeError, ValueError):
        return url


def find_product_node(data) -> dict | None:
    """递归找 schema.org Product（`product-ingest.ts:70-85`）。"""
    if isinstance(data, list):
        for d in data:
            found = find_product_node(d)
            if found:
                return found
        return None
    if not isinstance(data, dict):
        return None
    typ = data.get("@type")
    if typ == "Product" or (isinstance(typ, list) and "Product" in typ):
        return data
    graph = data.get("@graph")
    if graph:
        return find_product_node(graph)
    return None


def extract_json_ld_product(html: str) -> dict | None:
    """在所有 `application/ld+json` 块里找 Product；坏 JSON 跳过（`product-ingest.ts:88-100`）。"""
    import json

    for m in re.finditer(
            r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>([\s\S]*?)</script>",
            html or "", re.I):
        try:
            node = find_product_node(json.loads((m.group(1) or "").strip()))
        except (TypeError, ValueError):
            continue
        if node:
            return node
    return None


def format_price(price, currency: str | None) -> str | None:
    """价格格式化（`product-ingest.ts:106-126`）：0/负/非数字作废，已有的货币前缀不重复加。"""
    if price is None:
        return None
    raw = str(price).strip()
    if not raw:
        return None
    try:
        as_num = float(raw)
        if as_num <= 0:
            return None
    except ValueError:
        pass
    digits = re.sub(r"[^\d.]", "", raw)
    try:
        numeric = float(digits)
    except ValueError:
        return None
    if numeric <= 0:
        return None
    if re.search(r"[¥$€£₩]", raw) or re.match(r"^[A-Za-z]{2,3}[\s ]", raw):
        return raw
    cur = (currency or "").upper()
    sym = CURRENCY_SYMBOL.get(cur, f"{cur} " if cur else "")
    return f"{sym}{raw}"


def json_ld_price(node: dict) -> str | None:
    offers = node.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        return None
    price = offers.get("price")
    if price is None:
        price = offers.get("lowPrice")
    if price is None:
        price = offers.get("highPrice")
    return format_price(price, offers.get("priceCurrency") or node.get("priceCurrency"))


def json_ld_images(node: dict) -> list[str]:
    img = node.get("image")
    if not img:
        return []
    arr = img if isinstance(img, list) else [img]
    out: list[str] = []
    for x in arr:
        u = x if isinstance(x, str) else (x or {}).get("url")
        if isinstance(u, str) and u:
            out.append(u)
    return out


def parse_product_from_html(html: str, base_url: str) -> dict:
    """主解析（`product-ingest.ts:142-186`）。`source` 只用于说明这批字段是从哪一层拿到的。"""
    ld = extract_json_ld_product(html) or {}
    title_tag = re.search(r"<title[^>]*>([\s\S]*?)</title>", html or "", re.I)
    title = (decode_entities(str(ld.get("name"))) if ld.get("name") else None) \
        or get_meta(html, ["og:title", "twitter:title"]) \
        or (decode_entities(title_tag.group(1)) if title_tag else "") or ""

    og_price = get_meta(html, ["product:price:amount", "og:price:amount"])
    og_cur = get_meta(html, ["product:price:currency", "og:price:currency"])
    price_text = json_ld_price(ld) if ld else None
    if not price_text:
        price_text = format_price(og_price, og_cur)

    description = (decode_entities(str(ld.get("description"))) if ld.get("description") else None) \
        or get_meta(html, ["og:description", "twitter:description", "description"]) or ""

    raw: list[str] = list(json_ld_images(ld))
    og_img = get_meta(html, ["og:image", "og:image:secure_url"])
    if og_img:
        raw.append(og_img)
    tw_img = get_meta(html, ["twitter:image", "twitter:image:src"])
    if tw_img:
        raw.append(tw_img)
    seen: set[str] = set()
    images: list[str] = []
    for u in raw:
        if not u:
            continue
        abs_url = to_absolute(decode_entities(u), base_url)
        if not re.match(r"^https?://", abs_url, re.I):
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        images.append(abs_url)

    if ld.get("name") or json_ld_price(ld) or json_ld_images(ld):
        source = "json-ld"
    elif og_img or og_price or get_meta(html, ["og:title", "og:description"]):
        source = "open-graph"
    elif tw_img or get_meta(html, ["twitter:title", "twitter:description"]):
        source = "twitter-card"
    else:
        source = "title"

    return {"title": title.strip(), "price_text": price_text,
            "description": description.strip(), "images": images,
            "source_url": base_url, "source": source}


def extract_url(text: str) -> str | None:
    """从顾客粘进来的整段文本里抠出第一个链接。

    2026-11-08：淘宝/抖音/拼多多的「分享」复制出来都是一整串
    （`【淘宝】https://item.taobao.com/... 点击链接直接打开`），
    原来的 `check_public_url` 直接给整串前补 `https://` → 域名变成
    「【淘宝】https」→ 报 `Invalid IDNA hostname`。原样复现过。
    抠不到就返回 None，由调用方说人话。
    """
    s = (text or "").strip()
    if not s:
        return None
    m = re.search(r"https?://[^\s<>\"'，。；、）】」》]+", s, re.I)
    if m:
        return m.group(0)
    # 没有协议头：认第一个像域名的片段（`pixabay.com/api/docs/`）
    m = re.search(r"(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>\"'，。；、）】」》]*)?", s, re.I)
    return m.group(0) if m else None


#: 风控页/空壳页的通用标题 —— 它们不是商品名，不能拿去当商品名（2026-11-08 实测）
_PLACEHOLDER_TITLES = (
    "京东验证", "安全验证", "验证码", "滑动验证", "页面加载中",
    "商品详情页", "淘宝网", "天猫", "拼多多商城", "抖音电商", "登录",
)


def is_placeholder_title(title: str) -> bool:
    """风控页标题 → 当成「没抓到」，让分享文案里的商品名顶上。"""
    t = (title or "").strip()
    return (not t) or any(t == x or t.startswith(x) for x in _PLACEHOLDER_TITLES)


def from_share_redirect(url: str) -> dict:
    """抖音分享短链跳转后的最终地址里带着商品 JSON（`goods_detail=`）—— 白捡的标题/价格/主图。

    2026-11-08 实测（主人给的真实链接）：
    `https://haohuo.jinritemai.com/...?goods_detail=%7B%22title%22...%7D`
    解出来是 `{"title": "指甲刀指甲剪全套…", "sales": 1682,
    "img": {"url_list": ["https://p26-item.ecombdimg.com/...png"]},
    "min_price": 900, "max_price": 1200}` —— 价格单位是**分**。
    这不是绕过风控：跳转地址是平台自己给的，只是把里面的字段读出来。
    """
    try:
        q = parse_qs(urlparse(url or "").query)
    except Exception:  # noqa: BLE001
        return {}
    raw = (q.get("goods_detail") or [""])[0]
    if not raw:
        return {}
    try:
        d = json.loads(unquote(raw))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(d, dict):
        return {}
    title = str(d.get("title") or "").strip()
    img = ""
    urls = ((d.get("img") or {}).get("url_list") or [])
    if urls:
        img = str(urls[0])
    lo, hi = d.get("min_price"), d.get("max_price")
    price_text = ""
    try:
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo > 0:
            a, b = lo / 100, hi / 100
            price_text = f"¥{a:g}" if a == b else f"¥{a:g}-¥{b:g}"
    except Exception:  # noqa: BLE001
        price_text = ""
    return {"title": title, "price_text": price_text, "image": img,
            "sales": d.get("sales")}


def extract_share_title(text: str) -> str:
    """从「App 分享文案」里抠商品名（2026-11-08）。

    淘宝/抖音/拼多多的分享文本长这样（顾客就是粘这一整串）：
      淘宝：`【淘宝】https://m.tb.cn/h.gXXX?tk=abc CZ0001 「轻奢真皮手提包女」`
      抖音：`8.66 复制打开抖音，看看【某某店铺】这个包真的能装…`
      拼多多：`【拼多多】https://p.pinduoduo.com/xxx 「加厚收纳箱」`
    这些平台对无登录的程序一律返回风控页（实测：淘宝 mtop 都被 `_____tmd_____` 拦），
    但**标题就在顾客粘的这串字里**，不需要联网也能拿到。
    只认这两个形状，拿不到就返回空串 —— 不猜、不编（C10）。
    """
    s = (text or "").strip()
    if not s:
        return ""
    # 抖音商城（2026-11-08 主人给的**真实**分享文案，格式和别家不一样）：
    #   `5.30 07/18 can:/ t@E.UY 【抖音商城】https://v.douyin.com/2eUuCFUFWhg/ 指甲刀指甲剪全套…
    #    长按复制此条消息，打开抖音搜索，查看商品详情！`
    # 商品名在**链接后面**、到行尾为止，不在任何括号里。
    if "抖音" in s:
        m = re.search(r"https?://[^\s]+?\s+([^\n【】]{4,90})", s)
        if m:
            title = m.group(1).strip(" 　,，.。;；:：!！?？")
            if title:
                return title
    # 小红书：`39 【纯棉四件套 - 小红书】 😆 http://xhslink.com/...`
    m = re.search(r"【([^】\n]{2,80}?)\s*-\s*小红书】", s)
    if m:
        return m.group(1).strip()
    m = re.search(r"[「『]([^」』\n]{2,80})[」』]", s)
    if m:
        return m.group(1).strip()
    # 🩸 不认 `看看【X】` —— 抖音那格的方括号里是**账号名**（实测「小皮具店的作品」），
    # 当成商品名会把商品叫错。宁可返回空，让顾客手填（C10 不许编）。
    return ""


def check_public_url(u: str) -> str:
    """只收公网 http/https；补协议，挡私网/环回（原有 SSRF 口径）。"""
    raw = (u or "").strip()
    if not raw:
        raise IngestError("先粘一个链接")
    scheme = re.match(r"^([a-z][a-z0-9+.-]*)://", raw, re.I)
    if scheme and scheme.group(1).lower() not in ("http", "https"):
        raise IngestError("只收 http/https 链接")
    found = extract_url(raw)
    if not found:
        raise IngestError("这串里没找到链接，粘商品页的网址就行")
    u = found
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    host = urlparse(u).hostname or ""
    if not host:
        raise IngestError("链接里没有域名")
    # 中文域名要转 punycode，否则 httpx 报 `Invalid IDNA hostname`
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise IngestError(f"链接里的域名「{host}」格式不对")
    if ascii_host != host:
        u = u.replace(host, ascii_host, 1)
    # 🩸 不能把 `raise IngestError` 放在 `except ValueError` 覆盖的范围里 ——
    # IngestError 继承 ValueError，会被自己捕获后静默放行（实测 192.168/127.0 穿透）
    try:
        ip = ipaddress.ip_address(ascii_host)
    except ValueError:
        ip = None
        if ascii_host in ("localhost",) or ascii_host.endswith(".local"):
            raise IngestError("只收公网链接")
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_reserved):
        raise IngestError("只收公网链接")
    return u


def fetch_html(u: str, timeout: float = 15.0) -> tuple[str, str]:
    """抓页面 HTML，返回 `(最终 URL, 截断到 2MB 的 HTML)`。"""
    import httpx

    with httpx.Client(timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"}) as c:
        r = c.get(u)
        r.raise_for_status()
        return str(r.url), r.text[:2_000_000]


def fetch_product(u: str, timeout: float = 15.0) -> dict:
    """抓 + 解析（HTML 里 `<base href>` 优先作为相对地址基准）。"""
    final_url, html = fetch_html(check_public_url(u), timeout=timeout)
    base = final_url
    base_tag = re.search(r"<base[^>]+href=[\"']([^\"']+)[\"']", html or "", re.I)
    if base_tag:
        base = to_absolute(decode_entities(base_tag.group(1)), final_url)
    out = parse_product_from_html(html, base)
    out["url"] = final_url
    return out
