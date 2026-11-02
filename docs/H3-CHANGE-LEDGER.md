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
