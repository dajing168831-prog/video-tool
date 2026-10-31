"""全局配置（环境变量驱动，开发期默认值可直接跑）。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/


def _load_dotenv(path: Path) -> None:
    """读 backend/.env（没有就跳过）。已存在的环境变量优先，不被文件覆盖。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv(ROOT / ".env")


def _user_env(key: str) -> str:
    """进程环境里没有时，回读 HKCU\\Environment（Windows）。

    为什么要这样：密钥只放用户环境变量、不落工程文件；而已经开着的 shell
    不会自动看到新设的变量，`setx` 之后不重启就拿不到 —— 直接读注册表绕开这个坑。
    """
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            v, _ = winreg.QueryValueEx(k, key)
            return str(v or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _env(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if v is None or not str(v).strip():
        v = _user_env(key)
    v = (str(v) if v is not None else "").strip()
    return v or default


@dataclass(frozen=True)
class Settings:
    # 数据库：开发期 SQLite，生产切 PostgreSQL（只改连接串）
    database_url: str = _env("VT_DATABASE_URL", f"sqlite+aiosqlite:///{ROOT / 'data' / 'vt.db'}")
    # 临时文件目录
    temp_dir: Path = Path(_env("VT_TEMP_DIR", str(ROOT / "data" / "temp")))
    # 临时文件保留时长（秒）
    temp_ttl: int = int(_env("VT_TEMP_TTL", "7200"))
    # ffmpeg 可执行文件（不填则从 PATH 找）
    ffmpeg: str = _env("VT_FFMPEG", "")
    # 解析器重试次数与间隔
    parse_retries: int = int(_env("VT_PARSE_RETRIES", "2"))
    parse_retry_delay: float = float(_env("VT_PARSE_RETRY_DELAY", "1.5"))
    # 单条视频最大字节数（防止超大文件拖垮磁盘）
    max_video_bytes: int = int(_env("VT_MAX_VIDEO_BYTES", str(500 * 1024 * 1024)))
    # 请求超时
    http_timeout: float = float(_env("VT_HTTP_TIMEOUT", "60"))
    # 出口代理（格式 http://user:pass@host:port 或 socks5://...）
    proxy: str = _env("VT_PROXY", "")
    # 仅 YouTube 使用的代理（留空则用 proxy；YouTube 已下线，保留备用）
    youtube_proxy: str = _env("VT_YOUTUBE_PROXY", "")
    # 对外开放的平台。默认国内 4 个 + TikTok + X（Twitter）。
    # 2026-10-23 加 TikTok（主人要求，内部测试）；2026-10-29 加 twitter/X。
    # 🩸 TikTok 走 tikwm 公开接口，不需要大带宽出口；**X 走 yt-dlp 直连 x.com，
    #   本机在国内没配代理时大概率解析不了** —— 要真能用得先配 `VT_PROXY`
    #   （上面 :70）。配置没铺开时接口不会崩，是解析阶段报错。
    enabled_platforms: list[str] = field(
        default_factory=lambda: [
            p.strip()
            for p in _env(
                "VT_ENABLED_PLATFORMS",
                "douyin,kuaishou,xiaohongshu,bilibili,tiktok,twitter",
            ).split(",")
            if p.strip()
        ]
    )

    # ---- 复刻功能（clone）----
    # 识别/合成走哪个供应商：mock/sapi 是占位，volc 是火山豆包语音（生产）
    asr_provider: str = _env("VT_ASR_PROVIDER", "mock")
    tts_provider: str = _env("VT_TTS_PROVIDER", "sapi")
    # 豆包语音（新版控制台用单一 X-Api-Key，不需要 APPID + Access Token）
    volc_api_key: str = _env("VT_VOLC_API_KEY", "")
    # 录音文件识别 2.0；1.0 是 volc.bigasr.auc（本账号未开通）
    volc_asr_resource: str = _env("VT_VOLC_ASR_RESOURCE", "volc.seedasr.auc")
    # 语音合成 2.0；1.0 是 volc.service_type.10029（本账号未开通）
    volc_tts_resource: str = _env("VT_VOLC_TTS_RESOURCE", "seed-tts-2.0")
    # 声音复刻音色（S_ 开头）必须用复刻资源合成。官方 SoundReplicaAPI-V3：
    # 「V3 大模型语音合成接口通过 X-Api-Resource-Id 选择版本效果：
    #   seed-icl-2.0 对应声音复刻 ICL 2.0 版本效果」
    volc_icl_resource: str = _env("VT_VOLC_ICL_RESOURCE", "seed-icl-2.0")
    volc_tts_speaker: str = _env("VT_VOLC_TTS_SPEAKER", "zh_female_xiaohe_uranus_bigtts")
    # 接口要求的 user.uid，随便给个稳定标识即可（官方建议 IMEI/MAC，我们不采）
    volc_uid: str = _env("VT_VOLC_UID", "video-tool")

    # ---- 火山 AI MediaKit（人声分离：换配音时保留原片 BGM / 音效）----
    # 只认 API Key（`Authorization: Bearer`），和方舟 / 豆包语音的 key 不是同一个。
    # 输入只收公网可访问 URL，所以调用前要先过 oss.upload。
    mediakit_api_key: str = _env("VT_MEDIAKIT_API_KEY") or _env("MEDIAKIT_API_KEY")
    mediakit_endpoint: str = _env(
        "VT_MEDIAKIT_ENDPOINT") or _env("MEDIAKIT_ENDPOINT", "https://mediakit.cn-beijing.volces.com")

    # ---- 方舟（换画面用：重绘镜头 + 生成视频）----
    ark_api_key: str = _env("VT_ARK_API_KEY", "")
    # 素材库走**管控面**（ark.cn-beijing.volcengineapi.com），只能用 AK/SK 做 V4 签名，
    # API Key 签不了。没有这两个就退回"直接传图"，火山会拦真人脸。
    # 变量名两套都认：VT_ 是本工程前缀，ARK_ 是主人环境里已有的命名。
    volc_access_key: str = _env("VT_VOLC_ACCESS_KEY") or _env("ARK_ACCESS_KEY")
    volc_secret_key: str = _env("VT_VOLC_SECRET_KEY") or _env("ARK_SECRET_KEY")
    ark_asset_project: str = _env("VT_ARK_ASSET_PROJECT") or _env("ARK_ASSET_PROJECT", "default") or "default"
    # 主控开关：ARK_ASSET_ENABLED=false 时整条素材库链路休眠（退回直传）
    ark_asset_enabled: bool = (_env("VT_ARK_ASSET_ENABLED") or _env("ARK_ASSET_ENABLED", "1")).lower() not in ("0", "false", "no")
    # 素材库额度：官方 50 素材 + 50 组，全账号共享
    ark_asset_max: int = int(_env("VT_ARK_ASSET_MAX", "50"))
    # 超过这个小时数没被用到的素材组，出片前顺手回收
    ark_asset_stale_h: float = float(_env("VT_ARK_ASSET_STALE_H", "24"))
    # 人脸检测模型（OpenCV YuNet）；缺文件时按"检测不出"处理（宁多入库，不漏）
    face_model: str = _env("VT_FACE_MODEL", str(ROOT / "models" / "face_yunet.onnx"))
    # 图生图：拿原片关键帧当参考，换主体不换构图
    ark_image_model: str = _env("VT_ARK_IMAGE_MODEL", "doubao-seedream-5-0-flash-260915")
    # 图生视频：把重绘出来的静帧变成能放进时间轴的片段
    # 1.0-pro-fast 是实测可用且最短支持 2 秒的档，比 2.0/2.5 便宜
    ark_video_model: str = _env("VT_ARK_VIDEO_MODEL", "doubao-seedance-1-0-pro-fast-251015")
    # 一条片子里最多重绘几个镜头（防止一次点下去生成几十个视频）
    clone_max_regen: int = int(_env("VT_CLONE_MAX_REGEN", "12"))
    # 无缝转场（B7）：给延长接缝补过渡段用的型号。必须是**支持两段参考视频**的档：
    # 2.5 = 官方「视频无缝转场」，2.0 系列 = 「轨道补齐」（≤3 段 / 总 ≤15s）。
    # 🩸 别让它继承 `ark_video_model`（1.0 pro fast 只吃一张首帧，喂两段视频会报错）。
    # 🩸 只服务**延长链路**那一个接缝：出片链路不接（2026-10-25 主人拍板）。
    clone_seam_model: str = _env("VT_CLONE_SEAM_MODEL", "doubao-seedance-2-5-260628")

    # 🩸 「大头照 + 全身照」这套**整体作废**（2026-10-26，台账 D48）：三家官方原文
    # 复核后都是「一个换的人 = 一张图」，`ref_plan` 里裁大头照那段已删除。
    # 历史上这里配过 `VT_CLONE_HEAD_SHOT` 开关（2026-10-25 已撤）—— 别再往回加。

    # ---- 换画面·整片重制（双通道）----
    # 通道一：火山 Seedance 2.5 的 edit 任务。它是在源视频上做编辑，
    # 能保住原片的时长/构图/动作，这是"1:1 复刻"的正解。
    # 注意它和逐镜重绘用的 1.0 fast 不是一个档，别混。
    ark_video_edit_model: str = _env("VT_ARK_VIDEO_EDIT_MODEL", "doubao-seedance-2-5-260628")
    # 火山**只收公网 URL 当参考视频**（图/音频才收 base64），
    # 所以必须配一个对外能访问的地址，比如 https://api.example.com
    public_base_url: str = _env("VT_PUBLIC_BASE_URL", "")
    # 给外部模型拉原片的临时链接的签名密钥（不配就退回用方舟 key 派生）
    url_secret: str = _env("VT_URL_SECRET", "")
    # 临时链接有效期（秒）
    source_url_ttl: int = int(_env("VT_SOURCE_URL_TTL", "7200"))
    # 通道二：MiniMax H3。原生多模态参考（图/视频/音频），出片自带音轨，
    # 文档里没有火山那条"禁止真人脸参考"的限制 —— 真人素材优先走它。
    minimax_api_key: str = _env("VT_MINIMAX_API_KEY") or _env("MINIMAX_API_KEY")
    # 国内站是 api.minimaxi.com；海外站 api.minimax.io 用这把 key 会 401
    minimax_base: str = _env("VT_MINIMAX_BASE", "https://api.minimaxi.com")
    minimax_video_model: str = _env("VT_MINIMAX_VIDEO_MODEL", "MiniMax-H3")
    minimax_resolution: str = _env("VT_MINIMAX_RESOLUTION", "768P")
    # 默认走哪个通道：auto（按素材自动选）/ volc / minimax
    clone_channel: str = _env("VT_CLONE_CHANNEL", "auto")

    # ---- DeepSeek **官方**（复刻的 agent 用它写逐段指令）----
    # 🩸 2026-11-01 主人：「要调 deepseek 官方的，不要火山的」。
    #   在此之前 agent 走的是方舟托管的 `deepseek-v4-1-flash-261017`
    #   （`ark_chat.py`），花的是火山账户的钱。现在改官方端点，独立一把 key。
    #   **没有 key 就直接报错**，不静默回落火山 —— 回落了用户以为切了其实没切。
    deepseek_api_key: str = _env("VT_DEEPSEEK_API_KEY", "")
    # 官方端点（OpenAI 兼容）：https://api.deepseek.com/chat/completions
    deepseek_base: str = _env("VT_DEEPSEEK_BASE", "https://api.deepseek.com")
    # 官方 `/models` 实测返回的唯一型号 id（DeepSeek-V4.1-Flash，1M 上下文、
    # 原生读图、支持 function calling）。别填方舟那套 `deepseek-v4-1-flash-261017`。
    deepseek_model: str = _env("VT_DEEPSEEK_MODEL", "deepseek-flash")

    # ---- 视觉盘点（换画面之前先看清原片里有谁、在第几秒）----
    # 走方舟 Chat API 的视频理解：直接送视频，官方按 fps 抽帧并给每帧打时间戳，
    # 不需要我们自己 ffmpeg 抽帧。默认 lite（便宜一个档），失败自动升 pro。
    # 关掉它 = 退回"只写一句把画面里的人物替换为图1"的老行为（多人画面会没有唯一解）。
    vision_enabled: bool = _env("VT_VISION_ENABLED", "1").lower() not in ("0", "false", "no")
    vision_model: str = _env("VT_VISION_MODEL", "doubao-seed-2-1-lite-260915")
    vision_model_fallback: str = _env("VT_VISION_MODEL_FALLBACK",
                                      "doubao-seed-2-1-pro-260915")
    # 每秒抽几帧：官方默认 1，范围 0.2–5。单人/少数人的片子 1 帧/秒足够，
    # 画面变化快（多人跑动、频繁切镜）可以调到 2。
    vision_fps: float = float(_env("VT_VISION_FPS", "1"))

    # ---- OSS（火山的参考视频只收公网 URL，本地素材必须先传这里）----
    # 和在用的大鲸链路同一套桶：dajinggl-img（广州）→ CDN img.dajing.vip
    oss_endpoint: str = _env("VT_OSS_ENDPOINT", "oss-cn-guangzhou.aliyuncs.com")
    oss_bucket: str = _env("VT_OSS_BUCKET", "dajinggl-img")
    oss_access_key_id: str = _env("VT_OSS_ACCESS_KEY_ID", "")
    oss_access_key_secret: str = _env("VT_OSS_ACCESS_KEY_SECRET", "")
    oss_public_base: str = _env("VT_OSS_PUBLIC_BASE", "https://img.dajing.vip")
    oss_prefix: str = _env("VT_OSS_PREFIX", "uploads")
    # 对象 ACL，默认不发（桶/CDN 已可读）。桶是私有的才填 public-read，
    # 但要求这把 AccessKey 有 oss:PutObjectAcl 权限
    oss_acl: str = _env("VT_OSS_ACL", "")
    # 复刻产物目录（与解析任务的 temp 分开，避免被 TTL 清理掉）
    clone_dir: Path = Path(_env("VT_CLONE_DIR", str(ROOT / "data" / "clone")))
    # 一条参考片最多分析多少秒。**0 = 不限制（默认）**：原片多长就分析多长。
    # 要防"有人丢一整部电影进来"再把它设成正数，超过就只取前 N 秒。
    clone_max_seconds: float = float(_env("VT_CLONE_MAX_SECONDS", "0"))
    # 同时跑几个复刻任务。分析和出片都是等 ffmpeg/外部 HTTP，不吃 CPU 峰值
    clone_workers: int = int(_env("VT_CLONE_WORKERS", "2"))
    # 复刻产物保留时长（秒），默认 3 天。配方要复用，所以比 temp_ttl 长得多
    clone_ttl: int = int(_env("VT_CLONE_TTL", str(3 * 86400)))
    # 出片前预览用的单价（**不填就显示"未配置单价"，绝不猜**）。
    # 单位：视频按生成秒、图片按次、配音按千字。
    price_video_per_sec: float = float(_env("VT_PRICE_VIDEO_PER_SEC", "0") or 0)
    price_image_per_call: float = float(_env("VT_PRICE_IMAGE_PER_CALL", "0") or 0)
    price_tts_per_1k_chars: float = float(_env("VT_PRICE_TTS_PER_1K_CHARS", "0") or 0)

    cors_origins: list[str] = field(default_factory=lambda: ["*"])


settings = Settings()
settings.temp_dir.mkdir(parents=True, exist_ok=True)
settings.clone_dir.mkdir(parents=True, exist_ok=True)
(ROOT / "data").mkdir(parents=True, exist_ok=True)
