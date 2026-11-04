# H3 官方资料思维导图（2026-11-02 全源核验版）

> 这份是**资料地图**，不是规则表。规则细节在 [H3-OFFICIAL-MAP.md](H3-OFFICIAL-MAP.md)（34 源 / 25,488 行索引）。
> 本文回答三件事：**官方到底有哪些资料 / 哪份是最新的 / 我们缺哪份**。
>
> 建表起因（2026-11-02 主人）：「我测试这个模型是官方新上的，有可能是文档或是 skill 没有更新，
> 你大可去查他们上线时间还有 skill 包的更新」＋「把资料都做好思维导图」。
>
> 🩸 **结论先写**：所有官方源今天全部重拉核过，**没有任何一份比本工程手里的更新**。
> HuggingFace 那份一直没读到的「Prompting Guidance」，经 `hf-mirror.com` 拿到了 ——
> 就是我们已经有的 `base-en.txt` / `ref-en.txt`，**逐字节相同**（见 §2.3）。
>
> 🔴 **2026-11-03 补漏（最重要的一条）**：官方**换人样例一共 6 条，全部在飞书手册里**
> （`manual-2026-10-28.md` §2.2 / §3.1，见 **§六 6.4**），全是**自然语言短句**；
> `ref-en.txt` 六段式里**一条换人样例都没有**，只有一个 `attribute_transfer` 标记名。
> 所以「H3 换人怎么写」的答案只有一个出处 = **手册**，不是 `ref-en.txt`。

---

## 一、总览树（思维导图）

```
MiniMax H3 官方资料
│
├── ① 官方文档站 platform.minimaxi.com（CN）／platform.minimax.io（EN）
│   ├── 指南
│   │   ├── guides/video-generation.md ......... 生成方式/输入条件/三件套入口
│   │   ├── guides/video-prompt.md ............. 三大能力亮点示例（含富文本 table）
│   │   └── guides/local-deploy-h3.md .......... ComfyUI / SGLang 自托管
│   ├── API（v2 视频生成）
│   │   ├── video-generation-v2-create ......... 创建生成任务（model/content/resolution/duration/ratio/extra）
│   │   ├── video-generation-v2-h3-context-ir .. ★ 提示词改写器（只出词不出片）
│   │   ├── video-generation-v2-query .......... 查任务（%7 天）
│   │   ├── video-generation-v2-list ........... 列任务（task_type 过滤）
│   │   ├── video-generation-v2-delete ......... 取消/删除
│   │   ├── video-generation-v2-regeneration ... 768P → 2K 再生成
│   │   └── errorcode.md ....................... 错误码总表
│   ├── OpenAPI JSON
│   │   └── v2-video-generation.json ........... 机器可读 schema（模型枚举/字段）
│   ├── 版本与销售
│   │   ├── release-notes/models.md ............ 模型发布日志（H3 = 2026-07-31）
│   │   ├── release-notes/apis.md .............. 接口更新日志（最新 2025-10-28，未更 H3）
│   │   ├── faq/models.md ...................... 可用模型表（★ 与 create 页冲突，见 §3）
│   │   └── pricing/overview.md ................ 四档定价（Lite 480P ¥0.16/秒）
│   └── llms.txt ............................... 全站文档索引
│
├── ② GitHub MiniMax-AI/MiniMax-H3（最新提交 2026-10-28）
│   ├── README.md（模型卡：三件套 / 输入规格 / Full 2K Workflow）
│   ├── skills/
│   │   ├── h3-prompt-writing/ ................. ★ 官方提示词 skill
│   │   │   ├── SKILL.md（40 行，含 "Tips for Better Results"）
│   │   │   └── references/
│   │   │       ├── base-en.txt ................ T2VA / I2VA / FL2VA / L2VA 写法
│   │   │       └── ref-en.txt ................. Ref2VA 六段式写法
│   │   ├── 8 个体裁 skill（3d-animation / brand-promo / co-op-game /
│   │   │   handdrawn-live / minimalist-product-ad / music-video-subtitle /
│   │   │   paper-collage / papercraft-stop-motion）
│   │   │   ⚠️ 是"体裁工作流"，不是 API 规格，**不许套到换人/复刻上**
│   │   └── skills-lock.json ................... skill 版本锁
│   ├── .claude/skills/ 、.agents/skills/ ...... ⚠️ 旧副本（35 行，缺 Tips）
│   └── scripts/readme/ ........................ ★ 官方"怎么调"的可执行答案
│       ├── full-2k-ref2va-h3-context-ir.sh .... IR 请求（一句话输入）
│       ├── full-2k-ref2va-h3-base.sh .......... IR 的词 → 本地 H3-Base 出片
│       ├── full-2k-ref2va-h3-regenerate-2k.sh . 768P → 2K
│       ├── reproducible-768p-ref2va-request.sh  . 可复现的 768P 完整请求（带六段词原文）
│       └── full-2k-*-reference-{768p,2k}-...sh  . 开放平台直连对照
│
├── ③ HuggingFace MiniMaxAI/MiniMax-H3（lastModified 2026-08-13）
│   ├── README.md .............................. 比 GitHub 版旧
│   ├── docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md  ← = 我们的 base-en.txt（同哈希）
│   ├── docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md   ← = 我们的 ref-en.txt（同哈希）
│   ├── docs/QA-about-License.md ............... 许可证问答（与提示词无关）
│   └── 权重（FL2VA / Ref2VA / H3-Base 各一套）
│
├── ④ 飞书官方《MiniMax H3 模型 - 使用手册》（revision 1328）
│   └── manual-2026-10-28.md（我们的 rev 1327）
│       提示词公式 / 素材用途表 / 三类模式写法 / 6 条踩坑 / 编辑能力示例
│
└── ⑤ 官方博客 www.minimax.cn/blog/minimax-h3（2026-07-31）
    └── 发布说明 + 招牌示例：「参考视频1的希区柯克镜头运动，让图2中的人物唱歌，歌声参考音频3」
```

---

## 二、今天逐源核验的结果

### 2.1 平台文档站（CN / EN）

| 文件 | 线上现状 | 与工程本地比 |
|---|---|---|
| `video-generation-v2-create.md` | 21,925 B | **sha256 相同**（`9a7276b7…`） |
| `openapi v2-video-generation.json` | 76,669 B | **sha256 相同**（`0a3161c5…`） |
| `video-generation-v2-h3-context-ir.md`（EN） | 22,928 B | 内容与 CN 页一致，只是语言不同 |

→ **平台文档没有比 11-02 快照更新。**

### 2.2 GitHub skill 包（三份副本，只有一份是最新的）

| 路径 | 行数 | sha256 前 8 | 判定 |
|---|---|---|---|
| `skills/h3-prompt-writing/SKILL.md` | 40 | `a7000443…` | ✅ **最新**（= 工程本地那份，含 Tips 整节） |
| `.claude/skills/h3-prompt-writing/SKILL.md` | 35 | `a48f9db1…` | ⚠️ 旧版，缺 "Tips for Better Results" |
| `.agents/skills/h3-prompt-writing/SKILL.md` | 35 | `a48f9db1…` | ⚠️ 同上 |

references 两份（`base-en.txt` / `ref-en.txt`）三处副本**字节相同**，无需更新。

### 2.3 HuggingFace（这次经 `hf-mirror.com` 拿到了）

| 文件 | 大小 | sha256 前 8 | 对照结论 |
|---|---|---|---|
| `docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md` | 23,553 B | `1e574f35…` | **= 本地 `ref-en.txt`，逐字节相同** |
| `docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md` | 15,773 B | `2cfebc09…` | **= 本地 `base-en.txt`，逐字节相同** |
| `README.md` | 38,406 B | `f0116a90…` | 比 GitHub 版旧（HF lastModified **2026-08-13**） |
| `docs/QA-about-License.md` | 3,917 B | `c39dcfc5…` | 许可证问答，与提示词无关 |

→ **"HuggingFace 的 Prompting Guidance 是另一份更详细文档"这个猜测不成立**：
它就是 `ref-en.txt` + `base-en.txt`，我们已经有了、而且用了。

### 2.4 飞书使用手册

| 项 | 工程本地 | 线上现版 |
|---|---|---|
| revision | 1327 | **1328** |
| 正文 | — | 逐段对比后：**只有排版差异**（飞书自动编号被吞、表格并格方式不同），**无新增/删除任何一条规则** |

### 2.5 发布日志 / 模型表 / 定价

| 页面 | 关键内容 | 备注 |
|---|---|---|
| `release-notes/models.md` | **H3 发布于 2026-07-31**；之后只有 M3.1 Flash（10-19） | **Lite / Highspeed / Max 一条发布记录都没有** |
| `release-notes/apis.md` | 最新一条停在 **2025-10-28**（Hailuo-2.3） | 完全没提 H3 系列 |
| `faq/models.md` | 只列 **MiniMax-H3** 和 **MiniMax-H3-Max** | **Lite / Highspeed 不在表里**；且写「Max 仅支持文生/图生」 |
| `pricing/overview.md` | 四档齐全：H3 / Highspeed / Lite / Max，全支持参考生 | 与 FAQ 冲突（见 §3） |
| `guides/video-generation.md` | **只写 `MiniMax-H3` 一档** | 精确计数：`H3-Max` 0 次、`H3-Lite` 0 次；同一页 create API 里 `H3-Max` 7 次 |

---

## 三、官方文档自己打架的三处（引用前必须知道）

| # | 冲突点 | A 说法 | B 说法 | 位置 |
|---|---|---|---|---|
| 1 | **H3-Max 支不支持参考视频** | 「支持多模态参考生视频（参考图/参考视频/参考音频）」 | 「仅支持文生 / 图生（首帧、尾帧）」 | create 页 vs FAQ 模型表 |
| 2 | **Lite / Highspeed 在不在售** | 定价页在售、create 枚举里有、实际调用成功 | 可用模型表里完全没有这两档 | pricing vs FAQ |
| 3 | **H3-Max 有没有 `extra`** | create 页有 `extra.prompt_expansion_mode`（仅 Max） | guides/video-generation 11-02 版已删掉 Max 整段 | create vs guide |

🩸 判读规则：**以 create API 页 + OpenAPI JSON 为准**（机器可读、随接口发版），
FAQ / 发布日志是人工维护的说明页，明显滞后。

---

## 四、模型四档（官方口径）

| 模型 | 官方定位 | 分辨率 | 时长 | 参考生 | `extra` |
|---|---|---|---|---|---|
| `MiniMax-H3` | 高品质创作（= 论文里的 H3-Base） | 768P / 2K | 4–15s | 图/视频/音频 | — |
| `MiniMax-H3-Highspeed` | 兼顾质量与速度 | 768P（+480P） | 4–15s | 图/视频/音频 | — |
| `MiniMax-H3-Lite` | 低成本、创意尝试/批量 | 480P / 768P | 4–15s | 图/视频/音频 | — |
| `MiniMax-H3-Max` | 极速生成（fal 后训练版） | 480P / 768P | 5–15s | 官方两份文档说法冲突 | `prompt_expansion_mode` |

**上线时间**：H3 = 2026-07-31；Lite / Highspeed 在 2026-10-22～10-28 之间出现在文档里（不到一周，
没有任何发布说明、没有进 FAQ 模型表、没有专属 skill）；Max 官方日志无记录（媒体报为 fal 8 月底后训练版）。

---

## 五、H3 系统三件套（官方模型卡）

```
输入（文本 / 图片 / 视频 / 音频）
        │
        ▼
┌───────────────────────┐
│ H3-Context-IR         │  「理解素材之间、素材与目标结果之间的关系，
│ （托管改写器，只出词）│    转成 H3 能直接读的结构化表示」
└───────────────────────┘  官方：**critical to the quality of the final output**
        │ 六段英文
        ▼
┌───────────────────────┐
│ H3-Base（768P）       │  按 IR 的输出生成音视频
└───────────────────────┘
        │ 768P 成片 + 原始上下文
        ▼
┌───────────────────────┐
│ H3-Regenerate-2K      │  回到 2K
└───────────────────────┘
```

- IR 的 `model` **只能是 `MiniMax-H3`**（枚举唯一值）→ **没有"Lite 版改写器"**。
- 官方三个脚本把它们串起来：`h3-context-ir.sh` → `h3-base.sh` → `h3-regenerate-2k.sh`。

---

## 六、提示词规范（两份指南 + 一本手册）

### 6.1 `base-en.txt`（T2VA / I2VA / FL2VA / L2VA）

```
最终提示词
├── 第一段：图片对齐指令（I2VA / FL2VA / L2VA 才有）
│   └── I2VA 固定句：For the target video, at 0.00 seconds ..., <Picture 1> (from [Shot 1]) is fully referenced.
└── 第二段：三个核心字段
    ├── integrated_multimodal_description   ← 主正文，按时间轴写
    ├── overall_soundscape                  ← 环境声/动作声/非语言人声
    └── non_diegetic_music                  ← 只有观众听得到的配乐
```

另有：镜头切分、运镜三维度（类型+幅度+速度）、说话人 `(S1)`、台词 `<d>`、画外音、屏上文字。

### 6.2 `ref-en.txt`（Ref2VA 六段式，IR 的产出格式）

```
subject_definitions   ← 定义 <Subject N> / <Picture N> / <Video N> / <Audio N>
summary               ← [任务类型] + 一句话
retention_analysis    ← fully_preserved / partially_preserved / attribute_transfer / weak_reference
detailed_description  ← 主体正文（生成任务 350–500 英文词；编辑任务随复杂度）
overall_soundscape
non_diegetic_music
```

任务类型词表：`keyframe completion` / `reference generation` / `video editing` /
`video continuation` / `audio reuse` / `audio reference`（可 ` + ` 组合）。
编辑类 summary 必须以 `The target video is an edited version of <Video 1>.` 开头。

### 6.3 飞书手册（写给人看的中文版）

```
完整提示词 = 参考素材说明 + 核心创意 + 画面过程说明
├── 参考素材说明：每个素材编号 + 用途（官方用途表：人物参考/物体参考/场景参考/
│   关键帧/音色参考/故事版/风格参考/构图参考/音频复用/动作参考/运镜参考/
│   ★视频编辑（对视频某个内容进行增删改））
│   └─ 「如果素材中有非常想要保持的特征，建议明确写出来」
├── 核心创意：一句话锁 主体 / 地点 / 事件 / 题材风格（+运镜/切镜）
└── 画面过程说明：按时间轴分段，每段写 景别+内容+运镜+动作+台词+音效
```

### 6.4 换人怎么写 —— 官方样例全在这里（2026-11-03 补）

> 🩸 这一节是为上一轮的错误补的：当时只查 `ref-en.txt`（341 行）就下"官方没有替换示例"的结论。
> 实际官方有 **6 条**，全在手册里。**换人这件事，官方走的是「手写入口」那套，不是六段式。**

**（a）`manual-2026-10-28.md:207-213` §3.1 角色与物体编辑**

| 行 | 官方原句（逐字） |
|---|---|
| `:211` | `把视频中的猫换成狗` |
| `:212` | `画面左边增加一个穿着相同团队制服的人，动作与旁人保持一致` |
| `:213` | `视频1中最后面的小孩换成 图1中的金毛狗， 视频1中最左边小孩穿的卡其色外套改成图2中的牛仔外套` |

**（b）`manual-2026-10-28.md:185-192` §2.2 角色、动作与镜头参考**

| 行 | 官方原句（逐字） |
|---|---|
| `:192` | `参考视频1进行动作模仿。固定机位全景镜头，正视频中三个穿西装的男人替换为三只高度写实的水豚。水豚必须严格遵循原视频的运动轨迹：依次迅速趴到地板上，然后最左边的水豚跳到中间位置…保持原有的固定机位不变。确保水豚的毛发质感和光影与环境融合` |
| `:189` | `图1的人物动作、表情与表演节奏严格参考输入视频1` + 一段自然语言动作描述 |
| `:190` | `人物参考视频1的动作，表演街舞，人物参考图1 图2` |

**（c）能力声明（官方自己承认支持换人）**

- `:201` `H3支持多种维度的编辑与修改。角色替换、动作参考、背景替换、背景特效、台词替换与氛围感理解`
- `:203` `角色与物体编辑： 替换、删除或增加人物与物体，灵活调整画面主体`
- `:248` 素材用途表里明列 `视频编辑（对视频某个内容进行增删改）` 和 `人物参考（锁定脸/形象）`

**（d）这几条长什么样（结构归纳，不是官方原文）**

```
@/图N 的角色声明  +  一句"把 X 换成 Y"  +  要保住的维度（轨迹/机位/光影/表情）
```

`:192` 是最贴近我们复刻场景的一条：**多人替换 + 明确保住轨迹与机位 + 明确保住光影融合**，
完全用自然语言，没有 `subject_definitions`、没有 `retention_analysis`。

**（e）六段式那边有什么**

`ref-en.txt:165-168` 只有一个标记名是为换人设计的：

| 标记 | 官方定义（`ref-en:167`） |
|---|---|
| `attribute_transfer` | `Referenced characteristics are transferred to a different identifiable target subject` |

**只有一个标记名 + 没有任何完整换人段落。** 拿它做换人 = 我照着一个词推整段，这就是
26 次出不来生产的那条路的起点。

### 6.5 三条体裁，各管各的（别互相搬）

| 体裁 | 官方格式 | 谁在用 | 换人样例 |
|---|---|---|---|
| **A. 用户手写入口**（飞书手册） | `参考素材说明 + 核心创意 + 画面过程说明`（`:244`），标 `@图片N/@视频1` | 人直接提交；**我们复刻要走的这条** | ✅ **6 条**（6.4） |
| **B. Ref2VA 六段式**（`ref-en.txt`） | `subject_definitions` … `<Subject N>/<Picture N>` | 官方改写器 Context-IR 的输出格式 | ❌ 0 条 |
| **C. 三字段**（`base-en.txt`） | `integrated_multimodal_description` + 两句声音 | T2VA / I2VA / FL2VA / L2VA | ❌ 不适用 |

🩸 三条的**内容层要求**（台词长短、运镜词表、画外音写法）可以互相参考；
**格式与结构不能互相搬**（`official/docs/README.md`「引用边界」已写死这条）。

---

## 七、我方实现 ↔ 官方出处（对得上的一张表）

| 我方位置 | 干的什么 | 官方出处 |
|---|---|---|
| **`models/h3_compile.handwrite()`** | **机械拼「【参考素材说明】+ 正文」**（换人 / 换装 / 换产品 / 换场景 / 风格 / 边界续接） | `h3-manual:244`（三段公式）、`:248`（素材用途表）、`:192` / `:213`（换人样例）、`:234`（换产品）、`:221`（换场景）、`:266`（首帧） |
| **`scripts/ruler_h3_handwrite.py`** | 手写入口的尺子（探针 / 校准 / 扫描 / 穷举），**只认手册的标法** | `h3-manual:244` / `:248` / `:213` / `:41` |
| `minimax.context_ir()` | 调 IR：text → video → image → audio（**提示词优化线在用，复刻不走这条路**） | `api-ir` content/role 段 |
| ~~`h3_ir.instruction()`~~ **已归档** | 按「参考素材说明 + 核心创意 + 画面过程说明」写交给 IR 的文字 | `h3-manual:242-251` |
| ~~`h3_ir.prompt_for()`~~ **已归档** | 按输入指纹缓存 IR 产出，命中不花钱 | 自建（无官方对应） |
| `minimax.reference_video()` | 出片请求：text + reference_video + reference_image + reference_audio | `api-create` content 段 |
| `model_specs` "h3-max".request_extra | `prompt_expansion_mode: disabled` | `api-create` extra 段（仅 Max） |
| `identity.check()` | SFace 换脸核对（0.363 阈值） | **官方没有这个量具**，纯自建 |

---

## 八、实测数据（2026-11-02，17 次 H3-Lite 出片，本地 SFace 全跑）

| 时长 | 次数 | 换上 | 备注 |
|---|---|---|---|
| 4.633s | 9 | 2 | 4506 字 editing 版成功；2431–4888 字的失败 |
| 5.88s | 2 | **2** | 提示词最短（2322 / 2834 字），p90 0.646 / 0.511 |
| 9.233s | 1 | 0（H3 段） | p90 0.378 来自最后 1.4s 静帧重绘段 |
| 10.1s | 1 | 0 | p90 0.265 |
| 10.101s | 1 | 0 | p90 0.067 |
| 14.7s | 1 | 0 | p90 0.203 |
| 15.0s | 2 | 0 | p90 0.092 / 0.069 |

→ **≥9 秒的 6 次，H3 生成段一次都没换上**；换上的 4 次全在 4.6–5.9 秒。
→ IR 判 `video editing` 还是 `reference generation` **不决定成败**；提示词越长越不利。

---

## 九、还缺什么（唯一未覆盖项）

| 项目 | 状态 |
|---|---|
| 官方提示词指南（HF） | ✅ 已拿到，与本地同文件 |
| Lite / Highspeed 专属说明 | ❌ **官方不存在**（没有发布日志、没进 FAQ、没有 skill） |
| Max 的参考生能力 | ⚠️ 官方两份文档冲突，需要实测才能定 |
| 官方 H3-Base 768P 全套跑一次 | ⏳ 未跑（要花钱，等主人点） |

---

*核验方法留档：HF 域名本机不通，改走 `https://hf-mirror.com/MiniMaxAI/MiniMax-H3/raw/main/<path>`；
GitHub 走 `raw.githubusercontent.com`；平台文档走 `<url>.md` 直链；飞书走 `lark-cli docs +fetch --as bot`。*
