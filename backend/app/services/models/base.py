"""一家模型 = 一个适配器。核心代码只认这个接口，不认型号名。

🩸 2026-10-26 主人拍板：「现在到处都还绑定在一起，如果后期我们开发聚合平台这项目直接黄」
—— 这是模型分离的**代码层**（L3）。之前只做到 L1 验收分离（每家自己的尺子/测试文件）。

**为什么不是"再加几个 if"**：加第 4 家模型以前要改 10 处（参数表、compile 分派、
标号语法、通道选择、分辨率、闸分派、时长上限、extend 家族分支、尺子、测试），
没有一处是"新建一个文件就行"。有了这个接口，加一家 = 新建一个目录 + 登记一行。

**接口只有五件事**：
  · `caps`          能力参数（时长上下限/参考音频/提示词上限/分辨率表…）
  · `pic(n)`/`vid()` 参考图、参考视频在提示词里怎么写（`@图片1` vs `<Picture 1>`）
  · `pre_compile()` 编译前要做的加工（H3 的中文自动翻英文挂这里，核心不知道）
  · `gate()`        出片前的可指认闸（每家读的描述字段都不一样）
  · `compile()`     把规格编译成这家认的提示词

**不许在这里写"如果这家就…"**：那是把耦合搬了个地方。每家的差异写在各家目录里。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

#: 提示词上限没配时的兜底（不设限反而危险：超了是请求被拒，不是"效果差一点"）。
NO_CAP = 0


@dataclass(frozen=True)
class Caps:
    """一家的能力参数。字段全部有默认值，新增一家只覆盖它真的不同的那几项。"""

    model_id: str
    family: str                      # "volc" / "minimax"
    max_dur: float                   # 单段时长上限（秒）
    min_dur: float = 2.0
    ref_audio: bool = False          # 编辑任务能不能喂参考音频
    edit_task_param: bool = False    # 用不用"编辑任务"这套参数（2.5 的专有形态）
    #: 母版视频自带音轨，是否等同于「已经提供了音频参考」。
    #: 🩸 默认 False —— 两家官方口径都是**音频要单独作为 `reference_audio` 送**。
    #:   H3 更是明说反话：`ref-en:112`「An ordinary reference video does not
    #:   create `<Audio N>` merely because the file contains sound.」
    #:   曾经靠 `not edit_task_param` 隐式让 H3 走母版（注释写「只对 2.0 生效」，
    #:   可 2.0 下架后 2.5 被 edit_task_param 挡掉，**只剩 H3 走进去**）⇒
    #:   请求里一条音频都没有、提示词却写着 `<Audio 1>` ⇒ 嘴型必错。
    #:   2026-11-01 真实快照实锤（`audio=false` / `audio_in_master=false`）。
    audio_from_master: bool = False
    prompt_chars: int = NO_CAP       # 提示词硬上限（超了接口直接拒）
    default_resolution: str = "720p"
    #: 分辨率映射：{"1080p": "1080P"} 这类；空 = 原样传
    resolution_map: dict[str, str] = field(default_factory=dict)
    #: 这条通道收的全部档位名（**大小写敏感**：火山 480p / H3 480P）
    resolutions: tuple[str, ...] = ()
    #: 用户按"清晰度"选，各家档位名不一样 → 同义映射（火山 1080p ↔ H3 2K）
    resolution_alias: dict[str, str] = field(default_factory=dict)
    #: 这家认不认火山的 `asset://` 素材 ID
    asset_id: bool = False
    #: 清晰度默认档要不要**按原片画幅**自动推（火山这么做；H3 用固定默认档）
    auto_res_from_frame: bool = False
    #: **中文句子**里引用参考图的写法，`{}` 换成序号；空 = 直接用 `pic()`。
    #: 🩸 H3 有两套标号：六段式正文用 `<Picture N>`（`pic()`），
    #: 中文编辑目标句用 `图N` —— 这不是"哪家"的问题，是同一家的两种书写场合。
    pic_inline: str = ""
    vid_inline: str = ""

    # ---- 出片流水线里的能力开关（2026-10-26 L3 第二轮）----
    #: 要不要逐镜画面描述（H3 的 `detailed_description`；别家算了纯烧钱）
    shot_looks: bool = False
    #: 参考段帧数要不要卡成 8n+1（2.5 的编辑任务）
    align_8n1: bool = False
    #: 人物槽位要不要按「首次出场顺序」排（2.5 指南「角色对应错误」）
    order_by_appearance: bool = False
    #: 某一镜里没出现的人，要不要把它的参考图摘掉并重编号（H3 官方要求每张图都有定义）
    drop_absent_people: bool = False
    #: 边界帧是不是走「提示词内定义」（H3 / 2.5）
    boundary_pic: bool = False
    #: 💀 **已无消费者**（2026-10-26）：三家官方复核后都是「一个换的人 = 一张图」，
    #: `video_edit.ref_plan` 里裁大头照那段已删除（台账 D48）。字段留着只是
    #: 为了让三个 adapter 的 caps 形状不变；**别再照着它写两条图的逻辑**。
    split_person_images: bool = False
    max_ref_images: int = 0
    #: 缺逐镜描述时要不要先补一次盘点再重算提示词（H3）
    ensure_shot_source: bool = False
    #: 逐段提示词改由**这家自己的函数**产出（例如官方的提示词改写服务）。
    #: 签名 `(cid, n, *, video, images, slots, audio, dur, extra) -> str`；
    #: None = 用代码编译的那一版（默认）。
    #: 🩸 共用层只认"有没有这个函数"，不认型号名、也不 import 任何一家的模块。
    prompt_for: Callable[..., str] | None = None
    #: 同上那套输入的**指纹**（只算不发请求、不花钱）。出片核心要在查段缓存
    #: **之前**知道"这一次的提示词会不会变"，所以必须有它；没有 = 只有
    #: `prompt_for` 的机器，核心退回人工版本标记。
    #: 🩸 2026-11-02：以前只有 `prompt_for`，改写器产出的词进不了段缓存键，
    #:   全靠人工升 `:irN`；漏升一次，新词永远用不上（三次渲染拿回同一段旧片）。
    prompt_sig: Callable[..., str] | None = None
    #: 边界帧受不受「必须能钉死编辑任务类型」这条限制（2.0 / 2.5 受，H3 不受）
    boundary_by_edit_task: bool = False
    #: 输出时长只能取**整数秒**（2.0 系列，`sd20.md:119`「输出时长 4~15 秒」，
    #: 单位是秒、没有小数）。声明了它，核心会把段边界先吸附到整数秒，
    #: 让"生成长度与输入长度严格一致"（官方 A-4 口型那条）。
    #: 🩸 2026-10-31：这是**能力**不是"哪一家"，核心只读这个标记。
    int_output_sec: bool = False
    #: 发请求前跑「唯一请求形状」闸：视频恰好 1 段编辑母版、音频恰好 1 条、
    #: 段长整数秒、提示词非空。偏离的形状一次都没被验证过 ⇒ 本机报错不发票。
    #: 只有 2.0 声明（2026-10-31 主人批准的第 1 步）；别家声明前先把它们的
    #: 形状实测出来，别拿 2.0 的结论去管别家。
    shape_guard: bool = False
    #: 换装缺素材时要不要**逐个**查（名单里每个人各有槽位和自己那句描述，
    #: 缺一个就拦）。2.0 = True（2026-10-27 那轮定的，第 2、3 个人缺东西时
    #: 编译器会静默跳过，图白传）；2.5 / H3 仍是老口径（只查 `wardrobe` 一个槽位），
    #: 等轮到它们那一轮再改 —— 一轮一个型号。
    #: 🩸 2026-10-28：这个字段存在的原因是 `edit_spec` 是三家共读的，
    #: **不许在里面写型号名**（分离门会红）。核心只读这个标记。
    wardrobe_check_per_person: bool = False
    #: `auto` 选通道的优先级：`{"file": 0, "none": 1}` —— 数字小的先试
    auto_prefer: dict[str, int] = field(default_factory=dict)
    #: 没指定型号时，该通道的默认型号读配置里的哪个字段
    #: （`ark_video_edit_model` / `minimax_video_model`）—— 核心不认识字段名。
    default_model_setting: str = ""
    #: 这个适配器是不是**本通道的代表**（按通道取时用它）。
    #: 🩸 一个家族可以有好几个适配器（火山 2.0 / 2.5），只设一个为 True。
    is_channel_default: bool = False
    #: 🧊 这条产品线当前**不接这一家**（2026-10-31 复刻冻结 H3）。
    #: 只关入口：界面不列这条通道、`regen_model_error` 拒它的型号与通道；
    #: **参数表、编译器、测试全部保留**，改回 False 即解冻。
    #: 核心只读这个标记，不认厂商名（分离门要求）。
    frozen: bool = False

    #: 报错/提示里给人看的名字（核心不维护这张表）
    display_name: str = ""

    # ---- 视频延长（向前/向后，2026-10-26 L3 第三轮）----
    #: 拼接接缝：(前一段末尾裁几帧, 后一段开头裁几帧)。2.0 = (6,1)，2.5/H3 = 不裁。
    extend_seam: tuple[int, int] = (0, 0)
    #: 有没有「两段视频补全」能力（没有就不做接缝转场，交硬接）
    extend_transition: bool = False
    #: 送进去的源片要怎么收："" 原样 / "pixel_floor" 放大到像素下限 / "clip" 截时长
    extend_ref_mode: str = ""
    extend_ref_min_px: int = 0
    extend_ref_max_px: int = 0
    extend_ref_max_sec: float = 0.0
    extend_ref_max_mb: float = 0.0
    #: 延长任务能不能**带参考图**（官方 `sd25-guide:93` 的示例
    #: 「向后延长 @video1，@image1 的角色从天而降」= 可以）。
    #: 只有 2.5 声明；2.0 / H3 收到图会当场报错，不静默丢掉。
    extend_ref_images: bool = False
    #: 延长「往后接什么」的预设：`{key: 一句可直接填进模板的话}`。
    #: **空 = 这家不支持预设**，前端继续用自由文本框。
    #: 只有 2.5 填，条目出自它自己的官方 `sd25-pe:528`（各家标准不同，不共用）。
    extend_modes: dict[str, str] = field(default_factory=dict)

    # ---- 输入媒体硬门槛（超了是同步 400，不是效果差一点）----
    #: 参考图：`{"side": (lo, hi), "ratio": (lo, hi), "max_bytes": n}`
    image_limits: dict[str, Any] = field(default_factory=dict)
    #: 参考视频：`{"min_px", "max_px", "side", "ratio", "fps", "max_bytes"}`
    video_limits: dict[str, Any] = field(default_factory=dict)

    raw: dict[str, Any] = field(default_factory=dict)   # model_specs 里的原始条目


class Dialect:
    """一家把「换什么」翻成句子的口径 —— **共用层 `edit_spec._clauses` 只调这里**。

    🩸 2026-10-28 为什么要有它：`_clauses` 里原来有 13 处 `if edit_task:`，
    而 `edit_task` 名叫"任务类型"，实际 2.0 永远传 False、2.5 永远传 True
    （`model_specs` 里写死）—— **那就是型号开关伪装成任务开关**。
    后果：改 2.5 的句式要在三家共读的文件里动手，改完 2.0 的产出也会跟着变。

    现在每家把这些差异写进自己的 `Dialect` 子类，共用层只问"这家怎么说"。
    加第 4 家 = 再写一个子类，`_clauses` 一行不用改。

    **默认实现是"不写这句"**：只有真需要那半句的家才覆盖它。
    """

    #: 原对象的指代开头（`将其中的X` / `只把X`）
    def subj(self, obj: str) -> str:
        raise NotImplementedError

    #: 换装的动词（两家的官方动词表不同，见各家实现里的出处）
    def wardrobe_verb(self) -> str:
        raise NotImplementedError

    #: **没传图、只有文字描述**时的换装动词。默认 = 2.0 官方 `sd20-guide:39`
    #: 「将其中的<原特征>修改为<新特征>」；2.5 在自己的方言里覆盖。
    def wardrobe_verb_text(self) -> str:
        return "修改为"

    #: 换人句的职责分句（`面部特征参考…，妆造参考…`）。
    #: 🩸 2026-10-30：它现在是一个**独立的前置参考句**（以「参考@图…」开头），
    #:   不是接在替换句尾巴上的 `；…` —— 官方 `sd20-guide:59-65` 的组合任务句式是
    #:   「参考<图片N>的[参考维度]，严格编辑<视频X>，[具体编辑内容]」。
    def person_duty(self, *, pic: str, rtag: str, in_wardrobe: bool) -> str:
        return ""

    #: 原片里第 i 个人的**指认短语**（多人换人句的宾语）。
    #: 两家各一份实现 —— 它决定"模型认不认得出换的是谁"，是提示词产出，
    #: 不是共用工具（哪怕两家当前算法一样，也不许互借）。
    def orig_feat(self, people: list[dict], i: int,
                  pool: list[dict] | None = None, cloth: bool = True) -> str:
        return ""

    #: 指认短语取不出、方位也用不了时，还试不试**封顶后的特征短语**当宾语。
    #: 🩸 2026-10-30：`_head_noun` 只取第一个逗号前，整句用顿号时那就是全串，
    #:   3–6 个特征原样进宾语（绕过官方 `sd20-guide:95` 的「2–3 个」）。
    #:   2.0 有自己的封顶尺（产品线 2），在这里再抽一次；**别家返回空** ——
    #:   各家的封顶口径不同，不许借用（一轮一个型号，2.5/H3 还没轮到）。
    def feat_fallback(self, src: str) -> str:
        return ""

    #: `其他…保持不变` 这半句（LAS 官方原句的后半截）。
    def keep_others(self, names: list[str]) -> str:
        return ""

    #: 换装句的宾语 → `(短语, 后面是否可以不经 subj 直接拼动词)`。
    #: `ctx` 里给全：pid / i / people / frame_people / desc_by_id / who / c / idx。
    def wardrobe_subject(self, ctx: dict) -> tuple[str, bool]:
        raise NotImplementedError

    #: 风格参考图 / 视频的整句。
    def style_ref(self, pic: str) -> str:
        raise NotImplementedError

    def style_video(self) -> str:
        raise NotImplementedError

    #: 已经有风格参考图/视频时，还要不要发风格词（2.0 叠加、2.5 三选一）。
    def style_word_when_ref(self) -> bool:
        return True

    #: 风格词整句。
    def style_word(self, word: str) -> str:
        raise NotImplementedError


class NoDialect(Dialect):
    """不走 `edit_spec._clauses` 的模型用它占位（H3 是六段式，自己拼）。

    真被调到就说明路由错了 —— 每家该用自己那套。
    """

    def _no(self, *a, **k):
        raise NotImplementedError("这家不走 `_clauses`，别把它的 spec 送进火山编译器")

    subj = wardrobe_verb = wardrobe_subject = _no
    style_ref = style_video = style_word = _no


@dataclass(frozen=True)
class ModelAdapter:
    """一家的全部模型相关行为。核心只调这些，不 import 任何一家。"""

    caps: Caps
    #: 「换什么」怎么翻成句子的口径（见 `Dialect`）。共用层只调它，
    #: 于是 `edit_spec._clauses` 里不再需要 `if 某型号`。
    dialect: Dialect
    #: 按**具体型号**取这家参数表里那一档（核心不再自己判断属于哪一家）
    specs_for: Callable[[str], dict]
    pic: Callable[[int], str]                    # 第 n 张参考图在提示词里的写法
    vid: Callable[[], str]                       # 参考视频的写法
    compile: Callable[..., str]                  # (spec, **kw) -> 提示词
    gate: Callable[..., None] = lambda *a, **k: None      # 出片前的闸
    pre_compile: Callable[..., None] = lambda *a, **k: None  # 编译前加工（可原地改 spec）

    #: 把**一段**发出去。返回 `(真正发出去的视频地址, 真正发出去的参考图, 入库记录)`。
    #: 🩸 两家的请求形态完全不同（火山公开 URL + `asset://` 入库 + 生成音轨；
    #: H3 本地文件直传），所以整段下沉，核心只调这一个入口。
    submit: Callable[..., tuple] | None = None
    #: 接口报错时**追加**的「下一步点哪里」（返回空串 = 不追加）。
    #: 火山有审核类错误码要翻译，别家没有。
    error_hint: Callable[[str], str] = lambda m: ""
    #: 这条通道配好了没有 / 没配好时该改哪个环境变量
    ready: Callable[[], bool] = lambda: True
    ready_error: Callable[[], str] = lambda: ""

    #: 「逐段指令」agent 这条路：**这家自己的实现模块**（返回模块对象）。None = 没有。
    #: 🩸 2026-11-01：`clone_agent` 的 SYSTEM 与硬闸是火山 2.5 的模板（中文正文 +
    #: 五段标记 + `@视频1/@图片N`），H3 是英文六段式 + `<Picture N>`，**两套不通用**。
    #: 所以按家挂在适配器上，核心只调模块接口（`.generate` / `.cached` / `.load`），
    #: 既不 import 任何一家，也不写厂商名。
    agent: Callable[[], object] | None = None

    # ---- 视频延长（向前/向后，2026-10-26 L3 第三轮）----
    #: `(direction, content) -> 提示词`。三家的延长口径完全不同，各写各的。
    extend_prompt: Callable[[str, str], str] | None = None
    #: 真的把延长请求发出去（火山公网 URL / H3 本地直传，形态彻底不同）
    extend_submit: Callable[..., None] | None = None

    @property
    def family(self) -> str:
        return self.caps.family

    @property
    def model_id(self) -> str:
        return self.caps.model_id
