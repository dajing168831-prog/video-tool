# MiniMax H3 创作模式官方标准全集（T2VA / I2VA / FL2VA / L2VA）

> 2026-10-29。范围：**只讲 H3 的非六段式四种「基底模式」**。
> 跟 `PROMPT-AUDIT-H3.md`（Ref2VA 六段式，改已有视频）**并列存在，两套规则互不搬运**。
> 为什么要分开：同一家模型，两种模式的规则**方向相反**（见 §五）。

## 一、资料与出处

官方仓库 `MiniMax-AI/MiniMax-H3`（commit `d21241f0`），本机全量在 `D:/tmp/h3o/repo/MiniMax-H3-d21241f0…/`，
另一份快照在 `D:/tmp/official/h3/`。

| 文件 | 行数 | 本机路径 | 本文档怎么用 |
|---|---|---|---|
| `skills/h3-prompt-writing/SKILL.md` | 40 | `D:/tmp/official/h3/h3-prompt-writing-SKILL.md` | 总纲：五种模式、输出规则、4 条 Tips |
| `skills/h3-prompt-writing/references/base-en.txt` | 222 | `D:/tmp/official/h3/base-en.txt` | **主依据**：四种基底模式的完整写法 + 4 个官方完整案例（§5） |
| `api-create` | 581 | `D:/tmp/official/h3/api-create-2026-10-28.md` | 请求参数：`content` / `resolution` / `duration` / `ratio` / `text` / `extra` |
| `model-card` | 452 | `D:/tmp/official/h3/model-card-2026-10-28.md` | 对话语言稳定 11 种（已在 `h3_compile._LANG_STABLE`） |
| 8 个体裁 skill | 共约 150 KB | `…/skills/*/SKILL.cn.md` | **本文档不含**，见 §八 |

> `ref-en.txt`（六段式）属另一份文档，本文档一行都不引用。

## 二、五种模式，谁归谁

| 模式 | 全称 | 输入 | 归哪份文档 |
|---|---|---|---|
| **T2VA** | Text to Video+Audio | 只有文字 | **本文档** |
| **I2VA** | Image to Video+Audio | 文字 + 首帧图 | **本文档** |
| **FL2VA** | First+Last frame to Video+Audio | 文字 + 首帧 + 尾帧 | **本文档**（首期不做，见 §八） |
| **L2VA** | Last frame to Video+Audio | 文字 + 尾帧 | **本文档**（首期不做，见 §八） |
| Ref2VA | Full Reference to Video+Audio | 文字 + 图/视频/音频参考 | `PROMPT-AUDIT-H3.md`（六段式） |

出处：`h3-skill:11-14`「Identify the input mode: T2VA, I2VA, FL2VA, L2VA, or full-reference Ref2VA」。

## 三、硬规范（"必须/禁止"级）

> 「守」列写明谁来管：`尺子` = 计划中的 `scripts/ruler_h3_base.py` 规则号；
> `编译器` = 结构上写死、尺子不必单判；`待拍板` = 需要主人决定做不做。
> **现状一栏一律是「未实现」** —— 创作入口一行代码还没有，本文档是 Step 2 的施工图。

### A. 结构与语言

| # | 规范 | 出处 | 守 | 现状 |
|---|---|---|---|---|
| B1 | 正文只有**三个字段**，顺序固定：`integrated_multimodal_description` → `overall_soundscape` → `non_diegetic_music` | `base-en:36-44`、`h3-skill:23` | 尺子 B1 | 未实现 |
| B2 | 正文以 `[Shot 1]` 起头（有镜头时）；描述沿时间轴发展 | `base-en:39`、`base-en:81` | 尺子 B2 | 未实现 |
| B3 | 正文与三字段名一律英文；只有 `<d>` 里的话和画面可见文字保留原语言 | `h3-skill:33` | 尺子 B3 | 未实现（可复用 E12 的判据） |
| B4 | `text` 字段 **≤ 7000 字符** | `api-create:407` | 编译器 + 尺子 | 未实现 |

### B. 开头指令行（四种模式各一句，逐字）

| # | 规范 | 出处 | 守 | 现状 |
|---|---|---|---|---|
| B5 | **T2VA 没有指令行**，直接从三字段开始 | `base-en:14` | 尺子 B5 | 未实现 |
| B6 | **I2VA 恒用**：`For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.` | `base-en:16-20` | 尺子 B6 | 未实现 |
| B7 | **FL2VA 恒用**：`How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.` | `base-en:22-26` | 尺子 B7 | 未实现 |
| B8 | **L2VA 恒用**：`How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.` | `base-en:28-32` | 尺子 B8 | 未实现 |
| B9 | 指令行**必须是第一行**，其后**一个空行**再接三字段；`S.SS` = 实际时长，**恰好两位小数** | `base-en:34` | 尺子 B9 | 未实现 |

> 🩸 `base-en:25` 的 FL2VA 示例里 `Picture 1` **没有尖括号**，其余三处有。这是官方原文的写法不一致，
> **照抄示例原样，不要"修正"**（我们只对已判定的形状负责，不对官方排版负责）。

### C. 镜头与运镜

| # | 规范 | 出处 | 守 | 现状 |
|---|---|---|---|---|
| B10 | `[Shot 1]` **不带时间戳**；后续写 `[Shot N] At MM:SS.mmm, …`，切点**严格递增**且**落在视频时长内** | `base-en:86` | 尺子 B10（可复用 E16） | 未实现 |
| B11 | 切镜动词只用官方 5 种：`the camera cuts to` / `the shot cuts to` / `the shot transitions to` / `the shot changes to` / `the shot switches to`；交叉溶解/淡入淡出/划像**只有用户明确要求时**才用 | `base-en:92` | 尺子 B11 | 未实现 |
| B12 | **运镜类型只能取官方 13 类闭集**：`Zoom In/Out`、`Push In/Pull Out`、`Pan Left/Right`、`Truck Left/Right`、`Tilt Up/Down`、`Pedestal Up/Down`、`Arc Shot`、`Tracking Shot`、`Static Shot`、`Shake Slightly/Strongly`、`POV`、`Roll Clockwise/Counterclockwise` | `base-en:98-111` | 尺子 B12 | 未实现 |
| B13 | 幅度只许 `with small amplitude` / `with large amplitude`；速度只许 `at slow speed` / `at fast speed`；**中等幅度与常速通常省略** | `base-en:113-115`、`base-en:96` | 尺子 B13 | 未实现 |
| B14 | 运镜必须写成**句内自然英文动作**，不许当标签堆在句尾 | `base-en:117-123` | 尺子 B14 | 未实现 |
| B15 | 风格定调放在 `[Shot 1]` **开头**（如 `[Shot 1] Live-action, cinematic, a medium-wide shot frames…`）；官方列举的常见风格：`Cinematic` / `live-action` / `2D-animated` / `3D CG` / `claymation` / `watercolor` / `vintage film` | `base-en:78-82` | 尺子 B15 | 未实现 |
| B16 | 关键帧模式要有"首帧锚 → 动作起势 → 连续发展 → 结果/反应"的结构 | `base-en:56` | 编译器（结构） | 未实现 |

### D. 说话人与对白

> 这一节与 Ref2VA **共用**（`ref-en:9` 明写 shared），可整体复用 `h3_compile._h3_line`。

| # | 规范 | 出处 | 守 | 现状 |
|---|---|---|---|---|
| B17 | 说话人用稳定 `(S1)`/`(S2)`，跨镜不变；**不发声的角色不给号**；齐声/合唱用合成编号 `(S1,S2)` | `base-en:127` | 尺子 B17（可复用 E10） | 未实现 |
| B18 | 说话人首次出现要交代身份信息（类型/年龄/性别/画内画外/音高/音色/语速/口音） | `base-en:129` | 编译器 | 未实现 |
| B19 | 说话人短语、编号、动作、语气写在 `<d>` **外面**；`<d>` 里**只放** `[语言]` + 原词 | `base-en:129` | 尺子 B19（可复用 E20/E21） | 未实现 |
| B20 | 台词原词原语言，**不翻译不改写**；语气词与标点逐字保留 | `base-en:129` | 编译器 | 未实现 |
| B21 | 画外音用固定句 `says in an off-screen voiceover`；**每句之后立刻**写明画内人物嘴唇紧闭 | `base-en:136-140` | 尺子 B21 | 未实现 |
| B22 | 同一句跨切 → 两端都带 `<scenetrans>` 并明说声音跨切连续；被片尾截断 → `<cutoff>` | `base-en:142` | 尺子 B22（可复用现有） | 未实现 |

### E. 画面文字

| # | 规范 | 出处 | 守 | 现状 |
|---|---|---|---|---|
| B23 | 屏幕可见文字（招牌/横幅/霓虹/标识）放**英文双引号**内，原样保留不翻译 | `base-en:146-150` | 尺子 B23 | **做**（2026-10-29 主人拍板）。⚠️ 只做**画面内元素**；影片字幕是后期工序，仍不做 |

### F. 两层声音

| # | 规范 | 出处 | 守 | 现状 |
|---|---|---|---|---|
| B24 | `overall_soundscape`：**1–4 句**连续段落，只写环境音 / 物理动作声 / 非语言人声；**对白、演唱、画内音乐不在这里重复** | `base-en:154-158` | 尺子 B24（可复用 E17） | 未实现 |
| B25 | `non_diegetic_music`：**1–3 句**，写器乐/速度/节奏/动态变化；**不用抽象情绪词**、不解释配乐的情绪功能 | `base-en:162-166` | 尺子 B25（可复用 E17/E18） | 未实现 |
| B26 | 没有画外配乐 → `N/A`；`overall_soundscape` **只有用户明确要求全静音**才 `N/A` | `base-en:154`、`base-en:162` | 尺子 B26 | 未实现 |

### G. 内容自由度（这条与 Ref2VA 相反）

| # | 规范 | 出处 | 守 | 现状 |
|---|---|---|---|---|
| B27 | **T2VA 允许补细节**：官方原文「You may add scene, character, action, and sound details that remain consistent with the user's intent」 | `base-en:172` | 产品口径 | **做**（2026-10-29 主人拍板） |

> 🩸 2026-10-29 主人拍板「当然都做」。**这条不落在编译器，落在 Step 3 的槽位抽取层** ——
> 编译器只负责把已经确定的内容拼成官方语法，不认识"补"这个概念。
> **三条护栏（写进代码注释，也写进交付）：**
> 1. **只在顾客没给的地方补**；顾客写的人/物/动作/台词**一个字不改**
> 2. 补的内容从**官方词表与库**里取（风格词 `base-en:78`、运镜词 `base-en:98-115`、声音写法 `base-en:154-166`），**不自己造审美**
> 3. 交付时在提示词**外面**标明哪些是 AI 补的；不往提示词正文里掺任何标注

### H. API 参数（不是提示词，但顾客要照着填）

| # | 规范 | 出处 | 落点 |
|---|---|---|---|
| B28 | `duration`：**整数秒**，`MiniMax-H3` / `-Highspeed` / `-Lite` = **4–15**，**`-Max` = 5–15** | `api-create:294-300` | `model_specs` 已有 `min_sec/max_sec` |
| B29 | `ratio` 枚举：`adaptive` / `21:9` / `16:9` / `4:3` / `1:1` / `3:4` / `9:16` | `api-create:316` | **未接**（现有编辑链路不发 ratio） |
| B30 | **T2VA：`ratio` 必填，且不能是 `adaptive`** | `api-create:316` | 新入口必须处理 |
| B31 | **I2VA：宽高比由图片决定，`ratio` 恒 `adaptive`**；传别的会被忽略 | `api-create:316` | 新入口必须处理 |
| B32 | **`MiniMax-H3-Lite` 暂不支持 `adaptive`** | `api-create:316` | 交付时按型号收口 |
| B33 | `resolution`：`MiniMax-H3` = 768P/2K；`-Highspeed` = 仅 768P；`-Lite` / `-Max` = 480P/768P | `api-create:281-292` | `model_specs` 已有 |
| B34 | `content` 里 **`first_frame` / `last_frame` 与 `reference_image` / `reference_video` / `reference_audio` 互斥**，不可混用 | `api-create:186-215` | 新入口：I2VA 走 `first_frame`，与现有 r2va 链路物理隔离 |
| B35 | 每次请求**必须含一个非空 `text`** | `api-create:186-196` | 编译器保证 |
| B36 | `extra.prompt_expansion_mode` **不传 = 默认 `balanced` = 平台会把我们的提示词再扩写一遍** | `api-create:344-352` | **交付时要提醒顾客**：想原样执行得显式设 `disabled` |

## 四、我们现在的状态

| 项 | 事实 |
|---|---|
| H3 能力 | **两条并列链路**：Ref2VA（改已有视频，`h3_compile` + `ruler_h3`）／创作模式（T2VA/I2VA，`h3_base_compile` + `ruler_h3_base`） |
| 台词工具 | 两种模式共用 → 中立文件 `models/h3_common.py`（官方 `ref-en:9` 明写共用）。**两家编译器谁也不 import 谁** |
| 现有 H3 尺子 | 两把：`ruler_h3` **23 条**（E1–E23，六段式）／`ruler_h3_base` **22 条**（B1–B26 里可机械判的） |
| API 客户端 | `models/h3.py` 已发 `reference_image` / `reference_video` / `reference_audio`；**仍不发 `first_frame` / `last_frame`** —— 所以 I2VA 目前**只出提示词，不出片** |
| `ratio` | 创作模式的 `request_params()` 已接（编辑链路仍不发） |
| 真机跑过的 base 模式 | **0 次**。历史上 H3 只有 2 条请求，全是 r2va（1 条成功 768P，1 条 `HTTP 402` 余额不足） |

## 五、与 Ref2VA 的冲突点（这就是必须两套规则的原因）

| 维度 | Ref2VA（现有） | base 四种（新功能） | 冲突 |
|---|---|---|---|
| 字段 | 六段 | 三字段 | 结构不同 |
| **风格句位置** | `[Shot 1]` **之前**（`ref-en:230`） | `[Shot 1]` **之内、开头**（`base-en:78`） | 🩸 **方向相反** |
| 开头 | `summary:` + 方括号任务类型前缀 | T2VA 无；I2VA/FL2VA/L2VA 一行指令句 | 完全不同 |
| 分析段 | 有 `retention_analysis` + 4 个固定英文标记 | **没有这一段** | base 里出现即为错 |
| 参考标号 | `<Subject N>` / `<Picture N>` / `<Video N>` / `<Audio N>` 四类 | 只有 `<Picture N>`（帧锚） | 不同 |
| 内容自由度 | 只能写"谁换成谁"，不能编原片内容 | **官方明文允许补细节**（`base-en:172`） | 🩸 相反 |
| 我们的红线 | 不编 | 不编（主人口径优先于官方许可，见 B27） | 一致 |

## 六、现有 23 条规则的复用对照

| 类别 | 条数 | 明细 |
|---|---|---|
| **直接复用**（不依赖六段结构） | 9 | E5 镜头时间戳 · E10 台词必须有来源 · E11 句末标点 · E12 除 `<d>` 外英文 · E16 切点递增 · E17 两层声音句数与抽象词 · E19 `<d>` 无 emoji/装饰标点 · E20 `<d>` 无自造标号 · E21 `<d>` 语言标签 |
| **不适用** | 10 | E1 六段 · E2/E3/E4 summary 任务类型 · E6/E7 retention · E9/E22 参考标号唯一性 · E13 风格句位置（**方向相反**） · E14/E15 视频与音频标号 |
| **需按 base 模式重写判据** | 4 | E8 标签齐全（base 只认 `<Picture N>`）· E18 抽象词（范围按 `base-en` 重取）· E23 说话句分隔 · 其余同族 |

## 七、校准语料（现成的，不用另外找）

`base-en.txt §5` 有 **4 个官方完整案例**，正好一个模式一份：

| 案例 | 模式 | 行号 | 特征 |
|---|---|---|---|
| Case 1 | T2VA | `base-en:170-180` | 两镜 + 一句台词 + 无指令行 |
| Case 2 | I2VA | `base-en:182-194` | 指令行 + 首帧锚 + 一句台词 |
| Case 3 | FL2VA | `base-en:196-208` | 指令行（双图）+ 单镜 8 秒 + `non_diegetic_music: N/A` |
| Case 4 | L2VA | `base-en:210-222` | 指令行（尾帧 6 秒）+ 单镜 |

**尺子装好没装好的第一道判据**：这 4 份喂进去必须**全绿**。红一条，说明尺子装反了，不是官方写错了。

## 八、不做 / 待拍板

| 项 | 处置 | 理由 |
|---|---|---|
| **8 个体裁 skill**（3D动画短片 / 品牌宣传 / 合作游戏开场 / 手绘实拍 / 极简产品广告 / MV字幕 / 纸拼贴解说 / 纸艺定格） | **首期不做** | 它们是"整套交互流程 + 先出确认图再出片"，比"出一段提示词"重一个量级。等第一版跑通再作为"起步模板"接 |
| **FL2VA / L2VA** | **首期不做** | 各多一条指令行规则，且要传 `last_frame`，现有客户端从不发这个 role。二期 |
| ~~画面文字（B23）~~ | **做**（2026-10-29 拍板） | 只做画面内元素（招牌/霓虹/标识），**影片字幕仍不做** |
| ~~T2VA 允许补细节（B27）~~ | **做**（2026-10-29 拍板） | 落 Step 3 槽位抽取层，带三条护栏（见 §三 G） |
| **一键出片** | **不做** | 每次出片花钱，先验证"格式翻译"准不准，出片另议 |
| **接进编辑流程** | **不做** | 两套结构在一个对话里会打架，创作入口独立 |

## 九、Step 2 施工图（✅ 2026-10-29 已执行完，留档对照）

1. 新建 `app/services/models/h3_base_compile.py`：三字段拼装 + 指令行 + 运镜闭集，复用 `h3_compile._h3_line`（台词写法两模式共用）
2. 新建 `scripts/ruler_h3_base.py`：B1–B35 里可机械判的那部分 + 4 份官方案例 `--calib` + 每条一对探针
3. 门槛：`--calib` 4/4 绿、`--probes` 全对、`--current` 红 0
4. 全程零模型调用、零费用；真机验证要花钱，届时单独请示

## 十、分离边界（2026-10-29 主人拍板：**必须分开**）

> ✅ 2026-10-29 已落地：`models/h3_common.py`（中立共用件，登记进
> `model_separation_check.SHARED_STEMS`）—— 台词工具从 `h3_compile` 搬过去，
> 两个编译器都从它取，**谁也不 import 谁**。
> 搬完 `prompt_snapshot --model h3` **7/7 逐字一致**，六段式产出一个字没变。


> 主人原话：「要分开哦，虽然是在一个容器里面但是他们负责的功能完全不一样的」。

同一个工程、同一个后端进程里跑，但**功能上是两套东西**，所以物理分开：

| 层 | 改片模式（现有，Ref2VA） | 创作模式（本文档，base） | 边界规则 |
|---|---|---|---|
| 标准文档 | `PROMPT-AUDIT-H3.md` | `PROMPT-AUDIT-H3-BASE.md` | 互不引用；同一个事实在两份里写法不同也**必须各写各的** |
| 编译器 | `app/services/models/h3_compile.py` | `app/services/models/h3_base_compile.py` | **两个文件、零分支** —— 不许在一个文件里 `if 创作: … else: …`（那就是过去"一个文件塞三家"的翻版） |
| 尺子 | `scripts/ruler_h3.py`（23 条 E*） | `scripts/ruler_h3_base.py`（B* 系列） | 规则不跨文件引用 |
| 接口 | `app/api/clone.py`（`/clone/*`） | 新建 `app/api/h3_base.py`（`/h3/base/*`） | 入口分开，互不调用 |
| 型号锁 | `--model h3` | 独立开关 | 不共用一个锁文件 |

**允许的单向复用**（官方 `ref-en:9` 明写"对白、镜头、运镜、声音的基本格式与 base 模式共用"）：

- 创作 → 可 import `h3_compile` 里的台词工具（`_h3_line` / `_LANG_TAG` / `lang_support` / `_h3_mmss` / `_ucfirst`）
- **改片 → 一个字节都不许 import 创作的东西**

理由与三家模型分离同源：`models/` 目录每家一个文件、依赖单向（`h3_compile.py:7-9` 开篇即写「依赖方向是单向的」）。
现在是**同一家模型内部再按功能分一次**，规则一样 —— 混着改，改 A 必然弄坏 B。

## 十一、施工记录（2026-10-29 · Step 2 完成）

建了三件东西，全部零模型调用、零费用：

| 文件 | 行数量级 | 干什么 |
|---|---|---|
| `app/services/models/h3_base_compile.py` | ~330 行 | 三字段拼装 + 四种指令行 + 运镜闭集 + 说话人发号 + 请求参数 |
| `scripts/ruler_h3_base.py` | ~600 行 | 22 条规则 + 4 份官方案例校准 + 22 对探针 + 672 组合穷举 |
| `app/services/models/h3_common.py` | 189 行 | 两种模式共用的台词工具（从 `h3_compile` 搬来，逐字未改） |

判据现状（`check_all --model h3` 里已挂 5 个入口，通过 51 / 红 0）：

| 入口 | 结果 |
|---|---|
| `--calib` | 4 份官方案例，**88 条判定红 0** |
| `--probes` | **22/22**（坏样本必响、好样本不响） |
| `--current` | 0 红 |
| `--sweep` | 8 组合 + 6 项参数，0 红 |
| `--exhaustive` | **672/672** 组合，破口 0 |
| 六段式没被弄坏 | `prompt_snapshot --model h3` **7/7 逐字一致** · `ruler_h3 --probes` 23/23 · `test_edit_spec` 288/288 |

### 施工中抓到的 4 个真问题（全是判据抓的，不是靠眼看）

1. **B10 假红**：I2VA/L2VA 的**指令行里也写着 `(from [Shot 1])`**，那是帧锚来源不是镜头标号 → Case 2 / Case 4 双双判红。修：镜头标号只在描述字段之后数。
2. **B11 假绿（更危险）**：原来用 `([^.]{0,80})\\.` 卡长度，官方长句超过 80 字符 → **一个都没匹配上，规则从来没跑过**。修：改成"时间码之后到下一个句号"。
3. **B12 假绿**：断句不切 `[Shot N]` → 下一镜的 `the camera cuts to` 粘进上一镜的运镜句，规则被判为"有切镜动词"整句跳过。修：`[Shot N]` 也当句子边界。
4. **编译器两处漏**：① 台词没带 `(Sx)`（官方 `base-en:129` 要求编号写在 `<d>` 外）——B19 抓到；② 第 2 镜起**没有切镜动词** —— 穷举 **336/672** 组合同时报红抓到。另：`body` 没句号时会和运镜句粘成一句，亲眼读产出时看到。

### 分离门抓到的 1 个架构问题

`h3_base_compile` 一开始 `import h3_compile`，被 `model_separation_check` 判红
（它按文件名推家名，`h3_base_compile` → `h3_base`，算另一家）。
**门判得对**：共用件就该放中立文件。已搬进 `h3_common.py` 并登记进 `SHARED_STEMS`。
没走"给门开后门"那条路。

---

## 十一之二、Step 3 施工记录（2026-10-29 · 拆槽层，零费用）

把「顾客的话」变成编译器认的 spec。**两个文件，全部用桩模型验证，一次网络请求都没发**：

| 文件 | 干什么 |
|---|---|
| `app/services/h3_base_slots.py` | 严格 JSON Schema + `to_spec()` 收口 + `check_preserved()` 保真 + `extract()` 一步到位 |
| `scripts/test_h3_base_slots.py` | 21 组 / **45 条断言**，桩模型注入，红 0 |

`check_all --model h3` 现为 **通过 52 / 跳过 4 / 红 0**（新增「拆槽层自检」一项）。

### 两个入口，口径相反

| `kind` | 顾客给什么 | 规矩 |
|---|---|---|
| `rewrite` | **一段现成提示词**（豆包写的 / 网上抄的）—— 最高频 | 只做结构化和英文化，**不添任何内容**；环境声槽位空着就如实报出来，不替顾客编 |
| `idea` | 一句想法 | 允许补，但只补到"能拍"为止：不许编剧情、不许加人物、不许加台词（B27 三条护栏，`_GUARD` 字面进了 system prompt 并有断言守着） |

### 收口写在代码里，不靠模型自觉

模型返回的 JSON 一律过 `to_spec()`：镜头数截到 6、运镜不在官方 20 词就丢掉并告警、幅度/速度只认 4 个词、语言码认不出按有无汉字判、切点缺的按镜头数均分（补的是**时间**不是内容，且每次都报出来）、切点乱序调正、超时长报警。

### 两条客观护栏（这两条是"能机械对"的，不冒充"翻得好不好"）

1. **内容数字**：带量词或两位以上的数字（3 个人 / 1980 / 24H）必须原样出现在产出里；序数（「第1个」）不算，避免噪音。
2. **画面文字**：双引号 / `“”` / `「」` 里的招牌原样保留 —— 官方 `base-en:60` 允许招牌不翻译。

再加一条**不拦只报**的：正文引号外还有汉字时报警（官方 `h3-skill:33` 要求正文英文）。不拦是因为拦了等于吞掉顾客的话。

### 尺子自证（这条最关键）

「端到端过尺子红 0」只有在尺子**会响**时才有意义。所以同一份合法产出故意改坏三处 ——
正文中文化、自造运镜 `dollies in`、删掉 `non_diegetic_music` 字段 —— 尺子必须各报一次红。
三条都响了，好样本不响。**这一步不过，前面 3 条端到端的绿都是假绿。**

### 仍然没有的

- **真机 0 次**：所有 672 个组合都是本地编译，**没有一次真发出去过**。要花一次钱才能知道模型认不认。
- **拆槽层也是 0 次真调用**：45 条断言全用桩模型。**桩模型证明不了真模型会不会照 `_GUARD` 干活** —— 那要一次真调用。
- **I2VA 出不了片**：`models/h3.py` 从不发 `first_frame`，创作模式目前只出提示词。
- **还没接前端**：`extract()` 只有 Python 入口，没有 HTTP 路由，聊天框还没影。

---

## 十一之三、三家真机对照（2026-10-29，**花了约 1 毛钱**，主人批准）

5 段输入 × 3 家 = 15 次真实调用，全部成功。脚本 `D:/tmp/run_model_compare.py`，原始结果 `D:/tmp/cmp/`。

| 模型 | 通过尺子 | 平均耗时 | 平均长度 |
|---|---|---|---|
| doubao-seed-2.1-lite | 5/5（B28 未加前） | 4.6s | 652 字符 |
| doubao-seed-2.1-pro | 5/5 | 4.1s | 422 字符 |
| deepseek-v4.1-flash | 4/5（B3 红一次） | **2.0s** | 480 字符 |

**能下的结论（有数据支撑）：**
- 三家都能照 JSON Schema 输出、都能把顾客的招牌文字和数字原样留住
- deepseek 快一倍多（2.0s vs 4.1~4.6s）；pro 的产出最简洁
- deepseek 有一次把说话人写成中文「老板娘」放在 `<d>` 外 → B3 红（唯一一次红）

**不能下的结论：** 英文写得地不地道 —— 尺子判不了，只能人看。

### 这轮实测真抓到的东西：**6/15 份产出的运镜句读不通**

产出里出现 `The camera holds a static shot with small amplitude at slow speed the man on the platform.`
—— 目标成分**直接粘**在运镜句后面，没有连接词。

**为什么 22 条尺子一条都没响**：B12 只查"运镜词在不在闭集"，B13 只查"幅度/速度词对不对"，
**没有一条查句子能不能读**。这是判据真空，不是模型的问题。

**修了三处（都有官方出处）：**

| 位置 | 改法 | 出处 |
|---|---|---|
| `camera_sentence` 目标拼接 | 补连接词：Static Shot → `as`，其余 → `toward` | `base-en:122` `…toward the folded letter`；`base-en:124` `…as the runner exits the frame` |
| Static Shot 的幅度/速度 | **丢掉**（机位与镜头都不动，写幅度速度是自相矛盾） | `base-en:111` |
| Tracking Shot 带目标 | 写成 `The camera follows <目标>`，不再 `follows the subject toward X` | `base-en:107` |

**新增判据 B28**（运镜后接目标必须有连接词），并**拿已经抓到的 15 份真实产出去试**：
命中 **6/15**，和肉眼数的一致 —— 这条不是只为探针造的。

> ⚠️ 工程推断，已记在此备查：`toward` 官方只给了 push in 一例，其余运动类型沿用属推广。
> 官方对 pan 另给过 `, revealing the open doorway` 句式，暂未采用。

---

## 十一之四、接上入口（2026-10-29 · 「提示词优化」全链路通到页面）

### 分层调整：规则搬进 `app/`

判据要进**生产请求路径**（产出先过尺子，有红就重试），而 `scripts/` 不在包里，生产 import 不到。
所以把规则本体从 `ruler_h3_base.py` **逐字搬进** `app/services/models/h3_base.py`（481 行），
`ruler_h3_base.py` 只留官方校准 / 正反探针 / 多变数扫描 / 全维度穷举（测试代码）。

🩸 文件名必须叫 `h3_base.py`：分离门的家名由 `stem.removesuffix("_compile")` 推，
`h3_base_compile` → 家名 `h3_base`；新文件同家才允许互相 import。改名立刻被判红。

搬完回归：探针 23/23 · 官方案例 92 条判定 0 红 · 穷举 672/672 · 分离门 8 项全绿。

### 新建的 6 处

| 文件 | 干什么 |
|---|---|
| `app/api/prompt.py` | `GET /api/prompt/health` · `POST /api/prompt/optimize`，串四步 + 判红重试 |
| `app/services/models/h3_base.py` | 23 条判据本体（从 ruler 搬来） |
| `scripts/p18_check.py` | 接口层验收 29 条，桩模型零费用 |
| `frontend/.../pages/prompt/index.vue` | 页面：两种模式 + 时长 + 结果 + 复制 |
| `frontend/.../api/request.js` | 加 `promptOptimize`（**收 biz_code=0 和 2**，见下） |
| 首页卡片 + `pages.json` | 「提示词优化」入口，蓝紫卡跟「复刻爆款」并排 |

### 四步链路（大模型只在第 ① 步出现）

```
① 拆槽  大模型 → JSON 槽位（字段被 schema 锁死）
② 收口  运镜/幅度/速度/语言/切点 夹到官方闭集
③ 编译  按 base-en 模板拼三字段英文提示词
④ 自检  23 条判据；有红 → 把红的条目回灌，重试 1 次；还红 → 如实返回 biz_code=2
```

**为什么 `biz_code=2` 不能当失败**：那份提示词是能用的，只是有一条建议没过。
前端若按通用封装当失败，会把 data 丢掉 —— 所以 `request.js` 里单独写了 `promptOptimize` 收 0 和 2。

### 判据

`check_all --model h3` → **通过 53 / 跳过 4 / 红 0**（新增「提示词优化·接口层 29/29」）。

`p18_check` 的 29 条包括：健康探针 / 一次过不重试 / **判红后确实重试了一次** / 重试仍红不吞 /
空输入·未知 kind·未知画幅·超长输入 / 未配 key 直接拒 / 模型吐坏 JSON 明确报错 /
**模型白名单（3 个合法 key + 非法 key 被拒）** / **片长夹紧 4–15（下界·上界·越界如实说明）** /
**桩坏样本确实判红（证明"重试"那两条不是空跑）**。

### 🩸 事故纪录：我覆盖了已有的 `p17_check.py`（2026-10-29）

原来的 `p17_check.py` 是 **JPG 色度采样格式转正的验收**（D64-b，7 项），我新建接口层脚本时
**直接写了同名文件、没先看它存不存在**，原文件无备份 —— 这是真实损失，不是"改成新版"。

已恢复：把误写的文件 `mv` 成 `p18_check.py`，再**按 `docs/OPEN-DEFECTS.md:5529` 的描述逐项重建** p17。
重建后 `p17_check.py` = 8 条断言，且现场打印三份样本自证非空判：

```
good.jpg    pix_fmt=yuvj420p  320x240  needs=False
broken.jpg  pix_fmt=yuvj440p  320x240  needs=True   ← 改 SOF0 里 Cr 采样因子为 0x21 现造
fixed.jpg   pix_fmt=yuvj420p  320x240  needs=False  ← normalize_jpeg 转正后宽高不变
```

`check_all` 注册表里两者现在各占一行（`p17 JPG采样` / `提示词优化·接口层` → `p18_check.py`），
`--model h3` 全量回归：**通过 53 / 跳过 4 / 红 0**，两条各自独立跑（8/8 与 29/29）。

**以后开工前先 `ls` 目标文件名** —— 这个工程的 `scripts/pN_check.py` 是递增编号的历史关卡，
新关卡要**取下一个可用编号**，不许覆盖。

### 仍然没有的

- **真机 0 次**：29 条全用桩模型。真模型会不会照 `_GUARD` 干活，还得花一次钱才知道。
- **后端要重启才生效**（重启只能主人做）。

## 十二、铁律（与另外两份审计文档同一套）

1. **红 ≠ 顾客一定不满意，绿 ≠ 出来一定好看** —— 尺子只保证「格式没写错」。
2. **空集不算通过**：每组都报「实际跑了几条 / 期望几条」。
3. **一条红都不许留**：先判是尺子假红还是编译器真错，**不许为了变绿直接改尺子**。
4. **规则不许跨模式搬**：Ref2VA 的六段规则一条都不许进 base 模式（尤其 E13 风格句位置，方向相反）。
5. **官方没写的，不许当成"官方要求"** —— 写"工程推断"并说明理由。
6. **官方原样的不一致照抄**：`base-en:25` 的 `Picture 1` 不带尖括号，就照抄，不"修正"。
