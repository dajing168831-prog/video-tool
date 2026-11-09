# 竞品能力全景 ↔ 我们的落点（clipforge 全量）

> 2026-11-06。主人原话：「**是全部能力都开发出来，因为我现在发现你好像还是掐头去尾的开发单一功能**」。
> 这张表的唯一用途：**让「还差什么」一眼可数，不再靠主人一个个发现**。
>
> **口径**（可 grep 复验）：`src/app/api` **72** 路由 / 8,037 行；`src/app` 页面 **18** / 14,738 行；`src/lib` 非测试 **199** 文件 / 37,961 行；`src/lib/__tests__` **139** / 13,983 行。
> 逐文件笔记见 `D:/skills/product-drama/docs/CLIPFORGE-FILE-NOTES.md`（147 篇 / 2,439 行）。
>
> **判定只有四态，不许混**：
> ✅ **已做**（能指出我们的文件:行）· 🟡 **能做待做**（技术可行，排期即可）· 🔴 **做不了**（带官方出处）· ⏸ **待拍板**（涉钱 / 涉许可 / 改产品定位）
>
> ⚠️ 第 4 列「我们的位置」为空 = 还没接；写「另一条线」= 本仓有但不在商品短剧链上。

---

## A. 项目与内容（内容层，8 项）

| # | 竞品能力 | 出处 | 我们的位置 | 判定 |
|---|---|---|---|---|
| A1 | 项目 CRUD + 三步入场（商品来源 / 商品信息 / 视频配置） | `api/project/route.ts`、`api/project/[id]/route.ts`、`app/project/new/page.tsx` | `api/drama.py:363` 创建、`:469` 详情、`:482` 删除、`:424` 改商品 | ✅ |
| A2 | 商品链接解析**优先级链**（JSON-LD → OG → 微数据 → LLM 兜底） | `lib/product-ingest.ts:1-186` | `services/drama_product_ingest.py`、`POST /api/drama/import-url`、前端导入提示 | ✅ 四层逐条照抄：JSON-LD（含 `@graph`/数组递归）→ OG → Twitter Card → `<title>`；单遍实体解码、meta **引号回引用**（`Tom's Mug` 不截断）、价格格式化、图片绝对化去重、坏 JSON 跳过。🩸 能力表原写「微数据 → LLM 兜底」，但**竞品源码里没有这两段** → 照源码不编，抓不到就留空让用户手填（C10）。抓取仍走 SSRF 校验（只收公网 http/https） |
| A3 | 商品库（跨项目复用商品卡） | `app/products/page.tsx`、`web/lib/db/schema.ts` products 表 | `services/drama_product_lib.py`、`/api/drama/products` 6 条路由、前端「商品库」卡 | ✅ 文件库 `data/drama/products/index.json` + 每卡独立图片副本（**存/取都复制不移动**，删卡不影响项目图）；字段 name/points/facts/audience/category/price/platform + 最多 5 张图；列表按更新时间倒序；应用时只覆盖商品字段、不清空项目其他内容 |
| A4 | 剧本生成入口（分阶段 + 断点续跑） | `api/llm/script/route.ts`、`lib/script-engine/generator.ts` | `api/drama.py:498 generate`（stage 分阶段）、`:546 reset` | ✅ |
| A5 | **品类模板 5 类 / 22 条 + 5 条品类指令**（不同品类的钩子/证据/场景先验） | `lib/script-engine/templates/`（5 个品类文件 + `index`） | `app/data/category_templates.json`（22 条原样抽）、`services/drama_category_templates.py`、`api/drama.py` 剧本段注入 + 新建表单「品类套路」 | ✅ 类目换算复用 `drama_templates.CATEGORY_MAP`（digital→tech）；「其他」**不注入**（竞品会回落 beauty，我们明说不套） |
| A6 | 话题 → 剧本（无商品也能起片） | `api/topic/script/route.ts`、`app/project/topic/page.tsx` | `services/drama_topic.py`、`api/drama.py`（`GET /topic/options`、`POST /topic`）、话题项目卡 | ✅ 独立体裁（不复用 `BASE_SYS`、不走结构卡）；五种旁白风格、20/30/45/60 档、一次写 N 版、一次调用 `content_type="topic"` |
| A7 | 多版脚本管理（同一项目多稿对比/切换） | `api/project/[id]/scripts/route.ts` | `doc["scripts"]` 版本栈（≤12）+ `GET /projects/{id}/scripts`、`POST …/{sid}/select`、`DELETE …/{sid}` | ✅ 切版本时判「分镜过期」；**不照抄竞品「重生成先删旧版」**，旧稿留着 |
| A8 | 手写脚本 → 直接出片 | `api/project/[id]/import-script/route.ts`、`lib/script-import.ts` | `services/drama_import.py`、`POST /projects/{id}/import-script` | ✅ 竞品切分口径（CJK 5 字/秒、拉丁 14 字/秒、100 字/镜、40 镜封顶）+ 我们自己的单镜下限 4s；产物过 `validate_storyboard` |
| A9 | 四判官 + 重写对照 + 三档采纳 | `api/project/[id]/script-judge/route.ts`、`lib/script-judge.ts:1-296` | `api/drama.py:575 judge`、`:601 judge_apply`；**我们五位**（多视觉） | ✅ **超集** |
| A10 | **模板经济**：391 个成片模板 + AI 定制 + 导入导出 + 打包 + 已用次数 | `lib/ad-templates.ts`（5,885 行）、`api/ad-template/{generate,mine}` | `app/data/ad_templates.json`（391 条原样抽）、`services/drama_templates.py`、`drama_template_store.py`、`drama_script_templates.py`、`api/drama.py`（11 条路由）、`pages/drama/index.vue` | ✅ 主人 2026-11-06 拍板「直接接」。四件齐：391 条配方（分组/搜索/类目加权/关键词推荐 +2/+3/−2）、AI 定制（词表约束 + `sanitize` 夹取）、分享/打包（单条 + 整包信封、剥 id、广告法只警告）、我的模板（服务端落盘）+ **剧本结构模板**（存分镜节奏 → `【参考爆款结构】` 注入） |

---

## B. 素材（输入侧，11 项）

| # | 竞品能力 | 出处 | 我们的位置 | 判定 |
|---|---|---|---|---|
| B1 | 素材上传（图/视频/音频，MIME + 扩展名双白名单） | `api/upload/route.ts`、`api/products/upload/route.ts` | `api/drama.py` 商品图 `uploads`/`images`（10MB，JPG/PNG/WebP）+ `POST /projects/{pid}/materials`（80MB，mp4/webm/mov/m4v + 图）+ `POST /projects/{pid}/bgm`（mp3/wav/aac/m4a，20MB） | ✅ **三路都收**：图走商品图/素材库，视频走素材库，音频走 BGM；扩展名 + **ffprobe 真实格式**双查 |
| B2 | 本地素材库（自定义分类 + 元数据 + 批量导入） | `assets/_components/local-material-library.tsx`（668 行）、`api/project/[id]/materials` | `services/drama_materials.py` + `GET/POST/PATCH/DELETE /projects/{pid}/materials` + 前端「素材库」卡 | ✅ 内容寻址（sha256 文件名，重复上传返回 duplicate 不重写）+ 临时文件校验通过才发布 + sidecar 存原名/标签/宽高/时长 + 标签 ≤12×32 + 单文件 ≤80MB；**另加**出处字段（author/license/source_url）给 B5 用 |
| B3 | **免版权素材搜索：10 个源 + 许可证硬过滤**（Jamendo 去 NC/ND/SA、Freesound 只 CC0/BY、Archive 强制 publicdomain） | `lib/providers/`（pexels/pixabay/openverse/wikimedia…）、`api/stock/search/route.ts` | `services/drama_stock.py`（10 源归一化 + 许可硬过滤 + 并发聚合 + 5 分钟缓存 + 下载闸）· `GET /stock/sources` · `POST /projects/{pid}/stock/search` · `POST /projects/{pid}/stock/import` · 前端「免版权素材」卡 | ✅ 十源全接。**4 个免 Key 源真联网验过**（Openverse / Wikimedia / NASA / Archive，含真下载）＋ 本地素材池当源；5 个要 Key 的（Pexels/Pixabay/Coverr/Jamendo/Freesound）走环境变量，没 Key 就自动跳过并标「需 Key」。导入只传 `source+media_type+id`（服务端缓存取回，前端改不了地址/许可），下载前拒内网地址。图/视频进素材库带出处（B5 清单读得到），音频进 BGM 位并登记署名。🩸 Wikimedia 按 TLS 指纹拦 httpx（固定用 requests）+ 下载要 UA 带联系方式（`STOCK_USER_AGENT`） |
| B4 | 自动配画面（降级阶梯 original/narrowed/universal，**诚实标注**） | `lib/stock-matcher.ts:1-221`、`api/project/[id]/stock-fill/route.ts` | `services/drama_materials.auto_match` + `services/drama_film.shot_materials` + `GET/PUT /projects/{pid}/shot-materials` + `POST …/shot-materials/auto` + 前端「自动配画面 / 配画面」 | ✅ **走「每镜参考图」路线**（我推荐的两条路之一，主人 2026-11-06 回「继续」后落地；见文末说明）：素材图作为**某镜的场景参考**进出片提示词与上传序列（板 → 商品 → 人物 → 每镜画面 → 尾帧），人脸仍只认人物参考图。诚实标注 = **命中词数**（本地池版 `auto_match`）；**0 分不配**、一镜一张、跨镜去重、手选不被覆盖；换素材图会进 `plan_hash`（提示词一字不变也必须作废旧确认卡）。**第十一批补完**：`services/drama_stock_fill.py` + `POST /projects/{pid}/stock/auto-fill` + 前端「自动配画面」按钮 —— 逐镜**联网搜库**并走竞品那套三档降级阶梯（原文 → 中文动词断句取名词块 / 商品名主题锚 → 英文通用兜底），每镜结果带 `query` + `level`（original/narrowed/universal）**诚实标注**；跨镜不重复用同一份素材；**通用兜底默认只报告不绑定**（我们的素材图是喂 AI 的场景参考，硬塞不相关图会污染提示词），显式 `allow_universal` 才绑。默认仍只配**图片参考画面**（不改出片段数），`media_type="video"` 才配实拍画面。**两条路都做了**：图片→参考图（第八批）、视频→**当这一镜的画面**（第九批，`shot-clips`：该镜从 AI 出片里拿掉、合成时按镜头时长变速/补帧插进时间线） |
| B5 | 授权清单（来源/作者/许可/商用风险/可复制署名行/导出 md） | `lib/asset-credits.ts:1-247`、`api/project/[id]/credits/route.ts` | `services/drama_credits.py`、`GET /projects/{pid}/credits`（`?format=md` 直接给 Markdown）、`POST /projects/{pid}/bgm/credit`、前端「授权清单」卡 | ✅ 三档风险 + NC/ND 一律 review + 四类许可白名单 + 署名行 + 汇总 `commercialSafe`；**发布门禁直接读这一份**（`drama_compliance.gate_from_credits`）。🩸 与竞品一处不同：使用者自传的 BGM 没申报出处时按自有素材判 ok（竞品曲子来自 stock 曲库，所以那边「许可不明」是真风险） |
| B6 | 导入自有视频（1GB / 2 小时，流式落盘 + probe 校验） | `api/project/[id]/media/route.ts` | 另一条线（`services/transcript.py`） | ✅ **（第十二批）** 流式落盘：边写边计数（`content-length` 声明超限先拒，实收再拦——防撒谎头），写完真实解码校验（宽高 > 0 且时长 > 0，坏文件当场删）+ 时长闸 >2h 拒；**独立索引 `data/drama/media/<pid>/index.json`，不和素材库混**（长视频原料 vs 小素材 —— 能力表这条本来就要求分开）；取播放走 FileResponse（支持 Range，能拖进度条）。下游 B7 / B8 接这个索引 |
| B7 | 转写（分块追加 + 检查点） | `api/project/[id]/media/[id]/transcript/route.ts` | `services/transcript.py`（整段同步，≤30 分钟，另一条线）+ **第十三批新增** `services/drama_media_transcript.py` | ✅ **（第十三批）** 每块 **5 分钟**（`transcript-checkpoint.ts:11` 原值），ffmpeg 按块切 16k 单声道再识别，块内时间加起点偏移并裁到块末端；**每块落一次检查点**，中断从断点接着来；检查点清洗照 :61-104（model / language 对不上整份作废、字按进度 +0.25 秒截断）、追加照 :106-146（进度必须推进、块要和窗口重叠、拼完排序去重）、还原照 :148-162；并发上限照 `transcript.py` 的 `_SEM`；中断判定照 `media/route.ts:56-59`（transcribing 但没活任务 → failed） |
| B8 | 按文字剪（关键词 ≤160 字 → 5–120s 片段） | `api/.../clips/route.ts`、`src/lib/transcript-clips.ts` | 另一条线 + **第十四批新增** `services/drama_clips.py` | ✅ **（第十四批）** 参数闸照 `clips/route.ts:24`（≤160 字 / 5–120 秒 / 1–12 个），没转写完不给（:30-31）；找片段算法照 `transcript-clips.ts` 全文：NFKC+去空白归一、中文不加空格拼词、句末/停顿 0.8s/8 秒/80 词四种断法切 unit、向后找最接近目标时长的短语边界（**不跨 >3 秒静默**、到 1.35 倍就停）、前后 0.12/0.18 秒呼吸夹在邻词边界内、排序分 = 说话占比 − 时长偏差 + 句末 0.2 + 停顿 0.1、重叠 >50% 去重；**比竞品多一步**：竞品只给建议（真剪在 `transcript-render.ts`），我们把「剪出来」做成一步 —— 本地 ffmpeg 重编码导出 mp4（不用 `-c copy`，关键帧不在切点上会多一段），可直接打开/下载 |
| B9 | 时间线导出 OTIO / EDL / CSV | `api/.../timeline/route.ts`、`src/lib/timeline-export.ts` | 另一条线 + **第十五批新增** `services/drama_timeline.py` | ✅ **（第十五批）** 三种格式照 `timeline-export.ts` 全文：OTIO（Timeline.1 / Stack.1 / 视频·音频·字幕三轨 / ExternalReference 按文件名 relink / Gap / Marker）、CMX3600 EDL（`NNN AX AA/V C 源入 源出 记录入 记录出` + FROM CLIP NAME / TRANSCRIPT / CAPTION / BEAT）、CSV（12 列 / UTF-8 BOM / CRLF）；帧率 1–240 否则 30、时间码 `HH:MM:SS:FF`；没转写不给导（`route.ts:38-40`）、没区间 422；**我们的差异**：没有删词计划，保留区间来自 B8 已剪片段（也可手传），成片（AI+素材混排）时间线导出**没做** |
| B10 | 爆款复刻（参考视频 → 结构分析 → 复刻） | `api/replicate/analyze`、`api/project/[id]/replicate/save`、`app/project/clone/page.tsx` | **另一条线**（`api/clone.py`，H3/SD 复刻已成熟） | ✅（另一条线） |
| B11 | 媒体解构实验室 | `app/media-lab/page.tsx`、`api/media/analyze/route.ts`、`lib/media-analysis.ts` | **第二十四批新增** `services/drama_media_lab.py` + `POST /media/analyze` + `PATCH /projects/{pid}/production` + 前端「媒体解构」卡 | ✅ 一张图 / 一段视频（≤3 分钟）→ 摘要、主体标签、画面四格、动效三格、可复用提示词、反向提示词、适用场景。参数照 `route.ts`：图 15MB / 视频 80MB、JPG/PNG/WebP/MP4/WebM/MOV；视频先抽 **8 帧 / 缩略 200 / 波形 100** 拼速览，再把「时长 + 切点数 + 采样时间」当上下文；漂移 JSON 按 `media-analysis.ts` 收敛（摘要 600、标签 120×8、场景 5 条）。🩸 **Key 只从服务端读**（竞品让前端把 llmConfig 连 Key 一起发）；上游原文只进日志；「不认人、不猜身份」写进提示词 |

---

## C. 生成（画面侧，17 项）

| # | 竞品能力 | 出处 | 我们的位置 | 判定 |
|---|---|---|---|---|
| C1 | 多厂商图片生成（多参考图**保序**，本地图转 data URI） | `api/ai/image/route.ts`、`lib/providers/*` | `services/ark.py generate_image` | ✅（只火山） |
| C2 | 多厂商视频生成（**两阶段 submit + wait**，任务 ID 先落盘） | `api/ai/video/route.ts`、`api/ai/video/task/route.ts`、`lib/providers/types.ts:1-288` | `services/ark.py`（火山 2.0/2.5）、`services/minimax.py`（H3） | ✅ |
| C3 | 模型目录 / 单任务状态 / 在飞付费任务视图 | `api/ai/{models,status,tasks}` | `api/drama.py GET /tasks`（跨项目在飞登记，`film.running`）+ `POST /projects/{id}/tasks/clear` | ✅ |
| C4 | 平台 Key 连通性校验（服务端探针，12s 超时，**上游错误不外泄**） | `api/ai/test-provider/route.ts`、`api/llm/test/route.ts` | **第二十三批新增** `services/drama_probe.py`（4 通道登记 + 只读探针；MiniMax 属 H3 视频线，本产品不列）+ `GET/POST /probe` + 设置卡「测连通」/「全部测一遍」 | ✅ LLM 用 `max_tokens=64` 真补全，触顶 400/422 去上限重试一次，仍触顶判 ok+warning（会被截断）；平台打 `/models`，401/403 → invalid，2xx 普通平台 → ok，**ark 2xx 也只判 unknown**（`/models` 证明不了出图/出片权限）；只回 `configured` 布尔，Key 只从服务端读，上游原文只进日志；没有只读端点的 voice/MediaKit/MiniMax 标 `unsupported` 带原因，不编假探针 |
| C5 | **素人主播库（6 个预设 + 反 AI 脸硬约束）** | `lib/presenters.ts:57-106` | `services/drama_presets.py`（逐字抄） | ✅ |
| C6 | **2×2 四视图定妆照**（正面/左侧/背面/肩部特写） | `lib/character-sheet.ts:21-38`、`api/characters/sheet` | `services/drama_sheet.py`、`api/drama.py:1057` | ✅ |
| C7 | 九宫格分镜（3×3 锁人锁景锁光） | `api/project/[id]/storyboard-grid/route.ts`、`lib/storyboard-grid.ts` | `services/drama_grid.py`、`api/drama.py:720` | ✅ |
| C8 | 一键整片 | `api/project/[id]/storyboard-film/route.ts`、`lib/storyboard-film.ts:1-412` | `services/drama_film.py`、`api/drama.py:1188` | ✅ |
| C9 | **接缝三档 pin / tail / off**（尾帧接下镜首帧） | `lib/storyboard-film.ts`（seam）、`assets` 页 | 无。**严格版（像素级）做不了；间接版能做**（把上一镜尾帧当参考图 + 提示词指定为首帧，官方明说可「间接实现」） | ✅ **间接版已落地**：`film/plan?chain=tail` + `drama_film.build_prompt(tail_ref=)`（上一段真实尾帧 `.last.jpg` 当参考图，提示词指定 @图片N 为首帧）；严格首帧与全模态参考在 `ark.py:236-237` 互斥，故不做静默降级。见 §附录-1 |
| C10 | 命名运镜库（可叠加两层，只列不冲突组合） | `lib/camera-presets.ts:1-370` | 分镜里自由写「运镜：」，无预设库 | ✅ `services/drama_camera.py`（22 条 + 冲突判据 + 两层叠加 + 词表块注入分镜提示词） |
| C11 | 画面 Look（14 种全局光线色调，图生视频时锁光） | `lib/look-presets.ts:1-269` | 无 | ✅ `services/drama_looks.py`（14 种）。**三段都已接线**：出图段在 `drama_grid.prompt` 末尾、光锚在 `drama_film.build_prompt` 末尾、opener（real 组 6 种）前置在最前；没选模板时两处都空，提示词与以前逐字一致 |
| C12 | 真实感层三档（自动/仅约束/关；材质/物理/活背景/情绪过程） | `motion-prompt.ts:53-70 / 150-260`、`emotion-acting.ts:26-90`、`lib/presenters.ts:130-136` | **第二十五批新增** `services/drama_realism.py`（三档 + 品类约束 5 类 + 物理动作 15 条 + 活背景 6 条 + 发丝衣料惯性 + 情绪六档）+ `drama_film.build_prompt(realism=)` 逐镜接线 | ✅ **三档真落地**：`auto` = 品类材质约束 + 物理交互 + 活背景 + 发丝衣料惯性 + 情绪过程；`constraints` = 只加品类材质约束；`off` = **逐字等于老提示词形状**（回归对照过）。镜型靠 `purpose`/分镜 `product` 字段/角色名归一到竞品六种 hook/pain_point/product_reveal/demo/social_proof/cta；🩸 **只映射语义真正对齐的三拍**（矛盾升级→pain_point、商品登场→product_reveal、反转爽感→demo），冲突爆发→hook / 收束→cta 会给吵架镜塞「眼睛发亮」、给落败角色塞「自信」→ **不映射**（注释写明理由）。三档在出片面板可点、存进项目与全局默认 |

| C13 | **窗口精准修复**（坏 2–4 秒只重做那段） | `api/project/[id]/repair/route.ts:1-246`、`lib/video-repair-plan.ts` | `services/drama_repair.py`、`api/drama.py:1414/1449/1516` | ✅ |
| C14 | **单变量重投**（选一个症状 → 只改一个变量） | `lib/retake-patch.ts:1-114`、`lib/emotion-acting.ts` | 修复线已是「只换一项」 | ✅ |
| C15 | 变体矩阵 A/B（同素材只重跑合成） | `lib/variation-plan.ts:1-115`、`video` 页 | `services/drama_variants.py`、`POST /variants/plan`、`POST /variants/render`、`GET /variants/{idx}/file` | ✅ **不花生成费**：轮的是合成四维（转场/字幕/渲染档/BGM），复用 `compose_run` 逐槽跑；mulberry32 确定性 PRNG + 不同起点轮转，主合成状态跑完恢复 |
| C16 | 生成参数吸附 + 模型能力预检（规格已确认/按模型识别/未知 + 四条适配 + 五条警告） | `lib/gen-params.ts:1-265`、`lib/model-capabilities.ts:1-214` | `services/model_specs.py`（参考图上限 + 尺寸）· `services/drama_preflight.py`、`GET /model-capabilities`、`POST /preflight`、出片区「能力预检」卡 | ✅ 三档置信度（已知 / 推定 / 未知）+ 四类改写（clamped-duration · mapped-resolution · adaptive-ratio · unsupported-last-frame）+ 五类告警；分辨率「盖得住的最小档，盖不住取最大档」；**页面上字段与原因都写中文** |
| C17 | 云端任务恢复（已提交未取回单独列，「请勿重复提交」） | `api/ai/tasks?active=1` | **第二十三批新增** `services/drama_tasks.py` + `POST /projects/{pid}/tasks/{no}/resume` + `ark.fetch_task/retrieve_task`；`GET /tasks` 改为扫盘（项目 JSON 的 `film.running` × `<out>.task.json`） | ✅ 只分 `submitted`（有任务号可领回）/ `unknown`（任务号缺失，先去平台确认）——**不编 `processing`**（我们不做轮询）；领回只查询 + 下载，**绝不重新提交**（不重复付钱）；还在跑如实回报，失败/失效不自动清登记；前端不选项目也能看到「云端任务恢复」卡 |

---

## D. 合成与音频（后期侧，10 项）

| # | 竞品能力 | 出处 | 我们的位置 | 判定 |
|---|---|---|---|---|
| D1 | TTS 配音（免费 5 音色 + 付费） | `lib/tts.ts:1-408`、`api/tts`、`api/tts/free`（Edge TTS 防 SSML 注入） | **第十六批新增** `services/drama_tts.py` + 4 条路由 | ✅ **（第十六批）** 免费 Edge 朗读（**11 个音色**：中 5 / 英 3 / 日 / 韩 / 西），**真联网验过**（中文 20,736 字节 mp3 + 8 个字级时间戳，英文 17,856 字节）；付费四家（OpenAI 兼容 / Atlas / MiniMax T2A v2 / fal）照 `tts.ts` 逐条落地（情绪只送官方枚举、`instructions` 只送支持的模型、hex/data URI/URL 三种音频体都解）；内容寻址缓存（同文本同音色不重复计费）+ 连续 2 次失败熔断 30 秒 + 只对 408/429/5xx 重试；`[pause]` 换气标记只有免费这条渲染成 350ms 停顿，别处一律剥掉；SSML 全量转义防注入 |
| D2 | BGM（5 情绪 + 闪避 ducking + 强度） | `api/project/[id]/bgm/route.ts`、`lib/audio-mix.ts` | `services/drama_audio.py`（音量夹 0.05–0.40 / 默认 0.18 / 有对白才闪避）+ `drama_compose` 混音（aloop / 3s 淡出 / sidechaincompress）+ `POST /bgm` 上传 | ✅ |
| D3 | 人声落地（voice-ground，防人声「飘」） | `lib/video-composer/voice-ground.ts:1-35`、`composer.ts:525-548` | **第十六批** `services/drama_tts.py`；**第二十五批新增** `services/drama_voice.py` + `drama_compose` 音频段接线 | ✅ **已接进合成链**：逐句 TTS 落盘 `<data>/voice/<pid>/<shot_id>.mp3`（含实际时长），合成图按镜给槽（配音过 `voice_ground_chain`，没配音填 `anullsrc` 静音占位，逐镜 `atrim` 到缩放后的槽位再 concat，最后 pad/trim 到段实际时长防累加漂移）；整条时间线垫 `room_tone_source` 棕噪（**有 TTS 0.008 / 仅原生声 0.004**），顺序照 `composer.ts`：接音轨 → 底噪 → BGM。`voice_ground:false` 显式关掉逐字回到老图形；`GET /drama/tts/ground` 已标 `wired:true` + 指向合成 |

| D4 | 字幕烧录 + **四种预设**（标准/重击大字/极简/卡拉OK逐字） | `lib/caption-presets.ts:1-59` | `drama_captions.drawtext_chain`（三档 drawtext）+ `karaoke_ass`（逐字 `{\k}` 高亮），合成时真烧录 | ✅ |
| D5 | 转场四档（AI 智能 / AI 参考 / 直接拼 / 渐变） | `lib/video-composer/transitions.ts:1-127` | `drama_compose.TRANSITIONS` 四档；`direct_concat` / `ffmpeg_fade` 本地执行；AI 两档属出片阶段，选它会**明说只能硬切**（不偷降级） | ✅ |
| D6 | 渲染三档（快速 720p / 标准 1080p / 高清 1080p） | `lib/production-profiles.ts:1-94` | `drama_compose.RENDER_PRESETS` + `safe_encode`（x264 white list/crf 夹取） | ✅ |
| D7 | 风格配方导入导出（纯 JSON 可分享） | `lib/style-packs.ts:1-132` | `services/drama_styles.py`、`/api/drama/style-packs*` + `/projects/{pid}/style-pack` 4 条路由、前端「风格配方」卡 | ✅ 逐字段白名单 + 逐字段丢弃（坏 JSON/格式不对/没名字才整份作废）；音量夹 0.05–0.4 且按 **JS 四舍五入**（`floor(x*100+0.5)`，不是 Python 银行家舍入）；名字 60 / 说明 200 / 作者 60 / CTA 60 截断；导出 2 空格缩进、中文不转义。🩸 只支持 6 个字段：竞品的 `bgm`（情绪档）与 `aspectRatio` 这边**没有对应能力**（BGM 是上传/搜来的具体曲子，没有情绪分类；合成固定 9:16）→ 导入时进 `dropped` 原样告知，不假装应用；另接受 `clipforge-style-pack@1` 标记以便导社区配方，导出只写我们自己的标记 |
| D8 | 多语言译制（dub：译词 → 重新配 → 对轨） | `api/project/[id]/dub/route.ts`、`lib/script-engine/translate.ts` | **第十七批新增** `services/drama_dub.py` + 5 条路由 | ✅ **（第十七批）** 13 种语言；提示词照 `translate.ts:47-57`（逐行翻译、**不许合并/拆分**、顺序与条数不变、只回等长 JSON 数组）；解析照 `:60-79`（先剥 `<think>`、取 ```json 围栏或第一对 `[]`、条数不符判失败）；只换 `dialogue`，**画面字段（description/framing/camera/product）原样保留**，按译后文本重估时长（CJK 5 字/秒、其它 14 字符/秒、夹 2–15 秒）；推荐音色直接取 D1 免费 Edge 表（译完可零费用重新配音）；**差异**：竞品把译制版存成脚本新版本并置选中，我们是单份分镜 → 存 `dubs[lang]`，显式「应用」才写回且可一键还原 |
| D9 | 合成（**唯一必需阶段**，判官/配画失败都静默跳过） | `api/project/[id]/compose/route.ts:1-613` | `services/drama_compose.py`（plan 纯计算 + render 本地 ffmpeg）+ `POST /compose/plan`、`POST /compose`、`GET /compose/file` | ✅ |
| D10 | 片尾 CTA / 商品卡贴片 | `lib/video-composer/end-card.ts:1-121`、`api/project/[id]/end-card` | `drama_compose.build_graph` 尾卡段（图片 overlay + CTA drawtext，只在最后 N 秒）；图片来源 = 项目商品图（二维码当商品图传） | ✅ |

---

## E. 交付物料（发行侧，10 项）

| # | 竞品能力 | 出处 | 我们的位置 | 判定 |
|---|---|---|---|---|
| E1 | 封面图（从最新**成功**成片抽帧 + 叠标题） | `api/project/[id]/cover/route.ts`、`lib/video-composer/cover.ts` | `services/drama_cover.py`（折行/转义/字体逐字抄）、`api/drama.py POST /cover` | ✅ |
| E2 | 小红书图文卡（标题卡 + 每镜旁白一卡，3:4） | `api/project/[id]/carousel/route.ts` | `services/drama_cards.py`（逐行居中/五主题/最多 12 张）+ `POST /carousel` + `GET /carousel/file/{idx}` | ✅ |
| E3 | **店铺二维码（UTM）+ 平台三档把关**（抖音默认拒绝烧录） | `api/project/[id]/shop-qr/route.ts`、`lib/platform-specs.ts:52` | `services/drama_qr.py`（UTM + 自写 PNG，OpenCV 扫码回读验过）+ `services/drama_platform.py` 三档政策；`POST /shop-qr`（`burn=true` 时抖音拒） | ✅ |
| E4 | 多平台导出（按平台比例/码率重构图；`blur`/`fit`/`crop` 三档） | `api/project/[id]/export-platform/route.ts`、`platform-specs.ts:1-…` | `services/drama_platform.py`（7 平台逐值 / VBV 预算 / 帧率封顶 / 实测报告 / 单帧预览）+ `POST /export-platform` | ✅ |
| E5 | 成片速览（按真实切点取样 + 波形 + 时间码审片小样） | `api/project/[id]/contact-sheet/route.ts` | `services/drama_contact_sheet.py`（smart/even + 切点红框/红刻度 + 审片小样）+ `POST /contact-sheet` | ✅ |
| E6 | 预览 GIF（128 色） | `api/project/[id]/preview-gif/route.ts` | `services/drama_gif.py` + `POST /preview-gif` | ✅ |
| E7 | 原生感后期（三档 + 镜头光晕 + 平台二压感） | `api/project/[id]/native-feel/route.ts`、`lib/video-composer/native-feel.ts:1-171` | `services/drama_native_feel.py`（三层正弦漂移/颗粒/去精致/暗角/光晕/二压感，逐值抄）+ `POST /native-feel` | ✅ |
| E8 | 母版处理（mastering） | `api/project/[id]/mastering/route.ts`、`lib/video-mastering.ts` | `services/drama_mastering.py`（接缝 signalstats 打分 + loudnorm 测量 + 非破坏式渲染）+ `POST /mastering`（analyze/render） | ✅ |
| E9 | 字幕导出 SRT / VTT（成片里仍是烧录的，这份给二剪/平台原生字幕） | `api/project/[id]/subtitle/route.ts`、`lib/subtitle-export.ts:1-100` | `services/drama_subtitle.py`（逐字抄）、`api/drama.py GET /subtitle` | ✅ |
| E10 | 发布文案（3 标题 + hashtag + 种草文案 + **评论区运营包** + AI 声明句；无 LLM 走模板版） | `api/llm/publish/route.ts`、`lib/publish-pack.ts:1-290` | `services/drama_publish.py`（模板版零费用 + 提示词 + `sanitize` 夹取）+ `POST /publish-pack` / `POST /publish`（模型版） | ✅ |

---

## F. 质量与合规（闸门侧，8 项）

| # | 竞品能力 | 出处 | 我们的位置 | 判定 |
|---|---|---|---|---|
| F1 | **7 维质量合同 + 五种处置**（永不自动） | `lib/generation-quality.ts:1-309`、`api/project/[id]/quality` | `services/drama_quality.py`、`api/drama.py:1306` | ✅ |
| F2 | 成片技术 QC（黑屏/长静音/响度漂移/冻结/流完整性 → 三态） | `lib/video-composer/qc.ts:1-368`、`api/project/[id]/qc` | `services/qc.py deep_inspect`（阈值逐字抄 `qc.ts:67-79`）、`api/drama.py POST /qc` | ✅ |
| F3 | **发布门禁 + 最差状态胜出**（人工拒绝的镜头直接拦发布） | `lib/release-gate.ts:1-316`、`api/project/[id]/gate/route.ts` | `services/drama_compliance.py gate_from_*` / `build_gate`、`api/drama.py POST /gate`（5 项：脚本自检/成片质检/语义验收/素材授权/AI 规则） | ✅ |
| F4 | 发布前 8 项自检（三态：可发布 / 有风险 / 建议先改） | `lib/publish-readiness.ts:1-212` | `drama_compliance.check_readiness`、`POST /readiness` | ✅ 7 项（第 8 项 AIGC 角标**默认不查**，主人定过不打水印） |
| F5 | **广告法四类风险词表** + 改法提示 | `lib/ad-compliance.ts:1-95` | `drama_compliance.RULES / check_ad / check_shots` | ✅ |
| F6 | 抖音 AI 带货三条（测评形态 / 数字人五类目 / 亲测宣称） | `lib/ai-commerce-compliance.ts:1-132` | `drama_compliance.check_ai_commerce` | ✅ |
| F7 | 提示词卫生 lint | `lib/prompt-lint.ts:1-69` | `services/drama_format.py:158 lint_storyboard` + **第二十五批新增** `services/drama_prompt_lint.py`（10 条时序词 + 动作前一瞬指令句） | ✅ **两条都落地**：① 分镜描述 lint（内心戏/否定式动作/精确双人交互/多步动作链/不可画气氛 + S1/S2），随分镜进 `storyboard_lints`；② **静态关键帧时序词 lint** 10 条逐字照抄（先…然后 / 然后接着随后 / 逐渐渐渐 / 之后下一秒 / 开始做某事 / then / starts to / gradually / after that / followed by，含竞品单测里的正反样本）；③ `keyframe_instant_line` 关键帧末尾追加「画面是动作即将开始前一瞬的定格…」，中/英按 CJK 判定。接线：九宫格出图提示词末尾挂指令句、规划时逐格算 `cell_lints` 并在关键帧卡逐条显示（只提示不拦，竞品 `:9-11` 也是 warning-only） |
| F8 | 结构指纹（跨项目反同质化自检） | `lib/structure-fingerprint.ts:1-114`、`api/insights/homogeneity` | `services/drama_fingerprint.py`、`GET /api/drama/insights/homogeneity`、前端「结构自检」卡 | ✅ 权重逐字照抄（风格 .35 / 开场 .25 / 镜数 .15 或差 1 镜 .08 / 平均镜长 .15 / 总时长 .10），阈值 0.75，>50% 对越线 risk、>25% warn；字段全落现有真实字段（style ← 配方 `styleType` → 体裁回落；hook ← `card_json.hook.type`；shots ← 分镜时长）；只统计**有分镜**的项目，少于 2 条给 ok + 空结果 |

---

## G. 运营与批量（5 项）

| # | 竞品能力 | 出处 | 我们的位置 | 判定 |
|---|---|---|---|---|
| G1 | 批量作业（多商品一次排队，batch_jobs / batch_job_items 落库） | `api/batch/route.ts`、`app/batch/page.tsx`、`lib/variation-plan.ts` | **第二十四批新增** `services/drama_batch.py`（作业/条目落 JSON，等价两张表）+ `GET/POST/PATCH /batch` + `POST /batch/plan` + 前端「批量作业」卡 | ✅ 语义照 `route.ts`：条目五状态 / 作业三状态、**同一时间只一个在飞**（新建把旧 running 结算 cancelled）、错误截 500、写回 best-effort；反同质化按 `variation-plan.ts` 的 **mulberry32**（与 JS 逐位对拍）轮换 H1–H5 钩子 + 免费中文音色 + 卡拉OK隔条开，槽位随作业一起落盘、续跑用原计划。🩸 差异：① 执行器做到**分镜就绪**（结构卡→确认→剧本→分镜）为止，**不出片**（出片只归主人点）；② 竞品还能轮 BGM 情绪/风格/时长抖动，我们没有对应物（BGM 只收上传文件、风格由模板定、片长只 15/30/60）→ 不编 |
| G2 | 作品流（跨项目成片墙 + 封面回填预算） | `api/works/route.ts` | `services/drama_works.py`、`GET /api/drama/works`、前端「作品流」卡 | ✅ 只列盘上真有视频的（合成片 > 拼接整片 > 最后一段），按**视频文件 mtime** 倒序、上限 200；封面优先人做的 `film.cover`，缺的每次最多回填 **6 张首帧**（`BACKFILL_MAX`）写进 `film.poster`、**不覆盖 cover**，回填失败不拦列表。🩸 竞品按 `compositions.createdAt`，我们没有 compositions 表 → 文件 mtime 是唯一真实时间，不编 |
| G3 | 趋势话题（「今天该发什么」，零 Key） | `api/trends/route.ts` | `services/drama_trends.py`、`GET /api/drama/trends`、前端「趋势话题」卡 | ✅ 两路源：国内（抖音热搜 → 拿不到 ≥5 条退头条）/ 海外（Google Trends 每日 RSS）；解析全是纯函数（CDATA/实体/数字或数字字符串的热度都认）；热度中文读法（1150万 / 1.7亿）；标题 10 类关键词分类（垂类优先、未命中留 None 不硬分）；每日一条按 persona 计分、全不中回榜首并标 `matched=false`；10 分钟 TTL 缓存且**空结果不缓存**；上游挂了回空列表 + 人话 `error`，不 500。🩸 我们的 persona 默认取当前项目受众（`product.audience`），竞品让用户手填 |
| G4 | 发布指标回填（播放/点赞/成交 → 反哺风格收益） | `api/project/[id]/metrics/route.ts` | `services/drama_metrics.py`、`GET / POST /projects/{pid}/metrics`、前端「效果回流」卡 | ✅ 风格/品类**录入时定格**（配方 `styleType`，无则 `custom`；品类取商品 `category`），之后改配方不污染历史；五个数字按 JS `Number()` + `Math.max(0, Math.floor())` 归一（非法/负数 → 0）；备注截 500、发布日存毫秒、列表新的在前（同毫秒严格递增）。**反哺**：剧本阶段注入 `buildPerformanceHint` 原文，同品类优先、样本不够回落全局，读失败只跳过不阻断生成 |
| G5 | 风格成效统计 | `api/insights/styles/route.ts` | `services/drama_metrics.py`、`GET /insights/styles`、前端「效果回流」卡成绩单 | ✅ 按风格/钩子聚合 `samples / avgViews / engagementRate(赞+评+转/播放) / conversionRate(成交/播放) / totalOrders`；转化率降序、同分按样本数；`topConverting*` 要求 **≥2 条样本且转化 >0**（冷启动不硬报）。🩸 我们的结构卡只有 `H1–H5` 五个钩子编号，没有竞品那套 `visual_shock…` 机制名 → 界面只给 H1–H5，不替模型编中文名 |

---

## H. 基础设施（6 项）

| # | 竞品能力 | 出处 | 我们的位置 | 判定 |
|---|---|---|---|---|
| H1 | 一站式自诊断（真跑 DB 查询 / 迁移目录 / 数据目录可写 / ffmpeg 路径；只读无副作用） | `api/health/route.ts:1-65` | `api/drama.py GET /health`（真写一次数据目录 / 项目数 / ffmpeg+版本 / 磁盘余量 / problems 清单，**不含密钥内容**） | ✅ |
| H2 | 文件服务（先 decode 再 normalize，**必须仍在根内**防 `..%2f`；Range 206/416；流式；缓存一年） | `api/files/[...path]/route.ts`、`api/output/[...path]/route.ts` | `services/drama_files.py`、`GET /api/drama/files/{kind}/{path}` | ✅ 逐段先解码再挡（`..%2f` / `%2e%2e` / `%5c` 实测全挡在 403）；`is_relative_to` 再兜一次根目录；Range 由 Starlette `FileResponse` 原生给 206/416（`Accept-Ranges` + 正确 `Content-Range`）；缓存素材图一年、成片/关键帧一小时；`?download=1` 走 RFC 5987 文件名。🩸 与竞品一处行为差异：**多区间请求**竞品回 416，Starlette 回 `multipart/byteranges` 206 —— 更完整的那个，不改差｜目录白名单：images / films / bgm / media / materials / products / grids |
| H3 | 上传白名单（MIME + 扩展名双查，大小上限，`productId` 正则防穿越） | `src/app/api/upload/route.ts`、`src/app/api/products/upload/route.ts` | `api/drama.py:1705 _save_upload` + `_path` 项目号正则 | ✅ **四件齐**（第二十五批补齐后两件）：扩展名白名单（jpg/jpeg/png/webp）+ **MIME 与扩展名双查**（`image/png` 配 `.png`；空类型/`octet-stream` 按扩展名兜底，免得 RPA/curl 被误挡）+ 10MB 流式上限（空文件拒、文件名服务端重生成）+ **项目号 `^[A-Za-z0-9_-]{1,40}$`**（`_path` 统一挡 `../`、`a/b`、`p1.json`，所有按 pid 取文件的接口一起受益）。🩸 有意收窄：扩展名集不含 gif / svg / bmp（**SVG 会让同源静态服务执行脚本**） |
| H4 | 设置中心 + **五版迁移史**（每版对应一次线上事故） | `stores/settings-store.ts:1-292`、`app/settings/page.tsx` | `services/drama_settings.py`、`/api/drama/settings` 4 条路由（含 `/import`）、前端「设置中心」卡 | ✅ **五版修复已变成可执行迁移**：设置中心 9 个全局默认（原 6 个 + 成片分辨率 / 接缝默认 / 真实感默认），`SCHEMA_VERSION=2` + `MIGRATIONS` 注册表（v2 补三个成片默认，顺序与幂等验过）。🩸 **不编我们自己的事故史**（本工程密钥一直走环境变量、没有旧持久化文件），而是把竞品那五条修成**「旧版设置导入」**：v1 失效模型名（DeepSeek/火山/Atlas 三个官方 host 各自换名）· v2 Pollinations 停用端点 + 占位 Key 清除 · v3 Ollama `localhost→127.0.0.1` · v4 认不出的生产方案 → `balanced` · v5 Atlas 素材网关 → 聊天网关；**全部只在 baseUrl 命中对应官方端点时改写、幂等**，自建代理与用户自选模型一律不动。导入报告逐条列「搬了哪几项 / 修了哪几条 / 哪些没搬及原因」 |
| H5 | 数据目录可写探测 | `api/health` | `api/drama.py:146 _dir` 隐式 | ✅ |
| H6 | ffmpeg 路径探测 | `api/health`、`lib/media` | `services/media.py ffmpeg_path` | ✅ |

---

## 汇总（数出来的，不是估的）

按行统计（脚本数出来的：`grep -c '^| [A-H][0-9]'` = **77**）：

| 判定 | 条数 | 说明 |
|---|---|---|
| ✅ **已做（整格）** | **77** | A1 A2 A3 A4 A5 A6 A7 A8 A9 A10 B1 B2 B3 B4 B5 B6 B7 B8 B9 B10 B11 C1 C2 C3 C4 C5 C6 C7 C8 C9 C10 C11 C12 C13 C14 C15 C16 C17 D1 D2 D3 D4 D5 D6 D7 D8 D9 D10 E1 E2 E3 E4 E5 E6 E7 E8 E9 E10 F1 F2 F3 F4 F5 F6 F7 F8 G1 G2 G3 G4 G5 H1 H2 H3 H4 H5 H6（C12 / D3 / H4 / F7 / H3 第二十五批补齐） |
| ✅+🟡 **部分已做** | **0** | —— |
| 🟡 **能做待做（整格）** | **0** | —— 77 条已全部落地（B6 / B7 / B8 / B9 / D1 / D8 / A2 / A3 / D7 / F8 第十二至十九批；H2 第二十批；G3 第二十一批；G2 / G4 / G5 第二十二批；C4 / C17 第二十三批；B11 / G1 第二十四批；C12 / D3 / H4 / F7 / H3 五条「部分」第二十五批补成整格） |
| 🔴 **做不了** | **0** | —— |
| ⏸ **待拍板** | **0** | A10 已由主人 2026-11-06 拍板「直接接」，整格落地 |
| **合计** | **77** | 72 路由 + 18 页；B3 十个源已全接（4 个免 Key 现成可用，5 个要 Key 的配环境变量即生效） |

**2026-11-06 第一批已落地（零生成费）**：F2 成片技术质检 · E9 字幕 SRT/VTT · E1 封面 · H1 一站式自检 · C3 在飞任务视图（含 `film.running` 登记，重规划不清）。

**第二批已落地（零生成费）**：F3 发布门禁 · F4 发布前自检 · F5 广告法四类 · F6 抖音 AI 带货三条（`services/drama_compliance.py`，四份逻辑逐字抄）。

**第三批已落地（零生成费 · 2026-11-06）**：A10 模板经济（391 条配方 + AI 定制 + 分享/打包 + 我的模板 + 剧本结构模板）· C10 运镜库 22 条（含冲突判据、两层叠加、词表块注入分镜提示词）· C11 Look 14 种（出图段 / 光锚 / opener 三段全部接线）· D4 字幕四预设（数据与覆盖表就绪，烧录等合成阶段）。

**第四批已落地（零生成费 · 2026-11-06）**：D 组合成与音频整组 —— D2 BGM（5 情绪档 + 闪避 ducking + 强度夹取 0.05–0.40 + 上传/删除）· D4 字幕四预设**真烧录**（drawtext 三档 + 卡拉OK ASS 逐字高亮）· D5 转场四档 · D6 渲染三档 · D9 合成接入（时间轴 / 切点 / 指纹闸门）· D10 片尾 CTA + 商品卡贴片 · E5 成片速览（smart 按真实切点 / even 均匀）· E6 预览 GIF。

> ⚠️ **诚实说明**：D5 的 AI 智能过渡（`ai_start_end` / `ai_reference`）是**生成期**能力，本地合成做不到 —— 选它会在计划里出警告并回落硬切，不静默降级。真正的接缝实现见附录-1（C9 间接 tail 已落地，✅）。

**第五批已落地（E 组 · 发行物料 · 2026-11-06）**：E10 发布文案（模板版零费用确定性 + 模型版 + 评论区运营包）· E2 小红书图文卡 · E3 店铺二维码（UTM + 三档政策，**扫码回读验过**）· E4 多平台导出（7 平台 / blur·fit·crop / VBV 码率预算 / 实测报告）· E7 原生感（三档 + 光晕 + 二压感）· E8 母版（接缝打分 + 响度归一 + 非破坏式渲染 / 去闪烁）。

> 🩸 **一处本地化要主人知道**：E8 的 GB 45438 隐式 AI 元数据，竞品默认写，我们**默认不写**（与「AI 标记默认不打」一致），要写显式传 `aigc_meta=True`。

**第七批已落地（B 组 · 素材生态 · 本地闭环 · 2026-11-06 · 零生成费）**：B1 上传三路补齐（图/视频/音频，扩展名 + ffprobe 真格式双查）· B2 本地素材库（内容寻址去重 / 临时文件校验通过才发布 / sidecar 元数据 / 标签上限 / 出处字段）· B5 授权清单（三档风险 + NC/ND 拦截 + 署名行 + Markdown 导出，**发布门禁直接读这一份**）。

**第八批已落地（B4 · 每镜参考画面 · 2026-11-06 · 零生成费）**：B4 自动配画面。两条路（每镜参考图 / 合成时拼实拍段）里**走了前一条**——只改 `drama_film` 的分段参考图与提示词编号，不碰合成时间线。素材库图片按镜头 id 绑定（一镜一张），自动匹配按「素材标签/原名 → 分镜描述」命中词数排序，跨镜去重、0 分不配、手选不覆盖；提示词把它写成「场景与道具以 @图片N 为准，参考图里的人物不算角色」。换图会改 `plan_hash`（提示词一字不变也作废旧确认卡）。

> 🩸 **这一批只做了前半截**：图片素材只当**场景/陈设参考**（不改「这一镜演什么」，只锁「长什么样」）；成片里不会出现那张实拍图。要「素材就是这一镜的画面」见下一批。

**第九批已落地（素材当画面 · B4 下半截 · 2026-11-06 · 零生成费）**：**视频**素材可以直接当**某一镜的画面** —— 该镜从 AI 出片计划里拿掉（素材镜天然是段边界），合成时按 `timeline` 顺序插回时间线。
- 接口：`GET/PUT /projects/{pid}/shot-clips`（一镜一段、**只收视频**；图片会被拒并指路「配参考画面」）
- 计划：`film/plan` 新增 `clips` / `timeline`；素材名进 `plan_hash`；素材镜有台词时 plan 明示「台词不会出现」
- 合成：`drama_compose` 按时间线混排。时长对齐抄竞品判据（`composer.ts:506-521`）：**只有无声素材才变速**（源/槽 ∈ [0.7, 1.35]），超区间退回冻帧补足；**有原生音轨的永不变速**（变速会音画不同步）。素材段不出字幕（素材里没有这句台词）。

> 🩸 **代价要说清**：素材镜把 AI 段切成两半 → **出片段数可能变多**（段数是花费的乘数）。这是「逐镜换实拍」在我们「按段出片」架构下的必然代价，不是 bug；计划卡会先把段数列出来。

**第六批已落地（C 组 · 生成链增强 · 2026-11-06 · 零生成费）**：A5 品类模板（`category_templates.json` 22 条 + 5 条品类指令，原样抽）· A6 话题起片（独立体裁、五种旁白风格、一次写 N 版）· A7 多版脚本（版本栈 ≤12、切版本判「分镜过期」）· A8 手写稿导入（竞品切分口径 + 我们 4s 下限）· C9 接缝间接版（上一段真实尾帧当参考图锁首帧）· C15 变体矩阵（合成四维轮转，复用 `compose_run`）· C16 能力预检（三档置信度 + 四类改写 + 五类告警）。

> 🩸 **三处刻意与竞品不同**（都在各服务文件头写了理由）：① A5「其他」类目**不注入**模板（竞品回落 beauty，等于给错先验）；② A7 **不删旧稿**（竞品重生成先删，多版管理就形同虚设）；③ A6 片长档改 20/30/45/60、单镜 4–15 秒（竞品 15–40 / 单镜可 3 秒，3 秒进不了我们 `min_sec=4` 的出片链）。

**第十批已落地（B3 免版权素材搜索 · 2026-11-06 · 零生成费）**：10 个源一套检索 → 选中的下载进素材库（图/视频）或 BGM 位（音频）。
- 源：4 个**免 Key**（Openverse、Wikimedia、NASA、Internet Archive）+ 本地素材池 + 5 个要 Key（Pexels、Pixabay、Coverr、Jamendo、Freesound，Key 走环境变量，配了就自动参与）
- 许可硬过滤逐条照抄：Openverse 带 `license_type=commercial`；Jamendo 服务端排 NC/ND/SA + **客户端只认纯 CC-BY**（SA 会传染给成片）；Freesound 只收 CC0/CC-BY 并二次校验；Archive 强制 `licenseurl:*publicdomain*`；Wikimedia 视频只收 ≤720p webm 转码
- 排序抄 `stock-registry.ts:200-228`（类型对 → 本地 → 免 Key → 朝向 → 短边分辨率）；聚合并发、单源失败只进 `errored_sources`；结果缓存 5 分钟
- 接口：`GET /stock/sources`、`POST /projects/{pid}/stock/search`、`POST /projects/{pid}/stock/import`
- 导入**只传 `source + media_type + id`**（服务端短期缓存里取回候选）→ 前端拿不到也改不了下载地址；下载前校验「不是内网地址」（防 SSRF）
- 落地：图/视频走素材库（作者/许可/出处页/标签一起写进 sidecar，**B5 授权清单与发布门禁直接读得到**）；音频进 BGM 位（非 mp3/wav/aac/m4a 用 ffmpeg 转 mp3，超 20MB 拒）
- 🩸 **本机踩到的坑（写进代码头）**：Wikimedia 按 **TLS 指纹** 拦，httpx 同 UA 稳定 403、requests 稳定 200；下载集群**要求 UA 带联系方式**，不带就整段 429 → `STOCK_USER_AGENT` 可配

**第十一批已落地（B4 补完 · 自动配画面接搜索 + 降级阶梯 · 2026-11-06 · 零生成费）**：新建 `services/drama_stock_fill.py`。

- 阶梯照 `stock-matcher.ts:21-39`：**原词搜不到才往下走**；`fallbackLevelOf`（:38-50）的三档标注逐镜带回
- 中文适配（我们没有竞品那种英文 `stockKeywords`）：按动词/虚词断句取**最长名词块**（「抽出纸巾擦桌子」→「纸巾」），再退化到**商品名当主题锚**，最后四个英文通用兜底词（`abstract background / lifestyle / nature / light`，:10 原样照抄）
- 打分照 `stock-matcher.ts:100-165`：命中词 ×10、竖屏 +5、横屏 −3、已用过 −8、同源（同作者）+6、视频够填满槽位 +3；同实体词的镜头归一组（:186-221 并查集），组内偏向同作者
- 跨镜去重：整次填充共享 used ids/names（`stock-fill/route.ts` 的 usedIds），每档只在**没用过的候选**里挑，全用过就走下一档
- 落盘复用 `store_candidate`（sha256 文件名 + 出处写进 sidecar）→ **B5 授权清单与发布门禁直接读得到**；已配过的镜默认跳过（`force` 重配）；已经有实拍画面的镜不配参考图
- 接口 `POST /projects/{pid}/stock/auto-fill`（`media_type` / `source` / `force` / `per_page` / `allow_universal` / `max_shots`），返回 `filled/total/skipped/unmatched/results/levels`；`unmatched` 带 `matched_query` + `level` + 人话原因
- 前端「免版权素材」卡新增「自动配画面」按钮（先确认框说明代价），配完显示「配了 X/N 镜｜原词命中/放宽后命中/通用词各几条｜没配上的镜头号（只搜到通用词或不贴题，没硬塞）」，并刷新素材库/分镜素材/出片计划

**第十二批已落地（B6 长视频导入 · 2026-11-06 · 零生成费）**：新建 `services/drama_media_import.py` + 4 条路由 + 前端「长视频导入」卡。

- 常量照 `media/route.ts:22-31`：项目 ID 安全校验、1GB / 2 小时 / 五种扩展名（MP4 MOV WebM MKV M4V）
- 上传**不穿 multipart**：原始 body 流式落盘（`request.stream()`），`x-file-name` 带 URL 编码原名
  （`route.ts:35-44`）—— 1GB 才不会先在服务端落一份临时盘；前端走 XHR 直传并显示进度
- 边写边计数（`route.ts:107-124`）：`content-length` 声明超限先拒，**实收再拦一次**（头会撒谎）
- 写完真实校验（`media-validate.ts:29-45`）：宽高都 > 0 且时长 > 0，不合格删文件报「视频无法解码」；
  时长 > 2h 删文件拒
- **独立索引 `data/drama/media/<pid>/index.json`**（能力表 B6 那行要求的「不和素材库混」）：
  素材库放「能当某镜参考图 / 画面」的小素材，这里是长视频原料
- 接口：`GET /projects/{pid}/media`｜`POST /projects/{pid}/media/import`｜`GET …/media/{mid}/file`（Range）｜`DELETE …/media/{mid}`
- 🩸 实测踩到：索引排序键若只存「秒级时间字符串」，同一秒连导两条会按插入顺序返回（新的一条排后面）→ 改为毫秒 `created_ms`
- ⚠️ 名字歧义：`temp/probe_b6_smoke.py` 里的 **b6 是「第六批」**（素材当画面的出片计划冒烟），**不是能力编号 B6**；本次新增的是 `probe_drama_media_import*.py`

**第十三批已落地（B7 长视频转写 · 分块追加 + 检查点 · 2026-11-06）**：新建 `services/drama_media_transcript.py` + 2 条路由 + 前端转写按钮/进度/全文。

- 每块 **5 分钟**（`transcript-checkpoint.ts:11` 的 `ASR_CHUNK_SECONDS = 300`），块长夹在 30~300
- **ASR 在服务端跑**（火山 flash），不是竞品的浏览器本地模型 → 没有 heartbeat / 前端推块，
  改成一个后台任务：逐块切音频（`-ss/-t` + 16k 单声道，不整段解码）→ 识别 → **立刻落检查点**
- 块内时间戳**加块起点偏移**并裁到块末端（不越界到下一块）
- 检查点三条硬规则照抄：① 进度必须推进（没前进直接拒）② 块要和窗口重叠（全落窗外报「对不上」）
  ③ 拼完按 start 排序去重；**model / language 对不上整份作废**（换了模型或语言不能接着用）
- 中断判定：状态还是 `transcribing` 但没有活任务 → 判 `failed`「转写已中断，可直接重新开始」
  （`media/route.ts:56-59`）
- 接口：`GET /projects/{pid}/media/{mid}/transcript`（状态+进度+摘要，ready 时带全文）｜
  `POST …/transcript`（`action=start|cancel`，`resume=false` 丢检查点从头来）
- 前端：长视频列表每行「转写 / 转写中 45% / 重转」+ 进度条 + 「已转写」标记 + 「看文字」展开全文；
  静音视频不显示转写按钮
- 🩸 **与竞品的差异（写进文件头）**：竞品用**字级** start、去重容差 0.001 秒；我们是**句级**段，
  重叠区两次识别起点能差几百毫秒 → 容差放宽到 0.5 秒（仍要求文本完全相同，真正的重复台词不会被误删）

**第十四批已落地（B8 按文字剪 · 2026-11-06 · 零生成费）**：新建 `services/drama_clips.py` + 3 条路由 + 前端「按文字剪」面板。

- 参数闸照 `clips/route.ts:24`：关键词 ≤160 字、目标时长 5–120 秒、候选 1–12 个；**没转写完成不给**（:30-31）
- 找片段算法照 `transcript-clips.ts` 全文（归一化 / 拼词 / unit 切分 / 边界搜索 / 呼吸 / 打分 / 去重叠），
  逐条注释带行号；**不跨 >3 秒静默**、长度到目标 1.35 倍就停、太短（< min(3, 目标×0.4)）丢弃
- 我们的数据源是**段级 segments + 字级 chars**，先展平成词；没有字级时退回「每段当一个词」，结果里用
  `word_level` 标出来
- **比竞品多一步「剪出来」**：竞品这个接口只给建议（真剪在 `transcript-render.ts`，多区间 trim+concat）；
  我们没有时间线编辑器，所以把单区间裁剪做成一步：本地 ffmpeg **重编码**导出 mp4
  （`-c copy` 会因关键帧不在切点而多出一段），存 `data/drama/media/<pid>/clips/`，可直接打开或下载
- 接口：`GET /projects/{pid}/media/{mid}/clips?query=&target_seconds=&limit=`｜
  `POST …/clips/cut`（`{start,end}`，0.5–180 秒、不能越界）｜`GET …/clips/{name}/file`

**第十五批已落地（B9 时间线导出 · 2026-11-06 · 零生成费）**：新建 `services/drama_timeline.py` + 1 条路由 + 前端导出按钮。

- 三种格式逐条照 `timeline-export.ts`：OTIO（`Timeline.1` / `Stack.1` / 视频·音频·字幕三轨 /
  `ExternalReference.1` 按文件名 relink / `Gap.1` 补空 / `Marker.1` 节奏点）、
  CMX3600 EDL（`001  AX       AA/V C        源入 源出 记录入 记录出`，附 `* FROM CLIP NAME` /
  `* TRANSCRIPT` / `* CAPTION` / `* CLIPFORGE SOURCE` / `* BEAT`）、CSV（12 列固定表头 / UTF-8 BOM / CRLF，Excel 直开不乱码）
- 时间码 `HH:MM:SS:FF`（base 用 `round(帧率)`）、帧率夹 1–240 否则 30；帧率用 ffprobe `r_frame_rate` 真读
  （读不到回落 30）
- 附带两条轨道照 `route.ts:56-77`：**节奏标记**（每句起点映射到成片时间）、**字幕轨**（源时间 → 成片时间，
  跨切点按字级截断，被切掉的句子自然消失）
- 🩸 **我们的差异（写进文件头）**：竞品导出的是「转写删词计划」的保留区间；我们这条线没有删词编辑器，
  默认取 **B8 已经剪出来的片段**（从 `clips/<mid>-<起ms>-<止ms>.mp4` 还原），也可手传 `ranges`；
  成片（AI 段 + 素材段混排）的时间线导出**没做**，那是另一条链路
- 接口：`POST /projects/{pid}/media/{mid}/timeline`（`{format, ranges?, revision?, inline?}`）；
  `inline=true` 返回 JSON（前端自己落文件），否则带 `Content-Disposition` 下载并附
  `X-Product-Drama-Clips` / `X-Product-Drama-Frame-Rate`

**第十六批已落地（D1 配音 + D3 人声落地 · 2026-11-06 · 零费用）**：新建 `services/drama_tts.py` + 4 条路由 + 前端「配音试听」卡。

- **免费 Edge 朗读**（零 Key）：🩸 手写 WebSocket 实测**一律 403** —— 微软把 `Sec-MS-GEC` 换成了
  **v2 令牌**（`<16hex>-<64hex>`，内部是改过的 SHA256 + CS64，见 `edge_tts 7.3.1` 的
  `drm.py::generate_sec_ms_gec_v2`），旧版 `sha256(ticks+token)` 改版本号也没用 →
  改用 MIT 许可的 `edge-tts` 库建连，我们只管把流事件拼成 mp3 + 字级时间戳
- **真联网验收**：中文 20,736 字节 mp3 / 8 个字级时间戳（首字 0.1s）、英文 17,856 字节 / 7 个时间戳；
  同文本第二次命中缓存；带 `[pause]` 也能出声
- **付费四家**照 `tts.ts:203-408`：OpenAI 兼容 /audio/speech、Atlas generateAudio（异步轮询）、
  MiniMax T2A v2（hex 解码 + GroupId + 情绪只送 7 个官方枚举）、fal.ai（队列 + status_url 优先）；
  `clipErr` 截断 200 字并显式标「…(已截断)」
- **成本保护**：内容寻址缓存（provider/baseUrl/model/voice/speed/emotion/instruction/text 全进 key）、
  连续 2 次失败熔断 30 秒、只对 408/429/5xx 与网络抖动重试（401/403/400/402/404 不重试）
- **文本处理**：`[pause]` 只有免费 Edge 渲染成 `<break 350ms>`，其余路径一律剥掉（`voice-markup.ts`）；
  SSML 全量转义；语速/音高/音色非法值**回落默认而不是报错**（`api/tts/free/route.ts` 的防注入口径）
- **D3 人声落地**：`voice_ground_chain()`（HP 90 / LP 9500 / 3:1 压缩 / 激励器）+ `room_tone_source()`
  （棕噪 / LP 400 / 44100 立体声）；🩸 合成链**未接线**（成片走原生出声，没有 TTS 轨），接线点已写在文件末尾
- 接口：`GET /drama/tts/free`（11 音色）｜`POST /drama/tts/free`（试听 ≤200 字，返回 mp3）｜
  `GET /drama/tts/providers`（四家预设）｜`POST /drama/tts/preview`（付费试听）｜`GET /drama/tts/ground`

**第十七批已落地（D8 多语言译制 · 2026-11-06 · 零生成费，翻译走 DeepSeek）**：新建 `services/drama_dub.py` + 5 条路由 + 前端「多语言译制」卡。

- 13 种语言（`translate.ts:20-33` 原表）；推荐音色直接取 D1 的免费 Edge 表 —— 译完可零费用重新配音
- 提示词与解析逐条照抄：逐行翻译、**不许合并或拆分**、顺序与条数不变、只回等长 JSON 数组；
  先剥 `<think>`、再取 ```json 围栏或第一对 `[]`；条数不符判失败（不半截采用）
- **只换台词**：`description / framing / camera / product` 等画面字段原样保留，同一批画面复用；
  按译后文本重估每镜时长（CJK 5 字/秒、其它 14 字符/秒、夹 2–15 秒，`script-import.ts:29-32`）
- 🩸 **数据模型差异**：竞品有 scripts 多版本表，译制版直接「置为选中」；我们是单份 `storyboard_json`，
  所以译制版存进 `dubs[lang]`，**默认不动原分镜**，点「应用到分镜」才写回，写回前备份原分镜、可一键还原
- 接口：`GET /drama/dub/langs`｜`POST /drama/projects/{pid}/dub`（`{target_lang,title?,apply?}`）｜
  `GET …/dubs`｜`POST …/dubs/{lang}/apply`｜`POST …/dubs/restore`

探针 **2404** 条全绿（64 个文件：`probe_drama_*.py` + `probe_b*_smoke.py`，实测于第十七批收尾（D8 新增 **95** 条 = 纯逻辑 57 + 接口 38；D1 新增 **132** 条 = 纯逻辑 88 + 接口 33 + **真联网 11**）；B9 新增 133 条 = 纯逻辑 98 + 接口 35；其中 B3 新增 122 条 = 纯逻辑 67 + 接口 40 + 真联网抽查 15，B4 补完新增 62 条 = 纯逻辑 42 + 接口 20，B6 新增 73 条 = 纯逻辑 42 + 接口 31，B7 新增 67 条 = 纯逻辑 43 + 接口 24，B8 新增 54 条 = 纯逻辑 32 + 接口 22）；前端 UI 19 + 14 + 17 + 19 + 14 + 11 + 11 + 13 条全绿（`temp/shot_stock10_ui.py`、`temp/shot_stockfill11_ui.py`、`temp/shot_media12_ui.py`、`temp/shot_transcript13_ui.py`、`temp/shot_clips14_ui.py`、`temp/shot_timeline15_ui.py`、`temp/shot_tts16_ui.py`、`temp/shot_dub17_ui.py`）；前端构建通过。**未出片、未重启后端、未提交。**

**第十八批已落地（A2 商品链接解析 + A3 商品库 · 2026-11-06 · 零生成费）**：新建 `services/drama_product_ingest.py` + `services/drama_product_lib.py`，`import_url` 整函数替换 + 6 条商品库路由 + 前端「商品库」卡。

- A2 四层解析（`product-ingest.ts:1-186` 逐条）：JSON-LD（递归找 `@type=Product`，含 `@graph`）→ OpenGraph → Twitter Card → `<title>`；
  标题/价格/描述/图片四路各取优先级；相对地址按 `<base href>` 优先补全；只留 http(s)；去重
- 🩸 **能力表原文与源码不符**：表里写「微数据 → LLM 兜底」，竞品 `product-ingest.ts` 到 `<title>` 就结束。
  照源码实现、**不补那两段**（编产品事实违反 C10）；抓不到就留空让用户手填
- 🩸 **SSRF 真缺陷**：`IngestError` 继承 `ValueError`，`raise IngestError("只收公网链接")` 被自己的
  `except ValueError` 吞掉 → 192.168/127.0.0.1 实测穿透。改成「先 try 取 ip，再在 except 外部判私网」
- A2 前端：抓到的 `price_text` **只进导入提示、不写 `form.price`** —— 那个字段是固定区间选项组，塞自由文本会破坏选项结构
- A3 商品库：文件库 `data/drama/products/index.json` + 每卡 `products/<id>/` 图片副本（文件名加 uuid 前缀防同名）；
  「存」和「应用」**都是复制不移动**，删卡不碰项目图；应用只覆盖 7 个商品字段 + 图片，不动分镜/剧本
- 接口：`GET /drama/products`｜`POST /drama/products`｜`PATCH /drama/products/{prid}`｜
  `POST /drama/products/{prid}/apply`｜`DELETE /drama/products/{prid}`｜`GET /drama/products/{prid}/images/{name}`

探针 **2544** 条全绿（68 个文件：`probe_drama_*.py` + `probe_b*_smoke.py`，实测于第十八批收尾（A2/A3 新增 **140** 条 = 纯逻辑 34 + 接口 27 + 解析纯逻辑 72 + **真联网 7**）；D8 新增 **95** 条 = 纯逻辑 57 + 接口 38；D1 新增 **132** 条 = 纯逻辑 88 + 接口 33 + **真联网 11**；B9 新增 133 条 = 纯逻辑 98 + 接口 35；其中 B3 新增 122 条 = 纯逻辑 67 + 接口 40 + 真联网抽查 15，B4 补完新增 62 条 = 纯逻辑 42 + 接口 20，B6 新增 73 条 = 纯逻辑 42 + 接口 31，B7 新增 67 条 = 纯逻辑 43 + 接口 24，B8 新增 54 条 = 纯逻辑 32 + 接口 22）；前端 UI 19 + 14 + 17 + 19 + 14 + 11 + 11 + 13 + 15 条全绿（`temp/shot_stock10_ui.py`、`temp/shot_stockfill11_ui.py`、`temp/shot_media12_ui.py`、`temp/shot_transcript13_ui.py`、`temp/shot_clips14_ui.py`、`temp/shot_timeline15_ui.py`、`temp/shot_tts16_ui.py`、`temp/shot_dub17_ui.py`、`temp/shot_a18_ui.py`）；前端构建通过。**未出片、未重启后端、未提交。**

**第十九批已落地（D7 风格配方 + F8 结构指纹 · 2026-11-06 · 零生成费）**：新建 `services/drama_styles.py` + `services/drama_fingerprint.py`，4 + 1 条路由，前端「风格配方」「结构自检」两张卡。

- D7：配方是**纯 JSON 数据**（不含任何可执行内容），导入走逐字段白名单；不合格字段只丢这一项，整份仍可用；
  只有「坏 JSON / 格式标记不认 / 没名字」才整份作废。音量按 JS 的 `Math.round` 语义夹取（与 Python `round` 有差别，实测 0.185→0.19）
- 🩸 **能力差异要当面说**：竞品的 `bgm` 情绪档与 `aspectRatio` 我们**做不了**（BGM 是用户上传的具体曲子、
  合成固定 9:16）→ 导入接口返回 `dropped`，界面直接写「这些字段这边用不了」，不静默吞掉
- D7 导入**只改合成设置**：不碰分镜、不改已出片段、不自动合成；片子怎么出仍由使用者自己点
- F8：指纹维度与权重逐条照抄（`structure-fingerprint.ts:73-82`）；我们的数据模型没有竞品 `scripts` 表，
  字段找到对应物：风格 ← 选中配方的 `styleType`（没选退体裁）、开场 ← 结构卡 `hook.type`、镜数与时长 ← 分镜
- 接口：`GET /drama/style-packs`｜`POST /drama/style-packs/parse`｜`GET|POST /drama/projects/{pid}/style-pack`｜
  `GET /drama/insights/homogeneity?limit=8`（limit 非法回落 8，夹 2–20）

探针 **2691** 条全绿（71 个文件：`probe_drama_*.py` + `probe_b*_smoke.py`，实测于第十九批收尾（D7/F8 新增 **147** 条 = 配方纯逻辑 73 + 指纹纯逻辑 33 + 接口 41）；A2/A3 新增 **140** 条 = 解析 72 + 商品库 34 + 接口 27 + **真联网 7**；D8 新增 **95** 条 = 纯逻辑 57 + 接口 38；D1 新增 **132** 条 = 纯逻辑 88 + 接口 33 + **真联网 11**；B9 新增 133 条 = 纯逻辑 98 + 接口 35；其中 B3 新增 122 条 = 纯逻辑 67 + 接口 40 + 真联网抽查 15，B4 补完新增 62 条 = 纯逻辑 42 + 接口 20，B6 新增 73 条 = 纯逻辑 42 + 接口 31，B7 新增 67 条 = 纯逻辑 43 + 接口 24，B8 新增 54 条 = 纯逻辑 32 + 接口 22）；前端 UI 19 + 14 + 17 + 19 + 14 + 11 + 11 + 13 + 15 + 22 条全绿（`temp/shot_stock10_ui.py` … `temp/shot_a18_ui.py`、`temp/shot_d7f8_ui.py`）；前端构建通过。**未出片、未重启后端、未提交。**

**第二十批已落地（H2 文件服务 + H4 设置中心 · 2026-11-06 · 零生成费）**：新建 `services/drama_files.py` + `services/drama_settings.py`，1 + 3 条路由，前端「设置中心」卡。

- H2 防穿越是**逐段先解码再挡**（`files/route.ts:25-32`）：`path:path` 拿到的是未解码分段，`..%2f..%2f` 解码后才出现分隔符，
  等拼完再 normalize 已经多出层级了。实测 `..%2f` / `%2e%2e/` / `..%5c` / 子目录里的 `%2e%2e` 四种全挡在 403
- Range 不重写：Starlette 1.9 的 `FileResponse` 原生支持（206 / 416 / multipart），实测 `bytes=0-3` 正好 4 字节、
  `bytes=99-` 给 416 + `bytes */10`。我们只收口「根校验 + 缓存头 + 下载头」
- H4 设置中心：6 个全局默认（字幕 / 画质 / 转场 / BGM 音量闪避 / 配音音色）+ 5 条密钥状态（**只回前 4 后 4 掩码**，
  探针断言整串不外泄）；设置存 `data/drama/settings.json`，原子写（临时文件 + rename）
- 🩸 **H4 为什么是「部分」**：竞品 5 个版本各对应一次线上事故（失效模型名 / 接口停用 / Windows localhost 解析 / …），
  本工程历史上没有持久化设置文件，**没有旧值可迁** → 机制建好但从 v1 起记，不编五条假事故；
  纪律写进 `drama_settings.py`：今后改默认值必须 +1 版并写明事故与日期
- 顺带修一个真缺陷：`drama_media_import.add_source` 的 `created_ms` 用 `int(time.time()*1000)`，
  同毫秒连加两条会撞键 → 列表变「旧的在前」。改成进程内严格递增（撞了 +1ms），连跑三次稳定

探针 **2836** 条全绿（74 个文件：`probe_drama_*.py` + `probe_b*_smoke.py`，实测于第二十批收尾（H2/H4 新增 **144** 条 = 文件服务纯逻辑 48 + 设置纯逻辑 49 + 接口 47，另加媒体索引时间戳 1 条；D7/F8 新增 **147** 条；A2/A3 新增 **140** 条 = 解析 72 + 商品库 34 + 接口 27 + **真联网 7**；D8 新增 **95** 条；D1 新增 **132** 条 = 纯逻辑 88 + 接口 33 + **真联网 11**；B9 新增 133 条；其中 B3 新增 122 条、B4 补完 62 条、B6 新增 73 条、B7 新增 67 条、B8 新增 54 条）；前端 UI 19 + 14 + 17 + 19 + 14 + 11 + 11 + 13 + 15 + 22 + 16 条全绿（`temp/shot_stock10_ui.py` … `temp/shot_h4_ui.py`）；前端构建通过。**未出片、未重启后端、未提交。**

**第二十一批已落地（G3 趋势话题 · 2026-11-06 · 零生成费）**：新建 `services/drama_trends.py` + `GET /api/drama/trends` + 前端「趋势话题」卡。

- 两个零 Key 源：国内走抖音热搜（拿不到 ≥5 条才退头条热榜），海外走 Google Trends 每日 RSS；实测两边都通
  （抖音样例「降温了羽绒服先穿为敬 1159万」，Google 样例「baltimore ravens …」）
- 解析全纯函数：CDATA / XML 实体 / 热度是数字或数字字符串都认；热度转中文读法（1150万 / 1.7亿）
- 分类是**标题关键词**（10 类，垂类先于泛化，`新闻联播` 这类未命中就留空不硬塞），不猜抖音未公开的 `sentence_tag`
- 「今日一条」按人设打分；**没命中就诚实回榜首并标 `matched=false`**，界面写「先按榜首给」
- 10 分钟 TTL 缓存，**空结果不缓存**（临时失败能马上重试）；上游挂了返回空列表 + 人话 `error`，不回 500
- 前端选中直接带进「话题起片」表单（`useTrend` → `openTopic`），不用手抄

探针 **2933** 条全绿（77 个文件，实测于第二十一批收尾：G3 新增 **97** 条 = 纯逻辑 67 + 接口 20 + **真联网 10**；H2/H4 新增 144 条；D7/F8 新增 147 条；A2/A3 新增 140 条；D8 新增 95 条；D1 新增 132 条；B9 新增 133 条；B3 122 / B4 补完 62 / B6 73 / B7 67 / B8 54）；前端 UI 19 + 14 + 17 + 19 + 14 + 11 + 11 + 13 + 15 + 22 + 16 + 15 条全绿；前端构建通过。**未出片、未重启后端、未提交。**

**第二十二批已落地（G2 作品流 + G4 发布指标 + G5 风格成效 · 2026-11-06 · 零生成费）**：新建 `services/drama_works.py` + `services/drama_metrics.py`，3 + 2 条路由，前端「作品流」「效果回流」两张卡。

- **G2 作品流**：跨项目成片墙，只列盘上真有视频的（合成片 > 拼接整片 > 最后一段，与 `_film_video` 同口径）；
  按**视频文件 mtime** 倒序、上限 200。封面优先人压过字的 `film.cover`；早于封面列的片子按请求惰性回填首帧
  （每次最多 6 张，`BACKFILL_MAX`），写进 `film.poster` —— **不覆盖 cover**，回填失败不拦列表。
  🩸 竞品按 `compositions.createdAt` 排序；我们没有 compositions 表，文件 mtime 是唯一真实时间，不编。
- **G4 指标回填**：`GET / POST /projects/{pid}/metrics`。风格/品类在**录入时定格**（配方 `styleType`，没有则 `custom`；
  品类取商品 `category`），之后改配方不污染历史。五个数字按 JS `Math.max(0, Math.floor(Number(v)||0))` 归一
  （`"12万"` → 0、负数 → 0、`"1e3"` → 1000），备注截 500，发布日存毫秒；列表新的在前（同毫秒严格递增）。
- **G5 风格成效 + 反哺**：`GET /insights/styles` 按风格/钩子聚合 `samples / avgViews / engagementRate(赞+评+转/播放) /
  conversionRate(成交/播放) / totalOrders`，转化率降序、同分按样本数；`topConverting*` 要求 **≥2 条样本且转化 >0**
  （冷启动不硬报）。剧本阶段把 `buildPerformanceHint` 原文注进生成提示：**同品类优先，样本不够回落全局**，
  读失败只跳过、不阻断生成；冷启动什么都不加。
- 前端：「作品流」卡不选项目也可见，缩略图 + 内联播放；「效果回流」卡在项目内，录入表单 + 风格/钩子成绩单，
  「播放」必填，保存后保留平台、清空其余。
- 🩸 我们的结构卡只有 `H1–H5` 五个钩子编号（`references/output_card.md`），没有竞品那套 `visual_shock…` 机制名
  → 下拉只给 H1–H5，不替模型编中文名。

探针 **3080** 条全绿（80 个文件，实测于第二十二批收尾：G2/G4/G5 新增 **147** 条 = 成效纯逻辑 73 + 作品流 31 + 接口 43；G3 新增 97 条 = 纯逻辑 67 + 接口 20 + 真联网 10；H2/H4 新增 144 条；D7/F8 新增 147 条；A2/A3 新增 140 条；D8 新增 95 条；D1 新增 132 条；B9 新增 133 条；B3 122 / B4 补完 62 / B6 73 / B7 67 / B8 54）；前端 UI 新增 27 条全绿（`temp/shot_g2g4g5_ui.py`）；前端构建通过。**未出片、未重启后端、未提交。**

**第二十三批已落地（C4 平台 Key 连通性 + C17 云端任务恢复 · 2026-11-06 · 零生成费）**：新建 `services/drama_probe.py` + `services/drama_tasks.py`，`ark.fetch_task/retrieve_task`，4 条路由（`GET/POST /probe`、`GET /tasks` 改造、`POST /projects/{pid}/tasks/{no}/resume`），前端「云端任务恢复」卡 + 设置卡「测连通」/「全部测一遍」。

- **C4 连通性**：只做**只读**探针，统一 12 秒超时。LLM（DeepSeek）真的发一次 `max_tokens=64` 补全 —— 触顶（400/422 且报 max_tokens/output limit）就去掉上限重试一次，仍触顶判 `ok` + `warning`（说明会被截断）；401/403 → `invalid`，404 → `unknown`（先怀疑模型名）。平台（火山）打 `{base}/models`：401/403 → `invalid`（提控制台/项目授权），**2xx 也只判 `unknown`** —— `/models` 能取不代表有权出图/出片，不骗人。Key 只从服务端配置读，登记接口只回 `configured` 布尔，上游错误原文只进日志。豆包语音 / AI MediaKit / MiniMax 没有只读鉴权端点 → 标 `unsupported` 并写原因，**不编假探针**（不拿生成接口试）。
- **C17 任务恢复**：`GET /tasks` 从内存 `film.running` 改为**扫盘** —— 项目 JSON 的 `film.running` 是「任务源」，`films/<pid>/<out>.task.json` 是「任务号源」；有任务号 = `submitted`（可领回），没有 = `unknown`（先别重提，去平台确认）。领回走 `ark.fetch_task`（只查询）→ 成功才下载，**任何情况都不重新提交**；还在跑如实回报「过一会儿再点」，平台 failed/expired 如实回报并**保留登记**（不自动清，防主人以为已经处理过）。分类计数在 `limit` 之前算，保证 `submitted + unknown == count`。
- 前端：不选项目也能看到「云端任务恢复」卡（带固定提示「别重复提交」）；设置卡每个可探测通道旁一个「测连通」，底部一个「全部测一遍」；不支持的通道直接写「为什么不支持」，不给按钮。
- 🩸 为什么 `ark` 2xx 不判 ok：竞品 `test-provider` 对平台只验鉴权，但火山出图/出片是模型级授权（要开通具体模型、要 endpoint），`/models` 通过 ≠ 能出片 —— 判 `ok` 会让主人以为万事俱备。

探针 **3208** 条全绿（83 个文件，实测于第二十三批收尾：C4/C17 新增 **128** 条 = 连通性纯逻辑 61 + 任务恢复 26 + 接口 41；G2/G4/G5 147；G3 97；H2/H4 144；D7/F8 147；A2/A3 140；D8 95；D1 132；B9 133；B3 122 / B4 补完 62 / B6 73 / B7 67 / B8 54）；前端 UI 新增 20 条全绿（`temp/shot_c4c17_ui.py`）；前端构建通过。**未出片、未重启后端、未提交。**

**第二十四批已落地（B11 媒体解构 + G1 批量作业 · 2026-11-06 · 零生成费）**：新建 `services/drama_media_lab.py` + `services/drama_batch.py`，5 条路由，前端「媒体解构」「批量作业」两张卡。**这是 77 条表里的最后两条。**

- **B11 媒体解构**：图片直读；视频先出速览图（8 帧 / 缩略 200 / 波形 100，复用 `drama_contact_sheet`），再把「时长 + 切点数 + 代表帧时间」作为采样上下文。视觉调 `deepseek-flash`（原生读图），提示词要求「不说话式空话、不认人、不猜身份、给出可复用的生成提示词」。模型漂移的 JSON 按竞品规则收敛：摘要 600、标签 120×8、适用场景 5 条；视频多一段动效（节奏/镜头运动/剪辑节奏）。
  **Key 只从服务端读** —— 竞品是前端把 `llmConfig`（含 Key）一起发上来，我们不照抄这条。
  解构结果可一键存进项目（`PATCH /projects/{pid}/production`，字段 `media_type/summary/tags/reusable_prompt`）。
- **G1 批量作业**：JSON 落盘（`<data>/batch/jobs.json`）等价 `batch_jobs` / `batch_job_items`；条目五状态、作业三状态、同一时间只一个在飞、错误截 500、写回 best-effort，全部照 `route.ts`。
  反同质化照 `variation-plan.ts`：**mulberry32 与 JS 逐位对拍**，轮换 H1–H5 钩子 / 免费中文音色 / 卡拉OK隔条开；槽位随作业 config 落盘，续跑用原计划；新建项目时把 `preferred_hook` 带进结构卡提示词（对应竞品 `preferredHookId`）。
  前端执行器并发 **3**，逐条写回：建项目 → 复制商品图（失败不拦）→ 结构卡 → 确认 → 剧本 → 分镜，然后标完成。
- 🩸 **和竞品的两处老实差异**：① 我们**只做到分镜就绪，不自动出片**（出片只归主人点，这是硬规矩）；② 竞品还能轮 BGM 情绪档 / 剧本风格 / 时长抖动，我们没有对应物（合成 BGM 只收上传文件、风格由模板定、片长只支持 15/30/60）→ **不编**。

探针 **3348** 条全绿（86 个文件，实测于第二十四批收尾：B11/G1 新增 **140** 条 = 批量 53 + 媒体解构 48 + 接口 39；C4/C17 128；G2/G4/G5 147；G3 97；H2/H4 144；D7/F8 147；A2/A3 140；D8 95；D1 132；B9 133；B3 122 / B4 补完 62 / B6 73 / B7 67 / B8 54）；前端 UI 新增 26 条全绿（`temp/shot_b11g1_ui.py`，含真文件选择 + 真上传 + 批量两条跑完）；前端构建通过。**未出片、未重启后端、未提交。**

**第二十五批已落地（C12 真实感三档 + D3 人声落地接线 + H4 五版迁移 + F7 关键帧 lint + H3 上传双查 + 真人脸闸门 + 素材组回收 · 2026-11-06 · 零生成费）**：主人先点名三条「部分」说「补」；补完核对时又抓出 **F7 / H3 也被标着「部分」、以前却被算进整格**，主人再次说「补」→ 一起补齐，**汇总回到 ✅77 / 部分 0**。新建 `services/drama_realism.py` + `services/drama_voice.py` + `services/drama_prompt_lint.py`，改 `drama_film.py` / `drama_compose.py` / `drama_settings.py` / `drama_grid.py` / `api/drama.py`，前端出片面板 + 配音试听卡 + 合成面板 + 设置卡 + 关键帧逐格提示。

- **C12 真实感三档**：`auto` / `constraints` / `off` 三档，逐条照 `motion-prompt.ts:53-70 / 150-260` 与 `emotion-acting.ts:26-90`：品类材质约束（美妆/食品/家居日用/服饰鞋包/数码3C 各一句）、物理交互词（每类 3 条）、活背景 6 条、发丝衣料惯性、情绪六档过程句。镜型归一把我方 `purpose` / 分镜 `product` 字段 / 角色名映射到竞品六种镜型；🩸 **只映射矛盾升级 / 商品登场 / 反转爽感三拍**（冲突爆发→hook、收束→cta 会给吵架镜和落败角色塞反情绪，故不映射，理由写进文件头）。`off` 档**逐字等于老提示词形状**（回归对照过）。出片面板三 chips、存进项目与全局默认。
- **D3 人声落地接进合成链**：逐句 TTS 落 `<data>/voice/<pid>/<shot_id>.mp3` 并量实际时长；合成计划按镜算槽（`duration × 实际/计划`），有配音过 `voice_ground_chain`（HP 90 / LP 9500 / 3:1 / 激励器），没配音填静音占位，逐镜 `atrim` 后 `concat`，最后再 pad/trim 到段实际时长；整条时间线垫 `room_tone_source()` 棕噪（**有 TTS 0.008 / 仅原生声 0.004**），顺序照 `composer.ts:525-548`：接音轨 → 底噪 → BGM。`voice_ground:false` 显式关掉逐字回老图形；配音超槽位 / 文件丢失都给中文 warning 并回退。新增 `GET/POST/DELETE /projects/{pid}/voice`，`/tts/ground` 标 `wired:true`。
- **H4 五版迁移史**：`SCHEMA_VERSION=2`，设置中心 6 → **9 个全局默认**（新增成片分辨率 / 接缝默认 / 真实感默认），v2 迁移按 `setdefault` 补齐不覆盖用户值。竞品五条事故修复做成**旧版设置导入**（`POST /settings/import`）：v1 失效模型名（三个官方 host 各自换名）· v2 Pollinations 停用端点 + 占位 Key · v3 Ollama `localhost→127.0.0.1` · v4 生产方案 → `balanced` · v5 Atlas 素材网关 → 聊天网关；**只在 baseUrl 命中官方端点时改写、幂等**，自建代理和用户自选模型一律不动；导入报告逐条列「搬了 / 修了 / 没搬为什么」。
- 🩸 **诚实说明**：这三条是「补齐」不是「补真数据」—— 竞品那五版事故史我们确实没有（密钥一直走环境变量、没有旧持久化文件），所以**没有编五条我们自己的事故**，而是把五条修复做成可执行的导入迁移。D3 的成片验证只在本机 ffmpeg + 合成色块上跑（探针 47 条含一条真合 7 秒成片），**没调任何付费出片接口**。

- **F7 提示词卫生 lint（追加）**：新建 `services/drama_prompt_lint.py`，逐字照 `prompt-lint.ts:18-69` 搬 10 条时序词模式与「动作前一瞬定格」中/英指令句（连竞品单测里的正反样本一起验）。九宫格出图提示词末尾挂指令句；`_grid_plan` 逐格算 `cell_lints`，关键帧卡逐条显示（只提示不拦）。🩸 接线口径：竞品扫的是素材卡的 `asset.prompt || asset.description`，我们一格就是一张关键帧 → 扫每格 `description` 并带格号。
- **H3 上传白名单（追加）**：`_save_upload` 补 **MIME ↔ 扩展名双查**（`image/png` 配 `.png`；空类型 / `octet-stream` 按扩展名兜底，避免把 RPA / curl 误挡）；`_path` 补项目号正则 `^[A-Za-z0-9_-]{1,40}$`，所有按 pid 取文件的接口一起挡住 `../`、`a/b`、`p1.json`。🩸 有意收窄：仍不收 gif / svg / bmp（SVG 会让同源静态服务执行脚本）。

- 🩸 **主人指正后的修正（同日）**：MiniMax 不是本产品的配音通道 —— 它的 Key 属 **H3 视频线**，本产品付费配音读项目级 `tts.apiKey`。因此：设置中心密钥区 **5 → 4 行**（去掉 MiniMax；豆包语音标签改「转写」，它在 B7 转写里才用到）、C4 自检 **5 → 4 通道**（请求已下架的 `minimax` 按「未知」处理，不报错）；竞品付费四家的代码原样保留（D1 对照不破）。

- 🩸 **出片真人脸闸门（2026-11-06 现场故障）**：火山 Seedance 不收直传真人脸参考图（400 `InputImageSensitiveContentDetected.PrivacyInformation`，官方错误码 `error-codes.md:43`）。实测项目 `836e402e5693` 的 `content[2]/content[3]` = 小美/老王定妆图被拒。新增 `services/drama_refs.py`：本地 YuNet 判脸 → 有脸/判不了先入素材库换 `asset://`（复用 `ark_ingest` 的 sha1 缓存 + LRU 配额回收）→ 没脸照旧走公网 URL；入库失败/素材库没配**直接拦住不花钱**，不退回直传。出片五个参考图入口（板/商品/人物/每镜素材/尾帧）全部改走这道闸。

- 🩸 **素材组回收（同日补）**：素材库额度全账号 **50 素材 / 50 组**，入库不回收跑两单就满。补两处**终态**回收 `_recycle_assets(pid, why)`（`api/drama.py`，best-effort，包 try/except 绝不影响主流程）：**整片拼好**（`film_concat` 成功后）、**项目被删**（`delete_project` 后）；内部走 `ark_ingest.recycle_render(pid)`（同复刻线 `clone_jobs.py:237`），只删火山侧、本地登记表标 `recycled` 留痕。🩸 **分段出片期间不回收** —— 后续段还要吃 sha1 缓存；没拼成 / 缺段 / 只有一段都不回收（有 `ark_ingest` 的 1 小时节流 `recycle_stale()` 兜底）。

🩸 **诚实说明**：C12 / D3 / H4 是「补齐」不是「补真数据」—— 竞品那五版事故史我们确实没有（密钥一直走环境变量、没有旧持久化文件），所以**没有编五条我们自己的事故**，而是把五条修复做成可执行的导入迁移。D3 的成片验证只在本机 ffmpeg + 合成色块上跑（探针 47 条含一条真合 7 秒成片），**没调任何付费出片接口**。

探针 **3690** 条全绿（93 个文件，实测于第二十五批收尾：C12 **85** + D3 语音 **47** + 配音接口 **29** + 设置迁移 **62** + F7 lint **57** + H3 上传 **32** + 真人脸闸门 **21** + 素材回收 **17**；既有断言随字段/版本/提示词形状更新：设置 51、密钥选项 49、TTS 接口 33、模板 92、自检 62、连通/恢复 43。上批 3348 → 本批 3690）；前端 UI 新增 13 + 20 + 26 + 7 条全绿（`temp/shot_c12_ui.py`、`temp/shot_d3_ui.py`、`temp/shot_h4_ui.py`、`temp/shot_f7_ui.py`），既有 UI 探针回归 26 / 20 / 27 条全绿；前端构建通过（`npm run build:h5` → `DONE Build complete.`）。**未出片、未重启后端、未提交。**

---

## 附录-1：C9「接缝三档」——**严格版做不了，间接版能做**

### 先说结论

| 版本 | 是什么 | 判定 |
|---|---|---|
| **严格 tail**（竞品原版） | 下一镜的**第一帧像素级等于**上一镜真实末帧 | 🔴 做不了 |
| **间接 tail** | 把上一镜末帧当**一张参考图**传进去，并在提示词里指定「图片N 作为本镜首帧」 | 🟡 **能做**（模型照着画，不保证像素一致） |

### 为什么严格版做不了

火山把「怎么喂素材」分成**三套互斥的输入模式**（`/d/tmp/official/sd25/api-create-task.md:269` 原文）：

> 图生视频-首帧、图生视频-首尾帧、全模态参考生视频（包括参考图、视频、音频）为 **3 种互斥场景，不可混用**。

- 想要「第一帧就是这张图」→ 只能走 **首帧/首尾帧** 模式，槽位是 `role: first_frame`（`:235`）
- 想同时吃人物定妆 + 商品实拍 + 分镜板 → 只能走 **全模态参考** 模式，槽位是 `role: reference_image`（`:259`）
- 两个都要 = 混用 = **接口直接不收**

我们商品短剧每一镜都必须吃参考图（人物脸、商品外观），所以站在参考模式这一侧，**首帧槽根本不存在**。

### 为什么间接版能做（我上一轮漏看的就是这句）

同一份官方文档紧接着的 `:271` 写着：

> 全模态参考生视频**可通过提示词指定参考图片作为首帧 / 尾帧，间接实现**「首尾帧 + 全模态参考」效果。
> 若需**严格保障**首尾帧和指定图片一致，优先使用图生视频-首尾帧。

也就是说：参考模式里把上一镜末帧当第 N 张参考图传进去，提示词写「第 N 张参考图作为本镜首帧」，模型会照着它起手 —— 但这是「参考着画」，不是「复制像素」。接缝可能差一点，好处是人物/商品锁得住。

### 落地要点（下一批做）

- 上一镜末帧**已经有了**：`ark.py:425 _save_last_frame` 用 `return_last_frame` 取回来、落在成片旁边（`last_frame_path`），不用额外花钱
- `tail` 档必须**按顺序生成**（下一镜依赖上一镜的末帧），和竞品 `assets` 页的约束一致
- 画面里必须留出「本镜首帧 = 上一镜末帧」的参考图位，提示词编号要跟着 `@图片N` 顺延

🩸 上一版我把这条判成 🔴，是**只看了 `:269` 没看 `:271`** 就下结论 —— 正是主人说的「掐头去尾」。已改。

---

## 附录-2：建议的实施批次（等主人拍板才动）

顺序原则：**先做不花钱、能立刻纠错的；再做出片链上的；最后做发行/运营的。**

| 批 | 主题 | 条目 | 花不花钱 |
|---|---|---|---|
| **1** | 把已有能力接上（零生成费） | F2 成片 QC 接商品短剧 · E9 字幕 SRT/VTT · E1 封面 · H1 自诊断 · C3 在飞任务视图 | ¥0 |
| **2** | 交付前闸门（防废片，零生成费） | F3 发布门禁 · F4 发布前自检 · F5 广告法 · F6 AI 带货三条 | ¥0 |
| **3** | 后期加工（只重跑合成） | ✅ 已做：D2 BGM · D4 字幕四预设 · D5 转场四档 · D6 渲染三档 · D9 合成接入 · D10 尾卡 · E6 GIF · E5 速览（`services/drama_compose.py` 等 5 个新服务 + 12 条路由 + 「合成（后期）」面板） | ¥0（本地 ffmpeg） |
| **4** | 发行物料（部分调模型） | ✅ 已做：E10 发布文案 · E2 图文卡 · E3 二维码（带平台把关）· E4 多平台导出 · E7 原生感 · E8 母版（`services/drama_publish.py` / `drama_cards.py` / `drama_qr.py` / `drama_platform.py` / `drama_native_feel.py` / `drama_mastering.py` + 13 条路由 + 「发行物料」面板） | 只有 AI 版文案要 LLM 费 |
| **5** | 生成链增强 | ✅ 已做：C10 运镜预设库 · C11 Look 14 种 · C16 能力预检 · C15 变体矩阵 · A6 话题起片 · A7 多版脚本 · A8 手写脚本 · A5 品类模板（`drama_category_templates.py` / `drama_import.py` / `drama_preflight.py` / `drama_variants.py` / `drama_topic.py` + 11 条路由 + 前端 5 块界面） | 变体矩阵 ¥0 |
| **6** | 素材生态 | ✅ 已做：B1 上传三路 · B2 素材库 · **B3 免版权搜索（十源）** · B4 每镜参考画面 + **素材当画面** + **自动配画面（降级阶梯 + 诚实标注）** · B5 授权清单 · **B6 长视频导入（1GB / 2 小时）** · **B7 转写（分块 + 检查点）** · **B8 按文字剪（找片段 + 真剪出来）** · **B9 时间线导出（OTIO / EDL / CSV）** · **D1 配音（免费 Edge 11 音色 + 付费四家）** · **D8 多语言译制（13 语言，只换台词）** **｜第二十一批**：G3 趋势话题 **｜第二十二批**：G2 作品流 · G4 指标回填 · G5 风格成效 **｜第二十三批**：C4 Key 连通性 · C17 任务恢复 **｜第二十四批**：B11 媒体解构 | 已做的零费用；B3 的五个源要注册免费 Key（配环境变量即生效） |
| **7** | 运营 | ✅ 已做：G1 批量作业 · G2 作品流 · G3 趋势 · G4 指标 · G5 风格成效 · F8 结构指纹｜**77 条全清** | ¥0 |
| **8** | 待拍板项 | ~~A10 模板经济~~ ✅ 已接 · ~~B3 素材源~~ ✅ 已接（要不要注册那 5 个免费 Key 由主人定） | — |

> **第二十五批（补齐五条「部分」）**：C12 真实感三档（生成链增强）· D3 人声落地接进合成链（后期）· H4 五版迁移做成旧版导入（基础设施）· F7 关键帧时序 lint（质量闸门）· H3 上传 MIME 双查 + 项目号正则（基础设施）→ 表内 **✅77 · 部分 0**。同日现场故障再补两条：**真人脸闸门**（出片参考图判脸 → 换 `asset://`）· **素材组回收**（整片拼好 / 项目删除两个终态回收火山素材组，额度 50 组共享）。

> 🩸 每一批做完都要：**探针全绿 + 前端构建过 + 报给主人审**，不自动 commit、不自动重启后端、不出片。
