> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 视频生成

> 本文档介绍 MiniMax 视频生成服务（MiniMax H3、MiniMax H3 Max）的使用方法，助力高效创作视频内容。

MiniMax 视频生成目前提供 **MiniMax H3** 与 **MiniMax H3 Max** 两款模型：

* **MiniMax H3**：开放通用的多模态视频模型，可以统一理解文本、图片、视频和音频输入，完成视频生成、参考创作与视频编辑。
* **MiniMax H3 Max**：MiniMax 与 [fal.ai](https://fal.ai/) 联合出品，基于 MiniMax H3 后训练的视频生成模型，专为高速视频生成而优化。输出 480P、768P 主流分辨率，生成速度比 MiniMax H3 更快。支持 T2V（文生视频）、I2V（图生视频）与全能参考生成。

提示：若需要使用 MiniMax H3 或 MiniMax H3 Max，请点击 [按量购买 API](https://platform.minimax.cn/docs/pricing/overview#models/video)。

## 支持的生成方式

### MiniMax H3

| 生成方式 | 输入内容 | 适用场景 |
| - | - | - |
| 文生视频 | Prompt | 根据文字描述从零生成视频 |
| 图生视频 | Prompt + 首帧图片和/或尾帧图片 | 控制视频的开始或结束画面，让指定画面自然动起来 |
| 全能参考生成 | Prompt + 参考图片、视频或音频 | 参考角色、动作、镜头、风格、声音或剪辑节奏 |

### MiniMax H3 Max

| 生成方式 | 输入内容 | 适用场景 |
| - | - | - |
| 文生视频（T2V） | Prompt | 根据文字描述从零生成视频 |
| 图生视频（I2V） | Prompt + 首帧图片和/或尾帧图片 | 控制视频的开始或结束画面，让指定画面自然动起来 |
| 全能参考生成 | Prompt + 参考图片、视频或音频 | 参考角色、动作、镜头、风格、声音或剪辑节奏 |

## 模型规格与输入条件

### 输出规格

| 项目 | MiniMax H3 | MiniMax H3 Max |
| - | - | - |
| 模型名称 | `MiniMax-H3` | `MiniMax-H3-Max` |
| 输出分辨率 | 768P / 2K | 480P / 768P |
| 输出时长 | 4～15 秒，仅支持整数值 | 5～15 秒，仅支持整数值 |
| 宽高比 | 支持多种常见比例或自适应，[详见 API 文档](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create.md) | 支持多种常见比例或自适应，[详见 API 文档](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create.md) |

### 输入条件

| 项目 | 要求 |
| - | - |
| **首/尾帧入口** | 图片：0、1、2 张；宽高范围 \[256, 5760]；宽高比 5:2～2:5 范围内 |
| | 无图片输入时为文生视频模式 |
| **全能参考入口** | 图片：≤ 9 张；宽高范围 \[256, 5760]；宽高比 5:2～2:5 范围内 |
| | 视频：≤ 3 段；单段时长 \[2, 15] 秒；总时长 ≤ 15 秒；宽高范围 \[256, 5760]；宽高比 5:2～2:5 范围内 |
| | 音频：≤ 3 段；单段时长 \[2, 15] 秒；总时长 ≤ 15 秒 |
| | 混合输入的总上限是 12 个文件 |
| | 无图片、视频、音频输入时为文生视频模式 |
| **输入格式支持** | 视频：H.264/AVC、H.265/HEVC；视频内音频：AAC、MP3 |
| | 图片：JPG、JPEG、PNG、WEBP、HEIC、HEIF |
| | 音频：WAV、MP3 |
| **传入大小限制** | 视频单个 50 MB；图片单个 30 MB；音频单个 15 MB（加起来的不限制，限制都在单个素材上） |
| | API 请求体 64 MB（推荐使用 URL 传入素材） |
| **提示词字数上限** | 不超过 7000 字符 |

## 工作流程

视频生成是一个异步过程，包含以下三个步骤：

1. 创建生成任务：提交一个视频生成请求，获得任务 ID (`task_id`)
2. 查询任务状态：使用 `task_id` 轮询任务状态。任务成功后，直接返回成片下载地址 (`content.url`)
3. 获取视频文件：下载 `content.url` 指向的视频并保存到本地

## 功能与代码示例

为了简化代码，我们将轮询和下载的逻辑封装为公共函数，并举例了四种模式下如何创建任务。

```python theme={null}
import os
import time
import requests

api_key = os.environ["MINIMAX_API_KEY"]
headers = {"Authorization": f"Bearer {api_key}"}
BASE_URL = "https://api.minimax.cn"
MODEL = "MiniMax-H3"


# --- 步骤 1: 发起视频生成任务 ---
# MiniMax-H3 使用多模态 content[] 结构：每个元素通过 type（text / image_url / video_url / audio_url）区分，
# 并可用 role 标注用途。以下四个函数分别对应文生视频、图生视频、首尾帧、多模态参考四种模式，
# 都会发起一个异步任务并返回唯一的 task_id。

def invoke_text_to_video() -> str:
    """（模式一）纯文本生成视频（t2va）。t2va 场景 ratio 必填且不能为 adaptive。"""
    url = f"{BASE_URL}/v2/video_generation"
    payload = {
        "model": MODEL,
        "content": [
            # type=text 为必填项，用于描述视频的动态内容。
            {"type": "text", "text": "镜头拍摄一个女性坐在咖啡馆里，女人抬头看着窗外，镜头缓缓移动拍摄到窗外的街道，画面呈现暖色调，色彩浓郁，氛围轻松惬意。"},
        ],
        "duration": 5,
        "resolution": "2K",
        "ratio": "16:9",
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()["task_id"]


def invoke_image_to_video() -> str:
    """（模式二）首帧图 + 文本生成视频（i2va）。"""
    url = f"{BASE_URL}/v2/video_generation"
    payload = {
        "model": MODEL,
        "content": [
            {"type": "text", "text": "Contemporary dance, the people in the picture are performing contemporary dance."},
            # role=first_frame 指定视频起始帧；图生视频场景下宽高比由输入图片决定，ratio 恒为 adaptive。
            {"type": "image_url", "image_url": {"url": "https://filecdn.minimax.chat/public/85c96368-6ead-4eae-af9c-116be878eac3.png"}, "role": "first_frame"},
        ],
        "duration": 5,
        "resolution": "2K",
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()["task_id"]


def invoke_start_end_to_video() -> str:
    """（模式三）首帧图 + 尾帧图 + 文本生成视频。"""
    url = f"{BASE_URL}/v2/video_generation"
    payload = {
        "model": MODEL,
        "content": [
            {"type": "text", "text": "A little girl grows up."},
            # role=first_frame 指定起始画面
            {"type": "image_url", "image_url": {"url": "https://filecdn.minimax.chat/public/fe9d04da-f60e-444d-a2e0-18ae743add33.jpeg"}, "role": "first_frame"},
            # role=last_frame 指定结束画面
            {"type": "image_url", "image_url": {"url": "https://filecdn.minimax.chat/public/97b7cd08-764e-4b8b-a7bf-87a0bd898575.jpeg"}, "role": "last_frame"},
        ],
        "duration": 5,
        "resolution": "2K",
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()["task_id"]


def invoke_reference_to_video() -> str:
    """（模式四）多模态参考生视频（r2va）：可组合参考图 / 参考视频 / 参考音频。"""
    url = f"{BASE_URL}/v2/video_generation"
    payload = {
        "model": MODEL,
        "content": [
            {"type": "text", "text": "人物参考视频1的动作，表演街舞，人物参考图1 图2"},
            {"type": "image_url", "image_url": {"url": "https://cdn.hailuoai.com/prod/hailuo_demo/testsets/h3_promo_eval_ref2va/gallery/sr_v2p26_trio_seed42_20260724/inputs/9d5c7a33fa6e_01_%E5%9B%BE1_MHGgbVga3o_gpt4o-image-1780651118146.png"}, "role": "reference_image"},
            {"type": "image_url", "image_url": {"url": "https://cdn.hailuoai.com/prod/hailuo_demo/testsets/h3_promo_eval_ref2va/gallery/sr_v2p26_trio_seed42_20260724/inputs/7af326902315_00_%E5%9B%BE2_YqtKbY1jpo_u4391985813_Young_male_wearing_cream_hoodie_and_dark_brown_sh_45d56ed0-d626-4c37-9a5b-77f51f374982_1.png"}, "role": "reference_image"},
            {"type": "video_url", "video_url": {"url": "https://cdn.hailuoai.com/prod/hailuo_demo/testsets/h3_promo_eval_ref2va/gallery/sr_v2p26_trio_seed42_20260724/inputs/d9060f5cb9ab_02_%E8%A7%86%E9%A2%911_HDvmbpQrEo_%E8%A1%97%E8%88%9E3.mp4"}, "role": "reference_video"},
        ],
        "duration": 5,
        "resolution": "2K",
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()["task_id"]


# --- 步骤 2: 轮询查询任务状态 ---
# 视频生成是一个耗时过程，因此 API 设计为异步模式。
# 提交任务后，需使用 task_id 通过此函数进行轮询。任务成功后直接返回成片下载地址（content.url），无需再换 file_id。
def query_task_status(task_id: str) -> str:
    """根据 task_id 轮询任务状态，成功后返回成片下载地址。"""
    url = f"{BASE_URL}/v2/query/video_generation/{task_id}"
    while True:
        # 推荐的轮询间隔为 10 秒，以避免对服务器造成不必要的压力。
        time.sleep(10)
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        task = response.json()["task"]
        status = task["status"]
        print(f"当前任务状态: {status}")
        # 成功时 task.content.url 即为成片下载地址。
        if status == "succeeded":
            return task["content"]["url"]
        # 终态失败：failed / cancelled。
        if status in ("failed", "cancelled"):
            raise Exception(f"视频生成未成功: status={status}, error={task.get('error')}")


# --- 步骤 3: 下载并保存视频文件 ---
# 任务成功后直接得到成片下载地址，下载内容并保存到本地即可。
def fetch_video(download_url: str):
    """下载成片并保存到本地。"""
    with open("output.mp4", "wb") as f:
        video_response = requests.get(download_url)
        video_response.raise_for_status()
        f.write(video_response.content)
    print("视频已成功保存至 output.mp4")


# --- 主流程: 完整调用示例 ---
# 该部分演示了从发起任务到最终保存视频的完整调用链路。
if __name__ == "__main__":
    # 选择一种方式创建任务
    task_id = invoke_text_to_video()  # 方式一：文生视频
    # task_id = invoke_image_to_video() # 方式二：图生视频
    # task_id = invoke_start_end_to_video() # 方式三: 根据首尾帧生成视频
    # task_id = invoke_reference_to_video() # 方式四: 多模态参考生视频

    print(f"视频生成任务已提交，任务 ID: {task_id}")
    download_url = query_task_status(task_id)
    print(f"任务处理成功，成片地址: {download_url}")
    fetch_video(download_url)
```

## 生成视频结果

### 文生视频

只提供一段文字描述，模型即可根据描述生成视频。为了对视频内容进行更精细的控制，可在关键描述后添加 `[运镜]` 指令，来引导镜头调度。

示例生成结果

<video controls src="https://filecdn.minimax.chat/docs/video-generation-v2/text-to-video.mp4" />

### 首帧/尾帧生成视频

提供首帧图片、尾帧图片，或同时提供两张，再结合文字描述生成视频。视频的起始或结束画面完全可控，适合让静态图片"动起来"或补完自然的过渡画面。

示例生成结果

<video controls src="https://filecdn.minimax.chat/docs/video-generation-v2/first-last-frame.mp4" />

### 全能参考生成

提供参考图片、参考视频或参考音频（可组合使用），并结合文字描述生成视频，在生成过程中保持参考主体或素材的特征一致性。

示例生成结果

<video controls src="https://filecdn.minimax.chat/docs/video-generation-v2/reference.mp4" />

## 创建 H3-Context-IR 任务

如需在生成视频前获得更完整的提示词，可以[创建 H3-Context-IR 任务](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-h3-context-ir.md)。H3-Context-IR 会深度理解文本、图像、音频和视频等多模态上下文及其相互关系，通过复杂逻辑推理生成结构化表达，并在尽量保持用户原始意图的前提下丰富语义细节。本接口只返回增强提示词，不创建视频。

H3-Context-IR 采用异步任务形式。创建成功后，使用[查询任务](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-query.md)或[查询任务列表](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-list.md)获取结果；任务成功后从 `content.prompt` 获取增强提示词，并可通过 `task_type=h3_context_ir` 识别该任务。

## 视频再生成

如果已有符合 MiniMax-H3 768P 输出规格的成片，可以调用[创建视频再生成任务](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-regeneration.md)接口输出 2K 视频。请求时需原样提交生成 768P 视频时使用的全部 `content`，并额外加入且仅加入一个 `type=video_url`、`role=base_video` 的源视频项。

再生成任务与其他 H3 任务共用[查询任务](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-query.md)、[查询任务列表](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-list.md)以及[取消或删除任务](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-delete.md)接口；可通过 `task_type=regeneration` 识别。

## 推荐阅读

> **[创建视频生成任务](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create.md)**
>
> 使用本接口通过多模态 content 输入，创建 MiniMax-H3 视频生成任务。

> **[创建 H3-Context-IR 任务](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-h3-context-ir.md)**
>
> 深度理解视频生成的多模态上下文，并生成结构化增强提示词。

> **[创建视频再生成任务](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-regeneration.md)**
>
> 对符合 MiniMax-H3 768P 输出规格的源视频进行再生成，输出 2K 视频。

> **[查询任务](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-query.md)**
>
> 使用本接口按 task\_id 查询任务状态并获取成片下载地址。

> **[查询任务列表](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-list.md)**
>
> 分页查询最近 7 天内的任务，并按 task\_type 区分任务类型。

> **[取消或删除任务](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-delete.md)**
>
> 取消排队中的任务，或删除成功和失败的任务记录。

> **[产品定价](https://platform.minimaxi.com/docs/pricing/overview.md#models/video)**
>
> 各模型的定价说明、计费方式及使用限制。
