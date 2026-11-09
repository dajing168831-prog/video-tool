"""C4 平台 Key 连通性校验 —— 服务端只读探针（12 秒超时，上游原文不外泄）。

出处：
  · 生图/生视频平台：clipforge `api/ai/test-provider/route.ts:1-113`
      - 401/403 → invalid（Key 无效）；
      - 2xx → ok；
      - 其它（404/400/5xx/网络）→ unknown（无法判定，可直接试生成）；
      - **volcengine 特殊**：`GET /models` 只证明「连得上」，不证明有出图/出片权限
        → 除 401/403 外一律 unknown，并写明去控制台查项目权限。
      - fal 用 `authFirst`：只要不是 401/403 就算鉴权通过。
  · LLM 端点：clipforge `lib/llm-probe.ts:1-140` + `api/llm/test/route.ts`
      - 探针**真发一次最小补全**（`/models` 不能证明模型名存在，会给「连接正常」假绿）；
      - `max_tokens: 64` 起步；有些后端把「触顶」当 400/422 → **去掉上限重试一次**；
      - 重试后仍因「输出上限小」被拒 → 说明鉴权/端点/模型名都通 → **判 ok 并带 warning**；
      - 401/403 → invalid；超时/网络 → unknown。
  · 时长：平台探针 10s、LLM 探针 15s（竞品值）；本入口统一收敛到 `PROBE_TIMEOUT = 12s`
    （能力表这一行写的就是 12s）。

我们的差异（不抄错）：
  · Key **只从服务端配置读**，接口既不收 Key、也不回 Key —— 浏览器里从头到尾看不到整串。
  · 没有只读鉴权端点的通道（豆包语音 / AI MediaKit）**不做假探针**，直接标「不支持探测」并写原因。
  · 上游错误原文**只进日志**，返回给界面的是人话 + HTTP 状态码（能力表要求「上游错误不外泄」）。
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

#: 统一超时（能力表 C4：12s）
PROBE_TIMEOUT = 12.0
#: LLM 探针的最小补全预算（竞品 `llm-probe.ts:19`）
PROBE_MAX_TOKENS = 64

#: 平台登记：kind = platform（只读鉴权端点）/ llm（最小补全）/ unsupported（不做假探针）
PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek（写结构卡/剧本/分镜）",
        "kind": "llm",
        "note": "会发一次最小补全（约几十 token，费用可忽略）—— 只查 /models 证明不了模型名。",
    },
    "ark": {
        "label": "火山方舟（出图/出片）",
        "kind": "platform",
        "base": "https://ark.cn-beijing.volces.com/api/v3",
        "note": "只查 Key 是否被方舟接受；出图/出片权限要到方舟控制台看项目授权。",
    },
    "volc_tts": {
        "label": "豆包语音（转写）",
        "kind": "unsupported",
        "reason": "语音接口没有只读鉴权端点，只能在真转写一次时验证（不做假探针）。",
    },
    "mediakit": {
        "label": "AI MediaKit（人声分离）",
        "kind": "unsupported",
        "reason": "签名请求 + 异步任务，没有只读鉴权端点；只能在真跑一次时验证。",
    },
}

#: 触发「输出上限」类拒绝的片段（竞品 `isTokenCapRejection`）
_CAP_HINTS = ("max_tokens", "max_completion_tokens", "output limit", "token limit",
              "could not finish the message", "maximum context")


def is_token_cap_rejection(text: str) -> bool:
    """这段错误是不是「输出预算太小」而不是鉴权/模型问题（纯函数）。"""
    s = (text or "").lower()
    return any(h in s for h in _CAP_HINTS)


def normalize_chat_base(base: str) -> str:
    """OpenAI 兼容 base：去掉末尾 /，并把误填的 `/chat/completions` 剥掉。"""
    s = (base or "").strip().rstrip("/")
    for tail in ("/chat/completions", "/completions"):
        if s.endswith(tail):
            s = s[: -len(tail)]
    return s.rstrip("/")


def classify_platform(name: str, status: int) -> tuple[str, str]:
    """生图/生视频平台的判定（竞品 `test-provider/route.ts:78-100`，逐条）。"""
    if name == "ark":
        if status in (401, 403):
            return "invalid", ("方舟拒绝了这个 Key（或无权限）。请用 ARK 的出图/出片 Key，"
                               "并到控制台确认项目授权；Agent Plan 的凭证是另一套。")
        if 200 <= status < 300:
            return "unknown", ("方舟连得上；但这个模型列表探针**证明不了**出图/出片权限，"
                               "请在方舟控制台确认模型与项目授权。")
        return "unknown", (f"无法判定是否有出图/出片权限（HTTP {status}）。"
                           "检查 Key、项目授权与 Base URL：https://ark.cn-beijing.volces.com/api/v3")
    if status in (401, 403):
        return "invalid", "Key 无效或无权限"
    if 200 <= status < 300:
        return "ok", "连接正常"
    return "unknown", f"无法判定（HTTP {status}），可直接试生成"


def classify_llm(status: int) -> tuple[str, str]:
    """LLM 端点失败时的判定（成功与「触顶重试」在 probe_llm 里处理）。"""
    if status in (401, 403):
        return "invalid", "Key 无效或无权限"
    if status == 404:
        return "unknown", "端点或模型名对不上（HTTP 404）—— 检查设置里的模型名"
    if 400 <= status < 500:
        return "unknown", f"请求被拒（HTTP {status}）—— 可能是模型名或参数问题"
    return "unknown", f"无法判定（HTTP {status}）"


def _default_fetch(method: str, url: str, *, headers: dict | None = None,
                   body: dict | None = None, timeout: float = PROBE_TIMEOUT):
    """真实 HTTP（探测用；测试里整个替换掉）。返回 (status, text)。"""
    import httpx

    with httpx.Client(timeout=timeout, follow_redirects=False) as c:
        r = c.request(method, url, headers=headers or {}, json=body)
        return r.status_code, (r.text or "")


def probe_llm(base: str, api_key: str, model: str, *,
              fetch=None, timeout: float = PROBE_TIMEOUT) -> dict:
    """真发一次最小补全；触顶 4xx → 去上限重试一次；仍触顶 → ok + warning。"""
    fetch = fetch or _default_fetch
    url = f"{normalize_chat_base(base)}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    t0 = time.time()

    def call(max_tokens: int | None):
        body = {"model": model, "messages": [{"role": "user", "content": "hi"}]}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        return fetch("POST", url, headers=headers, body=body, timeout=timeout)

    try:
        status, text = call(PROBE_MAX_TOKENS)
        if 200 <= status < 300:
            return {"status": "ok", "message": "连接正常", "http": status,
                    "ms": int((time.time() - t0) * 1000)}
        if status in (400, 422) and is_token_cap_rejection(text):
            status, text = call(None)
            if 200 <= status < 300:
                return {"status": "ok", "message": "连接正常（该端点对 max_tokens 敏感，已去上限重试）",
                        "http": status, "ms": int((time.time() - t0) * 1000)}
            if status in (400, 422) and is_token_cap_rejection(text):
                # 连一句都写不完，但鉴权/端点/模型名全通了 —— 判 ok 并警告
                return {"status": "ok", "http": status,
                        "message": "连接正常，但该模型的输出上限很小（连一句话都写不完）："
                                   "剧本生成可能中途被截断，建议减少分镜数量/时长或换输出更充裕的模型",
                        "warning": True, "ms": int((time.time() - t0) * 1000)}
        st, msg = classify_llm(status)
        if text:
            log.info("[probe] llm %s HTTP %s：%s", model or "-", status, text[:300])
        return {"status": st, "message": msg, "http": status,
                "ms": int((time.time() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001
        name = type(e).__name__
        aborted = "timeout" in name.lower() or "timed out" in str(e).lower()
        log.warning("[probe] llm 探测失败 %s: %s", name, str(e)[:200])
        return {"status": "unknown",
                "message": "超时，无法判定" if aborted else "网络异常，无法判定",
                "http": 0, "ms": int((time.time() - t0) * 1000)}


def probe_platform(name: str, api_key: str, *, base: str = "",
                   fetch=None, timeout: float = PROBE_TIMEOUT) -> dict:
    """生图/生视频平台：打一个只读鉴权端点。"""
    fetch = fetch or _default_fetch
    spec = PROVIDERS.get(name) or {}
    root = (base or spec.get("base") or "").strip().rstrip("/")
    if not root:
        return {"status": "unknown", "message": "没有可用的 Base URL", "http": 0, "ms": 0}
    url = f"{root}/models"
    t0 = time.time()
    try:
        status, text = fetch("GET", url,
                             headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
        st, msg = classify_platform(name, status)
        if text and st != "ok":
            log.info("[probe] %s HTTP %s：%s", name, status, text[:300])
        return {"status": st, "message": msg, "http": status,
                "ms": int((time.time() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001
        name_ = type(e).__name__
        aborted = "timeout" in name_.lower() or "timed out" in str(e).lower()
        log.warning("[probe] %s 探测失败 %s: %s", name, name_, str(e)[:200])
        return {"status": "unknown",
                "message": "超时，无法判定" if aborted else "网络异常，无法判定",
                "http": 0, "ms": int((time.time() - t0) * 1000)}


def provider_rows(settings) -> list[dict]:
    """给界面看的登记表（不含任何 Key）。"""
    keys = {
        "deepseek": getattr(settings, "deepseek_api_key", "") or "",
        "ark": getattr(settings, "ark_api_key", "") or "",
        "volc_tts": getattr(settings, "volc_api_key", "") or "",
        "mediakit": getattr(settings, "mediakit_api_key", "") or "",
    }
    out = []
    for name, spec in PROVIDERS.items():
        out.append({
            "name": name,
            "label": spec.get("label") or name,
            "kind": spec.get("kind"),
            "supported": spec.get("kind") != "unsupported",
            "configured": bool(str(keys.get(name) or "").strip()),
            "reason": spec.get("reason") or "",
            "note": spec.get("note") or "",
        })
    return out


def probe_one(name: str, settings, *, fetch=None, timeout: float = PROBE_TIMEOUT) -> dict:
    """按名称探一个通道；未注册/未支持/未配置都回人话，不抛。"""
    spec = PROVIDERS.get(name)
    if not spec:
        return {"name": name, "label": name, "status": "unknown",
                "message": "没有这个平台", "http": 0, "ms": 0}
    label = spec.get("label") or name
    if spec.get("kind") == "unsupported":
        return {"name": name, "label": label, "status": "unsupported",
                "message": spec.get("reason") or "该通道不支持只读探针", "http": 0, "ms": 0}
    key = ""
    if name == "deepseek":
        key = getattr(settings, "deepseek_api_key", "") or ""
    elif name == "ark":
        key = getattr(settings, "ark_api_key", "") or ""
    if not str(key).strip():
        return {"name": name, "label": label, "status": "missing",
                "message": "未配置 Key（走环境变量）", "http": 0, "ms": 0}

    if spec.get("kind") == "llm":
        base = getattr(settings, "deepseek_base", "") or "https://api.deepseek.com"
        model = getattr(settings, "deepseek_model", "") or "deepseek-flash"
        got = probe_llm(base, key, model, fetch=fetch, timeout=timeout)
    else:
        got = probe_platform(name, key, base=spec.get("base") or "",
                             fetch=fetch, timeout=timeout)
    return {"name": name, "label": label, **got}


def probe_all(names: list[str] | None, settings, *, fetch=None,
              timeout: float = PROBE_TIMEOUT) -> list[dict]:
    """不传名称 = 全部登记通道；传了就按传的顺序探（未知名称也回一行，不静默丢）。"""
    picked = list(names) if names else list(PROVIDERS)
    return [probe_one(n, settings, fetch=fetch, timeout=timeout) for n in picked]
