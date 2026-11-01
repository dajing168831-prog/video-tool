"""各视频模型的参数标准 —— **按模型分档，不许一套通吃**。

出处（全部是厂商官方口径，2026-10-21 抓取；**不是**本地分镜套件的二手总结）
------------------------------------------------------------------------
火山方舟 Seedance
    官方文档  https://www.volcengine.com/docs/82379/1520757  「创建视频生成任务」
              （经文档中心 getDocDetail 取的正文，含参数表）
    模型教程  /docs/82379/2607688  Seedance 2.5
              /docs/82379/2291680  Seedance 2.0 系列
    官方 skill  npx skills@latest add "https://arkdocs.tos-cn-beijing.volces.com/skills/"
                --skill sd25-pe / --skill sd2-pe

MiniMax H3
    官方文档  https://platform.minimaxi.com/docs/guides/video-generation
    接口规范  https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create
              （OpenAPI：必填 model/content/resolution/duration）
    提示词示例 https://platform.minimaxi.com/docs/guides/video-prompt

为什么必须有这张表
------------------
同一个"换成图1里的人"，2.0 和 2.5 的标准并不一样，而且**两家的官方 skill
自己就互相打架** —— 这不是我总结的，是官方原文：

    2.0（sd2-pe「强制约束」）
        最终输出**必须**包含画质包 + 稳定包 + 水印 / Logo 兜底；
        非文字生成再挂字幕兜底；多人场景必挂双胞胎兜底。
        分辨率多一档 4k；参考图 ≤9；视频 ≤3 段、单段 [2,15]s、总 ≤15s。

    2.5（sd25-pe 原则 8「不滥加约束」）
        **不得**自动添加用户未要求的画质包、稳定包、水印、Logo、字幕或其他
        通用负向约束；参数（画幅/时长/分辨率/帧率/声音开关）**不许写进提示词**。
        参考图 ≤30；视频 ≤10 段、单段 [2,30]s、总 ≤30s；素材合计 ≤50 份。

    MiniMax H3（官方文档只有参数，没有"兜底包"这种提示词范式）
        分辨率 768P / 2K（**H3-Max 反过来没有 2K，只有 480P / 768P**）；
        时长 H3 4–15s、H3-Max 5–15s；提示词硬上限 7000 字符。

拿 2.5 能跑通就套到 2.0 上，或者把火山的兜底包搬到 H3 上，都是错的。
"""
from __future__ import annotations

SPECS = {
    # ------------------------------------------------------------------ MiniMax
    "minimax": {
        "label": "MiniMax H3",
        "min_sec": 4.0,
        "max_sec": 15.0,
        "fps": 24,
        # 官方「输出规格」：H3 = 768P / 2K
        "resolutions": ("768P", "2K"),
        "default_resolution": "768P",
        "max_ref_images": 9,
        "max_ref_videos": 3,
        # 参考视频**总时长**上限（官方：2.0 `seedance-20-guide.md:987` ≤15s；
        # 2.5 `seedance-25-guide.md:117` ≤30s；H3 `mm-docs:8273` ≤15s）
        "ref_video_total_sec": 15,
        "max_ref_audio": 3,
        # 人数标准：H3 与 2.0 对齐 = 4 人（2026-10-22 主人定）。
        # 🩸 官方手册**没有**给"几个主体才稳"的数字 —— 中文站/英文站/官方 skill
        # 三处都只给文件上限（参考图 ≤9、视频 ≤3、音频 ≤3、合计 12 文件）。
        # 所以 4 是**我们的产品标准**，不是官方口径，别在 UI 上冒充官方。
        "stable_subjects": 4,
        "max_subjects": 4,
        # 官方「输入条件·全能参考入口」：音频 ≤3 段、单段 [2,15]s、单个 ≤15MB。
        # 这就是"口型参考"的入口 —— H3 不给音频就自己编一套说话动作。
        "ref_audio": True,
        # 混合输入总上限 12 个文件（官方「输入条件」）
        "max_ref_total": 12,
        # 官方硬上限：单个 text 最多 7000 字符
        "prompt_chars": 7000,
        "prompt_advised": "",
        # 提示词里的素材指代（官方示例原文："人物参考视频1的动作…人物参考图1 图2"）
        "ref_style": "图N / 参考视频N / 音频N（不带 @、不带尖括号）",
        # 官方没有"画质包/稳定包/兜底包"这套，别搬火山的过来
        "auto_constraint": False,
        "negative_domain": False,
        # 没有 omni_reference_task_type 这类显式任务类型参数
        "edit_task_param": False,
        "edit_duration": None,
        "edit_ratio": "adaptive",
    },
    "h3-max": {
        "label": "MiniMax H3-Max",
        # 🩸 官方 create 页 `extra` 段（`api-create`:344-360，逐字）：
        #   「`MiniMax-H3-Max` 的额外生成选项。当前仅支持 `prompt_expansion_mode`。
        #     不传 `extra` 或不传此属性时，使用 `balanced`。」
        #   取值 disabled / balanced / quality，default = balanced。
        #   **四档里只有 Max 有 `extra`**，别的档传了是这个型号不收的字段
        #   （`additionalProperties: false`）。所以按型号声明、由请求层原样转发，
        #   核心不认识这个字段名。
        #   我们取 `disabled`：本产品的提示词是**编译出来的复刻稿**，18 条尺子验的
        #   就是发出去的那段正文；让平台再扩写一遍 = 验的和跑的不是同一份，
        #   尺子的保证当场失效。要改成 balanced/quality 只改这一处。
        "request_extra": {"prompt_expansion_mode": "disabled"},
        # 官方：H3-Max 5~15 秒（不支持 4 秒）
        "min_sec": 5.0,
        "max_sec": 15.0,
        "fps": 24,
        # 官方：H3-Max 480P / 768P，**不支持 2K**
        "resolutions": ("480P", "768P"),
        # 官方：不传时默认 768P（不是 480P）
        "default_resolution": "768P",
        "max_ref_images": 9,
        "max_ref_videos": 3,
        # 参考视频**总时长**上限（官方：2.0 `seedance-20-guide.md:987` ≤15s；
        # 2.5 `seedance-25-guide.md:117` ≤30s；H3 `mm-docs:8273` ≤15s）
        "ref_video_total_sec": 15,
        "max_ref_audio": 3,
        # 人数标准：与 H3 / 2.0 对齐 = 4 人（同 minimax 那条说明）
        "stable_subjects": 4,
        "max_subjects": 4,
        # H3-Max 同样是「全能参考生成」，输入条件表两大档共用：音频 ≤3 段
        "ref_audio": True,
        "max_ref_total": 12,
        "prompt_chars": 7000,
        "prompt_advised": "",
        "ref_style": "图N / 参考视频N / 音频N（不带 @、不带尖括号）",
        "auto_constraint": False,
        "negative_domain": False,
        "edit_task_param": False,
        "edit_duration": None,
        "edit_ratio": "adaptive",
    },
    # 🩸 2026-10-28（H3 轮）：官方视频生成 V2 现在是**四档**，不是两档。
    #   出处 `h3-models`（`D:/tmp/official/h3/api-models-2026-10-28.md`，
    #   直连 platform.minimaxi.com/api-reference/video-generation-v2-create 摘录）：
    #   「当前可用值：MiniMax-H3、MiniMax-H3-Highspeed、MiniMax-H3-Lite、MiniMax-H3-Max」。
    #   旧快照 `platform-docs.txt`（2026-10-22）里 Highspeed / Lite **0 次**出现
    #   ⇒ 这两档是之后新增的，不是我们漏抄。
    "h3-highspeed": {
        "label": "MiniMax H3-Highspeed",
        # 官方：Highspeed 与 H3 同档时长（4~15s）
        "min_sec": 4.0,
        "max_sec": 15.0,
        "fps": 24,
        # 🩸 2026-11-01 主人贴的官方价目表（H3 系列旗舰模型）：
        #   Highspeed 768P ¥0.40/s、**480P ¥0.26/s** —— 480P 是有的。
        #   旧注释「只有一档 768P」来自 2026-10-28 的 create 页摘录，价目表更全。
        #   2K 依旧没有（两处口径一致）。
        "resolutions": ("480P", "768P"),
        "default_resolution": "768P",
        "max_ref_images": 9,
        "max_ref_videos": 3,
        "ref_video_total_sec": 15,
        "max_ref_audio": 3,
        "stable_subjects": 4,
        "max_subjects": 4,
        "ref_audio": True,
        "max_ref_total": 12,
        "prompt_chars": 7000,
        "prompt_advised": "",
        "ref_style": "图N / 参考视频N / 音频N（不带 @、不带尖括号）",
        "auto_constraint": False,
        "negative_domain": False,
        "edit_task_param": False,
        "edit_duration": None,
        "edit_ratio": "adaptive",
    },
    "h3-lite": {
        "label": "MiniMax H3-Lite",
        # 🩸 官方 create 页 `ratio` 段：「多模态参考生视频…`MiniMax-H3-Lite` **暂不支持
        #   adaptive**，需显式指定具体比例」。我们参考类任务原来写死 adaptive ⇒
        #   选这一档会被拒。`minimax._ratio_for_video()` 按素材宽高比算一个显式值。
        "ratio_adaptive": False,
        # 官方：Lite 与 H3 同档时长（4~15s）
        "min_sec": 4.0,
        "max_sec": 15.0,
        "fps": 24,
        # 官方：「480P / 768P，不支持 2K」
        "resolutions": ("480P", "768P"),
        # 官方：「默认 768P」
        "default_resolution": "768P",
        "max_ref_images": 9,
        "max_ref_videos": 3,
        "ref_video_total_sec": 15,
        "max_ref_audio": 3,
        "stable_subjects": 4,
        "max_subjects": 4,
        "ref_audio": True,
        "max_ref_total": 12,
        "prompt_chars": 7000,
        "prompt_advised": "",
        "ref_style": "图N / 参考视频N / 音频N（不带 @、不带尖括号）",
        "auto_constraint": False,
        "negative_domain": False,
        "edit_task_param": False,
        "edit_duration": None,
        "edit_ratio": "adaptive",
    },
    # ------------------------------------------------------------------ 火山 2.5
    "seedance-2-5": {
        "label": "火山 Seedance 2.5",
        # 官方：2.5 默认 -1；取值范围 [4, 30]
        "min_sec": 4.0,
        "max_sec": 30.0,
        # 官方：2.5 默认 720p；可选 480p、720p、1080p（**没有 4k，4k 是 2.0 的**）
        "resolutions": ("480p", "720p", "1080p"),
        "default_resolution": "720p",
        # 官方：全模态参考 1~30 张
        "max_ref_images": 30,
        "max_ref_videos": 10,
        # 参考视频**总时长**上限（官方：2.0 `seedance-20-guide.md:987` ≤15s；
        # 2.5 `seedance-25-guide.md:117` ≤30s；H3 `mm-docs:8273` ≤15s）
        "ref_video_total_sec": 30,
        "max_ref_audio": 10,
        # 人数标准：官方《Seedance 2.5 提示词指南》§「素材输入建议」原句 ——
        # 「主体图，建议输入多少个主体：1-8 主体效果较好；更多可尝试 9-12 主体，
        #  但稳定性下降、可能需要抽卡」。
        # ⇒ 稳定线 8，硬上限 12（官方给的"可尝试"上限；再往上没有依据）。
        "stable_subjects": 8,
        "max_subjects": 12,
        # 官方：单个音频 [2,30]s、≤10 段，全部音频总时长 ≤30s
        "ref_audio": True,
        # 官方 skill：图片 + 视频 + 音频合计最多 50 份
        "max_ref_total": 50,
        "prompt_chars": None,
        # 🩸🩸 2026-10-28 更正：这里原来抄了「中文 ≤500 字 / 英文 ≤1000 词」——
        #   **那不是 2.5 的标准**，是从别处搬过来的：
        #   ① 那条写在 `volc-api:175`，位置是 `content.text` 字段的**通用说明**
        #      （`:169` 先说"所有模型均支持中英文"），而且 `:177` 的"更多使用技巧"
        #      直接链到 **2.0 的 prompt guide**；
        #   ② 2.5 自己的官方 skill 反而明写 `sd25-pe:522`：
        #      「Prompt 较长时优先保留主体映射、素材职责、事件和结束状态，压缩重复
        #        风格词、重复约束和未激活素材，**不设置固定字数上限**」。
        #   ⇒ 2.5 一律留空：`prompt_advice()` 解析不到数字就返回 ""，不提示、不压缩。
        #   2.0 系列的三个块保留 500 字（对它们是对的，别跟着改）。
        "prompt_advised": "",
        "ref_style": "@图片N / @视频N / @音频N",
        # 官方 skill 原则 8：不得自动加画质包/稳定包/水印/Logo/字幕
        "auto_constraint": False,
        "negative_domain": False,
        # 2.5 才有：显式声明任务类型；编辑任务 duration 只能 -1、ratio 只能 adaptive
        "edit_task_param": True,
        "edit_duration": -1,
        "edit_ratio": "adaptive",
    },
}

# 可选型号：ID 取自官方「模型列表」（2026-10-21）
#   火山 https://www.volcengine.com/docs/82379  模型列表 DocumentID=1330310
#   MiniMax https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create
# 1.0 pro / 1.0 pro fast 官方标「即将下线」，且不支持参考视频换主体，不放进选项。
MODELS = {
    # 🩸 2026-10-31 主人拍板：**2.0 三档全部下架**，界面不再提供。
    #   依据：29 次真实换画面请求全是 2.0 Mini（2.5 零次），而 2.0 Mini
    #     ① 分辨率天花板 720p；② 没有编辑任务身份（`edit_task_param=False`）；
    #     ③ 强制挂「细节丰富/电影质感」兜底包（`volc20_compile.py:1272`），
    #        与「保留原片」方向相反。
    #   SPECS 里的 2.0 条目**已随下架删除**（2026-10-31，见 `SPECS` 上方注释）。
    #   历史任务带旧 2.0 型号 ID 时不查表，`volc()` 直接回落 2.5 那一档 ——
    #   「再生成」照样能跑，只是按 2.5 的 30s 上限切段。别再按旧注释去找 2.0 表。
    "volc": [
        ("doubao-seedance-2-5-260628", "Seedance 2.5"),
    ],
    # 🧊 2026-11-01 主人要求冻住 H3、切到 2.5 验证：入口不再提供。
    #   `SPECS` 里四档（`h3` / `h3-max` / `h3-highspeed` / `h3-lite`）**一字未动** ——
    #   历史任务带旧型号 ID 进来时照样查得到档位，只是出片接口会按
    #   `Caps.frozen`（`models/h3.py`）拒绝。
    #   解冻：把下面四档填回来，并把 `models/h3.py` 的 `frozen` 改回 False。
    "minimax": [
        # ("MiniMax-H3", "MiniMax H3"),
        # ("MiniMax-H3-Max", "MiniMax H3-Max"),
        # ("MiniMax-H3-Highspeed", "MiniMax H3-Highspeed"),
        # ("MiniMax-H3-Lite", "MiniMax H3-Lite"),
    ],
}

# 出图型号（官方 Seedream 5.0 页「模型 ID」表，2026-10-31 实读原文：
#   Seedream 5.0 pro `doubao-seedream-5-0-pro-260628` / Seedream 5.0 flash
#   `doubao-seedream-5-0-flash-260915`；两者都支持「文生图」「单 / 多图生图」。
#   出处 https://docs.volcengine.com/docs/ark/seedream-5-0-pro
IMAGE_MODELS = [
    ("doubao-seedream-5-0-flash-260915", "Seedream 5.0 Flash"),
    ("doubao-seedream-5-0-pro-260628", "Seedream 5.0 Pro"),
]

# 默认（没配或认不出来时）落到 2.5 —— 2.0 已归档，火山只剩这一档在售。
# 猜宽了会让请求被拒，猜窄了只是多切一刀；2.5 的上限比谁都宽，认错型号时
# 宁可让它按自己的档位收窄（`_resolution_for` 会按型号再收一次）。
_DEFAULT_VOLC = "seedance-2-5"
_DEFAULT_MINIMAX = "minimax"


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def volc(model: str) -> dict:
    """按模型 ID 认档位。

    认不出来的返回 2.0 那档：时段上限更紧、参考数更少。
    猜宽了会让请求被模型直接拒掉，猜窄了只是多切一刀 —— 后者代价小。
    """
    m = _norm(model)
    if not m:
        return SPECS[_DEFAULT_VOLC]
    if "minimax" in m or m.startswith("h3"):
        # ⚠️ 不能用 "max" in m 判断：mini**max** 本身就含 max，
        # 会把 MiniMax-H3 误认成 H3-Max，结果时长下限变 5s、2K 被拒。
        # 🩸 2026-10-28：四档路由只留一份 —— 以前这里和 `minimax()` 各写一遍，
        #   加了 Highspeed / Lite 之后必然只改一处、另一处继续把她们当基础 H3
        #   （于是 `bounds_for` / `_resolution_for` / `subjects` 全是错档）。
        return minimax(model)
    if "seedance-2-5" in m or "seedance-2.5" in m:
        return SPECS["seedance-2-5"]
    # 🩸 2026-10-31：2.0 的参数表随复刻视频下架一并删除。传旧 2.0 型号
    #   （历史请求/老前端缓存）会落到下面的默认档（2.5），不会 KeyError。
    return SPECS[_DEFAULT_VOLC]


def minimax(model: str) -> dict:
    """按官方四档路由（`h3-models`）。

    🩸 2026-10-28：以前只有 `-max` 一条判断，其余一律落到基础 H3 ——
    `MiniMax-H3-Highspeed` / `MiniMax-H3-Lite` 会被当成 H3，于是我们放行 2K，
    接口直接拒（这两档官方都「不支持 2K」）。名称里没有 **max** 的档现在各自有表。
    """
    m = _norm(model)
    if "-highspeed" in m:
        return SPECS["h3-highspeed"]
    if "-lite" in m:
        return SPECS["h3-lite"]
    if "-max" in m:
        return SPECS["h3-max"]
    return SPECS["minimax"]


def subjects(model: str = "") -> tuple[int, int]:
    """这次能换几个人 → (稳定线, 硬上限)。

    用 `volc()` 认档位而不是按通道分：它内部已经把 MiniMax 的型号 ID 路由到
    H3 那两档，所以一个入口能覆盖全部可选型号（`/clone/models` 的 id 都在这张表里）。
    认不出来的型号按 2.0 的 4 人 —— 和时长/分辨率一样，宁可报窄也别报宽。
    """
    ms = volc(model)
    return (int(ms.get("stable_subjects") or 4), int(ms.get("max_subjects") or 4))
