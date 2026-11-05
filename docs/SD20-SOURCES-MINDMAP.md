# Doubao Seedance 2.0 官方资料 · 思维导图（2026-11-04 全量重拉版）

> 这份是**资料地图**，不是规则表。本文回答三件事：**官方到底有哪些 2.0 的资料 / 哪份最新 / 我们缺哪份**。
>
> 建立时间：2026-11-04（主人：「建一个 2.0 模型的导图，资料不够的就补齐」）
>
> 🩸 **2026-11-05 更正：`llms.txt` 不是全量。** 它 591 条，而方舟文档库（lib 82379）的目录树有
> **863 篇**——`real-person-ip-video-api`、私域人像素材库、版权 IP 视频整族都在索引外。
> 全量目录：`backend/data/official/sd-shared/DOCLIST.txt`；跨代共用资料：`sd-shared/pull-2026-11-05/`。
> **以后要"官方有没有写"这类判断，先查 DOCLIST，别只翻 llms.txt。**
>
> 🩸 **结论先写**：官方索引 `ark.volcengine.com/llms.txt`（631 行）扫过，2.0 相关 **15 篇共 12,363 行**已落地到
> `backend/data/official/sd20/pull-2026-11-04/`。本地原有的 `skills/sd2-pe/references/guide.md`
> 与官方今天的《Seedance 2.0 系列提示词指南》**逐字节相同**（sha256 `dd7fe63c…`）——
> 所以别再去别处找"更全的 2.0 提示词资料"，就是这一份。
>
> ⚠️ **2.0 与 2.5 不是一套**：参数、素材上限、分辨率、样片模式全都不一样。混用是 2026-10 付过代价的
> （`model_specs.py:21-38` 那段注释就是为这件事写的）。

---

## 一、总览树

```
Doubao Seedance 2.0 系列（火山方舟）官方资料
│
├── ① 模型与能力
│   ├── models-2-0.md ......................... 模型卡（doubao-seedance-2-0 / 260128）
│   ├── models-2-0-fast.md .................... 模型卡（快速档 / 260128）
│   ├── models-2-0-mini.md .................... 模型卡（性价比档 / 260615）
│   └── tutorial.md ........................... 系列教程（1,947 行）
│       ├── 模型能力对照表（:77 / :84）   ★ 三档差在哪（4k 只有标准版有）
│       ├── 全模态参考（:142）             ★ 图/视频/音频一起给
│       ├── 编辑视频（:546）               ★ 复刻换人走这条
│       ├── 延长视频（:873）
│       ├── 输出 4k（:1234）               ★ 10bit HEVC
│       ├── 联网搜索（:1558）
│       ├── 提示词 Skill（:1844）          ★ sd2-pe 官方安装法
│       ├── 提示词规则（:1862）
│       ├── 使用限制（:1868）
│       └── 常见问题（:1873 / 10bit 兼容 :1876 / 画面跳变 :1938）
│
├── ② 提示词（写 2.0 的词只看这一份）
│   └── prompt-guide.md ....................... 官方提示词指南（1,007 行）
│       ├── 基础公式（:12）
│       │   ├── 全模态参考（:18）· 编辑视频（:31）★ 复刻用这条
│       │   ├── 延长视频（:44）· 组合任务（:59）
│       ├── 进阶公式（:68）
│       │   ├── 定义主体（:88）★ 多主体必须能指代清楚
│       │   ├── 分镜时序（:125）★ 用「镜头1/镜头2」不说精确秒数
│       │   ├── 动作描述要求（:157）· 运镜写法（:189）
│       │   ├── 画质/风格/约束词（:198）· 实战案例（:215）
│       ├── 其他技巧（:251）：文字生成（:254）/ 延长 vs 拼接（:259）/ 素材配置（:267）
│       ├── 注意事项（:282）：语言规范（:285）/ 特殊字符（:290）
│       ├── 常见问题（:302）★ 稳定性全看这一节
│       │   ├── 人脸参考不准确（:305）· 字幕（:331）· Logo/水印（:346）
│       │   ├── 风格漂移（:354）· 延长衔接跳变（:368）· 双胞胎（:391）
│       │   └── 延长画质劣化（:426）· 特效不符（:445）· 参考人物过多（:464）
│       │       结尾噪音（:480）· 中文发音（:503）· 音色参考（:518）
│       └── 附录：提示词案例（:538 起）
│
├── ③ API
│   ├── api-create.md ......................... 创建任务（3,104 行）
│   │   ├── Body 参数（:93）→ content 组合（:99）
│   │   ├── resolution（:399）★ 2.0 有 4k，fast/mini 只到 720p
│   │   ├── ratio（:418）· duration（:481）★ 4–15 秒
│   │   ├── frames（:518）· generate_audio（:538，默认 true）
│   │   ├── watermark（:554）· seed（:582）· camera_fixed（:598）
│   │   ├── return_last_frame（:612）
│   │   ├── draft（:621）★ 样片模式**只 2.5 有**，2.0 系列写 true 会报错
│   │   └── service_tier（:640）★ 离线推理只 1.0 pro，2.0 系列不支持
│   ├── api-get.md ............................ 查询单个任务（454 行）
│   ├── api-list.md ........................... 查任务列表（839 行）
│   ├── api-cancel.md ......................... 取消/删除任务（174 行）
│   └── error-codes.md ........................ 全站错误码（265 行）★ 真人拦截/版权/任务类型
│
├── ④ 通用视频生成（2.0 也读，但按钮是全家共用的）
│   └── video-generation-tutorial.md ......... 2283 行
│       ├── 使用限制（:2111）★ 图片 1~9 张 / 视频 3 段总 ≤15s / 音频 3 段总 ≤15s
│       ├── 样片模式（:1844）★ 仅 2.5
│       └── 保存时间 / 限流（:2175 之后）
│
├── ⑤ 合规（真人脸）
│   ├── portrait-asset.md ..................... 三种合规通道总览（720 行）
│   └── real-person-asset.md .................. 本人扫码授权（168 行）
│
└── ⑥ 计费与平台
    ├── pricing.md ............................ 模型价格（577 行）
    └── model-list.md ......................... 全部模型 ID / 限流（786 行）
```

---

## 二、逐份说明（回答什么问题 / 记得看哪一段）

> 路径前缀统一为 `backend/data/official/sd20/`。

| 文件 | 回答什么问题 | 必看锚点 |
|---|---|---|
| `pull-2026-11-04/models-2-0.md` | 标准版 ID / 版本 / 任务类型 | 13 行全文；`doubao-seedance-2-0`、主版本 `260128` |
| `pull-2026-11-04/models-2-0-fast.md` | 快速版差在哪 | 继承 2.0 核心、生成更快；`260128` |
| `pull-2026-11-04/models-2-0-mini.md` | 性价比版 | `260615`；**三档里唯一标了 ImageToVideo 的也是它**（另两档卡片只写 TextToVideo，实际能力以教程对照表为准） |
| `pull-2026-11-04/tutorial.md` | **三档能力差在哪、每个任务怎么配** | 模型能力表 `:84`、全模态 `:142`、编辑 `:546`、延长 `:873`、4k `:1234`、提示词 Skill `:1844` |
| `pull-2026-11-04/prompt-guide.md` | **2.0 的提示词怎么写、写坏了长什么样** | 定义主体 `:88`、分镜时序 `:125`、素材配置 `:267`、常见问题 `:302–:537` |
| `pull-2026-11-04/api-create.md` | 每个请求字段的取值与限制 | `resolution :399`、`ratio :418`、`duration :481`、`draft :621`、`service_tier :640` |
| `pull-2026-11-04/api-get.md` | 轮询拿结果、拿尾帧 | 响应字段段 |
| `pull-2026-11-04/api-list.md` | 批量查任务 | 限流段 |
| `pull-2026-11-04/api-cancel.md` | 取消排队中的任务 | 全文 |
| `pull-2026-11-04/error-codes.md` | **报错码到底谁的责任** | 推理错误码表；真人/版权相关 |
| `pull-2026-11-04/video-generation-tutorial.md` | **素材上限、格式、保存时间** | 使用限制 `:2111`、图片 `:2128`、视频 `:2147`、音频 `:2170` |
| `pull-2026-11-04/portrait-asset.md` | 含真人脸怎么合法送进去 | 三种通道 |
| `pull-2026-11-04/real-person-asset.md` | 顾客本人授权怎么录 | 二维码 / 活体核验 |
| `pull-2026-11-04/pricing.md` | 一条片多少钱 | 视频生成价格表 |
| `pull-2026-11-04/model-list.md` | 型号 ID / 限流 | 搜 `doubao-seedance-2-0` |
| `skills/sd2-pe/SKILL.md` | 官方提示词优化 skill（2.0 专用） | 八要素 / 任务分类 / Step 0–3 工作流 |
| `skills/sd2-pe/references/guide.md` | **= 官方提示词指南，逐字节相同** | sha256 `dd7fe63c…`；行号与 `prompt-guide.md` 完全一致 |
| `skills/sd2-pe/references/trouble.md` | 官方排障手册（382 行） | 人脸/字幕/水印/跳变 |
| `skills/sd2-pe/references/tips.md` | 速查技巧（38 行） | 全文 |
| `skills/sd2-pe/references/camera-terms.md` | 运镜词表（32 行） | 全文 |

---

## 三、按「你要做什么」查

| 我要… | 看哪 |
|---|---|
| 判断这单该用 2.0 / fast / mini | `tutorial.md:84` 能力对照表 |
| 配分辨率 / 宽高比 / 时长 | `api-create.md:399` / `:418` / `:481` |
| 写换人 / 换装 / 换场景的提示词 | `prompt-guide.md:31` 编辑视频 + skill `sd2-pe` |
| 判断能不能上 4k | `api-create.md:399`（只有**标准版 2.0** 有 4k） |
| 想先出个 480p 预览省钱 | ❌ 2.0 **没有**样片模式（`api-create.md:621` 只列 2.5） |
| 想知道最多给几张参考图 | `video-generation-tutorial.md:2137`（2.0 全模态参考 **1~9 张**） |
| 想知道参考视频能多长 | `video-generation-tutorial.md:2148`（单段 2–15s，最多 3 段，总 ≤15s） |
| 排查「模型不听话 / 效果不稳」 | `prompt-guide.md:302–:537` 常见问题 12 条 |
| 排查报错 | `error-codes.md` |
| 真人脸 / 版权 | `portrait-asset.md` / `error-codes.md` |
| 算钱 | `pricing.md` |
| 看限流（会不会 429） | `tutorial.md:122–:135` 限流表（个人 180 RPM / 并发 3；4k 个人 15 RPM / 并发 1） |

---

## 四、2.0 自己的硬事实（和 2.5 逐项对照，别再混）

| 项 | Seedance 2.0 | 2.0 fast | 2.0 mini | 2.5（对照） |
|---|---|---|---|---|
| Model ID | `doubao-seedance-2-0`（260128） | `…-fast`（260128） | `…-mini`（260615） | `doubao-seedance-2-5`（260628） |
| 分辨率 | 480p / 720p / **1080p** / **4k** | 480p / 720p | 480p / 720p | 480p / 720p / 1080p（**无 4k**） |
| 4k = 10bit HEVC | ✅（`api-create.md:405`） | ✗ | ✗ | ✗（2.5 是 1080p 用 10bit HEVC） |
| 输出时长 | 4–15 秒 | 4–15 秒 | 4–15 秒 | 最长 30 秒 |
| 参考图上限 | **1~9 张** | 同 | 同 | 1~30 张 |
| 参考视频 | 单段 [2,15]s，≤3 段，总 ≤15s | 同 | 同 | 单段 [2,30]s，≤10 段，总 ≤30s |
| 参考音频 | 单段 [2,15]s，≤3 段，总 ≤15s | 同 | 同 | 单段 [2,30]s，≤10 段，总 ≤30s |
| 样片模式 Draft | ❌ | ❌ | ❌ | ✅ |
| 离线推理 `flex` | ❌ | ❌ | ❌ | ❌（只有 1.0 pro 有） |
| 单独传音频 | ❌（须配图/视频） | ❌ | ❌ | ✅ |
| 限流（个人） | 180 RPM / 并发 3；4k 档 15 RPM / 并发 1 | 180 / 3（无 4k） | 180 / 3（无 4k） | 180 RPM / 并发 3 |

> 🩸 **素材上限的出处是 `video-generation-tutorial.md:2137/2148/2171`**，
> 不是提示词指南里那句「总计 4-5 个素材（`prompt-guide.md:267`）」——
> 后者是**建议配置**，不是硬上限。两条别混。

---

## 五、本工程怎么用这份资料（2026-11-04 现状）

| 线路 | 现状 | 对应代码 |
|---|---|---|
| **提示词优化**（`/prompt/*`） | ✅ 在用 | `app/services/sd20_skill.py` → `models/volc20_pe.py`（规则校验，`RULES` 178 行起）；`api/prompt.py:44/580` |
| **复刻爆款**（换人/换装） | ✅ **已重新部署**（2026-11-04，三档全上） | `app/services/models/volc20.py` / `volc20_compile.py`（已从 `_archive/sd20/` 搬回并注册）；判据 `check_all --model volc20` **48 通过 / 4 跳过 / 红 0** |
| **型号参数** | ✅ 保留 | `app/services/model_specs.py`（2.0 与 H3 都是 4 人上限） |

**代码里引用的旧文件名对照**（历史注释用的是这些名字，别去盘上找不到就以为资料丢了）：

| 注释里写的 | 实际文件 |
|---|---|
| `seedance-20-guide.md:987` | `skills/sd2-pe/references/guide.md:987` = `pull-2026-11-04/prompt-guide.md:987`（"最多 3 段视频、总时长 ≤15 秒"） |
| `sd2-pe/SKILL.md` | `skills/sd2-pe/SKILL.md` |
| `volc20_compile.py:…` | `backend/app/services/models/volc20_compile.py`（2026-11-04 起在现役目录；`_archive/sd20/` 里那份是下架期的旧拷贝） |

---

## 六、两份快照的关系（重要）

| 位置 | 是什么 |
|---|---|
| `D:/tmp/official/sd20/` | **正本**。`model_separation_check.py:486` 只认这个目录（`OFFICIAL = Path("D:/tmp/official")`），清单/行数/sha 都由它校验 |
| `backend/data/official/sd20/` | **工程内镜像**（部署到服务器时正本不在） |
| `pull-2026-11-04/`（两边都有） | 2026-11-04 全量重拉的官方正文，**最新** |
| 根目录 `tutorial.md` / `video-gen-tutorial.md` | 更早的快照。**官方今天已小改**：教程 sha `594ec2ee…` vs 旧 `1cc95eb9…`；通用教程 `b6ab65a8…` vs 旧 `4a6cac97…`。引用行号时以 `pull-2026-11-04/` 为准 |
| 根目录 `guide.md` | 与 `pull-2026-11-04/prompt-guide.md` **逐字节相同**（`dd7fe63c…`），引用词可共用 `sd20-guide` |

> 判据：`python backend/scripts/model_separation_check.py` 全绿（三家 MANIFEST 与磁盘逐份一致）。
> 顺手清掉一份会引发"两份真相"的旧副本：`D:/tmp/volc_sd20_model.md`
> （与 `models-2-0.md` 逐字节相同、全工程 0 引用）→ 已挪到 `D:/tmp/_quarantine_20261104/`，没删。

---

## 七、缺什么 / 没抓什么

- **没抓**：`seedance-model-activation`（开通/退订说明）、`doc-skills`（Skills 目录页）、
  `usage-and-diagnostics`（arkcli 用量诊断）—— 这三篇是平台级通用页，2.0 没有专属内容。
- **没抓**：`video-fine-tuning-data-format`（精调数据格式，我们不训练模型）。
- **旧副本没有**：2.0 之前只有 skill 包，没建过 `pull-*`。这次是第一份官方正文快照。
- **skill 版本**：本地 `sd2-pe` 的 `guide.md` 与官方今日版逐字节相同；
  `SKILL.md` 未做逐字节比对（官方页面只给下载入口，没有版本号字段）。

---

## 八、怎么复现（下次重拉）

```bash
# ① 总索引（列全部文档；任一文档地址后加 .md 就是 Markdown）
curl -sSL --max-time 40 https://ark.volcengine.com/llms.txt -o ark_llms.txt

# ② 按需下载（示例：2.0 教程与提示词指南）
curl -sSL https://ark.volcengine.com/region:cn-beijing/docs/seedance-2-0.md -o tutorial.md
curl -sSL https://ark.volcengine.com/region:cn-beijing/docs/seedance-2-0-prompt-guide.md -o prompt-guide.md

# ③ 模型卡
curl -sSL https://ark.volcengine.com/models/doubao-seedance-2-0.md -o models-2-0.md
```

⚠️ 官方文档站 SSR，**不要**用 `tools/fetch_volc_doc.py`（那是拆 `_ROUTER_DATA` 的老路）；
直接取 `.md` 地址最省事，正文完整。

---

## 九、这次补齐的清单（15 篇 / 12,363 行）

| 文件 | 行数 |
|---|---|
| `api-create.md` | 3,104 |
| `video-generation-tutorial.md` | 2,283 |
| `tutorial.md` | 1,947 |
| `prompt-guide.md` | 1,007 |
| `api-list.md` | 839 |
| `model-list.md` | 786 |
| `portrait-asset.md` | 720 |
| `pricing.md` | 577 |
| `api-get.md` | 454 |
| `error-codes.md` | 265 |
| `api-cancel.md` | 174 |
| `real-person-asset.md` | 168 |
| `models-2-0.md` / `-fast.md` / `-mini.md` | 13 × 3 |
