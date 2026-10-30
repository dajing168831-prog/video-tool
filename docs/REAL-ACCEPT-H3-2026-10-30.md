# H3 提示词优化 · 真机验收（2026-10-30）

> 主人批的「B 组」四条路。全部打**跑着的后端** `127.0.0.1:8911` → 方舟，
> 模型显式传 `pro`（顾客会在前端选的那档），**不是本地桩**。
> 脚本：`temp/h3_real_accept.py`；原始响应：`D:/tmp/h3accept/*.json`。
> 素材**照抄现成的，一个字没改**：
> - 原稿 = 采集库 `视频-·-cinematic-narrative-short.md` 第一条（2,918 字，真·别家成稿）
> - 截图 = 现有成片 `render/722947…/out.mp4` 抽的一帧（68 KB）

## 结果

| # | 路 | 耗时 | 成品 | 判据 | 结论 |
|---|---|---|---|---|---|
| 1 | **转换** `/prompt/convert` | 216 s | 3,592 字 | **1 条红**（B12） | 跑通，**没收敛** |
| 2 | **修订** `/prompt/revise` | 131 s | 3,780 字 | 0 红 | ✅ 通 |
| 3 | **六段式 ref**（带参考素材） | 76 s + 79 s | 3,936 字 | 0 红 | ✅ 通（**首次真机验证**） |
| 4 | **体裁挑选**（纸艺定格） | 72 s + 79 s | 2,200 字 | 0 红 | ✅ 通（挑对了） |

## 逐条

### 1 转换：通了，但留了一条真红

- 第 1 次尝试 → `B11 切镜动词用官方 5 种` 红 → 回灌重试
- 第 2 次尝试 → `B12 运镜只取官方 20 个词` 红，句子是
  `The camera holds on the still ball.`
- **是真红不是误红**：官方 `base-en.txt:122` 的原句是
  `The camera holds **a static shot** as the runner exits the frame.`
  —— 官方要求点出镜头类型，模型这句只写了 "holds on"。
- 交付物 `biz_code=2`，前端会显示「1 条没过」并点名这句。

**根因**：输入 2,918 字、多镜头，**只回灌 1 次不够**把每一句运镜都改到闭集里。

### 2 修订：干净

拿第 1 条的成品 + 那张真截图，说「人物脸太假了，像塑料，别的地方不用动」：
3,780 字、0 红、结构仍是三字段（没被改散）。第 1 次尝试有红，第 2 次收敛。

### 3 六段式：第一次真机跑通

- 先问了一轮（说明参考素材的用法），补一句「8 秒 16:9 你定」后交付
- `kind=ref`，`subject_definitions` 在，3,936 字，0 红
- 读的是 `h3-prompt-writing/SKILL.md` + `references/ref-en.txt`（**通用包，没套体裁**）
- 🩸 之前只验过 ref 尺子本身的规则，**从没验过真模型能不能产出合规六段式** —— 现在验了

### 4 体裁挑选：挑对了

- 指令：「纸艺剪纸风格、定格动画质感……**不要真人也不要三维动画**」
- 读了：`paper-collage-explainer-generator` → `papercraft-stop-motion-explainer`
  → `h3-prompt-writing` + `base-en.txt`
- 成品开头：`Handmade paper-cut stop-motion animation, 16:9, a static miniature-stage sho…`
- 0 红。**对比 10-30 那次「金瓶梅→3D动画」的误判，这次体裁信号给足了，它就挑对了。**

## 三条观察（不是缺陷，是产品事实）

1. **真机上它总要先问一轮再出稿**（3、4 都是 ask → 追一轮）。顾客体验是「先问几个问题」，
   不是「一句话直接给」。
2. **贵的点在体裁那条**：第 4 条一次生成用了 **70,032 tokens / 6 次调用**；
   第 3 条 20,617 / 4 次。四轮 chat 合计 **162,210 tokens**（pro）。
3. **转换最慢**：216 秒。顾客要等 3 分半，页面上的「已 N 秒」提示是必要的。

## 还没做的

- 转换**收敛性**：要不要把回灌次数从 1 次加到 2 次？（会再多花时间和钱，需主人定）
- 转换/修订这两条路**没有 run_log**（只有 agent 那条有），所以这两条的 token 用量取不到。
- 9 个体裁包只真机验了 2 个（papercraft / 早前的 3D）。其余 7 个没验。

## 补跑：第 1 条换成 15 秒（2026-10-30，主人问「是不是你自己有问题」）

**是。我搭错了两处，而且揭出一个产品毛病。**

### 我的错

1. **源稿是 8 个 SHOT（2,956 字），我却按 `duration=5` 转。** 成品里模型只能把 8 个节奏点硬塞进
   `00:00.7 / 1.3 / 2.0 / 2.6 / 3.2 / 3.9 / 4.5 / 5.0`，每刀 0.6 秒 —— 这么赶，运镜句写得潦草很正常。
   这个 5 秒也不是我随手定的：**转换/修订这两条路，前端把片长写死成 `this.duration = 5`，
   界面上没有任何地方能改**（后面详细说）。
2. **只回灌 1 次**：每次都是修好一个红、冒出另一个（B11→B12 打地鼠），两次预算收不干净。

### 改 15 秒重跑的结果

| | 5 秒版 | 15 秒版 |
|---|---|---|
| 耗时 | 216 s | 292 s |
| 成品 | 3,592 字 · **1 个 `[Shot]`** | 4,651 字 · **8 个 `[Shot]`**（结构对上了） |
| 判据 | B12 红 | B12 红（**换了句**） |
| 红在哪 | `The camera holds on the still ball.` | `The camera tracks the dog as he runs out and returns.` |

**15 秒这版结构明显对了**（8 镜一一对应），但红还在 —— 而且这条红**站不太住**：

> `base-en:100-110` 的运镜表里，`Tracking Shot` = **"The camera follows a moving subject"**。
> 模型写的 `The camera tracks the dog` 就是这句话的动词形。表里只列了名词 `Tracking Shot`，
> 没列 `tracks` —— 尺子按字面判死。

这是**同一天第二次栽在「B12 只认字面」**（上午那次是 `uses a tracking shot` 被判红）。
一条 8 镜稿有约 8 句运镜，要求**每一句都逐字命中 20 个写法之一**，全中的概率本来就低；
再叠上「只回灌 1 次」，留红几乎是必然。

### 顺带查出的产品毛病（比上面那条重要）

`frontend/.../prompt/index.vue:280` `duration: 5` → 转换（`:478`）和修订（`:488`）都传它，
**界面上没有片长可选项**（时长选择器早先被拿掉了，只剩对话那条路由模型自己问）。
后果：**顾客粘一份 15 秒的分镜稿进来，也按 5 秒转，而且没有任何地方能改，模型也不会问。**

### 追加：B12 撤回（2026-10-30，主人：「我严重怀疑也是你制造的」）

查证结果：**成立。这条是我自造的。**

| 查什么 | 原文 |
|---|---|
| §4.3 表头 | **`Available Expression`**（可用表达）—— 词汇参考，不是白名单 |
| 有没有「只能用这些」 | **没有**。全节没有 must / only / required 之类的措辞 |
| 唯一带 `use` 的 | `base-en:92`「For ordinary cuts, **use** …」← 这是**切镜**，对应 B11（有依据，保留） |
| 唯一带 `only` 的 | `base-en:96`「Add amplitude and speed **only** when they are meaningful」← 说的是要不要加 |
| 官方对运镜写法的要求 | `base-en:117` / `ref-en:219`「write camera movement as **natural English**」← **鼓励自然写法** |

所以「运镜词不在那 20 个里就判红」跟官方自己的话是反的。同一天两次误红都出在这条上。

**已做**：
- 从 `h3_base.RULES` 删除 B12（尺子 **23 → 22 条**），`QUOTES` 同步删，探针删除
- 实现原文存档 `docs/_archive/b12-withdrawn-2026-10-30.md`
- `h3_base_compile.py` 里「官方给的是闭集，不是举例」这类**误导性注释**一并改掉
- 回归：`ruler_h3_base --probes` **22/22** · `p18` **68/68** · `check_all --model h3`
  通过 54 / 跳过 4 / **红 0**

**另外 21 条逐条对过原文**：全部有官方强制措辞（`always uses` / `must` / `do not` / `use` / 数字区间）。
只有 **B28（运镜后必须有连接词）** 是从官方 3 个例句反推的，没有「必须」原句撑腰 ——
但它依据的是 `base-en:117`「written as a natural English action」（句子要能读通），
**先留着，你要撤也一句话的事**。

## 对照实验：同一条原稿，代码路 vs 交给 agent（2026-10-30，主人批「跑」）

问的是主人那句话：**「从另一家标准提示词转换成另一家的提示词就这么难吗？」**
做法：同一条原稿（2,918 字，8 镜），一条走 `/prompt/convert`，一条走对话路让 agent 自己读
H3 skill 转。顾客口吻只说一句：**「换成 H3 能用的格式，内容一个字都别改」**。

脚本 `temp/agent_convert_try.py`；原始响应 `D:/tmp/h3accept/5-agent-convert.json`。

| | 代码路 `/prompt/convert` | agent（对话路） |
|---|---|---|
| 耗时 | 292 s | **126 s**（问一句 33 s + 出稿 93 s） |
| 成品 | 4,651 字 | 3,247 字 |
| 原稿 31 句保住几句 | **22 / 31（71%）** | **27 / 31（87%）** |
| 原稿没有、自己加的句子 | **28 句**，其中 5 句是纯自创运镜 | **5 句**，全是转换必需的（三字段名 / 切镜 / 声音段） |
| 8 镜结构 | 8 个 `[Shot]` | 8 个 `[Shot]` |
| 片长 | **写死 5 秒**（我手动改 15 才跑对） | **它主动问「多少秒」**，答「你定」它定 15 秒 |
| 花费 | 取不到（这两条路没 run_log） | 53,995 tokens（20,369 + 33,626） |

### 差距在哪：代码路自己编运镜

代码路成品里这 5 句**原稿根本没有**、是模型自己补的：

```
The camera remains in a static shot, keeping the dog in shallow focus beyond the girl's shoulder.
The camera trucks left with small amplitude at slow speed to keep her and the dog in frame.
The camera remains in a static shot as the ball slows and stops directly in front of the dog's trembling paws.
The camera tracks the dog as he runs out and returns.
The camera remains in a static shot with shallow depth of field, keeping her smiling face …
```

原稿 8 个 SHOT 只写了「Extreme low-angle close-up」这种机位，**没有一句运镜指令**。
转换这条路的本职是「只拆结构、只拼装」，补运镜 = **加内容**。
agent 那版一句运镜都没编，原稿句几乎逐字搬过去。

⚠️ **公平说明**：代码路那次跑的时候 B12 还没撤，所以它「1 条红」不是现在的行为；
而且**它判红抓的正是上面这几句自己编的运镜** —— 自造规则去卡自造内容，两次都是我的问题。

### agent 的两处真损失（如实记）

1. 原稿 CONSISTENCY 段被并进 Shot 1（H3 没有一致性段，这是对的），
   代价是 Shot 6「她仍穿军绿外套/卡其裤/棕靴」这种**回填**没有了 —— 代码路补了，agent 没补。
2. `Audio: ONLY natural breathing, house ambience, dog sounds, foots` 这句两边都没保住 ——
   **原稿本身就是断的**（采集那段代码块停在 `foots`），不是模型丢的。

### 结论

「转换」这个活，**agent 那条路已经是能用的**：顾客粘一份别家稿、选 H3、说一句「换格式别改内容」，
它读 skill → 问时长 → 出稿，0 红、两分钟、内容保真 87%（代码路 71%）。
代码路会自己加内容，跟「只搬运不改写」这个诉求方向是反的。

另外顺带解决了一个产品毛病：**代码路把片长写死 5 秒、界面改不了；agent 会主动问。**

### 追加：裸粘稿也不带指令会怎样（定改法用）

| 怎么发 | 原稿句保住 | 自己加运镜 | 判红 | 耗时 |
|---|---|---|---|---|
| 只粘稿，一句话不说 | 21/31（**68%**） | 有 | 1 条 | 43 + 154 s |
| 粘稿 + 「……换成 H3 能用的格式。内容一个字都别改……」 | 27/31（**87%**） | 没有 | 0 条 | 33 + 93 s |
| 代码路 `/prompt/convert` | 22/31（71%） | **5 句自创运镜** | 1 条（规则已撤） | 292 s |

原始响应：`D:/tmp/h3accept/6-agent-raw-paste.json`（裸粘）、`5-agent-convert.json`（带指令）。

**落地**：转换这条路从产品上摘掉，粘稿一律走对话路，**顾客写什么发什么，一个字不加**
（我先试过自动补那句意图，主人否掉：「不需要你加这些规则，顾客自己会知道怎么告诉 agents」）。
详见 `docs/MODEL-SEPARATION.md` §13.15；判据 `tools/e2e/prompt-paste.js` 4/4。
