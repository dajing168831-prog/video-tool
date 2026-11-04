# H3 改动台账（2026-11-02 · 第二步）

> **这张表只干一件事**：每一改动都必须回答四问 ——
> **为什么改 / 依据哪一行 / 拿什么验过 / 现在死活**。
> 指不出官方出处的 = 自造，当场撤回；指错行号的 = 引用缺陷，当场改。
>
> 统计口径（全部现算，不凭记忆）：
> · 已提交：`git diff f226079..HEAD` = **72 文件 / +7585 / −1105**（8 个 commit）
> · 未提交：**19 改 + 11 新 = 30 项**
> · 代码里的官方引用：**347 处 / 去重 112 条 / 越界 0**（`D:/tmp/front_probe/audit_code_citations.py`）
> · 索引表引用：**308 条 / 越界 0 / 无法解析 0**（`check_map_full.py`）

---

## 0. 结论（四条）

1. **H3 主链 13 组改动，组组指得出官方行**；本轮审计当场改掉 **9 处指错/指不到的引用**和 **1 处「声明一处、读另一处」**（§2）。
2. **一半改动还没生效**：监听 `8920` 的后端进程（PID 29280）是 **2026-10-23 19:38** 启动的，今天所有改动都要重启才进内存（§3）。
3. **改写器版本（`:ir3`）已出片、没换成**（§2.2）：改写器输出已到 `[video editing + audio reuse]`，
   成片 SFace 0.069。同素材 7 次 H3 出片只成功 1 次 → **问题不在提示词**，下一个未动过的变量是**清晰度档位**（我们一直在最低的 480P）。
4. 判据现状（本轮实测）：`check_all --model h3 --fast` = **通过 55 ｜ 跳过 5 ｜ 红 0**（119.0s）；
   `test_whole_wiring --model h3` = **115/115**；
   `check_all --model volc25 --fast` = **通过 51 ｜ 跳过 3 ｜ 红 0**（520.7s）；`p46` 57/57。

---

## 1. 台账正文（H3 主链）

### H1 · 复刻接回 H3，且 H3 用**自己**的逐段指令 agent
| 项 | 内容 |
|---|---|
| **改了什么** | 新增 `app/services/h3_agent.py`（581 行）；`models/h3.py` 挂 `agent=_agent_module`；`models/base.py` 加 `Caps.agent` |
| **为什么改** | H3 = 英文 Ref2VA 六段式 + `<Picture N>`；2.5 = 中文正文 + 五段标记。原来共用 `clone_agent`，等于拿 A 的模板写 B |
| **依据** | `ref-en:5` 六段正文用英文 · `ref-en:13-22` 六段顺序 · `ref-en:26-35` 标号种类 · `ref-en:123` 任务类型方括号 · `ref-en:149-153` 编辑母版原句 · `ref-en:157-198` 关系标记 · `ref-en:68` 图只定义人物时不单开 `<Picture N>` |
| **验过** | `p46_check` **57/57**（成对探针：好样本放行 / 坏样本必红）；`check_all --model h3 --fast` = **通过 55 ｜ 跳过 5 ｜ 红 0**（122.4s，2026-11-02 本轮实测） |
| **现在死活** | **活**。共用层只调 `.generate/.cached/.load`，不 import 任何一家（模型分离门绿） |

### H2 · 清掉 H3 提示词里的自造规则
| 项 | 内容 |
|---|---|
| **改了什么** | 删「is replaced by」等**无官方出处**的闸（它们逼模型把原片外观写死，成片连服装都不换）；换人改按 `attribute_transfer` 方向写；retention 里禁写 `(Sx)`；补「没有定妆参考图」分支 |
| **为什么改** | 自造规则会覆盖官方模板，且是上一轮「换了妆造不换脸 / 换了脸搬走场景」的直接原因之一 |
| **依据** | `ref-en:167` `attribute_transfer` 定义 · `ref-en:314` 指认一个人只写发型/服装/配饰 · `ref-en:278` `(Sx)` 只按发声顺序发 |
| **验过** | `p46_check` 逐条探针；`test_whole_wiring --model h3` |
| **现在死活** | **活** |

### H3 · 参考图隔离闸（新增一条硬闸）
| 项 | 内容 |
|---|---|
| **改了什么** | SYSTEM 规定必须**原样**写 `The scene, background, lighting, and image style must not be inherited from <Picture N>; they come from <Video 1>.`；硬闸正则核对图号，缺句判红退回（最多回灌 2 次） |
| **为什么改** | 2026-11-01 实测（任务 `949c0b2f` v3 `1414210e`）：脸换对了，**整间古风庭院被搬进成片**，原片客厅没了 |
| **依据** | `music-video-subtitle-generator/SKILL.md:191` `cards isolated without cross-contamination` · `:111` 每张参考图只给一个窄任务 · `co-op-game-intro-generator/SKILL.md:24` `Do not inherit … real-world lighting … the original image style` |
| **验过** | `p46_check` 三条成对探针：GOOD 放行 / 删掉那句必红 / `must not`→`should not` 也必红（要原样，不要「意思到了」） |
| **现在死活** | **活**；⚠️ **只挂了 H3 agent 路由**，`h3_compile`（代码编译版）没加 —— 它那轮背景是对的，**没有翻车证据就不叠规则** |

### H4 · 多人换人「外观串用」
| 项 | 内容 |
|---|---|
| **改了什么** | `h3_ref` 原来整个循环共用同一份 `subject_look`（= 第一个人那句），导致 `<Picture 2>` 的男性照被写成「古装女性、浅 V 长裙」；改成**一人一份**按槽位取，没描述就退回 `<Picture N>` 纯图号，**绝不借别人那句**。人物描述加 `gender`（看不清填 `unspecified`，不许猜），带 `_v=2` 版本号 |
| **为什么改** | 实测：上传的男性照片被定义成古装女性 |
| **依据** | `base-en:129` 说话人首次出现要给「角色类型、年龄、性别…」；一人一图是产品硬规矩 |
| **验过** | `test_subject_look` 20/20；`p46` |
| **现在死活** | **活** |

### H5 · 逐段提示词改由**官方改写器**产出（H3-Context-IR）
| 项 | 内容 |
|---|---|
| **改了什么** | 新增 `app/services/h3_ir.py`（133 行）+ `minimax.context_ir()`；`Caps.prompt_for` 钩子（共用层只认「有没有这个函数」，不认厂商名）；`video_edit` 在切片之后调它，按输入指纹落盘 `data/clone/<cid>/ir/` |
| **为什么改** | 官方「全能参考生成」的示例提示词就是**一句自然语言**；结构化六段式是官方**专门做了接口**去生成的。我们让 DeepSeek 现写 = 自己充当改写器 → 同一素材四次跑出三份不同的词、三种不同的失败 |
| **依据** | `api-ir:175-179` `model` **只能填 `MiniMax-H3`**（Lite/Max/Highspeed 都不收）· `manual-full:566` 官方示例「人物参考视频1的动作，表演街舞，人物参考图1 图2」· `manual-full:608` 「视频1中最后面的小孩换成 图1中的金毛狗」· `card:90` 官方把 H3-Context-IR 列为三大模块之一 |
| **验过** | 真调一次（`D:/tmp/ir_probe/ir_out.txt`）：一句中文 → 回 4682 字六段式，含 `<Subject 1> is the woman in <Picture 1>`、`<Picture 2> is the first frame of [Shot 1]`、`<Audio 1>`、`[video editing + reference generation + keyframe completion + audio reuse]`。**实际落盘的产物**：`data/clone/949c0b2f…/ir/` 有 **3 组**输入/输出对（00:43 / 01:06 / 01:11，输出 4761 / 3552 / 4804 字节），`data/clone/0a8657e9…/ir/` 1 组（2831 字节）—— 都是六段齐全的真产物 |
| **现在死活** | **半死**：代码在，**后端没重启 → 线上仍走旧路径**；界面已改成「出片时由官方改写器生成」的提示 |

### H6 · 把「长相特征」拼进改写器指令（缓存键 `:ir2`）
| 项 | 内容 |
|---|---|
| **改了什么** | 上传时算好的英文长相（`subject_desc.json` 的 `desc_en`）拼进那句自然语言；`video_edit._span_looks` 按段取 |
| **为什么改** | v5 实测（01:07）：背景对了、妆造对了、**脸没换**，SFace p90 **−0.013**。逐字读发出去的词才发现全篇只有 `a refined face`，**没有一个五官** |
| **依据** | `manual-full:667`「如果素材中有非常想要保持的特征，建议明确写出来，这样可以让一致性更好」 |
| **验过** | 改写器产出确实变成 `an oval smooth facial contour, long eyes with slightly upturned outer corners, a high straight nose, full lips, and no glasses`；缓存键升 `:ir1`→`:ir2`（指令变了不换键会命中旧段） |
| **现在死活** | 🔴 **验过、不达标**（2026-11-02 03:25，1 段 4.13s，H3-Lite 480P）：SFace 对参考图 **0.189**、对原片那个人 **0.656** → **没换成功**（阈值 0.363）。相比不写五官的 v5（0.026）确有提升，但远不够。根因见 §3 末行 |

### H7 · 音频不再从母版隐式取（口型的根因）
| 项 | 内容 |
|---|---|
| **改了什么** | 原逻辑 `not edit_task_param` 让 H3 走「母版自带音轨」分支 → 请求里**一条音频都没有**，提示词却写 `<Audio 1>` → 模型没东西可跟，嘴型必错。改成显式能力声明 |
| **为什么改** | 2026-11-01 真实快照实锤：`audio=false` / `audio_in_master=false` |
| **依据** | `ref-en:112`「An ordinary reference video does not create `<Audio N>` merely because the file contains sound.」 |
| **验过** | `p58_check`（零费用真跑整条链路，数调了几次模型） |
| **现在死活** | **未生效**（需重启）；本条已顺带修掉 §2-⑧ 的接线错误 |

### H8 · 官方错误码翻人话
| 项 | 内容 |
|---|---|
| **改了什么** | `minimax._ERROR_HINTS` 14 个码 + `_err_hint()`，接到视频任务与 IR 两条失败路径 |
| **为什么改** | 上次失败 code `1000`，界面让人以为是参数/素材问题 |
| **依据** | `api-error:15`「1000｜未知错误/系统默认错误｜请稍后再试」· `api-error:32`「2013｜参数错误」 |
| **验过** | `py_compile`；**没有专门判据**（文案层，靠人读） |
| **现在死活** | **未生效**（需重启） |

### H9 · 官方语料全量 + 索引表
| 项 | 内容 |
|---|---|
| **改了什么** | 源目录 34 文件 / 25,488 行全量重读；新抓 13 页、拷 14 份进 `backend/data/official/h3/`；索引 `docs/H3-OFFICIAL-MAP.md` 扩到 §14 |
| **为什么改** | 第一版只索引了 skill 包（30/6504），手册 / 模型卡 / API 规格 / 错误码全没读 ⇒ 每次从头翻 |
| **依据** | 30/30 文件 sha256 与源一致；`platform-docs.txt`（15,185 行全平台混合）**没进工程、禁止引用** |
| **验过** | `verify_h3_copy.py` **30/30**；`check_map_full.py` **308 条引用 / 越界 0** |
| **现在死活** | **活**（纯资料 + 文档） |

### H10 · 官方 11-02 改口径
| 项 | 内容 |
|---|---|
| **改了什么** | Highspeed 分辨率补 **480P**（旧代码只有 768P）；Lite/Max「默认 768P」注释更新（值不变） |
| **依据** | 官方价目表：Highspeed 768P ¥0.40/s、**480P ¥0.26/s**；11-02 版 create 页**删掉了**「不传时默认 768P」这句（只删说明，没说默认改了） |
| **验过** | `test_model_specs`；我们每条请求都显式带 `resolution`，兜底值不影响实际调用 |
| **现在死活** | **活** |

### H11 · `h3_skill` 瘦身（不再重抄官方规则）
| 项 | 内容 |
|---|---|
| **改了什么** | 132 行的「产品规则」删到只剩官方不可能知道的三件事：有什么工具、`prompt` 与 `note` 怎么分、「需要 Hub 画布」怎么理解 |
| **为什么改** | 主人 10-31 原话：「agents 调模型里面本来就已经有执行标准了，我们自己又再要求一次？」；而且抄漏过 |
| **依据** | `base-en:129`「preserve every original word and punctuation mark verbatim」· `ref-en:274` 听不清写 `[unclear]` · `ref-en:217` 保留原语言 · `ref-en:110` 序号只在**自己类别内** · `ref-en:35` 标签全程同义 |
| **验过** | `p9_check` 等 skill 侧判据 |
| **现在死活** | **活** |

### H12 · 切镜时间码假红修复
| 项 | 内容 |
|---|---|
| **改了什么** | 原正则扫**所有** `MM:SS.mmm,`，把镜头**内部**的事件时间码也当切点 → 报了 5 条假红；改成只扫紧跟 `[Shot N]` 的那个 |
| **依据** | `base-en:86`「begin each one with a strictly increasing cut time」—— `At MM:SS.mmm` 只属于**镜头开头** |
| **验过** | 真机复跑：4 处真切点全部是官方原句 `the camera cuts to` |
| **现在死活** | **活** |

### H13 · 冻住 / 解冻
| 项 | 内容 |
|---|---|
| **改了什么** | `Caps.frozen` 声明冻结；解冻只改 2 行（`models/h3.py` + `model_specs.MODELS["minimax"]`） |
| **依据** | 主人指令（10-31 冻、11-01 解冻），不是官方规则 |
| **验过** | 判据按 `frozen_families()` **动态断言**，不写死某一态；解冻后 `test_model_specs` 68/68 |
| **现在死活** | **已解冻**（`frozen=False`） |

### H14 · 喂给改写器的是自然语言，不是成品提示词骨架
| 项 | 内容 |
|---|---|
| **改了什么** | `h3_ir.instruction()` 去掉「参考素材说明：/ 核心创意：/ 画面过程说明：」三个小标题 —— 三段的**内容一字不增删**，只串成一个自然段；`test_whole_wiring.py` 的断言从「必须含三段」翻转成「不许含三段」＋「必须是一段话」 |
| **为什么改** | 官方调 H3-Context-IR 时 `text` 只有一句话；`h3-manual:244` 那条公式描述的是**改写器的输出**。把成品骨架当输入，改写器从「组织」变成「复述+扩写」—— 实测 4 份正文里 3 份反复写 `original woman/man`，SFace 0.021 / 0.069 / −0.012 |
| **依据** | IR 输入是一句话：`model-card-2026-10-28.md` 内链的 `scripts/readme/full-2k-ref2va-h3-context-ir.sh`、`guides_video-generation.md:143`；公式是输出结构：`h3-manual:244`；换人句式：`h3-manual:248`；想保持的特征写明：`h3-manual:248`；边界帧：`ref-en:65` |
| **验过** | `test_whole_wiring --model h3` **128/128**；`check_all --model h3 --fast` = 通过 53 ｜ 跳过 5 ｜ 红 2（p4 的 C1、p16 —— 两个脚本都不 import `h3_ir`，与本次改动无关）；模型分离门先红后修（裸 `manual:` → `h3-manual:`）已绿 |
| **现在死活** | **代码已落，未生效**（监听 8911 的后端是 10-23 启的，要重启才进内存）；**还没出过片** |

### H15 · 边界帧整条删除（第 2 段起不再带「上一段成片的尾帧」）
| 项 | 内容 |
|---|---|
| **改了什么** | `video_edit._gen_spans` 里 ①「相邻两段 + 切点不在镜头边界」的 `adjacent` 判定、②`_last_frame(pieces[-1])` 取上一段成片尾帧、③`boundary_allowed(...)` 拦截、④`bf_pic` 计算、⑤`if bf is not None: refs_list.append(bf)` 全部删除，改为 `bf = None` / `bf_pic = 0` / `bf_mark = ""`（段缓存键里的 `:bf3` 标记随之消失）；`_boundary_used()` 恒 `return False`，老判定改名 `_boundary_used__retired` 留墓碑；`boundary_allowed()` / `_last_frame()` 已无调用点，留墓碑不删。判据同步：`test_whole_wiring.py` 9 条、`test_video_edit_logic.py` 2 条正向断言全部翻成「不带」 |
| **为什么改** | 接缝信息**本来就在参考视频里**：第 2 段的参考视频是 `scene.cut_clip(video, a, cut_b)` 从原片单独切出来上传的，且 `a` 恰等于上一段的 `b`（分段定义，误差 1e-3）；中间段还往后多借 `_EXTRA = 0.5` 秒 —— 接缝那半秒**两次生成都看过原片**。再叠一张「上一段成片的尾帧」，是整条链上**唯一一个非原片来源的输入**，等于让模型从自己上一次的产物接着演，误差会累积。主人 2026-11-02：「把边界帧**彻底删掉**」 |
| **依据** | 官方两家**都没有**这个要求：火山只说「新片段的第一个画面承接**原视频**尾帧」（`sd25-pe:649`）、「原视频控制延长边界」（`sd25-pe:695`）—— 承接的是**原视频**，不是上一段生成结果；H3 只在 `ref-en:65` 规定「一张图当首帧时该怎么写」，不涉及要不要带。这套机制来自第三方 hypit，原句 2026-10-23 已删、机制一直留到现在 |
| **验过** | `test_whole_wiring --model h3` **128/128**；`test_video_edit_logic --model h3` **84/84**；`check_all --model h3 --fast` 全绿，唯一红项是 `p16` 的 S3（SFace 尺子自证「不同素材之间中位 0.575」，是量具既有问题，与本次改动无关 —— 两个脚本都不 import `video_edit` 的边界帧分支之外的东西） |
| **现在死活** | **代码已落，未生效**（监听 8911 的后端要重启才进内存）；**还没出过片**。⚠️ 缓存键少了一段 `:bf3`，带边界帧与不带是两种**真实不同的输入**，旧段缓存自然不复用（不会因此误命中） |

### H16 · 换人的定性从「视频编辑」改成官方范例的「动作参考 + 替换为」
| 项 | 内容 |
|---|---|
| **改了什么** | `h3_ir.instruction()` 换人分支那一句：`视频1是被编辑的原片，视频编辑：把视频1中的人物换成图N中的人物` → `视频1提供了动作参考和运镜参考，锁定动作和运镜；场景、背景、光线也来自视频1；视频1中的人物替换为图N中的人物`。**只动这一句**，`idea` / `process` 两段本轮的改动一个词没碰。判据同步：`test_whole_wiring.py` 的「用途写成视频编辑」翻转成「动作参考 + 不许出现视频编辑」＋新增两条（写「替换为」不写「换成」／场景背景光线点名）；黑名单里的 `场景、背景` 移出（有出处了，不是放宽） |
| **为什么改** | 官方换人范例用的是「动作模仿 + 替换成」，不是「视频编辑」。定性不同 → 改写器判的任务类型不同 → 保留标记不同：写「视频编辑」的 8 份产出，改写器一律判 `[video editing]` 并把 `<Video 1>` 标成 `partially_preserved`；写「视频1提供了动作、镜头和口型」的 4 份，判 `[reference generation]` 并标 `attribute_transfer`。**唯一换脸成功那次（SFace p90 0.575）在后一组** |
| **依据** | 官方换人范例 `h3-manual:192`：「参考视频1进行动作模仿。固定机位全景镜头，正视频中三个穿西装的男人**替换为**三只高度写实的水豚。水豚必须**严格遵循原视频的运动轨迹**……保持原有的固定机位不变。确保水豚的毛发质感和光影与环境融合」；同款 `h3-manual:189`「图1的人物动作、表情与表演节奏**严格参考**输入视频1」；用途词表 `h3-manual:248`「动作参考（锁定动作）」「运镜参考（锁定运镜）」；保留标记定性 `ref-en:167` `attribute_transfer` = 特征转移给**另一个可识别主体** vs `ref-en:166` `partially_preserved` = 内容还在用但部分特征被改掉 |
| **验过** | 干跑 `D:/tmp/show_instr2.py` 打印四种情形全文（单人/无五官/双人/无人物）；`test_whole_wiring --model h3` **130/130**；`test_edit_spec --model h3` **288/288**；`test_video_edit_logic --model h3` **84/84**；`check_all --model h3 --fast` 全绿，唯一红项仍是 `p16` 的 S3（SFace 尺子自证，与本次无关）；`model_separation_check.py` 8 项全绿 |
| **现在死活** | **代码已落，未生效**（后端要重启）；**还没出过片**。缓存键由 `prompt_sig` 自动带上指令文本，改了指令 → 键必变 → 下次每段重新生成（会扣费） |
| **已知未改** | ① 双人时 `idea` 仍只写「主体是图1中的人物」，同句没提第二个人（既有问题，不是本轮引入）② 无人物分支（`else`）仍写「视频编辑：在视频1上做改动」——本轮为守住单一变量没碰，下一轮单独看 |

### H17 · 段内镜头切点进改写器输入（原片 5 镜 → 产出只有 `[Shot 1]`）
| 项 | 内容 |
|---|---|
| **改了什么** | ① `h3_ir.instruction(..., cuts=None)` 新增参数，有切点时在「画面过程说明」开头插一句 `这一段原片有 N 个镜头，切点在 X、Y 秒；`；空列表一个字不加（单镜头行为与改前一致）。② `prompt_sig` / `prompt_for` 同步加参数并转交（切点进指纹，改切点 → 键必变）。③ `video_edit._gen_spans` 的两处调用点把已有的 `cuts` 传进去。判据同步：`test_whole_wiring.py` 新增 4 条（单镜不提切点／有切点写明镜头数和秒数／切点进指纹／出片链路真的把段内切点交给了改写器） |
| **为什么改** | 原片是多镜头的（`06386173` 分诊 shots=5、`68a96c9f` shots=17、`22dd24bc` shots=10），但全部 20 多份 IR 产出**只有 `[Shot 1]`，一个 `At 00:` 时间码都没有**。切点一直只喂给火山/2.0 的编译器（`video_edit` 的 `cuts`），**从没进过 IR 的 text** —— 改写器不知道有几刀，就按一镜到底写，原片的切镜节奏丢了 |
| **依据** | `base-en:86`「Use sequential shot numbers for later shots, and begin each one with a **strictly increasing cut time** that falls within the video duration」；`ref-en:242`「Video-editing descriptions scale with the complexity of the source video」；官方三镜示例 `official/dfe52602.txt`：`[Shot 2] At 00:03.000 …` / `[Shot 3] At 00:05.000 …` |
| **验过** | 干跑 `D:/tmp/show_instr2.py`：单镜不提切点、5 镜写「这一段原片有 5 个镜头，切点在 1.18、2.36、3.54、4.72 秒」、指纹随切点变化（`bb49c0f9e9ae` ≠ `1cd4c0e5f8f4`）；`test_whole_wiring --model h3` **134/134**；`check_all --model h3 --fast` 全绿，唯一红项仍是 `p16` 的 S3（SFace 尺子自证，与本次无关） |
| **现在死活** | **代码已落，未生效**（后端要重启）；⚠️ **产出侧没实测** —— 改写器拿到切点后会不会真的写成多个 `[Shot N]`、切点时间对不对，要真调一次 IR 才知道（落盘在 `data/clone/<cid>/ir/`，出片后可直接核）。**在拿到那份产出之前，不能宣称「多镜头已修好」** |
| **已知未改** | 切点是**分诊算出来的**，若分诊本身把两个镜头判成一个（快切/闪白），IR 拿到的就是少一刀 —— 那是分诊的问题，不是这条链路的 |

### H18 · 音频的用途写进改写器输入（搬了素材却一个字没说它是什么）
| 项 | 内容 |
|---|---|
| **改了什么** | ① `h3_ir.instruction(..., audio_mode="")` 新增参数：`original` → `音频1是视频1的原声轨，成片复用这条原声`；`tts` / `mix` → `音频1是成片的配音轨，人物台词按这条音频`；空 → 一个字不加。② `prompt_sig` / `prompt_for` 同步加参数并转交（也进指纹）。③ `video_edit._gen_spans` 两处调用点传 spec 的 `audio`，**默认值取 `tts`，与 `_audio_track()` 的 `spec.get("audio") or "tts"` 对齐**（否则 spec 不写 audio 时音轨照传、提示词却一个字不提）。判据同步：`test_whole_wiring.py` 新增 5 条 |
| **为什么改** | 音频素材一直**传进了** IR（`prompt_for(audio=…)`、`context_ir` 里标 `role=reference_audio`），但 `instruction()` 全文不出现「音频」二字 —— 用途全凭改写器自己猜。它猜成 `fully_copy` 那次，同一份产出的 `non_diegetic_music` 直接写成 `N/A`；原片要是有 BGM，就被判没了 |
| **依据** | `h3-manual:248` 用途词表：「音色参考（锁定音色）」「音频复用（生成视频的音频直接复用参考音频素材）」「音频部分复用（生成视频某个声音轨道/某个时间段部分复用参考音频素材）」，同段还有「在音频复刻/部分复刻中…强烈建议补充具体歌词文本内容」；编号按类型各算：`ref-en:110`「`<Video N>` and `<Audio N>` are numbered independently」 |
| **验过** | 干跑四种模式（空 / original / tts / mix）打印全文；`test_whole_wiring --model h3` **139/139**（新增：无音轨时不提音频1／原声模式写明复用／配音模式写明配音轨／不写回「同步音轨」「直接复用」两句老措辞／无音轨时链路传空串）；`check_all --model h3 --fast` 全绿，唯一红项仍是 `p16` 的 S3（SFace 尺子自证，与本次无关）；`model_separation_check.py` 8 项全绿 |
| **现在死活** | **代码已落，未生效**（后端要重启）；**产出侧没实测** —— 改写器拿到音频用途后 `non_diegetic_music` 还会不会写 `N/A`，要真调一次 IR 才知道 |
| **已知未改** | ① 歌词/台词原文还没写进 IR 输入（`h3-manual:248`「强烈建议补充具体歌词文本内容」）—— 我们的台词走 `voice_lines`，本轮为守住单一变量没接；② 音频是整条混音（人声+音乐+环境声），不是干净音色样本，`audio_mode` 只说明用途、不改变这个事实 |

### H19 · 换人写成「哪张图换哪一位」（只点名图1 → 第二张参考图发出去没人用）
| 项 | 内容 |
|---|---|
| **改了什么** | ① `h3_ir.instruction()`：`person_pic`（只记第一个）→ `person_pics`（记全部人物槽位），`idea` 改成 `主体是图1、图2中的人物…`。② **逐张指派**：新增 `ppl=`（与人物槽位同序的盘点记录，写方位）与 `frame_n=`（**这一段画面里一共有几个人**）。③ **要不要写方位由 `frame_n` 决定，不由图片张数决定**：`frame_n<=1` → 原句一字不改（「视频1中的人物替换为图1中的人物」）；`frame_n>=2` 且方位齐 → `图1中的人物替换左边那位，图2中的人物替换右边那位`；`frame_n>=2` 但方位缺一个 → 整句退回 `图1、图2 各替换一位`（只换一位时是 `图1 替换其中一位`）；`len(图) < frame_n` 才加 `，其余出镜人物保持原样`（全换时不加，因为没有"其余"）。④ `video_edit._gen_spans` 建 `ir_ppl`（`_span_people`）与 `ir_frame_n`（`vision_plan.people_in(inv, a, cut_b)`），传进 `prompt_sig` / `prompt_for`（都进指纹）。判据同步：`test_whole_wiring.py` 新增 13 条 |
| **为什么改** | 第一步事实：`1b3df54b` 11:48 那份 IR 产出**只定义 `<Subject 1>`**，`<Picture 2>` 发出去了却全文零引用，正文写「Beside her, two young men stand」但没定义其中任何一个；同素材 08:51 那版（「视频编辑」写法）定义了 3 个 Subject、两张图都用上。全库 3 份双人 IR 只有这一份塌了，时间点正在 H16 之后 —— **这是 H16 的「已知未改①」，上一轮记了没修**。第二步主人指出：那单原片**本来就是 3 个人**（左女 P1 / 中男 P2 / 右男 P3），只勾了 P1、P3 —— 「各替换一位」没说是哪一位。第三步主人再点：「**有些视频里面本来就是一个人，有些是多人换一人**」—— 所以判别条件必须是**画面人数**，不是上传张数；原片只有一个人时写「左边那位」等于凭空造一个区分，原片多人只换一位时不写方位等于让模型猜 |
| **依据** | `ref-en:37`「`subject_definitions` defines **each** piece of referenced content that must be tracked separately later… name the corresponding source asset」＋「If `<Picture N>` or `<Video N>` **only identifies the source of another referenced item and will not be analyzed or used separately later**, cite it inside that item's definition without adding a separate line」—— `<Picture 2>` 是要转移长相的独立主体，不是别人的来源，必须有自己的一行；官方换人范例 `h3-manual:192`「视频中**三个**穿西装的男人替换为**三只**高度写实的水豚」既是复数对应、也说明「换掉几个/留下几个」要写清。方位词不是自造：同素材 08:53 那份**成功的**产出里，改写器自己写的就是 `<Subject 1> … the woman on the left` / `<Subject 2> … the speaking man on the right` / `<Subject 3> … the young boy in the middle, remains unchanged` |
| **验过** | 干跑 7 种「画面人数 × 图片张数」组合（1人1图／3人换1人／3人换2人／2人全换／3人换1人无方位／盘点缺人数／人-场景-人串号）＋真实任务数据 `D:/tmp/new_task_check2.py`（新任务 `7f86ebd0`：`frame_n=3`，勾 P1P3 → 左边那位+右边那位+其余保持；勾 P1 → 左边那位+其余保持）；`test_whole_wiring --model h3` **152/152**；`test_edit_spec --model h3` **288/288**；`test_video_edit_logic --model h3` **84/84**；`check_all --model h3 --fast` 全绿，唯一红项仍是 `p16` 的 S3（SFace 尺子自证，与本次无关）；`model_separation_check.py` 全绿 |
| **现在死活** | **代码已落，待重启后端生效**；**产出侧没实测** —— 改写器拿到逐张指派后会不会真的定义两个 Subject，要真调一次 IR 才知道（落盘在 `data/clone/<cid>/ir/`）。⚠️ 单换人这条从「不写方位」改成「画面多人时写方位」是**行为变化**，之前 SFace 0.575 那次用的旧写法，这条没出片验证过 |
| **没证实的一件事** | 11:50 那次 `code 1027 output new_sensitive`（官方 `api_errorcode.md:22`「输出内容涉敏」）**不能归因于这条**：API 回的 `output_sensitive_type` 是 null，不给细分。能确定的只是「同素材同参数，08:53 旧提示词成功、11:50 新提示词被拦，唯一变量是提示词」 |

### H20 · 换人句按 `h3-manual:192` 的**五段**重排 + 「人数未知 ≠ 单人」拆开
| 项 | 内容 |
|---|---|
| **改了什么** | ① 换人句从「一句话里塞三件事」改成官方范例的五段结构，顺序照抄：`参考视频1进行动作模仿；<替换句>；<人物>必须严格遵循原视频的运动轨迹，保持原有的机位和分镜不变；场景、背景、光线也来自视频1，光影与环境与原片融合`。② 把「画面里有几个人（K）」和「这次换几个人（M）」在代码里显式拆成 `_k` / `_m` 两个量，判别改成三支：`K==1` → 不写方位（没有"哪一位"可分）；`K>=2` → 有方位就逐张指派、缺一个就整句退回泛称；**`K==0`（盘点没给人数）→ 有方位就写、没方位退回泛称**，不再和 `K==1` 共用「不写方位」。③ `其余出镜人物保持原样` 的判据从 `_multi_frame and …` 改成 `1 <= _k and _m < _k` —— 人数未知时不知道有没有"其余"，**不写** |
| **为什么改** | 主人两处点破：先是「到底哪些是有出处哪些是自造的」，逐条 grep 后发现换人句里真正有官方出处的只需要那五个要点，句子里多出来的组织方式是我自己搭的；接着「**因为你这个是单人视频还是换一个人的时候！所以逻辑有点乱了**」—— 代码里 `frame_n == 0` 和 `frame_n == 1` 确实走了同一个 `else` 分支，前者是"数据缺了"、后者是"确实是单人"，把两件事混成一个判据，等于拿缺数据当事实 |
| **依据** | 五段结构 = `h3-manual:192` 官方换人范例逐句：①「参考视频1进行动作模仿」②「三个穿西装的男人替换为三只高度写实的水豚」③「水豚必须严格遵循原视频的运动轨迹」④「保持原有的固定机位不变」⑤「确保…光影与环境融合」。逐张指派 = `h3-manual:213`「视频1中最后面的小孩换成图1中的金毛狗」。方位词来自盘点，不是我编的（同 H19）。`K==0` 时写方位不违反任何官方条文 ——「官方没写」不等于「禁止」，这里是**已知事实就写、未知就不写**，不是新增规则 |
| **验过** | 真实任务 `7f86ebd0`（原片 3 人）三种 `frame_n` 干跑对照（`D:/tmp/ppl_check3.py` → `D:/tmp/ppl_check3.txt`）：`frame_n=3` 换2人 → 左边那位+右边那位+其余保持原样；`frame_n=0` 换2人 → 同样逐张指派但**不带**「其余保持原样」；`frame_n=1` → 退回「分别替换为图1、图2中的人物」；换1人时 `frame_n=3` 带「其余保持原样」、`frame_n=0` 不带。`test_whole_wiring --model h3` **155/155**（新增 3 条：人数未知有方位照写／人数未知不写「其余」／人数未知无方位退回泛称）；`test_edit_spec --model h3` **288/288**；`test_video_edit_logic --model h3` **84/84** |
| **现在死活** | 代码已落，**待重启后端生效**；**产出侧仍未实测** —— 改写器拿到这五段 + 逐张指派后落成几个 `<Subject N>`、`<Video 1>` 定成 `attribute_transfer` 还是 `fully_preserved`，要真调一次 IR 看 `data/clone/<cid>/ir/seg_*.txt` 才知道。⚠️ 全部改动都没出片验证过 |
| **撤回记录** | 同轮我一度要把「锁定动作」「视频编辑」列进判据黑名单 —— `h3-manual:248` 的用途词表里两个都是官方词，**当场撤回**（判据回到「只验该有的五个要点在不在」，不设黑名单）。另：「frame_n 单人时不写方位」这条**本身没有官方明文**，是我从「单人没有第二位可分」推出来的，主人追问后确认属于自造规则 —— 但现在它只是**不提一个不存在的信息**，不约束模型行为，保留并写明「无明文」 |

### H21 · 这一段**真实说过的台词 + 相对秒数**写进改写器输入（它在补台词，模型就重念一遍）
| 项 | 内容 |
|---|---|
| **改了什么** | ① `h3_ir.instruction(..., lines=)`：新增台词行，拼进「画面过程说明」段 —— `这一段原片里说了这些台词，秒数相对本段起点：0.00–1.11 我词穷了已经；1.67–5.63 …；`，没台词时**一个字不加**（行为与改前一致）。② `video_edit._span_script(rec, a, b)`：从配方算出这一段真实说过的台词与相对秒数。归属按**字的中点**（跨界那个字归真正念它的那一段，不两段都算）；字级时间只有 ASR 那份有，按「文字完全一致」才借，避免重新配音后把原片的字级时间套到新文案上；没有字级时间就按整句时间**按比例**裁（与 `_span_lines` 同一套算法）。③ `prompt_sig` / `prompt_for` / `_gen_spans` 全部透传，台词**进缓存指纹** |
| **为什么改** | 主人报「第二段开始嘴型对不上了」。查出来：`db253cfc` 分 2 段（0–4.133 / 4.133–18.067），第 2 段音频起点经互相关实测是原声 **4.120s**，而原片字幕在 4.00–4.25 之间才从「然后我就这一个样品」切到「我词穷了已经」—— 这一句**只留了个尾巴在这一段**。改写器只拿到音频没有文字，就把上半句补全、当成第 2 段的第一整句写进提示词；模型照着**又念了一遍**，可这段音频里几乎没有那句 → 第 2 段嘴型全程对不上。第 1 段音频从整句开头（0.04s）起，改写器听到什么写什么，文本与实际一致，所以没出问题 |
| **依据** | `h3-manual:248`「在音频复刻/部分复刻中，如果对于人声对白内容/唱歌歌词内容的保持有较高的要求，**强烈建议补充具体歌词文本内容**」—— 我们走的正是音频复用，却一直只给音频不给字；`h3-manual:251`「**注意台词的长短尽量和镜头长短对齐（这个得强调下，很多口型问题会来自于这个）**」。文字**全部来自原片 ASR**（`recipe.speech.segments[].chars[]`），一个字不编 |
| **验过** | 真实任务 `db253cfc` 干跑（`D:/tmp/h21_check.py`）：第 1 段 = `0.04–4.04 我刚开始做短视频带货然后我就这一个样品`；第 2 段 = `0.00–1.11 我词穷了已经` 起，**不再有那半句**。`test_whole_wiring --model h3` **162/162**（新增 7 条：没台词不加句／起止秒数／相对本段起点／进指纹／跨界字按中点归属 ×2／重配不套原片字级时间）；`test_edit_spec` 288/288；`test_video_edit_logic` 84/84；`model_separation_check` 全绿 |
| **现在死活** | 代码已落，**待重启后端生效**；**产出侧未实测** —— 改写器拿到台词行后会不会按 `0-5秒` 这种时间分段写、嘴型对不对，要真跑一次看 `data/clone/<cid>/ir/seg_*.txt` + SFace 才知道。⚠️ 提示词变了 ⇒ 两段都会重跑（第 1 段也重跑，不只第 2 段） |

### H22 · 外观描述「缺就补算」是死代码 → 第 2 个人只剩一个图号，换不上脸
| 项 | 内容 |
|---|---|
| **改了什么** | `_prepare(..., compute_looks=False)` 新增开关，传给 `_look_for(..., compute=compute_looks)`；**只有真出片两条路**（`replace_spans` / `replace_whole`，各 2 个 `_prepare` 调用点）传 `True`。`prepare()` 公开默认值仍是 `False`，`/plan`、`/reuse-plan` 这些零费用入口一个字没动 |
| **为什么改** | `902c4d0f` 双人换人：改写器输入里第 1 人有整套五官，第 2 人只有「人物参考图2提供了人物的形象，锁定脸和长相；」——**空的**。SFace 实测两人在 H3 段都没换上（0.336 / 0.178，阈值 0.363）。时间戳对得上：`ref_person2.jpg` 15:02:20 传入、`subject_desc_person2.json` 15:02:35 才由**后台线程**算完，而出片在 15:02:2x 就构建了 plan —— 那一刻描述还不存在。`_look_for()` 里本来就写了「缺/过期就在真出片时补算」的兜底，但**全工程没有一个调用方传 `compute=True`**（只有注释提到它）⇒ 那段代码从上线起就没执行过。同 §2 第 ⑧ 条：声明一处、消费另一处 |
| **依据** | `h3-manual:248`（全本 `official_manual_h3_full.txt:667`）「**如果素材中有非常想要保持的特征，建议明确写出来，这样可以让一致性更好**」；`ref-en:314` 官方主体定义示例就是带特征的：`<Subject 3> is the young blonde woman in <Video 1>, with long blonde hair and a light-pink button-down shirt`。⚠️ 这条改的是**接线**，不是新增规则 —— 补算逻辑本来就在代码里 |
| **验过** | ① 结构：`replace_spans` / `replace_whole` 里每个 `_prepare`/`prepare` 调用都带 `compute_looks=True`（AST 逐调用点查，不是查文本）；② 效果：把描述路径指向不存在的文件 + mock `describe_person` —— `compute=True` 时**真的调**了一次并采用结果，默认`False` 时**一次都不调**、返回空（零费用语义不变）。`test_whole_wiring --model h3` **166/166**；`test_edit_spec` 288/288；`test_video_edit_logic` 84/84 |
| **现在死活** | 代码已落，**待重启后端生效**；**未出片验证**。要验的现象：双人换人时改写器输入里**两张人物图都带五官**，SFace 两人都 ≥ 0.363 |
| **没做的一件事** | 「最后 1.37 秒走静止镜头重画、结果还是原片造型」**没有动** —— 官方语料里没有任何一句讲静帧镜头该怎么处理，没有出处就不自己定规则（主人 2026-11-02：「有的就做，没有就不做」）。这一条留作待拍板 |

---

## 2. 本轮审计当场改掉的 10 处

> 判据：官方文件里那一行**真的写着**这句话。
> 除 ⑧ 以外，改的都是**注释与说明文字**（不改请求、不改判据逻辑）；
> ⑧ 是**接线修复**（行为等价：修之前这个开关恒为 `False`）。
> ⚠️ ⑦ 与 ⑥ 里的 `h3_agent.py:524` / `_brief_golden.json` 是**拼给 agent 读的说明文字**，
> 改了行号标签 ⇒ 逐段指令的输入签名会变，**下次要重新生成一次**（不会花钱，DeepSeek 调用除外）。

| # | 位置 | 原来指的 | 实际应该是 | 官方那一行 |
|---|---|---|---|---|
| ① | `models/base.py:40`、`video_edit.py`、`scripts/p58_check.py`（共 4 处） | `ref-en:109` | **`ref-en:112`** | `An ordinary reference video does not create <Audio N> merely because the file contains sound.` |
| ② | `h3_agent.py:89` | `ref-en:127` | **`base-en:127`** | `…characters who never vocalize receive no speaker ID.`（`ref-en:127` 只是方括号**格式示例**，`h3_compile:864` 早已写明这是误读） |
| ③ | `h3_agent.py:92` | `:142` | **`ref-en:221`** | `Use <scenetrans>, <cutoff>, and the corresponding continuity descriptions…` |
| ④ | `h3_agent.py:93` | `ref-en:154` | **`ref-en:284`** | `overall_soundscape summarizes ambience and physical sounds across the full video.` |
| ⑤ | `h3_agent.py:125 / :172` | `ref-en:55-58` | **`ref-en:54-58`** | 55 是空行，示例从 54 起 |
| ⑥ | `h3_agent.py:518 / :524`、`p46_check.py:189`、`_brief_golden.json`（6 处） | `ref-en:47` | **`ref-en:314`** | `<Subject 3> is the young blonde woman in <Video 1>, with long blonde hair…`（47 是空行；314 才是 `<Video 1>` 的外观示例） |
| ⑦ | `h3_agent.py:489`（跨行字符串） | 被解析成裸 `SKILL.md:114` | 合并为一行 `music-video-subtitle-generator/SKILL.md:114` | 引用本身没错，是**写断了**导致指到 40 行的根 SKILL.md |
| ⑧ | `video_edit.py` `_master_audio` | 读 `_spec_for(...).get("audio_from_master")` | 读 **`ad.caps.audio_from_master`** | 🩸 **声明在 `Caps`、消费点读参数表字典**，而 `model_specs` 里从没人声明过这个键 ⇒ 永远 `False`，等于没接线 |
| ⑨ | `h3_agent.py:178` | `ref-en:51 / :314 / :330` | **删掉 `:330`** | `:330` 是一句 `[Shot 1]` 镜头描述，不是 Subject 定义；「只列发型和服装」的例子只有 `:51` 与 `:314` 两处 |
| ⑩ | `clone_brief.py:103` | `ref-en:198` | **`ref-en:35`** | 198 是空行；官方约束是 `:35`「Once a reference label is assigned … it keeps the same meaning across …」 |

**改完复查**：引用审计 **335 处 / 去重 110 条 / 越界 0**；原句核对只剩 2 条「带省略号的转述」，已人工确认是转述不是伪造。

### 2.1 · 改写器指令的**任务类型措辞**（2026-11-02 第三轮）

**为什么改**：改写器是按我们那句自然语言判任务类型的。旧措辞写「都**参考**视频1，
保持原样不变；口型**跟着**参考音频1」→ 输出 `summary` 是
`[reference generation + audio reference]`（拿原片当参考**重画**）；
而 11-01 换脸成功的 agent 版是 `[video editing + audio reuse]`（在**原片**上改）。
两次实测：v5（无五官）对参考图 SFace 0.026 ／ `b2160e92`（有五官）0.189，
都远低于同人阈值 0.363，原片那张脸 0.789 / 0.656 —— **脸没换成**。

| 位置 | 原来 | 改成 | 官方那一行 |
|---|---|---|---|
| `h3_ir.py` `instruction()` 的 keep 句 | 动作、镜头、节奏、场景、背景、光线和道具都**参考**视频1，保持原样不变 | **直接在这条原片上修改**，除被替换的对象以外**不重新生成**，动作、镜头、节奏、场景、背景、光线和道具保持原样 | `ref-en:136` `video editing`：An existing source video is **directly modified** |
| 音频句 · `original` 且独立送音频 | 口型和说话节奏**跟着**参考音频1 | 音频1是视频1的**同步音轨**，成片**直接复用**这条原声，口型跟着它 | `ref-en:118`：`<Audio 2>` is the **synchronized audio track** of `<Video 1>` and **is reused** in the target video |
| 音频句 · `original` 且原声在母版视频里 | 一句都不加（`has_audio=False`） | 视频1自带的原声**直接保留复用** | `ref-en:138` `audio reuse`：The same audio signal is reused in full or in part |
| 音频句 · `tts` / `mix` | 口型和说话节奏跟着参考音频1 | **不变** —— 那是我们自己新合的配音，不是原片音轨，不能声称「复用」 | — |
| 两句合并的官方写法 | — | — | `ref-en:141`：Editing a source video while retaining its original audio may be written as `[video editing + audio reuse]` |
| `video_edit.py` 段缓存键 | `:ir2` | **`:ir3`** | 指令变 ⇒ 改写器输出变；不换键会命中 `:ir2` 那批「参考生成」的旧词 |

**接线**：`prompt_for(..., audio_mode=...)` 新增一个透传参数，`video_edit.py` 调用点传
`audio_mode=_amode`（同作用域已有，2003 行）。`tail` 句
「把视频1里画面中的人物换成图1里的人物」**没动**（`test_whole_wiring.py:256` 断言它）。

**验过（全部零费用）**：
- `instruction()` 三模式干跑文本，见 `D:/tmp/h3_ir_probe.txt`（original+独立音频 / original+母版带声 / tts）。
- `scripts/test_whole_wiring.py --model h3` = **115/115 通过**。
- `scripts/check_all.py --model h3 --fast` = **通过 55 ／ 跳过 5 ／ 红 0**（119.0s）；`复刻·逐段指令·H3` **57/57**。
- 引用审计 = **347 处 ／ 去重 112 条 ／ 越界 0**。
- 型号锁：为跑 H3 判据临时切到 `h3`，跑完**已切回 `volc25`**。

**没验（归主人）**：真出片。改完要**重启后端**才进内存，出片由主人点。

### 2.2 · 出片实测（2026-11-02 03:46，主人点的 `39d20785`）—— **措辞不是根因**

改写器这次**完全按官方口径出词**，逐字核对（`data/clone/44c007ff…/ir/seg_001_eb616d4cd565.txt`）：

```
<Video 1> is the source video for video editing, providing …
<Audio 1> is directly used as the target video's complete final audio track …
summary: [video editing + audio reuse] The target video is an edited version of <Video 1>. …
<Subject 1>: fully_preserved - the target preserves her oval face contour …
<Video 1> (source-video editing): partially_preserved - … but the original performer's
  identity and clothing are replaced by <Subject 1>.
```

任务类型已经和 11-01 换脸成功的 `1414210e` **一字不差**（`[video editing + audio reuse]`）。
**成片还是没换脸**：SFace 对参考图 p90 **0.069** / best 0.095（阈值 0.363），
按 5 秒分桶 0–5s 0.066 ／ 5–10s 0.069 ／ 10–15s 0.075 —— **整段都没换，不是中途漂移**。

**同素材全部 7 次 H3 出片的 SFace 实测**（`949c0b2f`，同一张 `subject.jpg`，同 `mini-H3-Lite` 480P）：

| 时间 | 渲染 | 时长 | 提示词来源 | p90 | 判定 |
|---|---|---|---|---|---|
| 11-01 09:56 | `37f9226a` | 4.633s | agent | 0.021 | ❌ |
| 11-01 15:57 | `a39031de` | 4.633s | agent | 0.113 | ❌ |
| 11-01 18:44 | `1414210e` | 4.633s | agent | **0.592** | ✅ |
| 11-01 23:41 | `b9d83311` | 4.633s | agent | 0.056 | ❌ |
| 11-02 01:07 | `a0ae41f8` | 4.633s | IR（无五官） | -0.013 | ❌ |
| 11-02 03:25 | `b2160e92` | 4.633s | IR（有五官） | 0.189 | ❌ |
| 11-02 03:41 | `39d20785` | 15.0s | IR（本版 `:ir3`） | 0.069 | ❌ |

**结论（证据链）**：
1. **不是提示词**：7 次里只有 1 次成功，成功的和失败的用过同一套 agent 六段式、同样的
   `[video editing + audio reuse]` 标签。措辞是必要条件，**不是充分条件**。
2. **不是时长**：4.633s 也失败过 5 次；15s 这次整段均匀失败，没有漂移。
3. **不是分辨率**：模型原始输出两次实测都是 **480×864**（`chunk_001.mp4`），不是变量。
4. 7 次里唯一的差别没有一个是稳定的 → **H3-Lite 480P 换脸本身是低成功率**（1/7）。
5. 🩸 还没动过的变量：**清晰度档位**。官方 `api-models:41` 写 Lite **默认 768P**
   （480P / 768P 两档），我们因为前端默认 `resolution: auto`「跟原片」，
   原片 576×1024 → 自动落到**最低的 480P**。官方模型卡 `:92` 也写明 2K 再生成
   「more accurate details and greater visual fidelity」—— 目前整条 2K 环节没接。

**下一步（要主人点，我一次都不碰出片）**：同一素材、同一提示词，把清晰度显式选
**768P**（或换 `MiniMax-H3` 主档 / `H3-Max`）再出一次。只变这一个变量。

### 2.3 · 主人指出的关键词：**画面描述里把「要被换掉的那个人」写出来了**

主人原话：「是不是其他版本的提示词把需要换掉的人也详细的描述出来了呀！」
按这个方向逐版扫 `detailed_description`（**画面描述段**，不是 summary / retention），
7 个出过的版本：

| 版本 | p90 | 正文提原片那个人 | 长什么样 |
|---|---|---|---|
| `1414210e` | **0.592 ✅** | **0 次** | 正文只写 `<Subject 1>` 在做什么 |
| `b2160e92` | 0.189 | 0 次 | — |
| `a39031de` | 0.113 | 0 次 | — |
| `b9d83311` | 0.056 | 0 次 | — |
| `a0ae41f8` | -0.013 | 0 次 | — |
| `37f9226a` | **0.021（最差）** | **1 次，还写了她的衣服** | `the cream cardigan…, the white inner top, and the light-blue jeans worn by the woman in <Video 1> **no longer appear anywhere in the frame**` |
| `39d20785` | **0.069（次差）** | **1 次** | `The original woman from the video is **completely replaced by** <Subject 1>` |

**命中规律**：正文提了原片那个人的两版，正好是**最差的两档**；成功那版**一次没提**。
但另外 4 版也没提、仍然失败 —— 所以它是**致病因素之一，不是唯一原因**。

**改写器的习惯（5/5）**：`949c0b2f` 的 5 组 IR 输出**全部**在正文里写了原片那个人
（`original woman` ×3 / ×5 / ×2、`original performer` ×1）。源头是我们喂的那句
**「把视频1里画面中的人物换成图1里的人物」** —— 句子本身把"要被换掉的人"当成了对象，
改写器照着写进画面描述，画面描述写到谁，模型就画谁。

**官方依据（主人问「有没有官方正解」）**：
- `ref-en:88`：If a person … from a reference video is **reused as visible content**, it still
  belongs under `<Subject N>`. **`<Video N>` identifies the asset or structural source and
  does not replace subject labels.**
  → 被替换掉的那个人**不是可见内容**，就不该出现在画面描述里。
- `ref-en:167`：`attribute_transfer` = **Referenced characteristics are transferred to a
  different identifiable target subject** —— 这才是"换人"的官方标记（成功版用的就是它；
  IR 版用的是 `fully_preserved`，语义只是"保留"）。
- 官方**没有**单独一节讲"换人"（video editing 只给了定义 `ref-en:136`），上面两条是从
  Subject/retention 规则推出来的，不是官方换人教程。

**改法（本轮，只改这一处）**：
`h3_ir.py` 的换人句 —— `把视频1里画面中的人物换成图1里的人物。`
→ **`成片里出镜的人物只有图1里的人。`**（正面声明"出镜的是谁"，不描述"原来是谁"）
段缓存键 `:ir3` → **`:ir4`**。

**同步改判据**：`test_whole_wiring.py:256` 原来断言旧句子，改成两条 ——
① 说清"出镜的是图1里的人"；② **不再出现「视频1里画面中的人物」**。

**验过（零费用）**：`test_whole_wiring --model h3` **116/116**；
`check_all --model h3 --fast` **通过 55 ／ 跳过 5 ／ 红 0**（120.1s）。
**没验**：改写器拿到新句子后正文还提不提原片那个人 —— 要调一次 IR 才知道，
等主人下次出片时自然落盘，我逐字核。

### 2.4 · 实测 `:ir5`（65 字）——**脸换上了，场景被定妆照带走**；把前端勾选接进改写器

主人点的 `c91c57da / 819f599c`（4.633s，Lite 480P）：

| 指标 | 结果 |
|---|---|
| SFace 对参考图 | **p90 0.575 / best 0.587 → `swapped`**（阈值 0.363） |
| 8 次出片里的排名 | 第 2 次成功，**且是指令最短的一次** |
| 场景 | ❌ 从原片的**室内房间**整段搬到定妆照的**古风亭子 + 荷花池 + 灯笼夜景** |

改写器输出这次判成 `[reference generation + audio reuse]`（不是 `video editing`），
**脸照样换上了** —— 所以昨天「任务类型必须是 video editing」那条判断**撤回**。

**根因（同素材干净对照，只差一句）**：

| 指令 | 有没有写「视频1 提供场景」 | 成片场景 | SFace |
|---|---|---|---|
| 172 字（`:ir3`） | ✅ 动作、镜头、节奏、**场景、背景、光线**和道具都参考视频1 | 室内 ✅ | 0.069 ❌ |
| 65 字（`:ir5`） | ❌ 只写「动作、镜头和口型」 | 亭子 ❌ | 0.575 ✅ |

改写器手上唯一带背景的素材就是定妆照 ⇒ 它把定妆照的亭子莲花池写进
`detailed_description`（原文：`against the softly blurred background of an outdoor
traditional pavilion at dusk, where warm glowing lanterns reflect gently over a quiet lotus pond`）。

**更深一层**：前端勾选（`change = {person: true, scene: false, ...}`）**从来没进过 IR 的输入**。
代码路径（不是推断）：`clone.py:1483` 前端 edit → spec；`video_edit.py:1046-1082` `_prepare`
就在读 `spec["change"]["person"]`；`video_edit.py:1205` `"spec": spec` 原样放进 plan；
但 `video_edit.py:2298` 调 `prompt_for` 时**只传素材，没传 spec/change**。

**改法（本轮）**：
- `h3_ir.instruction(..., change=...)`：**「视频1 提供什么」由前端勾选决定** ——
  `change.scene` 为假 ⇒ `视频1提供了动作、镜头、口型、场景、背景`；为真 ⇒ 只给动作/镜头/口型。
- `prompt_for(..., change=...)` 透传；`video_edit.py` 调用点传
  `change=(plan.get("spec") or {}).get("change")`。
- 段缓存键 `:ir5` → **`:ir6`**。

**四种勾选干跑**（`D:/tmp/h3_ir_probe.txt`）：
```
只换人        71 字：…视频1提供了动作、镜头、口型、场景、背景；音频1提供了声音参考。
换人+换场景    65 字：…视频1提供了动作、镜头、口型；音频1提供了声音参考。
只换人·无音频  60 字：…视频1提供了动作、镜头、口型、场景、背景。
只换人+补充    77 字：…场景、背景；音频1提供了声音参考。画面更亮一些
```

**验过（零费用）**：`test_whole_wiring --model h3` **116/116**（新增两条：没勾换场景 ⇒
场景/背景归视频1；勾了换场景 ⇒ 不再说视频1 给场景）；`check_all --model h3 --fast`
**通过 55 ／ 跳过 5 ／ 红 0**。

**没验**：真出片（要重启后端 + 主人点）。判成功的标志：成片留在**原片的室内场景**，
同时 SFace ≥ 0.363。

---

## 3. 仍没落地的（现在死活 = 半死）

| 项 | 状态 | 卡在哪 |
|---|---|---|
| 后端加载新代码 | 🔴 未生效 | 监听 `8920` 的进程（PID 29280）**2026-10-23 19:38** 启动，早于今天全部改动。**重启由主人做** |
| 改写器路线（H5/H6/§2.1） | 🟡 **出过片，没换成** | `:ir3` 已实测（`39d20785`）：改写器输出正确到 `[video editing + audio reuse]`，成片 SFace 0.069。**措辞不是根因**，见 §2.2 |
| 错误码人话（H8） | 🟡 未生效 | 同上，等重启 |
| 音频单独送（H7） | 🟡 未生效 | 同上，等重启 |
| 整片身份检查 | 🟡 只记录不拦 | 出片后身份检查「只记录、不拦截、不重试」——这是已知缺口，不是本轮范围 |
| 长相那一路的判据覆盖 | 🟡 覆盖不到 | `p58` 在临时任务里跑，**没拷 `subject_desc.json`** → 日志里 `人物参考图外貌描述失败（不影响后续）` —— `:ir2` 的长相注入**没有判据兜底**，只能靠真出片量 SFace |
| **IR 把任务类型判成「参考生成」** | 🔴 待改 | 实测对照：本次 IR 产出 `[reference generation + audio reference]`；11-01 换脸成功的 agent 版是 `[video editing + audio reuse]`。而我们喂给 IR 的原话是「…都**参考**视频1，保持原样不变；口型**跟着**参考音频1」——reference 语义，IR 忠实照做。官方定义：`ref-en:136` video editing = "an existing source video is **directly modified**"；`ref-en:118` 音频复用 = "the synchronized audio track … **is reused**" |

---

## 4. 非 H3 范围（只登记，不逐条审）

`f226079..HEAD` 72 个文件里，**45 个与 H3 无关**，属另外三条线：

| 线 | 代表文件 | 说明 |
|---|---|---|
| 火山 2.0 下架 | `sd20_direct.py`（−302）、`sd20_official.py`（−102）、`models/volc20*.py` → `_archive/sd20/` | 主人拍板下架 |
| 火山 2.5 接入 | `sd25_skill.py`、`sd25-pe/SKILL.md`（996 行）、`clone_agent.py`、`p20/p25/p30/p31_check.py` | 与 H3 **各写各的**，一条断言都不共用 |
| 先出第 1 段 | `p57_check`(38) / `p58_check`(12)、`clone.py`、`diagnose.vue`、`result.vue` | 共享层能力，不限型号 |

> 这三条线要不要也出四列台账，由主人定 —— 本文件只保证 **H3 这一侧每条都指得到出处**。

---

## 5. 复验命令（都能零费用跑）

```bash
cd C:/tmp/video-tool/backend

# 引用是否都指得到原文（应：越界 0）
python /d/tmp/front_probe/audit_code_citations.py

# 索引表每条引用对回原文（应：308 条 / 越界 0）
python /d/tmp/front_probe/check_map_full.py

# H3 一侧全部判据（零费用，不调模型）
python scripts/_model_lock.py h3
python scripts/check_all.py --model h3 --fast
```

维护：**新增/修改 H3 规则时，先在这张表里补一行**，再动代码；四列填不全 = 不许改。

---

## 6. 2026-11-02 追加：段缓存键 + 强制重跑

**触发**：主人点了「先出第 1 段」重出，三次得到同一段（`9d98e578` / `f1dea990` / `5d67b4d9`
同键 `minimax:0304407a125a:0.00-4.13:b72109:6f926c:ir8`，产物都是 **476,680 字节**，
模型一次没调）。07:05 预调的新词 `seg_001_f7cbdd413d7e` 从未被用上。

| 改动 | 为什么改 | 依据（出处） | 拿什么验过 | 现在死活 |
|---|---|---|---|---|
| `h3_ir.prompt_sig()` + `h3_ir._fp()` | 改写器产出的词在**缓存判定之后**才生成，进不了段缓存键；以前靠人工升 `:irN` 兜底，漏升一次新词永远用不上 | 事故本身：三次渲染同键同字节（`video_edit.py:2280` 旧 `seg_hash` 只含代码编译版提示词；IR 在 `:2353` 才产出） | `D:/tmp/sig_check.py`：`prompt_sig` 与 `prompt_for` 指纹**同值** `f7cbdd413d7e`；`D:/tmp/ir_sig_dryrun.py`：按出片真实参数干跑，`ir_sig` 也等于 `f7cbdd413d7e` | ✅ 已接，零费用判据过 |
| `Caps.prompt_sig` + `models/h3.py:_prompt_sig` | 共用层要在查缓存前拿到指纹，且**不许 import 任何一家**（模型分离门） | `models/base.py` 的 `Caps` 接口约定：共用层只认"有没有这个函数" | `test_whole_wiring.py` 新增 3 条：适配器挂了 `prompt_sig`、同输入指纹稳定、改一个字就变 | ✅ 132/132 |
| 段键 `ir_mark = ":ir:<fp>"` | 让"改写器的输入变了"必然导致重新生成；停止人工升版本号 | 同上事故 | `check_all --model h3 --fast`：通过 55 / 跳过 5 / 红 0 | ✅ |
| `force` 强制重跑（四层透传 + 前端开关） | 同键永远命中 = 省钱，但**失败了抽不到第二次**；模型本身不确定 | 主人 2026-11-02：「刚才都没有换脸成功，我回来重出为什么出不了？直接命中缓存了」 | `test_whole_wiring.py` 新增 6 条：API/任务层/出片函数默认 `False`、前端只在打开时才发、`_gen_spans` 真的跳过两级缓存；`npm run build:h5` 通过 | ✅ 132/132（开关默认关，打开会扣费） |

---

## 7. 2026-11-02 追加：清理 H3 路上的死代码与拦路闸（不动任何提示词措辞）

**触发**：主人「每次都会在几个模型之间来回捞别的模型信息进来，导致问题始终无法真正修复」
→ 先按 H3 这一条路逐个查「这行给谁用、IR 用不用得上」，只清**零行为变化**与**纯拦路**两类。

| 改动 | 为什么改 | 依据（出处） | 拿什么验过 | 现在死活 |
|---|---|---|---|---|
| 删 `h3_ir._STYLE_ZH`、`h3_ir._desc()` | 全工程 0 调用（指令里写风格/五官那两句撤掉后留下的死代码） | `grep -rn _STYLE_ZH --include=*.py` 仅定义行；`_desc(` 在 `h3_ir.py` 无调用 | `py_compile` 通过；`test_whole_wiring --model h3` **123/123**；`test_edit_spec.py --model h3` **288/288** | ✅ 已删 |
| 删 `video_edit._span_looks` / `_ir_descs` / `_ir_speakers` | 同上，0 调用；是 2026-11-02 早几轮「把长相/服装/说话人塞进改写器」的残留 | `grep -rn` 只剩注释里提到；无任何 import | 同上两条判据 | ✅ 已删 |
| `models/h3.py:_pre_compile` 去掉 `raise` | 旧六段式正文必须英文，所以翻译失败会**拦住出片**；正式出片的词由官方改写器产出（中文进、六段英文出），改写器本来就认识中文 | 官方 `api_v2-h3-context-ir.md:13/46`「深度理解文本…在保持用户原始意图前提下丰富语义细节」；`ref-en:5` 只约束**输出**正文 | `py_compile`；两条判据同上 | ✅ 翻不出来只记 warning，不拦出片 |

**查了但决定不改的（证据）**

| 项 | 查证结果 | 处置 |
|---|---|---|
| `caps.shot_looks=True` → `_shot_looks` | `vision_plan.describe_shots` **只读缓存**，不调模型、不花钱（`vision_plan.py:877-905`） | 不动 |
| `caps.ensure_shot_source=True` → `_ensure_shot_source` | 缺 `shots` 且缓存不存在时**补一次付费盘点**（`video_edit.py:2478-2482`）；产出只喂旧编译器 | 一次性的钱，不拦出片；要撤得连 `test_h3_shot_source.py` 一起改，单独一轮 |
| 旧六段式编译器 `h3_compile._minimax` | 出片时结果被改写器覆盖（`video_edit.py:2360`），但仍供界面展示与 `prompt_advice` | 不动 |
| `caps.drop_absent_people` / `boundary_pic` | 直接改**发出去的参考图/边界帧**，改写器吃得到 | 不动（影响真实输入） |

---

## 8. 2026-11-02 追加：送进 IR 的文字按官方公式对齐（参考素材说明 + 核心创意 + 画面过程说明）

**触发**：主人「我们都已经做好 H3 的资料导图了，不知道怎么使用 IR 难道就不会按照它的使用说明对齐吗？」

| 改动 | 为什么改 | 依据（出处） | 拿什么验过 | 现在死活 |
|---|---|---|---|---|
| `h3_ir.instruction()` 改成官方三段式 | 旧文只有素材用途一句：视频被写成「动作、镜头、口型」= 动作参考+运镜参考，**没有「视频编辑」** → 改写器不认「在原片上改」，背景只能从定妆照取材；公式里的核心创意、画面过程说明整段缺失 | `h3-manual:242-245`「完整提示词 = 参考素材说明 + 核心创意 + 画面过程说明」；`:248` 用途表含「视频编辑（对视频某个内容进行增删改）」「有非常想保持的特征，建议明确写出来」；`:250` 核心创意四要素；`:251` 按分镜写画面过程。索引 `H3-OFFICIAL-MAP.md:580-583` | `D:/tmp/ir_text.py` 打印四种情形全文；`test_whole_wiring --model h3` **125/125**；`test_edit_spec --model h3` **288/288** | ✅ 已改 |
| 断言同步（`test_whole_wiring.py:257-270`） | 旧断言要求指令逐字等于「人物参考图1提供了人物的形象；视频1提供了动作、镜头、口型。」 | 同上一行 | 125/125 | ✅ |
| 引注缩写 `manual:` → `h3-manual:` | 模型分离门要求引注落在 MANIFEST 的缩写表里（`D:/tmp/official/h3/MANIFEST.json` 的 `abbr`） | `model_separation_check.py:564-580` | `model_separation_check.py` 6 项全绿 | ✅ |
| 回退 `test_triage.py` / `p12_check.py` 里我自己加的分诊断言 | 那两条断言测的是我 2026-11-02 自己加的「静止镜压台词→video」规则，规则已按主人要求回退，断言留着就是假红 | 主人：「把你之前对这个模型做的所有拦路虎给删除撤掉」；`triage.py` 已 git checkout 回 HEAD | `test_triage --model h3` 35/35；`p12_check --model h3` 51/51 | ✅ |

**补记（同日修完）**：`p4_check.py` C1 那条红查到底了，不是代码回归，也不是「取样口径」这么含糊 ——
是**规则漂移**：最新那条真跑（`45fff4bb / 72db24c5`）出片时，分诊里还有我当天早先加的
「静止镜压着台词 → video」，末镜被并进前一段 → 真跑 1 段（`decisions.json: spans=[[0,10.1]]`）；
该规则已按主人要求回退到 HEAD，同一 intent 现在算出 **2 段**（`[0,8.73] video` + `[8.73,10.1] still`）。
两边各自都对，只是**两套规则**。修法：C1 只在「真跑时间晚于 triage/video_edit/work/clone_pipeline
最后一次改动」时才比，规则一改自动跳过，下一次真跑后恢复比较（`p4_check.py:318-345`）。
复跑：`p4 23/23 通过（跳过 1）`；`check_all --model h3 --fast` = **通过 55 / 跳过 5 / 红 0**。

**注意**：`instruction()` 变了 → `prompt_sig` 变了 → 段缓存键全部变，下一次出片**每段都会重新生成（会扣费）**。

---

## 9. 2026-11-02 追加：把定妆照的五官写进改写器输入（`h3-manual:248`）

**触发**：新三段式出片仍不换脸（`51071b2d / dadbc9a9`，SFace 0.09）。查真实请求快照
`triage/request_001.json`：`ref_images=['subject.jpg']`、`subject_look.used=false` ——
定妆照发了，但**五官描述一个字都没进提示词**；改写器产出的 `<Subject 1>` 只有发簪和衣服。

| 改动 | 为什么改 | 依据（出处） | 拿什么验过 | 现在死活 |
|---|---|---|---|---|
| `h3_ir.instruction(..., looks=)` 把人物特征原文写进「参考素材说明」 | 官方要求写出的特征没写；改写器自己不写脸（看得到图，但输出只挑发型/服装），模型于是按原片保脸、只贴发饰 | `h3-manual:248`「如果素材中有非常想要保持的特征，建议明确写出来，这样可以让一致性更好」；对照 = 唯一成功那次（`1414210e`，SFace 0.592）正文含 `keeps the exact face from <Picture 1>: …` 整段五官 | `D:/tmp/ir_looks.py` 用真实 `subject_desc.json` 打印全文；`test_whole_wiring --model h3` **127/127**；`test_edit_spec --model h3` **288/288**；`check_all --model h3 --fast` **55 通过 / 5 跳过 / 红 0** | ✅ 已接 |
| `prompt_sig` / `prompt_for` 增加 `looks` 参数 | 指纹要覆盖这份文本，否则改特征不进缓存键 → 命中旧段（老坑） | 同 §6 的 `_fp` 机制 | 新增断言：「特征变了 → 指纹也变」 | ✅ |
| `video_edit._look_ir()` + 两处调用点传 `plan["looks"]` | 传给改写器的是**定妆照自己的描述文件**（`subject_desc.json`），不是我现编的形容词 | 同上 | 同上 | ✅ |

**注意**：指纹变了 → 段缓存键变，下一次出片每段重新生成（扣费）。

---

## 10. 2026-11-02 追加：删掉「静止镜头重绘」这一档（分诊只剩 keep / video）

**触发**：主人「本来我们就是视频重置的啊！我建议删」。起因是双人换人 `902c4d0f`
最后 1.37 秒（motion=0.28）被判 still、走了另一条链路（生图 + 图生视频），
8s/9s 服装突变。

| 改动 | 为什么改 | 依据（出处） | 拿什么验过 | 现在死活 |
|---|---|---|---|---|
| `triage.decide()` 删掉两条 still 触发：① motion < 1.2 ② 新配音 + 这一镜有台词 | 阈值 1.2 是**自造**的：出处那篇 hypit `craft/video-direction.md` 只有定性原则（"静帧能交代的用静帧，时间里的展开才用视频参考"），**没有任何数值或判定算法**；1.2 是 2026-10-21 拿三组样本拍的。实测真实素材能低到 0.28，与「真实手持素材 7–20」的标定差一个量级 → 1.37 和 0.28 分属两条链路，造型对不上 | 主人 2026-11-02 拍板；`UPSTREAM-RULES.md:119` 准入线：指不到官方/hypit 行号的规则 = 自造，应撤回。hypit 原文 `D:/tmp/hypit-src/skills/hypit/references/playbooks/craft/video-direction.md:14-20` 复核：无阈值、无算法 | `test_triage --model h3` **28/28**（重写：运动量不再影响走法）；`test_separate` **35/35**；`test_whole_wiring` **166/166**；`test_auto_render` **42/45**（3 红为 `test_span_intervals` 既有，与本次无关） | ✅ 已改，**未出片验证** |
| 删 `MOTION_VIDEO_MIN` / `SPEECH_OVERLAP` / `_speaks` / `still_shots()` / `force_video` / `_auto_decision` 的 `audio_mode`+`speech_spans` 参数 | 都是只为 still 判定存在的死件；留着就是「没有消费者的参数」 | 同上 | 全判据通过 | ✅ |
| `_auto_decision` 删掉「配方没有 motion 就现场补算」 | 运动量已不参与任何决策，补算纯属白扫一遍帧 | 同上 | `test_auto_render` 相应断言已改成「不调静帧生成器」 | ✅ |
| `render` / `preview_render` / `work.py` 删掉 still 重绘块与 `still_shots` 计数 | 分支不存在了，留着就是不可达代码 | 同上 | 同上 | ✅ |
| 前端 `diagnose.vue`：删镜头条上的「动作/静态」标、`motion_min` 依赖；文案改成「没勾的保留原片，勾了的整段重制」 | 后端不再发 `motion_min`，同一套数字不在前端抄第二份 | 同上 | 前端改动，未构建验证 | ✅ |
| `api/clone.py` 删 `data["motion_min"]` | 没有消费者 | 同上 | 同上 | ✅ |

**没动**：`regen_mode="shots"`（按比例挑镜头、统一走静帧重绘）是**另一条独立入口**，
`generate.regen_shots` / `edit_spec.still_prompt` / `require_identifiable_still`
仍为它保留。这次只删了 auto 分诊里的静帧档。

**风险记录**：原来「新配音 + 口播 → still」是为了防「模型照搬原片口型」。删掉后
口播镜头也走视频重制，这个风险改由 H21 的 `_span_script`（把真实台词和相对秒数
喂进改写器）承担 —— **两套机制留一套，但这一套还没出片验证过**。

---

## 11. 2026-11-02 追加：整条「静帧重绘」链路删除（含 `regen_mode="shots"`）

**触发**：主人怀疑「静帧重绘 = 先生成静帧再喂视频模型，模型把它当人物参考 → 混乱」，
要求查清它还有什么用，没用就删。查完：**唯一活着的入口是前端的「只换开头」**，
而这个功能用「勾开头几镜 + 视频重制」就能做。

**查证的事实**：
- `generate.regen_shots` 的链路 = 抽原片帧 → `ark.generate_image`（图生图，参考图在这一步发）
  → `ark.generate_video(first_frame=重绘图)`（**只有这一张图**）。
- 首帧 / 参考图三家互斥（`volc-create.md:269`）⇒ 第二步**再也带不了人物参考图**，
  身份只在第一步锁一次。
- `regen_ratio` 前端恒传 0（界面不提供）；`regen_mode="shots"` 只由「只换开头」触发；
  `ark.generate_image` 除它之外零消费者。

| 改动 | 为什么改 | 依据（出处） | 拿什么验过 | 现在死活 |
|---|---|---|---|---|
| 删 `generate.regen_shots` 整个函数（`generate.py` 只剩 `seek_time`） | 链路本身删了 | 主人 2026-11-02「静帧删了」；功能可用 auto + picks 等价实现 | `test_gen_cache` **8/8**（删掉静帧缓存测试） | ✅ |
| 删 `edit_spec.still_prompt` / `motion_prompt` / `shot_prompt` / `pic_cn` | 零生产消费者 | 同上 | `test_edit_spec` **274/274**（删 14 条静帧断言） | ✅ |
| 删 `video_edit.require_identifiable_still` | 同上 | 同上 | `identifiability_check` 三道闸全绿 | ✅ |
| 删 `clone_pipeline` 的 `shots` 分支（render + preview）与静帧提示词构建块 | 同上 | 同上 | `test_auto_render` 41/44（3 红为 `test_span_intervals` 既有） | ✅ |
| `regen_mode="shots"` 在入口归一成 `auto`（老客户端兼容） | 老客户端/历史任务仍会传 shots | 同上 | `test_auto_render`「老客户端传 shots：归一化成自动分诊」 | ✅ |
| `render` / `preview_render` / `clone_jobs` / `RenderIn` 删 `regen_ratio` | 界面恒传 0，没有消费者 | 同上 | 全判据 | ✅ |
| 删 `lock_tail`（B6 尾帧锁定）：`RenderIn` / `normalize` / 缓存键 / 前端开关 | 它只作用于静帧重绘（每镜多一张尾帧图），链路删了就无处可用 | 同上 | `p14_check` **5/5**（S4/S5/S7 整节删） | ✅ |
| 前端「只换开头」不再转 `shots`，改为 `auto` + 勾开头几镜 | 走视频重制：参考图能发、身份锁得住、没有两条链路的接缝 | 同上 | `npm run build:h5` 成功 | ✅ |

**保留**：
- `ark.generate_image`（火山图生图客户端）—— 底层能力，本次没删；目前零业务消费者。
- `generate.seek_time` —— 镜头检测还在用（`test_shot_detect.py`）。

**判据汇总**：`test_triage` 28/28 · `test_separate` 35/35 · `test_whole_wiring` 166/166 ·
`test_edit_spec` 274/274 · `test_video_edit_logic` 84/84 · `test_gen_cache` 8/8 ·
`p10` 35/35 · `p12` 48/48 · `p14` 5/5 · `test_speech_est` 49/49 ·
`model_separation` 6 绿 · `check_all --fast` **54 通过 / 5 跳过 / 红 1**（p16 既有）。

---

## 12. 2026-11-02 追加：多人换人改用官方「合并来源」句式（`ref-en:57`）

**触发**：双人换人 `902c4d0f` 连出两版，两人都没换上（SFace `person` 0.347 / `person2` 0.182，
阈值 0.363）。逐项对比两次**真实请求**（`triage/request_001.json`）：通道/型号/分辨率/两张参考图
sha1 **完全一致**，差异只有生成时长与提示词。回查官方 H3 自己的资料
（`backend/data/official/h3/`，未引用任何其他厂商）：

- `ref-en:143`「**If a reference video provides only camera movement, cuts, or rhythm,
  it normally belongs to `reference generation`.** Use `video editing` or `video continuation`
  only when that video is directly edited or continued.」
  ⇒ 我们的任务：人物形象 100% 来自参考图，原视频只提供动作/运镜/切点/场景/原声
  ⇒ **本质是 `reference generation`**，但改写器一直判成 `[video editing + audio reuse]`。
- `ref-en:136` `video editing` = 「an existing source video is **directly modified**」
  —— 判成这个类型后，改写器把 `<Subject N>` 写成"原片那个人身上的新脸"，
  模型执行的是「修改原片」而不是「用两张图造两个人」。
- `ref-en:57` 官方给「同一主体来自多个素材」的定义句式：
  ```text
  <Subject 1> is the woman whose appearance comes from <Picture 1>
  and whose walking motion comes from <Video 1>.
  ```
  ⇒ **一个人的外貌来自图、动作来自视频**，不是「用 A 替换 B」。
- `ref-en §7` 完整示例 = 4 个主体（环境 / 狗 / 女主 / 男主）共存，任务类型
  `[reference generation + audio reference]`，全部 `fully_preserved`，**每个人 2–3 个特征**。

| 改动 | 为什么改 | 依据（出处） | 拿什么验过 | 现在死活 |
|---|---|---|---|---|
| `h3_ir.instruction()` 把「视频1中的出镜人物**替换为**人物参考图中的人物」改成「外貌来自图N、动作/站位/表演来自视频1」的合并来源表述 | 「替换」把改写器推向 `video editing`，主体定义变成"原片那个人身上的新脸"，模型去改原片 | `ref-en:143` · `ref-en:136` · `ref-en:57` | `test_whole_wiring --model h3` **181/181**；`rehearse_render --cid 902c4d0f…` **15/15**；`check_all --model h3 --fast` 仅 p16 既有红 | 🟡 已改未验（**产出类型需真调一次 IR 看**：HEAD 是否仍出 `The target video is an edited version of <Video 1>.`） |
| 同一次改动里**删掉重复的来源说明**：新句原本写「图1提供了人物的形象，其动作…」，而上面逐槽位那句已经写过「人物参考图1提供了人物的形象」——同一件事两遍，且「图1」/「人物参考图1」两种叫法会被当成两张不同的图 | 打完 `instruction()` 实文才看出来；两种叫法 + 重复，正是 `1b3df54b` 那次「`<Picture 2>` 发出去却零引用」的同款风险 | `ref-en:57`（一个主体、两个来源，来源各说一次） | 同上三条判据；指令实文已肉眼核对（`D:/tmp/show_new_instr.py`） | 🟡 已改未验 |
| 人物称谓全库统一成「人物参考图N」（`pics` 由 `图N` 改为 `人物参考图N`） | 同上：`图N` 与 `人物参考图N` 混用会指代不明；边界帧那句仍是「图N」（`ref-en:62` 的编号口径），本次不动 | `ref-en:57` · `ref-en:62` | `test_whole_wiring` 双人/混排编号断言 | 🟡 已改未验 |
| `process` 里「只替换出镜人物」→「出镜人物的样子按上面的参考图」 | 同一措辞族：留着「替换」二字，改写器照样读成"改原片" | `ref-en:143` | 同上 | 🟡 已改未验 |

**与 §9 的关系**：§9 把定妆照五官写进输入是依据 `h3-manual:248`，本次**不动**它。
**与 H16 / H20 的关系**：H16 用「锁定动作和运镜」失败（产出 `fully_preserved` → 脸没换）；
H20 改回「替换为」。本次既不是「锁定」也不是单纯「替换」，而是官方 `ref-en:57` 的**合并来源**句式。

### §12 补（2026-11-02 23:10）：句式恢复 + 完整素材实测

**改回**：§12 那三处（`pics` 用「人物参考图N」、有方位分支改「人物参考图N中{方位}那位的动作、站位与表演来自视频1」、`process` 结尾改「出镜人物的样子按上面的参考图」），并去掉前置的「参考视频1进行动作模仿」（与逐张来源句重复）。改后用同一组参数生成文本，与 18:39 落盘的 `seg_001_d4273fe9b7a5.in.txt` **逐字一致**（`D:/tmp/cmp_instr_1839.py` 输出「一致」）。

| 实测 | 输入 | 产出 |
|---|---|---|
| 第 1 次 | 上述文本 + `source.mp4`（10.1s）+ 音轨 + `duration=10` | `[Shot 2]` ✅ · `At 00:08.730` ✅ · **`<Subject 1/2>` = `fully_preserved`** ❌ · 4749 字 |
| 第 2 次 | **完全相同** | `[Shot 2]` ✅ · `At 00:08.730` ✅ · **`<Subject 1/2>` = `attribute_transfer`** ✅ · 3023 字 |

**结论**：
- **镜头覆盖已稳**：两次都写出 `[Shot 2] At 00:08.730`，说明切点句 + 复现的句式有效。
- **retention 定性不稳**：同一输入、同一素材，服务端两次判出 `fully_preserved` / `attribute_transfer`。⇒ 改写器存在服务端采样随机性，**光调输入句式消不掉**。
- 下游是否换脸取决于这个定性（18:37 那次 `fully_preserved` → SFace 未过）。⇒ 需要「产出验收 + 不过关重调」，而不是继续改句式。

**落盘**：`D:/tmp/ir_ab_out/H1_full.in.txt`（输入）· `H1_run1.txt`（第 1 次）· `H1_full.txt`（第 2 次）

### §13（2026-11-03 00:20）：八轮输入形态实测 —— 定性唯一锁得住的是「把人换掉」

**前提更正（主人 2026-11-02 定）**：生产里**从未真正换脸成功**。`a59b89b0`（15:02，SFace 过阈值）不再当"成功基准"。以下全部只依据 IR 输出层的 `attribute_transfer` / `fully_preserved`，不含真机结论。

同素材 `902c4d0f`（`source.mp4` 10.1s + 完整原声 + 两张图，`duration=10`），每形态跑 2–4 次：

| 输入形态 | 字数 | 跑次 | `attribute_transfer` | `[Shot N]` | BGM 老实 |
|---|---|---|---|---|---|
| **「把人换掉，一点不留」** | 98 | 2 | **2/2** | 1 | 2/2 |
| 「换掉」+ 镜头事实 | 131 | 2 | 1/2 | **2（`At 00:08.600`）** | 0/2 |
| 纯意图「换成」 | 33 | 4 | 2/4 | 1 | 3/4 |
| 「角色」换词 | 33 | 3 | **0/3** | 1 | 1/3 |
| 清单式（§12 合并来源句式） | 609 | 2 | 1/2 | 2 | 2/2 |
| 成功旧形态（`60c135c2e2a5` 同款） | 477 | 2 | 1/2（定义都不写 replaces） | 1 | 2/2 |

**结论**：
1. 「替换为」族 → 往 `fully_preserved` 滑；「整个换掉、一点不留」→ `attribute_transfer`。这是目前唯一 2/2 的措辞。
2. 一加镜头事实（几刀 + 切点），定性掉到 1/2 且开始编 BGM —— **信息量与定性成反比**。
3. 换词（女的→角色）无效，反而 0/3。
4. 输入越长越细，`replaces` 越容易被挤出 `Subject` 定义、挪进 `retention`。
5. **没有任何一版同时稳定拿到「2 镜 + 两条 attribute_transfer + 诚实 BGM」**。最接近的是 `T2_swap_shots_a.txt`（2 镜 + 2 条 attribute_transfer，只差编了 BGM）。

**落盘**：`D:/tmp/ir_ab_out/T1_swap_*.txt`（98 字）· `T2_swap_shots_*.txt`（131 字）· `P0_pure_*`（33 字）· `Q1_char_*`（角色）· `S1_success_*`（477 字）· `H1_*`（609 字）
**脚本**：`D:/tmp/swap_out.py` · `swap_out_shots.py` · `swap_out_shots_b.py` · `test_char.py` · `repro_g1.py` · `pure_full.py` · `back_to_success.py` · `verify_instr_full.py`

**⚠️ 代码尚未改为「换掉」说法**：`h3_ir.instruction()` 目前产出的是 609 字清单式；`test_whole_wiring.py` 的 11 条断言已按 §12 措辞改过但**未运行**（主人叫停）。

### §14（2026-11-03 08:30）：出片提示词**不再经 H3-Context-IR**，按手册第 3 章句式直接写

**为什么改**：主人拍板「再调 IR 已经没有意义了，因为 2.1 已经把视频看过一遍」。

先核过证据链（同一任务 `902c4d0f`，全部留档）：

| 环节 | 事实 |
|---|---|
| 实发提示词 | `render/84cc1be4…/triage/request_001.json` 的 `prompt` 与 `ir/seg_001_d4273fe9b7a5.txt` **逐字相同**（2619 字） |
| 参考图 | `ref_sha1` 与磁盘文件 sha1 一致（`5b79fd35…` / `ee4db786…`） |
| 参考视频 | `piece_001.mp4` 1024×576 / 30fps / 10.10s，原画质 |
| 成片 | 三次渲染 × 三个时间点，SFace：**0/26 张脸对上参考图**（最高 0.279，阈值 0.363），**25/26 对上原片原人** |

⇒ 不是「没传对」，是**传得太全**：改写器把一句「把这两个人换掉」扩写成整片复述
（台词、分镜、音效全写一遍），模型于是照着重拍，把原片原人也一起照抄。
官方手册第 3 章（`:211` `:213` `:233` `:234`）所有编辑示例都**只写改什么**，没有一句重述原片。

**改了什么**（`app/services/h3_ir.py`，单文件）：

- 新增 `final_prompt()`：按 `h3-manual:244` 三段式（参考素材说明 / 核心创意 / 画面过程说明）填槽，
  句子结构取 `:213`「视频1中…换成 图1中的…」，素材编号与用途取 `:248`（`@图片1` / 人物参考 / 视频编辑 / 音频复用），
  结尾按 `:251` 写 `非叙事性音乐：N/A`。
- `prompt_for()` 改为**直接返回** `final_prompt()`，不再调 `minimax.context_ir`，也不再读写 `ir/` 缓存。
- `prompt_sig()` 改算 `final_prompt()` 的指纹 —— 段缓存键必须跟真正发出去的字走。
- `instruction()` 保留原样（只给预览/对照用，出片路径不再调用）。

**刻意不写进提示词的**（都是这一版的选择，不是官方要求）：
1. 外观描述（发型/衣着/体型）—— 官方换人示例零个外观词；`looks` 里带裙子描述时，
   15:07 / 17:49 两次实测是**裙子换成了参考图那件、脸仍是原片女演员**，等于在引导模型换衣服。
2. 切点清单、台词文本 —— 参考视频和 `@音频1` 本身就在，只写「都按视频1原样」。

**同一任务的最终文本**（真实数据生成，244 字；旧版实发 2619 字）：

```
@视频1 是视频编辑的原片（在这一段原片上做改动）。@图片1 是人物参考（锁脸和形象）。@图片2 是人物参考（锁脸和形象）。@音频1 是音频复用（原片原声直接作为成片的音轨）。

把视频1中左边那位换成@图片1中的人物，把视频1中右边那位换成@图片2中的人物，其余出镜人物保持原样。

人物、动作、台词、站位、机位、分镜、场景、光线、口型都按视频1原样，只有被换掉的人长相变成@图片1、@图片2里的人，换上来的人的光影和质感与画面环境融合。

非叙事性音乐：N/A。不要额外添加背景音乐。
```

**每句的出处**（主人 2026-11-03 要求：第 2、3 章要能完全覆盖，不留自造句）：

| 提示词里的句子 | 手册出处 |
|---|---|
| `@视频1 是视频编辑的原片` | `:248` 用途词「视频编辑（对视频某个内容进行增删改）」 |
| `@图片N 是人物参考（锁脸和形象）` | `:248`「人物参考（锁定脸/形象）」 |
| `@音频1 是音频复用` | `:248`「音频复用（生成视频的音频直接复用参考音频素材）」 |
| `把视频1中左边那位换成@图片1中的人物` | `:213`「视频1中最后面的小孩换成 图1中的金毛狗」（方位来自 2.1 盘点） |
| `其余出镜人物保持原样` | `:206`「保持未编辑内容相对稳定」 |
| `动作…都按视频1原样` | `:189`「动作、表情与表演节奏严格参考输入视频1」 |
| `机位…按视频1原样` | `:192`「保持原有的固定机位不变」 |
| `分镜…按视频1原样` | `:181`「严格参考示例视频的镜头节奏、转场风格」 |
| `换上来的人的光影和质感与画面环境融合` | `:192`「确保…的毛发质感和光影与环境融合」 |
| `非叙事性音乐：N/A` | `:251` 原句 |

`补充要求：` 是我们自己的（用户手填的额外说明），只在用户填了才出现，不是官方句式。

**拿什么验过**：`D:/tmp/ir_abc/sface_cmp.py`（改前的 0/26 基线）· `D:/tmp/ir_abc/check_req.py`
（实发词与缓存逐字比对）· `D:/tmp/ir_abc/show_final_prompt.py`（新文本生成）。
三个文件 `py_compile` 通过。

**现在死活**：🔴 **未出片验证**。要主人重启后端后自己点一次出片，
判据只有一条 —— SFace 对参考图 ≥0.363 **且** 对原片 <0.363。
⚠️ `scripts/test_whole_wiring.py:226` 的 11 条断言仍按 `instruction()` 的旧措辞写，
测的是已不在出片路径上的函数；要么改，要么删，别拿它当基线。

**§14 附（2026-11-03 08:50）· 预览文案对齐**：出片路径改完后，界面预览还写着
「出片时由官方改写器生成（H3-Context-IR）」，已变成假话。改了 4 处纯文案（逻辑一行没动）：
`frontend/app/src/pages/clone/diagnose.vue`（段标签 + `peek-tip` + 一句注释）、
`backend/app/services/clone_pipeline.py`（`warnings` + `agent_error` + `prompt_source` 注释）。
⚠️ `prompt_source` 的**值**仍是 `"ir"`（前端按它隐藏复制按钮），只改说明，**别把这个值改名**。

**§14 附2（2026-11-03 09:10）· `final_prompt` 补齐五类改动（主人指出：界面有 5 类选项，之前只写了人物）**

原来只写「换成@图片N中的人物」一句；场景/服装/产品/风格只给了「@图片N 是XX参考」——
等于只告诉模型这张图干嘛用，**没说拿它改什么**。勾「场景 换背景」出片会原样不动。

补的五句，每句指手册原句：

| 界面选项 | 槽位 | 句子 | 出处 |
|---|---|---|---|
| 人物 换脸/换人 | `person*` | 把视频1中{方位}那位换成@图片N中的人物 | `:213` |
| 产品 换品/换道具 | `product` | 把视频1中的物品换成@图片N中的物体 | `:211`「把视频中的猫换成狗」 |
| 场景 换背景/换地点 | `scene` | 把视频1的背景换成@图片N中的场景 | `:221`「视频1窗外的场景改成图1」 |
| 服装造型 | `wardrobe*` | 把视频1中人物的服装换成@图片N中的服装 | `:213` 后半句「…外套改成图2中的牛仔外套」 |
| 风格 / 风格参考图 | `style_ref` | 画面整体的风格和色调参考@图片N | `:248`「风格参考（根据图片的风格，生成类似的风格内容）」 |

同时改了两处逻辑：

1. **「场景」不再无条件写进"按原片"那句** —— 换了背景又说背景按原片，模型会二选一（实测丢改动）。
2. **「其余出镜人物保持原样」从改动句挪到"按原片"句** —— 否则和后面追加的换装句连读
   会变成「其余出镜人物保持原样，把服装换成…」，读起来像两句打架。
3. `非叙事性音乐：N/A` 改成**无条件**写 —— 成片音轨由我们自己拼（原声复用/配音轨/上传 BGM），
   任何时候都不该让模型编音乐。

**验过**：`D:/tmp/ir_abc/show_final_prompt.py` 跑六种组合（只换人 / 只换场景 / 换人+换装 /
只换产品 / 换人+风格 / 全开），文本通顺、编号对位、无矛盾句；`py_compile` 通过。
**未出片验证**。

### §15（2026-11-03 09:40）：删掉 IR 时代残留 —— `instruction()` 与它那 40 条断言

**为什么删**：主人「如果不需要再调 IR 就删了吧，我怕会影响判断」。

`instruction()` 238 行写的是和现在**完全相反**的规矩（「替换为」族、合并来源句式、
609 字清单式、把切点和台词全塞进去）。生产路径早已不调它，但 `test_whole_wiring.py`
里有 40 条断言在测它，而且是绿的 —— 后来的人会以为那就是现行写法。

**删了什么**：

| 文件 | 删除内容 |
|---|---|
| `app/services/h3_ir.py` | `instruction()` 整段（第 53–290 行，238 行 / 10,504 字节） |
| `scripts/test_whole_wiring.py` | 40 条依赖它的断言（含「换人写成「替换为」，不写成「换成」」等**方向相反**的） |

**没删什么（有意保留）**：
- `minimax.context_ir()` —— 官方接口客户端，`rehearse_render.py` 拿它当替身，出片不调。
- `prompt_sig` / `prompt_for` / `final_prompt` —— 现行路径。
- `data/clone/*/ir/` 的历史产出 —— 是复盘的证据，不删。

**回滚**：删前完整副本
`D:/tmp/ir_removed/h3_ir_before_delete.py` · `h3_ir_HEAD.py`（HEAD 版）·
`test_whole_wiring_before.py`。恢复一条命令即可。

**验过**：`D:/venvs/video-tool/Scripts/python.exe scripts/test_whole_wiring.py --model h3`
→ **128/128 通过**（删前 168 条，删掉 40 条）。

**§14 附3（2026-11-03 10:05）· 预览内容也改用出片那条构造器**

主人截图问「怎么还是显示这些的」——预览里还是 2619 字英文六段式 + 旧标签。三个原因叠加：
① 后端没重启（提示语是进程里的旧串）；② 前端没重新打包（改的是 `.vue` 源码）；
③ **内容本身没换** —— 上次只改了文案，`work._video_prompts` 仍走 `_span_prompt`
（H3 六段式编译器），那版根本不会发出去。

改法：`work._video_prompts` 里 `ad.caps.prompt_for is not None` 时改调新增的
`work._h3_preview()` → `h3_ir.final_prompt()`，规则照抄 `video_edit._gen_spans`
（摘缺席人物、ppl 对齐、frame_n）只少"取尾帧"。预览文案同步改成
「出片时按这一段真实切片重算（这版是预估，可能差边界帧一句）」。

验过：`work._h3_preview` 用 902c4d0f 的真实参数跑出 **253 字中文**（与出片同形）；
`npm run build:h5` 完成，`dist/build/h5/assets/*.js` 里已无「官方改写器」；
`work.py` / `h3_ir.py` / `clone_pipeline.py` 语法通过。
**仍未重启后端**（规矩：重启一律主人做）。

---

## 15. 2026-11-03 回退：停止「手册句式手拼」，恢复官方改写器，并补验收 + 重抽

**为什么退**

当天真实出片 `d74bf43c`（同任务 `902c4d0f`，Lite/480P）实测：
`out.mp4` 抽 8 个时间点共 24 张脸，**0 张对上参考图**（女参考最高 0.298、
男参考 0.160，阈值 0.363），23 张仍是原片原人；逐帧像素差 16–23/255
＝模型把原片重画了一遍。

主人随后给出官方《MiniMax H3 - 视频扩写 Prompt 写作全能指南》
（飞书 `Vztzwstuqi3MQKkxs8QcGmxinxe`，revision 252，26,478 字，本地存
`D:/tmp/h3_prompt_guide.md`）：**全能参考必须是六段式英文**，引用标签是
`<Subject N>` / `<Picture N>` / `<Video N>` / `<Audio N>`。当天发出去的是
**253 字中文 + `@图片1`** —— 那是「用户手写入口」体裁的语法，不是 API 体裁。
`docs/H3-OFFICIAL-MAP.md:570-572` 早就写过「两种体裁，规则不能互相搬」，
这一版违反了它。

**改了什么**

| 文件 | 动作 |
|---|---|
| `models/h3.py` · `video_edit.py` · `work.py` · `clone_pipeline.py` · `diagnose.vue` | 回退到 HEAD（当天只改了注释/预览文案/预览构造器） |
| `scripts/test_whole_wiring.py` | 回退到 HEAD（当天删掉的 40 条断言随之恢复） |
| `h3_ir.py` | 回退到 HEAD（`instruction()` + `minimax.context_ir` 回到出片路径），**再在 `prompt_for` 上加验收 + 重抽** |

**新增判据（`h3_ir._ir_defects`）** —— ⚠️ 当天下午已按主人指示**砍到只剩前两条**
（后三条是"质量"判断，见 §16）

1. 六段齐全
2. `[Shot N]` 的**不同编号数** = 切点数 + 1（不能数出现次数，`retention_analysis` 会重复计）
3. ~~`non_diegetic_music` 必须是 `N/A`~~（**已撤**，§16）
4. ~~换 N 个人就要 N 条 `attribute_transfer`~~（**已撤**，§16）
5. ~~换人时正文必须出现 replace 关系~~（**已撤**，§16）

缓存规则：**通过才写**；不通过重抽（`_IR_MAX_TRY = 3`，每次约 ¥0.11）；
全不过则返回最后一次并记 WARNING、**不写缓存**。旧缓存也要先过验收才认。

**鉴别力实测（拿 `902c4d0f/ir/` 三份历史产出，n_replace=2 / n_shots=2）**

| 文件 | 字数 | 结果 |
|---|---|---|
| `seg_001_60c135c2e2a5.txt` | 2743 | 不合格：`[Shot N] 1≠2` |
| `seg_001_8a97d823be5c.txt` | 5310 | 不合格：BGM 不是 N/A、`attribute_transfer 0≠2` |
| `seg_001_d4273fe9b7a5.txt` | 2619 | **通过** |

🩸 **漏网的就是实际跑出 0/26 的那份**（它格式全对：两条 `attribute_transfer`、
两镜、N/A、有 replace）。所以这五条只是**格式粗筛**，挡不住"格式对但模型不照做"。
不要把它当成"双人换不动已修好"。

**验过**

`D:/venvs/video-tool/Scripts/python.exe scripts/test_whole_wiring.py --model h3`
→ **166/166 通过**；前端 `npm run build:h5` 完成。

**仍未验 / 仍未解**

- 后端**没重启**（规矩：重启一律主人做）→ 新代码还没生效
- **双人换不动**：`902c4d0f` 四次（IR 三次 + 手拼一次）全部失败；
  单人换人是真成的（`db253cfc/ccf2ba27` share 0.98，抽帧肉眼可验）

---

## 16. 2026-11-03 撤尺子：只留机械检查，质量判定全部撤掉

**为什么撤（主人原话）**

> 「我现在其实也在怀疑你的尺子问题会经常导致我自己判错！因为你可能会因为一些细节导致全局一直再不断的修改」
> 「要不把尺子撤掉吧？我们重新开始调整H3模型」

这不是一次普通的重构。根因是我**自己发明判据 → 自己判 → 判错 → 按判错的结论去改代码**：

| 尺子 | 我判成了什么 | 实际情况 | 后果 |
|---|---|---|---|
| `attribute_transfer` 必须 N 条 | 「这份 IR 不合格」 | 唯一真成功的 `db253cfc/ccf2ba27`（share 0.978）里是 **0 条** | 好样本被判死，差点按它去改好样本 |
| `best_sim ≥ 0.363` = 换上了 | `06386173` = 成功（best 0.653） | 只有 **33%** 的帧命中，全片没换对 | 把 partial 当成功，方向跑偏 |
| `ok = 全员 swapped` | 整片成败一个布尔 | 主人定义「成功 = 全片都换对」 | 我拿它当验收门 |

**改了什么**

| 文件 | 动作 |
|---|---|
| `backend/app/services/h3_ir.py` | `_ir_defects()` 砍到只剩 2 条结构检查（六段齐全 / `[Shot N]` 编号数 = 切点数+1）；三条质量判据删除，docstring 写明「别再自己加回来」 |
| `backend/app/services/identity.py` | 删 `swapped / partial / not_swapped` 判定与顶层 `ok`；`SWAP_SHARE_MIN` 常量删除；改输出 `best_sim / p90 / share / note`，`note ∈ measured·no_face·no_ref` |
| `backend/app/services/clone_pipeline.py` | `identity` 返回值注释同步；两处 `{"ok": True, "skipped": …}` 去掉 `ok` |
| `backend/app/api/clone.py` | 下发字段注释同步 |
| `frontend/app/src/pages/clone/result.vue` | `idNote` 改成报数（「人物1 33% 的帧像参考图（九成帧 ≤ 0.646，最像一帧 0.653）」）；`idBad` 只在 share < 20% 时标黄 |
| `backend/scripts/p16_check.py` | S4/S6/S7 断言从「标签对不对」改成「数算得对不对」；S3 先去重（素材库里 22 张参考图只有 5 张不同，最长一张重复 13 次） |

**现在 identity 的输出（真实样本 `06386173/6c5eadc3` 端到端跑过）**

```json
{"skipped": "", "threshold": 0.363,
 "people": [{"slot": "person", "ref_faces": 1, "best_sim": 0.653,
             "p90": 0.646, "share": 0.333, "at": 5.6, "frames": 15,
             "note": "measured"}]}
```

三个数怎么读（写进代码注释了，别再挑一个当结论）：

- `share` = 命中帧占比 —— **最接近「全片都换对了」**
- `p90`  = 九成帧都不超过它 —— 防「一帧幸运」，但 10% 命中也能过
- `best_sim` = 最像的那一帧 —— 只做参考，单帧不能代表全片

**验过**

| 命令 | 结果 |
|---|---|
| `python scripts/test_whole_wiring.py --model h3` | **166/166 通过** |
| `python scripts/p16_check.py --model h3` | **32/33**（S7/S7b 真样本不在本机 → skip；**S3 红**，见下） |
| 前端 `npx uni build -p h5` | DONE |

**S3 为什么还红（是素材问题，不是尺子问题）**

`data/clone/*/subject.jpg` 共 22 张，按内容 sha1 去重后**只有 5 张不同**（一张重复 13 次），
能认出脸的 4 张里 6 对相似度中位 **0.567**、3 对 ≥ 0.363 —— 说明这些"不同素材"多数
**本来就是同一个人**。S3 想验的是「不同人能不能分开」，样本本身凑不出足够的"不同人"。
**没有改判据让它变绿**，红着留在报告里。

**仍未验 / 仍未解**

- 后端**没重启**（规矩：重启一律主人做）→ 新代码还没生效
- **双人换不动**的原因仍未查明；已知唯一真成功 = `db253cfc/ccf2ba27`（share 0.978，单人）
- 尺子撤掉后，**判「换没换对」回到人眼 + share 数**；我此后不再用代码替主人下这个结论

---

## 17. 2026-11-03 「2.1 盘点 + 前端勾选 → IR」链路上会误导改写器的 6 处（已修 4 处）

**为什么查**：主人问「传给 IR 哪些地方会导致它判断错误」。逐行读
`h3_ir.instruction()` / `video_edit.replace_spans()` / `vision_plan.py`，
再用 `D:/tmp/ir_abc/show_instruction.py` 把**当前代码真正会发出去的那句话**打印出来对照
（不调接口、不花钱）。查实 6 处，本轮改前 4 处。

### 改动清单

| # | 问题 | 改法 | 可回退 |
|---|---|---|---|
| 1 | **换商品/场景/服装/风格在指令里没有"换成它"**，只多一句素材说明，后面还跟着「地点…与视频1一致」「其余内容保持不变」→ 自相矛盾 | `instruction()` 收集 `product/scene/wardrobe/style_pics`，生成与换人句同骨架的替换句；`idea` 只保留**这次没动**的维度 | 删 `_deltas` 分支 / `_keep_dims` |
| 2 | **方位认不出就丢**：`_POS_ZH` 只映射 3 个值，九宫格 10 个值里 7 个变空串 → 整句退回「各替换一位」 | 补齐九宫格映射；`_POS_ZH` 现在覆盖 `vision_plan._POSITIONS` 全部 9 个可用值 | 删映射键 |
| 3 | **用户按长相选人、IR 按方位换人**：前端 chips 只有 `desc_zh`（`vision_plan.summary` 不含 `position`），IR 只拿 `position` | `_pairs` 同时带 `desc_zh`；方位缺失时用「原片里{穿着/长相}那位」兜底（官方 `ref-en:246` 要的就是特征 + 位置两样） | 传 `ppl` 时不带 `desc_zh` |
| 4 | **2.1 的逐镜画面描述取到了却丢弃**：H3 声明 `shot_looks=True`、`_ensure_shot_source` 还会花钱补盘点，但 `prompt_for` 参数表里没有它，编译版又被改写器产出整段覆盖 | `instruction/prompt_sig/prompt_for` 加 `shot_looks`；`video_edit` 两处传 `seg_looks` | 把 `video_edit` 那两行改回 `shot_looks=None` |

### 改前 / 改后（实跑输出，同一组参数）

**只换场景**

- 改前：`场景参考图1提供了场景；…视频1是被编辑的原片，视频编辑：在视频1上做改动。主体、地点、事件、题材与风格都与视频1一致。…其余内容保持不变。`
- 改后：`…视频编辑：在视频1上做改动：视频1中的场景替换为场景参考图1中的场景。主体、事件、题材与风格都与视频1一致。…`

**双人 + 方位 `top-left`**

- 改前：`图1、图2 各替换一位`
- 改后：`图1中的人物替换左上角那位，图2中的人物替换右边那位`

**双人 + 方位 `unknown`（有 `desc_zh`）**

- 改前：`图1、图2 各替换一位`
- 改后：`图1中的人物替换原片里穿红裙的长发男生那位，图2中的人物替换原片里戴帽子的短发女生那位`

**双人 + 逐镜描述**

- 改前：`这一段原片有 2 个镜头，切点在 8.73 秒；`
- 改后：`…；这一段原片逐镜的画面（作为分镜、构图与运镜的依据；出镜人物的长相以参考图为准）：第1镜 …；第2镜 …；`

### 单一变量自证（没改的场景必须逐字不变）

`instruction()` 在**没有任何非人改动、没有 `ppl`、没有 `shot_looks`** 时的输出，
与改前**逐字相同**（脚本 A 组前后 diff 为空）。所以这次改动只影响
「勾了场景/商品/服装/风格」「方位不是 left/right」「有逐镜描述」这三种情形。

### 风险评估（写清楚，别当已解决）

- 第 4 条是**最可能反噬**的一条：逐镜描述写的是**原片**画面，里面包含原片人物的长相
  → 可能反过来强化"保留原片那张脸"（§15 的「传得太全 → 重拍原片」是同一类病）。
  已做两件事降低风险：① 它排在替换句**之后**；② 句子里写明「出镜人物的长相以参考图为准」。
  仍然只是**假设层面**的缓解，没有出片验证。
- 前 3 条都是"信息本来就有、只是没送到"，不改变任何提示词风格。

### 验过

| 命令 | 结果 |
|---|---|
| `scripts/test_whole_wiring.py --model h3` | **166/166** |
| `scripts/test_edit_spec.py --model h3` | **274/274** |
| `scripts/test_h3_shot_source.py --model h3` | **18/18** |
| `scripts/p16_check.py --model h3` | 32/33（S3 红，素材问题，与本次无关） |
| `D:/tmp/ir_abc/show_instruction.py` / `show_instruction2.py` | 8 组对照，见上面改前/改后 |

### 没改的两处（查到了，但不在本轮）

1. `instruction()` 里的切点没有自己排序 —— 生产里上游 `_clean_cuts` 已排好，
   但直接调 `instruction(cuts=[8.73, 4.0])` 会写出「切点在 8.73、4.00 秒」，
   违反官方 `base-en:86`「严格递增」。**加一行 `sorted()` 就够，等确认再动。**
2. `frame_n` 用 `cut_b`（= b + 0.5）算、`frame_ppl` 用 `b` 算，两处不一致；
   且「这一段一共几个人」这个事实没有写进句子，只用来决定要不要写「其余出镜人物保持原样」。

### §17 补（2026-11-03 11:10）：第 4 条**已撤回** —— 官方第 3 章给了反证

主人指了官方手册目录：`data/official/h3/manual-2026-10-28.md`

- **第 2 章「原生多模态理解与生成」（:165）** = 参考生成。2.2（:192）换人范例：
  「参考视频1进行动作模仿。固定机位全景镜头，正视频中三个穿西装的男人替换为
  三只高度写实的水豚。水豚必须严格遵循原视频的运动轨迹……保持原有的固定机位
  不变。确保水豚的毛发质感和光影与环境融合」
- **第 3 章「全能精准编辑与修改」（:200）** = 编辑。写法完全不同：
  - 3.1（:211）「**把视频中的猫换成狗**」
  - 3.1（:213）「视频1中最后面的小孩换成图1中的金毛狗，视频1中最左边小孩穿的
    卡其色外套改成图2中的牛仔外套」
  - 3.2（:221）「**视频1窗外的场景改成图1**」
  - 3.4（:206）「准确执行局部修改与细化要求，**同时保持未编辑内容相对稳定**」

**第 3 章所有编辑范例都是一句话，没有一条把原片画面逐镜描述一遍。**
3.4 那句「保持未编辑内容相对稳定」是**指令层面的能力**，不是靠复述原片换来的。

所以 #4（把 2.1 的 `shots[].en` 整段塞进改写器输入）**方向错了**：
逐镜描述写的是原片画面（含原片人物长相），塞进去恰恰可能强化"保留原片那张脸"，
与 §15「传得太全 → 重拍原片」是同一类病。已全部撤回（`h3_ir.py` 三处入参 +
`video_edit.py` 两处传参），原位留了一段「为什么不用」的注释，防止以后被重新加回去。

验过：`test_whole_wiring --model h3` 166/166、`test_edit_spec --model h3` 274/274；
`instruction()` 的 A 组输出与改动前逐字一致。

---

## §18（2026-11-03 12:0x）：用户手填的「改成什么」交给 IR

### 为什么改

主人定调：「提示词已经由 IR 帮我们撰写了」，我们不纠结措辞，
只保证 **IR 收到的事实是全的、准的、不自相矛盾的**。

查下来，用户在编辑页亲手打的字，只有一部分曾经进过提示词，而且进的是
**已经废弃的那条手拼链路**（`edit_spec.compile_prompt`），改写器那条路
一个字都没收到：

| 用户填的 | 之前到没到 IR | 现在 |
|---|---|---|
| `scene_desc`（场景改成什么样） | ❌ | ✅ |
| `product_desc`（商品改成什么样） | ❌ | ✅ |
| `product_target`（画面里换哪一件） | ❌ | ✅ |
| `wardrobe_desc` / `wardrobe_desc_by_id`（谁换成哪套） | ❌ | ✅ |
| `style`（风格 id） | ❌ | ✅（转中文词，见下） |
| 2.1 的 `notes` / `face_visible` / `main` / `desc_en` | ❌ | 未动（第 3/4 步） |
| 逐句说话人 `speaker_ids` | ❌ | 未动（第 2 步） |

### 怎么改

- `h3_ir.instruction()` 加 `changes: dict` / `people_desc: dict` 两个入参。
- 新增 `_has_product / _has_scene / _has_wardrobe / _has_style`：
  **槽位有图 或 用户勾了/写了** 都算"动了"。
  这三处同时决定 `_deltas`（换成什么）、`_bg`（光影那句）、`_keep_dims`
  （「X 与视频1一致」那句）—— 以前只看槽位，于是会出现
  「视频1中的场景不变」和「场景换成办公室」同时出现在一句里。
- 没有图、只有字时也能出句：
  - `视频1中的场景换成落地窗的现代办公室，白天，冷色调`
  - `视频1画面中桌上的玻璃杯换成陶瓷马克杯，米白色`
  - `穿红裙的长发女生的服装换成米色风衣；戴帽子的短发男生的服装换成深蓝工装外套`
  - `画面的风格和色调改为动漫`
- `video_edit._gen_spans` 在 `ir_looks` 旁边组 `ir_changes` + `ir_people_desc`，
  `prompt_sig` / `prompt_for` 两处都带上 → **改动也进缓存指纹**，改了描述会重抽。

### 🩸 改动中发现并修掉的一个自己造的坑

`edit_spec.STYLES` 的键是英文 id（`live` / `anime` / `3d` / `film` / `sketch`），
值才是中文（实拍 / 动漫 / 三维渲染 / 胶片质感 / 手绘插画）。
第一版直接 `bool(_sc.get("style"))` + 把 id 塞进句子，会写出
「画面的风格和色调改为 anime」。现改成在 `video_edit` 边界查表，
只把中文词交给 `h3_ir`（那边不认识 `edit_spec`，也不该认识）。

### 单一变量自证

`changes` 为空、`people_desc` 为空时，`_has_*` 退化成 `bool(槽位图)` —— 
与改前逐字同义（不是"差不多"，是同一个表达式）。A–H 八组（双人/单场景/
商品/服装/换人+换场景/九宫格/unknown/无盘点）输出与改前一致。

### 验过

| 命令 | 结果 |
|---|---|
| `scripts/test_whole_wiring.py --model h3` | **166/166** |
| `scripts/test_edit_spec.py --model h3` | **274/274** |
| `scripts/test_h3_shot_source.py --model h3` | **18/18** |
| `scripts/p16_check.py --model h3` | 32/33（S3 红，素材问题，与本次无关） |
| `D:/tmp/ir_abc/show_instruction3.py` 新增 S/T 两组 | 风格：文字走中文词；图优先 |

### 顺手查到的、**没动**的一处

`style_video`（用户上传一段**风格参考视频**）这条路，IR **完全看不见**：
`h3_ir.py:608` 只发 `videos=[video]` 这一段原片，风格参考视频只进了出片请求
（`models/h3.py:70` 的 `ref_videos`）。此时 `_has_style` 还是 False，
句子仍会说「题材与风格都与视频1一致」—— 是真矛盾。
但直接告诉改写器「参考第二个视频」而它手上没有那段视频，只会更糟。
要修得把参考视频也送进 `context_ir`（成本/指纹都会变），单独一轮做。

---

## §19（2026-11-03）：每句台词带上「谁说的」交给 IR

### 为什么改

第 2 步。改写器产出的正文靠 `(S1)/(S2)` 把台词绑到主体上（`<d>[Chinese] …</d>`），
但它拿到的输入只有「秒数 + 字」，**没说是谁开口** —— 只能听音频猜。
两人同框对白最容易猜错，猜错就等于让错的人动嘴。

### 事实其实早就算出来了，只是没往下传

- `_assign_speakers(rec, inventory)`（`video_edit.py:1695`）本来就会把
  「声纹分句（`asr_speaker`）+ 画面唯一在场」两路证据投票，落到
  `voice_lines[].speaker = "P1"`
- 但 `_span_script` 只返回 `(起, 止, 字)` 三元组，`who` 被丢掉
- 它自己的 docstring 那句「H3：仍走界面手勾的 `speaker_ids`，**没接**这里的推断」
  就是这条断链的自白（已改写）

### 怎么改

- `_span_script(rec, a, b, people_desc=None)` → 返回 **4 元组**，第 4 项 = 中文外观
  （盘点 id 经 `desc_by_id` 翻译；查不到 → 空串，**不编人**）
- `_gen_spans` 把 `ir_people_desc` 提前到台词那一段算（换装和台词共用同一份）
- `h3_ir.instruction()` 的 `lines` 兼容 3/4 元组：
  - 有说话人 → `1.20–3.56 穿红裙的长发女生：你们俩学成之后想做什么`
  - 没有 → 老格式 `1.20–3.56 你们俩学成之后想做什么`（逐字不变）

### 边界

- 界面手勾的 `speaker_ids` 是**整段名单**（「谁开口」），**没有逐句对应**，
  所以不能拿它逐句点名；仍只进 `edit_spec` 手拼链路。要让用户手选「这句谁说的」
  是产品改动，不在本轮。
- `speaker` 只在 `_gen_spans` 的内存副本上算，不写回任务记录（老行为）。

### 验过

| 命令 | 结果 |
|---|---|
| `scripts/test_whole_wiring.py --model h3` | **168/168**（原 166 + 新增 2 条说话人断言） |
| `scripts/test_edit_spec.py --model h3` | **274/274** |
| `scripts/test_h3_shot_source.py --model h3` | **18/18** |
| `scripts/p16_check.py --model h3` | 32/33（S3 红，素材问题） |
| 端到端（合成 rec + 盘点） | `_assign_speakers` → `P1/P2` → `_span_script` 带出两位中文外观 |

> 🩸 三条老断言（`_span_script` 返回值相等）同步改成 4 元组 —— 判据本身
> （哪个字归哪一段）一个字没动，只是返回形状变了，属于契约变更不是凑绿。

### 顺带发现（不是本轮引入）

跑全量时多跑了一套 `scripts/test_auto_render.py` → **41/44**，三条红都关于
分镜排片（`两段拼起来覆盖整镜` / `重叠参考不重复排片` / `第三段从素材 0.4s 起`）。
把本轮两个改动文件 `git stash` 掉再跑，**同样 41/44** → 与本轮无关，是老红。
没有动它，记在这里。

---

## §20（2026-11-03）：风格参考视频也交给 IR（补 §18 末尾那条缺口）

### 缺口是什么

用户传一段**风格参考视频**时：
- 出片请求里它是存在的（`models/h3.py:70` → `ref_videos=[style_clip]`）
- 但改写器 `context_ir` 只收到**一段**视频（`h3_ir.py` 的 `videos=[video]`）
- 句子还写着「题材与风格都与视频1一致」

→ 改写器既看不见风格片，又被明确告知风格跟原片走。两边矛盾。

### 官方口径（先查再改）

`data/official/h3/pull-2026-11-02/api_v2-h3-context-ir.md`
- `:234-249` 视频 `video_url`（多模态参考场景）：**个数 ≤3**、单段 [2,15]s、
  **总时长 ≤15 s**、单文件 ≤50 MB
- `:183-206` content 数组顺序即编号；`reference_video` 与首尾帧互斥
- 出片侧同一套上限（`minimax.check_limits`，`create` 页）

我们本来就有预算闸：`video_edit.style_video_budget` 按 `ref_video_total_sec`（H3 = 15s）
反推风格片段能截多长，放不下就**一次都不发**。所以「原片段 + 风格片段 ≤15s」已成立，
不需要在这个接口上重做配额。

### 怎么改

| 位置 | 改动 |
|---|---|
| `h3_ir.prompt_for` | 新增 `style_video`（片段文件）/ `style_src` / `style_span`；`videos=[原片, 风格片段]` |
| `h3_ir.prompt_sig` | 新增 `style_src` / `style_span`，与 `prompt_for` 走同一个 `_fp` |
| `h3_ir._fp` | **有**风格时才把 `sig_of(style_src, span)` 拼进键 → 无风格任务指纹与改前**逐字相同**（不白废已缓存的改写结果） |
| `h3_ir.instruction` | 新增 `style_video: bool`；`_has_style` 把它算进去（不再说「题材与风格与视频1一致」）；`_deltas` 出句 |
| `video_edit._gen_spans` | 两处调用都带上 `style_clip` + 源 + `(0, clip_sec)`；`style_clip_sec` 提前到 if 外 |

出句：
> 画面的风格、色调和质感参考视频2，只取风格与色调，不复制视频2里的画面内容

编号依据：**content 顺序 = 原片在前、风格片段在后**，与出片请求一致
（`minimax.reference_video` 也是先原片、后 `ref_videos`）。

「不复制它的画面内容」这句不是修辞 —— 不写，改写器会把风格片里的人/场景当成
要复刻的素材（`clone_brief.py:355` 给 agent 的同一句就是这个意思）。

### 优先级

风格**图** > 风格**视频** > 风格**词**，与老编译器 `edit_spec.py:1326-1334` 一致
（三者同时勾时前者生效、后者被忽略）。原来的写法是「词」排在「视频」前，已调正。

### 验过

| 项 | 结果 |
|---|---|
| 无风格任务指纹 | 与改前公式**逐字相同**（`01399bd77068` 两算一致） |
| 有风格任务指纹 | 随风格素材变（A/B 两段素材 → 两个不同键） |
| `instruction` 风格视频组 | 出现「参考视频2…不复制」；`主体…与视频1一致` 里**不再**出现「题材与风格」 |
| 风格图 + 风格视频同时给 | 只出图那句，不提视频2（与老编译器优先级一致） |
| `test_whole_wiring --model h3` | **168/168** |
| `test_edit_spec --model h3` | **274/274** |
| `test_h3_shot_source --model h3` | **18/18** |
| `test_person_refs --model h3` | 3/3 |
| `p16_check --model h3` | 32/33（S3 素材问题，老红） |

### ⚠️ 没实测的部分（说清楚，不冒充验过）

- 真调一次 `context_ir` 带**两段视频**能不能过（会不会 2013/超时/传不上去）——
  要花钱，**没跑**。官方 schema 允许 ≤3 段，但「schema 允许」≠「我们账号跑得通」。
- 风格任务的旧缓存不会被复用（键里多了风格指纹）→ 下次出片这几段会**重新抽一次** IR。
- 生效仍需**主人重启后端**。

---

## §21（2026-11-03）：主人问「还有没有会让 IR 判错的地方」—— 逐项核完，又补了两处

不是凭印象答，是把 `instruction()` 的**每一个入参**跟「真正发出去的请求」逐项对了一遍。

### 核过、确认对齐的（不用改）

| 项 | 怎么核的 |
|---|---|
| 图号 `图N` ↔ `images[]` | 两者同源：`plan["slots"]` 与 `plan["ordered"]` 都来自同一次 `ref_plan()`；按段摘缺席者时用**同一个 `keep_i`** 同时裁；`instruction` 从 `enumerate(slots,1)` 起编号 |
| 视频号 | 原片段=视频1，风格片段=视频2；`context_ir` 的 content 顺序先原片后风格，与 `reference_video` 一致 |
| 音频号 | `audio_mode` 只在 `seg_audio` 非空时给；`audios=[seg_audio]` 同步。`_master_audio` 分支**没有任何型号声明**（`Caps.audio_from_master` 全库 0 处为 True）→ 是死分支，不会出现"句子说有音频、请求里没有" |
| 时长 | `prompt_sig` / `prompt_for` 都是 `_gen_duration(dur, plan.get("model") or "")`，同一表达式 |
| 切点 | `_clean_cuts` 排序、去重、丢掉越界；全部相对段起点 |
| 外观描述 `looks` | `{槽位: 该槽位自己那张图的描述}`，不跨槽位借用 |
| 方位 `ppl` | 由 `span_slots` 推导，与 `person_pics` 同序；只勾第 2 个人时也对得上（实测） |
| 台词秒数 | `_span_script` 按 `[a,b)` 裁，减 `a`；用 `b` 不用 `cut_b` |
| 边界帧 | `bf_pic` 恒 0（2026-11-02 已整条停用） |

### 新发现并修掉的两处

**① 取消勾选的人，换装描述还在生效**（`h3_ir._deltas`）

- 前端 `diagnose.vue:2624-2636 pickWardrobe` 取消勾选时**只动 `wardrobe_ids`**，
  已经填好的 `wardrobe_desc_by_id[id]` 不删；
- 后端 `edit_spec.py:277-286` 也只校验 id 形状，**不按名单过滤**；
- 老编译器没这毛病（`edit_spec.py:1211` 是按 `wardrobe_ids` 遍历的），
  但我新加的 `_deltas` 是**按字典键**遍历 → 用户说"这个人不改"，句子照样写
  「她的服装换成…」。
- 修法：`ir_changes` 多传 `wardrobe_ids`，`_deltas` 只认名单里的人。
  名单为空（老任务/全员一起换）时保持老行为。

**② 推断的说话人可能顶撞用户手勾的名单**（`video_edit._span_script`）

- `speaker_ids` 的语义是 `clone_brief.py:390`「名单外的人在画面里不开口」，
  是用户拍的板；声纹/画面推断只是猜。
- 修法：`_span_script(allow_ids=...)`，推断出名单外的人 → 这一句**不署名**，
  宁可退回"谁说的不知道"。名单为空 = 不限制（老行为）。

> 顺带记一条**没改**的：用户在界面上手勾的 `speaker_ids` **对 H3 出片本身没有作用**
> —— 它只进了 `edit_spec` 编译版，而 H3 的编译版会被改写器产出整段覆盖。
> 现在只做到"不让推断顶着它"，没有把它当成一句事实交给 IR
> （"只有这几位开口"是**全片级**断言，套到单段上会和 §18 第 3 步 `notes` 同一个毛病）。

### 还剩的（都没改，逐条有理由）

| 项 | 现状 | 为什么不改 |
|---|---|---|
| `notes` / `main` / `face_visible` | 不进 IR | 全片级、无时间锚；官方 IR 输入是一句话（§18 第 3 步） |
| `frame_n` 用 `cut_b`、`frame_ppl` 用 `b` | 差 0.5 秒尾巴 | 只影响"要不要说『其余出镜人物保持原样』"，边缘情形 |
| 切点来自本地 `scene.detect_shots` | 不是 2.1 的镜头表 | 对 IR 不算误导（它看到的视频就是这个结构）；但**界面显示的镜头和 IR 说的可能不是同一套** |
| `_ir_defects` 只查结构 | 不判内容对不对 | 质量判定是主人 2026-11-03 明确撤掉的 |
| 风格视频真调一次 | 没跑 | 要花钱 |

### 验过

`test_whole_wiring` **170/170**（新增 2 条说话人名单断言）｜`test_edit_spec` 274/274｜
`test_h3_shot_source` 18/18｜`test_person_refs` 3/3｜`p16_check` 32/33（S3 老红）

---

## §22（2026-11-03）：让 2.1 顺带记「谁在动嘴」（同框对白也能定说话人）

### 问题

`_assign_speakers` 的第二路证据（画面唯一在场）在**多人同框**时**主动弃权**
（`return hit[0] if len(hit)==1 else ""`，防两个嗓音被混成一个）。
结果是：三个人同屏的片子，ASR 明明分出了两个声纹（`1,2,1`），却一个都落不到人身上
→ 台词全都不署名 → 改写器不知道谁开口，口型/台词容易绑错人。

### 根因：2.1 从没被问过这件事

盘点 schema 里**没有**任何「谁在说话」字段：

- 顶层 6 个：`duration_s / people / products / scenes / shots / notes`
- 人物 7 个：`id / desc_zh / desc_en / position / appearances / main / face_visible`
- 镜头 3 个：`start / end / en`（`en` 是构图描述，不说谁开口）

### 改法（**不新增调用**）

2.1 收到的本来就是**整条视频**（`data:video/mp4;base64` + fps 送方舟），盘点这单
已经调过一次。所以在同一次请求里多答一个字段：

| 位置 | 改动 |
|---|---|
| `vision_plan._SCHEMA` | `people[].speaks: [{start,end}]`，**故意不进 required** |
| `vision_plan._ASK` | 明写「只报看得见的嘴部开合，多人同框也照实填，不要凭剧情猜」 |
| `vision_plan.normalize` | 保留并夹回视频时长；老盘点没有 → `[]` |
| `video_edit._assign_speakers` | 第 ③ 路证据 `who_speaking()`：这句时间里**只有一个人在动嘴**才投票 |

优先级：**动嘴（唯一）> 画面唯一在场 > 声纹映射回填**。
投票机制没变（仍要「声纹↔人物」一致 + 一人只占一个声纹），**闸没放宽**，
只是多了一个能在同框时开口的证据源。

### 为什么**不升** `_SCHEMA_VER`

文件原注释写「schema 加字段就要 +1」，这次是**例外**，理由写在常量旁边：

- 新字段非必填，老盘点读出来是空数组 → 行为与今天**完全一样**，
  不是"改了没生效"；
- 升版本会让老任务下一次 `inventory()`（不带 refresh）**静默重新扣一次费**；
- 「重新识别」按钮走 `refresh=True`，本来就绕缓存，一定拿到新字段。

### 验过

| 项 | 结果 |
|---|---|
| 三人同框、只有 `speaks` 能区分 | `['P1','P3','P1']`（与声纹 1,2,1 一致） |
| 两人同时动嘴 | 弃权，不标 |
| 老盘点（无 `speaks`） | 与改前**逐字一样**：全不标 |
| `normalize` 夹取 | `end=99` → 夹到 10.1；缺失 → `[]` |
| `test_video_edit_logic --model h3` | **87/87**（新增 3 条） |
| `test_whole_wiring` | 170/170 |
| `test_edit_spec` / `test_h3_shot_source` / `test_person_refs` | 274/274 · 18/18 · 3/3 |
| `p16_check` | 32/33（S3 老红） |

### ⚠️ 没实测

2.1 真跑一次会不会老老实实给 `speaks`（会不会空、会不会给得过宽）**没跑过**
—— 要花钱。要验就给一条片子点「重新识别」，然后看 `inventory/*.json` 里有没有这个字段。

---

## §23（2026-11-03）：台词署名的**指代**写错了（主人当场看出来）

### 症状（真实发出去的那句，`ir/seg_001_6b4aa9cd0a9d.in.txt`）

> …1.20–3.56 **黑色高束马尾，额间有红色痣，佩戴长款白色垂坠耳饰，穿印黑白太极图案的
> 白色抹胸，黑色百褶短裙，腰间系红绳挂铜钱配饰，脚穿黑色夹脚拖鞋**：你们俩学成之后想做什么；…

三个毛病：

1. **太长** —— 60 个字塞进一句话，句子读不成句；
2. **指代对不上** —— 正文用的是 `<Subject N>` / `图N`，这里突然换成一整段长相描述，
   改写器还得自己猜这段长相对应哪个 Subject；
3. 🩸 **写的是原片那个人的衣服和发型**，而他正是**要被换掉的人**。
   复述原片外观会强化"保留原片那个人"—— 与 §17 撤回逐镜描述**同一类病**。

### 改法（`video_edit._gen_spans`）

台词署名换成与换人句**同一套指代**：

- 有参考图的人 → **`图N中的人物`**（N = 该人物图在 `images` 里的序号，正文里就是 `<Subject N>`）
- 没被换的人（没图，如中间那位）→ 外观描述的第一小段（不含衣服列表）
- 换装那条路仍用**完整**外观描述（"谁的哪套"要叫得出那个人），两者分开，不共用一份

### 改后（同一单、同一份盘点、真实数据）

> …1.20–3.56 **图1中的人物**：你们俩学成之后想做什么；
> 4.00–6.88 **图2中的人物**：我想天天抓僵尸不用干活洗衣；
> 7.68–9.68 **图1中的人物**：先把今天的水缸叼满再说；…

### 代价

文本变了 → 改写器指纹变 → 下次出片**每段会重新调一次 IR**（旧缓存不复用）。
这是必要的：旧词按新代码根本不会再生出来。

### 验过

`test_whole_wiring` 170/170｜`test_edit_spec` 274/274｜
`test_h3_shot_source` 18/18｜`test_video_edit_logic` 87/87

### 顺带记录：这一单（`56b0bb23`）第一版的出片结果

- 出片成功、10.1 秒、无报错
- 身份核对：`person` best_sim **0.222** / p90 0.148 / **share 0.0**；
  `person2` best_sim **0.200** / p90 0.171 / **share 0.0**
  （对照：唯一确认换成功的单人样本 `ccf2ba27` share **0.978**）
- 只报数，不下结论标签（2026-11-03 主人已撤掉质量判定）

---

## §24 · 2026-11-03 · **换人句改成官方第 3 章「编辑」体裁**（主人定：是我给的指令不对）

### 为什么改（主人原话）

> 「我说了绝对是你没有按要求给到准确的指令给IR所以才导致每次换人换不了！」

数了一下**真实这一单**（`56b0bb23`）发出去的原话，主句是"复刻原片"：

| 词 | 改前（真实 in.txt） | 改后（真实数据重放） |
|---|---|---|
| 保持 | 2 | 2 |
| 一致 | 2 | 0 |
| 复刻 | 1 | 0 |
| 必须严格遵循 | 1 | 0 |
| 光影 | 1 | 0 |
| 替换 | 4 | 0 |
| **换成** | **0** | **2** |

改后剩下的两处「保持」都是**限定范围的**：
「其余出镜人物保持原样」（K=3、只换 2 人时必须有）、
「其余未编辑的内容保持相对稳定」（官方 `manual:206` 原话）。

### 出处（不是自造）

`data/official/h3/manual-2026-10-28.md`：
- 第 3 章「全能精准编辑与修改」`:200`
  - `:211`「把视频中的猫换成狗」
  - `:213`「视频1中最后面的小孩换成图1中的金毛狗，视频1中最左边小孩穿的卡其色外套改成图2中的牛仔外套」
  - `:221`「视频1窗外的场景改成图1」
  - `:206`「准确执行局部修改与细化要求，同时保持未编辑内容相对稳定」
- **第 3 章全章「保持」只出现这一次**；范例全是**一句话**，没有一条复述原片画面。
- 原来那五段（动作模仿/替换为/严格遵循轨迹/保持机位分镜/光影融合）出自**第 2 章
  `:192` 的参考生成范例**（水豚那条）—— 体裁用错了。

### 改了什么（`app/services/h3_ir.py`，只动换人分支）

1. 主句：「图1中的人物替换左边那位」→ **「视频1中左边那位换成图1中的人物」**
   （`manual:213` 的主宾次序）
2. 删除「{图N}必须严格遵循原视频的运动轨迹，保持原有的机位和分镜不变」
3. 删除「场景、背景、光线也来自视频1，光影与环境与原片融合」
4. 换人时不再写核心创意句「主体是…，地点、事件、题材与风格都与视频1一致」
5. 收尾：「按视频1原样的分镜逐镜复刻，景别、构图、运镜、动作、口型都与视频1一致，
   只替换出镜人物」→ **「其余未编辑的内容保持相对稳定」**（`manual:206`）
6. 另两个分支（认不出方位/单人）的「替换为」同步改「换成」，同一出处

**保留**：两张人物素材说明（图1、图2 都在）、音频说明、`参考视频1进行动作模仿`、
镜头数+切点、逐句台词与说话人。

### 单一变量

**非人物改动**（换商品/场景/风格/服装、无换人）的 `_keep_dims`/`process`/`idea`
一个字没动 —— 输出与改前逐字相同（M/N/O/Q/R/S/T/X 八例已在 `show_instruction3.py` 对比）。

### 真实这一单改后原话（`56b0bb23`，数据重放，未出片）

> 人物参考图1提供了人物的形象，锁定脸和长相：…；人物参考图2提供了人物的形象，
> 锁定脸和长相：…；音频1是视频1的原声轨，成片复用这条原声；参考视频1进行动作模仿；
> **视频1中左边那位换成图1中的人物，视频1中右边那位换成图2中的人物，其余出镜人物保持原样。**
> 这一段原片有 2 个镜头，切点在 8.73 秒；这一段原片里说了这些台词，秒数相对本段起点：
> 1.20–3.56 图1中的人物：你们俩学成之后想做什么；…；**其余未编辑的内容保持相对稳定。**

### 验过

`test_whole_wiring` **172/172**（12 条旧断言按新契约重写，每条都指到 `manual:206/211/213`）｜
`test_edit_spec` 274/274｜`test_h3_shot_source` 18/18｜`test_video_edit_logic` 87/87｜
`p16_check` 32/33（S3 素材问题，与本次无关）

### 代价

文本变 → IR 指纹变 → 下次出片每段重调一次 IR（旧缓存不复用）。

### ⚠️ 生效条件

需要**主人重启后端**（我不重启）。

---

## §25 · 2026-11-03 · **人物素材行不再写外观描述**（主人指官方范例）

### 主人指出的证据

官方 `manual:213` 的「精准换人物与细节」范例整行：

> 视频1中最后面的小孩换成 **图1中的金毛狗**，视频1中最左边小孩穿的卡其色外套
> **改成图2中的牛仔外套**
> 输入：图1（狗的照片）+ 图2（牛仔外套照片）+ 参考视频

—— 参考素材**只给图，一个字的外观描述都没有**；成片是女孩直接穿上了那件外套。

### 原来那句的问题（不是"措辞重"，是**内容打架**）

原句：`人物参考图1提供了人物的形象，锁定脸和长相：{subject_desc.json 全文}`

`subject_desc.json` 是上传定妆照时由 `doubao-seed-2-1-lite-260915` 自动生成的，
本次核到 `_image_sha1` = `subject.jpg` 的 sha1。它**不只写脸**：

| 描述（定妆照） | 原片里这个人实际是 |
|---|---|
| 深棕褐色**大波浪长卷发** | 黑色**高束马尾** |
| 单肩露肩**修身收腰高开叉拖尾层叠薄纱礼服** | 白色太极印花**抹胸 + 黑色百褶短裙** |
| **高挑纤细**身形 | — |

一句话里同时有「其余未编辑的内容保持相对稳定」（衣服场景照原片）和
「锁定：卷发 + 露肩礼服 + 纤细身形」（第二套外观）—— IR 收到两条冲突事实。

另外「锁定脸和长相」本身出自 `manual:248` 用途词表「人物参考（锁定脸/形象）」，
不是自造；**但官方范例句里没有这个概念**，只有「@图片1 提供了xx角色的形象」。

### 改了什么（`app/services/h3_ir.py`）

```diff
- materials.append(f"人物参考图{i}提供了人物的形象，锁定脸和长相：{feat}")
+ materials.append(f"人物参考图{i}提供了人物的形象")
```

`looks` 参数保留在签名里（调用方不用改），但**不再进句子**。

### 连带：指纹

句子不再含描述 → `looks` 单独变化不再让段缓存失效（**换图**本身会让
`images` 的 sha 变，指纹照样变）。`test_whole_wiring` 那条断言已按新契约改。

### 真实这一单改后原话（`56b0bb23`，数据重放）

> 人物参考图1提供了人物的形象；人物参考图2提供了人物的形象；音频1是视频1的原声轨，
> 成片复用这条原声；参考视频1进行动作模仿；视频1中左边那位换成图1中的人物，
> 视频1中右边那位换成图2中的人物，其余出镜人物保持原样。这一段原片有 2 个镜头，
> 切点在 8.73 秒；这一段原片里说了这些台词，秒数相对本段起点：1.20–3.56 图1中的人物：
> 你们俩学成之后想做什么；4.00–6.88 图2中的人物：我想天天抓僵尸不用干活洗衣；
> 7.68–9.68 图1中的人物：先把今天的水缸叼满再说；其余未编辑的内容保持相对稳定。

（408 字 → **258 字**）

### ⚠️ 一个已知的反证要记住

2026-11-02 做过一次「不传描述」的对照，当时结论是"零个五官词 → 成片不换脸
（SFace 0.09）"。但那次同时缺别的条件（§17 已撤回多条规则），**不能据此
认定描述是必要的**；而且描述原文本身就带着第二套外观。这次先按官方范例走，
若仍不换脸，下一个变量**不是**把描述加回来。

### 验过

`test_whole_wiring` **172/172**｜`test_edit_spec` 274/274｜
`test_h3_shot_source` 18/18｜`test_video_edit_logic` 87/87｜
`p16_check` 32/33（S3 素材问题，与本次无关）

---

## §26 · 2026-11-03 · **换人也走第 3 章「编辑」体裁，不再写「参考视频1进行动作模仿」**

### 主人第三次指同一件事

> 「说你一直给不准确的指令给到IR让他产生了误判。然后本来该有的运镜也被你锁死
> 让IR自己判断不出来。」

### 错在哪

换人分支的开头是 `参考视频1进行动作模仿`，出处是 `manual:192`（水豚那条）——
那是**第 2 章 2.2 动作参考**：「参考视频1进行动作模仿。…必须严格遵循原视频的
运动轨迹…保持原有的固定机位不变」。它的语义是**照着参考片重新生成一段**，
所以运镜/分镜/表演全被锁在原片上，IR 没有余地判断。

我们的任务是在**已有原片**上改一个人，属于第 3 章编辑（`:200`）。
第 3 章全部范例（`:211`「把视频中的猫换成狗」/ `:213`「视频1中最后面的小孩换成
图1中的金毛狗」/ `:221`「视频1窗外的场景改成图1」/ `:206` 原则句）
**一句"动作模仿/保持机位"都没有** —— 编辑体裁的默认语义就是"没说的不动"，
运镜本来就在原片里，不需要（也不该）再由我们锁一遍。

而且我自己的**非换人分支**（换商品/场景/风格/服装）早就在用第 3 章的
`视频1是被编辑的原片，视频编辑：在视频1上做改动` —— 同一段里两种体裁并存。

### 改了什么（`app/services/h3_ir.py`）

```diff
- materials.append(f"参考视频1进行动作模仿；{_repl}{_more}")
+ materials.append("视频1是被编辑的原片，视频编辑：在视频1上做改动："
+                  f"{_repl}{_more}")
```

H20 那套五段注释已标 **⛔ 2026-11-03 作废**，保留只为说明当时依据。

### ⚠️ 与一条旧实测记录冲突（如实记下）

2026-11-02 的 A/B：写「视频编辑」的 8 份产出，IR 标 `partially_preserved`；
写「动作/镜头」的 4 份标 `attribute_transfer`，**唯一换脸成功的那次在后一组**。
但那次对照跑在**旧的 6 处"保持"骨架上**（§17/§24 已撤），两组之间不止体裁一个
变量 —— 结论不能直接沿用。这次按官方体裁走；若仍不换脸，下一个变量另找，
**不要把"动作模仿"加回来当默认**。

### 真实这一单改后原话（`56b0bb23`，数据重放）

> 人物参考图1提供了人物的形象；人物参考图2提供了人物的形象；音频1是视频1的原声轨，
> 成片复用这条原声；视频1是被编辑的原片，视频编辑：在视频1上做改动：
> 视频1中左边那位换成图1中的人物，视频1中右边那位换成图2中的人物，
> 其余出镜人物保持原样。这一段原片有 2 个镜头，切点在 8.73 秒；这一段原片里说了
> 这些台词，秒数相对本段起点：1.20–3.56 图1中的人物：你们俩学成之后想做什么；
> 4.00–6.88 图2中的人物：我想天天抓僵尸不用干活洗衣；7.68–9.68 图1中的人物：
> 先把今天的水缸叼满再说；其余未编辑的内容保持相对稳定。

### 验过

`test_whole_wiring` **172/172**｜`test_edit_spec` 274/274｜
`test_h3_shot_source` 18/18｜`test_video_edit_logic` 87/87｜
`p16_check` 32/33（S3 素材问题，与本次无关）

---

## §27 · 2026-11-03 · **画面里所有的人都点名**（主人：IR 全靠猜）

### 主人

> 「你改得太乱了！其实2.1模型和IR如果能得到准确的指令他们能做得出精准的判断！
> 现在IR根本都不知道你要什么很多都是自己猜的」

### 证据（真实 IR 产出 `7bd9bab305fd`）

指令只写了「视频1中**右边那位**换成图2中的人物」，同框有两个男人：

| IR 产出 | 实际 |
|---|---|
| `summary`: `<Subject 2> replaces **the man**` | 两个男人，没指哪一个 |
| `retention_analysis`: `replaces **the original man's** position and role` | 同上 |
| `subject_definitions`: `the man in a black T-shirt from <Picture 2>` | 只有参考图里的样子，没说是原片哪一位 |
| 只在 `detailed_description` 才补 `stands on the right` | 前面全在猜 |

**根因**：§17 撤"逐镜复述原片长相"时，把**指认"是哪一个人"**也一起撤了。
两件事必须分开：
- 复述原片长相去描写画面 → 会强化"保留原片那张脸"（该撤）；
- **指认要换的是哪一个人** → 必须有唯一标识（官方 `manual:213`
  「最后面的小孩」「最左边小孩穿的卡其色外套」就是 方位 + 可辨识特征）。

### 改了什么

`h3_ir.instruction()` 新增 `ppl_all`（这一段画面里**所有人**，来自
`vision_plan.people_in`），有名单时逐人写：

> 视频1中**左边黑色高束马尾、额间有红色痣那位换成图1中的人物**；
> 视频1中**中间黑色齐刘海短发、穿灰色立领中式长衫那位保持原样**；
> 视频1中**右边黑色短发、穿深蓝色立领中式上衣那位换成图2中的人物**

- 外观取盘点 `desc_zh` 的**前两项**（发型/标记 或 发型/上衣）—— 短名词短语，
  与官方范例同一种指认方式，不复述整段画像
- 不换的人也写出来 → 模型没有"顺手换错人"的空间
- 没给 `ppl_all`（老调用）→ **逐字退回**原来的方位写法，行为不变
- `video_edit` 两处调用点传 `ppl_all=ir_ppl_all`（与 `frame_n` 同一次
  `people_in` 结果，不多算）

### 真实这一单的原话（318 字，数据重放）

> 人物参考图1提供了人物的形象；人物参考图2提供了人物的形象；音频1是视频1的原声轨，
> 成片复用这条原声；视频1是被编辑的原片，视频编辑：在视频1上做改动：
> 视频1中左边黑色高束马尾、额间有红色痣那位换成图1中的人物；
> 视频1中中间黑色齐刘海短发、穿灰色立领中式长衫那位保持原样；
> 视频1中右边黑色短发、穿深蓝色立领中式上衣那位换成图2中的人物。
> 这一段原片有 2 个镜头，切点在 8.73 秒；这一段原片里说了这些台词，
> 秒数相对本段起点：1.20–3.56 图1中的人物：你们俩学成之后想做什么；
> 4.00–6.88 图2中的人物：我想天天抓僵尸不用干活洗衣；
> 7.68–9.68 图1中的人物：先把今天的水缸叼满再说；其余未编辑的内容保持相对稳定。

### 验过

`test_whole_wiring` **175/175**（新增 3 条：全员点名两位、不换的那位也点名、
无名单时退回老写法）｜`test_edit_spec` 274/274｜`test_h3_shot_source` 18/18｜
`test_video_edit_logic` 87/87

### ⚠️ 未做

新一轮 IR 没跑（要主人同意再花一次钱）。

---

## §28 · 2026-11-03 · **台词按镜头归位**（不再平铺给 IR）

### 主人

> 「怎么改？只针对这个提示改还是按照什么逻辑改？」→ 按通用逻辑改，不打单点补丁。

### 实测翻车（真实 IR 产出 `edb6eb707089`）

我们平铺给三句，IR 自己分配到镜头，分错了：

| 台词 | 实际时间 | IR 写进 |
|---|---|---|
| 你们俩学成之后想做什么 | 1.20–3.56 | `[Shot 1]` ✅ |
| 我想天天抓僵尸不用干活洗衣 | **4.00–6.88** | **`[Shot 2]`** ❌（第 2 镜从 8.73 开始） |
| 先把今天的水缸叼满再说 | 7.68–9.68（跨切点） | `[Shot 2]`（整句） |

音频是 1:1 复用的：提示词说 8.73 秒后说，音频 4 秒就在说 → **口型必错**。
这是独立于"换人脸"的第二个失败原因。

### 官方依据

- `manual:251`「如果一句台词跨shot，可以用**接着上个shot继续说**这样的描述
  表明是跨shot的台词对白」
- `manual:255`「H3 能够响应跨shot（J-cut，L-cut）的台词响应，**只要明确写出
  一句台词跨了哪些shot就可以响应**」
- `base-en:142` 跨切点要在连接点标 `<scenetrans>` 并说明音频跨切点继续

### 改法（通用算法，不是为这单写死）

`h3_ir.instruction()` 新增 `span_dur`（本段时长）；台词输出改为：

1. 无切点 → **逐字退回**原来的平铺写法（单镜头任务行为不变）
2. 有切点 → 按切点把本段切成 N 个区间，每句按它的 `[起,止]` 归到区间：
   - 整句落在一个区间 → 归到那个镜头
   - **跨过切点** → 归到它开始的那个镜头，并注明「这句跨过切点，接着上一个
     镜头继续说」
3. 没有台词的镜头不列（`cuts_txt` 已说明一共几个镜头）

`video_edit` 两处调用点传 `span_dur=dur`（本段真实长度 `cut_b - a`）。

### 真实这一单现在的原话（363 字）

> …视频1中右边黑色短发、穿深蓝色立领中式上衣那位换成图2中的人物。
> 这一段原片有 2 个镜头，切点在 8.73 秒；这一段原片里说了这些台词，
> 秒数相对本段起点，**按镜头分：第 1 个镜头（0.00–8.73 秒）**：
> 1.20–3.56 图1中的人物：你们俩学成之后想做什么；
> 4.00–6.88 图2中的人物：我想天天抓僵尸不用干活洗衣；
> 7.68–9.68 图1中的人物：先把今天的水缸叼满再说
> **（这句跨过切点，接着上一个镜头继续说）**；其余未编辑的内容保持相对稳定。

### 与 2.1 镜头表的关系

2.1 盘点给的是 `0–8.6 / 8.6–10.1`；逐帧场景分实测硬切在 **8.733**
（该帧 0.461，前后各帧均 <0.03）。**时间点用帧级实测值**，2.1 用它来判断
"有几个镜头"；两者不冲突，2.1 的 8.6 是粗采样。

### 验过

`test_whole_wiring` **179/179**（新增 4 条：第 1 镜归位、第 2 镜不重复列、
跨切点标注、落在第 2 镜的台词归位、无切点逐字退回）｜`test_edit_spec` 274/274｜
`test_h3_shot_source` 18/18｜`test_video_edit_logic` 87/87｜
`p16_check` 32/33（S3 素材问题）

---

## §29 · 2026-11-03 · **跨镜台词用 ASR 字级时间在切点处切开**

### 主人

> 「ASR？？？这个我们不是也调用过了吗？」

对 —— ASR 早就在任务里（`recipe.speech.segments[].chars[]`），
`_span_script` 一直在用它把台词切到**每一段**。缺的只是**在段内的镜头切点
再切一次**，不需要任何新的模型调用。

### 上一版 `b3d6978179e8` 剩下的偏差

第三句 7.68–9.68 跨切点 8.73；我们整句挂在 Shot 1 并注明跨镜，IR 仍把**整句**
放进了 `[Shot 2]` —— Shot 1 最后约 1 秒原声在说话，提示词却没写。

### 改了什么

1. `video_edit._span_script` 第 5 项带出**字级时间** `[(字, 起, 止)]`（相对段起点）
2. `h3_ir._group_lines`：一句台词跨切点时，按**字的中点**把它切开：
   - 前截归前一个镜头（结束时间钳到切点）
   - 后截归后一个镜头（开始时间钳到切点），并注明「（接着上一个镜头继续说）」
   - 没有字级时间（重配文案/老任务）→ 退回整句挂起始镜头 + 跨镜说明
3. 官方依据：`base-en:142`「use `<scenetrans>` at the connecting points **in both
   parts** and explicitly state that the audio continues across the cut」；
   `manual:255`「只要明确写出一句台词跨了哪些shot就可以响应」

### 真实这一单现在的原话（396 字，台词部分）

> …按镜头分：**第 1 个镜头（0.00–8.73 秒）**：1.20–3.56 图1中的人物：
> 你们俩学成之后想做什么；4.00–6.88 图2中的人物：我想天天抓僵尸不用干活洗衣；
> **7.68–8.73 图1中的人物：先把今天的水缸**；
> **第 2 个镜头（8.73–10.10 秒）：8.92–9.68 图1中的人物：叼满再说
> （接着上一个镜头继续说）**；其余未编辑的内容保持相对稳定。

### 验过

`test_whole_wiring` **181/181**（`_span_script` 6 条断言改为 5 元组；
新增 2 条：跨切点前半截归第 1 镜、后半截归第 2 镜并带说明）｜
`test_edit_spec` 274/274｜`test_h3_shot_source` 18/18｜`test_video_edit_logic` 87/87

### ⚠️

新指令还没跑过 IR（要主人同意再花一次钱）。

---

## §30 · 2026-11-03 · **撤回"切点切开台词"**（主人判断正确：是我加的第二条规则导致的）

### 主人

> 「不对，台词的镜头是不是你刚才给了两个规则导致的？
> 你说2.1只能粗识别，那么ASR不是能精准的吗？」

### 三次实测（同一单、同一批素材）

| 版本 | 台词规则 | 4.00–6.88 那句（属第 1 镜） |
|---|---|---|
| `edb6eb707089` | 平铺 | ❌ 写进 `[Shot 2]` |
| `b3d6978179e8` | 按镜头归组 | ✅ 写进 `[Shot 1]` |
| `29e34dea87ff` | 归组 **+ 按字级时间切开** | ❌ 又写进 `[Shot 2]` |

后两次**唯一的变量就是"切开"** → 撤回。

### 事实核对（回应"ASR 不是能精准的吗"）

- 台词归镜用的是 **ASR 的字级时间**（`speech.segments[].chars[]`）+ **帧级实测切点
  8.733**；2.1 的 `8.6` 一个字都没进指令，只用它判断"这一段有几个镜头"。
- 撤回后 ASR 字级时间仍由 `_span_script` 第 5 项带出（`(字, 起, 止)`），
  只是暂不用于切台词 —— 要用先拿对照，别再直接开。

### 撤回后的指纹

`b3d6978179e8` —— **正好是 IR 归镜正确的那一版，缓存还在**
（`ir/seg_001_b3d6978179e8.txt`，2726 字节）。出片直接命中，**不再花 IR 的钱**。

### 验过

`test_whole_wiring` **180/180**（原先两条"切开"断言按撤回后的行为改为
"整句挂起始镜头 + 跨镜说明"）｜`test_edit_spec` 274/274｜
`test_h3_shot_source` 18/18｜`test_video_edit_logic` 87/87｜
`p16_check` 32/33（S3 素材问题）

---

## §31 · 2026-11-03 · **换人标记 `attribute_transfer` 是我们自己写错的 → 校准成 `fully_preserved`**

### 主人

> 「到底是不是你这个所谓的保留导致的？我上传的图草泥马的意义在哪里」
> 「傻逼，查提示词产出有没有问题啊！」

### 铁证：提示词产出里白纸黑字写着"保留原片的人"

IR 产出（指纹 `e57ad5b6967f`）原文：

```
<Subject 1> (appears in [Shot 1], [Shot 2]): attribute_transfer - <Subject 1>'s
appearance, long wavy brown hair, and purple and blue ruffled gown replace the woman
with the high ponytail and yin-yang top in <Video 1>, while retaining her placement
on the left and her actions.
```

官方 `ref-en:167`：`attribute_transfer` = 「Referenced characteristics are transferred to
**a different identifiable target subject**」
→ 主体 = 原片那位；图只提供**外观特征**。模型完全照做，所以"人还是原片的人，只被重画"。

### 统计（26 条出片记录，SFace 同人线 0.363）

| | 条数 | Subject 行写 `attribute_transfer` | 写 `fully_preserved` |
|---|---|---|---|
| 换成功 | 7 | 1 | **6** |
| 失败 | 19 | 10 | 11 |

另：把某人定义成 `<Subject N> … from <Video 1>` 的有 4 条，**全部失败**；成功样本 0 条。

### 图没丢

`request_001.json`：`ref_images = ['subject.jpg','ref_person2.jpg']`，两张都 `mm_file://`
上传成功，IR 也确实写成 `<Subject 1>` / `<Subject 2>`。
问题不在传输，在**提示词把图降级成"特征库"**。

### 改了两处

1. **指令**：不换的人不再写「保持原样」（§27 那条撤回）；换人句补一句
   「成片里出现的就是图N中的人物本人，只替换出镜人物」。
   ⚠️ 单单这句**没能说服 IR** —— 指纹 `2ff42a897cd8` 里它照样写 `attribute_transfer`。
2. **出口校准** `h3_ir._swap_marks()`：IR 产出后，把**定义里引用了人物图**的那几个
   `<Subject N>` 的 `attribute_transfer` 改成 `fully_preserved`（依据 `ref-en:165`）。
   商品/服装/场景的 Subject 不动（负样本验过：只校准图1 时，图2 的夹克仍是
   `attribute_transfer`）。

### 验过

`test_whole_wiring --model h3` **181/181**｜`p46_check --model h3` **57/57**｜
`test_edit_spec --model h3` **274/274**｜对三份真实产出做前后对比，标记 2 → 0。

### 现在死活

**活，但要重启后端才进内存。** 本单命中 `2ff42a897cd8` 缓存（**没多花 IR 的钱**），
重启后出片读到的就是 `fully_preserved` 那版。

---

## §32 · 2026-11-03 · **照抄外部跑通的实战骨架，补齐 IR 产出的三处结构**

### 来源（都是别人真跑出来的，不是我编的）

- `github.com/lshhhhhhh/ai-school-op` `docs/02-人物替换.md`
  —— 整部动画 OP 逐镜复刻，73 个单元、**生成并人工验收 118 个 H3 版本**，
  63 份最终通过的提示词在 `prompts/`。它踩的坑和我们一模一样：
  「简短自然语言提示词 → 模型几乎原样照抄原片，人没换、字没换」。
- `github.com/siyuan-liu31/minimax-h3-video-studio`
  `skills/h3-dance-replication/references/prompt-pattern.md` —— 多人换人的完整骨架。
- （`seedance.tv` 那篇用 `attribute_transfer`，与上面 118 次实测结果相反，**不采纳**。）

### 补的三处（`h3_ir._skeleton()`）

1. **每个 Subject 两截**：外观←图 + 「位置/姿势/动作←原片哪个人」
   外面成品原句：`… and whose position, pose and motion come from the tanned
   short-haired girl in <Video 1>.` —— 我们只有前截。
2. **`<Video 1>` / `<Audio 1>` 各占一行**（官方 `ref-en:37`），`<Video 1>` 带排除句：
   `It is not a source for target identity, clothing, environment, watermark, logos, or text.`
3. **summary 前缀补 `reference generation`**（官方 `ref-en:134`：图片给"角色"提供生成依据
   就是这个类型；外面成品前缀全是 `[video editing + reference generation]`）。

在 `prompt_for` 里对 IR 产出（缓存命中也算）做确定性校正，**不额外调 IR、不花钱**。

### 验过

`test_whole_wiring --model h3` **188/188**（新增 7 条骨架断言：三处补齐 / 标记校准 /
幂等 / 无人图时一字不动）｜`p46_check` 57/57｜`test_edit_spec` 274/274。
真实样本 `dad130d5` 的 IR 产出走一遍，三处全部补上，`attribute_transfer` 归零。

### 现在死活

**活，但要重启后端才进内存。** 出片后仍未换 → 按调研结论走**首帧图生视频兜底**
（外面那位一镜试 5 版都是 SSIM≈0.94，最后就是这么绕过去的），**不再往上叠规则**。

---

## §33 多角色「能指代清楚」+ 锁定脸（2026-11-03 晚）

### 为什么改

主人点破：官方飞书手册**写明了怎么更换**，别再怪模型。回头做人眼验收的分档对照：

| 档 | 换成功 / 总数 |
|---|---|
| 单人图（1 张人物图） | **8 / 19** |
| 多人图（2–3 张人物图） | **0 / 12** |

缺口**只出现在"多角色"这一档**。再去看两张人物图时的素材说明，是**逐字相同的两句话**：

```
人物参考图1提供了人物的形象；人物参考图2提供了人物的形象；
```

IR 无从知道图1对应画面里哪一位，产出的定义只剩外观的一个碎片：

```
<Subject 1> is the character with long, wavy dark hair in <Picture 1>,
and whose position, pose and motion come from the performer on the left in <Video 1>.
```

**全句没有一个字说"脸来自图"**。原片那位同样是长深色头发 → 描述两边都成立 →
模型最省力的解就是留着原片那张脸，只把服装/发型换掉（= 12 次失败的一致失效模式）。

### 依据哪一行

- `manual-2026-10-28.md:248`（1.2 四个要素如何描述 · 参考素材说明）原文：
  「@图片1 提供了xx角色的形象（**如果有多个角色，需要能指代清楚**）」
- 同一段用途词表：「**人物参考** → 锁定脸/形象」
- 同一段写死的第 1 条建议：「如果素材中有非常想要保持的特征，**建议明确写出来**，
  这样可以让一致性更好」
- 官方模板 `ref-en.txt:57`：
  `<Subject 1> is the woman whose appearance comes from <Picture 1> and whose walking motion comes from <Video 1>.`

### 改了什么（`h3_ir.instruction()`，一处）

`len(person_pics) >= 2` 时，把每张人物图的素材说明改写成：

```
人物参考图1提供了视频1中左边黑色高马尾长发、额间有红色痣那位的形象，锁定这张脸
```

- 方位 + 可辨识特征来自 2.1 盘点（`ppl_all`），不是我编的；
- **单人那一句一个字不动** —— 8/19 已经能成，不拿它一起赌；
- 盘点缺方位也缺长相时退回「一位人物」，不许出现空「那位」。

### 拿什么验过

- `test_whole_wiring --model h3` **191/191**（新增 3 条：图1指左边 / 图2指右边 / 单人不动）
- `p46_check --model h3` **57/57**
- `test_edit_spec --model h3` **274/274**
- 零费用回放 `D:/tmp/ir_abc/check_multiperson_materials.py`：两人版 / 单人版 / 缺信息兜底 三种输出逐条贴出比对

### 现在死活

**活，但要重启后端才进内存。** 指令改了一个字 → 指纹变 → **必然是一次新的 IR 调用**
（不是缓存命中）。IR 产出没验过，出片也没验过。

### §33 补充（2026-11-03 晚 · 第一次调 IR 后的实况）

调了一次 IR（指纹 `8d73580c278a`，付费 1 次），产出**暴露三个问题**：

1. **我那句写错了。** 第一版写「图1提供了视频1中左边黑色高马尾长发、**额间有红色痣**
   那位的形象」——「红痣」是**原片那位**的特征（`inventory` 的 P1），图1本人是
   「深棕黑大波浪、无红痣」（`subject_desc.json`）。IR 原样吸收成
   `<Subject 1> is the long-haired woman with a red dot on her forehead from <Picture 1>`
   —— 等于告诉模型"这张图就是原片那个人"，比改前更糟。
   → 改为**只写方位**：`人物参考图1提供了视频1中左边这个角色的形象，锁定这张脸`。
2. **`_skeleton` 位置半句挂错。** IR 把 `<Video 1> is …` 夹在 Subject 段中间，半句
   被接到 `<Video 1>` 上，Subject 2 反而没有位置来源。→ 先剔除行内 `<Video 1>/<Audio 1>`
   定义，半句只挂到本 Subject 定义末尾（遇下一条 `<Video N>/<Audio N>` 即断开）。
3. **`<Video 1>` 没单列、缺排除句。** → 统一按 `ref-en:37` 单列，带排除句。
   （删定义时行尾只吃空格不吃换行，否则 `summary:` 会被粘到上一行；`lstrip` 保证幂等。）

验：wiring **192/192**（+1 条"素材说明不许出现原片那位的长相特征"）｜p46 57/57｜
edit_spec 274/274｜真实 IR 产出 `8d73580c278a` 走校正后，三处全对、幂等 True。
**但 (1) 的修正还没被 IR 消费过 —— 要再调一次 IR 才能看到真正的成品。**

---

## §34 第二次调 IR + 两处机械校正（2026-11-03 深夜）

### 结果：指令改对了

`人物参考图1提供了视频1中左边这个角色的形象，锁定这张脸`（第二次指纹 `cfb9c0ed9e77`）之后，
`<Subject 1>` 终于描述的是**图里的人**：

```
<Subject 1> is the woman in <Picture 1>, featuring long wavy dark hair, a deep V-neck
purple dress with a high side slit, and delicate features, and whose position, pose and
motion come from the performer on the left in <Video 1>.
```

对照第一次（错的那版）：`the long-haired woman with a red dot on her forehead from
<Picture 1>` —— 红痣是原片那位的。**"图的素材说明里不许出现原片长相"这条坐实。**

### 这次产出还剩两处机械错，已确定性校正（不花钱、不改内容）

| 错 | 官方出处 | 校正 |
|---|---|---|
| `[Shot 1] At 00:00.000, the scene…` | `base-en.txt:86`「**Do not add a timestamp to the first shot**」 | 删掉第一镜时间戳，首字母大写 |
| `[Shot 2] At 08.730` | 同处示例 `[Shot 2] At 00:03.500`（分:秒.毫秒） | 补成 `At 00:08.730` |
| 台词「水缸**挑**满」 | `manual-2026-10-28.md:248`「人声对白…**强烈建议补充具体歌词文本内容**」（我们给的就是原文） | `_restore_lines()`：`<d>[Chinese] …</d>` 与 ASR 原文差 ≤2 字时还原 |

新增函数：`_lev()` / `_shots()` / `_restore_lines()`，在 `_skeleton()` 末尾按序执行。

### 验过

wiring **192/192**｜p46 57/57｜edit_spec 274/274｜真实产出 `cfb9c0ed9e77` 校正后
四条断言全 True、幂等 True。

### 现在死活

**活，但要重启后端才进内存。** 出片未验证。共花 IR 两次（`8d73580c278a` 作废、
`cfb9c0ed9e77` 这份是最终要用的）。

---

## §35 出片 `91977d66` 实测：只换了女的裙子（2026-11-03）

### 事实（逐帧比对，不是指标）

| 人物 | 原片 | 成片 | 变化 |
|---|---|---|---|
| 左·女 | 白色抹胸（阴阳图案）+ 黑色百褶裙 | 紫色深V印花长裙 | **只换衣服，脸没换** |
| 中·男 | 灰色立领长衫 | 灰色立领长衫 | 没要求换，正常 |
| 右·男 | 深蓝立领盘扣短衫 + 腰后短刀 | **一处没动**（脸/头发/衣服/刀/口袋全同） | **该换的没换** |

放大裁图对比：`D:/tmp/audit/man_orig.jpg` / `man_gen.jpg`。

### 根因：提示词里没有任何辨别人物的"差异"

```
<Subject 1> … featuring long wavy dark hair, a deep V-neck purple dress …, and delicate features
<Subject 2> … wearing glasses, a dark jacket over a striped top, and holding a dark bottle
```

- 女的：裙子描述与原片（白抹胸黑裙）**完全不同** → 模型照做
- 男的：`dark jacket` 与原片那位的深蓝立领外套**文字上重合** → 模型判"无需改动"
- 两人：**通篇零个五官**

### 关键证据：定妆照文字根本没进提示词

出片请求快照 `triage/request_001.json`：

```
"subject_look": {"used": false, "text": "精致鹅蛋脸，柔长眼型，高挺鼻梁，饱满淡红唇形，无眼镜…"}
```

→ 图**是**拿到并上传了（IR 产出里有图1的紫裙、成片真穿上了），
但**没人告诉模型这两张脸要换上去**。它能自主挑的只有服装和发型。

### 改了什么

`h3_ir.instruction()`：`len(person_pics) >= 2` 时，素材说明带上该定妆照自己的五官
（`looks[slot]`，来自 `subject_desc*.json`，一个字不改）：

```
人物参考图1提供了视频1中左边这个角色的形象（精致鹅蛋脸，柔长眼型…），锁定这张脸
```

单人档不动。依据仍是 `manual-2026-10-28.md:248`。

### ⚠️ 指标本身的坑（写下来免得再被骗）

`subject_look.used` 是按「原文是否出现在**最终提示词**里」判的，而 IR 会把中文翻成英文
→ 改完之后它**仍可能显示 `false`**，但这不代表没生效。看这条灯会再次下错结论。

### 验过

wiring **193/193**（+1 条「多角色素材说明带五官」）｜p46 57/57｜edit_spec 274/274。

### §35 补：带五官重调 IR（指纹 `88d46d3c8649`）

两份 Subject 都写上了五官（英文由改写器翻译）：

```
<Subject 1> … characterized by a refined oval face, slender eyes, high nose bridge, full
light red lips, and deep brown-black long wavy hair, wearing a slim-fit one-shoulder …
<Subject 2> … characterized by a square-round face with a receding hairline and thinning
hair, wearing shallow transparent fine-framed glasses, with gentle brows, a wide nose,
and thin lips, appearing approachable, wearing …
```

机械项复核：`[Shot 1]` 无时间戳 ✅｜`[Shot 2] At 00:08.730` ✅｜台词「叼满」保住 ✅｜幂等 True。
⚠️ **必须重启后端**，否则进程里还是旧 `instruction()`，算出的指纹对不上这份缓存，会当缓存未命中**再调一次 IR**。

### §38 🌍 外部调研：别人到底怎么用 H3 换人（2026-11-03 15:40）

> 主人令：「出去查看别人到底是怎么用 H3 模型实现换人换脸这些操作！查仔细一点」
> 下面每条都带出处；**没写"实测"的都是别人写的**。

**路线 A —— 专用 recast 端点（不是提示词换人）**
- fal `minimax/h3-max/recast`：`video_url` + `reference_image_urls`（1–4 张，**默认按左到右对应画面里的人**）
  + 可选 `prompt`（只用来写"谁对哪张图"）+ `resolution`(768P/1080P) + `seed`；**保留源音**。
- schema 原话：*a reference photo replaces its person in **all the shots where that person appears***；
  源片 5–30s、**单个镜头 ≤15s**。
- ⚠️ MiniMax 官方 `platform.minimaxi.com` **没有**公开这个端点，目前只在 fal / venice / layer / makeugc 这类托管上有。
  出处：<https://fal.ai/learn/tools/how-to-make-a-character-replacement-video>、<https://fal.ai/models/minimax/h3-max/recast/api>

**路线 B —— Ref2VA 六段式 + 身份迁移写法（我们现在这条路）**
- `siyuan-liu31/minimax-h3-video-studio` 的 `identity-migration` 规范（**最具体的一份**）：
  1. **原片的人建 `<Subject 1>`、图里的人建 `<Subject 2>`**（我们是反的：只有图里的人有号）
  2. 方向写两遍：`<Subject 2> completely replaces <Subject 1>; the reverse must never be implied.`
  3. `<Video 1>` 只当**非身份**来源：动作/姿势/时序/机位/构图/环境/光
  4. retention 专用词：`<Subject 1>: identity_not_preserved`（脸/发/身形/衣服/颜色全去掉）、
     `<Picture 1>: fully_referenced`、`<Subject 2>: identity_fully_preserved`、
     `<Video 1>: fully_preserved for …（只列表演与场景，明确排除身份）`
  5. `detailed_description` **在 0.00 秒就锚定目标身份**
  6. 🚫 **禁止**给源实体用 `attribute_transfer`，禁止给要严格跟随的源视频用 `partially_preserved`/`weak_reference`
- `seedance.tv` 的中文模板（另一份独立来源）同样给原片人建 `<Subject 2>`，写「将 <Subject 2> 替换为 <Subject 1>」，
  retention 用 `<Subject 1>: attribute_transfer`；还要求写 **替换契约**（目标/范围/身份来源/源结构/音频/交付），
  禁写「替换那位女性」这种模糊指代；**源片 5–8 秒、只含一次运镜**最好。
  出处：<https://www.seedance.tv/zh/blog/minimax-h3-character-replacement-workflow>
- `akatz-ai` 的 LoRA 示例（最简短可用）：`Replace the selected person in <Video 1> with the character in
  <Picture 1>. Keep the reference character's face, hair and clothing. Follow the source performance's pose,
  gaze, expression and movement. Preserve the scene and the other people.`

**路线 C —— 专用 LoRA + 掩码（社区最稳的做法）**
- `akatz-ai/MiniMax-H3-Character-Swap-LoRA` V1.5（strength 1.0）；`Alissonerdx` 还有 **head_swap LoRA**
  （只换整个头、保留身体与衣服），输入必须走两条不同通道：脸图 → 原生参考图通道；原片 → `AddGuide`(frame_idx=0)。
- 结论：**换人这件事社区是"微调 + 掩码"做出来的，不是靠提示词**。

**四条我们跟别人不一样的地方（都可指到出处）**
| | 别人 | 我们 |
|---|---|---|
| 原片的人 | 建 Subject + 明确"身份不被保留" | 不建号，只写"位置来自原片" |
| 五官描述 | joeygambino 实测：写身份句 → 渲出另一个人；改成 `looks exactly as in the reference photographs` → 就是参考图本人（同 seed 对照） | 把五官/气质/穿搭全写进 `<Subject N>` |
| 片段长度 | 逐镜 2–8 秒、单镜单跑 | 一次 10.1 秒含切点 |
| 参考图 | 头肩特写；MacroSony 明确"只有全身图，特写会失败" | `subject.jpg` 是全身走秀图，脸很小 |

**两个机制性发现**
- **抽卡是真实存在的**：`MacroSony` 的 LIMITATIONS 原话 —— 同工作流同提示词、**只换 seed**，
  可能"output == source（完全没换）"，也可能换对；官方 API 无 `seed` 参数，只能重跑。
  <https://github.com/MacroSony/minimax-h3-chained-character-swap/blob/main/references/LIMITATIONS.md>
- **音轨参考可能压身份**：HF 讨论 #91（本地部署）Ref2VA 带音频参考时 InsightFace 余弦掉到 0.07–0.09，
  FL2VA 纯视觉是 0.8855。我们每次都挂 `<Audio 1>` —— 值得做一次**去掉音频参考**的对照。
  <https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/91>
- **外观相近/人物小/快速推拉**：模型会以为"已经换好了" → 写**对比句**（原片什么样 → 换成什么样）。
  <https://github.com/lshhhhhhh/ai-school-op/blob/main/docs/02-人物替换.md>

### §37 🩸 **回归实锤：同一条源片、同两张图、同 Lite/480P，昨天两个人都换成了**（2026-11-03 15:30）

主人问「那为什么上次一个人就换成了」—— 查出来不是单人/多人的差别，是**提示词回退了**。

> 🔧 **2026-11-03 15:35 主人纠正 + 逐帧复核**：昨天那单**只有片尾几秒换了**
> （1.0s / 5.0s 两张脸都没动，只换衣服；8.0s 男的换了；8.8s 两个人都换了；
> `share=0.154` 就是证据）。所以下面"两个人都换成了"只对**最后一个镜头**成立，
> 不是整片成功 —— 我先前只看 `best_sim` 没看 `share`，夸大了。

**同一份素材**：`1b3df54b…` 与 `dad130d5…` 的 `source.mp4` md5 完全相同
（`8c26773e7b1042842a07b32f3cef49ce`），参考图同名同槽位（`subject.jpg` / `ref_person2.jpg`），
`person_ids` 都是 `['P1','P3']`，都是 `MiniMax-H3-Lite` / 480P / `audio=original`。

| | 昨天 2026-11-02 08:53 `b35fc8a9` | 今天 `54255690` / `1583f944` |
|---|---|---|
| 女的 SFace | `best_sim 0.475` verdict **swapped** | 0.177 / 0.194 |
| 男的 SFace | `best_sim 0.67` verdict **swapped** | 0.196 / 0.164 |
| 人眼 | 女的换了脸+杏色裙；男的换了人+黑 T | 两张脸原样 |

**差在哪（逐行 diff 两份真实请求，`diff_prompts.py` 可复现）**：

| 层 | 昨天（成） | 今天（败） |
|---|---|---|
| `<Subject N>` | `is the woman in <Picture 1>, **serving as the character replacement for the woman on the left in the source video**` | `is the female character in <Picture 1>, characterized by …, **and whose position, pose and motion come from the performer on the left in <Video 1>**` |
| 未换的人 | `<Subject 3> is the young boy in <Video 1> …`（单独建号） | **没建** |
| retention | `<Video 1> (source-video editing): **partially_preserved** … replaced by <Subject 1> and <Subject 2>` | `<Video 1> … **fully_preserved**` |
| 分镜描述 | 逐个 `On the left stands <Subject 1>, **replacing the original woman**` | **一次都没出现 "replacing"** |

那句 `whose position, pose and motion come from the performer …` **是我们自己注入的**
（`_skeleton()` 的位置半句，§32 照外部 `ai-school-op` 骨架加的），
它把 IR 原本的 **character replacement** 语义顶掉了 —— 模型读到的是「这个人站在左边」，
不是「这个人**替代**左边那位」。

**结论**：不是模型、不是档位、不是单人多人，是 §32/§33 那一串改动把「替换」写没了。
基准件已在盘上：昨天的 IR 输入 `1b3df54b…/ir/seg_001_1c7c8247b82f.in.txt` 和
成品 `render/b35fc8a9…/triage/request_001.json`（5279 字）。

**下一步（待主人拍板）**：先拿昨天那份成品提示词原样 force 发一次（单一变量：提示词），
成了再回退代码；不成就说明还有别的东西（今天 2 镜 / 10.1s vs 昨天 1 镜 / 9.233s）。

### §36 中文直发 + `<Picture N>` 实测（2026-11-03 15:21，主人授权我代发）

**为什么测**：API 侧引用标号是 `<Picture N>`（`ref-en.txt:60-80`），`@图片N` 只存在于
网页手写入口（`manual:248`）。所以上一版中文直发（`d74bf43c`）**根本没测到"中文直发"**
—— 那一版发出去的 `@图片1` 在 API 里就是一段无意义文本。

**怎么测的**：
- `data/clone/dad130d5…/direct_prompt.txt`（323 字，中文，`<Video 1>/<Picture 1>/<Picture 2>/<Audio 1>`）
  经 `h3_ir.prompt_for` 顶部的临时旁路**不经改写器**直发；
- `force=true` 绕过逐段缓存（缓存键在 `video_edit.py:2422` 由**编译后的提示词**算出，
  `prompt_for` 在 2479 才调用 —— 不 force 就永远读不到直发文件）；
- 渲染 `1583f9448ea64899bfde3fccd6fda1b4`，`MiniMax-H3-Lite` / 480P / 2 张参考图 /
  `role=reference_image`（`minimax.py:495-497`）/ 全片 1 段 10.10 秒。

**核对**：`triage/request_001.json` 的 `prompt` 与 `direct_prompt.txt` **逐字相同**（323/323，
True）。所以这一次是真的发出去了，不是又被改写。

**结果：两张脸都没换。**
- 人眼：第 1 镜、第 2 镜的男女主角，五官、发型、服装全部与原片一致；只有表情/口型/呼吸
  有重新生成的痕迹，原片字幕被去掉（说明模型确实重绘了整片）。
- SFace：person `best_sim 0.194` / person2 `0.164`，阈值 `0.363`，`share 0.0`
  —— 与六段式那一版（0.177 / 0.196）没有差别。

**结论**：体裁（六段式英文 / 中文自然语言直发）**都不是瓶颈**。
两条路一共 32 次多人出片，0 次换成功。

**还没排除的两项**（下一轮一次只动一个变量）：
1. **档位**：`MiniMax-H3-Lite`（轻量版，480P/768P，无 2K、无 adaptive）。官方文档没有
   任何"换人能力弱于标准版"的说明，但也没有正面说明支持多主体换人。
2. **参考图本身**：`subject.jpg` 是**全身走秀图**，脸只占画面很小一块；`ref_person2.jpg`
   是大头照（脸够大）。两张都没换 —— 说明"脸太小"不足以单独解释，但可能是压垮
   `subject.jpg` 的那一根草。

**🩸 请求体的坑（已踩）**：`RenderIn.edit` 是**扁平**的 `EditIn`（`person/person_ids/audio/…`），
`task.json` 里存的是**归一后**的嵌套规格（`change/keep/…`）。回传嵌套版时 pydantic
**静默丢键** → `person=False` → 整片重绘逻辑根本没进，5 秒出片（`2753c776`，未调模型）。
回放旧任务必须先把嵌套规格压平。

---

### §39 🧊 复刻爆款下架 H3（2026-11-03 16:xx，主人要求）

**边界**：下架的是**复刻爆款的入口**，H3 的提示词 / IR / 六段式**一条规则都没动** ——
提示词优化那条线照常用。出处：主人原话「复刻爆款H3下架……不要去动的H3模型优化提示词」，
同 2026-10-31 下架 2.0 时的口径（[[decommission-scope-is-feature-not-model]]）。

**改动（5 处，每处有出处）**

| 文件 | 改什么 | 出处 |
|---|---|---|
| `models/h3.py:239` | `frozen=False` → `True` | `ff78059`（2026-11-01 冻结）原样做法 |
| `model_specs.py` `MODELS["minimax"]` | 四档注释掉 | `85a708d` 解冻 diff 的反向；`SPECS` 四档**一字未动** |
| `video_edit.py:271` `pick_channel` | auto 循环跳过 `frozen_families()` | 见下「旧洞」 |
| `frontend/.../diagnose.vue:1505` `effChannel` | 自动分支先看 `models` 里还有没有 minimax | 同文件 `:1282` 已确立「单一真相源是 `MODELS`」 |
| `.model-lock.json` | `h3` → `volc25` | `ff78059` 冻结时同步改过 |

**🩸 发现的旧洞（`ff78059` 冻结时没堵上）**：`pick_channel` 的 `auto` 只按
`Caps.auto_prefer` + `ready()`（查 API key）排序，**不看 `Caps.frozen`**；
`clone.py:1510` 调用它时只要不抛 `EditError` 就继续。于是「通道=自动 + 传本地人物图」
→ auto 选中 minimax → `regen_model_error` 只看得到 `ask="auto"`（不在冻结名单里）
→ **照样出 H3 的片**。本次用现成的 `frozen_families()` 补上，核心文件不写厂商名。

**连带修（判据，不是功能）**：`p4_check.py` 的夹具原来写死「20s 素材 = 2 段」。
20s 在 H3（15s 上限）下切 2 段，在火山（30s 上限）下只有 1 段 → A1/A5/B1 假红，
A5 还会退化成空转（复用恒为 0，没有鉴别力）。夹具改成 **40s**（火山 2 段 / H3 3 段），
A5/B1 的期望值改成 `len(spans) - 1`。`test_video_edit_logic.py:118` 的
「auto 本地人物图 → MiniMax」改成按 `frozen_families()` 动态断言。

**验证（全部零成本）**：`test_video_edit_logic` 87/87 · `test_model_specs` 60/60 ·
`p11_check` 28/28 · `model_registry_check` 14/14 · `p4_check` 23/23。
离线三条：`frozen_families()==['minimax']`｜`MODELS["minimax"]==[]`｜
`pick_channel('auto', file)=='volc'`｜`regen_model_error('MiniMax-H3')=='这个型号暂不可用'`｜
四档 `SPECS` 仍可查（768P/2K、480P/768P 原样）。
`p16_check` 的 `S3`（SFace 中位 0.567）**改动前就是红的**，已用 stash 对比确认，与本次无关。

**现在死活**：代码已改；**后端要重启才生效 —— 按规矩主人自己重启**。

---

### §40 🔎 官方 API 里那个"在原片上重画"的入口找到了：`/v2/video_regeneration`

**来源**：`data/official/h3/pull-2026-11-02/api_v2-regeneration.md`（516 行）。
之前一直漏读——只读了同目录那份只覆盖 `/v2/video_generation` 的 OpenAPI JSON。

**关键事实**
- `role=base_video`（`:359`）：**拿一条 768P 源片当底重画**；`content` 中必须且只能有 1 个。
- `base_video` **可以**和 `reference_image` 同时出现 —— 互斥规则只禁
  `reference_image` 与 `first_frame`/`last_frame` 混用（`api_v2-create.md:213`），
  参考图最多 9 张（`:239`）。
- 官方示例本身就是**改内容**：`:103` 的 text 是
  `Pull focus to the people in the background and add more steam to the ramen bowl.`
  —— 不是原样超分。`:130` 还有 `reference_video + reference_audio + base_video` 的组合示例。

**源片规格**（`:186` 表格）：必须有音轨 / **24 fps** / 宽高各被 32 整除 /
面积 589,824–1,032,192 / 总帧数 107–362（每档 +17，约 4–15 秒）。

**我们这条原片**（`dad130d5…/source.mp4`）：1024×576（面积 **589,824，正好等于下限**）、
30 fps、303 帧、10.1 s、AAC 有音轨。→ 只差**帧率 30→24** 和**帧数落到 243（107+17×8）**。

**风险**：文档 `:13` 写「不支持任意视频的通用处理」、`:186` 要求「原样提交生成时的全部输入」，
但 schema 不校验。服务端会不会因「这条源片不是本账号 H3 生成的」而拒，**只能实跑才知道**。
代码里**尚未接线**（`app/` 全目录 grep `regeneration` = 0 处）。

---

### §41 🧊 H3 从复刻**永久移除**：执行链归档（2026-11-03，主人改口「不打算再接入」）

§39 只关了入口、保留了解冻开关。主人随后明确「**不打算再接入 H3 模型的了，该清理就清理**」，
并按「连编译器一起抽」拍板。处置原则照 2026-10-31 下架 2.0 那次：
**`git mv` 归档，不删文件**，随时可回滚。

**归档到 `backend/_archive/h3_clone/`（10 个文件）**

| 文件 | 是什么 |
|---|---|
| `h3_ir.py` | H3-Context-IR 改写器（出片逐段产词） |
| `h3_agent.py` | 逐段指令 agent（预览/对照） |
| `minimax.py` | H3 API 客户端（`reference_video` / `context_ir` / `upload_file`） |
| `h3_compile.py` | 六段式编译器（Ref2VA 改片） |
| `ruler_h3.py` | Ref2VA 尺子（23 条）—— 靠 `h3_compile` 校验，所以一起走 |
| `p46_check.py` / `p58_check.py` | 复刻逐段指令 / 先出一段的判据 |
| `test_edit_spec_h3.py` / `test_h3_shot_source.py` / `snap_cases_h3.py` | 复刻侧自检与用例 |

目录里附了 `README.md`：依赖图 + 「接回来要改哪 6 处」+ 「不许把规则搬进 `h3_base`」。

**`models/h3.py` 改成墓碑**：只保留型号识别（`MiniMax-H3` 四档仍归 `minimax` 家族）、
`Caps.frozen=True`、`ready()=False`；出片相关可调用项全部指向 `_gone()` 抛错。
不再 import 任何已归档模块。

**连带改的 8 个脚本**（都只是去掉 H3 那一半，火山侧照跑）：
`check_all.py`（删 h3 主尺 + 镜头来源 + p46 + p58 四条，`RULER["h3"]` 改指 `ruler_h3_base`）·
`test_whole_wiring.py`（删 MiniMax 段 576 行 + 口型音频 H3 段 + 双人 H3 段，共 706 行）·
`p12_check.py`（删 S6 与 S8 的 H3 断言）· `p19_check.py`（E 段只剩 base 尺子）·
`brief_golden_check.py`（基线只剩 2.5）· `rehearse_render.py` / `test_auto_render.py`（去 minimax 桩）·
`prompt_fingerprint.py`（本地内联夹具取代 `ruler_h3._people`）。
另有 4 张映射表去掉 `h3` 键：`prompt_snapshot.CASE_MODULES` / `test_edit_spec.MODELS` /
`ruler_atoms.MODELS` / `recheck_real_prompts._MOD`。

**产品代码只动两处**：`model_specs.MODELS` 删掉整个 `"minimax"` 键（`SPECS` 四档**没动**，
历史任务仍能查档位）；`h3_convert_route.GUIDES["ref"]["ruler"]` 置空（运行时从不 import 尺子）。

**提示词优化一行没动**：`h3_base` / `h3_base_compile` / `h3_common` / `h3_ref` /
`h3_skill` / `h3_direct` / `h3_convert_route`（除上面那个字符串）全在原地，
`app/api/prompt.py` 的 import 一条没改。

**验证**：`test_whole_wiring` **76/76** · `p12_check` **47/47** · `p19_check` **31/31**（`--force` 跨型号）·
`brief_golden_check` 13 份逐字一致 · `test_video_edit_logic` **87/87** · `test_model_specs` **59/59** ·
`p11_check` **28/28** · `model_registry_check` **14/14** · `test_vision_plan` **42/42** ·
`p4_check` **20/20（跳过 1）**。
`check_all --model volc25` 全量结果见下方 §41.1。

### §41.1 归档后发现的两处「判据跟着被测对象一起下线」

全量自检跑出来两个红，都不是产品坏了，是判据还在验已经不存在的东西：

| 位置 | 红什么 | 怎么处理（出处） |
|---|---|---|
| `scripts/test_vision_plan.py` | 「提示词」段里 9 条 H3 断言要 `_span_prompt` 走 H3 编译器 → 墓碑抛 `_GONE` | 整段删掉，留注释指向 `_archive/h3_clone/README.md`。**火山那 5 条不动** |
| `scripts/p4_check.py` C0–C3 | 拿**最新一条真跑**回放：`regen_channel="minimax"` → `pick_channel` 按入口下架拒绝 | 改成「跳过走已下架通道的真跑，换下一条仍在用的；全都没有就 `chk(..., None, ...)` 明说跳过」。本机 22 条真跑**全是 H3**，所以实跑是 SKIP —— 看得见的跳过，不是假绿 |

`p16_check` S3（SFace 不同人素材中位 0.567 > 0.363）是**既有红**：用 `git stash` 对比过，
下架前同一条就红，与本次改动无关，另行处理。

**全量总账**：`check_all --model volc25` → **通过 50 ｜ 跳过 1 ｜ 红 1**（101.0s）。
唯一红 = 上面那条 p16 S3；跳过 1 = 「人像外观·型号闸：不归本轮」。
同一套上一轮是**红 3**（视觉盘点 / p4 静帧 / p16），前两个已在上表修掉。

**要接回来**：按 `_archive/h3_clone/README.md` 六步走。

---

## §42 🔓 **H3 复刻换体裁：Ref2VA 六段式 → 手写入口三段式**（2026-11-03 夜）

**为什么改**（主人原话）：「H3**一定有的**，所以我叫你删除干净，然后再像 2.5 这样走导图」／
「**不是他的就不要串啊**」／「你修好 H3 的就行了，我自己测」。

根因不是"提示词写得不够好"，是**体裁选错**：官方换人样例 **6 条全在手册**
（`h3-manual:207-213` / `:185-192`），全是自然语言短句；`ref-en` 六段式里
**一条换人样例都没有**（唯一那份 `ex-lamb` 是口型重做）。照着没有样例的体裁推整段，
就是 10–11 月那 26 次出不了片的那条路。

| 项 | 改前 | 改后 |
|---|---|---|
| 编译器 | `h3_compile.py`（Ref2VA 六段式，`<Subject N>`/`<Picture N>`） | **`h3_compile.py` 换名顶位**，正文是 `handwrite()`（`@图片N`，中文） |
| 旧文件 | 就地 | 归档 `_archive/h3_clone/h3_compile_ref2va.py` |
| 尺子 | `ruler_h3.py`（E1–E23） | `ruler_h3_handwrite.py`（H1–H6）；旧尺子归档 |
| 中译英钩子 | `_pre_compile` 自动翻英文 | **改成 no-op**（手写入口本身就是中文） |
| 路由 | `h3_convert_route.GUIDES["ref"]["ruler"] = ruler_h3` | 指向 `ruler_h3_handwrite` |
| `check_all.RULER["h3"]` | `ruler_h3` | `ruler_h3_handwrite` |

**依据（每条都指到行）**：`:244`（三段公式）· `:248`（素材用途表 + 「非常想要保持的特征建议明确写出来」）·
`:192`（多人替换官方样例）· `:213`（点名换人/换装）· `:234`（换产品）· `:221`（换场景）·
`:266`（首帧参考图）· `:41`（≤7000 字符）。

**这一轮顺手补的四个真缺口**（不是重构，是换体裁时暴露出来的）：
1. **边界续接没落点** —— `work.py` 仍传 `boundary_pic`，手写入口原来直接丢掉 →
   第二段会从原片开头重来。现按 `:248`「关键帧（锁定帧）」写进用途句，正文首句
   `画面从@图片N定义的首帧自然开始。`（`:266` 排布）。
2. **参考图外观描述没落点** —— `subject_look/subject_looks` 原来只喂六段式 →
   现挂在用途句括注里：`@图片1 是人物参考，锁定…的脸和形象（黑色短发，白色衬衫）。`
   （`:248` + `:264` 的括注写法）。**写 zh**，快照 `_look_text` 才记得对。
3. **九宫格四角丢了** —— `_POS_ZH` 只有 left/right/center/top/bottom/foreground/background，
   缺 `top-left/top-right/bottom-left/bottom-right` → 盘点给四角时会退化成泛称。
4. **一句话都没有时的指名** —— 有图、有 `person` 勾选、但盘点为空时，原来整段不写
   （`@图片N` 都不出现）；现退回图号点名。

**拿什么验过**：`check_all --model h3` → **通过 53 ｜ 跳过 3 ｜ 红 2**。
两红：`p16 S3`（既有红，SFace 阈值，与本次无关）、`提示词逐字检查`（改完再跑已归零，
见下）。逐项：`prompt_lint 1930/1930` · `prompt_model_standards 23/23` ·
`identifiability 84/84 抽取成功、三闸与输出全一致` · `p9 34/34` · `p10 36/36` ·
`test_edit_spec 50/50` · `test_person_refs 3/3` · `test_subject_look 21/21` ·
`ruler_h3_handwrite` 探针 7/7、校准 11 组 0 破口、扫描 6 组 0 破口、穷举 6 开关 0 破口。

**现在死活**：✅ 机械侧全绿；**没有出过片**（出片＝主人自己点）。
下一轮若要验，先跑一条 Lite/480P 看换人是否成立，再上 1080P。

**判据跟着换的地方（不是放宽）**：`prompt_lint_check` / `prompt_model_standards_check` /
`identifiability_check` / `p9_check` / `p10_check` / `test_subject_look` 里原来锁
`<Subject N>`、六段字段名、`(Sx)` 说话人号、`upper/lower part` 的断言，
全部改成手写入口的字面；**并加了反向守卫**「六段式/别家模板句不许回流」。
`p10 C3–C9`（H3 说话人绑定）整组改写成「复用原声」—— 主人 2026-11-03 拍板
「让模型沿用原声」，手写入口手册里也没有「音色绑到某主体」的句式。

## §43 🩹 **加回「其余按@视频1原样」**（2026-11-03 深夜 · 单变量修复）

| 为什么改 | 依据哪一行 | 拿什么验过 | 现在死活 |
|---|---|---|---|
| 换体裁时把「其余按原片」这条约束丢了 → 真跑 `81633d37` / render `d7a7dc93` 开头约 2.6s 被重画成**参考图所在的城市街拍**，之后才对上原片。同档（Lite）、同拼接、带这句的 `dad130d5` / `1583f944` 全程 1:1 对齐（逐帧灰度高差 11–14 vs 22–57） | `h3-manual:133`「…必须保持 100% 不变」· `:206`「准确执行局部修改…同时**保持未编辑内容相对稳定**」· `:248`「**以及其他要求也可按需写明**」 | `prompt_lint 1930/1930` · `standards 23/23` · `identifiability 三闸全一致` · `p9 34/34` · `p10 36/36` · `test_edit_spec 50/50` · `subject_look 21/21` · `person_refs 3/3` · `ruler --current 11 组 0 破口` · `check_all --model h3` **54 通过 / 3 跳过 / 1 红**（红=p16 S3 既有） | ✅ 代码已落；**未出片**（出片＝主人自己点）。需重启后端才生效 |

**这一刀只改一处**：`h3_compile._KEEP_ITEMS` + `_keep_line()`，插在正文 ⑨（风格之后、extra 之前）。

**措辞逐字对齐已跑通的旧版**：`人物、动作、台词、站位、机位、分镜、场景、光线、口型都按<Video 1>原样`
→ 只把 `<Video 1>` 换成手写入口的 `@视频1`，项表一个不多一个不少。
**没有**加「除了上面点名的改动」之类前缀 —— 那是自作聪明，会变成第二个变量。

⚠️ **未决第二变量**：`subject_look.used=True`（把整段形象描述写进用途句，`:248`+`:264` 括注）。
旧版跑通时 `used=False`。若本条加回后仍出现开头重画，下一步单独撤它，别一起改。

## §44 🏗️ **正文改回官方三段公式 + 逐条点名的换人句**（2026-11-04）

| 为什么改 | 依据哪一行 | 拿什么验过 | 现在死活 |
|---|---|---|---|
| 真跑 `f35fadf`（双人）**只换了衣服、脸一点没动**：SFace `person 0.19` / `person2 0.258`（阈值 0.363）；同一张参考图在上一次 `81633d37` 换到了 `0.71`。查下来正文是**一整段无标题自由文字**，替换句和「人物…都按@视频1原样」对冲 | `h3-manual:244` 三段公式 · `:213` 精准换人（`视频1中最后面的小孩换成 图1中的金毛狗`）· `:192` 三句保持 · `:250` 核心创意 · `:251` 画面过程说明 | `check_all --model h3` **54 通过 / 3 跳过 / 1 红**（红=p16 既有）· `lint 1930/1930` · `standards 23/23` · `p9 34/34` · `p10 36/36` · `test_edit_spec 50/50` · `ruler 探针 7/7、当前产出 11 组 0 破口` · `identifiability 三闸全一致` | ✅ 机械侧全绿；**未出片**（出片＝主人自己点），需重启后端 |

**结构变化**（一段 → 三段）：

```
【参考素材说明】   ← 不变（`:248` 用途句）
【核心创意】       ← 只放「改什么」，一条改动一句
【画面过程说明】   ← 只放「怎么动、怎么保」，`:192` 两句
```

**删掉的三处**（都不是 H3 的写法）：
1. `人物、动作、台词、站位、机位、分镜、场景、光线、口型都按@视频1原样。`（§43 加的）
   —— 句首「人物」和替换句对冲；「站位」在 H3 官方全库 **0 次**（2.5 里 20 次）。
2. `画面右侧的人物保持原样。` —— `:213` 只点名"换谁"，不说"其余别动"。
3. `参考视频1做人物替换。` —— 自造前缀（`:192` 的「参考视频1进行**动作模仿**」是动作参考任务）。

**改掉的两处用词**：
- 动词 `替换为` → **`换成`**（`:213` 逐字）
- `原片` → **`原视频`**（"原片"在 H3 手册只以"原片段"出现过，指音轨）

**连带改的判据**（不是放宽，是跟着官方句式换）：`p9 C9`、`p10 A6`、`test_edit_spec_h3`、
`prompt_model_standards_check.phase_h3_boundary`、`identifiability_check` H3 抽取分支、
`ruler_h3_handwrite` 的 H4 规则与 GOOD 样本。其中两条**反转为"不许有"**：
「未被换的人写保持原样」→「不点名谁别动」。


---

## §45 · 按官方**实际范例**重装素材说明（2026-11-04）

**起因**：主人要求把手册目录 2.1–3.4 的案例**一条一条拆**，拆完再组装。
拆解落盘 `docs/H3-CASES-BREAKDOWN.md`（19 条功能案例 + 2 条完整范例 + 第四节规则表）。

**§44 之后仍然只换衣服不换脸**，所以不动结论，只换**有出处**的写法。

### 改了什么（每一条都指得到行号）

| 改动 | 依据 |
|---|---|
| 素材说明改**冒号式** `@图片N：人物参考（…）` | `:284`（大字幕 MV 完整范例）`@图片1：人物形象（脸、发型、服装轮廓、比例、气质、整体氛围）` |
| 素材列表末尾加 `只参考指定维度，不直接复制参考图。` | `:284` 原句 |
| `@视频1：视频编辑素材（对@视频1中的内容进行增删改）` | `:248` 用途表 + `:284` 冒号式 |
| `@音频1：音频复用素材（生成视频的音频直接复用@音频1）` | 同上 |
| 物体/场景/服装/关键帧/风格 五句统一冒号式 | 同上 |
| **删掉** `保持原有的固定机位不变` | 它是 `:192` 贴着**该案例自己的源片**说的（该例第 2 句 = `固定机位全景镜头`）。复刻源片有切镜（`f35fadf` = `[(0,8.4),(8.4,10.2)]`），抄这句 = 禁止切镜 → 真跑两镜压成一镜到底。`:250` 明写「默认会切镜」 |
| 新增 `非叙事性音乐：N/A`（仅 `audio_ref` 时） | `:251`「不想要（视频里不要出现什么）」唯一给了样例的一条 |

### 没有改的（刻意保留）

- **外观长括注**（含服装/鞋/耳饰）：这轮先不动，留作下一个单变量。
- **方位指代**：素材说明里仍不写（沿用 §44 的结论：`:264` 的「这位女子」= 图里那个人）。
- 三段结构本身：`:273` 明确把「只写一段话没分段」列为坑 → 分段是对的，§44 后我曾怀疑分段，
  **已按官方原文撤回该怀疑**。

### 连带改的判据

`p9 C8` · `p10 C3/C7` · `prompt_model_standards_check`（两处）· `test_edit_spec_h3`（5 处，
其中「固定机位」由"必须有"**反转**为"不许有"）· `prompt_lint_check` · `test_subject_look`（含 `subj_line`）。
尺子 `ruler_h3_handwrite` 未改（`OFFICIAL_USES` 里本就有「人物参考」）。

### 验证

`check_all --model h3` → **54 通过 / 3 跳过 / 1 红**（红 = p16 身份核对，既有问题，与本轮无关）。
重编 `f35fadf` 实测产出见台账下一节真跑记录（**尚未出片**）。


---

## §46 · 加回「锁定…的脸」—— 单人换脸跑通（2026-11-04）

**起因**：§45 改完第一次真跑（任务 `cb7a6ea1`），切镜回来了，**但人还是换不动**
（远景里女主只换了衣服）。主人当场看不出问题，逐项对账后定位到一句。

### 根因：§45 用了错体裁的范例

`:284`（大字幕 MV）是**创作任务**的范例 —— 表格标题写着「上传多模态素材融合
（**多模态参考**）」，括号里放的是"我要哪些维度"（`脸、发型、服装轮廓、比例、气质、整体氛围`）。

我们是**编辑任务**（§3 全能精准编辑）。官方给编辑任务的两处都带**动作词**：

| 行 | 原文 |
|---|---|
| `:248` | `人物参考（**锁定**脸/形象）` |
| `:264` | `@图片1 是人物参考（**锁**这位女子的脸）` |

§45 把「锁」弄丢了，只剩纯描述 → 模型读到的是"这张图长这样"，
于是照描述去换 —— 而描述里服装/配饰占了一半篇幅（礼服、廓形、体型、耳饰、鞋），
**所以它只换了衣服**。

### 改了什么（一处）

```diff
- @图片1：人物参考（鹅蛋脸型，眼型偏长眼尾微扬，…）
+ @图片1：人物参考（锁定图中人物的脸；鹅蛋脸型，眼型偏长眼尾微扬，…）
```

**只在括号开头加了「锁定图中人物的脸；」**，后面的描述一个字没动（单变量）。

### 实测（任务 `cb7a6ea1` · render `97ac0be7` · MiniMax-H3-Lite · 480P · 7.133s）

| 指标 | 成片 vs 参考图 | 源片 vs 参考图（对照） |
|---|---|---|
| best_sim | **0.415** | 0.065 |
| p90 | **0.382** | 0.065 |
| share | 0.333 | 0.0 |
| 阈值 | 0.363 | 0.363 |

- **换脸成立**：源片那个人与参考图只有 0.065（不是同一个人），成片 0.415 过线。
- **时长完全对齐**：7.133s → 7.133s。
- **切镜**：§45 删掉 `保持原有的固定机位不变` 后，前一次真跑已确认切镜按原片回来了。

### 仍未验证

- 🔴 **这次是单人**（盘点 1 个人，只有 1 张参考图）。双人（`f35fadf`）用同一版**还没跑**。
- 0.415 是刚过线，强度不如 `81633d37` 那次的 0.71。可能和 480P 有关，未定。

### 教训（写死）

**抄官方句式前，先看那条范例属于哪个任务类型。** 手册里有「创作」和「编辑」两条线：
创作看 `:264`/`:284`（提供维度、融合），编辑看 `:248`/`:213`（锁定、替换）。
混用不会报错，只会静默地把编辑做成创作。

---

## §47 · 音频用途句改为**条件写入** + 撤回一条自造句（2026-11-04）

### ① 改了什么

`@音频1：音频复用素材（…）` 原来是**无条件写**，上一轮被整段删掉（主人：「复刻视频本来就没让他生成新的音频」）。
删过头了：`:248` 要求「写清**每个**素材的用途」，挂了音轨却不交代用途是缺项。
改成**条件写入**：

```python
if audio_ref:
    duties.append("@音频1：音频复用素材（生成视频的音频直接复用参考音频素材）。")
```

**依据**：`h3-manual:248` 用途表原词「音频复用（生成视频的音频直接复用参考音频素材）」。
`audio_ref` 由 `video_edit.py:1197` 算：audio 模式在 tts/mix/original **且** 型号 `caps.ref_audio`。

🩸 **一个重要澄清（先写下来，免得下次又删一遍）**：`ref_audio` 是**型号能力位**（`model_specs.py`），
不是"用户传没传音频"。复刻走 `original` 模式时，`clone_pipeline.py:1418` 会抽**原片音轨**
当 `ref_audio` 发回去 → `audio_ref=True` → 这句**正常会出现**。
它说的是「**复用**参考音频素材」，不是「生成新音频」—— 和主人要的"沿用原声"是同一件事。
**"不生成新音频"靠的是 `original` 模式本身，不是靠删掉这句。**

**顺手改掉的重复指代**：旧句是「直接复用@音频1」，而 `@音频1` 在同一行开头已经出现过一次。

**验**：`prompt_lint_check --model h3` **1930/1930**（改前 35 条红，全是这条）；
`p10_check --model h3` **36/36**；`ruler_h3_handwrite --exhaustive` 破口 **6 → 0**（音轨开关恢复落点）；
`test_edit_spec --model h3` **50/50**。`check_all --model h3` 由 **6 红 → 2 红**。

### ② 撤回的自造句（记下来别再犯）

曾加过一句「画面右下的女生保持原样。」，依据引的是 **C10 `:212`**「…**动作与旁人保持一致**」。
逐字回原文核对，那句是：

> 画面左边**增加**一个穿着相同团队制服的人，动作与旁人保持一致

——是对**新加进来的人**的行为要求，**不是**「场上已有的人保持原样」。引用不成立，当场撤回。

**官方唯一"部分编辑"案例 = C11 `:213`**：只点名要改的那两个（最后面的小孩 / 最左边小孩的外套），
其余一个字不提。所以我们也不提。`test_edit_spec.py` 的「不点名谁别动」守的就是这条。

### ③ 关于双人失败，现在能说什么、不能说什么

| 样本 | 盘点 | 换了 | 结果 |
|---|---|---|---|
| `81633d37` | 1 人 | 1（全） | ✅ 0.71 |
| `cb7a6ea1` | 1 人 | 1（全） | ✅ 0.415 |
| `f35fadf` | 3 人 | 2 | ❌ |
| `de591f35` | 3 人 | 2 | ❌ |

**能说**：这四次的差别之一确实是「场上有没有没被点名的人」，2/2 对 2/2，值得作为下一个实验变量。
**不能说**：这构不成规则。官方 19 条案例里**没有一条**写"未点名者怎么处理"，
`docs/H3-CLONE-MATRIX.md` §10 已登记为空白 —— 空白就按 C11 的"不提"走，不许自己补句子。

### ④ 同时删掉又恢复的：外观长描述

同一轮还试过把 `@图片N：人物参考（锁定图中人物的脸；<外观描述>）` 的**后半段整段删掉**
（理由："编辑任务不需要外观描述"）。**已恢复。**

恢复理由不是"我觉得该留"，而是：**§46 那次单人真跑（0.415 过线）是带着描述跑的**，
删掉等于动了一个没有真跑证据的变量；而且 `:248` 明写「如果素材中有非常想要保持的
特征，**建议**明确写出来」—— 这是官方**建议**，不是空白。要删必须单独跑一条验证。

**净结果**：本轮结束时，提示词与 §46 已验证版本**逐字一致**，只多了一层"没有外观描述时
不写空括号"的兜底（判据 `test_subject_look.py` 21/21）。

### ⑤ 补记两处早先删掉、但当时没记账的句子

对照 `de591f35`（09:55 那次真跑）的实发请求 `triage/request_001.json`，当时提示词里还有两句，
现在代码里没有了。**两句都删得对，但当时漏了记账**：

| 被删的句子 | 出处 | 为什么删 |
|---|---|---|
| `只参考指定维度，不直接复制参考图。` | `:284` **大字幕 MV（图生视频·创作任务）** | 同一类错误已在 §46 记过一次：创作范例不套编辑任务。复刻要的就是"复制那张脸"，这句话反而在往回拉 |
| `非叙事性音乐：N/A` | `:251`「**不希望视频里出现背景音乐时**…建议在提示词最后明确写」 | 这是**有条件**的句子。复刻沿用原片音轨，原片有没有 BGM 由原片决定 —— 写 `N/A` 等于告诉模型"别出 BGM"，会把原片的背景音乐压掉 |

⚠️ 同时补一条**时序事实**：`de591f35` 的实发提示词是
`@视频1中画面左侧的人物换成@图片1中的人物，画面中央的人物换成@图片2中的人物。`
—— **第二个分句没有重带 `@视频1中`**。现在代码是每个分句都带（C11 `:213` 的写法）。
⇒ 说明那次真跑用的**不是现在这版代码**（后端当时还没重启）。拿它当"当前版本"的对照组会归错因。

---

## §48 · 接上**镜头结构句**（2026-11-04 · 主人：「细节没看全」）

### ① 断在哪

数据链是通的，**只有最后一段没接**：

```
clone_pipeline.py:102  scene.detect_shots(video)      → 2 镜（0–3.333 / 3.333–5.362）
recipe["shots"]                                        → 存进 task.json
video_edit.py:2406     cuts = _clean_cuts([...])       → [3.333]
video_edit.py:1799     compile_prompt(shot_cuts=cuts)  → ✅ 传到了
models/h3.py  handwrite(...)                           → ❌ **没有 shot_cuts 这个参数**
```

2.5 有（`volc25_compile._shot_plan` → 「第 3 秒按@视频1原有的剪切点与转场切镜」），
**H3 一直没有** → 镜头结构句从来没进过 H3 的提示词。

### ② 依据（全是 H3 自己的，不是 2.5 的）

| 行 | 原文 |
|---|---|
| `:251` | 按时间轴或故事线分段写…**以切镜 shot 作为时间戳的分段** |
| `:250` | **默认会切镜**（不写切点，模型自己编） |
| `:266` | …自然衔接，**不要切镜** |
| `:276` | 想一镜到底但写了很多分镜 → **删掉【镜头 N】结构** |
| `:181` | **严格参考示例视频视频1的镜头节奏、转场风格**及音乐 |

### ③ 改成什么

【画面过程说明】最前面加一句，三态：

| `shot_cuts` | 写什么 |
|---|---|
| `[3.333]` | `在@视频1第 3.33 秒的切镜点切镜，严格参考@视频1的镜头节奏和转场风格。` |
| `[]`（确定一镜到底） | `全程一镜到底，不要切镜。` |
| `None`（不知道） | **一个字不写** —— 不许瞎猜 |

### ④ 实测证据

`de591f35` · render `45749cef`：源片 2 镜 → 成片 3 镜（`detect_shots` 实测），
多出来的 **4.0–5.37** 那一刀，画面是参考图2 的夜晚中式庭院（`ref_person2.jpg` 的背景）。
参考图的外观描述里**一个背景词都没有**（`:24` + `_DESC_SCHEMA` 都拦住了）—— 背景是**看图复制**的。

⇒ 模型没有切镜点，就自己切到参考图里去了。

### ⑤ 判据

`p10_check.py` C10/C11/C12 三条（三态各一条，缺一条就等于"不知道"被当成"一镜到底"）。
`check_all --model h3`：**54 通过 / 3 跳过 / 1 红**（红 = 既有的「可指认性穷举」）。

### ⑥ 还没接的（下一轮，一次一个）

- `inventory.shots[].en` 里的**景别 / 动作 / 运镜**（`Medium full shot` /
  `dance rhythmically` / `camera slowly pulls back`）—— `:251` 要这三样，数据在手，还没接。
- `:174`「氛围与剪辑理解：参考原视频的**整体剪辑感**」—— `@视频1` 用途句还没写它。

---

## §49 · 接上**逐镜画面内容**（2026-11-04 · 接 §48 的第二段）

### 改了什么

【画面过程说明】最前面加一句画面内容，数据来自盘点 `inventory.shots`：

```
原片画面：Medium full shot, two aproned women dance rhythmically behind the wooden
cooking counter, warm lighting, bamboo thatched roof, tropical plants in background,
camera slowly pulls back.
在@视频1第 3.33 秒的切镜点切镜，严格参考@视频1的镜头节奏和转场风格。
替换后的人物必须严格遵循原视频的运动轨迹。
确保替换后的人物质感和光影与环境融合。
```

**依据**：`:251`「每个 shot 内部写好**景别、具体内容、运镜**」+ `:260`「切镜的时候可明确写出
**切镜到什么景别**，具体主体是之前的哪个角色，**有助于跨镜头一致性的保持**」。

**三种形态**：

| 盘点 `shots` | 写什么 |
|---|---|
| 1 段 | `原片画面：<en>`（不写时间戳 —— 写了也是假的精度） |
| ≥2 段 | `0-2.8 秒：<en>` 逐段写（最多 12 段，再多就稀释重点） |
| 空 | 不写，不留空壳 |

**顺带的正作用**：这条 en 里带 `warm lighting, bamboo thatched roof, tropical plants in
background` —— 正是原片的环境。它和"参考图2 的夜晚庭院"对着干，能从文字上把画面拽回原片。

### 没做的那条（`:174` 整体剪辑感）—— 判断为**重复，不加**

`:174`「氛围与剪辑理解：参考原视频的视觉风格、叙事节奏、声音氛围与整体剪辑感」。
逐项对下来，现在已经被覆盖：

| `:174` 的项 | 现在谁在管 |
|---|---|
| 视觉风格 | `原片画面：<en>`（含光照/环境） |
| 叙事节奏 / 整体剪辑感 | 切镜点句「第 X 秒切镜，严格参考@视频1的镜头节奏和转场风格」 |
| 声音氛围 | `@音频1：音频复用素材` |

再往 `@视频1` 用途句里塞一句，是和切镜句重复。`:251` 要求「尽量少写比喻句，多写看得见的画面」
—— 重复的抽象句不加。

### 判据

`p10_check.py` C13/C14/C15（单镜 / 多镜 / 空盘点三态）。`p10_check --model h3` **42/42**。
`check_all --model h3`：**54 通过 / 3 跳过 / 1 红**（红 = 既有的「可指认性穷举」）。

### 待验证

改动要**重启后端**才进内存（`h3.py` / `h3_compile.py` / `video_edit.py` 三个文件）。
重启后跑 `de591f35`，看两件事：
1. 成片镜头数是否回到 **2**（源片 2）
2. 4.0s 之后是否还是原片的白日木屋（不再是参考图的夜晚庭院）

---

## §50 · `原片画面` 只取**景别**（2026-11-04 · 主人：「把无关复刻的东西加进来了」）

### 错在哪

§49 把盘点 `shots[].en` **整句**搬进了【画面过程说明】：

```
原片画面：Medium full shot, two aproned women dance rhythmically behind the wooden
cooking counter, warm lighting, …, camera slowly pulls back.
```

三个问题，一个比一个严重：

1. **`two aproned women`** —— 这是原片的人。复刻要换掉的就是她们，
   写进提示词等于告诉模型"画面里是两个穿围裙的女人"，跟「换成@图片1中的人物」对着干。
2. **这句不是给复刻用的** —— `vision_plan.py:172` 写着 `shots[].en` 是给
   **提示词优化线**（`ref-en:7` 的 `detailed_description`）用的完整画面描述。
   两条产品线共用一份数据，复刻直接拿来会带进另一条线的前提。
3. **`warm lighting, bamboo thatched roof, tropical plants`** —— 环境词看着有用，
   但那是"描述原片"，不是"复刻要干什么"。

### 怎么改的（不是删，是挑）

`:251` 要三样：**景别 / 内容 / 运镜**。复刻里逐项处理：

| `:251` 要的 | 复刻里 |
|---|---|
| 景别 | ✅ **写** —— 取 `en` 第一个逗号前。`vision_plan.py:211` 规定 en 的顺序就是「景别 → 主体 → 动作 → 环境 → 运镜」，**13/13 样本全中** |
| 内容 | ❌ **不写** —— 内容就是"换成谁"，已经在【核心创意】里了 |
| 运镜 | ❌ **不写** —— 实测 `camera at frame center`（位置）、`camera to show the full pile of snacks`（内容）都被误认成运镜，宁可少说 |

改完：

```
原片画面：Medium full shot。
在@视频1第 3.33 秒的切镜点切镜，严格参考@视频1的镜头节奏和转场风格。
```

### 教训（写死）

**"这条出自哪一章"只能决定"要不要搬"，不能决定"能不能用"。**
第四章是创作任务的公式，但它的**结构**（景别+内容+运镜）照样能拆开，
在复刻里各取所需 —— 一律否掉，和一律照抄是同一个毛病。

### 判据

`p10_check.py` C13/C14/C15 改成守「只取景别、不带人物、不带运镜」。**42/42**。
`check_all --model h3`：**54 通过 / 3 跳过 / 1 红**（红 = 既有「可指认性穷举」）。

## §51 · 通读全书后补**保留清单 + 禁止新场景**（2026-11-04 · 主人：「再看多一些细节」）

### 起因：上一轮的结论是错的

§47 撤回过一条「画面右下的人物保持原样」，当时顺带下了个结论：

> 官方唯一"部分编辑"的案例是 C11 `:213`：只点名要改的那两个，其余一个字不提。
> 所以我们也不提。

**这个结论是"只扫了第三章"得出的。** 主人让再挖细节，通读 1–297 行后发现：

| 位置 | 原文 | 说明什么 |
|---|---|---|
| `:206`（第三章总纲） | 「高精度指令控制：准确执行局部修改与细化要求，**同时保持未编辑内容相对稳定**」 | **写"什么不能动"是官方第一原则** |
| `:133`（1.8 硬件演示） | 「…**必须保持 100% 不变**，确保替换元素与原画面无缝融合」 | 全书唯一一条「替换某元素、其余保持」的完整范文 |
| `:88`（1.3 MG） | 「严格保持原视频的人物、五官、服装、动作、场景、综合色、镜头运动、时长与帧率完全不变」 | 官方有"保留清单"这种句式 |
| `:95`（1.4 AR） | 「使用上传的原视频作为**唯一视频基础**…**不要重新生成一个新场景**，而是在原视频上做…编辑效果」 | 官方有"禁止新场景"这种句式 |
| `:96`（1.4） | 「保留原始构图、镜头角度、…位置、动作节奏、…位置关系」 | 同上，列举式保留 |

→ 撤回「画面右下的人物保持原样」**仍然是对的**（引的 `:212` 是给"新增加进来的人"的要求），
但**"所以什么都不写"同样不成立**。这是两件事，§47 把它们混成一件了。

### `:133` 全拆（唯一可套的范文）

| 段 | 原文 | 复刻里 |
|---|---|---|
| ① 任务命名 | 「精准替换场景背景」 | ➖ 不需要（【核心创意】已点名） |
| ② 替换对象 | 「将原视频中的桌面替换为…」 | ✅ 已有（`:213` 的「@视频1中画面左侧的人物换成@图片1中的人物」） |
| ③ 融合要求 | 「透视比例需与原镜头完全匹配」 | ✅ **采纳** |
| ③ 融合要求 | 「桌面材质需自然承接原视频的光影投射」 | ❌ 换桌面专用 |
| ③ 融合要求 | 「边缘阴影与高光方向必须与原场景光源严格一致」 | ❌ 说的是桌面边缘投射；换人的光影已由 `:192` 覆盖，搬进来同一维度说两遍 |
| ③ 融合要求 | 「景深虚化程度需与原视频焦点对齐」 | ❌ 换背景专用 |
| ③ 融合要求 | 「保持原有空间纵深感」 | ❌ 换背景专用 |
| ④ **保留清单** | 「镜头运动轨迹、机械臂的完整运动时序与速度、画面中其他物品的相对位置与空间遮挡关系、以及整体光照氛围必须保持 100% 不变」 | ✅ **四项全采纳**（机械臂→人物动作、其他物品→其他元素） |
| ⑤ 收尾 | 「确保替换元素与原画面无缝融合」 | ✅ 已有（`:192`「质感和光影与环境融合」） |

「其他物品」写成「其他元素」而不是「其他人物」：只换 1 个角色、场上没有别人的时候
这句话不落空（道具和背景还在），也不会引得模型去找"还有谁"。

### 改了什么

`h3_compile.py` `if swapped:` 块新增三句、原有两句保留：

```
替换后的人物必须严格遵循原视频的运动轨迹。                              ← 原有（:192）
@视频1的镜头运动、人物动作的时序与速度、画面中其他元素的相对位置和空间遮挡关系、
  以及整体光照氛围必须保持 100% 不变。                                  ← 新增（:133 ④）
替换后的人物的大小和透视与原视频中的人物完全匹配。                      ← 新增（:133 ③）
确保替换后的人物质感和光影与环境融合。                                  ← 原有（:192）
使用@视频1作为唯一视频基础，不要重新生成一个新场景，而是在@视频1上做人物替换。 ← 新增（:95）
```

### 为什么这次值得做

`93dbec8f` 的失败形态就是「**重新生成了一个新场景**」——切镜后的画面跑到
参考图2 的夜晚庭院去了。`:95` 那句话是官方对这种失败的直接禁止项。

### 判据

`test_edit_spec_h3.py` 新增 10 条：保留清单四项、融合一项、禁止新场景一项、
**不串**换背景专用的四项（景深虚化 / 空间纵深感 / 承接光影投射 / 阴影高光方向）。
`test_edit_spec.py --model h3` **60/60**；`p10_check.py --model h3` **42/42**。
未出片（等主人重启后点）。

## §52 · 逐条判完剩下的七条：做四条、驳回三条（2026-11-04）

主人：「你刚才细扫得出的 1–7 的都修好了是吗？…还有四项为什么不一起做完呢？
**其实最关键的还是那句话要灵活运用不要全抄**」

§51 只修了七条里的三条，剩下四条我用「一次只改一个变量」压着 —— 那不是判断，
是偷懒。这一轮**逐条过**，该做的做，不该做的给出驳回理由。

| # | 发现 | 判 | 理由 |
|---|---|---|---|
| 1 | 推翻旧结论，官方要求写保留项（`:206`） | ✅ 已做（§51） | — |
| 2 | `:133` 完整范例五段 | ⚠️ 用了 ③④⑤；**①任务命名驳回** | 「精准替换场景背景」是案例**标题**，不是提示词正文。`:213` 的「精准换人物与细节」同理 |
| 3 | `:95` 不要重新生成新场景 | ✅ 已做（§51） | — |
| 4 | `:88` 的「综合色」 | ✅ **做**：并进光照那句 →「整体光照**和色调**」 | 色彩和光照是两个维度，加一个词 |
| 4 | `:88` 的「时长与帧率」 | ❌ **驳回** | 时长由 API 参数（`_gen_duration`）控制，写进提示词模型看不见，等于没写 |
| 5 | `:254` H3 对切镜点遵从较强 | ➖ 只做佐证，写进注释 | — |
| 6 | 自造标签「原片画面：」 | ✅ **做**：改官方 `0-3 秒：全景`（`:251`/`:285`） | 自己造的标签没有出处 |
| 6 | 全局规则该分组 | ✅ **做**：【整体要求补充】+ `▍组名（贯穿全片）` | `:284`/`:285` 两条完整模板共用 12 次 |
| 7 | 切镜风格四选一（`:250`） | ❌ **驳回** | 那是给"凭空指定风格"的创作场景。复刻的 `@视频1` 本身就是参照物，硬填一种反而是多押一个注 |
| 8 | `:260`「主体是之前的哪个角色」 | ✅ **做** | 用图号指代（不描述外观，不跟「换成@图片N」打架） |

### 结构变化（这是本轮最大的一处）

之前所有句子都堆在【画面过程说明】里，和时间轴分段混在一节。现在按 `:284`/`:285`：

```
【画面过程说明】          ← 只有时间轴（`:251`）
0-5.3 秒：Medium full shot。
在@视频1第 3.33 秒的切镜点切镜。

【整体要求补充】          ← 贯穿全片的规则（`:284`/`:285`）
▍镜头（贯穿全片）
严格参考@视频1的镜头节奏和转场风格。
▍人物与动作（贯穿全片）
替换后的人物必须严格遵循原视频的运动轨迹。
@视频1的镜头运动、人物动作的时序与速度、画面中其他元素的相对位置和空间遮挡关系、
  以及整体光照和色调必须保持 100% 不变。
▍画面融合（贯穿全片）
替换后的人物的大小和透视与原视频中的人物完全匹配。
确保替换后的人物质感和光影与环境融合。
▍禁止项（贯穿全片）
使用@视频1作为唯一视频基础，不要重新生成一个新场景，而是在@视频1上做人物替换。
```

`:244` 的三段公式是**简版骨架**；任务复杂到有全局约束时，官方自己用四段（`:284`/`:285`）。

### 顺手逮到一个真 bug

改完第一次跑探针，输出是：

```
0-5.3 秒：Medium full shot。
```

**切镜点没了。** 因为 `inventory.shots` 只给 1 段景别、`recipe.shots` 有 2 镜
（`de591f35` 就是这样），代码走 `len(_scales)==1` 分支，只写景别不写切点。
`:250`「默认会切镜」—— 不写它就自己编。现在补：单段景别 + 有切点时，
景别按盘点写、**切点单独补一句**，不去编第二镜的景别（盘点没给）。

### 判据

`p10_check.py` C13/C14 改成官方标签格式；新增 C16（单段景别 + 有切点 → 补切点句、
不编第二镜景别）、C17（跨全片规则单列【整体要求补充】+ `▍` 分组）。**44/44**。
`test_edit_spec.py --model h3` **60/60**。
未出片（等主人重启后点）。

## §53 · 主人三问：换场景没用到 `:133`、保留清单被 `if swapped` 盖住、能不能套到任意爆款（2026-11-04）

主人的三个问题：

1. 「我们也有换场景的哟！只是现在还没勾选呢，目前只调试换人」
2. 「没有把所有东西都叠加到一个测试单片上吧？」
3. 「能准确的灵活运用到任意一个爆款视频上改用到的吧？」

### 一、`:133` 的那四项不是"换人用不上"，是**换场景用的**

§52 我写「另四项（承接光影投射 / 阴影与高光方向 / 景深虚化 / 空间纵深）全是
换桌面+换背景专用的 → 换人不用」，然后就**整批丢掉**了。

错在只盯着"当前在测换人"。`:133` 原文就是「精准替换**场景背景**」，
那五项是**我们自己的 `c["scene"]` 入口**该用的。现在补上：

```
▍场景融合（贯穿全片）
新背景的透视比例与原镜头完全匹配，边缘阴影与高光方向与原场景光源严格一致，
景深虚化程度与原视频焦点对齐，保持原有空间纵深感。
```

（五项里「材质自然承接光影投射」并入"光影方向一致"，不单列 —— 换场景时说的是
背景材质接光，和下一句同义。）

### 二、更严重的：保留清单 + 禁止项被 `if swapped:` 包着

这两句原来写在 `if swapped:` 块里 → **只换场景 / 只换产品 / 只改风格时，一个字都不写**。
而 `:206` 总纲说的是「保持**未编辑内容**相对稳定」，跟改的是什么毫无关系。

现在提到函数末尾，判据改成 `if idea:`（有任何一条改动就写）。
禁止项末句跟改动类型走：**只换人**才写「人物替换」，还换了别的就沿用 `:95` 的原词「编辑」。

### 三、形态矩阵（回答"能不能套到任意爆款"）

新判据 `scripts/h3_matrix_check.py`，已挂进 `check_all.py`（"H3 形态矩阵"）。
**18 种形态**各编一遍，逐条查：缺段 / 多出不该有的句子 / 空壳标题 / 非换人却写了换人句。

| 组 | 形态 |
|---|---|
| A 换人 | 单镜1人 / 单镜2人 / 多镜2人（两段景别）/ 多镜2人（盘点只给一段）/ 不知道切镜 / 盘点全空 / 3人只换2个 / 有音轨 |
| B 非换人 | 只换场景（文字）/ 只换场景（图）/ 只换产品 / 只改风格 |
| C 组合 | 换人+换装 / 换人+换场景 / 换人+换产品+风格 / 换人+换场景+换装 |
| D 边界 | 什么都没改 / 首帧续接 |

### 矩阵当场抓到的三个问题

1. **矩阵自己第一版是错的**：`build()` 无条件给 `person` 槽 → 只换场景也被编译成"换人"，
   B1–B4/D1 全报"非换人却写了运动轨迹"。**先修的是判据，不是代码** ——
   不改的话会去"修"一个不存在的 bug。
2. **`▍人物与动作` 出现两次**：分组原来是"相邻同名合并"，中间插进「画面融合」后
   又开了一个同名标题。改成按组**归并**（dict 保插入序）。
3. **组名误导**：保留清单挂在「人物与动作」下，只换场景时读起来像只对角色生效 → 改名「镜头与画面」。

### 判据

- `h3_matrix_check.py` **18/18**
- `p10_check.py --model h3` **44/44**
- `test_edit_spec.py --model h3` **60/60**
- `check_all.py --model h3`：见下（红仍是既有的「可指认性穷举」）

⛔ 未出片（等主人重启后点）。

## §54 · 换人"写死"：矩阵用例是我编的 → 改用 20 个真实任务的盘点（2026-11-04）

主人：「换人这一块我发现你还是会写死【A1 单镜·1人 / A2 单镜·2人 / A3 多镜·2人 /
A4 多镜·2人（盘点只给一段） / A7 3人只换2个】」

### 说的是什么

§53 那个"18 种形态 18/18"，**用例全是我手写的**：1/2/3 人、left/center/right。
拿自己挑的样例自证"能套任意爆款"，这是循环论证。

### 怎么办

`data/clone/*/inventory/*.json` 里有 **20 份真实盘点**。里面本来就有：

| 真出现过的形态 | 数量 |
|---|---|
| 9 人（含两个 `left`、两个 `right`、两个 `center` 的同方位撞车） | 1 份 |
| 5 人（含 `top-left` / `top-right`） | 1 份 |
| 3 人 | 6 份 |
| 1 人 | 8 份 |
| `bottom-right` 方位 | 1 处 |
| 镜头数 1 / 2 / 3 / 5 / 15 | 都有 |
| 时长 5.3s – 47.8s | 都有 |

新判据 `scripts/h3_real_matrix_check.py`：遍历每一份真盘点，
对「全换 / 前 1 / 前 2 / 前 3 / 末 2」每种组合各编一遍，查四件事：
① 每个被换的人都有 `@图片N`；② 指代词互不重复（撞车要退回描述）；
③ 全局规则必须在；④ 不许漏出原片人物描述。

**43 组合全部通过。**

### 中途差点又犯病（记下来）

看到 `_PERSON_NOUNS` 是写死的结尾词表，我用 33 条真实描述一验：**27 条不以人中心词结尾**，
以为找到了"写死"的证据，动手改成"看末 4 字"。

**改完一跑，43 组的输出一个字没变。** 两种判法在真实数据上判定完全相同 ——
`留黑色长直发` 两种都补「的人」、`留黑色短发的女性` 两种都不补。

**当场还原，只留注释。** 补出来的「画面左侧的留黑色长直发的人」读着啰嗦，
但语法完整、模型看得懂。**要改它得先看见它出过错，不能凭"读着别扭"就动**
（`no-stacking-rules`：指不到出处 = 自造，当场撤回）。

### 判据

- `h3_real_matrix_check.py` **43/43**
- 已挂进 `check_all.py`「H3 真实盘点矩阵」
- 其余见 §53

## §55 · 逐句核对：哪些是照抄、哪些是改造（2026-11-04）

主人贴了预览截图问「该修改的都修改好了吧？没有逐条全抄吧？」

逐句核完，**没有一段是整段照抄官方原文的**。补了一处漏的（下面第 9 行）。

| # | 提示词里的句子 | 出处 | 处理 |
|---|---|---|---|
| 1 | `@图片1：人物参考（锁定图中人物的脸；鹅蛋脸…）` | `:248` 用途枚举 + 「非常想要保持的特征建议明确写出来」 | **改造**：括号里的描述来自盘点，不是官方的 |
| 2 | `@视频1：视频编辑素材（对@视频1中的内容进行增删改）。` | `:248` 枚举原词 | **逐字**——这是官方**枚举值**，不是句子，本来就该原样用 |
| 3 | `@音频1：音频复用素材（生成视频的音频直接复用参考音频素材）。` | `:248` 枚举原词 | **逐字**，同上；且只在真有音轨时写 |
| 4 | `@视频1中画面左侧的人物换成@图片1中的人物` | `:213`「视频1中最后面的小孩换成图1中的金毛狗」 | **改造**：换成盘点给的方位指代 |
| 5 | `0-5.3 秒：Medium full shot。` | `:251`「0-3 秒：全景，女子（@图片1）…」的分段格式 | **改造**：时间/景别都来自盘点 |
| 6 | `在@视频1第 3.33 秒的切镜点切镜，主体仍是@图片1、@图片2中的人物。` | `:260` 句 + `:251` 示例 | **改造**：`de591f35` 的切点 3.333s、图号都来自任务数据 |
| 7 | `严格参考@视频1的镜头节奏和转场风格。` | `:181`「参考示例视频视频1的镜头节奏、转场风格**及音乐**」 | **改造**：**删掉「及音乐」**（复刻音频走复用，不让模型生成） |
| 8 | `替换后的人物必须严格遵循原视频的运动轨迹。` | `:192`「水豚必须严格遵循原视频的运动轨迹」 | **改造**：水豚 → 人物 |
| 9 | `替换后的人物的大小和透视与原视频中的人物完全匹配。` | `:133`「透视比例需与原镜头完全匹配」 | **改造**：办公桌 → 人物 |
| 10 | `确保替换后的人物质感和光影与环境融合。` | `:192`「确保水豚的毛发质感和光影与环境融合」 | **改造**：水豚毛发 → 人物 |
| 11 | `@视频1的镜头运动、人物动作的时序与速度、画面中其他元素的相对位置和空间遮挡关系、以及整体光照和色调必须保持 100% 不变。` | `:133` 的四项保留清单 | **改造**：机械臂→人物动作、其他物品→其他元素、光照氛围→光照和**色调**（`:88` 补的一项） |
| 12 | `使用@视频1作为唯一视频基础，不要重新生成一个新场景，而是在@视频1上做人物替换。` | `:95`「使用上传的原视频作为唯一视频基础…不要重新生成一个新场景，而是在原视频上做 AR 实景合成与世界编辑效果」 | **改造**：上传的原视频→@视频1、AR 实景合成→人物替换 |

**没有搬的**（每一条都有理由，记在 §51–§54）：
`:133` 的①任务命名（是标题）、`:133` 的承接光影/阴影高光/景深/纵深（换场景才用，见 §53）、
`:88` 的时长与帧率（API 参数控制）、`:250` 的切镜风格四枚举（复刻有原片做参照）、
`:261`（官方标题下面是空的）。

### 本轮补的一处

第 6 行原来只有 `在@视频1第 3.33 秒的切镜点切镜。` —— 盘点只给了一段景别时，
`:260` 的「主体是之前的哪个角色」被漏掉了。已补，且**不编第二镜的景别**（盘点没给）。

### 判据

`h3_matrix_check` **18/18** ｜ `h3_real_matrix_check` **43/43** ｜
`p10_check` **44/44** ｜ `test_edit_spec --model h3` **60/60**

## §56 🩸 实测翻车：`:133`（换场景）的公式套到换人上 → 脸一个都不换（2026-11-04）

主人贴 v5 成片：「一点改动都没有哟，你说你看完的所有文档细节呢？」

### 先确认不是链路问题

| 查了什么 | 结果 |
|---|---|
| 参考图发出去没有 | `ref_images: ['subject.jpg','ref_person2.jpg']` ✅ |
| 是不是复用旧片段 | 四次 render 缓存键全不同（`b46da6ef` / `60e3c657` / `95eab9de` / `4daedf2e`）→ **每次都真重新生成** ✅ |
| 成片 vs 源片人脸相似度 | 5 个时间点 × 2 张脸，**sim 0.59–0.69**，全部判「没换」 |

### 真凶：`v4 → v5` 多的那 4 句

```
+ 替换后的人物的大小和透视与原视频中的人物完全匹配。      ← :133 ③
+ @视频1的镜头运动、人物动作的时序与速度、画面中其他元素的
  相对位置和空间遮挡关系、以及整体光照和色调必须保持 100% 不变。  ← :133 ④
+ 使用@视频1作为唯一视频基础，不要重新生成一个新场景，而是在@视频1上做人物替换。 ← :95
+ 主体仍是@图片1、@图片2中的人物。                        ← :260（这句留着）
```

对照：

| render | 提示词 | 结果 |
|---|---|---|
| v4 `93dbec8f` | 只有 `:192` 两句 | **前半段两张脸都换成了** |
| v5 `f2825696` | + `:133` 保留清单 + `:95` 禁止句 | **每一帧都"没换"** |

### 根因：**三种替换任务，官方给了三套公式，我搬错了**

| 案例 | 任务 | 官方原文 | 公式 |
|---|---|---|---|
| `:213` C11 | 换人物 | 「视频1中最后面的小孩换成图1中的金毛狗」 | **只写替换句，其余不提** |
| `:192` C07 | 换主体 | 「水豚必须严格遵循原视频的运动轨迹…质感和光影与环境融合」 | **两句** |
| `:133` | 换场景 | 「精准替换**场景背景**」+ 融合五项 + 保留清单四项 + 100% 不变 | **重** |

`:133` 保留的是「桌面和背景换了、**场上的人别动**」。换人反过来：**人换了、背景别动**。
同一句「画面中其他物品…必须保持 100% 不变」到了换人语境，模型把人也算进「其他物品」，
整片被按住不动。

**这正是主人一直说的「没灵活运用、全抄」**：我看见了 `:133` 的完整范文，就整段搬，
没问它服务的是哪种任务。

### `:95` 为什么也删

「不要重新生成一个新场景」加进来的理由是 `45749cef` 场景跑偏（切镜后跑到参考图2 的庭院）。
但那个失败的真正成因是**没写切镜点**。`:260` 的切镜句加上之后，v4/v5 两版场景都是对的 ——
不需要 `:95`。它属于 AR 特效案例（在原片上加东西），「不要重新生成」在换人语境读成「整片别动」。

### 改完的换人提示词（= v4 + 主体指代 + 分组）

```
【画面过程说明】
0-5.3 秒：Medium full shot。
在@视频1第 3.33 秒的切镜点切镜，主体仍是@图片1、@图片2中的人物。

【整体要求补充】
▍镜头（贯穿全片）            严格参考@视频1的镜头节奏和转场风格。
▍人物与动作（贯穿全片）      替换后的人物必须严格遵循原视频的运动轨迹。
▍画面融合（贯穿全片）        确保替换后的人物质感和光影与环境融合。
```

`v4` 相比 v5 少的是三句，多的是**主体指代**这一句。

### 判据同步反转

- `test_edit_spec_h3.py`：原来 6 条断言「保留清单/透视/禁止新场景要在」→ 改成「**换人路径不许有**」，
  另加 2 条「换场景时必须在」。
- `h3_matrix_check.py`：`MUST` 按任务类型拆开；新增 `PERSON_NEVER`——换人路径串了换场景公式直接红。
- `h3_real_matrix_check.py`：硬项从「100% 不变 / 禁止新场景」改成「运动轨迹 / 光影与环境融合」。

`18/18` 形态、`43/43` 真实盘点、`44/44` p10、`59/59` edit_spec。

---

## §57 换人补「特征维度清单」—— 主人 2026-11-04「要区分换什么不换什么」

### 为什么改

主人问「再看看有什么关于复刻的你没看齐全的，**但是你要区分换什么不换什么**」。
重扫手册第 1–4 章，把**所有**"参考图 + 人物"的句子拉出来对照，发现官方分三类写法：

| 写法 | 官方例句 | 换的是什么 |
|---|---|---|
| 只写替换句 | `:208`「把视频中的猫换成狗」<br>`:213`「视频1中最后面的小孩换成 图1中的金毛狗」<br>`:192`「三个穿西装的男人替换为三只高度写实的水豚」 | **通用物** —— 模型知道狗/水豚长什么样 |
| 替换句 + **逐项特征清单** | `:65`「保持人物一致：白金色长发、窄黑色复古墨镜、黑色高光漆皮风衣、冷酷自信的时尚表情、火光映在皮衣表面的橙色反射」<br>`:128`「使用 图2作为固定人物参考，保持黑色半扎长发、银色镂空发冠、黛蓝发带、浅色层叠汉服、半透明蓝色外袍、深蓝腰封、银色花形扣饰和长流苏一致」<br>`:142`「使用图2作为严格的角色身份参考。请保持同一个角色**脸、发型、体型比例、服装设计、材质细节**和乙游 CG 质感一致」 | **具体的人** —— 人有参考图，必须说清哪些维度要跟过来 |
| 替换句 + **属性级"不变"** | `:225`「左边的人穿白色西装…**但两人手套颜色不变**」 | 同一主体内换 A 属性、保 B 属性（我们不适用） |

我们复刻换人 = 第二类（给的是具体人的定妆图），但当时写的是第一类句式
（`@视频1中画面左侧的人物换成@图片1中的人物。`）→ **维度清单是缺的**。

后果：模型自己挑最好换的那一维。§49 的 `f35fadf` 就是**只换了衣服、脸没动**。

### 依据

主依据 `:142` 的维度名（脸、发型、体型比例、服装设计、材质细节）；
`:65`/`:128` 证明这套写法在"给参考图"的场合是官方的常规动作，不是孤例。

### 改了什么（`h3_compile.py` · 替换句后新增一句）

```
@视频1中画面左侧的人物换成@图片1中的人物，@视频1中画面中央的人物换成@图片2中的人物。
替换后的人物在脸、发型、体型比例、服装设计和材质细节上与@图片1、@图片2保持一致。
```

三处细节：

1. **指向参考图，不指向原片**。v5 `f2825696` 的 `:133` 保留清单是「原视频的…必须保持
   100% 不变」——指向原片 → 模型照抄原片 → **一帧都没换**。新句是「替换后的…与@图片N
   一致」，方向相反。（`test_edit_spec_h3.py` 加了断言锁这个方向。）
2. **勾了换装的人去掉「服装设计」**。否则 `_wardrobe_pairs()` 的「服装改为牛仔外套」
   和清单的「服装设计…与@图片1一致」正面打架。
   判定口径与 `_wardrobe_pairs()` 同源：有 `wardrobe_ids` 按 ids，否则全员。
3. **按图号排序输出**。多人时第二句不能指回第一个人（第一版写反了，已修）。

### 没改的部分（"不换什么"已经是官方全集）

| 维度 | 状态 | 依据 |
|---|---|---|
| 运动轨迹 | ✅ 已在 | `:192`「水豚必须严格遵循原视频的运动轨迹」 |
| 光影/质感融合 | ✅ 已在 | `:192`「确保水豚的毛发质感和光影与环境融合」 |
| 固定机位 | ❌ 不许写 | `:192` 那句贴着它自己的固定机位源片；我们源片有切镜 |
| 其他没点名的人 | ❌ 不写 | `:213` 只点名要改的 |
| 场景/光照/构图 100% 不变 | ❌ 不许写 | `:133` 换场景公式，v5 实测把脸按死 |
| 时长/帧率 | ❌ 不写 | `:88` 是"原片上加特效"的任务，不是替换 |

### 验过什么

`h3_matrix_check` 18/18 · `h3_real_matrix_check` 43/43 · `test_edit_spec --model h3` 62/62。

### 现在死活

**未出片。** 等主人重启后端后自己点一次渲染验证。
关键看：两张脸是不是**同时**换了，以及**服装有没有跟着定妆图走**（记忆
`clone-swap-carries-costume`：定妆图带服装，整包跟着走才对）。

---

## §58 撤掉「补切镜点」—— 源片本来就是一个镜头（主人 2026-11-04 确认）

### 铁证：四版逐帧对照（同一任务 `de591f35`、同一素材）

| render | 0–3.3s | 3.3–5.36s |
|---|---|---|
| `74d65218` | 围裙 · **没换** | 厨房 ✅ |
| `93dbec8f`（曾被误记为"成功基准"） | 礼服 · **换了** | **夜晚庭院 ✗** |
| `f2825696`（v5） | 围裙 · **没换** | 厨房 ✅ |
| `c8455a93`（§57 那版） | 礼服 · **换了** | **夜晚庭院 ✗** |

**只有"没换人"的版本背景是对的** —— 因为它整片在照抄原片，跟换人无关。
一旦真的换人，第二个镜头就整段搬来 `@图片2` 的原场景（夜晚庭院、单人古装）。

### 根因

**源片根本没有切镜**。主人肉眼确认：`camera slowly pulls back`，全程同一个厨房、
同样的两人、连续舞蹈，只是镜头缓慢后拉。

是**切片器**在舞蹈的大幅运动上误判了 3.33s 有切点（盘点 `inventory.shots` 只有 1 条，
`recipe.shots` 却给出 2 条）。§56 我加的那句把它当既定事实写进了提示词：

```
在@视频1第 3.33 秒的切镜点切镜，主体仍是@图片1、@图片2中的人物。
```

模型收到"切镜"就必须生成一个新镜头；新镜头**没有原片可依**，只能从参考图取材
→ 搬来 `@图片2` 的庭院。

### 依据

`:251`「按时间轴或故事线分段写…**以切镜 shot 作为时间戳的分段**」
——盘点只给了一个 shot，官方意义上就只有一个镜头，**不该分段**。

切片器的切点是**内部实现数据**，不是官方输入。盘点几段就写几段。

### 改了什么（`h3_compile.py`）

`len(_scales) == 1` 分支里，`if _cuts:` 补切点句整段删除（留注释说明为什么撤）。
`len(_scales) >= 2`（盘点真给了多镜）那条分支**原样保留**。

### 判据同步反转

- `p10_check.py` C16：原「单段景别 + 有切点 → 补切点句」→ 改成
  「盘点只有 1 个 shot → **不补切点**、不编第二镜景别」。
- `test_edit_spec_h3.py` 新增「盘点 1 个 shot → 不补切点」一条。

### 验过什么

`h3_matrix_check` 18/18 · `h3_real_matrix_check` 43/43 · `p10_check --model h3` 44/44 ·
`test_edit_spec --model h3` 63/63。

### 现在死活

**未出片。** 下一次出片只动了这一个变量（切镜句没了），其余与 §57 逐字相同。
看两件事：①两镜（现在是一段到底）是否全程留在厨房 ②两张脸是否都换了。

---

## §59 维度清单合并成多图一句 → 对应关系丢失，脸一个都没换

### 怎么发现的

主人近距离看 `c8455a93`：「脸真没换，两个都是，只换了衣服」。
我以为换了 —— 被换掉的服装和发型骗了。用工具复核：

| 成片时间 | 脸 vs `subject.jpg` | 脸 vs `ref_person2.jpg` |
|---|---|---|
| 0.3s | 0.183 / 0.286 | 0.177 / 0.185 |
| 1.2s | 0.236 / 0.150 | 0.189 / 0.094 |
| 2.0s | 0.316 / 0.036 | 0.342 / 0.050 |
| 2.8s | 0.216 / 0.254 | 0.225 / 0.129 |

全部 0.03–0.34。§46 单人成功那次是 **0.415**（阈值 0.363）。**脸一个都没换。**

### 根因：我 §57 自己写的一句

```
@视频1中画面左侧的人物换成@图片1中的人物，@视频1中画面中央的人物换成@图片2中的人物。
替换后的人物在脸、发型…上与@图片1、@图片2保持一致。   ← 这句
```

第二行把两个人**合并成一个集合**，抹掉了「左侧→图1、中央→图2」的对应。
模型拿到的是"要跟这两张图一致"，取不了交集 → 只执行最显眼、最容易的那件事：
换服装、换发型，脸留着原片的。

反证：官方 `:213`「视频1中最后面的小孩换成图1中的金毛狗，**视频1中最左边**小孩穿的
卡其色外套改成图2中的牛仔外套」——**每个分句都重带 `视频1中`**，逐句对应，从不合并。
单人时不存在合并问题，所以 §46 能成功；双人一合并就塌。

### 改了什么（`h3_compile.py`）

维度**跟人绑定，一人一句**：

```
@视频1中画面左侧的人物换成@图片1中的人物，替换后该人物的脸、发型、体型比例、服装设计和材质细节与@图片1保持一致。
@视频1中画面中央的人物换成@图片2中的人物，替换后该人物的脸、发型、体型比例、服装设计和材质细节与@图片2保持一致。
```

删掉原来那套 `_plain_n` / `_wd_n` 分组 + 合并句的写法。
勾了换装的人仍然走"去掉服装设计"的维度（`_wd_all or pid in _wd_ids`）。

### 判据

- `test_edit_spec_h3.py`：维度断言改成绑定本人图号；**新增**「不许合并成
  `与@图片1、@图片2保持一致`」一条（这条就是本次翻车的形状）。
- `p10_check.py` A6：换人句后面现在是逗号不是句号，断言同步。

### 验过什么

`h3_matrix_check` 18/18 · `h3_real_matrix_check` 43/43 · `p10_check --model h3` 44/44 ·
`test_edit_spec --model h3` 64/64。

### 现在死活

**未出片。** 本轮只动了「维度句合并 → 一人一句」这一个变量
（切镜句仍是 §58 撤掉的状态）。

⚠️ 还剩一个未验证的怀疑：`@图片N` 用途句里服装描述占了大半
（「…单肩露肤修身收腰高开叉层叠薄纱拖尾礼服；身形高挑纤瘦修长」），
可能继续把模型往"换衣服"上引。` :248` 官方词是「人物参考（**锁定脸/形象**）」、
`:264` 是「锁这位女子的**脸**」——官方锁的是脸。**这轮先不动**，等这一版出片再说。

---

## §60 素材用途句砍掉服装/身形，只锁「脸 + 气质 + 发型」

主人 2026-11-04：「这个确实有点问题呀，哪里有这么详细的呢？现在新出的那个脸在换上与
没换上之间来回跳，肉眼可以看出明显区别」；「看图看得**发型是最容易看出换没换**」。

### 改前

```
@图片1：人物参考（锁定图中人物的脸；鹅蛋脸，柔长眼型，高挺鼻梁，饱满淡红唇形，
        佩戴垂坠镶钻耳饰；气质明艳柔媚；深棕黑色蓬松大波浪长卷发；
        单肩露肤修身收腰高开叉层叠薄纱拖尾礼服；身形高挑纤瘦修长）。
```

脸只占 1/5，其余是气质、发型、**整套礼服**、身形。具体词比维度名强势 →
模型把"换人"执行成"换衣服"，脸在换与不换之间跳。

### 依据（分工）

- 用途句 = `:248`「人物参考（**锁定脸/形象**）」、`:264`「锁这位女子的**脸**」→ 锁脸。
- 服装设计、体型比例 = `:142` 列给**【核心创意】维度清单**的，不该在用途句里
  重复一遍、还写得更具体。同一件事在两处写，一具体一抽象，模型照具体的做。

### 改后

```
@图片1：人物参考（锁定图中人物的脸；鹅蛋脸，柔长眼型，高挺鼻梁，饱满淡红唇形，
        佩戴垂坠镶钻耳饰；气质明艳柔媚；深棕黑色蓬松大波浪长卷发）。
@图片2：人物参考（锁定图中人物的脸；流畅鹅蛋脸型，狭长柔媚桃花眼，高挺鼻梁，
        饱满红唇，无佩戴眼镜；面部气质柔媚温婉；乌黑发色，梳成高耸规整的古风盘发发髻，
        发髻点缀多枚金色小花造型发饰）。
```

实现：`h3_compile._face_only()` —— 描述按 `；` 分段（脸；气质；发型；服装；身形），
剔掉命中服装词 / 身形词的段。剔完为空就原样返回（宁可多留，不清空）。

**发型一定留** —— 它是肉眼判断换没换最灵敏的一项（主人 2026-11-04），
官方 `:65`「保持人物一致：白金色长发、窄黑色复古墨镜…」、
`:128`「保持黑色半扎长发、银色镂空发冠…一致」也都细写发型。

### 判据

`test_edit_spec_h3.py` 新增两条：「用途句不写服装/身形」「用途句保留发型」。

### 验过什么

`h3_matrix_check` 18/18 · `h3_real_matrix_check` 43/43 · `p10_check --model h3` 44/44 ·
`test_edit_spec --model h3` 66/66 · `test_subject_look --model h3` 21/21。

### 现在死活

**未出片。** 本轮变量：用途句去掉服装/身形。

---

## §61 撤回 §60 之后那次「恢复完整描述 + 加 `:284` 闸」

主人 2026-11-04：「整句话不适用，然后脸那里和核心创意你怎么又改回去了呢」。

### 被撤回的是什么

中间我一度改成：用途句写回**完整**描述（含礼服、身形），并在其后加 `:284` 那句
「只参考指定维度，不直接复制参考图，不出现真实品牌、原参考图 logo/标题/可识别文字。」，
核心创意删掉维度清单。

**两个理由都不成立：**

1. **`:284` 那句整句不适用**（主人判定）。它出自第四章「特定风格·提示词示意」的
   大字幕 MV —— **创作任务**，不是第三章的视频编辑。全手册仅此一处。
2. 删维度清单 = 把 §59 修好的东西改回去。

### 现在的状态（= §60）

```
【参考素材说明】
@图片1：人物参考（锁定图中人物的脸；<脸；气质；发型>）。      ← 不含服装/身形
@图片2：人物参考（锁定图中人物的脸；<脸；气质；发型>）。
@视频1：视频编辑素材（对@视频1中的内容进行增删改）。
@音频1：音频复用素材（生成视频的音频直接复用参考音频素材）。

【核心创意】
@视频1中画面左侧的人物换成@图片1中的人物，替换后该人物的脸、发型、体型比例、服装设计和材质细节与@图片1保持一致。
@视频1中画面中央的人物换成@图片2中的人物，替换后该人物的脸、发型、体型比例、服装设计和材质细节与@图片2保持一致。

【画面过程说明】
0-5.3 秒：Medium full shot。
```

- 用途句：`_face_only()` 剔掉服装/身形，只留脸、气质、发型（§60）。
- 核心创意：一人一句、维度绑本人图号（§59）。
- **没有** `:284` 闸句、**没有** `:133` 保留清单、**没有**切镜句（§58）。

### 判据

`h3_matrix_check` 18/18 · `h3_real_matrix_check` 43/43 · `p10_check --model h3` 44/44 ·
`test_edit_spec --model h3` 66/66 · `test_subject_look --model h3` 21/21。

### 现在死活

**未出片。**

---

## §62 回到 v7（`67285c2f`）+ 我为什么会来回横跳

### 出片结果把 §60 / §61 都否掉了

| 版本 | 提示词配置 | 前半段 | 后半段 |
|---|---|---|---|
| v7 `67285c2f` | 完整描述 + 维度清单 + 时间轴 + `▍` 分组 | 衣服/发型换了，**脸部分换上** | 厨房 ✓ |
| v8 `9135cdd7` | §60 的 `_face_only()`（剔掉服装/身形） | **什么都没变** | 厨房 ✓ |

主人判 v7「最接近成功」。v8 的教训：**模型靠大色块（服装、发型）定位"要改哪里"**，
把服装描述剔掉 = 抽掉锚点 = 一个像素都不动。原话「这次又是没有任何变化了」。

### 现在恢复成 v7，只留一处改动

```
【参考素材说明】
@图片1：人物参考（锁定脸/形象；<完整描述，含发型/服装/身形>）。
@图片2：人物参考（锁定脸/形象；<完整描述>）。
@视频1：视频编辑素材（对@视频1中的内容进行增删改）。
@音频1：音频复用素材（生成视频的音频直接复用参考音频素材）。

【核心创意】
@视频1中画面左侧的人物换成@图片1中的人物，替换后该人物的脸、发型、体型比例、服装设计和材质细节与@图片1保持一致。
@视频1中画面中央的人物换成@图片2中的人物，替换后该人物的脸、发型、体型比例、服装设计和材质细节与@图片2保持一致。

【画面过程说明】
0-5.3 秒：Medium full shot。

【整体要求补充】
▍镜头（贯穿全片）          严格参考@视频1的镜头节奏和转场风格。
▍人物与动作（贯穿全片）    替换后的人物必须严格遵循原视频的运动轨迹。
▍画面融合（贯穿全片）      确保替换后的人物质感和光影与环境融合。
```

- 相对 v7 的唯一差别：用途句 `锁定图中人物的脸` → **`锁定脸/形象`**
  （`:248` 素材用途表原文就是「人物参考（**锁定脸/形象**）」，两个词；`:264`
  的「锁这位女子的脸」是示例简称，不是完整用途名）。
- 恢复的三块各自有出处：维度清单 `:142`、时间轴 `:251`、`▍` 分组 `:284`。

### 我为什么来回横跳（主人问的原话：为什么你会来回横跳呢）

因为我把「一次出片不好」当成了「这条有出处的规则错了」，于是删规则；
下一次又照着出处把它加回来。**删和加都只凭一轮出片结果，没有判据。**

立一条规矩（写进本文件，后面照办）：

> **删一条内容，必须先指出它错在哪、错在哪一行/哪个病句。**
> 指不出 = 出片不好是**别的变量**（本次就是"两句合成一句"毁了图号对应，
> 与维度清单无关），不许拿内容开刀。
> 反过来，加一条内容必须有 `:行号`，加完一次只改这一个变量。

### 判据（现锁 v7 形态）

`test_edit_spec_h3.py`：「维度句在、且绑定本人图号」+「维度不合并成多图一句」
（`与@图片1、@图片2保持一致` 必须没有）。
`h3_matrix_check.py` MUST["A"] 加回 `【整体要求补充】` / `▍人物与动作（贯穿全片）`
（`:284` 全例结尾那组追加约束）。

`h3_matrix_check` 18/18 形态通过 · `h3_real_matrix_check` 43/43 真实组合通过 ·
`p10_check --model h3` 44/44 通过 · `test_edit_spec --model h3` 66/66 通过 ·
`test_subject_look --model h3` 21/21 通过。

### 顺手清掉的死代码

`_face_only()` + `_CLOTHING` / `_BODY` 已从 `h3_compile.py` **删除**（全工程 grep 只剩定义、
零调用）。留着它，下一个接手的人会以为"剔服装"还在生效 —— 那正是本次横跳的成因。
§60/§61 原样留在上面当历史，别照 §60 实现。

### 现在死活

**未出片。** 本轮变量只有一：用途句 `锁定图中人物的脸` → `锁定脸/形象`。
其余全部 = v7。

---

## §63 定妆描述补「鞋」，版本升 v5（主人：怕有鞋子的镜头没换上）

主人 2026-11-04：「以后直接统一用最新版的，然后完整度【含礼服、鞋、身形】要和成功版一样，
主要就是怕有鞋子的镜头没换上」。

### 查出的事实

`data/clone/*/subject_desc*.json` 共 **35 份**，只有 **3 份**写了鞋
（`cb7a6ea1` / `dad130d5` / `f35fadf1`）—— 而且**全是 v4**。
所以不是版本问题，是提问里没把鞋列成必写项，模型有时写有时不写。
唯一换脸成功那次 `cb7a6ea1` 的描述恰好有「搭配露趾细高跟凉鞋」。

### 改了什么（`vision_plan.py`）

1. `_DESC_ASK` 第 4 项（clothing silhouette）补一句：
   「**鞋也要写**（款式 + 颜色，如「露趾细高跟凉鞋」）……**看不出来就不写，不要猜**」。
   出处：`co-op-game-intro-generator/SKILL.md:34` 的 outfit dimensions 里列着
   `brown boots`；`3d-animation-short-generator/SKILL.md:147` 把 `shoes` 列进
   「重要标注项」。
2. `_DESC_VERSION` **4 → 5**：老描述作废重算。`video_edit.py:1045` 的 stale 检查会
   在下次出片时补算，**每张人物图多一次视觉调用（几厘）**，算完写回缓存。

### 判据

`scripts/test_vision_plan.py` 新增两条（描述提问里点名要写鞋 / 版本号 ≥5）。

`test_vision_plan --model h3` **44/44** · `test_edit_spec --model h3` 66/66。

### 现在死活

**未出片。** 本单两张定妆图下次出片时会重算描述（各自一次视觉调用）。
