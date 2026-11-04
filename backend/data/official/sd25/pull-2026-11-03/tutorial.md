# Doubao Seedance 2.5 教程

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

Doubao Seedance 2.5（下文简称 Seedance 2.5）是新一代视频创作模型，在长叙事能力、全模态参考能力和编辑能力上全面提升。单次生成时长提升至 30 秒并支持多轮延长，单次参考多模态素材上限提升至 50 个，提供基于时间戳的精准编辑控制。画面质感全面优化，成片更接近实拍的影视质感。本文介绍 Seedance 2.5 模型的特色能力与使用方法，帮助您快速实现 [创建视频生成任务 API](/docs/create-video-generation-task-api) 调用。

> **说明：模型开通条件**
>
> 开通 Seedance 2.5 模型前，请确保您满足以下任一条件：
> * **【推荐】账户余额 > 200 元**（[前往充值](https://console.volcengine.com/finance/fund/recharge)）
> * **【推荐】购买 200 元档位及以上专属节省计划**，购买入口：[购买节省计划](https://console.volcengine.com/common-buy/AI-SavingsPlans%7C%7Cd682ppeeq1mp7kd5q0e0)。
> * 已购买 Seedance 2.5 系列资源包且有可用余量 （[前往购买](https://console.volcengine.com/common-buy/ark_bd%7C%7Cd9li7rchmjlhari755h0)）
>
> 详细规则见 [Seedance 2.5 与 Seedance 2.0 系列模型开通、使用与退订说明](/docs/seedance-model-activation-usage-and-refund)。

<span id="2.5_compatibility"></span>
# 使用前必读

> **警告**
>
> Seedance 2.5 模型在视频编辑、首帧/首尾帧、视频延长任务下存在特殊限制，如不遵循将触发 [报错](/docs/seedance-2-5#2.5_error_handling)。
>
> **请务必在调用模型前仔细阅读下文，确保任务类型、提示词意图和参数配置一致。**

<span id="2.5_task_type_intro"></span>
## 任务类型与限制

Seedance 2.5 会根据输入素材和提示词意图判断任务类型。任务类型包括文生视频、首帧/首尾帧生视频，以及**全模态参考生视频任务**；其中全模态参考生视频任务根据提示词意图进一步分为参考生视频、视频编辑和视频延长 3 类子任务。

|任务类型 ||触发条件 |特殊限制 |
|---|---|---|---|
|文生视频 ||仅传入文本提示词 | `ratio` / `duration` 无特殊限制 |
|首帧/首尾帧生视频 ||`content.role` 设置为 `first_frame` / `last_frame` |`ratio` 必须为 `adaptive` | \
| | | |<blockquote>模型自动保持输出视频宽高比和 `first_frame` 指定的首帧图片一致</blockquote> |
|全模态生视频任务 |参考生视频 |`content` 中至少包含一个 `role` 为 `reference_image`、`reference_video` 或 `reference_audio` 的参考素材 |`ratio` / `duration` 无特殊限制 |
|^^ |视频编辑 |`content` 中至少包含一个 `role` 为 `reference_video` 的参考视频，并通过提示词表达编辑意图 |* `ratio` 必须为 `adaptive`、`duration` 必须为 `-1`  | \
| | | |<blockquote>模型根据提示词意图选定待编辑视频，并自动保持输出视频宽高比、时长和待编辑视频一致</blockquote> | \
| | | |* 参考视频时长必须为 4-30 秒 |
|^^ |视频延长 |`content` 中至少包含一个 `role` 为 `reference_video` 的参考视频，并通过提示词表达延长意图 |`ratio` 必须为 `adaptive` | \
| | | |<blockquote>模型根据提示词意图选定待延长视频，并自动保持输出视频宽高比和待延长视频一致</blockquote> |

> **注意**
>
> 为减少因特殊限制触发的异步报错，全模态参考生视频任务可通过配置`omni_reference_task_type`显示引导任务类型将报错前置，具体参考下文配置方法。

<span id="2.5_param_constraints"></span>
## 配置方法

### 全模态参考生视频（不区分子任务）
对于全模态参考生视频任务，如果您没有明确区分具体的子任务类型，**推荐按以下方式配置参数**：

1. `omni_reference_task_type` 设置为 `auto`。
2. `content.role` 设置为 `reference_image`、`reference_video` 或 `reference_audio`。
3. 推荐将 `ratio` 设置为 `adaptive`、`duration` 设置为 `-1`。如果传入参考视频，建议单个参考视频时长为 4–30 秒。

> **说明**
>
> `omni_reference_task_type` 设置为 `auto` 时，模型根据提示词意图，可能将任务判定为参考生视频、视频编辑、视频延长任务。其中视频编辑、视频延长任务对配置参数有特殊限制。**按推荐方式配置，可以兼容这些限制，减少任务创建后触发 [异步报错](/docs/seedance-2-5#2.5_async_error)**。

### 视频编辑
> 对原视频的画面或音频进行编辑操作，如替换视频主体、增删视频中对象、局部画面重绘或修复等

对于明确的视频编辑类任务，推荐以下**配置方法:**
1. `omni_reference_task_type` 设置为 `edit`。
2. `content` 中至少包含一个 `role` 为 `reference_video` 的参考视频。
3. `ratio` 必须为 `adaptive`；`duration` 必须为 `-1`；参考视频时长必须为 4–30 秒。
4. 提示词中需包含至少一个关键词：编辑视频、增加/加上、删除/去掉、修改/替换/改成。
> 提示词示例：@video1 中加一些小动物；把 @video1 的人物修改为 @image1；删掉 @video1 的背景音乐

### 视频延长
> 对原视频进行向前或向后延长

对于明确的视频延长类任务，推荐以下**配置方法:**
1. `omni_reference_task_type` 设置为 `extend`。
2. `content` 中至少包含一个 `role` 为 `reference_video` 的参考视频。
3. `ratio` 必须为 `adaptive`。
4. 提示词中需包含至少一个关键词：向前/向后延长、延续、续写。
> 提示词示例：向后延长 @video1，@image1 的角色从天而降...；续写 @video1 前 5s，@video2 女人入画说...

### 首帧/首尾帧生视频
> 输入 1 张图作为首帧生成视频，或输入 2 张图分别作为首帧和尾帧生成视频
1. `content` 中需包含 `role` 为 `first_frame` 的图片；首尾帧生视频还需包含 `role` 为 `last_frame` 的图片。
2. `ratio` 必须为 `adaptive`。

<span id="2.5_error_handling"></span>
## 报错机制

Seedance 2.5 存在以下两种参数校验与报错机制。

<span id="2.5_sync_error"></span>
### 同步报错（提交任务时）
* 对于全模态参考生视频任务，显式指定 `omni_reference_task_type` 为 `edit` 或 `extend` 时，接口将前置校验特殊参数限制，若不符合要求，接口立即返回错误。

> **注意**
>
> 实际处理任务时，模型仍会进一步结合提示词判断任务类型。若实际判定的任务类型和指定的不一致，仍会触发异步报错（错误码： [`InvalidParameter.TaskTypeMismatch`](/docs/error-codes)）。建议遵循各任务类型提示词写法，降低报错概率。

<span id="2.5_async_error"></span>
### 异步报错（任务启动后）
* 对于全模态参考生视频任务，未传入 `omni_reference_task_type` 或将其设置为 `auto` 时，模型先根据输入素材和提示词判断实际任务类型，再校验该类型的特殊参数限制。不符合要求时，任务异步报错。

* 对于首帧/首尾帧生视频，参数配置不符合任务特殊限制时，任务异步报错

> **说明**
>
> 因参数配置和任务类型不兼容导致的异步报错，错误码：[`InvalidParameter.TaskTypeConstraint`](/docs/error-codes)。

<span id="2.5_quick_start"></span>
# 新手入门

> **说明**
>
> * 若您是编程零基础用户，推荐使用 [控制台体验中心](https://ark.volcengine.com/region:cn-beijing/experience/gen_video?model=doubao-seedance-2-5-260628)，包含丰富的模板库，可一键生成同款视频，无需编写代码即可快速上手创作。
> * 若您想快速体验 API 调用，推荐使用<a href="https://api.volcengine.com/api-explorer/?action=CreateContentsGenerationsTasks&groupName=%E8%A7%86%E9%A2%91%E7%94%9F%E6%88%90API&serviceCode=ark&version=2024-01-01">API Explorer</a>，内置预设参数模板，可一键发起 API 调用；同时也支持灵活调整参数（例如设置视频水印等），满足多样化的测试和使用场景。
> * 若您想真正开始编程开发，但苦于搭建开发环境、依赖安装等问题，推荐阅读本节内容。

本入门教程专为 **API 新手用户** 设计，帮助您一键搭建  Python  开发环境、完成虚拟环境创建和方舟 SDK 安装，并提供直接可运行的 Seedance 2.5 调用代码，您只需修改对应的输入素材，即可开始您的视频生成创作。
**1. 准备工作**
在开始之前，请确保您已经完成以下准备：
1. **注册账号**：确保您拥有火山引擎账号并已 [登录](https://console.volcengine.com/)。
2. **获取 API Key**：访问 [API Key 管理页面](https://ark.volcengine.com/region:cn-beijing/apikey)，点击 **创建 API Key**，并复制保存您的 API Key。注意请妥善保管您的 API Key，不要泄露给他人。
3. [**开通模型**](https://ark.volcengine.com/region:cn-beijing/openManagement?LLM=%7B%7D&advancedActiveKey=model&projectName=default&tab=ComputerVision)：请确保您的账户余额大于等于 200 元，或已 [购买资源包](https://console.volcengine.com/common-buy/ark_bd%7C%7Cd9li7rchmjlhari755h0)，否则无法开通 Seedance 2.5 模型。
4. **下载并解压文件**：点击下载下方附件，将其解压到您的本地目录（如桌面或“下载”文件夹）。

    [ark_seedance2.5_quickstart_package.zip](https://arkdocs.tos-cn-beijing.volces.com/files/video-generation/ark_seedance2.5_quickstart_package_arkruntime-20260909.zip)

**2.操作步骤**

**选项：Windows 用户**

1. 进入 `scripts/init_dev_env` 目录。
2. 双击运行 `setup_windows.bat`。
3. 脚本会自动执行以下操作：

    * 下载 uv 工具。

    * 自动下载 Python 3.12（如果不干扰您的系统 Python）。

    * 创建虚拟环境 .`venv`。

    * 安装方舟 SDK。
4. 完成后，在项目根目录会生成一个 `run_demo.bat`。
5. 双击 `run_demo.bat`，即可运行 Python SDK 示例代码(python/demo_standard.py)。

**选项：macOS 用户**

1. 打开终端，进入 `scripts/init_dev_env` 目录。
2. 运行构建脚本：

    ```Plain Text
    ./setup_mac.sh
    ```

3. 脚本会自动配置好所有环境。
4. 完成后，在项目根目录会生成一个 `run_demo.sh`。
5. 运行 `./run_demo.sh` 即可运行 Python SDK 示例代码(python/demo_standard.py)。

**3.运行说明**
运行脚本后，您将看到如下流程：
1. **API Key 校验**：脚本会自动检测您本地是否配置了`ARK_API_KEY`环境变量。如果没有，会提示您手动输入。
2. **素材预览**：脚本会自动在您的默认浏览器中弹出一个本地生成的 HTML 页面，直观地展示本次任务的文本提示词、待替换的参考图片以及原始参考视频。
3. **任务创建与轮询**：脚本向火山方舟服务器发起异步请求。由于视频生成需要一定时间，控制台会每隔 30 秒打印一次任务状态（如 `running`等）。
4. **获取结果**：任务成功后，控制台会输出一段最终生成的视频 URL。您可以复制该链接到浏览器下载或在线播放。

**4.下一步**
在成功跑通本示例后，您可以尝试修改 `python/``demo_standard.py`，来打造您专属的视频生成任务：
1. 修改文本提示词

找到代码中的 `user_content` 变量，更改为您想要的画面描述。
2. 替换输入素材 (图片、视频、音频)

您可以将 `reference_image_url`、`reference_video_url` 和 `reference_audio_url` 替换为您自己的素材链接。
**注意**：请确保 URL 是公网可公开访问的链接（建议存放在 TOS 对象存储服务中，并配置为公共读。详细介绍请参见 [TOS 数据订阅](https://docs.volcengine.com/docs/TorchObjectStorage/Datasubscription-5?lang=zh)）。
3. 继续学习下文中丰富的使用示例。

<span id="2.5_latest_capability"></span>
# 最新能力

<div style="min-height: 260px;">

**[生成视频时长翻倍](/docs/seedance-2-5#2.5_30s_video)**

* 生成视频时长上限由 15 秒延长至 30 秒。

</div>

<div style="min-height: 260px;">

**[参考素材数量增加](/docs/seedance-2-5#2.5_50_reference)**

* 参考图数量上限由 9 张增至 30 张，
* 参考音/视频数量上限由 3 个增至 10 个
* 参考音/视频总时长由 15 秒增至 30 秒

</div>

<div style="min-height: 260px;">

**[更智能的宽高比/时长控制](/docs/seedance-2-5#2.5_smart_ratio_duration)**

* 视频编辑任务，自动保持输出视频的宽高比、时长和输入视频一致。
* 视频延长、首帧/首尾帧任务，自动保持输出视频的宽高比和输入视频一致。

</div>

<div style="min-height: 140px;">

**[新增 mov 输出格式](/docs/seedance-2-5#2.5_output_format)**

* 输出视频新增 mov 格式（H.264 视频编码 + yuv444p 色度采样 + PCM 音频编码），提升视频编辑和视频延长场景下的色彩保真度与声画一致性。

</div>

<div style="min-height: 140px;">

**[原生多语言](/docs/seedance-2-5#2.5_multi_language)**

* 支持中文、英语、西班牙语、印度尼西亚语、马来语、泰语、阿拉伯语、葡萄牙语、越南语、日语、韩语等 11 种语言。

</div>

<span id="2.5_capability_overview"></span>
# 能力概述

|模型名称 | |[Seedance 2.5](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedance-2-5&projectName=default) |[Seedance 2.0](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedance-2-0&projectName=default) |[Seedance 2.0 fast](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedance-2-0-fast&projectName=default) |[Seedance 2.0 mini](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedance-2-0-mini&projectName=default) |
|---|---|---|---|---|---|
|Model ID | |doubao-seedance-2-5-260628 |doubao-seedance-2-0-260128 |doubao-seedance-2-0-fast-260128 |doubao-seedance-2-0-mini-260615 |
|[文生视频](/docs/video-generation-tutorial#4e74bcee) | |✓ |✓ |✓ |✓ |
|[首帧生视频](/docs/video-generation-tutorial#979b2d28) | |✓ |✓ |✓ |✓ |
|[首尾帧生视频](/docs/video-generation-tutorial#0d55ca07) | |✓ |✓ |✓ |✓ |
|[全模态参考](/docs/seedance-2-5#2.5_50_reference) |图片参考 |✓ |✓ |✓ |✓ |
|^^| | | | | | \
| |视频参考 |✓ |✓ |✓ |✓ |
|^^| | | | | | \
| |音频参考 |✓ |✗（需搭配图片/视频） |✗（需搭配图片/视频） |✗（需搭配图片/视频） |
|^^| | | | | | \
| |组合参考 |✓ |✓ |✓ |✓ | \
| | | | | | | \
| |* 图片 + 音频 | | | | | \
| |* 图片 + 视频 | | | | | \
| |* 视频 + 音频 | | | | | \
| |* 图片 + 视频 + 音频 | | | | |
|[编辑视频](/docs/seedance-2-5#2.5_edit) | |✓ |✓ |✓ |✓ |
|[延长视频](/docs/seedance-2-5#2.5_extend) | |✓ |✓ |✓ |✓ |
|[生成有声视频](/docs/seedance-2-5#2.5_multi_language) | |✓ |✓ |✓ |✓ |
|参考素材数量上限 | |50（30张图+10个视频+10个音频） |15（9张图+3个视频+3个音频） |15（9张图+3个视频+3个音频） |15（9张图+3个视频+3个音频） |
|[联网搜索工具](/docs/seedance-2-0#c40ed3ef) | |✓ |✓ |✓ |✓ |
|[样片模式](/docs/seedance-2-5#2.5_draft_mode) | |✓ |✗ |✗ |✗ |
|[返回尾帧](/docs/video-generation-tutorial#141cf7fa) | |✓ |✓ |✓ |✓ |
|[输出视频规格](/docs/seedance-2-5#2.5_video_output_specs) |[输出分辨率](/docs/seedance-2-5#2.5_resolution) |* 480p（8bit 位深） |* 480p（8bit 位深） |* 480p（8bit 位深） |* 480p（8bit 位深） | \
| | |* 720p（8bit 位深） |* 720p（8bit 位深） |* 720p（8bit 位深） |* 720p（8bit 位深） | \
| | |* 1080p（10bit 位深） |* 1080p（8bit 位深） | | | \
| | | |* 4k（10bit 位深） | | |
|^^ |[输出宽高比](/docs/seedance-2-5#2.5_ratio) |21:9, 16:9, 4:3, |21:9, 16:9, 4:3, |21:9, 16:9, 4:3, |21:9, 16:9, 4:3, | \
| | | 1:1, 3:4, 9:16, adaptive | 1:1, 3:4, 9:16, adaptive | 1:1, 3:4, 9:16, adaptive | 1:1, 3:4, 9:16, adaptive |
|^^ |[输出时长](/docs/seedance-2-5#2.5_duration) |4~30 秒；-1（在有效时长内由模型自动选择最佳时长） |4~15 秒；-1（在有效时长内由模型自动选择最佳时长） |4~15 秒；-1（在有效时长内由模型自动选择最佳时长） |4~15 秒；-1（在有效时长内由模型自动选择最佳时长） |
|^^ |[输出视频格式](/docs/seedance-2-5#2.5_output_format) |mp4, mov |mp4 |mp4 |mp4 |
|[离线推理](/docs/video-generation-tutorial#c3588bd1) | |✗ |✗ |✗ |✗ |

<span id="2.5_featured_capabilities"></span>
# 特色能力

<span id="2.5_30s_video"></span>
## 30 秒视频连贯直出

Seedance 2.5 视频生成时长上限由 Seedance 2.0 系列的 15 秒延长至 30 秒，支持一次性生成长达 30 秒的连贯视频，无需多段拼接即可呈现完整故事。

|输入：文本 + 8 张图片 ||||输出 |
|---|---|---|---|---|
|<div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 24px;">![](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference1.png)![](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference2.png)![](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference3.png)![](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference4.png)![](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference5.png)![](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference6.png)![](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference7.png)![](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference8.png)<blockquote style="grid-column: 1 / -1;">提示词：一镜到底，镜头平稳跟随一个穿黑色大衣的人从左向右穿过六个相连的不同色调、不同氛围的房间...（详见下方代码示例中的完整提示词）</blockquote></div> ||||[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_30s_output1.mp4) |

**选项：Curl**

```Bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-5-260628",
    "content": [
        {
            "type": "text",
            "text": "一镜到底，镜头平稳跟随一个穿黑色大衣的人（参考【图片 1】）从左向右穿过六个相连的不同色调、不同氛围的房间。每个房间结构相同：白墙、人字拼浅色木地板、法式双开落地窗、白纱帘，参考【图片 2】但窗外风景和室内氛围完全不同。主角全程匀速走动，穿过墙壁上敞开的每一扇门。0-5秒，第一个房间，主题为美漫打斗，主角进入屋内与人物（【图片 3】）打斗，人物落败；5-10秒，第二个房间，主题为温暖，毛毡风格，窗外场景为向日葵田（【图片 4】），室内光线暖橙柔光，有一个画家正在画向日葵（【图片 5】）。主角进入后也变成毛毡风格；10-15秒，第三个房间，主题为悲伤，整个画面为黑白漫画定格动画风格，窗外阴雨，室内光线冷灰低沉，一个人独自坐在空房间中央地板上，低头抱膝，身旁一只手机亮着无人接听的通话界面。主角进入房间后关上房间的灯，马上开灯，房间内变为彩色，瞬间生长出满屋鲜花；15-20秒，第四个房间，主题为欢乐，整个场景为浸泡在海里的房间，参考【图片 6】，主角游进房间，身旁有美丽的珊瑚礁和鱼群；20-25秒，第五个房间，主题为惊喜，窗外场景漫天烟花夜空，参考【图片 7】，室内光线彩色闪烁映射，主角被卷入欢呼气氛。25-30秒，最后主角来到一个空白房间，站在中央打了个响指，同时音效为响指声，画面整体黑屏，中间出现“seedance”字样，参考【图片 8】。整体电影质感，高级时装广告风格，光线完全由窗外场景决定形成强烈情绪反差，画面无文字。"
        },
        {
            "type": "image_url",
            "role": "reference_image",
            "image_url": {
                "url": "asset://asset-20260831133727-94rtr"
            }
        },
        {
            "type": "image_url",
            "role": "reference_image",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference2.png"
            }
        },
        {
            "type": "image_url",
            "role": "reference_image",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference3.png"
            }
        },
        {
            "type": "image_url",
            "role": "reference_image",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference4.png"
            }
        },
        {
            "type": "image_url",
            "role": "reference_image",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference5.png"
            }
        },
        {
            "type": "image_url",
            "role": "reference_image",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference6.png"
            }
        },
        {
            "type": "image_url",
            "role": "reference_image",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference7.png"
            }
        },
        {
            "type": "image_url",
            "role": "reference_image",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference8.png"
            }
        }
    ],
    "generate_audio": true,
    "ratio": "16:9",
    "duration": 30,
    "watermark": true
}'
```

**选项：Python**

```Python
import os
import time
# Install SDK: python -m pip install --upgrade arkruntime
from arkruntime import Ark

client = Ark(
    # The base URL for model invocation
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    # Get API Key：https://ark.volcengine.com/region:cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    prompt = "一镜到底，镜头平稳跟随一个穿黑色大衣的人（参考【图片 1】）从左向右穿过六个相连的不同色调、不同氛围的房间。每个房间结构相同：白墙、人字拼浅色木地板、法式双开落地窗、白纱帘，参考【图片 2】但窗外风景和室内氛围完全不同。主角全程匀速走动，穿过墙壁上敞开的每一扇门。0-5秒，第一个房间，主题为美漫打斗，主角进入屋内与人物（【图片 3】）打斗，人物落败；5-10秒，第二个房间，主题为温暖，毛毡风格，窗外场景为向日葵田（【图片 4】），室内光线暖橙柔光，有一个画家正在画向日葵（【图片 5】）。主角进入后也变成毛毡风格；10-15秒，第三个房间，主题为悲伤，整个画面为黑白漫画定格动画风格，窗外阴雨，室内光线冷灰低沉，一个人独自坐在空房间中央地板上，低头抱膝，身旁一只手机亮着无人接听的通话界面。主角进入房间后关上房间的灯，马上开灯，房间内变为彩色，瞬间生长出满屋鲜花；15-20秒，第四个房间，主题为欢乐，整个场景为浸泡在海里的房间，参考【图片 6】，主角游进房间，身旁有美丽的珊瑚礁和鱼群；20-25秒，第五个房间，主题为惊喜，窗外场景漫天烟花夜空，参考【图片 7】，室内光线彩色闪烁映射，主角被卷入欢呼气氛。25-30秒，最后主角来到一个空白房间，站在中央打了个响指，同时音效为响指声，画面整体黑屏，中间出现“seedance”字样，参考【图片 8】。整体电影质感，高级时装广告风格，光线完全由窗外场景决定形成强烈情绪反差，画面无文字。"
    reference_images = [
        "asset://asset-20260831133727-94rtr",
        "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference2.png",
        "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference3.png",
        "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference4.png",
        "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference5.png",
        "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference6.png",
        "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference7.png",
        "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference8.png",
    ]
    content = [{"type": "text", "text": prompt}]
    content.extend(
        {
            "type": "image_url",
            "role": "reference_image",
            "image_url": {"url": image_url},
        }
        for image_url in reference_images
    )

    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-5-260628",  # Replace with Model ID
        content=content,
        generate_audio=True,
        ratio="16:9",
        duration=30,
        watermark=True,
    )
    print(create_result)

    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    deadline = time.monotonic() + 30 * 60
    while time.monotonic() < deadline:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            raise RuntimeError(f"Video generation task failed: {get_result.error}")
        else:
            print(f"Current status: {status}, Retrying after 30 seconds...")
            time.sleep(30)
    else:
        raise TimeoutError("Video generation task did not finish within 30 minutes")
```

**选项：Java**

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.models.content_generation.*;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();

    public static void main(String[] args) {

        // Model ID
        final String modelId = "doubao-seedance-2-5-260628";
        // Text prompt
        final String prompt = "一镜到底，镜头平稳跟随一个穿黑色大衣的人（参考【图片 1】）从左向右穿过六个相连的不同色调、不同氛围的房间。每个房间结构相同：白墙、人字拼浅色木地板、法式双开落地窗、白纱帘，参考【图片 2】但窗外风景和室内氛围完全不同。主角全程匀速走动，穿过墙壁上敞开的每一扇门。0-5秒，第一个房间，主题为美漫打斗，主角进入屋内与人物（【图片 3】）打斗，人物落败；5-10秒，第二个房间，主题为温暖，毛毡风格，窗外场景为向日葵田（【图片 4】），室内光线暖橙柔光，有一个画家正在画向日葵（【图片 5】）。主角进入后也变成毛毡风格；10-15秒，第三个房间，主题为悲伤，整个画面为黑白漫画定格动画风格，窗外阴雨，室内光线冷灰低沉，一个人独自坐在空房间中央地板上，低头抱膝，身旁一只手机亮着无人接听的通话界面。主角进入房间后关上房间的灯，马上开灯，房间内变为彩色，瞬间生长出满屋鲜花；15-20秒，第四个房间，主题为欢乐，整个场景为浸泡在海里的房间，参考【图片 6】，主角游进房间，身旁有美丽的珊瑚礁和鱼群；20-25秒，第五个房间，主题为惊喜，窗外场景漫天烟花夜空，参考【图片 7】，室内光线彩色闪烁映射，主角被卷入欢呼气氛。25-30秒，最后主角来到一个空白房间，站在中央打了个响指，同时音效为响指声，画面整体黑屏，中间出现“seedance”字样，参考【图片 8】。整体电影质感，高级时装广告风格，光线完全由窗外场景决定形成强烈情绪反差，画面无文字。";

        // Example resource URLs
        final String[] referenceImages = {
                "asset://asset-20260831133727-94rtr",
                "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference2.png",
                "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference3.png",
                "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference4.png",
                "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference5.png",
                "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference6.png",
                "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference7.png",
                "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference8.png"
        };

        // Output video parameters
        final boolean generateAudio = true;
        final String videoRatio = "16:9";
        final long videoDuration = 30L;

        System.out.println("----- create request -----");
        // Build request content
        List<ContentItem> contents = new ArrayList<>();

        // 1. Text prompt
        contents.add(ContentItem.builder()
                .type(ContentType.TEXT)
                .text(prompt)
                .build());

        // 2. Reference images
        for (String referenceImage : referenceImages) {
            contents.add(ContentItem.builder()
                    .type(ContentType.IMAGE_URL)
                    .imageUrl(ImageURL.builder()
                            .url(referenceImage)
                            .build())
                    .role("reference_image")
                    .build());
        }

        // Create video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .generateAudio(generateAudio)
                .model(modelId)
                .content(contents)
                .ratio(videoRatio)
                .duration(videoDuration)
                .watermark(true)
                .build();

        CreateContentGenerationTaskResponse createResult = service.createContentGenerationTask(createRequest);
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */

    private static void pollTaskStatus(String taskId) {
        String getRequest = taskId;

        System.out.println("----- polling task status -----");
        try {
            long deadlineNanos = System.nanoTime() + TimeUnit.MINUTES.toNanos(30);
            while (System.nanoTime() < deadlineNanos) {
                ContentGenerationTask getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus().toString();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    return;
                } else if ("failed".equalsIgnoreCase(status)) {
                    throw new IllegalStateException(
                            "Video generation task failed: " + getResponse.getError());
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
            throw new IllegalStateException(
                    "Video generation task did not finish within 30 minutes");
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Polling interrupted", ie);
        } catch (Exception e) {
            throw new RuntimeException("Error occurred while polling", e);
        } finally {
            service.shutdownExecutor();
        }
    }
}
```

**选项：Go**

```Go
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/volcengine/ark-runtime-go/arkruntime"
	model "github.com/volcengine/ark-runtime-go/arkruntime/model/contentgeneration"
)

func main() {
	// Initialize Ark client
	client := arkruntime.NewClientWithApiKey(
		os.Getenv("ARK_API_KEY"),
		// The base URL for model invocation
		arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
	)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	// Model ID
	modelID := "doubao-seedance-2-5-260628"
	// Text prompt
	prompt := "一镜到底，镜头平稳跟随一个穿黑色大衣的人（参考【图片 1】）从左向右穿过六个相连的不同色调、不同氛围的房间。每个房间结构相同：白墙、人字拼浅色木地板、法式双开落地窗、白纱帘，参考【图片 2】但窗外风景和室内氛围完全不同。主角全程匀速走动，穿过墙壁上敞开的每一扇门。0-5秒，第一个房间，主题为美漫打斗，主角进入屋内与人物（【图片 3】）打斗，人物落败；5-10秒，第二个房间，主题为温暖，毛毡风格，窗外场景为向日葵田（【图片 4】），室内光线暖橙柔光，有一个画家正在画向日葵（【图片 5】）。主角进入后也变成毛毡风格；10-15秒，第三个房间，主题为悲伤，整个画面为黑白漫画定格动画风格，窗外阴雨，室内光线冷灰低沉，一个人独自坐在空房间中央地板上，低头抱膝，身旁一只手机亮着无人接听的通话界面。主角进入房间后关上房间的灯，马上开灯，房间内变为彩色，瞬间生长出满屋鲜花；15-20秒，第四个房间，主题为欢乐，整个场景为浸泡在海里的房间，参考【图片 6】，主角游进房间，身旁有美丽的珊瑚礁和鱼群；20-25秒，第五个房间，主题为惊喜，窗外场景漫天烟花夜空，参考【图片 7】，室内光线彩色闪烁映射，主角被卷入欢呼气氛。25-30秒，最后主角来到一个空白房间，站在中央打了个响指，同时音效为响指声，画面整体黑屏，中间出现“seedance”字样，参考【图片 8】。整体电影质感，高级时装广告风格，光线完全由窗外场景决定形成强烈情绪反差，画面无文字。"

	// Example resource URLs
	referenceImages := []string{
		"asset://asset-20260831133727-94rtr",
		"https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference2.png",
		"https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference3.png",
		"https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference4.png",
		"https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference5.png",
		"https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference6.png",
		"https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference7.png",
		"https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_30s_reference8.png",
	}

	// Output video parameters
	generateAudio := true
	videoRatio := "16:9"
	videoDuration := int64(30)

	content := []model.ContentItem{
		{
			Type: model.ContentTypeText,
			Text: model.NewOptString(prompt),
		},
	}
	for _, referenceImage := range referenceImages {
		content = append(content, model.ContentItem{
			Type: model.ContentTypeImageURL,
			ImageURL: model.NewOptImageURL(model.ImageURL{
				URL: referenceImage,
			}),
			Role: model.NewOptString("reference_image"),
		})
	}

	// 1. Create video generation task
	fmt.Println("----- create request -----")
	createReq := &model.CreateContentGenerationTaskRequest{
		Model:         modelID,
		GenerateAudio: model.NewOptBool(generateAudio),
		Ratio:         model.NewOptString(videoRatio),
		Duration:      model.NewOptInt64(videoDuration),
		Content:       content,
		Watermark:     model.NewOptBool(true),
	}

	createResp, err := client.CreateContentGenerationTask(ctx, createReq)
	if err != nil {
		panic(fmt.Errorf("create content generation task: %w", err))
	}

	taskID := createResp.ID
	fmt.Printf("Task Created with ID: %s\n", taskID)

	// 2. Poll task status
	pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
	fmt.Println("----- polling task status -----")
	for {
		getReq := taskID
		getResp, err := client.GetContentGenerationTask(ctx, getReq)
		if err != nil {
			panic(fmt.Errorf("get content generation task: %w", err))
		}

		status := getResp.Status
		if status == "succeeded" {
			fmt.Println("----- task succeeded -----")
			fmt.Printf("Task ID: %s \n", getResp.ID)
			fmt.Printf("Model: %s \n", getResp.Model)
			fmt.Printf("Video URL: %s \n", getResp.Content.Or(model.TaskContent{}).VideoURL.Or(""))
			fmt.Printf("Completion Tokens: %d \n", getResp.Usage.Or(model.TaskUsage{}).CompletionTokens)
			fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt.Or(0), getResp.UpdatedAt.Or(0))
			return
		} else if status == "failed" {
			if getResp.Error.IsSet() {
				panic(fmt.Errorf("video generation task failed: %s: %s", getResp.Error.Value.Code, getResp.Error.Value.Message))
			}
			panic("video generation task failed")
		} else {
			fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
			time.Sleep(10 * time.Second)
		}
	}
}
```

<span id="2.5_50_reference"></span>
## 50 个全模态参考素材输入

Seedance 2.5 单次输入素材上限提升至 50 个（30 张图片 + 10 段视频 + 10 段音频），可自由组合图片、视频、音频等多模态素材，实现更丰富的创意表达。同时，Seedance 2.5 新增支持纯音频参考生成视频，无需搭配图片或视频素材。

|输入：文本 + 1 张图片 + 6 段视频 |||输出 |
|---|---|---|---|
|![](https://arkdocs.tos-cn-beijing.volces.com/images/resources/seedacne2.5_reference1.png) |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/resources/seedacne2.5_reference2.mp4) |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/resources/seedacne2.5_reference3.mp4) |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/resources/eedacne2.5_reference_output.mp4) | \
| |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/resources/seedacne2.5_reference4.mp4) |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/resources/seedacne2.5_reference5.mp4) | | \
| |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/resources/seedacne2.5_reference6.mp4) |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/resources/seedacne2.5_reference7.mp4) | | \
| | | | | \
|<blockquote>提示词：明亮多彩的广告片风格，果味饼干为主角...（详见下方代码示例中的完整提示词）</blockquote> | | | |

**选项：Curl**

```Bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-5-260628",
    "content": [
        {
            "type": "text",
            "text": "明亮多彩的广告片风格，果味饼干为主角，包含草莓、苹果、葡萄、橙子四种口味，草莓味参考@图像1，饼干与对应水果以强秩序感的几何阵列排布，整体画面干净、高级、节奏强。开场水果快速建立视觉聚焦，参考@视频1的构图，音乐重拍切入。随后不同口味饼干整齐排列，切特写，参考@视频2的动态和运镜。高潮段一块饼干被折断，瞬间进入慢动作，果味夹心爆开，碎屑飞溅，果汁感与颗粒冲击被放大展示，参考@视频3的冲击感。横向阵列，形成节奏抛物感，参考@视频4的运动，突出秩序美感与产品丰富度。随后迅速回到快节奏剪辑。结尾英文文字 One bite of crispness, a heart full of delight 快速分词切换入画，配合强节奏文字运动与产品定格，参考@视频5，最终品牌感收束，饼干和水果向四周发散，参考@视频6画面充满年轻、活力、好吃、想分享的广告氛围。"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png"
            },
            "role": "reference_image"
        },
        {
            "type": "video_url",
            "video_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference2.mp4"
            },
            "role": "reference_video"
        },
        {
            "type": "video_url",
            "video_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference3.mp4"
            },
            "role": "reference_video"
        },
        {
            "type": "video_url",
            "video_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference4.mp4"
            },
            "role": "reference_video"
        },
        {
            "type": "video_url",
            "video_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference5.mp4"
            },
            "role": "reference_video"
        },
        {
            "type": "video_url",
            "video_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference6.mp4"
            },
            "role": "reference_video"
        },
        {
            "type": "video_url",
            "video_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference7.mp4"
            },
            "role": "reference_video"
        }
    ],
    "generate_audio": true,
    "ratio": "16:9",
    "duration": 15,
    "omni_reference_task_type": "reference",
    "output_format": "mov",
    "watermark": true
}'
```

**选项：Python**

```Python
import os
import time
# Install SDK: python -m pip install --upgrade arkruntime
from arkruntime import Ark

client = Ark(
    # The base URL for model invocation
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    # Get API Key：https://ark.volcengine.com/region:cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-5-260628", # Replace with Model ID
        content=[
            {
                "type": "text",
                "text": "明亮多彩的广告片风格，果味饼干为主角，包含草莓、苹果、葡萄、橙子四种口味，草莓味参考@图像1，饼干与对应水果以强秩序感的几何阵列排布，整体画面干净、高级、节奏强。开场水果快速建立视觉聚焦，参考@视频1的构图，音乐重拍切入。随后不同口味饼干整齐排列，切特写，参考@视频2的动态和运镜。高潮段一块饼干被折断，瞬间进入慢动作，果味夹心爆开，碎屑飞溅，果汁感与颗粒冲击被放大展示，参考@视频3的冲击感。横向阵列，形成节奏抛物感，参考@视频4的运动，突出秩序美感与产品丰富度。随后迅速回到快节奏剪辑。结尾英文文字 One bite of crispness, a heart full of delight 快速分词切换入画，配合强节奏文字运动与产品定格，参考@视频5，最终品牌感收束，饼干和水果向四周发散，参考@视频6画面充满年轻、活力、好吃、想分享的广告氛围。",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png"
                },
                "role": "reference_image",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference2.mp4"
                },
                "role": "reference_video",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference3.mp4"
                },
                "role": "reference_video",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference4.mp4"
                },
                "role": "reference_video",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference5.mp4"
                },
                "role": "reference_video",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference6.mp4"
                },
                "role": "reference_video",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference7.mp4"
                },
                "role": "reference_video",
            },
        ],
        generate_audio=True,
        ratio="16:9",
        duration=15,
        extra_body={
            "omni_reference_task_type": "reference",
            "output_format": "mov",
        },
        watermark=True,
    )
    print(create_result)


    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    deadline = time.monotonic() + 30 * 60
    while time.monotonic() < deadline:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            raise RuntimeError(f"Video generation task failed: {get_result.error}")
        else:
            print(f"Current status: {status}, Retrying after 10 seconds...")
            time.sleep(10)
    else:
        raise TimeoutError("Video generation task did not finish within 30 minutes")
```

**选项：Java**

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.models.content_generation.*;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;
import retrofit2.Call;
import retrofit2.Retrofit;
import retrofit2.http.Body;
import retrofit2.http.POST;

import java.io.IOException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    interface ContentGenerationApi {
        @POST("contents/generations/tasks")
        Call<CreateContentGenerationTaskResponse> create(@Body Map<String, Object> request);
    }

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();
    static Retrofit retrofit = ArkService.defaultRetrofit(
            ArkService.defaultApiKeyClient(apiKey, Duration.ofSeconds(180)),
            ArkService.defaultObjectMapper(),
            "https://ark.cn-beijing.volces.com/api/v3/",
            Runnable::run);
    static ContentGenerationApi contentGenerationApi =
            retrofit.create(ContentGenerationApi.class);

    public static void main(String[] args) throws IOException {

        // Model ID
        final String modelId = "doubao-seedance-2-5-260628";
        // Text prompt
        final String prompt = "明亮多彩的广告片风格，果味饼干为主角，包含草莓、苹果、葡萄、橙子四种口味，草莓味参考@图像1，饼干与对应水果以强秩序感的几何阵列排布，整体画面干净、高级、节奏强。开场水果快速建立视觉聚焦，参考@视频1的构图，音乐重拍切入。随后不同口味饼干整齐排列，切特写，参考@视频2的动态和运镜。高潮段一块饼干被折断，瞬间进入慢动作，果味夹心爆开，碎屑飞溅，果汁感与颗粒冲击被放大展示，参考@视频3的冲击感。横向阵列，形成节奏抛物感，参考@视频4的运动，突出秩序美感与产品丰富度。随后迅速回到快节奏剪辑。结尾英文文字 One bite of crispness, a heart full of delight 快速分词切换入画，配合强节奏文字运动与产品定格，参考@视频5，最终品牌感收束，饼干和水果向四周发散，参考@视频6画面充满年轻、活力、好吃、想分享的广告氛围。";

        // Example resource URLs
        final String refImage1 = "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png";
        final String refVideo1 = "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference2.mp4";
        final String refVideo2 = "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference3.mp4";
        final String refVideo3 = "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference4.mp4";
        final String refVideo4 = "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference5.mp4";
        final String refVideo5 = "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference6.mp4";
        final String refVideo6 = "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference7.mp4";

        // Output video parameters
        final boolean generateAudio = true;
        final String videoRatio = "16:9";
        final long videoDuration = 15L;
        System.out.println("----- create request -----");
        // Build request content
        List<ContentItem> contents = new ArrayList<>();

        // 1. Text prompt
        contents.add(ContentItem.builder()
                .type(ContentType.TEXT)
                .text(prompt)
                .build());

        // 2. Reference image 1
        contents.add(ContentItem.builder()
                .type(ContentType.IMAGE_URL)
                .imageUrl(ImageURL.builder()
                        .url(refImage1)
                        .build())
                .role("reference_image")
                .build());

        // 3. Reference video 1
        contents.add(ContentItem.builder()
                .type(ContentType.VIDEO_URL)
                .videoUrl(VideoURL.builder()
                        .url(refVideo1)
                        .build())
                .role("reference_video")
                .build());

        // 4. Reference video 2
        contents.add(ContentItem.builder()
                .type(ContentType.VIDEO_URL)
                .videoUrl(VideoURL.builder()
                        .url(refVideo2)
                        .build())
                .role("reference_video")
                .build());

        // 5. Reference video 3
        contents.add(ContentItem.builder()
                .type(ContentType.VIDEO_URL)
                .videoUrl(VideoURL.builder()
                        .url(refVideo3)
                        .build())
                .role("reference_video")
                .build());

        // 6. Reference video 4
        contents.add(ContentItem.builder()
                .type(ContentType.VIDEO_URL)
                .videoUrl(VideoURL.builder()
                        .url(refVideo4)
                        .build())
                .role("reference_video")
                .build());

        // 7. Reference video 5
        contents.add(ContentItem.builder()
                .type(ContentType.VIDEO_URL)
                .videoUrl(VideoURL.builder()
                        .url(refVideo5)
                        .build())
                .role("reference_video")
                .build());

        // 8. Reference video 6
        contents.add(ContentItem.builder()
                .type(ContentType.VIDEO_URL)
                .videoUrl(VideoURL.builder()
                        .url(refVideo6)
                        .build())
                .role("reference_video")
                .build());

        // Create video generation task
        Map<String, Object> createRequest = new LinkedHashMap<>();
        createRequest.put("model", modelId);
        createRequest.put("content", contents);
        createRequest.put("generate_audio", generateAudio);
        createRequest.put("ratio", videoRatio);
        createRequest.put("duration", videoDuration);
        createRequest.put("omni_reference_task_type", "reference");
        createRequest.put("output_format", "mov");
        createRequest.put("watermark", true);

        retrofit2.Response<CreateContentGenerationTaskResponse> response =
                contentGenerationApi.create(createRequest).execute();
        if (!response.isSuccessful() || response.body() == null) {
            throw new IOException("Unexpected code " + response.code());
        }
        CreateContentGenerationTaskResponse createResult = response.body();
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */

    private static void pollTaskStatus(String taskId) {
        String getRequest = taskId;

        System.out.println("----- polling task status -----");
        try {
            long deadlineNanos = System.nanoTime() + TimeUnit.MINUTES.toNanos(30);
            while (System.nanoTime() < deadlineNanos) {
                ContentGenerationTask getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus().toString();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    return;
                } else if ("failed".equalsIgnoreCase(status)) {
                    throw new IllegalStateException(
                            "Video generation task failed: " + getResponse.getError());
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
            throw new IllegalStateException(
                    "Video generation task did not finish within 30 minutes");
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Polling interrupted", ie);
        } catch (Exception e) {
            throw new RuntimeException("Error occurred while polling", e);
        } finally {
            service.shutdownExecutor();
        }
    }
}
```

**选项：Go**

```Go
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/volcengine/ark-runtime-go/arkruntime"
	model "github.com/volcengine/ark-runtime-go/arkruntime/model/contentgeneration"
)

func main() {
	// Initialize Ark client
	client := arkruntime.NewClientWithApiKey(
		os.Getenv("ARK_API_KEY"),
		// The base URL for model invocation
		arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
	)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	// Model ID
	modelID := "doubao-seedance-2-5-260628"
	// Text prompt
	prompt := "明亮多彩的广告片风格，果味饼干为主角，包含草莓、苹果、葡萄、橙子四种口味，草莓味参考@图像1，饼干与对应水果以强秩序感的几何阵列排布，整体画面干净、高级、节奏强。开场水果快速建立视觉聚焦，参考@视频1的构图，音乐重拍切入。随后不同口味饼干整齐排列，切特写，参考@视频2的动态和运镜。高潮段一块饼干被折断，瞬间进入慢动作，果味夹心爆开，碎屑飞溅，果汁感与颗粒冲击被放大展示，参考@视频3的冲击感。横向阵列，形成节奏抛物感，参考@视频4的运动，突出秩序美感与产品丰富度。随后迅速回到快节奏剪辑。结尾英文文字 One bite of crispness, a heart full of delight 快速分词切换入画，配合强节奏文字运动与产品定格，参考@视频5，最终品牌感收束，饼干和水果向四周发散，参考@视频6画面充满年轻、活力、好吃、想分享的广告氛围。"

	// Example resource URLs
	refImage1 := "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png"
	refVideo1 := "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference2.mp4"
	refVideo2 := "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference3.mp4"
	refVideo3 := "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference4.mp4"
	refVideo4 := "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference5.mp4"
	refVideo5 := "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference6.mp4"
	refVideo6 := "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_reference7.mp4"

	// Output video parameters
	generateAudio := true
	videoRatio := "16:9"
	videoDuration := int64(15)
	omniReferenceTaskType := "reference"
	outputFormat := "mov"

	// 1. Create video generation task
	fmt.Println("----- create request -----")
	createReq := &model.CreateContentGenerationTaskRequest{
		Model:         modelID,
		GenerateAudio: model.NewOptBool(generateAudio),
		Ratio:         model.NewOptString(videoRatio),
		Duration:      model.NewOptInt64(videoDuration),
		Content: []model.ContentItem{
			{
				Type: model.ContentTypeText,
				Text: model.NewOptString(prompt),
			},
			{
				Type: model.ContentTypeImageURL,
				ImageURL: model.NewOptImageURL(model.ImageURL{
					URL: refImage1,
				}),
				Role: model.NewOptString("reference_image"),
			},
			{
				Type: model.ContentTypeVideoURL,
				VideoURL: model.NewOptVideoURL(model.VideoURL{
					URL: refVideo1,
				}),
				Role: model.NewOptString("reference_video"),
			},
			{
				Type: model.ContentTypeVideoURL,
				VideoURL: model.NewOptVideoURL(model.VideoURL{
					URL: refVideo2,
				}),
				Role: model.NewOptString("reference_video"),
			},
			{
				Type: model.ContentTypeVideoURL,
				VideoURL: model.NewOptVideoURL(model.VideoURL{
					URL: refVideo3,
				}),
				Role: model.NewOptString("reference_video"),
			},
			{
				Type: model.ContentTypeVideoURL,
				VideoURL: model.NewOptVideoURL(model.VideoURL{
					URL: refVideo4,
				}),
				Role: model.NewOptString("reference_video"),
			},
			{
				Type: model.ContentTypeVideoURL,
				VideoURL: model.NewOptVideoURL(model.VideoURL{
					URL: refVideo5,
				}),
				Role: model.NewOptString("reference_video"),
			},
			{
				Type: model.ContentTypeVideoURL,
				VideoURL: model.NewOptVideoURL(model.VideoURL{
					URL: refVideo6,
				}),
				Role: model.NewOptString("reference_video"),
			},
		},
		Watermark:     model.NewOptBool(true),
	}

	createResp, err := client.CreateContentGenerationTask(
		ctx,
		createReq,
		arkruntime.WithExtraBody(map[string]interface{}{
			"omni_reference_task_type": omniReferenceTaskType,
			"output_format":            outputFormat,
		}),
	)
	if err != nil {
		panic(fmt.Errorf("create content generation task: %w", err))
	}

	taskID := createResp.ID
	fmt.Printf("Task Created with ID: %s\n", taskID)

	// 2. Poll task status
	pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
	fmt.Println("----- polling task status -----")
	for {
		getReq := taskID
		getResp, err := client.GetContentGenerationTask(ctx, getReq)
		if err != nil {
			panic(fmt.Errorf("get content generation task: %w", err))
		}

		status := getResp.Status
		if status == "succeeded" {
			fmt.Println("----- task succeeded -----")
			fmt.Printf("Task ID: %s \n", getResp.ID)
			fmt.Printf("Model: %s \n", getResp.Model)
			fmt.Printf("Video URL: %s \n", getResp.Content.Or(model.TaskContent{}).VideoURL.Or(""))
			fmt.Printf("Completion Tokens: %d \n", getResp.Usage.Or(model.TaskUsage{}).CompletionTokens)
			fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt.Or(0), getResp.UpdatedAt.Or(0))
			return
		} else if status == "failed" {
			if getResp.Error.IsSet() {
				panic(fmt.Errorf("video generation task failed: %s: %s", getResp.Error.Value.Code, getResp.Error.Value.Message))
			}
			panic("video generation task failed")
		} else {
			fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
			time.Sleep(10 * time.Second)
		}
	}
}
```

<span id="2.5_smart_ratio_duration"></span>
## 更智能的时长和宽高比控制

Seedance 2.5 模型支持通过配置`ratio` 为 `adaptive`、`duration` 为 `-1`以智能控制输出视频的宽高比和时长；但在**视频编辑、视频延长、首帧或首尾帧生视频**任务中，具有特殊的控制行为，详情参考以下示例。

<span id="2.5_edit"></span>
### 使用示例-视频编辑

在视频编辑任务中，Seedance 2.5 会根据提示词意图选定待编辑视频，并自动保持输出视频宽高比、时长和待编辑视频一致（参数 `ratio` 默认且仅支持配置为 `adaptive`，参数 `duration` 默认且仅支持配置为 `-1`，均不支持另行设置）。

> **注意**
>
> 受输入帧处理影响，输出时长可能略短于输入视频（误差不超过 0.4 秒）。

|输入：文本 + 视频（宽高比 5:4，时长 16 秒） |输出（宽高比 5:4，时长 16 秒） |
|---|---|
|[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_edit_input.mov) |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_edit_output.mov) | \
|<blockquote>提示词：视频编辑：删除 @视频1中的所有人，除了主角。</blockquote> |<blockquote><strong>输出视频宽高比自动和待编辑视频的 5:4 保持一致；输出视频时长和待编辑视频的 16 秒基本一致</strong></blockquote> |

**选项：Curl**

```Bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-5-260628",
    "content": [
        {
            "type": "text",
            "text": "视频编辑：删除 @视频1中的所有人，除了主角。"
        },
        {
            "type": "video_url",
            "video_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_edit_input.mov"
            },
            "role": "reference_video"
        }
    ],
    "generate_audio": true,
    "ratio": "adaptive",
    "duration": -1,
    "omni_reference_task_type": "edit",
    "output_format": "mov",
    "watermark": true
}'
```

**选项：Python**

```Python
import os
import time
# Install SDK: python -m pip install --upgrade arkruntime
from arkruntime import Ark

client = Ark(
    # The base URL for model invocation
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    # Get API Key：https://ark.volcengine.com/region:cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-5-260628", # Replace with Model ID
        content=[
            {
                "type": "text",
                "text": "视频编辑：删除 @视频1中的所有人，除了主角。",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_edit_input.mov"
                },
                "role": "reference_video",
            },
        ],
        generate_audio=True,
        ratio="adaptive",
        duration=-1,
        extra_body={
            "omni_reference_task_type": "edit",
            "output_format": "mov",
        },
        watermark=True,
    )
    print(create_result)


    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    deadline = time.monotonic() + 30 * 60
    while time.monotonic() < deadline:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            raise RuntimeError(f"Video generation task failed: {get_result.error}")
        else:
            print(f"Current status: {status}, Retrying after 10 seconds...")
            time.sleep(10)
    else:
        raise TimeoutError("Video generation task did not finish within 30 minutes")
```

**选项：Java**

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.models.content_generation.*;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;
import retrofit2.Call;
import retrofit2.Retrofit;
import retrofit2.http.Body;
import retrofit2.http.POST;

import java.io.IOException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    interface ContentGenerationApi {
        @POST("contents/generations/tasks")
        Call<CreateContentGenerationTaskResponse> create(@Body Map<String, Object> request);
    }

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();
    static Retrofit retrofit = ArkService.defaultRetrofit(
            ArkService.defaultApiKeyClient(apiKey, Duration.ofSeconds(180)),
            ArkService.defaultObjectMapper(),
            "https://ark.cn-beijing.volces.com/api/v3/",
            Runnable::run);
    static ContentGenerationApi contentGenerationApi =
            retrofit.create(ContentGenerationApi.class);

    public static void main(String[] args) throws IOException {

        // Model ID
        final String modelId = "doubao-seedance-2-5-260628";
        // Text prompt
        final String prompt = "视频编辑：删除 @视频1中的所有人，除了主角。";

        // Example resource URLs
        final String refVideo = "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_edit_input.mov";

        // Output video parameters
        final boolean generateAudio = true;
        final String videoRatio = "adaptive";
        final long videoDuration = -1L;
        System.out.println("----- create request -----");
        // Build request content
        List<ContentItem> contents = new ArrayList<>();

        // 1. Text prompt
        contents.add(ContentItem.builder()
                .type(ContentType.TEXT)
                .text(prompt)
                .build());

        // 2. Reference video
        contents.add(ContentItem.builder()
                .type(ContentType.VIDEO_URL)
                .videoUrl(VideoURL.builder()
                        .url(refVideo)
                        .build())
                .role("reference_video")
                .build());

        // Create video generation task
        Map<String, Object> createRequest = new LinkedHashMap<>();
        createRequest.put("model", modelId);
        createRequest.put("content", contents);
        createRequest.put("generate_audio", generateAudio);
        createRequest.put("ratio", videoRatio);
        createRequest.put("duration", videoDuration);
        createRequest.put("omni_reference_task_type", "edit");
        createRequest.put("output_format", "mov");
        createRequest.put("watermark", true);

        retrofit2.Response<CreateContentGenerationTaskResponse> response =
                contentGenerationApi.create(createRequest).execute();
        if (!response.isSuccessful() || response.body() == null) {
            throw new IOException("Unexpected code " + response.code());
        }
        CreateContentGenerationTaskResponse createResult = response.body();
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */

    private static void pollTaskStatus(String taskId) {
        String getRequest = taskId;

        System.out.println("----- polling task status -----");
        try {
            long deadlineNanos = System.nanoTime() + TimeUnit.MINUTES.toNanos(30);
            while (System.nanoTime() < deadlineNanos) {
                ContentGenerationTask getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus().toString();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    return;
                } else if ("failed".equalsIgnoreCase(status)) {
                    throw new IllegalStateException(
                            "Video generation task failed: " + getResponse.getError());
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
            throw new IllegalStateException(
                    "Video generation task did not finish within 30 minutes");
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Polling interrupted", ie);
        } catch (Exception e) {
            throw new RuntimeException("Error occurred while polling", e);
        } finally {
            service.shutdownExecutor();
        }
    }
}
```

**选项：Go**

```Go
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/volcengine/ark-runtime-go/arkruntime"
	model "github.com/volcengine/ark-runtime-go/arkruntime/model/contentgeneration"
)

func main() {
	// Initialize Ark client
	client := arkruntime.NewClientWithApiKey(
		os.Getenv("ARK_API_KEY"),
		// The base URL for model invocation
		arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
	)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	// Model ID
	modelID := "doubao-seedance-2-5-260628"
	// Text prompt
	prompt := "视频编辑：删除 @视频1中的所有人，除了主角。"

	// Example resource URLs
	refVideo := "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/seedance2.5_edit_input.mov"

	// Output video parameters
	generateAudio := true
	videoRatio := "adaptive"
	videoDuration := int64(-1)
	omniReferenceTaskType := "edit"
	outputFormat := "mov"

	// 1. Create video generation task
	fmt.Println("----- create request -----")
	createReq := &model.CreateContentGenerationTaskRequest{
		Model:         modelID,
		GenerateAudio: model.NewOptBool(generateAudio),
		Ratio:         model.NewOptString(videoRatio),
		Duration:      model.NewOptInt64(videoDuration),
		Content: []model.ContentItem{
			{
				Type: model.ContentTypeText,
				Text: model.NewOptString(prompt),
			},
			{
				Type: model.ContentTypeVideoURL,
				VideoURL: model.NewOptVideoURL(model.VideoURL{
					URL: refVideo,
				}),
				Role: model.NewOptString("reference_video"),
			},
		},
		Watermark:     model.NewOptBool(true),
	}

	createResp, err := client.CreateContentGenerationTask(
		ctx,
		createReq,
		arkruntime.WithExtraBody(map[string]interface{}{
			"omni_reference_task_type": omniReferenceTaskType,
			"output_format":            outputFormat,
		}),
	)
	if err != nil {
		panic(fmt.Errorf("create content generation task: %w", err))
	}

	taskID := createResp.ID
	fmt.Printf("Task Created with ID: %s\n", taskID)

	// 2. Poll task status
	pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
	fmt.Println("----- polling task status -----")
	for {
		getReq := taskID
		getResp, err := client.GetContentGenerationTask(ctx, getReq)
		if err != nil {
			panic(fmt.Errorf("get content generation task: %w", err))
		}

		status := getResp.Status
		if status == "succeeded" {
			fmt.Println("----- task succeeded -----")
			fmt.Printf("Task ID: %s \n", getResp.ID)
			fmt.Printf("Model: %s \n", getResp.Model)
			fmt.Printf("Video URL: %s \n", getResp.Content.Or(model.TaskContent{}).VideoURL.Or(""))
			fmt.Printf("Completion Tokens: %d \n", getResp.Usage.Or(model.TaskUsage{}).CompletionTokens)
			fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt.Or(0), getResp.UpdatedAt.Or(0))
			return
		} else if status == "failed" {
			if getResp.Error.IsSet() {
				panic(fmt.Errorf("video generation task failed: %s: %s", getResp.Error.Value.Code, getResp.Error.Value.Message))
			}
			panic("video generation task failed")
		} else {
			fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
			time.Sleep(10 * time.Second)
		}
	}
}
```

<span id="2.5_extend"></span>
### 使用示例-视频延长

在视频延长任务中，Seedance 2.5 会根据提示词意图选定待延长视频，并自动保持输出视频宽高比和待延长视频一致（参数 `ratio` 默认且仅支持配置为 `adaptive`）。视频输出时长可以自行设置或由模型智能判断（参数 `duration` 支持配置为 `[4, 30]` 或 `-1`）。

|输入：文本 + 视频（视频1宽高比 7:5，视频2、视频3宽高比 16:9） ||输出（宽高比 7:5）|
|---|---|---|
|[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video1_75.mov) |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video2.mp4) |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_output_75.mov) | \
| | | | \
|<blockquote>提示词：延长@视频1，窗户打开后进入@视频2的美术馆室内，最后镜头进入@视频3的画内</blockquote> |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video3.mp4) |<blockquote><strong>输出视频宽高比自动和待延长视频的 7:5 保持一致</strong></blockquote> |

**选项：Curl**

```Bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-5-260628",
    "content": [
        {
            "type": "text",
            "text": "延长@视频1，窗户打开后进入@视频2的美术馆室内，最后镜头进入@视频3的画内"
        },
        {
            "type": "video_url",
            "video_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video1_75.mov"
            },
            "role": "reference_video"
        },
        {
            "type": "video_url",
            "video_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video2.mp4"
            },
            "role": "reference_video"
        },
        {
            "type": "video_url",
            "video_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video3.mp4"
            },
            "role": "reference_video"
        }
    ],
    "generate_audio": true,
    "ratio": "adaptive",
    "duration": 11,
    "omni_reference_task_type": "extend",
    "output_format": "mov",
    "watermark": true
}'
```

**选项：Python**

```Python
import os
import time
# Install SDK: python -m pip install --upgrade arkruntime
from arkruntime import Ark

client = Ark(
    # The base URL for model invocation
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    # Get API Key：https://ark.volcengine.com/region:cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-5-260628", # Replace with Model ID
        content=[
            {
                "type": "text",
                "text": "延长@视频1，窗户打开后进入@视频2的美术馆室内，最后镜头进入@视频3的画内",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video1_75.mov"
                },
                "role": "reference_video",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video2.mp4"
                },
                "role": "reference_video",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video3.mp4"
                },
                "role": "reference_video",
            },
        ],
        generate_audio=True,
        ratio="adaptive",
        duration=11,
        extra_body={
            "omni_reference_task_type": "extend",
            "output_format": "mov",
        },
        watermark=True,
    )
    print(create_result)


    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    deadline = time.monotonic() + 30 * 60
    while time.monotonic() < deadline:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            raise RuntimeError(f"Video generation task failed: {get_result.error}")
        else:
            print(f"Current status: {status}, Retrying after 10 seconds...")
            time.sleep(10)
    else:
        raise TimeoutError("Video generation task did not finish within 30 minutes")
```

**选项：Java**

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.models.content_generation.*;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;
import retrofit2.Call;
import retrofit2.Retrofit;
import retrofit2.http.Body;
import retrofit2.http.POST;

import java.io.IOException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    interface ContentGenerationApi {
        @POST("contents/generations/tasks")
        Call<CreateContentGenerationTaskResponse> create(@Body Map<String, Object> request);
    }

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();
    static Retrofit retrofit = ArkService.defaultRetrofit(
            ArkService.defaultApiKeyClient(apiKey, Duration.ofSeconds(180)),
            ArkService.defaultObjectMapper(),
            "https://ark.cn-beijing.volces.com/api/v3/",
            Runnable::run);
    static ContentGenerationApi contentGenerationApi =
            retrofit.create(ContentGenerationApi.class);

    public static void main(String[] args) throws IOException {

        // Model ID
        final String modelId = "doubao-seedance-2-5-260628";
        // Text prompt
        final String prompt = "延长@视频1，窗户打开后进入@视频2的美术馆室内，最后镜头进入@视频3的画内";

        // Example resource URLs
        final String refVideo1 = "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video1_75.mov";
        final String refVideo2 = "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video2.mp4";
        final String refVideo3 = "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video3.mp4";

        // Output video parameters
        final boolean generateAudio = true;
        final String videoRatio = "adaptive";
        final long videoDuration = 11L;
        System.out.println("----- create request -----");
        // Build request content
        List<ContentItem> contents = new ArrayList<>();

        // 1. Text prompt
        contents.add(ContentItem.builder()
                .type(ContentType.TEXT)
                .text(prompt)
                .build());

        // 2. Reference video 1
        contents.add(ContentItem.builder()
                .type(ContentType.VIDEO_URL)
                .videoUrl(VideoURL.builder()
                        .url(refVideo1)
                        .build())
                .role("reference_video")
                .build());

        // 3. Reference video 2
        contents.add(ContentItem.builder()
                .type(ContentType.VIDEO_URL)
                .videoUrl(VideoURL.builder()
                        .url(refVideo2)
                        .build())
                .role("reference_video")
                .build());

        // 4. Reference video 3
        contents.add(ContentItem.builder()
                .type(ContentType.VIDEO_URL)
                .videoUrl(VideoURL.builder()
                        .url(refVideo3)
                        .build())
                .role("reference_video")
                .build());

        // Create video generation task
        Map<String, Object> createRequest = new LinkedHashMap<>();
        createRequest.put("model", modelId);
        createRequest.put("content", contents);
        createRequest.put("generate_audio", generateAudio);
        createRequest.put("ratio", videoRatio);
        createRequest.put("duration", videoDuration);
        createRequest.put("omni_reference_task_type", "extend");
        createRequest.put("output_format", "mov");
        createRequest.put("watermark", true);

        retrofit2.Response<CreateContentGenerationTaskResponse> response =
                contentGenerationApi.create(createRequest).execute();
        if (!response.isSuccessful() || response.body() == null) {
            throw new IOException("Unexpected code " + response.code());
        }
        CreateContentGenerationTaskResponse createResult = response.body();
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */

    private static void pollTaskStatus(String taskId) {
        String getRequest = taskId;

        System.out.println("----- polling task status -----");
        try {
            long deadlineNanos = System.nanoTime() + TimeUnit.MINUTES.toNanos(30);
            while (System.nanoTime() < deadlineNanos) {
                ContentGenerationTask getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus().toString();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    return;
                } else if ("failed".equalsIgnoreCase(status)) {
                    throw new IllegalStateException(
                            "Video generation task failed: " + getResponse.getError());
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
            throw new IllegalStateException(
                    "Video generation task did not finish within 30 minutes");
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Polling interrupted", ie);
        } catch (Exception e) {
            throw new RuntimeException("Error occurred while polling", e);
        } finally {
            service.shutdownExecutor();
        }
    }
}
```

**选项：Go**

```Go
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/volcengine/ark-runtime-go/arkruntime"
	model "github.com/volcengine/ark-runtime-go/arkruntime/model/contentgeneration"
)

func main() {
	// Initialize Ark client
	client := arkruntime.NewClientWithApiKey(
		os.Getenv("ARK_API_KEY"),
		// The base URL for model invocation
		arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
	)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	// Model ID
	modelID := "doubao-seedance-2-5-260628"
	// Text prompt
	prompt := "延长@视频1，窗户打开后进入@视频2的美术馆室内，最后镜头进入@视频3的画内"

	// Example resource URLs
	refVideo1 := "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video1_75.mov"
    refVideo2 := "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video2.mp4"
    refVideo3 := "https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/r2v_extend_video3.mp4"

	// Output video parameters
	generateAudio := true
	videoRatio := "adaptive"
	videoDuration := int64(11)
	omniReferenceTaskType := "extend"
	outputFormat := "mov"

	// 1. Create video generation task
	fmt.Println("----- create request -----")
	createReq := &model.CreateContentGenerationTaskRequest{
		Model:         modelID,
		GenerateAudio: model.NewOptBool(generateAudio),
		Ratio:         model.NewOptString(videoRatio),
		Duration:      model.NewOptInt64(videoDuration),
		Content: []model.ContentItem{
			{
				Type: model.ContentTypeText,
				Text: model.NewOptString(prompt),
			},
			{
				Type: model.ContentTypeVideoURL,
				VideoURL: model.NewOptVideoURL(model.VideoURL{
					URL: refVideo1,
				}),
				Role: model.NewOptString("reference_video"),
			},
			{
				Type: model.ContentTypeVideoURL,
				VideoURL: model.NewOptVideoURL(model.VideoURL{
					URL: refVideo2,
				}),
				Role: model.NewOptString("reference_video"),
			},
			{
				Type: model.ContentTypeVideoURL,
				VideoURL: model.NewOptVideoURL(model.VideoURL{
					URL: refVideo3,
				}),
				Role: model.NewOptString("reference_video"),
			},
		},
		Watermark:     model.NewOptBool(true),
	}

	createResp, err := client.CreateContentGenerationTask(
		ctx,
		createReq,
		arkruntime.WithExtraBody(map[string]interface{}{
			"omni_reference_task_type": omniReferenceTaskType,
			"output_format":            outputFormat,
		}),
	)
	if err != nil {
		panic(fmt.Errorf("create content generation task: %w", err))
	}

	taskID := createResp.ID
	fmt.Printf("Task Created with ID: %s\n", taskID)

	// 2. Poll task status
	pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
	fmt.Println("----- polling task status -----")
	for {
		getReq := taskID
		getResp, err := client.GetContentGenerationTask(ctx, getReq)
		if err != nil {
			panic(fmt.Errorf("get content generation task: %w", err))
		}

		status := getResp.Status
		if status == "succeeded" {
			fmt.Println("----- task succeeded -----")
			fmt.Printf("Task ID: %s \n", getResp.ID)
			fmt.Printf("Model: %s \n", getResp.Model)
			fmt.Printf("Video URL: %s \n", getResp.Content.Or(model.TaskContent{}).VideoURL.Or(""))
			fmt.Printf("Completion Tokens: %d \n", getResp.Usage.Or(model.TaskUsage{}).CompletionTokens)
			fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt.Or(0), getResp.UpdatedAt.Or(0))
			return
		} else if status == "failed" {
			if getResp.Error.IsSet() {
				panic(fmt.Errorf("video generation task failed: %s: %s", getResp.Error.Value.Code, getResp.Error.Value.Message))
			}
			panic("video generation task failed")
		} else {
			fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
			time.Sleep(10 * time.Second)
		}
	}
}
```

<span id="2.5_first-last-frame"></span>
### 使用示例-首帧/首尾帧生视频

在首帧/首尾帧生视频任务中，Seedance 2.5 会自动保持输出视频宽高比和 `first_frame` 指定的首帧图片一致（参数 `ratio` 默认且仅支持配置为 `adaptive`）。视频输出时长可以自行设置或由模型智能判断（参数 `duration` 支持配置为 `[4, 30]` 或 `-1`）。

|输入：文本 + 首帧（宽高比 1:1） + 尾帧 ||输出（宽高比 1:1）|
|---|---|---|
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/649cb2057eae48d6a6eec872d912c75c~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/e39fd8e500a34bbdad50d06659c4ea6b~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/3aa8c84b8a29408ab29e95992d61c559) | \
| | | | \
|<blockquote>提示词：图中女孩对着镜头说“茄子”，360 度环绕运镜</blockquote> | |<blockquote><strong>输出视频宽高比自动和首帧图片的 1:1 保持一致</strong></blockquote> |

**选项：Curl**

```Bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-5-260628",
    "content": [
        {
            "type": "text",
            "text": "草莓夹心饼干缓慢旋转一周，镜头平滑环绕，保持产品居中"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png"
            },
            "role": "first_frame"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png"
            },
            "role": "last_frame"
        }
    ],
    "generate_audio": true,
    "ratio": "adaptive",
    "duration": 5,
    "watermark": true
}'
```

**选项：Python**

```Python
import os
import time
# Install SDK: python -m pip install --upgrade arkruntime
from arkruntime import Ark

client = Ark(
    # The base URL for model invocation
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # Get API Key: https://ark.volcengine.com/region:cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-5-260628",  # Replace with Model ID
        content=[
            {
                "type": "text",
                "text": "草莓夹心饼干缓慢旋转一周，镜头平滑环绕，保持产品居中",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png"
                },
                "role": "first_frame",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png"
                },
                "role": "last_frame",
            },
        ],
        generate_audio=True,
        ratio="adaptive",
        duration=5,
        watermark=True,
    )
    print(create_result)

    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    deadline = time.monotonic() + 30 * 60
    while time.monotonic() < deadline:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        if status == "failed":
            raise RuntimeError(f"Video generation task failed: {get_result.error}")

        print(f"Current status: {status}, Retrying after 10 seconds...")
        time.sleep(10)
    else:
        raise TimeoutError("Video generation task did not finish within 30 minutes")
```

**选项：Java**

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.models.content_generation.*;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();

    public static void main(String[] args) {
        // Model ID
        final String modelId = "doubao-seedance-2-5-260628";
        // Text prompt
        final String prompt = "草莓夹心饼干缓慢旋转一周，镜头平滑环绕，保持产品居中";

        // Example resource URLs
        final String firstFrameUrl = "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png";
        final String lastFrameUrl = "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png";

        // Output video parameters
        final boolean generateAudio = true;
        final String videoRatio = "adaptive";
        final long videoDuration = 5L;

        System.out.println("----- create request -----");
        // Build request content
        List<ContentItem> contents = new ArrayList<>();

        // 1. Text prompt
        contents.add(ContentItem.builder()
                .type(ContentType.TEXT)
                .text(prompt)
                .build());

        // 2. First frame image
        contents.add(ContentItem.builder()
                .type(ContentType.IMAGE_URL)
                .imageUrl(ImageURL.builder()
                        .url(firstFrameUrl)
                        .build())
                .role("first_frame")
                .build());

        // 3. Last frame image
        contents.add(ContentItem.builder()
                .type(ContentType.IMAGE_URL)
                .imageUrl(ImageURL.builder()
                        .url(lastFrameUrl)
                        .build())
                .role("last_frame")
                .build());

        // Create video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .generateAudio(generateAudio)
                .model(modelId)
                .content(contents)
                .ratio(videoRatio)
                .duration(videoDuration)
                .watermark(true)
                .build();

        CreateContentGenerationTaskResponse createResult = service.createContentGenerationTask(createRequest);
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */
    private static void pollTaskStatus(String taskId) {
        String getRequest = taskId;

        System.out.println("----- polling task status -----");
        try {
            long deadlineNanos = System.nanoTime() + TimeUnit.MINUTES.toNanos(30);
            while (System.nanoTime() < deadlineNanos) {
                ContentGenerationTask getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus().toString();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    return;
                } else if ("failed".equalsIgnoreCase(status)) {
                    throw new IllegalStateException(
                            "Video generation task failed: " + getResponse.getError());
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
            throw new IllegalStateException(
                    "Video generation task did not finish within 30 minutes");
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Polling interrupted", ie);
        } catch (Exception e) {
            throw new RuntimeException("Error occurred while polling", e);
        } finally {
            service.shutdownExecutor();
        }
    }
}
```

**选项：Go**

```Go
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/volcengine/ark-runtime-go/arkruntime"
	model "github.com/volcengine/ark-runtime-go/arkruntime/model/contentgeneration"
)

func main() {
	// Initialize Ark client
	client := arkruntime.NewClientWithApiKey(
		os.Getenv("ARK_API_KEY"),
		// The base URL for model invocation
		arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
	)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	// Model ID
	modelID := "doubao-seedance-2-5-260628"
	// Text prompt
	prompt := "草莓夹心饼干缓慢旋转一周，镜头平滑环绕，保持产品居中"

	// Example resource URLs
	firstFrameURL := "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png"
	lastFrameURL := "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_reference1.png"

	// Output video parameters
	generateAudio := true
	videoRatio := "adaptive"
	videoDuration := int64(5)

	// 1. Create video generation task
	fmt.Println("----- create request -----")
	createReq := &model.CreateContentGenerationTaskRequest{
		Model:         modelID,
		GenerateAudio: model.NewOptBool(generateAudio),
		Ratio:         model.NewOptString(videoRatio),
		Duration:      model.NewOptInt64(videoDuration),
		Content: []model.ContentItem{
			{
				Type: model.ContentTypeText,
				Text: model.NewOptString(prompt),
			},
			{
				Type: model.ContentTypeImageURL,
				ImageURL: model.NewOptImageURL(model.ImageURL{
					URL: firstFrameURL,
				}),
				Role: model.NewOptString("first_frame"),
			},
			{
				Type: model.ContentTypeImageURL,
				ImageURL: model.NewOptImageURL(model.ImageURL{
					URL: lastFrameURL,
				}),
				Role: model.NewOptString("last_frame"),
			},
		},
		Watermark:     model.NewOptBool(true),
	}

	createResp, err := client.CreateContentGenerationTask(ctx, createReq)
	if err != nil {
		panic(fmt.Errorf("create content generation task: %w", err))
	}

	taskID := createResp.ID
	fmt.Printf("Task Created with ID: %s\n", taskID)

	// 2. Poll task status
	pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
	fmt.Println("----- polling task status -----")
	for {
		getReq := taskID
		getResp, err := client.GetContentGenerationTask(ctx, getReq)
		if err != nil {
			panic(fmt.Errorf("get content generation task: %w", err))
		}

		status := getResp.Status
		if status == "succeeded" {
			fmt.Println("----- task succeeded -----")
			fmt.Printf("Task ID: %s \n", getResp.ID)
			fmt.Printf("Model: %s \n", getResp.Model)
			fmt.Printf("Video URL: %s \n", getResp.Content.Or(model.TaskContent{}).VideoURL.Or(""))
			fmt.Printf("Completion Tokens: %d \n", getResp.Usage.Or(model.TaskUsage{}).CompletionTokens)
			fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt.Or(0), getResp.UpdatedAt.Or(0))
			return
		} else if status == "failed" {
			if getResp.Error.IsSet() {
				panic(fmt.Errorf("video generation task failed: %s: %s", getResp.Error.Value.Code, getResp.Error.Value.Message))
			}
			panic("video generation task failed")
		} else {
			fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
			time.Sleep(10 * time.Second)
		}
	}
}
```

<span id="2.5_multi_language"></span>
## 原生多语言生成

Seedance 2.5 原生支持多种语言的提示词输入和有声视频生成，覆盖支持中文、英语、西班牙语、印度尼西亚语、马来语、泰语、阿拉伯语、葡萄牙语、越南语、日语、韩语。

|输入：文本 + 图片 |输出 |
|---|---|
|![](https://arkdocs.tos-cn-beijing.volces.com/images/resources/seedacne2.5_muti_language_input.png) |[视频](https://arkdocs.tos-cn-beijing.volces.com/videos/resources/seedacne2.5_muti_language_output.mp4) | \
| | | \
|<blockquote>提示词：电影级 hip-hop / 说唱音乐视频，歌词覆盖 8 种语言...（详见下方代码示例中的完整提示词）</blockquote> | |

**选项：Curl**

```Bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-5-260628",
    "content": [
        {
            "type": "text",
            "text": "电影级 hip-hop / 说唱音乐视频，真实照片级质感，高端调性，海边场景。以@图像1构建画面：一支乐队在金色沙滩、海浪拍岸的岸边表演 —— 一名主唱手握麦克风、麦架立于湿沙上激情演唱，一名吉他手立于画面左侧，一名吉他手立于画面右侧，一名鼓手坐在后方的架子鼓后敲击；辽阔的海岸线在身后展开，滚滚海浪层层涌来，巨大而温暖的黄金时刻夕阳斜掠过沙滩、在水面上粼粼闪耀，空气中漂浮着海雾与咸湿水汽。 红色运动服的主唱对着镜头充满节奏感地 RAP 演唱 —— 口型与下颌随每一个字精准对位，头随节拍用力点动，带动整段 flow。乐手们随节奏摇摆律动，身后海浪层层拍岸。这是一首明快带劲的说唱曲 —— 语速快、自信、节拍强劲。踩着节拍硬切（HARD CUT），每次切换双重反差（景别与镜头类型同时改变）。 歌词（主唱依次演唱以下每种语言的「你好」，精准对口型）： 英语：\"Hello\" 中文：\"你好\" 日语：\"こんにちは\" 韩语：\"안녕하세요\" 葡萄牙语：\"Olá\" 泰语：\"สวัสดี\" 西班牙语：\"Hola\" 阿拉伯语：\"مرحبا\" 镜头 1 [0:00–0:03] —— 低角度大远景定场，斯坦尼康在黄金夕照与海雾中缓缓推进，海浪在乐队身后翻涌。歌词第 1 句（英语「Hello」）。硬切。镜头 2 [0:03–0:05] —— 红运动服主唱对镜头 RAP 的特写，手持甩镜切入，身后海面虚焦粼粼波光。歌词第 2 句（中文「你好」）。硬切。镜头 3 [0:05–0:08] —— 微距插入镜头，固定机位，吉他手的手指在弦上快速拨动，沙粒与咸湿水雾从画面前掠过。歌词第 3 句（日语「こんにちは」）。硬切。镜头 4 [0:08–0:10] —— 对某位乐手的 3/4 侧中景，缓慢潜行环绕，乐器金属件与湿润高光映着海面低斜的夕阳。歌词第 4 句（韩语「안녕하세요」）。硬切。镜头 5 [0:10–0:13] —— 岸边一名乐手，快速横移轨道掠过他，他转向镜头，身后一道浪花破碎。歌词第 5 句（葡萄牙语「Olá」）。硬切。镜头 6 [0:13–0:15] —— 水边的鼓手，手持快速上摇，海风与水花吹动他的头发，他随节拍律动敲击。歌词第 6 句（泰语「สวัสดี」）。硬切。镜头 7 [0:15–0:18] —— 对红运动服主唱 flow 正酣时的紧凑猛推，富攻击性的手持，身后暮色海面衬着乐队剪影。歌词第 7 句（西班牙语「Hola」）。硬切。镜头 8 [0:18–0:20] —— 全乐队英雄式大远景，富攻击性的手持推进，主唱与乐手踩着节拍向镜头迈步，海浪拍碎、金色夕光在整支乐队身后炸开光晕。歌词第 8 句（阿拉伯语「مرحبا」）。 白平衡 4000K，青橙（teal-and-amber）调色，35mm，浅景深，胶片颗粒，弥漫的海雾，黄金时刻光晕。质感扎实、高级、高端。节奏感说唱表演，精准对口型，头随节拍点动。无字幕、无文字叠加、无叠化转场、无重复人物，仅用硬切。总时长 20 秒。"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_multi_language_input.png"
            },
            "role": "reference_image"
        }
    ],
    "generate_audio": true,
    "ratio": "16:9",
    "duration": 20,
    "watermark": true
}'
```

**选项：Python**

```Python
import os
import time
# Install SDK: python -m pip install --upgrade arkruntime
from arkruntime import Ark

client = Ark(
    # The base URL for model invocation
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    # Get API Key：https://ark.volcengine.com/region:cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-5-260628", # Replace with Model ID
        content=[
            {
                "type": "text",
                "text": "电影级 hip-hop / 说唱音乐视频，真实照片级质感，高端调性，海边场景。以@图像1构建画面：一支乐队在金色沙滩、海浪拍岸的岸边表演 —— 一名主唱手握麦克风、麦架立于湿沙上激情演唱，一名吉他手立于画面左侧，一名吉他手立于画面右侧，一名鼓手坐在后方的架子鼓后敲击；辽阔的海岸线在身后展开，滚滚海浪层层涌来，巨大而温暖的黄金时刻夕阳斜掠过沙滩、在水面上粼粼闪耀，空气中漂浮着海雾与咸湿水汽。 红色运动服的主唱对着镜头充满节奏感地 RAP 演唱 —— 口型与下颌随每一个字精准对位，头随节拍用力点动，带动整段 flow。乐手们随节奏摇摆律动，身后海浪层层拍岸。这是一首明快带劲的说唱曲 —— 语速快、自信、节拍强劲。踩着节拍硬切（HARD CUT），每次切换双重反差（景别与镜头类型同时改变）。 歌词（主唱依次演唱以下每种语言的「你好」，精准对口型）： 英语：\"Hello\" 中文：\"你好\" 日语：\"こんにちは\" 韩语：\"안녕하세요\" 葡萄牙语：\"Olá\" 泰语：\"สวัสดี\" 西班牙语：\"Hola\" 阿拉伯语：\"مرحبا\" 镜头 1 [0:00–0:03] —— 低角度大远景定场，斯坦尼康在黄金夕照与海雾中缓缓推进，海浪在乐队身后翻涌。歌词第 1 句（英语「Hello」）。硬切。镜头 2 [0:03–0:05] —— 红运动服主唱对镜头 RAP 的特写，手持甩镜切入，身后海面虚焦粼粼波光。歌词第 2 句（中文「你好」）。硬切。镜头 3 [0:05–0:08] —— 微距插入镜头，固定机位，吉他手的手指在弦上快速拨动，沙粒与咸湿水雾从画面前掠过。歌词第 3 句（日语「こんにちは」）。硬切。镜头 4 [0:08–0:10] —— 对某位乐手的 3/4 侧中景，缓慢潜行环绕，乐器金属件与湿润高光映着海面低斜的夕阳。歌词第 4 句（韩语「안녕하세요」）。硬切。镜头 5 [0:10–0:13] —— 岸边一名乐手，快速横移轨道掠过他，他转向镜头，身后一道浪花破碎。歌词第 5 句（葡萄牙语「Olá」）。硬切。镜头 6 [0:13–0:15] —— 水边的鼓手，手持快速上摇，海风与水花吹动他的头发，他随节拍律动敲击。歌词第 6 句（泰语「สวัสดี」）。硬切。镜头 7 [0:15–0:18] —— 对红运动服主唱 flow 正酣时的紧凑猛推，富攻击性的手持，身后暮色海面衬着乐队剪影。歌词第 7 句（西班牙语「Hola」）。硬切。镜头 8 [0:18–0:20] —— 全乐队英雄式大远景，富攻击性的手持推进，主唱与乐手踩着节拍向镜头迈步，海浪拍碎、金色夕光在整支乐队身后炸开光晕。歌词第 8 句（阿拉伯语「مرحبا」）。 白平衡 4000K，青橙（teal-and-amber）调色，35mm，浅景深，胶片颗粒，弥漫的海雾，黄金时刻光晕。质感扎实、高级、高端。节奏感说唱表演，精准对口型，头随节拍点动。无字幕、无文字叠加、无叠化转场、无重复人物，仅用硬切。总时长 20 秒。",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_multi_language_input.png"
                },
                "role": "reference_image",
            },
        ],
        generate_audio=True,
        ratio="16:9",
        duration=20,
        watermark=True,
    )
    print(create_result)


    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    deadline = time.monotonic() + 30 * 60
    while time.monotonic() < deadline:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            raise RuntimeError(f"Video generation task failed: {get_result.error}")
        else:
            print(f"Current status: {status}, Retrying after 30 seconds...")
            time.sleep(30)
    else:
        raise TimeoutError("Video generation task did not finish within 30 minutes")
```

**选项：Java**

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.models.content_generation.*;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();

    public static void main(String[] args) {

        // Model ID
        final String modelId = "doubao-seedance-2-5-260628";
        // Text prompt
        final String prompt = "电影级 hip-hop / 说唱音乐视频，真实照片级质感，高端调性，海边场景。以@图像1构建画面：一支乐队在金色沙滩、海浪拍岸的岸边表演 —— 一名主唱手握麦克风、麦架立于湿沙上激情演唱，一名吉他手立于画面左侧，一名吉他手立于画面右侧，一名鼓手坐在后方的架子鼓后敲击；辽阔的海岸线在身后展开，滚滚海浪层层涌来，巨大而温暖的黄金时刻夕阳斜掠过沙滩、在水面上粼粼闪耀，空气中漂浮着海雾与咸湿水汽。 红色运动服的主唱对着镜头充满节奏感地 RAP 演唱 —— 口型与下颌随每一个字精准对位，头随节拍用力点动，带动整段 flow。乐手们随节奏摇摆律动，身后海浪层层拍岸。这是一首明快带劲的说唱曲 —— 语速快、自信、节拍强劲。踩着节拍硬切（HARD CUT），每次切换双重反差（景别与镜头类型同时改变）。 歌词（主唱依次演唱以下每种语言的「你好」，精准对口型）： 英语：\"Hello\" 中文：\"你好\" 日语：\"こんにちは\" 韩语：\"안녕하세요\" 葡萄牙语：\"Olá\" 泰语：\"สวัสดี\" 西班牙语：\"Hola\" 阿拉伯语：\"مرحبا\" 镜头 1 [0:00–0:03] —— 低角度大远景定场，斯坦尼康在黄金夕照与海雾中缓缓推进，海浪在乐队身后翻涌。歌词第 1 句（英语「Hello」）。硬切。镜头 2 [0:03–0:05] —— 红运动服主唱对镜头 RAP 的特写，手持甩镜切入，身后海面虚焦粼粼波光。歌词第 2 句（中文「你好」）。硬切。镜头 3 [0:05–0:08] —— 微距插入镜头，固定机位，吉他手的手指在弦上快速拨动，沙粒与咸湿水雾从画面前掠过。歌词第 3 句（日语「こんにちは」）。硬切。镜头 4 [0:08–0:10] —— 对某位乐手的 3/4 侧中景，缓慢潜行环绕，乐器金属件与湿润高光映着海面低斜的夕阳。歌词第 4 句（韩语「안녕하세요」）。硬切。镜头 5 [0:10–0:13] —— 岸边一名乐手，快速横移轨道掠过他，他转向镜头，身后一道浪花破碎。歌词第 5 句（葡萄牙语「Olá」）。硬切。镜头 6 [0:13–0:15] —— 水边的鼓手，手持快速上摇，海风与水花吹动他的头发，他随节拍律动敲击。歌词第 6 句（泰语「สวัสดี」）。硬切。镜头 7 [0:15–0:18] —— 对红运动服主唱 flow 正酣时的紧凑猛推，富攻击性的手持，身后暮色海面衬着乐队剪影。歌词第 7 句（西班牙语「Hola」）。硬切。镜头 8 [0:18–0:20] —— 全乐队英雄式大远景，富攻击性的手持推进，主唱与乐手踩着节拍向镜头迈步，海浪拍碎、金色夕光在整支乐队身后炸开光晕。歌词第 8 句（阿拉伯语「مرحبا」）。 白平衡 4000K，青橙（teal-and-amber）调色，35mm，浅景深，胶片颗粒，弥漫的海雾，黄金时刻光晕。质感扎实、高级、高端。节奏感说唱表演，精准对口型，头随节拍点动。无字幕、无文字叠加、无叠化转场、无重复人物，仅用硬切。总时长 20 秒。";

        // Example resource URLs
        final String refImage1 = "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_multi_language_input.png";

        // Output video parameters
        final boolean generateAudio = true;
        final String videoRatio = "16:9";
        final long videoDuration = 20L;

        System.out.println("----- create request -----");
        // Build request content
        List<ContentItem> contents = new ArrayList<>();

        // 1. Text prompt
        contents.add(ContentItem.builder()
                .type(ContentType.TEXT)
                .text(prompt)
                .build());

        // 2. Reference image
        contents.add(ContentItem.builder()
                .type(ContentType.IMAGE_URL)
                .imageUrl(ImageURL.builder()
                        .url(refImage1)
                        .build())
                .role("reference_image")
                .build());

        // Create video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .generateAudio(generateAudio)
                .model(modelId)
                .content(contents)
                .ratio(videoRatio)
                .duration(videoDuration)
                .watermark(true)
                .build();

        CreateContentGenerationTaskResponse createResult = service.createContentGenerationTask(createRequest);
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */

    private static void pollTaskStatus(String taskId) {
        String getRequest = taskId;

        System.out.println("----- polling task status -----");
        try {
            long deadlineNanos = System.nanoTime() + TimeUnit.MINUTES.toNanos(30);
            while (System.nanoTime() < deadlineNanos) {
                ContentGenerationTask getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus().toString();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    return;
                } else if ("failed".equalsIgnoreCase(status)) {
                    throw new IllegalStateException(
                            "Video generation task failed: " + getResponse.getError());
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
            throw new IllegalStateException(
                    "Video generation task did not finish within 30 minutes");
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Polling interrupted", ie);
        } catch (Exception e) {
            throw new RuntimeException("Error occurred while polling", e);
        } finally {
            service.shutdownExecutor();
        }
    }
}
```

**选项：Go**

```Go
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/volcengine/ark-runtime-go/arkruntime"
	model "github.com/volcengine/ark-runtime-go/arkruntime/model/contentgeneration"
)

func main() {
	// Initialize Ark client
	client := arkruntime.NewClientWithApiKey(
		os.Getenv("ARK_API_KEY"),
		// The base URL for model invocation
		arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
	)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	// Model ID
	modelID := "doubao-seedance-2-5-260628"
	// Text prompt
	prompt := "电影级 hip-hop / 说唱音乐视频，真实照片级质感，高端调性，海边场景。以@图像1构建画面：一支乐队在金色沙滩、海浪拍岸的岸边表演 —— 一名主唱手握麦克风、麦架立于湿沙上激情演唱，一名吉他手立于画面左侧，一名吉他手立于画面右侧，一名鼓手坐在后方的架子鼓后敲击；辽阔的海岸线在身后展开，滚滚海浪层层涌来，巨大而温暖的黄金时刻夕阳斜掠过沙滩、在水面上粼粼闪耀，空气中漂浮着海雾与咸湿水汽。 红色运动服的主唱对着镜头充满节奏感地 RAP 演唱 —— 口型与下颌随每一个字精准对位，头随节拍用力点动，带动整段 flow。乐手们随节奏摇摆律动，身后海浪层层拍岸。这是一首明快带劲的说唱曲 —— 语速快、自信、节拍强劲。踩着节拍硬切（HARD CUT），每次切换双重反差（景别与镜头类型同时改变）。 歌词（主唱依次演唱以下每种语言的「你好」，精准对口型）： 英语：\"Hello\" 中文：\"你好\" 日语：\"こんにちは\" 韩语：\"안녕하세요\" 葡萄牙语：\"Olá\" 泰语：\"สวัสดี\" 西班牙语：\"Hola\" 阿拉伯语：\"مرحبا\" 镜头 1 [0:00–0:03] —— 低角度大远景定场，斯坦尼康在黄金夕照与海雾中缓缓推进，海浪在乐队身后翻涌。歌词第 1 句（英语「Hello」）。硬切。镜头 2 [0:03–0:05] —— 红运动服主唱对镜头 RAP 的特写，手持甩镜切入，身后海面虚焦粼粼波光。歌词第 2 句（中文「你好」）。硬切。镜头 3 [0:05–0:08] —— 微距插入镜头，固定机位，吉他手的手指在弦上快速拨动，沙粒与咸湿水雾从画面前掠过。歌词第 3 句（日语「こんにちは」）。硬切。镜头 4 [0:08–0:10] —— 对某位乐手的 3/4 侧中景，缓慢潜行环绕，乐器金属件与湿润高光映着海面低斜的夕阳。歌词第 4 句（韩语「안녕하세요」）。硬切。镜头 5 [0:10–0:13] —— 岸边一名乐手，快速横移轨道掠过他，他转向镜头，身后一道浪花破碎。歌词第 5 句（葡萄牙语「Olá」）。硬切。镜头 6 [0:13–0:15] —— 水边的鼓手，手持快速上摇，海风与水花吹动他的头发，他随节拍律动敲击。歌词第 6 句（泰语「สวัสดี」）。硬切。镜头 7 [0:15–0:18] —— 对红运动服主唱 flow 正酣时的紧凑猛推，富攻击性的手持，身后暮色海面衬着乐队剪影。歌词第 7 句（西班牙语「Hola」）。硬切。镜头 8 [0:18–0:20] —— 全乐队英雄式大远景，富攻击性的手持推进，主唱与乐手踩着节拍向镜头迈步，海浪拍碎、金色夕光在整支乐队身后炸开光晕。歌词第 8 句（阿拉伯语「مرحبا」）。 白平衡 4000K，青橙（teal-and-amber）调色，35mm，浅景深，胶片颗粒，弥漫的海雾，黄金时刻光晕。质感扎实、高级、高端。节奏感说唱表演，精准对口型，头随节拍点动。无字幕、无文字叠加、无叠化转场、无重复人物，仅用硬切。总时长 20 秒。"

	// Example resource URLs
	refImage1 := "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seedance2.5_multi_language_input.png"

	// Output video parameters
	generateAudio := true
	videoRatio := "16:9"
	videoDuration := int64(20)

	// 1. Create video generation task
	fmt.Println("----- create request -----")
	createReq := &model.CreateContentGenerationTaskRequest{
		Model:         modelID,
		GenerateAudio: model.NewOptBool(generateAudio),
		Ratio:         model.NewOptString(videoRatio),
		Duration:      model.NewOptInt64(videoDuration),
		Content: []model.ContentItem{
			{
				Type: model.ContentTypeText,
				Text: model.NewOptString(prompt),
			},
			{
				Type: model.ContentTypeImageURL,
				ImageURL: model.NewOptImageURL(model.ImageURL{
					URL: refImage1,
				}),
				Role: model.NewOptString("reference_image"),
			},
		},
		Watermark:     model.NewOptBool(true),
	}

	createResp, err := client.CreateContentGenerationTask(ctx, createReq)
	if err != nil {
		panic(fmt.Errorf("create content generation task: %w", err))
	}

	taskID := createResp.ID
	fmt.Printf("Task Created with ID: %s\n", taskID)

	// 2. Poll task status
	pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
	fmt.Println("----- polling task status -----")
	for {
		getReq := taskID
		getResp, err := client.GetContentGenerationTask(ctx, getReq)
		if err != nil {
			panic(fmt.Errorf("get content generation task: %w", err))
		}

		status := getResp.Status
		if status == "succeeded" {
			fmt.Println("----- task succeeded -----")
			fmt.Printf("Task ID: %s \n", getResp.ID)
			fmt.Printf("Model: %s \n", getResp.Model)
			fmt.Printf("Video URL: %s \n", getResp.Content.Or(model.TaskContent{}).VideoURL.Or(""))
			fmt.Printf("Completion Tokens: %d \n", getResp.Usage.Or(model.TaskUsage{}).CompletionTokens)
			fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt.Or(0), getResp.UpdatedAt.Or(0))
			return
		} else if status == "failed" {
			if getResp.Error.IsSet() {
				panic(fmt.Errorf("video generation task failed: %s: %s", getResp.Error.Value.Code, getResp.Error.Value.Message))
			}
			panic("video generation task failed")
		} else {
			fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
			time.Sleep(10 * time.Second)
		}
	}
}
```

<span id="2.5_more_capabilities"></span>
# 更多能力

Seedance 2.5 同样支持以下基础能力，详细使用方式和代码示例请参考对应链接：

- [**文生视频**](/docs/video-generation-tutorial#4e74bcee)：输入文本提示词生成一段视频。
- [**使用联网搜索**](/docs/seedance-2-0#c40ed3ef)：根据提示词自主判断是否搜索互联网内容（如商品、天气等）。提升生成视频的时效性。
- [**样片模式**](/docs/seedance-2-5#2.5_draft_mode)：先生成 480p Draft 视频验证效果，再基于 Draft 视频生成高质量成片。

<span id="2.5_draft_mode"></span>
## 样片模式
**样片（Draft）模式是一种“先快速验证效果，再生成高质量成片”的两步式视频生成方式**。开启该功能后，您可以更快速地生成一段低分辨率的预览视频，用于验证其场景结构、镜头调度、主体动作和提示词意图等关键要素；确认结果符合预期后，再使用 Draft 视频任务 ID 生成高质量成片。

> **注意：Draft 视频任务 ID 有效期**
>
> * Draft 视频任务 ID 存在有效期（从 `created_at` 时间戳开始计算），超时后将自动失效。
> * 2026 年 10 月 28 日 10:00（UTC+8）及之后创建的 Draft 视频任务 ID 有效期为 14 天，此前创建的 Draft 视频任务 ID 有效期仍为 7 天。超出有效期后，无法使用该 Draft 视频生成正式视频。

|输入 |Draft 视频 |正式视频 |
|---|---|---|
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ebb5217645b04cfc94209a6f7d36a523~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/7c190b3a0ed34b29bc1192acbce2f4d2) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/a82cd582a5d54f34a8adec10f2815081) | \
| | | | \
|<blockquote>提示词：女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声</blockquote> |<blockquote>生成一段 Draft 视频，预览并确认生成效果。</blockquote> |<blockquote>复用 Draft 视频使用的模型、提示词、输入素材、种子值、音频设置、视频宽高比、视频时长等关键参数生成正式视频，保证视频关键要素一致。</blockquote> |

### Step1:生成 Draft 视频
在调用 `POST /contents/generations/tasks` 接口创建生视频任务时，通过配置 `draft=true`，即可开启 Draft 模式。

> **注意**
>
> * 仅支持生成 480p 分辨率的 Draft 视频，设置其他分辨率将触发报错。
> * 生成 480p Draft 视频的 token 用量和单价，均与正常生成 480p 视频一致。
> * Draft 视频任务 ID 存在有效期（从 `created_at` 时间戳开始计算），超时后将自动失效。2026 年 10 月 28 日 10:00（UTC+8）及之后创建的 Draft 视频任务 ID 有效期为 14 天，此前创建的 Draft 视频任务 ID 有效期仍为 7 天。超出有效期后，无法使用该 Draft 视频生成正式视频。

**选项：Curl**

1. 创建 Draft 视频生成任务。
    > 请求成功后，系统将返回一个任务 ID。此 ID 即为 Draft 视频任务 ID，后续需基于这个 ID 生成最终视频。

    ```Bash
    curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $ARK_API_KEY" \
      -d '{
        "model": "doubao-seedance-2-5-260628",
        "content": [
          {
            "type": "text",
            "text": "女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，镜头缓缓拉远"
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/i2v_foxrgirl.png"
            }
          }
        ],
        "duration": 5,
        "ratio": "adaptive",
        "resolution": "480p",
        "output_format": "mov",
        "service_tier": "default",
        "draft": true,
        "watermark": true
      }'
    ```

2. 使用 Draft 视频任务 ID，查询生成状态和结果。
    > 当任务状态变为 `succeeded` 后，可在 `content.video_url` 字段处下载生成的 Draft 视频文件。确认 Draft 视频效果符合预期后，即可按照后续步骤生成最终视频。

    ```Bash
    curl "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/<DRAFT_TASK_ID>" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $ARK_API_KEY"
    ```

### Step2:生成正式视频
如果确认 Draft 视频符合预期，可基于 Step1 返回的 Draft 视频任务 ID，再次调用 `POST /contents/generations/tasks` 接口，生成最终视频。

> **注意**
>
> - 基于 Draft 视频生成正式视频时，当前仅支持生成 1080p 分辨率的视频，设置其他分辨率将触发报错。
> * Draft 视频任务 ID 存在有效期（从 `created_at` 时间戳开始计算），超时后将自动失效。2026 年 10 月 28 日 10:00（UTC+8）及之后创建的 Draft 视频任务 ID 有效期为 14 天，此前创建的 Draft 视频任务 ID 有效期仍为 7 天。超出有效期后，无法使用该 Draft 视频生成正式视频。
> - Step 1 和 Step 2 两类任务独立计费：
>   - Step 1：生成 Draft 视频，按 480p 视频计费。
>   - Step 2：基于 Draft 生成正式视频，按目标分辨率计费：
>     - token 单价**根据 Step 1 是否包含输入视频确定**。
>     - 计算 token 用量时，**输入视频时长按 Step 1 的输入视频计算，Draft 视频不计入**。

基于 Draft 视频生成正式视频时，不同参数的处理方式不同：部分需固定传入，部分由模型自动复用，部分可按成片需求重新设置。请按下表规则配置参数，避免请求报错。

| 类型 | 参数 | 规则 |
| --- | --- | --- |
| 取值固定参数 | * 模型 ID（`model`） | * `model` 必须与创建 Draft 任务时使用的一致。 | \
| | * 样片模式（`draft`） | * `draft` 可不传入或设置为 `false`。 | \
| | * 分辨率（`resolution`） | * `resolution` 必须传入，仅支持设置为 `1080p`。 |
| 自动复用参数 | * 提示词（`content.text`） | * 模型自动复用创建 Draft 任务时使用的参数取值。 | \
| | * 参考图片/视频/音频（`content.image_url`、`content.video_url`、`content.audio_url`） | * **禁止传入。即使传入值与 Draft 阶段使用的一致，也会触发报错**。 | \
| | * 时长（`duration`） | | \
| | * 宽高比（`ratio`） | | \
| | * 随机种子数（`seed`） | | \
| | * 是否生成有声视频（`generate_audio`） | | \
| | * 任务类型（`omni_reference_task_type`） | |
| 可重新指定参数 | * 返回尾帧（`return_last_frame`） | * 不传入时，自动使用模型默认值，不会沿用 Draft 视频的实际取值。 | \
| | | * 参数取值需满足 Seedance 2.5 模型对应的限制，详见 [创建视频生成任务 API](/docs/create-video-generation-task-api)。 | \
| | * 输出格式（`output_format`） | | \
| | * 水印（`watermark`） | | \
| | * 服务等级（`service_tier`） | | \
| | * 任务超时阈值（`execution_expires_after`） | | \
| | * 执行优先级（`priority`） | | \
| | * 回调地址（`callback_url`） | | \
| | * 用户标识（`safety_identifier`） | |

**选项：Curl**

1. 基于 `content.draft_task.id` 创建视频生成任务。

    ```Bash
    curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $ARK_API_KEY" \
      -d '{
        "model": "doubao-seedance-2-5-260628",
        "content": [
          {
            "type": "draft_task",
            "draft_task": {
              "id": "<DRAFT_TASK_ID>"
            }
          }
        ],
        "resolution": "1080p",
        "output_format": "mov",
        "watermark": true
      }'
    ```

2. 使用视频任务 ID，查询生成状态和结果。
    > 当任务状态变为 `succeeded` 后，可在 `content.video_url` 字段处下载生成的视频文件。

    ```Bash
    curl "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/<TASK_ID>" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $ARK_API_KEY"
    ```

<span id="2.5_video_output_specs"></span>
# 自定义视频输出规格
通过 API 参数控制输出视频的规格，包括分辨率、宽高比、时长、输出格式、是否包含水印等。

* **resolution**：指定输出视频的分辨率。
* **ratio**：指定输出视频的宽高比。
* **duration**：指定输出视频的时长。
* **output_format**：指定输出视频的格式。
* **watermark**：指定是否为输出视频添加水印。

<span id="2.5_resolution"></span>

## 分辨率

通过 **resolution** 参数指定输出视频的分辨率。

* 默认值：`720p`
* 可选值：
  * `480p`（8bit 位深）
  * `720p`（8bit 位深）
  * `1080p`（10bit 位深）

> **说明**
>
> **Seedance 2.5 输出的 1080p 视频采用 10bit 位深与 H.265/HEVC 编码**。
> * 相较于一般的 8bit 位深，10bit 位深能够保留更丰富的色彩层次与更平滑的渐变过渡，满足专业影视制作与 HDR 视频内容的要求。
> * H.265/HEVC 编码在少数播放环境中可能不兼容。如遇问题，建议升级系统、更换设备，或使用 VLC、MPV、QuickTime Player 等 [播放器](/docs/seedance-2-0#4k_player) 查看。

```Json
{
    "resolution": "720p"
}
```

<span id="2.5_ratio"></span>

## 宽高比

通过 **ratio** 参数指定输出视频的宽高比。

* 默认值：`adaptive`：即模型根据输入的提示词和参考素材，自动适配视频宽高比。
* 可选值：`16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive`

> **说明：adaptive 适配规则**
>
> * **视频编辑 / 视频延长**：模型根据提示词意图选定待编辑视频或待延长视频，并自动保持输出视频宽高比和待编辑视频或待延长视频一致。
> * **首帧 / 首尾帧生视频**：保持输出视频宽高比和 `first_frame` 指定的首帧图片一致。
> * **文生视频/参考生视频**：根据提示词选择可选宽高比中（`16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`）最合适的宽高比。

> **注意**
>
> `Seedance 2.5` 在视频编辑、视频延长、首帧 / 首尾帧生视频任务中，仅支持配置 `ratio` 为 `adaptive`，不可指定具体宽高比。

```Json
{
    "ratio": "16:9"
}
```

不同宽高比对应的宽高像素值：

| 分辨率 | 宽高比 | 像素尺寸（宽×高） |
| --- | --- | --- |
| 480p | 16:9 | 854×480 |
| ^^ | 4:3 | 752×560 |
| ^^ | 1:1 | 640×640 |
| ^^ | 3:4 | 560×752 |
| ^^ | 9:16 | 480×854 |
| ^^ | 21:9 | 992×432 |
| 720p | 16:9 | 1280×720 |
| ^^ | 4:3 | 1112×834 |
| ^^ | 1:1 | 960×960 |
| ^^ | 3:4 | 834×1112 |
| ^^ | 9:16 | 720×1280 |
| ^^ | 21:9 | 1470×630 |
| 1080p | 16:9 | 1920×1080 |
| ^^ | 4:3 | 1664×1248 |
| ^^ | 1:1 | 1440×1440 |
| ^^ | 3:4 | 1248×1664 |
| ^^ | 9:16 | 1080×1920 |
| ^^ | 21:9 | 2206×946 |

<span id="2.5_duration"></span>

## 视频时长

通过 **duration** 参数指定生成视频的时长（单位：秒）。

* 默认值：`-1`：即模型根据输入的提示词和参考素材，自动适配视频时长。
* 取值范围：`[4, 30]` 或 `-1`

> **说明：duration = -1 适配规则**
>
> * 视频编辑任务：模型根据提示词意图选定待编辑视频，并自动保持输出视频时长和待编辑视频基本一致。
>   * 输出视频可能是非整数秒
>   * 输出视频可能略短于待编辑视频，误差不超过 0.4 秒
> * 其他生视频任务：模型在 `[4, 30]` 范围内，自主选择合适的视频长度（整数秒）。

> **注意**
>
> `Seedance 2.5` 在视频编辑任务仅支持配置 `duration` 为 `-1`，不可指定具体时长；且传入的待编辑视频时长需在 `[4, 30]s` 内，否则将触发报错。

```Json
{
   "duration": 10
}
```

<span id="2.5_output_format"></span>

## 输出格式

通过 **output_format** 参数控制输出视频的格式。

* `mp4`（默认）：通用格式，兼容性最好，采用标准色彩精度可在网页、移动端、各类播放器及分发平台直接播放。
* `mov`：面向专业场景的高色彩精度格式，更好地保持画面色彩与亮度一致性、适用于调色、抠像、合成等对色彩还原要求高的专业后期加工。推荐在视频编辑和视频延长场景使用 mov 格式作为输入和输出。

> **说明：mov 格式播放兼容性**
>
> mov 格式采用专业编码（H.264视频编码+yuv444p 色度采样+PCM 音频编码），部分播放器可能不兼容。以下为常见的支持播放 mov 格式的播放器：
>
>
> | 播放器 | macOS | Windows |
> | --- | --- | --- |
> | IINA | ✓ | ✕ |
> | VLC | ✓ | ✓ |
> | mpv | ✓ | ✓ |
> | ffplay | ✓ | ✓ |

```Json
{
    "output_format": "mov"
}
```

<span id="2.5_watermark"></span>

## 视频中添加水印
通过 **watermark** 参数，来控制是否在生成的视频中添加水印。
- true：在视频右下角添加`AI生成`水印标识。
- false（默认）：不添加水印。
```Json
{
    "watermark": true
}
```

<span id="2.5_convenient_creation"></span>
# 便利创作含肖像视频

Seedance 2.5 支持与 Seedance 2.0 系列相同的便利创作功能，详细教程请参见 [Doubao Seedance 便利创作含肖像视频](/docs/seedance-portrait-asset-guide)：

|方案 |介绍 |
|---|---|
|[信任模型产物作为输入素材](/docs/seedance-portrait-asset-guide#trust-model-output) | 本账号下部分模型生成的含人脸原始产物可作为输入素材，再次调用 Seedance 2.5 系列模型进行二次创作，不会触发输入审核拦截。 |
| [使用预置虚拟人像](/docs/seedance-portrait-asset-guide#preset-avatar) |平台预置虚拟人像库，为创作者提供免费、合规、丰富多样的肖像素材。适用于需真人风格人脸但无需指定具体人物，追求零合规风险、快速创作的场景。 |
|[使用已授权真人素材](/docs/seedance-portrait-asset-guide#authorized-real-person) |支持使用已获得授权的真人肖像素材进行视频生成。 |

<span id="2.5_prompt_guide"></span>
# 提示词技巧

## 提示词 Skill

平台提供 **Seedance 2.5 提示词优化技能**，方便您对提示词进行调优。
1. **在本地项目中通过 NPX 安装**：
```Bash
npx --yes skills@latest add \
  "https://arkdocs.tos-cn-beijing.volces.com/skills/" \
  --skill sd25-pe \
  --yes
```
2. **使用方式**：在 AI 对话框输入 `/sd25-pe + 你的提示词内容`，开始调试提示词。

## 提示词规则

- **遵循基础公式**：按照"主体 + 动作/事件 + 场景与环境 + 视觉风格 + 运镜/切镜 + 声音"的顺序组织提示词，不需要的部分可省略。
- **明确素材职责**：使用 `@图片1`、`@视频1`、`@音频1` 指代参考素材，说明每份素材具体提供什么（如外貌、动作、音色），以及不采用什么。
- **声音用特殊字符区分**：音乐用 `()`、音效用 `<>`、台词用 `{}`、字幕用 `【】`。非中文台词建议在台词前明确语言。

完整的提示词撰写方法、模板和进阶技法详见 [Seedance 2.5 提示词指南](/docs/seedance-2-5-prompt-guide)。

<span id="2.5_usage_limits"></span>
# 使用限制

<span id="2.5_multimodal_input"></span>
## 全模态输入

> **注意**
>
> Seedance 2.5 不支持直接上传含有真人人脸的参考图/视频。
> 为了便利创作者对肖像的使用，平台推出了一系列解决方案，详情参见 [Doubao Seedance 便利创作含肖像视频](/docs/seedance-portrait-asset-guide)。

**图片要求**
* 传入方式：图片 URL、图片 Base64 编码、素材 ID。
* 图片格式：jpeg、png、webp、bmp、tiff、gif、heic、heif。
* 单个图片尺寸：

    * 宽高比（宽/高）： [0.4, 2.5]

    * 宽高长度（px）：[300, 6000]
* 大小：单张图片小于 30 MB。请求体大小不超过 64 MB。大文件请勿使用Base64编码。
* 图片数量：

    * 图生视频-首帧：1 张

    * 图生视频-首尾帧：2 张

    * 全模态参考生视频：1~30 张

**视频要求**
* 传入方式：视频URL、素材 ID。
* 视频格式：mp4、mov，支持编码格式见下表。
* 分辨率：480p，720p，1080p，4k
* 时长：
    * 非视频编辑任务：单个视频时长 [2, 30] s。
    * [视频编辑任务](/docs/seedance-2-5#2.5_task_type_intro)：单个视频时长 [4, 30] s。
    * 最多传入 10 个参考视频，所有视频总时长不超过 30 s。
* 单个视频尺寸：

    * 宽高比（宽/高）：[0.4, 2.5]

    * 宽高长度（px）：[300, 6000]

    * 总像素数：[614×664=407696, 3326×2494=8295044]，即宽和高的乘积符合 [407696, 8295044] 的区间要求。
* 大小：单个视频不超过 200 MB。
* 帧率 (FPS)：[24, 60]

|**容器格式** |**常用文件扩展名** |**MIME** |**支持编码** |
|---|---|---|---|
|MP4 |.mp4 |video/mp4 |视频：H.264/AVC、H.265/HEVC | \
| | | |音频：AAC、MP3 |
|QuickTime |.mov |video/quicktime |视频：H.264/AVC、H.265/HEVC | \
| | | |音频：AAC、MP3、PCM |

**音频要求**
* 传入方式：音频 URL 、音频 Base64 编码、素材 ID。
* 音频格式：wav、mp3
* 时长：单个音频时长 [2, 30] s，最多传入 10 段参考音频，所有音频总时长不超过 30 s。
* 大小：单个音频不超过 15 MB，请求体大小不超过 64 MB。大文件请勿使用Base64编码。

<span id="2.5_storage_duration"></span>
## 保存时间
- 视频任务 ID 存在有效期（从 `created_at` 时间戳开始计算），超时后将自动失效。
    - **Draft 视频任务 ID**：2026 年 10 月 28 日 10:00（UTC+8）及之后创建的 Draft 视频任务 ID 有效期为 14 天，此前创建的 Draft 视频任务 ID 有效期仍为 7 天。超出有效期后，无法使用该 Draft 视频生成正式视频。
    - **其他视频任务 ID**：有效期均为 7 天。
- 视频 URL：保存 24 小时（超时后无法访问），下载次数上限为 100 次，请及时下载或转存。

<span id="2.5_rate_limits"></span>
## 限流说明

同一主账号下，使用同一模型（不区分版本）的请求受到以下限制。超过对应限制会返回 “429: 'Too Many Requests'” 错误。

### 模型维度的限流

* **RPM（Requests Per Minute）**：每分钟允许创建的视频生成任务数上限。超过上限时，创建任务请求将因触发限流而失败。
* **最大并发任务数**：同一时刻可处于处理状态的任务数上限。达到上限后，新创建的任务将进入队列等待处理。

|限流维度 |企业用户 |个人用户 |
|---|---|---|
|最大 RPM |600 |180 |
|最大并发数 |10 |3 |

### 非推理 API 请求频率限制

* **QPS（Queries Per Second）**：每秒允许的请求数上限。超过上限时，任务请求将因触发限流而失败。

|接口名称 |账号维度的 QPS 上限 |
|---|---|
|查询视频生成任务 |20 |
|查询视频生成任务列表 |1 |
|取消或删除视频生成任务 |20 |
