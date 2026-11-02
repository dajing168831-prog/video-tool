# 各家模型 / 开源项目的规则 → 我们落在哪段代码

> 目的：改代码之前先看这张表，别把 A 家的规矩套到 B 家头上。
> 每条都给「规则出处」和「我们守它的地方」，两边都能点开看。

---

## 一、各家模型（参数与提示词语法，**按家分档，不许一套通吃**）

规则表：`backend/app/services/model_specs.py` 顶部的 SPECS ——
每档写死时长区间、分辨率档位、参考图/视频/音频上限、参考图指代语法、
是否「自动加兜底包」、是否允许负向域、编辑任务参数。

| 家族 | 硬规则 | 我们守它的地方 | 判据 |
|---|---|---|---|
| 火山 Seedance 2.5 | 编辑任务必须带 `omni_reference_task_type=edit`；`duration=-1`；`ratio=adaptive`；参考图 ≤30、视频 ≤10、音频 ≤10 | `ark.edit_body()` | `test_ark_edit_body` 38/38 |
| 火山 Seedance 2.0 / 极速 / Mini | 无 omni 参数；时长只能是整数秒（向上取整）；参考图 ≤9、视频 ≤3 | 同上 | 同上 |
| 火山 2.0 提示词范式 | 官方 skill `sd2-pe`：**必须**挂画质包 + 稳定包 + 水印/Logo 兜底、多人双胞胎兜底 | `edit_spec._clauses` 的 volc 分支 | `test_edit_spec` 105/105 |
| 火山 2.5 提示词范式 | 官方 skill `sd25-pe`：**不得**自动加兜底包；参数不许写进提示词 | `model_specs.auto_constraint=false` 分支 | 同上 |
| MiniMax H3 / H3-Max | H3 4–15s、H3-Max 5–15s；H3 有 768P/2K，H3-Max 只有 480P/768P；提示词 ≤7000 字符 | `model_specs` + `edit_spec` 的 h3 分支 | `test_model_specs` 65/65 |
| 参考图指代语法 | 火山 `@图片N`；MiniMax H3 `<Picture N>`；图片生成 API「图一/图二」 | `edit_spec` 按通道编译；`still_prompt()` 用图一/图二 | `test_edit_spec`、`test_whole_wiring` 79/79 |
| 火山图片生成 | `image` 收 string 或 string[]；Seedream 5.0 lite / 4.5 / 4.0 ≤14 张，Pro ≤10 张 | `ark.image_body()` | `test_ark_edit_body` 38/38 |
| 火山声音复刻 V3 | `POST /api/v3/tts/voice_clone`、`/get_voice`；头只要 `X-Api-Key` + `X-Api-Request-Id`；音频 ≤10MB；推荐 10–30s | `app/services/voice_clone.py` | `test_voice_clone` 25/25（截获请求体，不联网） |
| 复刻音色合成 | `S_` 开头必须走 `X-Api-Resource-Id=seed-icl-2.0` | `providers/tts.py::resource_for()` | `test_voice_clone` |

### 一.1 换人的两个数量口径（2026-10-22 定，**每个数字都有原文**）

| 口径 | 官方原文 | 我们怎么落 |
|---|---|---|
| **参考人物人数** | 2.0 指南 §「参考人物过多」：「当参考人物数量**超过 4 人**时，模型输出稳定性下降，生成的视频可能出现**人物数量不符（如少人、多人）或人物重复**」；示例「输入 8 个参考角色，输出视频有 9 人」<br>2.5 指南 §「素材输入建议」：「主体图，**1-8 主体效果较好**；更多可尝试 **9-12 主体，但稳定性下降、可能需要抽卡**」 | `model_specs.SPECS` 的 `stable_subjects / max_subjects`：<br>2.0 系列 **4/4**、H3 **4/4**（与 2.0 对齐，官方无人数口径）、2.5 **8/12**<br>判定入口 `edit_spec.subject_gate()`：稳定线以上只提示，超硬上限拦并指向 2.5 |
| **每人几张参考图**（**三家统一：一人一张**，2026-10-26 台账 D48 定案） | 2.0：指南 §6 实战案例「@图片 1：女主半身照」**一张打全片**；`guide:414`「人物参考图**优先使用单人独立照片**」；`sd2-pe:66`「角色图 1–2」= 一张合规。「**面部特征参考图片1（大头照），妆造参考图片2（全身照）**」只出现在指南 §「人脸参考不准确」这一**问题章节**，是出了问题的补救，不是默认配置<br>2.5：`sd25-pe` 与 2.5 指南**全文 0 次「大头照/全身照」**，写法是**一人一图 + 全属性**（`sd25-pe:227`/`:472`/`:948`），多图只用于多视角（`:456`）<br>H3：无此条（`ref-en:48`「One subject **may** be defined by multiple reference assets」是许可不是要求） | `video_edit.ref_plan(spec, refs)`：**一槽一张，用户传哪张发哪张**，不派生、不裁、不替换。<br>🩸 历史：2026-10-24 曾按 2.0 的「补救章」给每人拆两张（大头照 + 原图）；2026-10-25 双人实测被拆那位**没换脸**（SFace 0.19–0.36 vs 参考）；2026-10-26 三家官方原文复核后**整块删除**（台账 D48）—— 派生大头照、`person_body` 槽、`split_person_images` 消费点全没了<br>判据 `test_person_refs.py` + `p4_check` B4（防回潮） |

### 一.2 换装 / 道具 / 说话人 / 画面文字（2026-10-22 第一期）

| 口径 | 官方原文 | 我们怎么落 |
|---|---|---|
| **换谁的衣服要逐人点名** | 2.5 指南编辑案例：「**视频中深色衣服的男子的服饰替换为 @图片2**」 | `wardrobe_ids[]`：第 i 个人 → `wardrobe{i+1}` 槽，逐人一句「把@视频1中<外观描述>的服装换成@图片N中的服装」；**名单空 = 老语义（全体一起换）** |
| **换的对象必须点名** | 2.5 指南 §能力清单「修改·**对象**」；编辑句式「把<原对象>替换为<目标>」 | `product_target / product_target_en`：界面从视觉盘点里点选「换画面里哪一件」，提示词写成「把@视频1中<那一件>替换为@图片N中的产品」；不点名退回老句式。**不另开「道具」入口**（主人 2026-10-22：产品那行本来就写着换商品/换道具） |
| **说话人编号** | H3 `base-en.txt:127`：「Subjects who speak… use stable IDs such as `(S1)`… **characters who never vocalize receive no speaker ID**」<br>`ref-en.txt:258`：「write `<Subject N> (Sx)` when the speaker maps to a defined subject, or use a **stable voice description** followed by `(Sx)` otherwise」 | `speaker_ids[]` → 按名单顺序发 `(S1)(S2)`；不在换人名单里的说话人用英文外观描述 + `(Sx)`；没指定 = 老语义 `<Subject 1> (S1)`；没喂音轨时一个字都不写 |
| **画面内文字：整个能力不做** | 主人 2026-10-23 拍板：广告语 / 字幕 / 气泡全部下线，**就算复刻的带货视频原片带字幕，也不复刻那些字幕** —— 画面带字幕对 AI 天然不友好（2.5 指南 §「文字拼写错误」：高频错字；§「字幕约束不生效」：写了"不要字幕"仍可能出现） | 后端 `on_screen_text` / `_text_clauses` / `text_gate` / `text_warn` 全部删除；`p10_check` E5 守"界面不许再出现这个入口" |
| **换人句要直说、单人别带原片描述** | 2.5 指南触发词示例原句：「**把 @video1 的人物修改为 @image1**」<br>2.0 指南 §定义主体：主体要 2–3 个稳定特征定义，且每次指代要用同一标签 | `_clauses`：单人画面 → 「把@视频1中的人物**修改为**@图片1中的人物」；**多人画面才**用盘点描述当定位词。<br>🩸 2026-10-22 实测：旧句把原片人物的**衣服**写进替换句（"身着…和服…腰带"），模型照着只换了衣服 —— SFace 判定成片与**原片同人 49/56 帧**、与**参考图 0/65 帧**（max 0.292 < 0.363） |

### 一.3 视频延长（2026-10-22 第二期）

| 口径 | 官方原文 | 我们怎么落 |
|---|---|---|
| **比例锁定、时长自定** | 2.5 指南「有锁定：编辑 / 首尾帧 / **延长**」表：比例**锁定待延长视频**、**时长支持用户自定义** | `ark.extend_body`：`ratio="adaptive"`，`duration` 用请求值（按型号上限收口：2.0 ≤15s、2.5 ≤30s） |
| **怎么触发延长** | 2.5 指南：`content.role` 用 `reference_video`，提示词出现「**向前 / 向后延长**、延续、续写」 | 视频项带 `role="reference_video"`；`extend.prompt_for` 固定以「向后延长@视频1，生成…」/「向前延长@视频1，生成…」开头 |
| **别写成参考任务** | 2.0 指南 §延长视频：写「参考<视频N>」会被判成参考任务 | `p11_check` B3 断言提示词里没有「参考@视频1 / 参考视频1」 |
| **接缝跳变** | 2.0 指南 §延长视频衔接处跳变：**前段末尾删 6 帧、后段开头删 1 帧** | `extend.seam_frames`：2.0 系列返回 (6,1)，拼接前按帧裁；2.5 指南明确拼接处无痕迹 → 不裁 |
| **模型只出新增段** | 2.0 指南示例把「输出」与「拼接后的视频」分开列 | `ark.extend_video` 只下载新增段，`extend.stitch` 本地拼；缺音轨的一段补等长静音 |
| **反复延长会掉画质** | 2.0 指南 §延长视频：多次延长画质持续下降 | 结果页在已延长版本上提示「再延画质会继续下降」 |
| **H3 也能延长，但不是同一套写法**（2026-10-24） | 官方 skill `ref-en.txt:137` 任务类型 `video continuation`：「New content continues, extends, resumes, or transitions from an existing source video」；`:32/:81` `<Video N>` = continuation starting point；`:130-141` summary 首行必须是方括号任务类型 | `extend.prompt_for_h3`：六段式 + `[video continuation]` + `<Video 1>`，**不写**火山的「向后延长@视频1」（H3 没有独立延长接口，任务类型只能靠提示词声明） |
| **H3 参考片有硬上限** | 创建接口：参考视频 ≤3 段、**单段 [2,15]s、总时长 ≤15s**、单文件 ≤50MB | `extend.clip_for_h3`：向后延截**结尾 15s**、向前延截**开头 15s**（接续点必须和成片接缝同一处）；已达标原样送 |
| **H3 没有接缝计帧规则** | 官方未给接缝帧数，也没有保真度量化承诺 | `seam_frames`：H3 返回 (0,0)，先不裁；实测有跳变再定 |
| **清晰度各型号各收各的** | 火山 480p/720p/1080p(/4k)、H3 768P/2K、H3-Max 480P/768P | `extend.pick_resolution`：默认按待延长视频短边选，型号不收就落它的默认档；**档位大小写敏感**（`768P` 不能写成 `768p`） |

### 一.4 分段续接的边界帧（2026-10-22，H3 专属）

| 口径 | 官方原文 | 我们怎么落 |
|---|---|---|
| **图文互斥，边界帧只能按参考图发** | 创建任务文档：*"Image-to-video and reference-to-video are **mutually exclusive**: if any `reference_image` / `reference_video` / `reference_audio` role appears in content, then `first_frame` / `last_frame` must not appear (and vice versa); the two cannot be mixed."* | 边界帧不改成 `first_frame`；`minimax.reference_video` 仍按 `reference_image` 发 |
| **但提示词里可以钉成「第一帧」** | ref-en.txt:62 `<Picture N>` 可用于 *"a shot's first frame, keyframe, last frame"*；:134 关系标记 `keyframe completion`；:141 任务类型用 ` + ` 组合 | `edit_spec._minimax(boundary_pic=N)`：`subject_definitions` 写 `<Picture N> is the first frame of the target video at 0.00 seconds …must begin from this frame`，`retention_analysis` 写 `keyframe completion`，`summary` 叠成 `[video editing + … + keyframe completion]` |
| **六段全英文** | ref-en.txt:3-5 | 边界句不再追加中文；判据断言整段无中文 |
| **句尾中继句不算锚** | ——（实测） | 2026-10-22 render `e6bfd247`：旧写法把中文句挂在 `non_diegetic_music: N/A` 后、`<Picture 5>` 未定义 → 第 2 段开头 3 秒原片人物回灌；改成 `phase_h3_boundary` 的写法 |
| **每张参考图都必须有定义** | ref-en.txt:35：请求里出现的每一个参考件都要在 `subject_definitions` 里写明 | H3 **按段发图**：这一刀没出现的人，图不发（`_gen_spans` 摘掉并重编号）；火山保持「图号稳定」写法（图照发、不点名），两家不共用这一条 |

**换人 / 换服装这类「参考图怎么发」的规则，三个模式共用一处：**
`clone_pipeline.render()` 里在分支之前统一组装 `slot_refs`（顺序 = `SLOT_ORDER`），
auto（智能重制）和 shots（混剪 / 换开头）都从这里取 —— 曾经只写在 auto 分支里，
混剪换人就不发人物图（见 `CLONE-CHANNELS.md` §三十四）。

---

## 二、母本：hypit（**设计决策只能从这里来**）

选它当母本的三条判据（2026-10-22 定）：

1. **产品同构** —— 它做"参考素材/脚本 → 成片"，我们做"爆款原片 → 成片"，
   同一台机器：素材契约 → 分段生成 → 音画交付。
2. **有完整源码在本地** —— `D:/tmp/hypit-src`（30MB）。以前反复调研同一个问题，
   就是因为手里只有二手摘要；现在能逐行读。
3. **覆盖我们失血最多的三块** —— 分诊（什么该重画）、素材契约（每张图负责什么）、
   出片前算账（价位）。

> ⚖️ 许可：hypit 是改版 Apache 2.0，**禁止**把它的源码或其衍生作品用于多租户 SaaS
> 或打包转售（`LICENSE:1.a/1.b`）。所以**只学结构和做法，不搬代码**。
> 这条和我们一贯的"抽规则不侵权、复制表达侵权"是同一条线。

| 上游 | 规则 | 我们落地在哪 |
|---|---|---|
| **hypit** | `plan` / `pricing` 先于 `build`：出片前先算会动几段、多少钱，且**未知价格必须继续可见**，不能拿已知几组之和冒充总价 | `clone_pipeline.preview_render()` 的 `price.groups` / `unknown`；`POST /clone/{cid}/plan` |
| **hypit** | 帧 / 采样是**合同**不是估算：`frames = round(duration×fps)`，`samples` 由帧数反推 48kHz，**没有容差** | `preview_render` 的 `contract`；出片后按同一公式复核 |
| **hypit** | 静帧段的权重 / 连续整数帧规则 | 静帧重绘（`generate.regen_shots`）按镜头区间切，不越界 |
| **hypit** | transformations：换主体要覆盖它的**每种表现形式**；画幅 / 时长是独立变换轴 | `edit_spec._clauses` 每个槽位一句，逐槽位编译 |
| **hypit** | 画面参考与声音参考是**两类独立素材**，参考视频永远静音 | `ark.edit_body` 的 `reference_video` + 独立 `reference_audio` |
| **hypit** | 复刻 ≠ 把整条原片当生成输入（`craft/video-direction.md`）：静帧能交代的用静帧，只有"一段时间里发生什么"是重点时才用视频参考 | 逐镜分诊 `triage.py` 的 keep / video。<br>🩸 **2026-11-02 已删 still 档**：hypit 原文只有定性原则、**没有阈值也没有判定算法**，我们自标的 1.2 是自造 → 主人拍板「本来我们就是视频重制的」。`regen_mode="shots"` 也只是历史值，2026-11-02 起在入口归一成 `auto` |
| **hypit** | 多人物是"一人一图一轨 + 说话人映射"（`seedance-kits/kits/podcast-v1.svs`：`@image1`=Host A、`@image2`=Host B、`@audio1`/`@audio2`、SPEAKER MAP） | ⚠️ 未做：我们现在是单人契约（1 个人物槽 + 定位词），多人换人要按这个桩加槽位 |

**明确不做**（不是漏）：hypit 的在线 Provider 编排、我们不需要的镜头级重排、
以及任何「替用户写台词 / 写提示词审美」的部分 —— 边界见 `CLONE-CHANNELS.md` §十三。

### 二.1 查证源（**只核对，不产生规则**）

下面三家降级为查证源：需要核对某一句原文时引用它们，**但设计决策不从它们来**。

| 查证源 | 保留什么 | 不再使用它的什么 |
|---|---|---|
| **ReplicaPilot**（`francoeur003/replication`） | 身份锁那一句（`create_face_swap_contract.py:61`）+ 场景锁（`:68-72`）+ 负向包（`:79`）——见 §三 | 它的产品结构：脚本只有一个必填 `--person-image`，是**单人带货换脸**，撑不起我们的产品 |
| **viral-video-replicator** | 四模式选择表（`references/reverse-prompt.md:56-100`）：有脸图→`face_swap`、有衣服图→`outfit_swap`、都有→`full_swap`，作为"换什么"的对照 | 它的反推/生成逻辑 |
| **OpenMontage** | 只作换脸架构参考：它走 HeyGen `FaceswapNode`（外部付费 API），说明"专用换脸 API"和"视频模型重画"是两条路 | 全部：我们没这个 key，产品形态也不同 |

| 旧行（现归查证源） | 规则 | 我们落地在哪 |
|---|---|---|
| ReplicaPilot | `final_qa.py` 只查有限几项、**默认只报告不拦**（`--strict` 才非零） | `app/services/qc.py`；出片后记录不阻断 |
| ReplicaPilot | 一条原片 → 多个受控变体（只变一个变量） | 诊断页「一次出多版」：只改 `edit.extra`，其余参数完全一致 |
| viral-video-replicator | 换人 / 换装走主体参考，不和原片人物描述混用 | `edit_spec` 的 H3 主体绑 `<Picture N>` + `fully_preserved`；换装时身份句收窄为 face/hairstyle/body |

> 🩸 **准入线（2026-10-22 起）**：新规则要进代码，必须能指到 **hypit 的 `文件:行号`**
> 或**模型官方 skill 的原文**。指不到的 = 自己造的，当场撤回。

| 上游 | 规则 | 我们落地在哪 |
|---|---|---|
| **hypit** | `plan` / `pricing` 先于 `build`：出片前先算会动几段、多少钱，且**未知价格必须继续可见**，不能拿已知几组之和冒充总价 | `clone_pipeline.preview_render()` 的 `price.groups` / `unknown`；`POST /clone/{cid}/plan` |
| **hypit** | 帧 / 采样是**合同**不是估算：`frames = round(duration×fps)`，`samples` 由帧数反推 48kHz，**没有容差** | `preview_render` 的 `contract`；出片后按同一公式复核 |
| **hypit** | 静帧段的权重 / 连续整数帧规则 | 静帧重绘（`generate.regen_shots`）按镜头区间切，不越界 |
| **hypit** | transformations：换主体要覆盖它的**每种表现形式**；画幅 / 时长是独立变换轴 | `edit_spec._clauses` 每个槽位一句，逐槽位编译 |
| **hypit** | 画面参考与声音参考是**两类独立素材**，参考视频永远静音 | `ark.edit_body` 的 `reference_video` + 独立 `reference_audio` |
| **ReplicaPilot** | `final_qa.py` 只查有限几项、**默认只报告不拦**（`--strict` 才非零） | `app/services/qc.py`；出片后记录不阻断 |
| **ReplicaPilot** | 一条原片 → 多个受控变体（只变一个变量） | 诊断页「一次出多版」：只改 `edit.extra`，其余参数完全一致 |
| **viral-video-replicator** | 换人 / 换装走主体参考，不和原片人物描述混用 | `edit_spec` 的 H3 主体绑 `<Picture N>` + `fully_preserved`；换装时身份句收窄为 face/hairstyle/body |

**明确不做**（不是漏）：hypit 的在线 Provider 编排、我们不需要的镜头级重排、
以及任何「替用户写台词 / 写提示词审美」的部分 —— 边界见 `CLONE-CHANNELS.md` §十三。

---

## 三、换人提示词骨架（2026-10-22 逐行读过对标源码后定稿）

**来源**：ReplicaPilot `francoeur003/replication`
`runtime/seedance-face-swap/scripts/create_face_swap_contract.py`（下面行号都是这个文件）
＋ `src/core/variants.js` 的 `BASE_PROMPT`。

| # | 对标原句（出处） | 我们落地 |
|---|---|---|
| 1 | 身份锁：`Use @Image 1 as the replacement person identity throughout the entire video: same face, hair, skin tone, age impression, facial structure, and visible styling. @Image 1 always wins over other references.`（`:61`） | `edit_spec._clauses` person 分支：`<图>是替换后人物的唯一身份来源：脸、发型、肤色、年龄感、面部结构、可见造型都以它为准，与其他参考冲突时以它为准` |
| 2 | 原片只当动作/镜头参考，**原片的脸不保留**（`:59`） | 原片人物描述**降级为定位词**，但写成**正向**：`（这句只用来认出是哪一位，长相以@图片1为准）`。⚠️ 照抄"其长相和身份不保留"会让模型把"不保留"绑到替换目标上、干脆不换（2026-10-22 实测一次） |
| 3 | 场景锁：`Preserve @Video 1 background exactly… Do not use @Image 1 background, studio backdrop… as the scene.`（`:68-72`） | 正向句 `场景一律取自@视频1：背景、产品、画面布局、原有文字和界面、光线、物体位置与空间关系都与@视频1一致`（**换场景时不写**） |
| 4 | 负向：`no duplicate people, no face morphing, no original source face returning, no frozen expression, no blank stare`（`:79`） | `_VOLC_20_FACE_GUARD`，**只挂 2.0** |
| 5 | 人物图最短边 < 512px 只警告（`inspect_inputs.py:245/:274`） | **不追第二张**（2026-10-26 台账 D48）：三家统一**一人一张原图**，`ref_plan` 不派生大头照、不裁脸。脸能不能换住取决于**顾客那张图里脸占得够大**（半身照比全身照好），但这**不写成提示**（主人口头禁令：任何形态的「再传一张 / 脸太小换半身照」都不许出现，见 `subject_ref.py` 墓碑与 `p5_check` F3 的禁用词表）<br>🩸 历史：曾按 `sd2-pe:139` 给 2.0 派生「大头照 + 原图」两张（判据 `subject_ref.has_full_body()`，脸宽 ≥25%），2026-10-26 整块删除 |
| 6 | 交付前机检提示词里**必须出现** `BACKGROUND / SCENE LOCK`（`create_face_swap_contract.py:226`） | 待办：换人时机检「身份来源」「场景取自」两段是否在提示词里 |

**负向词按模型分家（主人 2026-10-22 再次确认）**：

- **只有 2.0 系列吃负向约束**（`seedance-2-0` / `-mini` / `-fast`）
- **2.5 和 H3 只吃正向词** —— 代码里早就写死为 `model_specs` 的 `negative_domain: False`，
  加约束前**查这个字段**，不要再按记忆判断

**另一家的换人写法（viral-video-replicator，作为对照）**：
`references/reverse-prompt.md:56-100` 四模式——clone（无图）/ face_swap（1 张=脸+身材，衣服仍写原文）/
outfit_swap（1 张=衣服）/ full_swap（图1=衣服、图2=人脸）。模式由**用户给了什么素材**决定。

---

### 三.1 加过又撤回的规则（别再捡回来）

| 加过的规则 | 撤掉的原因 | 撤回日 |
|---|---|---|
| 原片描述句写「其长相和身份不保留」 | 负向句紧挨"替换为@图片1"，模型把"不保留"绑到**替换目标**上，结果干脆不换 | 2026-10-22 |
| 人物图**只发一张**大头照 | 当时的理由是"发两张时火山把原片原样还回来"。复测不成立：那一版成片与原片 PSNR 20.02 dB、画面里人物根本没换；而**同一模型发一张时（`43be9920`，17.40 dB）也没换**。真因是模型/提示词，不是张数 | 2026-10-22 |
| 「速度优化版（fast）在指令遵循上退化」 | 当时 fast 全部跑的是新提示词、mini 全部跑的是旧提示词，**模型和提示词完全混淆**，不能归因到型号 | 2026-10-22 |
| 「mini 能换成功」 | mini 只把画面改了，脸从未锁住；后来的 male 参考图那条也是通用脸 | 2026-10-22 |

> 🩸 教训：一次只改一个变量。上面四条里有三条是"同时改了模型/提示词/张数，却拿结果归因到其中一个"。

## 四、改代码时的自检顺序

```bash
python scripts/test_model_specs.py      # 参数档位有没有被改坏
python scripts/test_ark_edit_body.py    # 真正发给火山的 body
python scripts/test_edit_spec.py        # 各家的提示词语法
python scripts/prompt_model_standards_check.py  # 选了哪个型号 → 就按那个型号的官方标准（67 条，含分段续接的第一帧锚点）
python scripts/prompt_lint_check.py     # 矩阵体检：通道×改动×保持×声音×边界帧全组合，扫自相矛盾/未定义标号/拼接毛刺（2794 条）
python scripts/test_voice_clone.py      # 声音复刻的协议
python scripts/rehearse_render.py       # 整条出片链路彩排（零费用）
```

> 🩸 **这一条是 2026-10-22 换人失败换来的**：同一个提示词写法被所有型号共用，
> 2.0 上把「替换人物」执行成了「替换衣服」（SFace：与原片同人 49/56、与参考图 0/65）。
> 主人当天的口径：**顾客选了模型，就按那个模型的标准执行** —— 所以现在每个型号的
> 「必须有 / 不许有」都写成 `prompt_model_standards_check.py` 的断言，改提示词先跑它。
