# 创建视频生成任务

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

`POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks`

本文介绍创建视频生成任务 API 的输入输出参数，供您使用接口时查阅字段含义。模型会依据传入的图片及文本信息生成视频，待生成完成后，您可以按条件查询任务并获取生成的视频。

> **警告：使用必读**
>
> Seedance 2.5 已全面公开，您可在火山方舟平台调用 API 及在线体验。调用模型前，**请务必仔细查阅 [使用必读](/docs/seedance-2-5#2.5_compatibility)，以确保正确设置任务类型和配置参数**。

**模型开通条件**

开通 Seedance 2.5、Seedance 2.0 系列模型前，请确保您**满足以下任一条件**：
* **【推荐】账户余额 > 200 元**（[前往充值](https://console.volcengine.com/finance/fund/recharge)）
* **【推荐】购买 200 元档位及以上专属节省计划**，购买入口：[购买节省计划](https://console.volcengine.com/common-buy/AI-SavingsPlans%7C%7Cd682ppeeq1mp7kd5q0e0)。
* 已购买 Seedance 2.5、Seedance 2.0 系列资源包且有可用余量（[前往购买](https://console.volcengine.com/common-buy/ark_bd%7C%7Cd9li7rchmjlhari755h0)）

详细规则见 [Seedance 2.5 与 Seedance 2.0 系列模型开通、使用与退订说明](/docs/seedance-model-activation-usage-and-refund)。

**模型能力**

* **Doubao Seedance 2.5<sup>==new==</sup>**（有声视频 / 无声视频）
  * **全模态参考生视频**：输入参考图片（0-30 张）+ 参考视频（0-10 个）+ 参考音频（0-10 个）+ 文本提示词（可选）生成 1 个目标视频。支持仅传入音频。支持生成全新视频、编辑视频、延长视频，支持 30 秒视频连贯直出。
  * **图生视频-首尾帧**：输入首帧图片 + 尾帧图片 + 文本提示词（可选）生成 1 个目标视频。
  * **图生视频-首帧**：输入首帧图片 + 文本提示词（可选）生成 1 个目标视频。
  * **文生视频**：输入文本提示词生成 1 个目标视频。
* **Doubao Seedance 2.0 系列**（有声视频 / 无声视频）
  * **全模态参考生视频**：输入参考图片（0-9 张）+ 参考视频（0-3 个）+ 参考音频（0-3 个）+ 文本提示词（可选）生成 1 个目标视频。注意不可单独输入音频，应至少包含 1 个参考视频或图片。支持生成全新视频、编辑视频、延长视频。
  * **图生视频-首尾帧**：输入首帧图片 + 尾帧图片 + 文本提示词（可选）生成 1 个目标视频。
  * **图生视频-首帧**：输入首帧图片 + 文本提示词（可选）生成 1 个目标视频。
  * **文生视频**：输入文本提示词生成 1 个目标视频。
* **Doubao Seedance 1.0 pro**
  * 支持【图生视频-首尾帧】【图生视频-首帧】【文生视频】。
* **Doubao Seedance 1.0 pro fast**
  * 支持【图生视频-首帧】【文生视频】。

**参数传入方式说明**

> **说明**
>
> * 对于 `resolution`、`ratio`、`duration`、`frames`、`seed`、`camera_fixed`、`watermark` 参数，除了在 request body 中直接传入，也支持在文本提示词后追加 `--[parameters]` 的弱校验方式传参，所有模型均兼容。
> * 不同模型对应支持不同的参数与取值，详见 [输出视频格式](/docs/video-generation-tutorial#9fe4cce0)。当输入的参数或取值不符合所选的模型时，该参数将被忽略或触发报错：
>     * **常规方式（推荐）**：在 request body 中直接传入参数。此方式为**强校验**，若参数填写错误，模型会返回错误提示。
>     * **弱校验方式**：在文本提示词后追加 `--[parameters]`。若参数填写错误，该参数将被忽略或触发报错。

**常规方式（推荐）：在 request body 中直接传入参数**

```JSON
{
    "model": "doubao-seedance-1-0-pro-250528",
    "content": [
        {
            "type": "text",
            "text": "小猫对着镜头打哈欠"
        }
    ],
    "resolution": "720p",
    "ratio": "16:9",
    "duration": 5,
    "seed": 11,
    "camera_fixed": false,
    "watermark": true
}
```

**弱校验方式：在文本提示词后追加 `--[parameters]`**

```JSON
{
    "model": "doubao-seedance-1-0-pro-250528",
    "content": [
        {
            "type": "text",
            "text": "小猫对着镜头打哈欠 --rs 720p --rt 16:9 --dur 5 --seed 11 --cf false --wm true"
        }
    ]
}
```

## 鉴权

本接口支持鉴权方式如下，详情请参见 [Base URL 及鉴权](/docs/base-url-and-authentication)。

* API Key 鉴权，请在 [API Key 管理](https://ark.volcengine.com/region:cn-beijing/apiKey) 页面，获取长效 API Key。

---

<span id="request-parameters"></span>
## 请求参数

### Body 参数

**model** `string` `必选` | 模型 ID

您需要调用的模型的 ID（Model ID）。[开通模型服务](https://ark.volcengine.com/region:cn-beijing/openManagement?LLM=%7B%7D&OpenTokenDrawer=false) 后可 [查询 Model ID](/docs/model-list)。

您也可通过 Endpoint ID 来调用模型，获得限流、计费类型（前付费 / 后付费）、运行状态查询、监控、安全等高级能力，可参考 [获取 Endpoint ID](/docs/online-inference-standard)。

**content** `object[]` `必选` | 输入内容列表

输入给模型生成视频的信息，支持文本、图片、音频、视频、样片任务 ID 等多种类型的元素。

支持以下几种组合：

* 纯文本
* 文本（可选）+ 图片
* 文本（可选）+ 视频
* 文本（可选）+ 音频（仅 Seedance 2.5 支持单独传入音频）
* 文本（可选）+ 图片 + 音频
* 文本（可选）+ 图片 + 视频
* 文本（可选）+ 视频 + 音频
* 文本（可选）+ 图片 + 视频 + 音频
* 样片任务 ID：样片指使用 Seedance 模型成功生成的样片视频，模型可基于样片生成高质量正式视频

> **注意**
>
> Seedance 2.5、Seedance 2.0 系列模型不支持直接上传含有真人人脸的参考图 / 视频。
>
> 为了便利创作者对肖像的使用，平台推出了以下解决方案，详情参见 [教程](/docs/seedance-2-0#5c67c9a1)。
>
> * 支持使用部分模型的含人脸原始产物作为输入素材
> * 支持使用预置虚拟人像作为输入素材
> * 支持使用已授权真人素材作为输入

文本信息 `object`

文本部分，作为生成内容的文本提示词。

**type** `string` `必选` | 内容类型

`content.type`

输入内容的类型，此处固定为 `text`。

**text** `string` `必选` | 文本提示词

`content.text`

输入给模型的文本提示词，描述期望生成的视频。

> **说明**
>
> * **提示词语言支持**：所有模型均支持中英文提示词；
>     * **Seedance 2.5**：额外支持西班牙语、印度尼西亚语、葡萄牙语、日语、马来语、泰语、阿拉伯语、越南语、韩语；
>     * **Seedance 2.0 系列**：额外支持西班牙语、印度尼西亚语、葡萄牙语、日语。
> * **提示词字数建议**：中文提示词不超过 500 字，英文提示词不超过 1000 词。字数过多易导致信息分散，模型可能忽略细节、仅关注重点，进而造成视频缺失部分元素。
> * **更多使用技巧**：提示词的详细使用技巧，请参见 [Seedance 提示词指南](/docs/seedance-2-0-prompt-guide)。

图片信息 `object`

输入给模型的图片信息。

**type** `string` `必选` | 内容类型

`content.type`

输入内容的类型，此处固定为 `image_url`。

**image_url** `object` `必选` | 图片对象

`content.image_url`

输入给模型的图片对象。

**url** `string` `必选` | 图片来源

`content.image_url.url`

图片 URL、图片 Base64 编码、素材 ID。

* **图片 URL**：填入图片的公网 URL。
* **Base64 编码**：将本地文件转换为 Base64 编码字符串后提交给大模型，遵循格式 `data:image/<图片格式>;base64,<Base64 编码>`，注意 `<图片格式>` 需小写，如 `data:image/png;base64,{base64_image}`。
* **素材 ID**：用于视频生成的预置素材及虚拟人像的 ID，遵循格式 `asset://<ASSET_ID>`。可从 [素材 & 虚拟人像库](https://ark.volcengine.com/region:cn-beijing/experience/gen_video?model=doubao-seedance) 获取。

> **说明：传入单张图片要求**
>
> * **格式**：`jpeg`、`png`、`webp`、`bmp`、`tiff`、`gif`。其中，Seedance 2.0 系列及以上模型版本额外支持 `heic`、`heif`。
> * **宽高比（宽/高）**：`[0.4, 2.5]`
> * **宽高长度（px）**：`[300, 6000]`
> * **大小**：单张图片小于 30 MB。请求体大小不超过 64 MB。大文件请勿使用 Base64 编码。
> * **图片数量**：
>     * **图生视频-首帧**：1 张
>     * **图生视频-首尾帧**：2 张
>     * **Seedance 2.5 全模态参考生视频**：1-30 张
>     * **Seedance 2.0 系列全模态参考生视频**：1-9 张

**role** `string` | 角色/用途

`content.role`

图片的位置或用途。

图生视频-首帧

**字段 `role` 取值**：需要传入 1 个 `image_url` 对象，`role` 为 `first_frame` 或不填。

图生视频-首尾帧

**字段 `role` 取值**：需要传入 2 个 `image_url` 对象，且 `role` 必填。
* 首帧图片对应的 `role` 为 `first_frame`
* 尾帧图片对应的 `role` 为 `last_frame`

> **说明**
>
> 传入的首尾帧图片可相同。首尾帧图片的宽高比不一致时，以首帧图片为主，尾帧图片会自动裁剪适配。

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`
* `Seedance 1.0 pro`

图生视频-参考图

**字段 `role` 取值**：必填，每张参考图对应的 `role` 均为 `reference_image`。

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`

> **注意**
>
> * **图生视频-首帧**、**图生视频-首尾帧**、**全模态参考生视频**（包括参考图、视频、音频）为 3 种互斥场景，**不可混用**。
> * **全模态参考生视频**可通过提示词指定参考图片作为首帧 / 尾帧，间接实现「首尾帧 + 全模态参考」效果。若需严格保障首尾帧和指定图片一致，**优先使用图生视频-首尾帧**（配置 `role` 为 `first_frame` / `last_frame`）。

视频信息 `object`

输入给模型的视频信息。

方舟平台信任 Seedance 2.5、Seedance 2.0 系列模型生成的含人脸视频，您可使用**本账号下近 30 天内**由上述模型生成的含人脸原始视频，作为输入素材进行二次创作。

详情参见 [教程](/docs/seedance-portrait-asset-guide#trust-model-output)。

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`

**type** `string` `必选` | 内容类型

`content.type`

输入内容的类型，此处固定为 `video_url`。

**video_url** `object` `必选` | 视频对象

`content.video_url`

输入给模型的视频对象。

**url** `string` `必选` | 视频来源

`content.video_url.url`

视频 URL、素材 ID。

* **视频 URL**：填入视频的公网 URL。
* **素材 ID**：用于视频生成的预置素材及虚拟人像视频的 ID，遵循格式 `asset://<ASSET_ID>`。可从 [素材 & 虚拟人像库](https://ark.volcengine.com/region:cn-beijing/experience/gen_video?model=doubao-seedance) 获取。

> **说明：传入单个视频要求**
>
> * **视频格式**：`mp4`、`mov`，支持编码格式见下表。
> * **分辨率**：`480p`、`720p`、`1080p`、`4k`
> * **时长**：
>     * **Seedance 2.5**：
>         * 非视频编辑任务：单个视频时长 `[2, 30]` s。
>         * [视频编辑任务](/docs/seedance-2-5#2.5_task_type_intro)：单个视频时长 `[4, 30]` s。
>         * 最多传入 10 个参考视频，所有视频总时长不超过 30 s。
>     * **Seedance 2.0 系列**：单个视频时长 `[2, 15]` s，最多传入 3 个参考视频，所有视频总时长不超过 15 s。
> * **尺寸**：
>     * **宽高比（宽/高）**：`[0.4, 2.5]`
>     * **宽高长度（px）**：`[300, 6000]`
>     * **总像素数**：`[614×664=407696, 3326×2494=8295044]`，即宽和高的乘积符合 `[407696, 8295044]` 的区间要求。
> * **大小**：单个视频不超过 200 MB。
> * **帧率（FPS）**：`[24, 60]`

**支持的视频编码格式**：

| 容器格式 | 常用文件扩展名 | MIME | 支持编码 |
| --- | --- | --- | --- |
| MP4 | .mp4 | video/mp4 | 视频：H.264/AVC、H.265/HEVC；音频：AAC、MP3 |
| QuickTime | .mov | video/quicktime | 视频：H.264/AVC、H.265/HEVC；音频：AAC、MP3、PCM |

**role** `string` `必选` | 角色/用途

`content.role`

视频的位置或用途，此处固定为 `reference_video`。

音频信息 `object`

用作参考音频。

**模型支持**：

* **Seedance 2.5**：可仅传入音频，无需搭配图片 / 视频；也可配合图片 / 视频一起传入
* **Seedance 2.0 系列**：不可单独输入音频，应至少包含 1 个参考视频或图片。

**type** `string` `必选` | 内容类型

`content.type`

输入内容的类型，此处固定为 `audio_url`。

**audio_url** `object` `必选` | 音频对象

`content.audio_url`

输入给模型的音频对象。

**url** `string` `必选` | 音频来源

`content.audio_url.url`

音频 URL、音频 Base64 编码、素材 ID。

* **音频 URL**：填入音频的公网 URL。
* **Base64 编码**：将本地文件转换为 Base64 编码字符串后提交给大模型，遵循格式 `data:audio/<音频格式>;base64,<Base64 编码>`，注意 `<音频格式>` 需小写，如 `data:audio/wav;base64,{base64_audio}`。
* **素材 ID**：用于视频生成的虚拟人的音频素材 ID，遵循格式 `asset://<ASSET_ID>`。可从 [素材 & 虚拟人像库](https://ark.volcengine.com/region:cn-beijing/experience/gen_video?model=doubao-seedance) 获取。

> **说明：传入单个音频要求**
>
> * **格式**：`wav`、`mp3`
> * **时长**：
>     * **Seedance 2.5**：单个音频时长 `[2, 30]` s，最多传入 10 段参考音频，所有音频总时长不超过 30 s。
>     * **Seedance 2.0 系列**：单个音频时长 `[2, 15]` s，最多传入 3 段参考音频，所有音频总时长不超过 15 s。
> * **大小**：单个音频不超过 15 MB，请求体大小不超过 64 MB。大文件请勿使用 Base64 编码。

**role** `string` `必选` | 角色/用途

`content.role`

音频的位置或用途，此处固定为 `reference_audio`。

样片信息 `object`

样片信息。基于样片任务 ID，生成正式视频。[阅读文档](/docs/video-generation-tutorial#5acd28c8) 获取 draft 功能的使用教程和注意事项。

**模型支持**：

* `Seedance 2.5`

**type** `string` `必选` | 内容类型

`content.type`

输入内容的类型，此处固定为 `draft_task`。

**draft_task** `object` `必选` | 样片任务对象

`content.draft_task`

输入给模型的样片任务对象。

**id** `string` `必选` | 样片任务 ID

`content.draft_task.id`

样片任务 ID。

基于 Draft 视频生成正式视频时，部分参数由模型自动复用，部分参数禁止重复传入，部分参数可重新指定。详细规则参见 [Seedance 2.5 样片模式](/docs/seedance-2-5#2.5_draft_mode)。

使用分为两步：

* **Step 1**：调用本接口生成 Draft 视频。
* **Step 2**：如果确认 Draft 视频符合预期，可基于 Step 1 返回的 Draft 视频任务 ID 调用本接口生成最终视频。

> **注意**
>
> * Draft 视频任务 ID 存在有效期（从 `created_at` 时间戳开始计算），超时后将自动失效。
>
> * 2026 年 10 月 28 日 10:00（UTC+8）及之后创建的 Draft 视频任务 ID 有效期为 14 天，此前创建的 Draft 视频任务 ID 有效期仍为 7 天。超出有效期后，无法使用该 Draft 视频生成正式视频。

**omni_reference_task_type<sup>==new==</sup>** `string` `默认值 auto` | 任务类型引导

Seedance 2.5 **全模态参考生视频任务**包括参考生视频、视频编辑和视频延长 3 类子任务。不同任务类型对参数有特殊限制，为减少任务创建后异步报错的情况，可通过本参数指定子任务类型，以提前校验对应限制。

* 默认情况下，即 `omni_reference_task_type=auto`：模型根据输入素材和提示词自动判定任务类型，再校验参数取值。如果参数与实际任务类型不兼容，任务将触发 [异步报错](/docs/seedance-2-5#2.5_async_error)（错误码：[`InvalidParameter.TaskTypeConstraint`](/docs/error-codes)）。
* 显式指定任务类型，即 `omni_reference_task_type` 为 `reference`、`edit` 或 `extend`：接口在提交任务时提前校验对应任务的特殊参数限制。不符合要求时，接口立即报错，任务不会创建。

> **注意**
>
> 实际处理任务时，模型仍会进一步结合提示词判断任务类型。若实际判定的任务类型和指定的不一致，仍会触发 [异步报错](/docs/seedance-2-5#2.5_async_error)（错误码：[`InvalidParameter.TaskTypeMismatch`](/docs/error-codes)）。建议遵循各任务类型的 [提示词写法](/docs/seedance-2-5#2.5_param_constraints)，降低报错概率。

**可选值：**

* `auto`：由模型根据输入素材和提示词自动判定任务类型。
* `reference`：参考生视频任务，即基于参考图片、参考视频或参考音频生成新视频。设置 `reference` 时，`ratio` 或 `duration` 无特殊限制。
* `edit`：视频编辑任务，即对原视频的画面或音频进行编辑操作。设置 `edit` 时，`content` 中必须至少包含一个 `reference_video`，且视频时长必须为 4–30 秒；`ratio` 必须为 `adaptive`；`duration` 必须为 `-1`。
* `extend`：视频延长任务，即对原视频向前或向后延长。设置 `extend` 时，`content` 中必须至少包含一个 `reference_video`；`ratio` 必须为 `adaptive`。

**模型支持**：

* `Seedance 2.5`

**resolution** `string` | 视频分辨率

视频分辨率。可选值：`480p`、`720p`、`1080p`、`4k`。

> **说明**
>
> * `Seedance 2.5` 输出的 1080p 视频和 `Seedance 2.0` 输出的 4k 视频均采用 10bit 位深与 H.265/HEVC 编码。
>   * 相较于一般的 8bit 位深，10bit 位深能够保留更丰富的色彩层次与更平滑的渐变过渡，满足专业影视制作与 HDR 视频内容的要求。
>   * H.265/HEVC 编码在少数播放环境中可能不兼容。如遇问题，建议升级系统、更换设备，或使用 VLC、MPV、QuickTime Player 等播放器查看。播放兼容性说明详见 [10bit 位深与 H.265/HEVC 编码视频播放兼容性说明](/docs/seedance-2-0#4k_player)。

**模型支持**：

* **Seedance 2.5**：默认值 `720p`；可选值 `480p`、`720p`、`1080p`
* **Seedance 2.0**：默认值 `720p`；可选值 `480p`、`720p`、`1080p`、`4k`
* **Seedance 2.0 fast**：默认值 `720p`；可选值 `480p`、`720p`
* **Seedance 2.0 mini**：默认值 `720p`；可选值 `480p`、`720p`
* **Seedance 1.0 pro**：默认值 `1080p`；可选值 `480p`、`720p`、`1080p`
* **Seedance 1.0 pro fast**：默认值 `1080p`；可选值 `480p`、`720p`、`1080p`

**ratio** `string` | 视频宽高比

生成视频的宽高比例。
* 可选值：`16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive`（根据任务类型和输入内容自动适配宽高比）

不同模型的取值限制和 `adaptive` 适配规则

|任务类型 | |Seedance 2.5 |Seedance 2.0 系列 |Seedance 1.0 系列 |
|---|---|---|---|---|
|文生视频 | |支持在可选宽高比中自行设置，或由模型根据提示词在可选宽高比中自动选择 |支持在可选宽高比中自行设置，或由模型根据提示词在可选宽高比中自动选择 |仅支持在可选宽高比中自行设置 | \
| | |> 支持 `adaptive` 或指定宽高比 |> 支持 `adaptive` 或指定宽高比 |> 不支持 `adaptive` |
|首帧或首尾帧生视频 | |**自动保持输出视频宽高比和 `first_frame` 指定的首帧图片一致** |支持在可选宽高比中自行设置，或由模型根据首帧图在可选宽高比中自动选择 |支持在可选宽高比中自行设置，或由模型根据首帧图在可选宽高比中自动选择 | \
| | |> 默认且仅支持 `adaptive` |> 支持 `adaptive` 或指定宽高比 |> 支持 `adaptive` 或指定宽高比 |
|全模态参考生视频 |视频编辑 / 视频延长 |**模型根据提示词意图选定待编辑视频或待延长视频，并自动保持输出视频宽高比和待编辑视频或待延长视频一致，不支持另行设置** |支持在可选宽高比中自行设置，或由模型根据待编辑视频或待延长视频在可选宽高比中自动选择 |— | \
| | |> 默认且仅支持 `adaptive` |> 支持 `adaptive` 或指定宽高比 | |
|^^ |参考生视频 |支持在可选宽高比中自行设置，或由模型根据提示词在可选宽高比中自动选择 |支持在可选宽高比中自行设置，或由模型根据提示词在可选宽高比中自动选择 |— | \
| | |> 支持 `adaptive` 或指定宽高比 |> 支持 `adaptive` 或指定宽高比 | |

不同宽高比对应的宽高像素值

图生视频，选择的宽高比与您上传的图片宽高比不一致时，方舟会对您的图片进行裁剪，裁剪时会居中裁剪，详细规则见 [图片裁剪规则](/docs/video-generation-tutorial#f76aafc8)。

| 分辨率 | 宽高比 | 宽高像素值 Seedance 2.5 | 宽高像素值 Seedance 2.0 系列 | 宽高像素值 Seedance 1.0 系列 |
| --- | --- | --- | --- | --- |
| 480p | `16:9` | 854×480 | 864×496 | 864×480 |
| ^^ | `4:3` | 752×560 | 752×560 | 736×544 |
| ^^ | `1:1` | 640×640 | 640×640 | 640×640 |
| ^^ | `3:4` | 560×752 | 560×752 | 544×736 |
| ^^ | `9:16` | 480×854 | 496×864 | 480×864 |
| ^^ | `21:9` | 992×432 | 992×432 | 960×416 |
| 720p | `16:9` | 1280×720 | 1280×720 | 1248×704 |
| ^^ | `4:3` | 1112×834 | 1112×834 | 1120×832 |
| ^^ | `1:1` | 960×960 | 960×960 | 960×960 |
| ^^ | `3:4` | 834×1112 | 834×1112 | 832×1120 |
| ^^ | `9:16` | 720×1280 | 720×1280 | 704×1248 |
| ^^ | `21:9` | 1470×630 | 1470×630 | 1504×640 |
| 1080p<br>（Seedance 2.0 fast/mini 暂不支持） | `16:9` | 1920×1080 | 1920×1080 | 1920×1088 |
| ^^ | `4:3` | 1664×1248 | 1664×1248 | 1664×1248 |
| ^^ | `1:1` | 1440×1440 | 1440×1440 | 1440×1440 |
| ^^ | `3:4` | 1248×1664 | 1248×1664 | 1248×1664 |
| ^^ | `9:16` | 1080×1920 | 1080×1920 | 1088×1920 |
| ^^ | `21:9` | 2206×946 | 2206×946 | 2176×928 |
| 4k | `16:9` | — | 3840×2160 | — |
| ^^ | `4:3` | — | 3326×2494 | — |
| ^^ | `1:1` | — | 2880×2880 | — |
| ^^ | `3:4` | — | 2494×3326 | — |
| ^^ | `9:16` | — | 2160×3840 | — |
| ^^ | `21:9` | — | 4398×1886 | — |

> **注意**
>
> Seedance 2.5 模型在**视频编辑、视频延长、首帧 / 首尾帧生视频任务**（详见 [任务类型与判定条件](/docs/seedance-2-5#2.5_task_type_intro)）存在特殊限制：
> * 仅支持配置`ratio`为 `adaptive`，不支持指定具体宽高比。
>   * 视频编辑 / 视频延长任务中，模型根据提示词意图选定待编辑视频或待延长视频，并自动保持输出视频宽高比和待编辑视频或待延长视频一致。
>   * 首帧 / 首尾帧生视频任务中，模型自动保持输出视频宽高比和 `first_frame` 指定的首帧图片一致。

**模型支持**：

* **Seedance 2.5**：默认值 `adaptive`
* **Seedance 2.0 系列**：默认值 `adaptive`
* **Seedance 1.0 pro**：文生视频默认 `16:9`，图生视频默认 `adaptive`
* **Seedance 1.0 pro fast**：文生视频默认 `16:9`，图生视频默认 `adaptive`

**duration** `integer` | 视频时长

生成视频时长（单位：秒）。

`duration` 和 `frames` 二选一即可，`frames` 优先级更高。如果您希望生成整数秒的视频，建议指定 `duration`。

不同模型的 `duration = -1` 适配规则

当 `duration` 设置为 `-1` 时，实际生成视频的时长可通过 [查询视频生成任务 API](/docs/get-video-generation-task-api) 返回的 `duration` 字段获取。视频时长与计费相关，请谨慎设置。

| 模型 | `duration = -1`取值规则 |
| --- | --- |
| Seedance 2.0 系列 | 模型在 `duration` 的有效取值范围内，自主选择合适的视频长度（整数秒）。 |
| Seedance 2.5（视频编辑任务） | 模型根据提示词意图选定待编辑视频，并自动保持输出视频时长和待编辑视频基本一致，不支持另行设置。 | \
| |> 输出时长可能为非整数秒 | \
| |> 输出时长可能略短于待编辑视频，误差约 0.4 秒 |
| Seedance 2.5（其他任务类型） | 模型在 `duration` 的有效取值范围内，自主选择合适的视频长度（整数秒）。 |

> **说明：duration 返回值说明**
>
> 通过 [查询视频生成任务 API](/docs/get-video-generation-task-api) 接口返回的 `duration` 值为视频的时长约数（整数秒），与实际的视频时长可能不同。具体返回规则如下：
> - 计算公式：接口返回的 `duration` = 实际总帧数 / 24（向下取整）
> - 举例：若最终生成视频为 133 帧，视频实际时长为 133 / 24 = 5.54 秒；向下取整后，`duration` 最终返回值为 5

> **注意**
>
> Seedance 2.5 模型在**视频编辑任务**（详见 [任务类型与判定条件](/docs/seedance-2-5#2.5_task_type_intro)）存在特殊限制：
> * 仅支持配置`duration`为 `-1`，不支持指定具体输出时长。
> * 传入的待编辑视频时长需在 `[4, 30]s` 内，否则将触发报错。

**模型支持**：

* **Seedance 2.5**：默认值 `-1`；取值范围 `[4, 30]`；或设置为 `-1`（智能选择）
* **Seedance 2.0 系列**：取值范围 `[4, 15]`；或设置为 `-1`（智能选择）
* **Seedance 1.0 pro**：取值范围 `[2, 12]`
* **Seedance 1.0 pro fast**：取值范围 `[2, 12]`

**frames** `integer` | 视频帧数

生成视频的帧数。通过指定帧数可以灵活控制生成视频的长度，生成小数秒的视频。

由于 `frames` 的取值限制，仅能支持有限小数秒，您需要根据公式推算最接近的帧数：

* **计算公式**：帧数 = 时长 × 帧率（24）
* **格式约束**：支持 `[29, 289]` 区间内所有满足 `25 + 4n` 格式的整数值，其中 n 为正整数

**举例**：假设需要生成 2.4 秒的视频，帧数 = 2.4 × 24 = 57.6。由于 `frames` 不支持 57.6，您只能选择一个最接近的值——根据 `25 + 4n` 计算出最接近的帧数为 57，实际生成的视频为 57 / 24 = 2.375 秒。

`duration` 和 `frames` 二选一即可，`frames` 优先级更高。

**取值范围**：`[29, 289]`

**模型支持**：

* `Seedance 1.0 pro`
* `Seedance 1.0 pro fast`

**generate_audio** `boolean` `默认值 true` | 生成有声视频

控制生成的视频是否包含与画面同步的声音。

* `true`：模型输出的视频包含同步音频，模型会基于文本提示词与视觉内容自动生成匹配的人声、音效及背景音乐。建议将对话部分置于双引号内以优化音频生成效果，例如：男人叫住女人说："你记住，以后不可以用手指指月亮。"
* `false`：模型输出的视频为无声视频。

> **注意**
>
> Seedance 2.0 及之后版本生成的有声视频均为双声道，与传入的音频声道数无关。

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`

**watermark** `boolean` `默认值 false` | 视频水印

生成视频是否包含水印。

* `true`：生成视频右下角会展示 `AI 生成` 水印。
* `false`：生成视频不含水印。

**output_format<sup>==new==</sup>** `string` `默认值 mp4` | 输出格式

输出视频的格式。
* `mp4`：通用格式，兼容性最好，采用标准色彩精度，可在网页、移动端、各类播放器及分发平台直接播放。
* `mov`：面向专业场景的高色彩精度格式，更好地保持画面色彩与亮度一致性、适用于调色、抠像、合成等对色彩还原要求高的专业后期加工。推荐在视频编辑、视频延长场景使用 mov 格式作为输入和输出。

> **说明：mov 格式播放兼容性**
>
> mov 格式采用专业编码（H.264 视频编码+yuv444p 色度采样+PCM 音频编码），部分播放器可能不兼容。以下为常见的支持播放 mov 格式的播放器：
>
> | 播放器 | macOS | Windows |
> | --- | --- | --- |
> | IINA | ✓ | ✕ |
> | VLC | ✓ | ✓ |
> | mpv | ✓ | ✓ |
> | ffplay | ✓ | ✓ |

**模型支持**：

* `Seedance 2.5`

**seed** `integer` `默认值 -1` | 随机种子

种子整数，用于控制生成内容的随机性。`-1` 表示使用随机数替代。

> **注意**
>
> * 相同的请求下，模型收到不同的 `seed` 值（不指定、令 `seed=-1` 或手动变更），将生成不同的结果。
> * 相同的请求下，模型收到相同的 `seed` 值，会生成类似的结果，但不保证完全一致。

**取值范围**：`[-1, 2147483647]`

**模型支持**：

* `Seedance 1.0 pro`
* `Seedance 1.0 pro fast`

**camera_fixed** `boolean` `默认值 false` | 固定摄像头

是否固定摄像头。

* `true`：固定摄像头。平台会在用户提示词中追加固定摄像头，实际效果不保证。
* `false`：不固定摄像头。

参考图场景不支持。

**模型支持**：

* `Seedance 1.0 pro`
* `Seedance 1.0 pro fast`

**return_last_frame** `boolean` `默认值 false` | 返回尾帧

是否返回生成视频的尾帧图像。

* `true`：返回生成视频的尾帧图像，可通过 [查询视频生成任务接口](/docs/get-video-generation-task-api) 获取，尾帧图像的格式为 `jpeg`，宽高像素值与生成的视频保持一致，无水印。
* `false`：不返回生成视频的尾帧图像。

使用该参数可实现生成多个连续视频：以上一个生成视频的尾帧作为下一个视频任务的首帧，快速生成多个连续视频，调用示例详见 [教程](/docs/video-generation-tutorial#141cf7fa)。

**draft** `boolean` `默认值 false` | 样片模式

控制是否开启样片模式。[阅读文档](/docs/video-generation-tutorial#5acd28c8) 获取使用教程和注意事项。

* `true`：开启样片模式，生成一段预览视频，用于确认场景结构、镜头调度、主体动作与 Prompt 意图是否符合预期。
* `false`：关闭样片模式，正常生成一段视频。

> **说明**
>
> * 开启样片模式后，仅支持生成 480p 分辨率的 Draft 视频（使用其他分辨率会报错）。
>
> * Draft 视频任务 ID 存在有效期（从 `created_at` 时间戳开始计算），超时后将自动失效。2026 年 10 月 28 日 10:00（UTC+8）及之后创建的 Draft 视频任务 ID 有效期为 14 天，此前创建的 Draft 视频任务 ID 有效期仍为 7 天。超出有效期后，无法使用该 Draft 视频生成正式视频。
>
> * 参数限制和计费方式详见 [Seedance 2.5 样片模式](/docs/seedance-2-5#2.5_draft_mode)。

**模型支持**：

* `Seedance 2.5`

**service_tier** `string` `默认值 default` | 服务等级

指定处理本次请求的服务等级类型。

* `default`：在线推理模式，RPM 和并发数配额较低（详见 [模型列表](/docs/model-list#7571da3f)），适合对推理时效性要求较高的场景。
* `flex`：离线推理模式，TPD 配额更高（详见 [模型列表](/docs/model-list#7571da3f)），价格为在线推理的 50%，适合对推理时延要求不高的场景。`Seedance 2.5`、`Seedance 2.0 系列`暂不支持。

> **注意**
>
> 不支持修改已提交任务的服务等级。

**模型支持**：

* `Seedance 1.0 pro`
* `Seedance 1.0 pro fast`

**callback_url** `string` | 回调地址

填写本次生成任务结果的回调通知地址。当视频生成任务有状态变化时，方舟将向此地址推送 POST 请求，请求内容结构与 [查询任务 API](/docs/get-video-generation-task-api) 的返回体一致。

> **说明**
>
> 回调返回的 `status` 包括以下状态：
>
> * `queued`：排队中
> * `running`：任务运行中
> * `succeeded`：任务成功（如发送失败，即 5 秒内未接收到成功发送的信息，会回调三次）
> * `failed`：任务失败（如发送失败，即 5 秒内未接收到成功发送的信息，会回调三次）
> * `expired`：任务超时，即任务处于「运行中或排队中」状态超过过期时间，可通过 `execution_expires_after` 字段设置过期时间

**execution_expires_after** `integer` `默认值 172800` | 任务超时阈值

任务超时阈值。指定任务提交后的过期时间（单位：秒），从 `created_at` 时间戳开始计算，默认 48 小时。

超过该时间后任务会被自动终止，并标记为 `expired` 状态。

不论使用哪种 `service_tier`，都建议根据业务场景设置合适的超时时间。

**取值范围**：`[3600, 259200]`

**priority** `integer` `默认值 0` | 执行优先级

设置当前请求的执行优先级，决定其在队列中的排序位置。数值越大，优先级越高。

默认情况下，请求按 FIFO（First In, First Out，先进先出）顺序执行；设置较高优先级后，该请求将插队到同 Endpoint（推理接入点）下所有低优先级请求之前。

**示例**：某 Endpoint 当前队列中有 3 个排队中（`status=queued`）任务，优先级均为 0（默认）：

```
队列：[任务 A: priority=0] → [任务 B: priority=0] → [任务 C: priority=0]
```

此时提交一个 `priority=5` 的新请求，该请求将直接排到队首：

```
队列：[新请求: priority=5] → [任务 A: priority=0] → [任务 B: priority=0] → [任务 C: priority=0]
```

> **说明**
>
> * 相同优先级的请求之间仍按 FIFO 排序。
> * 优先级仅影响排队顺序，不会中断正在执行中（`status=running`）的任务。
> * 优先级仅在同一 Endpoint 内生效，不影响其他 Endpoint。
> * 离线推理模式（`service_tier=flex`）不支持配置优先级。

**取值范围**：`[0, 9]`

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`

**safety_identifier** `string` | 用户标识

终端用户的唯一标识符，用于协助平台检测您的应用中可能违反火山方舟使用政策的用户。该标识符为英文字符串，需保证对单个用户固定且唯一，长度不超过 64 个字符。

推荐传入对用户名、用户 ID 或邮箱进行哈希处理后生成的字符串，避免泄露用户隐私信息。

**tools** `object[]` | 工具配置

配置模型要调用的工具。

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`

**type** `string` `必选` | 工具类型

`tools.type`

指定使用的工具类型。

* `web_search`：联网搜索工具。开启联网搜索后，模型会根据用户的提示词自主判断是否搜索互联网内容（如商品、天气等）。可提升生成视频的时效性，但也会增加一定的时延。[阅读教程](/docs/seedance-2-0#c40ed3ef) 获取详细代码示例。

> **说明**
>
> 实际搜索次数可通过 [查询视频生成任务 API](/docs/get-video-generation-task-api) 返回的 `usage.tool_usage.web_search` 字段获取，如果为 0 表示未搜索。

## 响应参数

**id** `string` | 任务 ID

视频生成任务 ID 存在有效期（从 `created_at` 时间戳开始计算），超时后将自动失效。

* **Draft 视频任务 ID**：2026 年 10 月 28 日 10:00（UTC+8）及之后创建的 Draft 视频任务 ID 有效期为 14 天，此前创建的 Draft 视频任务 ID 有效期仍为 7 天。超出有效期后，无法使用该 Draft 视频生成正式视频。
* **其他视频任务 ID**：有效期均为 7 天。

创建视频生成任务为**异步接口**，获取 ID 后需要通过 [查询视频生成任务 API](/docs/get-video-generation-task-api) 来查询任务状态。任务成功后会输出生成视频的 `video_url`。


## 代码示例

## 全模态参考

### Python


#### Request

```python
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=11, ratio='16:9', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

### Java


#### Request

```java
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=11, ratio='16:9', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

### Go


#### Request

```go
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=11, ratio='16:9', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

### cURL


#### Request

```bash
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=11, ratio='16:9', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

## 编辑视频

### Python


#### Request

```python
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=16, ratio='5:4', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

### Java


#### Request

```java
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=16, ratio='5:4', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

### Go


#### Request

```go
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=16, ratio='5:4', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

### cURL


#### Request

```bash
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=16, ratio='5:4', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

## 延长视频

### Python


#### Request

```python
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=11, ratio='7:5', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

### Java


#### Request

```java
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=11, ratio='7:5', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

### Go


#### Request

```go
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=11, ratio='7:5', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

### cURL


#### Request

```bash
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

#### Response

```
----- create request -----
ContentGenerationTaskID(id='cgt-20260414114820-*****')
----- polling task status -----
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
Current status: running, Retrying after 10 seconds...
...
----- task succeeded -----
ContentGenerationTask(id='cgt-20260414114820-*****', model='doubao-seedance-2-5-260628', status='succeeded', error=None, content=Content(video_url='https://xxx', last_frame_url=None, file_url=None), usage=Usage(completion_tokens=411300, total_tokens=411300), frames=None, framespersecond=24, created_at=1776138520, updated_at=1776139219, seed=33608, service_tier='default', execution_expires_after=172800, generate_audio=True, duration=11, ratio='7:5', output_format='mov', resolution='720p', draft=False, draft_task_id=None)
```

## 有声视频-首帧

### cURL


#### Request

```bash
curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-5-260628",
    "content": [
        {
            "type": "text",
            "text": "女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/i2v_foxrgirl.png"
            }
        }
    ],
    "generate_audio": true,
    "ratio": "adaptive",
    "duration": 5,
    "watermark": true
}'
```

#### Response

```
{
  "id": "cgt-2025******-****"
}
```

### Python


#### Request

```python
import os
from arkruntime import Ark

# Get API Key：https://ark.volcengine.com/region:cn-beijing/apikey
client = Ark(base_url="https://ark.cn-beijing.volces.com/api/v3", api_key=os.environ.get("ARK_API_KEY"))

if __name__ == "__main__":
    print("----- create request -----")
    resp = client.content_generation.tasks.create(
        model="doubao-seedance-2-5-260628", # Replace with Model ID
        content=[
            {
                "text": (
                    "女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声"
                ),
                "type": "text"
            },
            {
                "image_url": {
                    "url": (
                        "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/i2v_foxrgirl.png"
                    )
                },
                "type": "image_url"
            }
        ],
        generate_audio=True,
        ratio="adaptive",
        duration=5,
        watermark=True,
    )

    print(resp)
```

#### Response

```
{
  "id": "cgt-2025******-****"
}
```

### Java


#### Request

```java
package com.ark.sample;

import com.volcengine.ark.runtime.models.content_generation.*;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
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
        String model = "doubao-seedance-2-5-260628"; // Replace with Model ID
        Boolean generateAudio = true;
        String ratio = "adaptive";
        Long duration = 5L;
        Boolean watermark = true;
        System.out.println("----- create request -----");
        List<ContentItem> contents = new ArrayList<>();

        // Combination of text prompt and parameters
        contents.add(ContentItem.builder()
                .type(ContentType.TEXT)
                .text("女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声")
                .build());
        // The URL of the first frame image
        contents.add(ContentItem.builder()
                .type(ContentType.IMAGE_URL)
                .imageUrl(ImageURL.builder()
                        .url("https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/i2v_foxrgirl.png")
                        .build())
                .build());

        // Create a video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .model(model)
                .content(contents)
                .generateAudio(generateAudio)
                .ratio(ratio)
                .duration(duration)
                .watermark(watermark)
                .build();

        CreateContentGenerationTaskResponse createResult = service.createContentGenerationTask(createRequest);
        System.out.println(createResult);

        service.shutdownExecutor();
    }
}
```

#### Response

```
{
  "id": "cgt-2025******-****"
}
```

### Go


#### Request

```go
package main

import (
    "context"
    "fmt"
    "os"

    "github.com/volcengine/ark-runtime-go/arkruntime"
    model "github.com/volcengine/ark-runtime-go/arkruntime/model/contentgeneration"
)

func main() {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    client := arkruntime.NewClientWithApiKey(
        // Get your API Key from the environment variable. This is the default mode and you can modify it as required
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()
    // Replace with Model ID
    modelEp := "doubao-seedance-2-5-260628"

    // Generate a task
    fmt.Println("----- create request -----")
    createReq := &model.CreateContentGenerationTaskRequest{
        Model: modelEp,
        GenerateAudio: model.NewOptBool(true),
        Ratio:         model.NewOptString("adaptive"),
        Duration:      model.NewOptInt64(5),
        Watermark:     model.NewOptBool(true),
        Content: []model.ContentItem{
            {
                // Combination of text prompt and parameters
                Type: model.ContentTypeText,
                Text: model.NewOptString("女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声"),
            },
            {
                // The URL of the first frame image
                Type: model.ContentTypeImageURL,
                ImageURL: model.NewOptImageURL(model.ImageURL{
                    URL: "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/i2v_foxrgirl.png",
                }),
            },
        },
    }
    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v", err)
        return
    }
    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s", taskID)
}
```

#### Response

```
{
  "id": "cgt-2025******-****"
}
```

## 有声视频-首尾帧

### cURL


#### Request

```bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-0-260128",
    "content": [
         {
            "type": "text",
            "text": "图中女孩对着镜头说“茄子”，360度环绕运镜"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seepro_first_frame.jpeg"
            },
            "role": "first_frame"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seepro_last_frame.jpeg"
            },
            "role": "last_frame"
        }
    ],
    "generate_audio":true,
    "ratio": "adaptive",
    "duration": 5,
    "watermark": true
}'
```

#### Response

```
{
  "id": "cgt-2025******-****"
}
```

### Python


#### Request

```python
import os
# Install SDK:  python -m pip install --upgrade arkruntime
from arkruntime import Ark

# Make sure that you have stored the API Key in the environment variable ARK_API_KEY
# Initialize the Ark client to read your API Key from an environment variable
client = Ark(
    # This is the default path. You can configure it based on the service location
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # Get API Key：https://ark.volcengine.com/region:cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)


if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID
        content=[
            {
                # Combination of text prompt and parameters
                "type": "text",
                "text": "图中女孩对着镜头说\"茄子\"，360度环绕运镜"
            },
            {
                # The URL of the first frame image
                "type": "image_url",
                "image_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seepro_first_frame.jpeg"
                },
                "role": "first_frame"
            },
            {
                # The URL of the last frame image
                "type": "image_url",
                "image_url": {
                    "url": "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seepro_last_frame.jpeg"
                },
                "role": "last_frame"
            }
        ],
        generate_audio=True,
        ratio="adaptive",
        duration=5,
        watermark=True,
    )
    print(create_result)
```

#### Response

```
{
  "id": "cgt-2025******-****"
}
```

### Java


#### Request

```java
package com.ark.sample;

import com.volcengine.ark.runtime.models.content_generation.*;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
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
        String model = "doubao-seedance-2-5-260628"; // Replace with Model ID
        Boolean generateAudio = true;
        String ratio = "adaptive";
        Long duration = 5L;
        Boolean watermark = true;
        System.out.println("----- create request -----");
        List<ContentItem> contents = new ArrayList<>();

        // Combination of text prompt and parameters
        contents.add(ContentItem.builder()
                .type(ContentType.TEXT)
                .text("图中女孩对着镜头说“茄子”，360度环绕运镜")
                .build());
         // The URL of the first frame image
        contents.add(ContentItem.builder()
                .type(ContentType.IMAGE_URL)
                .imageUrl(ImageURL.builder()
                        .url("https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seepro_first_frame.jpeg")
                        .build())
                .role("first_frame")
                .build());

        // The URL of the last frame image
        contents.add(ContentItem.builder()
                .type(ContentType.IMAGE_URL)
                .imageUrl(ImageURL.builder()
                        .url("https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seepro_last_frame.jpeg")
                        .build())
                .role("last_frame")
                .build());

        // Create a video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .model(model)
                .content(contents)
                .generateAudio(generateAudio)
                .ratio(ratio)
                .duration(duration)
                .watermark(watermark)
                .build();

        CreateContentGenerationTaskResponse createResult = service.createContentGenerationTask(createRequest);
        System.out.println(createResult);

        // Get the details of the task
        String taskId = createResult.getId();
        String getRequest = taskId;

        // Polling query section
        System.out.println("----- polling task status -----");
        while (true) {
            try {
                ContentGenerationTask getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus().toString();
                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    System.out.println("Error: " + getResponse.getStatus());
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                System.err.println("Polling interrupted");
                break;
            }
        }
    }
}
```

#### Response

```
{
  "id": "cgt-2025******-****"
}
```

### Go


#### Request

```go
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
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    client := arkruntime.NewClientWithApiKey(
        // Get your API Key from the environment variable. This is the default mode and you can modify it as required
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()
    // Replace with Model ID
    modelEp := "doubao-seedance-2-5-260628"

    // Generate a task
    fmt.Println("----- create request -----")
    createReq := &model.CreateContentGenerationTaskRequest{
        Model: modelEp,
        GenerateAudio: model.NewOptBool(true),
        Ratio:         model.NewOptString("adaptive"),
        Duration:      model.NewOptInt64(5),
        Watermark:     model.NewOptBool(true),
        Content: []model.ContentItem{
            {
                // Combination of text prompt and parameters
                Type: model.ContentTypeText,
                Text: model.NewOptString("图中女孩对着镜头说“茄子”，360度环绕运镜"),
            },
            {
                // The URL of the first frame image
                Type: model.ContentTypeImageURL,
                ImageURL: model.NewOptImageURL(model.ImageURL{
                    URL: "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seepro_first_frame.jpeg",
                }),
                Role: model.NewOptString("first_frame"),
            },
            {
                // The URL of the last frame image
                Type: model.ContentTypeImageURL,
                ImageURL: model.NewOptImageURL(model.ImageURL{
                    URL: "https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/seepro_last_frame.jpeg",
                }),
                Role: model.NewOptString("last_frame"),
            },
        },
    }
    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v", err)
        return
    }
    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s", taskID)

    // Polling query section
    fmt.Println("----- polling task status -----")
    for {
        getReq := taskID
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.Or(model.TaskContent{}).VideoURL.Or(""))
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.Or(model.TaskUsage{}).CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d", getResp.CreatedAt.Or(0), getResp.UpdatedAt.Or(0))
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error.IsSet() {
                fmt.Printf("Error Code: %s, Message: %s", getResp.Error.Value.Code, getResp.Error.Value.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
            time.Sleep(10 * time.Second)
        }
    }
}
```

#### Response

```
{
  "id": "cgt-2025******-****"
}
```

## 图生视频-base64编码

### cURL


#### Request

```bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-1-0-lite-i2v-250428",
    "content": [
        {
            "type": "text",
            "text": "女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,aHR0******cG5n"
            }
        }
    ],
    "ratio": "adaptive",
    "duration": 5,
    "watermark": true
}'
```

#### Response

```
{
  "id": "cgt-2025******-****"
}
```

## 文生视频

### cURL


#### Request

```bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-1-0-pro-250528",
    "content": [
        {
            "type": "text",
            "text": "写实风格，晴朗的蓝天之下，一大片白色的雏菊花田，镜头逐渐拉近，最终定格在一朵雏菊花的特写上，花瓣上有几颗晶莹的露珠"
        }
    ],
    "ratio": "16:9",
    "duration": 5,
    "watermark": true
}'
```

#### Response

```
{
  "id": "cgt-2026******-****"
}
```

### Python


#### Request

```python
import os
# Install SDK:  python -m pip install --upgrade arkruntime
from arkruntime import Ark

# Make sure that you have stored the API Key in the environment variable ARK_API_KEY
# Initialize the Ark client to read your API Key from an environment variable
client = Ark(
    # This is the default path. You can configure it based on the service location
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # Get API Key：https://ark.volcengine.com/region:cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-1-0-pro-250528", # Replace with Model ID
        content=[
            {
                # Combination of text prompt and parameters
                "type": "text",
                "text": "写实风格，晴朗的蓝天之下，一大片白色的雏菊花田，镜头逐渐拉近，最终定格在一朵雏菊花的特写上，花瓣上有几颗晶莹的露珠"
            }
        ],
        ratio="16:9",
        duration=5,
        watermark=True,
    )
    print(create_result)
```

#### Response

```
{
  "id": "cgt-2026******-****"
}
```

### Java


#### Request

```java
package com.ark.sample;

import com.volcengine.ark.runtime.models.content_generation.*;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3")
           // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();

    public static void main(String[] args) {
        String model = "doubao-seedance-1-0-pro-250528"; // Replace with Model ID
        String ratio = "16:9";
        Long duration = 5L;
        Boolean watermark = true;
        System.out.println("----- create request -----");
        List<ContentItem> contents = new ArrayList<>();

        // Combination of text prompt and parameters
        contents.add(ContentItem.builder()
                .type(ContentType.TEXT)
                .text("写实风格，晴朗的蓝天之下，一大片白色的雏菊花田，镜头逐渐拉近，最终定格在一朵雏菊花的特写上，花瓣上有几颗晶莹的露珠")
                .build());

        // Create a video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .model(model)
                .content(contents)
                .ratio(ratio)
                .duration(duration)
                .watermark(watermark)
                .build();

        CreateContentGenerationTaskResponse createResult = service.createContentGenerationTask(createRequest);
        System.out.println(createResult);


        // shutdown service after all requests is finished
        service.shutdownExecutor();
    }
}
```

#### Response

```
{
  "id": "cgt-2026******-****"
}
```

### Go


#### Request

```go
package main

import (
    "context"
    "fmt"
    "os"

    "github.com/volcengine/ark-runtime-go/arkruntime"
    model "github.com/volcengine/ark-runtime-go/arkruntime/model/contentgeneration"
)

func main() {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    client := arkruntime.NewClientWithApiKey(
        // Get your API Key from the environment variable. This is the default mode and you can modify it as required
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()
    // Replace with Model ID
    modelEp := "doubao-seedance-1-0-pro-250528"

    // Generate a task
    fmt.Println("----- create request -----")
    createReq := &model.CreateContentGenerationTaskRequest{
        Model: modelEp,
        Ratio:         model.NewOptString("16:9"),
        Duration:      model.NewOptInt64(5),
        Watermark:     model.NewOptBool(true),
        Content: []model.ContentItem{
            {
                // Combination of text prompt and parameters
                Type: model.ContentTypeText,
                Text: model.NewOptString("写实风格，晴朗的蓝天之下，一大片白色的雏菊花田，镜头逐渐拉近，最终定格在一朵雏菊花的特写上，花瓣上有几颗晶莹的露珠"),
            },
        },
    }
    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v", err)
        return
    }
    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s", taskID)
}
```

#### Response

```
{
  "id": "cgt-2026******-****"
}
```
