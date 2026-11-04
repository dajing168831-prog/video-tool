# H3 官方资料全量索引（34 个源文件 / 25,488 行）

> 📖 **要看"官方怎么写的"而不是"官方有什么"**：[H3-CASES-BREAKDOWN.md](H3-CASES-BREAKDOWN.md)
> —— 手册 2.1–3.4 的 **19 条案例逐条拆解** + `§2` 两条完整范例（`:284`/`:285`）+ 第四节规则表。
> 🩸 抄句式前先看那条范例属于**创作**还是**编辑**任务（2026-11-04 付过一次代价，见台账 §46）。

> 🗺️ **先看地图再看表**：[H3-SOURCES-MINDMAP.md](H3-SOURCES-MINDMAP.md)（各源新旧状态 / 官方自相矛盾 /
> HuggingFace 那份 Prompting Guidance 已于 2026-11-02 经 `hf-mirror.com` 取到，= 本表里的 `ref-en` + `base-en`，逐字节相同）。

> 建表：2026-11-02（第一版只索引了 skill 包 30 文件 / 6504 行）。
> **2026-11-02 主人追问「够全量了没」→ 全量补齐并重读**：源目录 `D:/tmp/official/h3/` 共
> **34 个文件 / 25,488 行**（含 `MANIFEST.json`），工程内 `backend/data/official/h3/`
> 现在 **67 个文件 / 15,791 行**（含 8 个 skill 的 `meta.yaml`、中文版）。
> 该拷的 **30/30 逐文件 sha256 一致**；未拷的 4 个已在下面「排除」点名并写明理由。
> 建这张表的起因：两天里每次改 H3 都要从头翻一遍官方资料，每次只读到一段就下结论，
> 报告里还时不时冒出"没看见的细节"。表建好之后**改成先查表**，表里没有 = 先补表再动手。
>
> **规则（写死）**
> 1. 每行必须带 `文件:行号`，指不到出处的不许写。
> 2. 别把「官方没写」当成「官方禁止」——§8 专门记"官方沉默"的地方。
> 3. **8 个风格 skill 是"体裁工作流"**，不是 API 规格。只在做那个体裁时用，
>    **不许套到「复刻/换人」上**（同一套数值换个体裁就等于没依据）。
> 4. **串味已审计**（§13）：`platform-docs.txt` 是全平台大杂烩，**没进工程、禁止引用**；
>    其余文件里出现的其他型号词都是别名或案例文件名，不是规则。
> 5. **官方会改口径**（§14）：`guides/video-generation` 11-02 已删掉 H3-Max 段、
>    `create` 页 Highspeed 新增 480P。引用前先看抓取日期。

**短名约定**（本表所有引用都按这张表展开；根目录 = `backend/data/official/h3/`）

| 本表写法 | 实际文件 | 行数 |
|---|---|---|
| `SKILL.md` | `SKILL.md`（根目录那份） | 40 |
| `base-en:N` | `base-en.txt` | 222 |
| `ref-en:N` | `ref-en.txt` | 341 |
| `README.md` | `skills/README.md` | 117 |
| `skills/<目录>/SKILL.md:N` | 对应风格包里那份（**必须带目录**，8 个包同名） | — |
| `api-create:N` | `pull-2026-11-02/api_v2-create.md` | 581 |
| `api-ir:N` | `pull-2026-11-02/api_v2-h3-context-ir.md` | 531 |
| `api-query:N` | `pull-2026-11-02/api_v2-query.md` | 434 |
| `api-list:N` | `pull-2026-11-02/api_v2-list.md` | 392 |
| `api-delete:N` | `pull-2026-11-02/api_v2-delete.md` | 185 |
| `api-regen:N` | `pull-2026-11-02/api_v2-regeneration.md` | 516 |
| `openapi:N` | `pull-2026-11-02/openapi_v2-video-generation.json` | 1640 |
| `api-error:N` | `pull-2026-11-02/api_errorcode.md`（官方错误码总表） | 61 |
| `guide-gen:N` | `pull-2026-11-02/guides_video-generation.md` | 270 |
| `guide-prompt:N` | `pull-2026-11-02/guides_video-prompt.md` | 265 |
| `guide-local:N` | `pull-2026-11-02/guides_local-deploy-h3.md` | 484 |
| `guide-local-all:N` | `pull-2026-11-02/guides_local-deploy.md`（**混合产品线**） | 57 |
| `llms:N` | `pull-2026-11-02/llms.txt`（全站目录） | 158 |
| `manual:N` | `manual-2026-10-28.md`（中文手册 · 飞书 wiki 版） | 297 |
| `manual-full:N` | `official/docs/official_manual_h3_full.txt`（同手册 · 官网版） | 865 |
| `manual-ssr:N` | `official/docs/official_manual_h3_p1-ssr.md`（手册第一页 SSR 结构） | 270 |
| `card:N` | `model-card-2026-10-28.md`（官方模型卡 / README） | 452 |
| `models:N` | `api-models-2026-10-28.md`（10-28 档位摘录，**已过时**，见 §14） | 42 |
| `site-index:N` | `official/docs/official_llms-index.txt`（10-26 全站索引，**已过时**） | 173 |
| `ex-lamb:N` | `official/11f12610.txt`（官方完整 Ref2VA 示例 · **口型重做 + 配音，不是换人**） | 24 |
| `ex-coffee:N` | `official/dfe52602.txt`（官方完整 Ref2VA 示例 · 多图多视频） | 28 |

---

## 0. 覆盖清单

### A 组：写作规则（官方 skill 包，30 个文件 / 6504 行）

| # | 文件 | 行数 | 性质 | 读法 |
|---|---|---|---|---|
| 1 | `SKILL.md` | 40 | 提示词 skill 入口（五种模式的分流） | 全读，见 §1 |
| 2 | `base-en.txt` | 222 | **正本**：T2VA/I2VA/FL2VA/L2VA 提示词规格 | 全读，见 §2 |
| 3 | `ref-en.txt` | 341 | **正本**：Ref2VA（全能参考）六段式规格 | 全读，见 §3 |
| 4 | `skills/README.md` | 117 | 技能包目录（1 提示词 + 8 风格） | 全读，见 §4 |
| 5 | `skills/h3-prompt-writing/SKILL.md` | 40 | **副本**（与 #1 md5 相同 `c7567f9a`） | 不重复 |
| 6 | `skills/h3-prompt-writing/references/base-en.txt` | 222 | **副本**（md5 同 #2 `f63d793a`） | 不重复 |
| 7 | `skills/h3-prompt-writing/references/ref-en.txt` | 341 | **副本**（md5 同 #3 `18415f88`） | 不重复 |
| 8 | `3d-animation-short-generator/SKILL.md` | 249 | 风格工作流 | 全读，见 §5.1 |
| 9 | `3d-animation-short-generator/SKILL.cn.md` | 615 | **中文版，内容同 #8**（把 STEP 7 的子节提成了标题） | 全读核对 |
| 10 | `3d-.../references/shot-table-spec.md` | 75 | 六列镜头表 + 自检门 | 全读，见 §5.1 |
| 11 | `3d-.../references/storyboard-guidelines.md` | 185 | 文本分镜/铅笔分镜 | 全读 |
| 12 | `3d-.../references/model-selection.md` | 49 | 选模型/选分辨率/prompt 前缀 | 全读 |
| 13 | `3d-.../references/fallback-policy.md` | 52 | 失败回退阶梯 | 全读 |
| 14 | `3d-.../references/qc-checklist.md` | 99 | 拼接/复盘/资产纪律 | 全读 |
| 15 | `brand-promo-video-generator/SKILL.md` | 189 | 风格工作流 | 全读，见 §5.2 |
| 16 | `brand-promo-video-generator/SKILL.cn.md` | 178 | 中文版，**少一节 `Tool Coverage Rule`**（其余逐节对应） | 已核对 |
| 17 | `co-op-game-intro-generator/SKILL.md` | 54 | 风格工作流 | 全读，见 §5.3 |
| 18 | `co-op-.../SKILL.cn.md` | 44 | 中文版，**少一节 `Required References`** | 已核对 |
| 19 | `co-op-.../references/h3-confirmation-image-template.md` | 388 | 确认图模板 | 全读，见 §5.3 |
| 20 | `co-op-.../references/h3-video-prompt-template.md` | 133 | 视频 prompt 模板 | 全读 |
| 21 | `handdrawn-live-video-generator/SKILL.md` | 87 | 风格工作流 | 全读，见 §5.4 |
| 22 | `handdrawn-.../SKILL.cn.md` | 86 | 中文版，逐节对应 | 已核对 |
| 23 | `minimalist-product-ad-generator/SKILL.md` | 398 | 风格工作流 | 全读，见 §5.5 |
| 24 | `minimalist-.../SKILL.cn.md` | 397 | 中文版，逐节对应 | 已核对 |
| 25 | `music-video-subtitle-generator/SKILL.md` | 205 | 风格工作流 | 全读，见 §5.6 |
| 26 | `music-video-.../SKILL.cn.md` | 213 | 中文版，逐节对应 | 已核对 |
| 27 | `paper-collage-explainer-generator/SKILL.md` | 273 | 风格工作流 | 全读，见 §5.7 |
| 28 | `paper-collage-.../SKILL.cn.md` | 271 | 中文版，逐节对应 | 已核对 |
| 29 | `papercraft-stop-motion-explainer/SKILL.md` | 471 | 风格工作流 | 全读，见 §5.8 |
| 30 | `papercraft-.../SKILL.cn.md` | 470 | 中文版，逐节对应 | 已核对 |

**去重后真正要记的正文 = 19 个文件 / 3627 行**（其余 12 个是副本或翻译）。

### B 组：API 规格（2026-11-02 新抓，11 个文件 / 4,982 行）

这组是**接口能不能发出去**的依据（参数、上限、错误码），和 A 组"提示词怎么写"是两回事。

| # | 文件 | 行数 | 性质 | 读法 |
|---|---|---|---|---|
| 31 | `pull-2026-11-02/api_v2-create.md` | 581 | **创建视频任务**全文（含 OpenAPI 规格） | 见 §9.1 |
| 32 | `pull-2026-11-02/api_v2-h3-context-ir.md` | 531 | **官方提示词改写器**（我们正在用） | 见 §9.2 |
| 33 | `pull-2026-11-02/api_v2-query.md` | 434 | 查询单个任务（7 天窗口） | 见 §9.3 |
| 34 | `pull-2026-11-02/api_v2-list.md` | 392 | 分页列任务（可过滤） | 见 §9.3 |
| 35 | `pull-2026-11-02/api_v2-delete.md` | 185 | 取消/删除任务（**通用**，正文不出现 H3） | 见 §9.3 |
| 36 | `pull-2026-11-02/api_v2-regeneration.md` | 516 | 768P → 2K 再生成（我们**没做**） | 见 §9.4 |
| 37 | `pull-2026-11-02/openapi_v2-video-generation.json` | 1640 | **机器可读全量规格**（6 个端点） | 见 §9.5 |
| 38 | `api-create-2026-10-28.md` | 580 | 10-28 快照（**已被 #31 取代**，留作比对） | 见 §14 |
| 39 | `api-models-2026-10-28.md` | 42 | 10-28 档位摘录（**已过时**） | 见 §14 |
| 40 | `official/index.json` | 20 | 两份官方示例的 sha8 / 任务类型索引 | — |
| +1 | `pull-2026-11-02/api_errorcode.md` | 61 | **官方《错误码查询》总表**（1000/1024/1026/2013…） | 见 §9.6（**这是错误码的唯一权威页**，别再拿 HTTP 示例反推） |

### C 组：中文手册 + 模型卡（4 个文件 / 1,883 行）

| # | 文件 | 行数 | 性质 | 读法 |
|---|---|---|---|---|
| 41 | `manual-2026-10-28.md` | 297 | **中文《使用手册》**：功能表 / **亮点能力与示例（第 2 章多模态理解、第 3 章精准编辑）** / 写法公式 / 拆镜 / 6 条坑 / 多语种样例 | 见 §10（**§10.1 能力清单必读**） |
| 42 | `official/docs/official_manual_h3_full.txt` | 864 | 同一手册的**官网版**（与 #41 已逐条核对一致） | 见 §10 |
| 43 | `official/docs/official_manual_h3_p1-ssr.md` | 270 | 手册**第一页** SSR 结构化还原（补表格与素材名） | 见 §10 |
| 44 | `model-card-2026-10-28.md` | 452 | **官方模型卡**：系统三模块 / 规格表 / 本地部署 / 2K 工作流 | 见 §11 |

### D 组：站点指南与两份官方示例（6 个文件 / 1,126 行）

| # | 文件 | 行数 | 性质 | 读法 |
|---|---|---|---|---|
| 45 | `pull-2026-11-02/guides_video-generation.md` | 270 | 视频生成指南（规格表 + 四种模式代码） | 见 §12 |
| 46 | `pull-2026-11-02/guides_video-prompt.md` | 265 | H3 亮点功能示例（六组中文提示词 + 成片） | 见 §12 |
| 47 | `pull-2026-11-02/guides_local-deploy-h3.md` | 484 | 本地部署（ComfyUI / SGLang）；**不适用我们的 API 产品** | 见 §12 |
| 48 | `pull-2026-11-02/guides_local-deploy.md` | 57 | **混合产品线**（M3/M2.7/Music/H3），只作定位 | 见 §12 |
| 49 | `official/11f12610.txt` | 23 | **官方完整 Ref2VA 示例**：口型重做 + 音色参考（🩸 **不是换人**，`<Subject 1>` 就是原片同一个人，标 `fully_preserved`） | 见 §12.4 |
| 50 | `official/dfe52602.txt` | 27 | **官方完整 Ref2VA 示例**：多图（场景/狗）+ 双视频 + 音色 | 见 §12.4 |

### 排除（拷贝时故意没进工程）

| 文件 | 行数 | 为什么排除 |
|---|---|---|
| `platform-docs.txt` | 15,185 | **全平台抓取合集**：开头是 Mintlify 自己的文档，正文混 Speech / Music / Image / abab 和其他视频型号。留在 `D:/tmp/official/h3/` 取证，**禁止当 H3 依据引用**（见 §13） |
| `h3-prompt-writing/`（3 个） | 603 | 与根目录 `SKILL.md` / `base-en` / `ref-en` **内容完全相同**（sha256 一致） |
| `llms.txt` / `official_llms-index.txt` | 158 / 173 | **全站目录**，含 M2.7/M3/Music/Speech 条目；只用来查"H3 还有哪页没抓"，不是规则 |

---

## 1. `SKILL.md`（40 行）—— 五种模式怎么分流

| 行 | 官方说什么 | 我们代码 |
|---|---|---|
| `SKILL.md:11` | 先判模式：T2VA / I2VA / FL2VA / L2VA / Ref2VA | `h3_convert_route.py`（按素材决定模式） |
| `SKILL.md:12-13` | 基础/关键帧模式读 `base-en.txt`；全能参考读 `ref-en.txt` | `h3_base*.py` / `h3_ref.py` |
| `SKILL.md:14` | **保留原样的字段名、段落顺序、标签、时间写法** | `h3_ref.py` E1、`h3_base.py` B1 |
| `SKILL.md:18-21` | 四模式各一句定义 | `h3_base.py` B5–B8 |
| `SKILL.md:23` | 三核心字段按 `base-en` 里的顺序 | `h3_base.py` B1 |
| `SKILL.md:27` | Ref2VA 六段顺序固定，标签跨段一致 | `h3_ref.py` E1 |
| `SKILL.md:33` | 正文英文；对白/歌词/画面文字保留原语言 | `h3_ref.py` E12 |
| `SKILL.md:34` | 每镜写：构图/主体/环境/动作/运镜/声音/参考内容出现的准确时点 | `h3_agent.py` 硬闸（逐镜写法） |
| `SKILL.md:35` | 禁止：剧情摘要、悬空标签、与时长对不上的时间 | `h3_agent.py` 闸 13 条 |
| `SKILL.md:37` | 描述总时长必须和请求时长一致（4–15 秒） | `h3_agent.py` / `video_edit` 分段 |
| `SKILL.md:39` | 少用 `cinematic`/`beautiful` 这类抽象词 | `h3_ref.py` E18 |

---

## 2. `base-en.txt`（222 行）—— 基础四模式规格

### 2.1 四种模式与指令行

| 行 | 官方说什么 | 我们代码 |
|---|---|---|
| `base-en:5-8` | T2VA / I2VA / FL2VA / L2VA 一句话定义 | `h3_base.py` B5–B8 |
| `base-en:14` | **T2VA 没有对齐指令行**，直接三核心字段 | B5 |
| `base-en:16-20` | I2VA 固定句：`For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.` | B6 |
| `base-en:22-26` | FL2VA 固定句（首帧 + 尾帧两个时点） | B7 |
| `base-en:28-32` | L2VA 固定句（只在尾帧时点） | B8 |
| `base-en:34` | 指令行必须是**第一行**，后面跟一个空行 | B9 |

### 2.2 三核心字段

| 行 | 官方说什么 | 我们代码 |
|---|---|---|
| `base-en:39-43` | `integrated_multimodal_description` / `overall_soundscape` / `non_diegetic_music` 三段顺序 | B1 |
| `base-en:46` | 第一段管：画面/动作/镜头/说话人/台词/演唱/同期声 | `h3_base_compile.py` |
| `base-en:47` | 第二段管：环境音/物理动作声/非语言人声 | B24 |
| `base-en:48` | 第三段管：只有观众能听见的配乐 | B25 |

### 2.3 关键帧三模式的写法

| 行 | 官方说什么 |
|---|---|
| `base-en:54` | I2VA：`<Picture 1>` 就是 0.00 秒的真实首帧，属于 `[Shot 1]`；身份/服装/颜色/关键物/空间关系必须一致 |
| `base-en:56` | I2VA 推荐结构：**首帧锚定 → 动作起势 → 持续发展 → 结果/反应** |
| `base-en:60-62` | FL2VA：P1 是开头、P2 是结尾；**一般只做单镜**，让模型连续插值；非明确要求不要多镜 |
| `base-en:64` | FL2VA 推荐结构：首帧状态 → 中间变化 → 差异收窄 → 尾帧状态 |
| `base-en:68` | L2VA：`<Picture 1>` 是**最后一帧**，属于最后一个 `[Shot N]`，不天然属于 Shot 1 |
| `base-en:70` | L2VA 推荐结构：合理前态 → 明确动作路径 → 末镜收敛 → 落在尾帧 |

### 2.4 正文怎么写

| 行 | 官方说什么 | 我们代码 |
|---|---|---|
| `base-en:76-78` | 每个细节都要**看得见或听得见**；`[Shot 1]` 开头先给整体风格与初始构图；风格从参考图来（关键帧任务）或从用户文字来（T2VA） | B15（风格写在 `[Shot 1]` 之内） |
| `base-en:86` | `[Shot 1]` **不加时间戳**；后续镜 `[Shot N] At MM:SS.mmm`，切点严格递增且在时长内 | B10、E5 |
| `base-en:92` | 普通切镜**只用五种**：`the camera cuts to` / `the shot cuts to` / `the shot transitions to` / `the shot changes to` / `the shot switches to`；只有用户明确要求才用叠化/淡入淡出/划像 | B11 |
| `base-en:96` | 运镜三维：**类型 + 幅度 + 速度**；中等幅度/常速可省略 | B13 |
| `base-en:98-115` | 运镜**闭集**：Zoom In/Out、Push In/Pull Out、Pan、Truck、Tilt、Pedestal、Arc Shot、Tracking Shot、Static Shot、Shake Slightly/Strongly、POV、Roll；幅度只用 `with small/large amplitude`；速度只用 `at slow/fast speed` | `h3_base_compile.py:91-97`（词表）、B13 |
| `base-en:117-123` | 运镜要写成**句子里的动作**，不许堆在句尾当标签 | B14、B28 |
| `base-en:127` | 发声者用 `(S1)(S2)`；多人齐声 `(S1,S2)`；同一人跨镜同号；**不发声的角色不给号** | B17 |
| `base-en:129` | `<d>` **外面**写识别语/编号/动作/语气；`<d>` **里面**只放语言标签 + 用户原词；原词的每个字和标点都要保留，不许翻译改写 | B19 |
| `base-en:136-140` | 画外音必须用原句 `says in an off-screen voiceover`，并在每个 `<d>` 后写"嘴唇保持闭合" | B21 |
| `base-en:142` | 台词跨切点用 `<scenetrans>` 并写明音频跨切继续；说到片尾被截断用 `<cutoff>` | B22 |
| `base-en:146` | 画面里真实可见的文字放**英文双引号**里，原样保留不翻译 | `h3_common` |
| `base-en:154` | soundscape：1–4 句，一整段；只写环境/物理/非语言人声；台词/演唱/同期音乐不重复；**只有用户明确要全片无声才写 `N/A`** | B24、B26 |
| `base-en:162` | music：1–3 句，写乐器/速度/节奏/动态；**不用抽象情绪词、不解释配乐作用**；角色能听见的音乐属于同期声 | B25 |
| `base-en:168-222` | 四个完整案例（T2VA/I2VA/FL2VA/L2VA） | `h3_base_compile` 的骨架来源 |

---

## 3. `ref-en.txt`（341 行）—— Ref2VA 六段式（**我们复刻/换人用的就是这套**）

### 3.1 总则

| 行 | 官方说什么 | 我们代码 |
|---|---|---|
| `ref-en:5` | 六段**全部英文**；只有 `<d>` 里的台词/歌词和画面文字保留原语言 | E12 |
| `ref-en:7` | `detailed_description` 要**尽可能详细**：每镜写清构图/主体外观与位置/环境与光/动作与状态变化/运镜/当下声音/参考内容真正出现或生效的时点；**不许写成剧情摘要或参考关系清单** | `h3_agent.py` 硬闸 |
| `ref-en:9` | 镜头/运镜/说话人/普通声音的**基础格式与 base 共用** | `h3_common.py` |
| `ref-en:13-22` | 六段顺序：`subject_definitions` → `summary` → `retention_analysis` → `detailed_description` → `overall_soundscape` → `non_diegetic_music` | E1 |

### 3.2 四类标签

| 行 | 官方说什么 | 我们代码 |
|---|---|---|
| `ref-en:28-33` | 四种标签：`<Subject N>`（可复用/可改的可见内容）、`<Picture N>`（具体帧/构图锚）、`<Video N>`（整片关系：编辑源/续写起点/时间结构）、`<Audio N>`（被复制或参考的音频） | `h3_compile.py` |
| `ref-en:35` | **标签一旦分配，跨五段保持同一含义** | E8 |
| `ref-en:37` | `subject_definitions` 每个对象**单独一行**，写清"这个标号指什么、参考角色是什么、要跟住的要点"；**只用来指出处、后文不再单独分析的图/视频，写在别的条目里，不单开一行** | E9、`h3_compile.py:559` |
| `ref-en:39-48` | `<Subject N>` 管：人/动物/物体、场景环境、服装道具界面特效、风格动作表情姿态 | `h3_compile.py` |
| `ref-en:54-58` | 同一主体来自多个素材时，写清每个素材各出什么（例：外貌来自 P1、走姿来自 V1） | `h3_compile.py` |
| `ref-en:62` | 图**当帧用**（首帧/关键帧/尾帧/编辑关键帧/构图锚）才单独写 `<Picture N>` | E8 |
| `ref-en:65` | 写清它是哪一镜的第一帧 | `h3_agent.py` |
| `ref-en:68` | **图只用来定义人物/场景/服装/风格 → 不单独建 `<Picture N>` 行**，写进对应 `<Subject N>` 里 | `h3_compile.py:559/605` |
| `ref-en:72-74` | 图当分镜/镜头规划参考时，写明它对应哪几镜、提供什么规划信息 | `h3_compile.py` |
| `ref-en:78-86` | `<Video N>` 只管**整片关系**：编辑原片 / 从原片末尾续写 / 参考原片的运镜·剪辑·节奏·时间结构 | `h3_compile.py` |
| `ref-en:88` | 从参考视频里复用的"人/物/场景/动作/特效"仍然归 `<Subject N>`；`<Video N>` 不替代主体标签 | E8 |
| `ref-en:92-98` | `<Audio N>` 用于：整段或部分复制音频、参考 BGM 风格、参考音色与语气、用原音频的台词/歌词/音效、参考节拍连续性 | `h3_compile.py` |
| `ref-en:100-104` | 音频明显对应某个说话人时，定义里复用该说话人的 `(Sx)`；**编号来自目标片的全局说话顺序，不在音频定义里另起号** | E15 |
| `ref-en:106` | 一个音频承担多个角色时，用一句自然语言写清，不要拆子节 | — |
| `ref-en:110` | `<Video N>` 与 `<Audio N>` **各自独立编号**，不同号不影响它们来自同一素材 | `h3_compile.py` |
| `ref-en:112` | **参考视频本身有声音 ≠ 自动产生 `<Audio N>`** | `h3_compile.py`（口型只在真传音频时才写） |
| `ref-en:114-118` | 音频定义主要写角色，不必点名来自哪个视频；只有出处会混淆时才写 | — |

### 3.3 `summary`

| 行 | 官方说什么 | 我们代码 |
|---|---|---|
| `ref-en:123` | 一段短英文，**必须以方括号任务类型前缀开头** | E2 |
| `ref-en:134` | `keyframe completion`：图当首帧/关键帧/尾帧/编辑关键帧/具体帧锚 | `h3_compile.py` |
| `ref-en:135` | `reference generation`：素材只提供生成指导，不当具体帧、不当被编辑/续写的源片 | 同上 |
| `ref-en:136` | `video editing`：**直接修改现有源视频**；改图或两张静帧之间生成不算 | E3 |
| `ref-en:137` | `video continuation`：从已有源视频继续/延长/接续/过渡 | E3 |
| `ref-en:138` | `audio reuse`：同一音频信号整段或部分复用 | E3 |
| `ref-en:139` | `audio reference`：不直接复制，只参考风格/音色/内容/质感/节拍/连续性 | E3 |
| `ref-en:141` | 多类型用 ` + ` 连接，**同一类型不重复** | E2 |
| `ref-en:143` | **素材在场 ≠ 自动有对应任务类型**；参考视频只给运镜/剪辑/节奏 → 归 `reference generation` | — |
| `ref-en:145` | 编辑时原声还在就要加 `audio reuse`；续写不抄原音频则用 `audio reference` | E3 |
| `ref-en:147` | summary 只用已定义的标签，**不引入新标签** | E2 |
| `ref-en:149-153` | 编辑任务在这句之后用固定原句：`The target video is an edited version of <Video 1>.` | E4 |

### 3.4 `retention_analysis`

| 行 | 官方说什么 | 我们代码 |
|---|---|---|
| `ref-en:157` | **每个标签一行**，含义与 `subject_definitions` 一致 | E6 |
| `ref-en:165-168` | 可见内容的四个标记：`fully_preserved` / `partially_preserved` / `attribute_transfer` / `weak_reference` | E6 |
| `ref-en:173` | 主体条目写法：`<Subject 1> (appears in [Shot 1], [Shot 3]): fully_preserved - …` | `h3_ref.py` |
| `ref-en:179` | 图片条目：`<Picture 2> ([Shot 1] first frame): …` | 同上 |
| `ref-en:185` | 视频结构条目：`<Video 1> (cut and pacing structure): weak_reference - …` | 同上 |
| `ref-en:194-197` | 音频四个标记：`fully_copy` / `partially_copy` / `reference` / `weak_reference` | E6 |
| `ref-en:207` | 目标片里**新增的动作/背景/剧情不算保真度下降** | E6 注释 |
| `ref-en:278` | **`retention_analysis` 里不许写 `(Sx)`** | E7 |

### 3.5 `detailed_description`（正文）

| 行 | 官方说什么 | 我们代码 |
|---|---|---|
| `ref-en:217` | 正文英文；对白歌词画面文字保留原语言 | E12 |
| `ref-en:218` | `[Shot 1]` 无时间戳；后续 `[Shot N] At MM:SS.mmm, …` | E5 |
| `ref-en:219` | 运镜写成句中动作，需要时带类型/幅度/速度 | B13/B14 |
| `ref-en:220` | 发声源给 `(S1)(S2)`；台词写 `<d>[Language] …</d>` | E10 |
| `ref-en:221` | 用 `<scenetrans>` / `<cutoff>` 处理跨切对白与片尾截断 | B22 |
| `ref-en:230` | 与 base 的差异：**风格句写在 `[Shot 1]` 之前**（base 是写在 Shot 1 之内） | E13 |
| `ref-en:231` | 首现处插入对应标签，并在角色适用的地方继续用 | `h3_agent.py` |
| `ref-en:232` | 音频关系写进对应镜头或音频阶段，并说明是复制还是参考 | `h3_compile.py` |
| `ref-en:242` | **生成任务正文一般 350–500 英文词**；**编辑任务的描述长度跟着原片复杂度走，不受这个区间约束** | `h3_agent.py:95`（明确不套用） |
| `ref-en:246` | 重要 `<Subject N>` 首次清晰出现时，写它被参考的特征、画面位置、当下动作；后续镜头**继续用同一标签、不再重新定义** | `h3_agent.py` |
| `ref-en:250-254` | 帧锚点的自然写法：`the shot begins from <Picture 1>` / `…keyframe corresponds to…` / `…ends on…` | `h3_compile.py` |
| `ref-en:256` | 编辑/续写时在恰当位置自然引用 `<Video N>`；音频关系在对应镜头引用 `<Audio N>` | `h3_compile.py` |
| `ref-en:263` | 被参考的主体亲自说话时，写法是 `<Subject 2> (S1) turns toward … and says, <d>…</d>` | E15 |
| `ref-en:266` | `<Subject N>` 管"是谁"，`(Sx)` 管"谁在发声"；离屏同一人保持同样写法并标 off-screen | E15 |
| `ref-en:268` | 声音只是被复用 BGM/整轨里的一个提示、没有具体人发出 → 用 `<Audio N>` 当发声源，**不要另编一个 `(Sx)`** | E15 |
| `ref-en:274` | 直接复用参考音频的台词/旁白/歌词时：**逐字保留原词与原语言**；听不清写 `[unclear]`；标点统一成 `, . ? !`，去掉重复波浪号/emoji/项目符号/装饰标点；完整陈述/疑问/感叹分别以 `. ? !` 收尾 | E11、E19 |
| `ref-en:276` | 只参考音色/节奏/情绪时，**不要把参考音频的台词搬进目标片** | E14 |
| `ref-en:278` | `(Sx)` 按目标片**实际发声顺序**分配，每次发声复用同一号；`retention_analysis` 不写 | E7 |

### 3.6 声音两段 + 完整示例

| 行 | 官方说什么 |
|---|---|
| `ref-en:284` | soundscape 只汇总全片环境/物理声；与具体镜头同步的台词和声音事件留在正文 |
| `ref-en:290-294` | music 写乐器/速度/动态发展 |
| `ref-en:296-300` | 参考音频用在哪一层就在哪一层写关系：环境/音效写进 soundscape，只有观众能听的配乐写进 music |
| `ref-en:303` | 台词和歌词**只写在正文的 `<d>` 里**，这两段不重复 |
| `ref-en:305-341` | 完整范例（咖啡店 + 萨摩耶），可当骨架 |

---

## 4. `skills/README.md`（117 行）—— 包结构

- `README.md:3` 包内共 **1 个提示词 skill + 8 个风格 skill**；风格 skill 都有中英双语。
- `README.md:11-22` 安装方式是 `npx skills add …`（**我们不用这套**，本地已有副本）。
- `README.md:26-33` `h3-prompt-writing` 就是 §1–§3 三份文件的入口。
- `README.md:35-113` 8 个风格 skill 各一段介绍（下面 §5 逐个索引）。

---

## 5. 八个风格 skill（**体裁工作流，不是 API 规格**）

> 🩸 这一节的内容**只在做该体裁时用**。拿"3D 动画要求单镜 ≤3 个主角"去卡"真人复刻换人"就是拿 A 体裁量 B。
> 对我们真正有用的是它们反复出现的**方法**（参考素材只捐什么、失败怎么升级、>15s 怎么拼），而不是它们的数值。

### 5.1 `3d-animation-short-generator`（3D 动画短片，249 行 + 5 份参考）

| 行 | 要点 | 对复刻有没有用 |
|---|---|---|
| `skills/3d-animation-short-generator/SKILL.md:12` | 核心流程：六列镜头表 → 自检门 → 文本分镜 → 选模型/分辨率 → 单镜出片 → 拼接 | 流程可借鉴，资产类型不同 |
| `skills/3d-animation-short-generator/SKILL.md:16-27` | 全局风格锁 + 负向约束（不许写实/塑料/僵硬） | 体裁专属 |
| `shot-table-spec.md:15` | 「连续性衔接」列要写清本镜如何承接上一镜的**结束画面/道具位置/眼神/姿态/声桥/情绪** | ✅ 通用：跨镜连续性字段 |
| `shot-table-spec.md:17-21` | 空间锚点四子字段：固定地标 / 人物位置 / **退场人物状态** / 光位基线 | ✅ 通用：换人后"人物去哪了"就是这个字段 |
| `shot-table-spec.md:23` | 每秒指令五要素：动作姿态表情 / 运镜 / 空间位置 / 音频线索 / 交接 | ✅ 通用 |
| `shot-table-spec.md:62` | **任何镜头不超过 15 秒** | ✅ 与 H3 API 15s 上限一致 |
| `shot-table-spec.md:63` | 单镜不超过 3 个"有动作或台词"的重要角色 | ⚠️ 体裁专属（3D 动画），**别套到复刻** |
| `shot-table-spec.md:61` | hook 密度：每 3 镜至少 1 个 reveal/reversal/callback | ⚠️ 体裁专属 |
| `storyboard-guidelines.md:21-40` | 每镜分镜字段（标题/hook/场景角色/空间锚点/连续性/双绑定/每面板四象限） | ✅ 骨架可借鉴 |
| `storyboard-guidelines.md:136-142` | 面板物理排布 3s→1×3、4s→2×2、6s→2×3 | 体裁专属 |
| `model-selection.md:11` | H3 强项：视觉包装/动效/文字 UI/多模态理解/性价比；**单片段最长 15s @2K**；原生双声道 | ✅ 选型依据 |
| `model-selection.md:45` | H3 的 prompt 前缀（包装/设计语言/双声道意图） | 体裁专属 |
| `fallback-policy.md:7-14` | **H3 失败升级阶梯**：①强化 prompt 引用锚点 ②缩短到 ≤6s 拆行 ③切 Seedance ④三次后停下来问人 | ✅ 方法通用 |
| `fallback-policy.md:34` | 片段与锚点漂移（门框落错边/人物从错边离场/光位翻转）→ 引用锚点重渲；仍漂移就换模型；**不许把修正版和未修正版混着拼** | ✅ 通用 |
| `qc-checklist.md:9-15` | 拼接：保持镜头顺序、BGM 压在对白下、**不许加字幕除非要求**、终片不许留分镜痕迹 | ✅ 通用 |

### 5.2 `brand-promo-video-generator`（品牌宣传片，189 行）

| 行 | 要点 | 对我们 |
|---|---|---|
| `skills/brand-promo-video-generator/SKILL.md:39-42` | 素材默认可用，**只有出现具体风险信号才追问授权**（水印/抓来的电商图/合规宣称） | ✅ 口径参考 |
| `skills/brand-promo-video-generator/SKILL.md:53` | 无法认证的标志性资产（logo/UI/吉祥物）→ 停下来要原始件，**不许生成替代品** | ✅ 红线同源 |
| `skills/brand-promo-video-generator/SKILL.md:73` | 不许用 logo 聚合站/搜索缩略图/粉丝重绘当身份来源 | ✅ |
| `skills/brand-promo-video-generator/SKILL.md:104` | 15s 片 5–8 个节拍；30s 片 8–12 个 | 体裁专属 |
| `skills/brand-promo-video-generator/SKILL.md:151` | 默认用**视频模型原生音频**（H3 `generate_audio=true`），不要在提示词外再单独生成一条配乐 | ✅ 与我们的音频口径一致 |
| `skills/brand-promo-video-generator/SKILL.md:155` | 不许重画 logo/包装/UI/吉祥物；生成素材只能做抽象动效/氛围 | ✅ |
| `skills/brand-promo-video-generator/SKILL.md:186` | 「好看但空洞」→ 补真实的交互/输出/证明 | 方法 |

### 5.3 `co-op-game-intro-generator`（双人游戏开场，54 行 + 2 份模板）

| 行 | 要点 | 对我们 |
|---|---|---|
| `skills/co-op-game-intro-generator/SKILL.md:24` | **参考图只捐身份锚点**（脸型轮廓/发型/眼镜/五官比例/特征）；**不捐写实质感、皮肤纹理、真实光线、画质、原图风格**；脸要重画成目标风格 | 🔥 **直接支撑我们 11-01 那条"参考图隔离"闸** |
| `h3-confirmation-image-template.md:86-88` | 同上，逐字：`It does not donate photographic realism, real skin texture, real-world lighting, camera quality, or the original image style.` | 🔥 同上（英文原文，可直接进 prompt） |
| `h3-confirmation-image-template.md:5-11` | **两套系统分离**：UI 框架（固定）vs 视觉风格（动态）；风格冲突时保留框架 | ✅ 分离思路通用 |
| `h3-video-prompt-template.md:10-22` | 优先级顺序：用户选的风格 > 确认图 > 角色身份参考 > 固定事件框架 | ✅ 权重写法 |
| `h3-video-prompt-template.md:42-46` | 身份锚点写死：脸/比例/发型/昵称对应；**禁止身份互换、脸互相融合、体型趋同** | ✅ 与我们的换人闸同向 |

### 5.4 `handdrawn-live-video-generator`（手绘发光融合，87 行）

| 行 | 要点 | 对我们 |
|---|---|---|
| `skills/handdrawn-live-video-generator/SKILL.md:13` | **提示词语言跟随用户输入的主导语言**（中文入→中文出） | ⚠️ 与 Ref2VA「正文必须英文」冲突 —— 属于不同路径，别混用 |
| `skills/handdrawn-live-video-generator/SKILL.md:11` | 输出结构固定：15s、16:9、0–3s 必须出现接触 | 体裁专属 |
| `skills/handdrawn-live-video-generator/SKILL.md:22` | 明确禁止项清单（3DCG/毛绒/平滑霓虹/恐怖怪物…） | 体裁专属 |

### 5.5 `minimalist-product-ad-generator`（极简产品广告，398 行）

| 行 | 要点 | 对我们 |
|---|---|---|
| `skills/minimalist-product-ad-generator/SKILL.md:56-59` | **不要做 4 宫格拼版锚图**（视频模型会把拼版画进成片），改成 3 张独立锚图 | 🔥 与我们「3×3 场景板必须切单格」同源 |
| `skills/minimalist-product-ad-generator/SKILL.md:71-73` | **产品本体颜色是硬约束**：风格化不等于把产品改成白/银 | ✅ 换产品时同理 |
| `skills/minimalist-product-ad-generator/SKILL.md:298-300` | **出片时不要把原产品图直接传给视频模型**，只用锚图 | ✅ 素材角色分离 |
| `skills/minimalist-product-ad-generator/SKILL.md:303` | 终片不许出现拼版/分屏/网格/分镜板 | ✅ |
| `skills/minimalist-product-ad-generator/SKILL.md:88-99` | 画面文字规则：3–5 个英文词、单行、两种颜色分前后半 | 体裁专属 |
| `skills/minimalist-product-ad-generator/SKILL.md:219` | 锚图必须是**独立完整的产品照**，不许网格/拼贴/分屏 | ✅ |

### 5.6 `music-video-subtitle-generator`（MV / 卡点字幕，205 行）

| 行 | 要点 | 对我们 |
|---|---|---|
| `skills/music-video-subtitle-generator/SKILL.md:34` | **超过单次生成上限（>15s）就自动走多镜拼接**：分镜拆解 + 头尾帧衔接 + 卡点硬切 + 全局主音轨对齐 | 🔥 长片拼接方法 |
| `skills/music-video-subtitle-generator/SKILL.md:63` | 30s → 拆 4–8 个 **2–5 秒**短镜 | ✅ 分段参数来源 |
| `skills/music-video-subtitle-generator/SKILL.md:95` | 同场景续接用上一镜尾帧当下一镜头帧；硬切则保持同一角色卡/服装/光位/同向运镜 | ✅ |
| `skills/music-video-subtitle-generator/SKILL.md:166-180` | 拼接五把锁：人声与口型 / 节拍 / 色调 / 运镜 / 文字动势 | ✅ 方法 |
| `skills/music-video-subtitle-generator/SKILL.md:191` | **角色卡 / 场景卡 / 文字卡三张卡互不串味**（`without cross-contamination`） | 🔥 与 11-01 的场景隔离闸同向 |
| `skills/music-video-subtitle-generator/SKILL.md:138` | 文字不许盖眼、不许盖主要表情、口型关键处避开嘴 | 体裁专属 |

### 5.7 `paper-collage-explainer-generator`（纸拼贴科普，273 行）

| 行 | 要点 | 对我们 |
|---|---|---|
| `skills/paper-collage-explainer-generator/SKILL.md:40-43` | 默认**只保留拼贴音效**，不加 BGM/旁白/字幕，除非用户要 | ✅ 默认口径参考 |
| `skills/paper-collage-explainer-generator/SKILL.md:47` | 画面里避免可读文字/数字/UI/字幕/水印/logo | ✅ |
| `skills/paper-collage-explainer-generator/SKILL.md:67` | 纸张质感控制："不许过于平整，也不许过度做旧/发黄" | 体裁专属 |
| `skills/paper-collage-explainer-generator/SKILL.md:201` | 运动写法：逐件出现 → 轻弹 → 压平 → 停顿 → 锁定 | 体裁专属 |

### 5.8 `papercraft-stop-motion-explainer`（纸艺定格科普，471 行）

| 行 | 要点 | 对我们 |
|---|---|---|
| `skills/papercraft-stop-motion-explainer/SKILL.md:18` | 长文档写画布，不在对话里堆 | 体裁专属 |
| `skills/papercraft-stop-motion-explainer/SKILL.md:83` | 关键信息缺失时**给合理默认值继续，不要停下来**（除非是硬约束） | ✅ 交互口径 |
| `skills/papercraft-stop-motion-explainer/SKILL.md:402` | 旁白时长与视频时长偏差 >20% → 问用户缩短/延长/接受 | ✅ 可复用判据 |
| `skills/papercraft-stop-motion-explainer/SKILL.md:409-430` | 负向提示块（平滑塑料 3D/写实/矢量…） | 体裁专属 |
| `skills/papercraft-stop-motion-explainer/SKILL.md:317` | 节奏：15s→4–6 镜(2–4s/镜)、30s→6–8 镜(3–5s/镜)、60s→8–12 镜(4–7s/镜) | ⚠️ 体裁专属数值，别当通用 |

---

## 6. 我们代码 → 官方依据 反查表

> 🔴 **口径（2026-11-03）**：**复刻换人走「手写入口」，不是 Ref2VA 六段式。**
> 官方换人样例 6 条全在 `manual:207-213` / `:185-192`，全是自然语言短句；
> `ref-en` 六段式里**一条换人样例都没有**（`ex-lamb` 是口型重做，不是换人，见 §12.4）。
> 故「换人怎么写」的出处**只有一个** = `manual`。

| 我们的模块 | 干什么 | 官方依据 | 状态 |
|---|---|---|---|
| **`app/services/models/h3_compile.py`** | **手写入口三段式编译器**（`handwrite()`）：素材用途 + 替换句 + 保有句 + 融合句 | `h3-manual:244` / `:248` / `:192` / `:213` / `:234` / `:221` / `:266` | ✅ **2026-11-03 换体裁完成**（原六段式版归档为 `_archive/h3_clone/h3_compile_ref2va.py`） |
| **`scripts/ruler_h3_handwrite.py`** | 手写入口尺子（H1–H6：结构 / 用途句 / 官方词 / 点名换人 / 不串别家 / ≤7000 字） | `h3-manual:244` / `:248` / `:213` / `:41` | ✅ |
| ~~`scripts/ruler_h3.py`~~ | ~~六段式尺子（E1–E23）~~ | `ref-en` 各段 | 🧊 **已归档** `_archive/h3_clone/ruler_h3_ref2va.py` |
| `app/services/models/h3_ref.py` | Ref2VA 六段式**判据本体**（E1–E23）；**只有提示词优化线（`/prompt/*`）在用** | 每条规则旁已标 `ref-en:<行>`（表在 `h3_ref.py:538-590`） | ✅ 提示词优化线，复刻不碰 |
| `app/services/models/h3_base.py` | 基础四模式判据（B1–B28） | `base-en` 行号见 `h3_base.py:407-430` | ✅ 创作线，**不动** |
| `app/services/models/h3_base_compile.py` | 基础模式编译器（运镜闭集 `:91-97`、切镜动词 `:105`） | `base-en:96-123` | ✅ 创作线，**不动** |
| `app/services/models/h3_common.py` | 两套模式共用工具（镜头/运镜/说话人/声音） | `ref-en:9` | ✅ |
| ~~`app/services/h3_agent.py`~~ | ~~agent 读官方 skill 现写逐段指令~~ | `ref-en` 各段 | 🧊 **已归档** `_archive/h3_clone/` |
| ~~`app/services/h3_ir.py`~~ | ~~出片时改调官方改写器（H3-Context-IR）~~ | 官方 API 文档 | 🧊 **已归档** `_archive/h3_clone/` |
| `app/services/h3_skill.py` / `h3_direct.py` | 读 skill 包 / 直接拼，两条平级线 | `skills/README.md` | ✅（提示词优化那条线） |
| `app/services/h3_official.py` | 把官方资料装进上下文（`:70` 记着"只传 ref-en 会丢运镜闭集"） | `ref-en` + `base-en` | ✅ |
| `app/services/h3_convert_route.py` | 按素材选模式、选尺子（纯规则） | `skills/papercraft-stop-motion-explainer/SKILL.md:11` | ✅ `guide=ref` 已指向 `ruler_h3_handwrite` |

---

## 7. 读完 30 个文件后，值得单独记住的 10 条

1. **`ref-en:68`**：图只用来定义人物/场景/服装/风格时，**不单独开 `<Picture N>` 行** —— 写进对应 `<Subject N>`。
2. **`ref-en:112`**：参考视频自带声音 ≠ 自动有 `<Audio N>`；口型必须单独喂一条音频。
3. **`ref-en:230`**：Ref2VA 的**风格句写在 `[Shot 1]` 之前**；base 四模式写在 `[Shot 1]` 之内。**同一句话换模式就换位置**。
4. **`ref-en:242`**：350–500 词只管"生成任务"；**编辑复刻不受这个区间约束**。
5. **`ref-en:274`**：台词逐字保留，听不清写 `[unclear]`，标点统一成 `, . ? !`。
6. **`ref-en:207`**：目标片里新增的动作/背景/剧情**不算保真度下降**。
7. **`ref-en:278`**：`(Sx)` 按"目标片实际发声顺序"发号，`retention_analysis` 里不写。
8. **`base-en:154/162`**：soundscape 1–4 句、music 1–3 句；`N/A` 只在用户明确要全片无声时用于 soundscape。
9. **`skills/co-op-game-intro-generator/SKILL.md:24`**：参考图**只捐身份锚点**，不捐写实质感/光线/原图风格 —— 这是"换人别把整间屋子搬走"的官方原话来源。
10. **`skills/music-video-subtitle-generator/SKILL.md:34/63`**：>15s 就自动多镜拼接（2–5s 一段 + 头尾帧 + 主音轨对齐），这是官方对待长片的做法。

---

## 8. 官方"没写"的地方（别把沉默当禁令）

| 我们想做的 | 官方资料里 | 处理 |
|---|---|---|
| 参考音频 + 参考视频的**总时长**上限 | 只分别写了「视频总 ≤15s」「音频总 ≤15s」，**没写两者合计** | 不许自己加规则；出问题按证据查 |
| H3-Lite 的具体能力边界（码率/人脸/多人） | 风格 skill 只说 H3「单片段最长 15s @2K」 | 实测为准，别拿 Max 的说明套 Lite |
| 失败码含义 | A 组（skill 包）里没有；**官方有专页**《错误码查询》（`api-error`，61 行） | 直接查 §9.6，别再翻 skill 包、别再从 HTTP 示例反推 |
| 复刻任务的字数/节奏要求 | `ref-en:242` 明确说编辑任务不受生成任务字数约束 | 要按原片复杂度写，不凑字数 |

---

## 9. API 规格（B 组）—— 发不发得出去，看这节

> 和 A 组的分工：A 组管「提示词怎么写」，B 组管「参数合不合法、失败码什么意思」。
> 全部行号来自 **2026-11-02 抓取**的 `pull-2026-11-02/`。

### 9.1 创建任务 `api-create`（`POST /v2/video_generation`）

| 参数 | 行号 | 规则（原文要点） |
|---|---|---|
| `model` | `api-create:165-187` | 四档：`MiniMax-H3` / `-Highspeed` / `-Lite` / `-Max` |
| `content` 组合 | `api-create:188-215` | 必须有**一个非空 `text`**（`:195`）；**图生视频与多模态参考生视频互斥** —— 出现 `reference_*` 就不能出现 `first_frame`/`last_frame`（`:213-215`） |
| 请求体上限 | `api-create:221` | **≤ 64 MB**；大文件用公网 URL，别 Base64（Base64 放大 ~33%，`:432-433`） |
| 图片限制 | `api-create:224-239` | JPG/JPEG/PNG/WEBP/HEIC/HEIF；单张 ≤30MB；边长 [256,5760]；宽高比 [0.4,2.5]；首帧 ≤1、尾帧 ≤1、**参考图 ≤9** |
| 视频限制 | `api-create:242-263` | MP4/MOV；H.264/H.265 + AAC/MP3；单个 ≤50MB；**≤3 个**；单段 [2,15]s、**总 ≤15s**；帧率 [23.976,60] |
| 音频限制 | `api-create:266-279` | WAV/MP3；单个 ≤15MB；**≤3 个**；单段 [2,15]s、总 ≤15s |
| `resolution` | `api-create:282-294` | H3：768P/2K；Highspeed/Lite/Max：480P/768P |
| `duration` | `api-create:295-316` | H3/Highspeed/Lite：4–15；**Max：5–15（不支持 4 秒）** |
| `ratio` | `api-create:317-336` | 默认 `adaptive`；**t2va 必填且不能 adaptive**（`:324-325`）；i2va 恒 adaptive（`:328-330`）；**Lite 不支持 adaptive**（`:333-336`） |
| `extra` | `api-create:345-361` | **只有 H3-Max 有**；仅 `prompt_expansion_mode`（`disabled`/`balanced`/`quality`，默认 `balanced`）；**不要传 `balance`、空串、布尔值、未声明字段** |
| `callback_url` | `api-create:362-371` | 先发含 `challenge` 的验证请求，**3 秒内原样返回** |
| `aigc_watermark` | `api-create:372-374` | 默认 `false` |
| `text` 长度 | `api-create:404-408` | **单个 `text` ≤ 7000 字符** |
| 素材地址三种形态 | `api-create:409-446` | 公网 URL / `mm_file://{file_id}` / `data:<mime>;base64,…` |
| `role` 五个值 | `api-create:447-461` | `first_frame` / `last_frame` / `reference_image` / `reference_video` / `reference_audio` |

### 9.2 官方提示词改写器 `api-ir`（`POST /v2/h3_context_ir`）

| 事实 | 行号 |
|---|---|
| **只返回增强提示词，不创建视频任务** | `api-ir:11` |
| 产物从 `content.prompt` 取；`task_type=h3_context_ir` | `api-ir:21`，`api-query:314-316` |
| `model` **只能填 `MiniMax-H3`**（Lite/Max/Highspeed 都不收） | `api-ir:175-179` |
| `duration` **必填**，4–15 | `api-ir:274-289` |
| 请求体**没有 `resolution` 字段**（对比 create 的 `:282`） | `api-ir:167-332`（schema 全文） |
| `ratio` 语义与 create 相同（t2va 必填非 adaptive） | `api-ir:290-315` |
| 计费按 token 记（示例 `total_tokens:9090`） | `api-ir:137-141` |

### 9.3 查询 / 列表 / 删除

| 事实 | 行号 |
|---|---|
| 只能查**最近 7 天**（窗口 `[T-7天, T)`）；过期返回 `invalid task_id` | `api-query:37-38` |
| 失败任务带 `error{code,message}`（示例 1026） | `api-query:165-181`、`:245-247` |
| 视频产物 URL **有时效**，过期可重新查询 | `api-query:313` |
| 列表分页：`page_num` / `page_size` / `filter.status` / `filter.task_ids` / `filter.model` / `filter.task_type` | `api-list:34-80` |
| 列表 `total` **只统计 7 天内** | `api-list:118-120` |
| 删除是**通用接口**（正文 0 次出现 H3）：`queued` 只能取消，成功/失败记录才可删除 | `api-delete:39-48`、`:78-84` |

### 9.4 768P → 2K 再生成 `api-regen`（我们**没做**）

| 事实 | 行号 |
|---|---|
| **只对符合 H3 768P 输出规格的源视频**生效，不是通用超分 | `api-regen:7`、`:16` |
| 两种输入**必须且只能二选一**：`source_task_id` 或 `content` 里一个 `base_video` | `api-regen:46` |
| 按 task_id 那条路**需开通白名单** | `api-regen:50`、`:210` |
| 源视频规格：**必须有音轨**、24fps、宽高被 32 整除、面积 589,824–1,032,192、107–362 帧 | `api-regen:250-265` |
| `text` 必须是**当时实际送进模型的最终 prompt**（不是 IR 处理前的原文），≤40000 字符 | `api-regen:243-245`、`:324-325` |

### 9.5 机器可读全量规格 `openapi`

`openapi` 是同一个规格的 JSON 版，6 个端点（`openapi:21-22`、`openapi:197`、`openapi:345`、`openapi:460`、`openapi:587`）：

```
POST /v2/video_generation
POST /v2/h3_context_ir
GET  /v2/query/video_generation/{task_id}
GET  /v2/query/video_generation
DELETE /v2/video_generation/{task_id}
POST /v2/video_regeneration
```

**用法**：查字段枚举、必填项、schema 分支，直接读这个 JSON，比读 581 行 Markdown 快。

### 9.6 错误码表（排查失败必查）—— **权威页是 `api-error`**

> 官方专门有一页《错误码查询》（`api-error`，61 行）。**别再从 HTTP 示例里反推**。

| code | 官方含义 | 官方给的解法 | 行号 |
|---|---|---|---|
| **1000** | **未知错误 / 系统默认错误** | **请稍后再试** | `api-error:15` |
| 1001 | 请求超时 | 请稍后再试 | `api-error:16` |
| 1002 | 请求频率超限 | 请稍后再试 | `api-error:17` |
| 1004 | 未授权 / Token 不匹配 / Cookie 缺失 | 请检查 API Key | `api-error:18` |
| 1008 | 余额不足 | 请检查账户余额 | `api-error:19` |
| 1024 | 内部错误 | 请稍后再试 | `api-error:20` |
| 1026 | 输入内容涉敏 | 请调整输入内容 | `api-error:21` |
| 1027 | 输出内容涉敏 | 请调整输入内容 | `api-error:22` |
| 1033 | 系统错误 / 下游服务错误 | 请稍后再试 | `api-error:23` |
| 1042 | 不可见字符比例超限 / 非法字符超过 10% | 检查输入内容 | `api-error:27` |
| 1045 | 任务并发数超限 | 等前一个任务完成再提 | `api-error:30` |
| 2013 | **参数错误** | 请检查请求参数 | `api-error:32` |
| 2022 | 模型不存在或无权使用 | 检查 `model` 参数 | `api-error:35` |
| 2069 | 模型已下线 | 更换在售模型 | `api-error:58` |

**结论（写死）**：任务 `status=failed` 且 `error.code=1000` = **官方「未知错误/系统默认错误」，
官方解法是「请稍后再试」**；参数问题是 **2013**（`api-error:32`）。两者别混。
→ 直接对上 2026-11-02 那次失败：不是素材超限，重试才是正确动作。

> 旁证（同一结论的两条路）：HTTP 500 示例把 `1000` 写成 `internal error`（`api-create:569`）；
> 任务失败示例用 `1026`，与 422 的敏感内容示例一致（`api-query:165-181`）—— 任务错误码与 HTTP 错误码同一套。

---

## 10. 中文《使用手册》（C 组）

> `manual`（297 行，飞书 wiki 版）与 `manual-full`（864 行，官网版）**同一份文档，已逐条核对一致**。
> 🩸 **体裁边界**：这本手册讲的是**用户手写入口**（素材用 `@图片1/@视频1` 标注），
> 我们发出去的是 **skill 的 Ref2VA 六段式**（`<Picture 1>`）。`official/docs/README.md:47-53` 原话：
> 「两种体裁，规则不能互相搬」——手册能用来核对**内容层**要求（台词长短、运镜词表），不能当六段式格式的判据。

| 要知道什么 | 行号 |
|---|---|
| 模型功能信息总表（分辨率/时长/帧率/声音/输入条件/格式/大小/字数/语言） | `manual:28-42` |
| 输出分辨率怎么算：768p 短边 768，21:9 → 1536×672；**1440p 为官方推荐** | `manual:33` |
| 输入条件：首尾帧 0/1/2 张；全能参考 ≤9 图 / ≤3 视频 / ≤3 音频；**混合总上限 12 个文件** | `manual:37-38` |
| **音频必须配图片或视频，不能单独输入** | `manual:38` |
| 提示词 ≤7000 字符 | `manual:41` |
| 多语言：TTS 稳定 11 种，可衍生 40+ | `manual:42`、`:148-152` |
| 三大能力（原生多模态 / 精准编辑 / 商用多场景） | `manual:46-50` |
| **提示词公式 = 参考素材说明 + 核心创意 + 画面过程说明** | `manual:242-245` |
| 素材说明：**13 类用途**（人物/物体/场景/关键帧/音色/故事板/风格/构图/音频复用/**音频部分复用**/动作/运镜/视频编辑），逐条定义见 §10.1；**"非常想保持的特征，建议明确写出"** | `manual:248` |
| 核心创意四要素；环绕运镜建议写 `truck left + pan right` | `manual:250` |
| 画面过程说明：按 shot 分段写；**台词长短要和镜头长短对齐**；不要 BGM 就写 `non_diegetic_music: N/A` | `manual:251` |
| 拆镜：支持跨 shot 台词（J-cut/L-cut）；切镜要写清景别与主体 | `manual:253-261` |
| 三类模式（多模态参考 / 图生视频 / 纯文生）分别怎么写 | `manual:262-267` |
| 六条常见坑 | `manual:269-278` |
| 两个超长完整样例（大字幕 MV / 手绘特效） | `manual:284-285` |

### 10.1 第 2、3 章：**官方明确声明的能力与示例**（2026-11-03 补 · 此前整节漏索引）

> 🩸 **补这一节的起因**：2026-11-03 我回答「H3 官方有没有换人 / 多人能力」时，
> 只 grep 了 `face` / `人脸` / `肖像` / `likeness` / `换脸`，**没搜「角色替换」**，
> 据此下了「官方没写」的结论，被主人用两页手册截图当场纠正。
> **根因不是 grep 词少，是本表 §10 漏收了 `manual:200-238` 整节** —— 我按自己的地图查，必然查不到。
> 🔴 **写死的纪律：按本表查不到 ≠ 官方没有。查不到时必须先怀疑本表，回手册目录（`manual:1-27`）逐章翻一遍。**

**一、模型定位（`manual:21-25`）**

> 「MiniMax H3 是新一代开放通用多模态视频模型，我们正在探索从"特化任务模型"迈向"通用多模态智能"的新范式。H3 **不再以图片、视频、声音的生成、编辑、参考等单一任务为边界**，而是面向由文本、图像、视频与声音共同构成的多模态上下文，统一理解创作意图。」

**总表（`manual:46-50`，官方三大能力）**

| 三大能力 | 官方原文要点 |
|---|---|
| 原生多模态理解与生成 | 文字/图片/音频/视频多种输入，理解**人物、动作、声音、情绪、镜头、风格与表达意图** |
| **多模态精准编辑与控制** | 支持对**人物、物体、场景、声音与节奏**进行多维度编辑，具备**精细化指令遵循能力**，可在已有内容上**持续修改和迭代** |
| 商用级多场景内容生成 | 影视/广告/品牌/电商/游戏 |

**二、模型功能信息（`:26-42` 整表 · 2026-11-03 按主人 11-01 版截图逐行核对，逐字一致）**

| 维度 | 行号 | 官方原文 |
|---|---|---|
| 模型 | `:30` | `MiniMax-H3` |
| 输出时长 | `:31` | 4–15 秒 |
| 输出宽高比 | `:32` | 首/尾帧模式：遵循输入图片原始比例；文生视频：21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16；全能参考：同上或**自动由 H3 自行判断** |
| 分辨率 | `:33` | **768p（已开放）/ 1440p（官方推荐👍）**；比例在 16:9~9:16 之间取短边 768 / 1440，否则总面积约 1M / 3.7M 像素（21:9 → 1536×672 / 2976×1248） |
| 输出帧率 | `:34` | **24 FPS** |
| **输出声音** | `:35` | **所有结果全部带声音输出，原生双声道** |
| 首/尾帧入口 | `:37` | 图片 **0 / 1 / 2 张**；宽高 [256, 5760]；**宽高比 5:2 ~ 2:5** |
| **全能参考入口** | `:38` | 图片 **≤9 张**（[256,5760]）<br>视频 **≤3 段**，单段 [2,15]s、总 ≤15s，[256,5760]，宽高比 5:2~2:5<br>音频 **≤3 段**，**必须配图片或视频，不能单独输入**，单段 [2,15]s、总 ≤15s<br>🔥 **混合输入总上限 = 12 个文件** |
| 输入格式 | `:39` | 视频 **H.264/AVC、H.265/HEVC**；视频内音频 **AAC、MP3**<br>图片 JPG / JPEG / PNG / WEBP / HEIC / HEIF<br>音频 WAV / MP3 |
| 大小限制 | `:40` | 视频单个 **50MB**；图片单个 **30MB**；音频单个 **15MB**（**加起来不限制，限制都在单个素材上**）；API 请求体 **64MB**（**推荐用 url 传入素材**） |
| 提示词上限 | `:41` | **≤7000 字符** |
| 语言支持 | `:42` | 同第 2 章 `:171-175`（11 种 TTS 语言 / 40+ 衍生） |

**三、模型亮点能力& 示例（章标题 `:44`）→ 下设 1 / 2 / 3 三大块**

**第 1 章「商用级多场景内容生成」（`:52-163`，10 个场景示例，与复刻无关，只登记不细看）**

| 小节 | 行号 | | 小节 | 行号 |
|---|---|---|---|---|
| 1.1 品牌大片与影视内容 | `:56` | | 1.6 产品与电商营销 | `:108` |
| 1.2 视觉创意与内容包装 | `:67` | | 1.7 数字体验与游戏创意 | `:117` |
| 1.3 动态图形、MG动画、AE特效 | `:80` | | 1.8 硬件、实体工业、具身智能演示 | `:128` |
| 1.4 AR现实增强创意视频 | `:90` | | 1.9 动画与风格化影像 | `:135` |
| 1.5 AI 剧情内容创作 | `:99` | | 1.10 出海多语种场景 | `:148` |

**第 2 章「原生多模态理解与生成」（标题 `:165`，正文 `:166-175`，小节到 `:198`）**

`:166` 总述：**「H3 支持文字、图片、音频、视频等多种输入，将所有素材视作统一上下文，理解信息、声音、情绪、画面与表达意图之间的关系，进而实现从内容理解到视听融合的一体化创作。」**

`:167-170` **官方四条能力**（原话）：

| # | 能力 | 官方原话 |
|---|---|---|
| 1 | 多素材联合参考 | 文字、图片、音频与视频自由组合，共同参与内容生成 |
| 2 | **角色、动作与镜头参考** | **参考主角形象、人物动作、镜头运动与画面构图** ← 复刻三件套的官方出处 |
| 3 | 音色迁移与克隆 | 参考音频音色，丝滑更新角色声音 |
| 4 | **氛围与剪辑理解** | **参考原视频的视觉风格、叙事节奏、声音氛围与整体剪辑感** |

`:171-175` **语言支持与本地化表达**（原话）：
- 支持多语言提示词输入与输出
- TTS（文本转语音）精准覆盖 **11 种语言**：中文、英语、日语、韩语、法语、德语、西班牙语等
- 更多语言可衍生探索，如阿拉伯语、泰语、印尼语、印地语等 **40 多种语言**
- 适合海外品牌传播、多语种广告、跨语言短片和本地化产品介绍等场景

| 小节 | 行号 | 官方能力 | 代表示例（逐字） |
|---|---|---|---|
| 2.1 多素材联合参考 | `:176-183` | 文字/图片/音频/视频自由组合共同参与生成 | 图1-6，严格参考示例视频1的镜头节奏、转场风格及音乐 |
| **2.2 角色、动作与镜头参考** | `:185-192` | **参考主角形象、人物动作、镜头运动与画面构图** | 🔥 `:192`「**参考视频1进行动作模仿**。固定机位全景镜头，正视频中**三个穿西装的男人替换为三只高度写实的水豚**。水豚必须**严格遵循原视频的运动轨迹**：依次迅速趴到地板上，然后最左边的水豚跳到中间位置……**保持原有的固定机位不变**」 |
| | `:189` | 同上 | 「图1的人物**动作、表情与表演节奏严格参考**输入视频1」（输出文件名 `角色替换+动作参考.mp4`） |
| | `:190` | 同上 | 「人物参考视频1的动作，表演街舞，**人物参考图1 图2**」（**双人**→ `角色替换+动作参考2.mp4`） |
| | `:191` | 同上 | 「参考视频1的希区柯克镜头运动，让视频2中的人物唱歌，歌声和唱歌表演参考视频3」 |
| 2.3 音色克隆与迁移 | `:194-198` | 参考音频音色更新角色声音 | 角色说话：…，音色参考音频1 |

**第 3 章「全能精准编辑与修改」（`:200`→`:238`）**

> `:201` 原文：「H3支持多种维度的编辑与修改。**角色替换**、动作参考、背景替换、背景特效、**台词替换**与氛围感理解，并支持高精度的指令遵循能力。」
> `:203` 「角色与物体编辑：**替换、删除或增加人物与物体**，灵活调整画面主体」
> `:206` 「高精度指令控制：准确执行局部修改与细化要求，**同时保持未编辑内容相对稳定**」

| 小节 | 行号 | 代表示例（逐字） |
|---|---|---|
| **3.1 角色与物体编辑**（标题 `:207`） | `:211` | 把视频中的猫换成狗 |
| | `:212` | 画面左边**增加**一个穿着相同团队制服的人，动作与旁人保持一致 |
| | `:213` | 🔥 **精准换人物与细节**：「视频1中**最后面的小孩**换成 图1中的金毛狗，视频1中**最左边小孩**穿的卡其色外套改成图2中的牛仔外套」 |
| **3.2 场景与视觉效果编辑**（标题 `:215`） | `:219` | 将视频1绿幕背景去除，变成类似视频2的童话感背景，背景元素需要完全匹配视频1的人物动作 |
| | `:220` | 替换光影 · 参考视频，改变光照，改成夜晚 |
| | `:221` | 实拍景色替换 · 视频1窗外的场景改成图1 |
| **3.3 声音、台词与音色修改**（标题 `:223`） | `:227` | 将视频1女生说的话："…"改成音频1的台词："…"，**并略微调整对应的表演** |
| **3.4 高精度的指令遵循**（标题 `:229`） | `:233` | 将参考视频中的报纸替换为一本绿色封皮的书；人物所坐的椅子改为红色沙发；**去掉人物佩戴的墨镜，保留清晰面部**；移除汽车燃烧效果…同时在画面左侧增加一棵树（**一条指令同时改 6 处**） |
| | `:234` | 参考视频，将视频开头出现的易拉罐饮料替换为可口可乐；背景中"全家"便利店招牌修改为"互惠"；结尾塑料袋零食统一替换为可口可乐易拉罐，**结尾人物台词从"买了一些小零食"变成"买了一堆可乐"**（改物 + 改招牌 + 改台词，三类同时） |
| | `:235` | 🔥 两位魔术师…**两人的西装颜色互换——左边的人穿白色西装，右边的人现在穿黑色西装，但两人手套颜色不变**（**左右方位 + 换装 + 部分保持**） |
| | `:236` | 在视频1中两个人周围加上图片1这种橙黄色的手绘涂鸦…（创意理解+文字特效） |

**四、如何更好地使用 H3（`:238-297`）**

| 小节 | 行号 | 要点 |
|---|---|---|
| **1. 撰写提示词的友好建议**（章标题 `:240`） | `:240-279` | 下设 1.1–1.5 五小节 |
| 1.1 整体公式 | `:242-245` | 完整提示词 = 参考素材说明 + 核心创意 + 画面过程说明 |
| **1.2 四个要素如何描述** | `:246-252` | 见下方「素材用途词表」+ 四条写死的建议 |
| 1.3 镜头怎么拆 | `:253-261` | 按 shot 分段；跨 shot 台词写「接着上个 shot 继续说」 |
| 1.4 三类模式 | `:262-268` | 多模态参考 / 图生视频 / 纯文生 |
| 1.5 容易踩的坑 | `:269-279` | 六条 |
| 2. 特定风格 · 提示词示意 | `:280-286` | 大字幕 MV `:284` / 手绘特效（纯文生）`:285` 两个完整长样例 |
| 3. 撰写提示词的「最佳方式」 | `:287-297` | 官方推荐用 MiniMax Design（`design.minimaxi.com` / `.io`）—— **与复刻无关，只登记** |

**`:248` 素材用途词表（官方 13 类，逐字）**

| 用途 | 官方定义 |
|---|---|
| 人物参考 | 锁定脸 / 形象 |
| 物体参考 | 锁定物体 |
| 场景参考 | 锁定场景 |
| 关键帧 | 锁定帧（有首帧尾帧需求明确提出） |
| 音色参考 | 锁定音色 |
| 故事版 | 根据故事版分镜生成镜头内容 |
| 风格参考 | 根据图片的风格，生成类似的风格内容 |
| 构图参考 | 根据图片中物体构图，生成对应的构图 |
| 音频复用 | 生成视频的音频直接复用参考音频素材 |
| 音频部分复用 | 生成视频某个声音轨道 / 某个时间段部分复用参考音频素材 |
| **动作参考** | **锁定动作** |
| **运镜参考** | **锁定运镜** |
| **视频编辑** | **对视频某个内容进行增删改** |

**`:248-251` 官方写死的四条建议（逐字）**
1. 「如果素材中有**非常想要保持的特征，建议明确写出来**，这样可以让一致性更好」
2. 「在音频复刻/部分复刻中，如果对于人声对白内容/唱歌歌词内容的保持有较高的要求，**强烈建议补充具体歌词文本内容**」
3. 🩸 **`manual:251`「注意台词的长短尽量和镜头长短对齐（这个得强调下，很多口型问题会来自于这个）」** ← **口型问题的官方归因**
4. 「尽量少写比喻句，多写看得见的画面」（H3 更擅长明确画面指令，不是抽象比喻）

**这张表推翻的两条旧结论（2026-11-03）**

1. ❌ 旧说法「官方唯一换人示例是单人 `ex-lamb`」→ **错**。官方有三人替换（`:192`）、多人精确换（`:213`）、左右互换（`:235`）。
2. ❌ 旧说法「我们落在 `reference generation` 而不是 `video editing`」→ **不成立**。官方把「角色替换」明确归在**「全能精准编辑与修改」**章（`:200-206`）。

⚠️ **体裁边界仍然有效**：这些示例是**用户手写入口**（`@图片1/@视频1`），不是 Ref2VA 六段式。
**句式不能直接搬**；但**能力声明**（H3 能做什么）是跨体裁的，可以作为"官方有此能力"的依据。
我们给 IR 的输入本来就是自然语言（`h3_ir.py:275-280`），所以这些示例的**句式骨架**可作为 IR 输入的候选写法来源 —— 但仍须单独立项验证，不许直接改代码。

---

## 11. 官方模型卡（C 组 `card`）

| 事实 | 行号 |
|---|---|
| 系统输出规格：4–15s、短边默认 768、**2K 需 H3-Regenerate-2K**、24 FPS、**32 kHz 立体声**、稳定支持 11 种语言 | `card:69-78` |
| 模型变体输入规格：Ref2VA ≤9 图 / ≤3 视频（单段 2–15s、总 ≤15s）/ ≤3 音频、**混合 ≤12** | `card:80-92` |
| 系统三模块：**H3-Context-IR → H3-Base（768p）→ H3-Regenerate-2K** | `card:92-110` |
| 🩸 **官方强推 IR**：「H3-Context-IR is critical to the quality of the final output, so we strongly recommend incorporating it into your generation pipeline」 | `card:90` |
| 本地部署两个 checkpoint（FL2VA / Ref2VA），BF16 | `card:184-192` |
| 本地/自托管**不含 Context-IR 与 2K 再生成** | `guide-local:259`（同 `guide-local:33`） |
| 官方把 Prompting Guidance 放在 HuggingFace，**没复制进仓库** | `card:440-444` |

---

## 12. 站点指南与官方示例（D 组）

### 12.1 `guide-gen`（视频生成指南）

| 事实 | 行号 |
|---|---|
| 11-02 版**只列 `MiniMax-H3` 一款**（H3-Max 段已删，见 §14） | `guide-gen:7-13` |
| 输出规格：768P / 2K，4–15 秒，整数 | `guide-gen:27-33` |
| 输入条件（与手册同表） | `guide-gen:35-51` |
| 四种模式代码；**t2va 的 ratio 必填且不能 adaptive** | `guide-gen:65-200`、`:82` |
| 想要更完整的提示词 → 先调 H3-Context-IR（异步，产物从 `content.prompt` 取） | `guide-gen:230-234` |

### 12.2 `guide-prompt`（H3 亮点功能示例）

六组中文提示词 + 成片：品牌大片 `:19` / 视觉创意 `:63` / AI 剧情 `:101` / 产品电商 `:141` / 数字体验与游戏 `:183` / 动画风格化 `:221`。
**用途**：找"官方认可的写法长什么样"，不是规则来源。

### 12.3 `guide-local` / `guide-local-all`（自托管，**不适用我们的 API 产品**）

| 事实 | 行号 |
|---|---|
| 开放发布**不含** H3-Context-IR 与 H3-Regenerate-2K，自托管**不能复现**完整工作流 | `guide-local:33` |
| H3-Base 短边 768、宽高对齐 32 的倍数；16:9 原生画布 = 1344×768 | `guide-local:102` |
| 组合输入上限同模型卡（9 图 / 3 视频 / 3 音频） | `guide-local:261` |
| `guide-local-all` 是**混合产品线**页（M3 / M2.7 / Music 3 / H3），只用来定位 | `guide-local-all:7`、`:22` |

### 12.4 两份官方完整 Ref2VA 示例（**写六段式时的金标准**）

| 文件 | 内容 | 为什么重要 |
|---|---|---|
| `ex-lamb`（23 行） | **口型重做 + 音色参考，不是换人**：`<Subject 1>` 是原片里穿粉色西装抱小羊的**同一个人**，`retention_analysis` 写 `fully_preserved`（身份/发型/西装/怀里的小羊全部保留），只是「mouth newly animated to speak」；`<Audio 1>` 原声部分复用、`<Audio 2>` 音色参考 | 🔴 **2026-11-03 纠正**：本行旧标注写成「和我们『换人 + 配音』最接近的官方样例」＝**误导源**。自始至终没有任何一条官方**完整换人**的六段式样例；换人样例只有手册里那 6 条自然语言（`manual:207-213` / `:185-192`）。`ex-lamb` 的价值只在「`partially_copy` / `reference` / `[任务类型 + 类型 + 类型]` 组合写法」这三个格式点上 |
| `ex-coffee`（27 行） | 多图（场景 1 张 + 狗 3 张）+ 双视频（女/男）+ 音色音频，三镜 | 多素材怎么编号、怎么在 `[Shot N]` 里复用 |

---

## 13. 串味审计（2026-11-02，主人点名要查）

**判据**：在 H3 语料里逐个文件扫其他型号/产品线的名字，再回原文看上下文。
**结论行**：真正串味的只有 **1 份**（`platform-docs.txt`），已挡在工程外；H3 规则文件 **0 串味**。

| 文件 | 扫到的"其他型号" | 回原文核对后的判定 |
|---|---|---|
| `platform-docs.txt`（15,185 行） | Speech 196 / abab 58 / Hailuo 49 / Image-01 13 / Music 7 | 🔴 **真串味**：整站抓取合集，开头甚至是 Mintlify 自家文档（`# Claude Code setup` / `# Cursor setup`）。**未进工程**，禁止引用 |
| 6 个 v2 API 页 + openapi | `Hailuo-03` ×1 每份 | ⚪ **别名**：只出现在 OpenAPI `info.description: MiniMax video generation V2 (Hailuo-03) API`（`api-create:17`）。是同一产品线的内部代号，不是别的模型 |
| `manual` / `manual-full` | `Hailuo` / `Seedance` | ⚪ **假阳性**：都是**案例视频文件名**（`Hailuo_Video_机器臂…mp4`、`…_seedance2-1780…mp4`），`manual:132` / `manual:234` |
| `card` | `Embedding` / `Kling` | ⚪ **假阳性**：`Embeddings` 是 MM-RoPE 技术术语；`Kling` 实际是英文单词 `sparkling` 的子串 |
| `llms.txt` / `site-index` | `MiniMax-M3` / `M2.7` / `Speech` / `Music` | ⚪ **目录文件**：这是全站目录，用来查"H3 还有哪页没抓"，本身不是规则 |
| `SKILL.md` / `base-en` / `ref-en` | — | ✅ **0 次**：核心写作规则完全干净 |

**工程里还剩三处提到 `platform-docs.txt`，逐个定性**：

| 位置 | 用途 | 判定 |
|---|---|---|
| `app/services/model_specs.py:128` | 注释：说明 10-22 快照里没有 Highspeed/Lite，证明两档是后加的 | ✅ 只作时间线证据，不引用其规则 |
| `scripts/test_edit_spec_h3.py:794` | 读「40 supported languages」当**拼写白名单** | ⚠️ 该表是**语音模型**的（同文件 `:809` 自己写了"找错了尺子"）；已在注释里写明**不是 H3 语言口径**，H3 稳定 11 种见 `card:78` / `manual:42` |
| `scripts/test_edit_spec_h3.py:791`（注释） | 说明快照来源 | ✅ |

---

## 14. 官方口径漂移（10-28 → 11-02）

> 抓取日不同，同一页内容会变。**引用前先看是哪天的快照**。

| # | 变了什么 | 旧（10-26/10-28 快照） | 新（11-02） | 出处 |
|---|---|---|---|---|
| 1 | 视频生成指南删掉了 H3-Max | 「提供 **MiniMax H3** 与 **MiniMax H3 Max** 两款模型」+ 一整节 Max 表 | **只剩 `MiniMax-H3` 一款** | 旧 `official/docs/official_video-generation.md:9-33` → 新 `guide-gen:9-23` |
| 2 | 型号写法统一 | `MiniMax H3`（带空格） | `MiniMax-H3`（连字符） | 同上 |
| 3 | **Highspeed 多了 480P** | 768P（不支持 2K） | **480P / 768P** | `api-create:174-176`（旧 `api-create-2026-10-28.md:175`） |
| 4 | Lite/Max 不再写"默认 768P" | 「480P、768P（**默认 768P**，不支持 2K）」 | 「480P、768P（不支持 2K）」 | `api-create:288-290` |
| 5 | 手册与 API 的分辨率叫法不同 | 手册叫 **1440p**（`manual:33`） | API 叫 **2K**（`api-create:282-294`） | 两处都已记录，别互相换算当同义词 |

**影响（只记事实，不改代码）**：
- 我们代码里的档位表若仍按 10-28 的「Highspeed 只有 768P」，**与 11-02 官方不符** → 第二步台账里核。
- 但 `api-create` 的**四档枚举**没变（仍是 H3 / Highspeed / Lite / Max），所以出片请求本身不受影响。

**维护缺口（如实记）**：`D:/tmp/official/h3/MANIFEST.json` **没有登记 11-02 新抓的 12 个文件**
（只登记到 10-28 的 17 条）。`p19_check` 只用它校验 `base-en` / `ref-en`，**不影响判据**；
下次维护时把新文件补进 MANIFEST。

---

## 维护

- 官方资料更新 → **先改本表，再改代码**。
- 代码里新增/修改任何 H3 规则 → 必须在本表对应行补 `文件:行号`；补不出来 = 这条规则没有出处。
- 本表的行号都按 **2026-11-02 的本地副本**计（副本随官方包更新会变）。
- **重新全量拉取**：`python D:/tmp/front_probe/pull_h3_official.py`（11 个 H3 页面一次拉完，
  落到 `D:/tmp/official/h3/pull-<日期>/`，旧快照不动）。
- **核对工程内副本与源目录**：`python D:/tmp/front_probe/verify_h3_copy.py`
  （逐文件 sha256；结论行带 N/M；未拷的必须点名给理由）。
- **串味扫描**：`python D:/tmp/front_probe/audit_h3_corpus.py`（每文件扫其他型号词 + 首次行号）。
- **新增文件的流程**：先 `audit` 看有没有串味 → 再 `verify` 拷进工程 → 本表加行 → 再动代码。
