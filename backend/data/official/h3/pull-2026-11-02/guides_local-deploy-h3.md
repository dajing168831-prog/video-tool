> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 本地运行与自托管部署 MiniMax H3

> 使用 ComfyUI 本地运行 MiniMax H3，或通过 SGLang 部署可复现的 H3-Base 服务。

> [!WARNING]
>
> MiniMax H3 受 [MiniMax H3 Community License Agreement](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) 约束。截至 2026 年 8 月 26 日审阅的 License 版本，美国、欧盟、英国和韩国属于 Excluded Territories，需要另行获得许可。下载、部署或提供托管服务前，请阅读最新协议。

MiniMax H3-Base 联合生成 768p 视频与同步立体声音频。本页提供两条不同路径：使用 ComfyUI 的本地可视化工作流，以及在 NVIDIA 数据中心 GPU 上使用 SGLang 部署自托管 API 服务。

## 状态与范围

| 项目 | 固定基线 |
| :- | :- |
| SGLang 部署状态 | **Preview** — H3 支持已随 SGLang v0.5.17 及以后版本在 PyPI 发布；本页为可复现性固定源码 commit，上游 diffusion 安装的依赖仍使用 `--prerelease=allow` |
| vLLM-Omni 支持 | 社区维护的 recipe，基于 vLLM 0.26.0；见[使用 vLLM-Omni 自托管](#使用-vllm-omni-自托管) |
| ComfyUI 支持 | ComfyUI `0.30.0` 及以上版本原生提供 T2V、I2V 和 R2V 模板；使用 Comfy-Org 转换权重 |
| 最后审阅 | 2026 年 8 月 26 日 |
| 模型 | [`MiniMaxAI/MiniMax-H3`](https://huggingface.co/MiniMaxAI/MiniMax-H3)，revision `42ed227ee7df40d41602854ae760620d6eb651fe` |
| 推理框架 | SGLang 源码 commit `2511743bd784e69e5a81ca3d926a000711dae4ab` |
| SGLang Quickstart checkpoint | FL2VA，官方混合 BF16/FP32 权重 |
| SGLang Quickstart 硬件 | 单节点 8 × NVIDIA B200、Ulysses degree 8、组件常驻 |
| 上游配方验证的 API | 异步 `/v1/videos` 接口、短边 768 像素的 5 秒 T2VA |

固定 commit 可以提高命令的可复现性，但 H3 diffusion 服务尚不是稳定的 SGLang 发布契约。修改任一 revision 前应重新验证本页。

> [!NOTE]
>
> 开放发布包含 H3-Base FL2VA 与 Ref2VA，不包含 H3-Context-IR 和 H3-Regenerate-2K。因此，自托管 H3-Base 不能复现 MiniMax 平台完整的 Context-IR 与 2K 工作流。

## 选择部署路径

| 路径 | 适用场景 | 接口 | 权重 | 验证边界 |
| :- | :- | :- | :- | :- |
| **ComfyUI 本地工作流** | 交互创作、提示词迭代、关键帧和参考素材 | 可视化节点图与模板库 | Comfy-Org 发布的裁剪和量化转换权重 | ComfyUI 原生模板；数值基线不同于官方混合 BF16/FP32 checkpoint |
| **SGLang 自托管 API** | 可复现的服务器部署与应用集成 | 异步 `/v1/videos` API | 官方 `MiniMaxAI/MiniMax-H3` checkpoint | 本文固定的 8 × B200 FL2VA 参考配置 |
| **vLLM-Omni 自托管 API** | FL2VA + Ref2VA 合并服务、同步 MP4 响应、AMD ROCm 主机 | 同步与异步 `/v1/videos` API | 官方 `MiniMaxAI/MiniMax-H3` checkpoint | 社区维护的上游 recipe；见[使用 vLLM-Omni 自托管](#使用-vllm-omni-自托管) |

需要在本地工作站通过可视化方式创建和调整工作流时，选择 ComfyUI；需要 HTTP 服务、可复现服务器配置或应用集成时，选择 SGLang。

## 使用 ComfyUI 本地运行 H3

ComfyUI 原生提供 MiniMax H3 节点和示例模板，无需先搭建推理 API，适合快速体验 T2V、I2V 和参考素材驱动工作流。

> [!WARNING]
>
> ComfyUI 模板使用 [`Comfy-Org/MiniMax-H3`](https://huggingface.co/Comfy-Org/MiniMax-H3) 发布的裁剪和量化文件，其中包含 INT8/NVFP4 组件。这些文件不同于 SGLang 基线使用的官方混合 BF16/FP32 H3 checkpoint，输出质量、显存占用和可复现性可能不同；不要混用两条路径的性能结论。

### ComfyUI 基线

| 项目 | 基线 |
| :- | :- |
| ComfyUI | `0.30.0` 或更高版本 |
| 内置工作流 | MiniMax H3 T2V、I2V 和 R2V |
| 本文核验的工作流模板 revision | [`3c1df78`](https://github.com/Comfy-Org/workflow_templates/tree/3c1df78dedcc66c94ec27e0ed8a809ed7742f863) |
| 本文核验的 Comfy-Org 模型 revision | [`4cc1d817`](https://huggingface.co/Comfy-Org/MiniMax-H3/tree/4cc1d817b6184899b41293954329f576cb5ae86b) |
| 已公布最低显存与性能 | ComfyUI H3 指南未公布；请在实际硬件上验证所选工作流 |

以上版本和 revision 记录 2026 年 8 月 26 日核验的文档基线。此后 Template Library 可能继续更新。

### 通过 Template Library 快速开始

1. 将 ComfyUI 更新到 `0.30.0` 或更高版本，并正常启动。
2. 打开 **Template Library** > **Video**。
3. 选择 **MiniMax H3 T2V**、**MiniMax H3 I2V** 或 **MiniMax H3 R2V**。
4. 按模型扫描弹窗下载所需文件。如果模型列表没有刷新，请重启 ComfyUI。
5. 设置提示词，以及需要的输入图片、视频或音频参考素材。
6. 在 **Resolution Selector** 中使用 `0.98` Megapixels 和 `32` 的倍数，或者为 16:9 原生画布直接设置 `1344 × 768`。不要选择 `1.0` Megapixels：它会得到 `1376 × 768`，超过 H3-Base 的 768 × 1344 像素面积上限。
7. 将工作流加入队列。正确结果应为包含 24 FPS 视频流和同步立体声音频的 MP4。

### 选择工作流

| 工作流 | 输入与控制 | checkpoint 系列 | 原生节点 | 固定模板 |
| :- | :- | :- | :- | :- |
| T2V | 描述镜头、运镜、对白、音效和音乐的文本提示词 | FL2VA | 不连接关键帧的 `MiniMaxH3ImageToVideo` | [T2V JSON](https://github.com/Comfy-Org/workflow_templates/blob/3c1df78dedcc66c94ec27e0ed8a809ed7742f863/templates/video_minimax_h3_t2v.json) |
| I2V | 输入图片；可选首帧和尾帧 | FL2VA | `MiniMaxH3ImageToVideo` | [I2V JSON](https://github.com/Comfy-Org/workflow_templates/blob/3c1df78dedcc66c94ec27e0ed8a809ed7742f863/templates/video_minimax_h3_i2v.json) |
| R2V | 支持的图片、视频和音频参考素材组合 | Ref2VA | `MiniMaxH3ReferenceToVideo` | [R2V JSON](https://github.com/Comfy-Org/workflow_templates/blob/3c1df78dedcc66c94ec27e0ed8a809ed7742f863/templates/video_minimax_h3_r2v.json) |

T2V 和 I2V 使用 FL2VA diffusion model；R2V 需要独立的 Ref2VA diffusion model，两者不能互换。在 R2V 提示词中，按连接顺序使用 `<Picture 1>`、`<Video 1>`、`<Audio 1>` 等标签引用输入，并说明每个参考素材负责身份、风格、动作、运镜还是声音。

### 手动放置模型文件

推荐使用 Template Library 的自动下载流程。离线部署或手动管理模型时，请从 [Comfy-Org 模型仓库](https://huggingface.co/Comfy-Org/MiniMax-H3) 下载所选模板列出的文件，并按下表放置：

| 组件 | 文件 | ComfyUI 目录 |
| :- | :- | :- |
| T2V/I2V 使用的 FL2VA diffusion model | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `ComfyUI/models/diffusion_models/` |
| R2V 使用的 Ref2VA diffusion model | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `ComfyUI/models/diffusion_models/` |
| Text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `ComfyUI/models/text_encoders/` |
| Video VAE | `minimax_h3_video_vae_fp16.safetensors` | `ComfyUI/models/vae/` |
| Audio VAE | `minimax_h3_audio_vae_fp32.safetensors` | `ComfyUI/models/vae/` |
| 可选工作流 LoRA | 所选模板要求的 FL2V 8-step 或 Ref2V 4-step LoRA | `ComfyUI/models/loras/` |

团队需要可复现工作流时，请导出 Workflow JSON，并记录 ComfyUI 版本和每个模型文件的 revision。不要在未记录的情况下将 FL2VA 替换为 Ref2VA，或启用会改变质量的 Turbo LoRA。

### 分辨率、时长与 Turbo 模式

* H3-Base 使用 768 像素短边，宽高需要对齐到 `32` 的倍数；`1344 × 768` 是原生 16:9 画布。
* 时长会按模型的 `17k + 5` 帧网格和 24 FPS 对齐，因此请求时长可能被调整到有效帧数。
* FL2VA 示例工作流默认使用 20 steps；可选 8-step Turbo LoRA 更快，但可能降低动作和音频质量。
* R2V 使用独立的可选 4-step Turbo LoRA。比较结果时，应记录 LoRA 名称、强度、steps、seed 和全部参考素材。

ComfyUI 还提供 `MiniMaxH3AddGuide` 任意帧锚点、提示词 embedding，以及使用 latent noise mask 进行局部重绘或扩展等高级工作流。这些能力和可选的 Sage Attention 加速会随 ComfyUI 更新；将其用于固定生产流程前，请查看 [MiniMax H3 ComfyUI 官方指南](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)。

## SGLang 硬件与环境

下方 8 × B200 拓扑是参考配置，不代表最低硬件要求。当前 MiniMax 模型卡提供了四 GPU 的 SGLang 命令，但未注明 GPU 型号，也未公布该命令的峰值显存、主机内存、磁盘、互联、驱动、CUDA 或延迟数据。

| 要求 | 参考值 | 信息来源状态 |
| :- | :- | :- |
| GPU | 单节点 8 × NVIDIA B200 | 本页采用的 SGLang 已验证拓扑 |
| 精度与放置 | 官方混合 BF16/FP32 权重；组件常驻 | SGLang 上游参考路径 |
| 主机内存 | 此 B200 配方未公布 | 部署前确认容量 |
| 本地磁盘 | 精确要求未公布；上游 Cookbook 报告模型权重约为 108 GB | 还需为下载元数据和输出预留空间 |
| 互联 | 最低要求未公布 | 建议采用高带宽单节点 GPU 拓扑 |
| OS 与 Python | Linux、Python 3.12 | 本页源码安装环境 |
| CUDA 与 NVIDIA 驱动 | 未公布 H3 专用最低版本 | 使用与 B200、PyTorch 和固定 SGLang commit 兼容的版本 |

继续前请安装 `git`、`curl`、`jq`、`ffmpeg`、兼容的 NVIDIA 驱动与 CUDA runtime。信息未公布不代表没有要求。

## SGLang Quickstart

以下流程仅下载 FL2VA 分区，启动只监听本机的服务，等待就绪，提交并轮询任务，下载 MP4，然后检查媒体流。

### 1. 安装固定的 SGLang 源码

```bash theme={null}
export MINIMAX_H3_WORKDIR="$PWD/minimax-h3-deploy"
mkdir -p "$MINIMAX_H3_WORKDIR"

git clone https://github.com/sgl-project/sglang.git "$MINIMAX_H3_WORKDIR/sglang"
cd "$MINIMAX_H3_WORKDIR/sglang"
git checkout 2511743bd784e69e5a81ca3d926a000711dae4ab

python3 -m pip install --upgrade uv
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e "python[diffusion]" --prerelease=allow
uv pip install "huggingface_hub==1.28.0"
sglang --version
```

固定 commit 避免使用 H3 早期支持阶段常见的可变 `main`、`dev` 或无版本预发布安装。

### 2. 下载固定的 FL2VA checkpoint

```bash theme={null}
export HF_HOME="$MINIMAX_H3_WORKDIR/hf-cache"
export MINIMAX_H3_MODEL_DIR="$MINIMAX_H3_WORKDIR/model"

hf download MiniMaxAI/MiniMax-H3 \
  --revision 42ed227ee7df40d41602854ae760620d6eb651fe \
  --include "model_index.json" "FL2VA/*" \
  --local-dir "$MINIMAX_H3_MODEL_DIR"
```

`--model-path` 应指向仓库根目录，不要指向 `FL2VA/` 子目录。SGLang 通过 `--model-variant fl2va` 选择分区。

### 3. 启动 FL2VA 服务

在 SGLang 仓库目录中激活虚拟环境后运行：

```bash theme={null}
HF_HUB_OFFLINE=1 sglang serve \
  --model-path "$MINIMAX_H3_MODEL_DIR" \
  --model-variant fl2va \
  --num-gpus 8 \
  --tp-size 1 \
  --ulysses-degree 8 \
  --encoder-parallel auto \
  --performance-mode speed \
  --host 127.0.0.1 \
  --port 30010
```

保持进程运行。首次启动需要加载模型并 warmup，可能需要数分钟才会就绪。

### 4. 检查就绪状态

在第二个终端运行：

```bash theme={null}
curl --fail --retry 60 --retry-delay 10 --retry-all-errors \
  http://127.0.0.1:30010/health
```

服务就绪后返回：

```json theme={null}
{"status":"ok"}
```

`/liveness` 只表示 HTTP 进程能接收请求。应使用 `/health`；模型 warmup 完成前该接口返回 HTTP 503。

### 5. 生成、轮询并下载 MP4

```bash theme={null}
video_id=$(
  curl -fsS -X POST http://127.0.0.1:30010/v1/videos \
    -H "Content-Type: application/json" \
    -d '{
      "model": "MiniMaxAI/MiniMax-H3",
      "prompt": "At night, three cats perform with tiny brass instruments in a warm living room, with movement synchronized to the music.",
      "seconds": 5,
      "task": "t2va",
      "conditions": [],
      "target": {
        "short_edge": 768,
        "aspect_ratio": "16:9",
        "duration_seconds": 5.0
      },
      "num_outputs_per_prompt": 1,
      "num_inference_steps": 50,
      "flow_shift": 12.0,
      "audio_flow_shift": 3.0,
      "seed": 1101
    }' | jq -r '.id'
)

test -n "$video_id" && test "$video_id" != "null"

while true; do
  job=$(curl -fsS "http://127.0.0.1:30010/v1/videos/${video_id}")
  status=$(printf '%s' "$job" | jq -r '.status')

  case "$status" in
    completed) break ;;
    failed)
      printf '%s\n' "$job" | jq . >&2
      exit 1
      ;;
    *) sleep 5 ;;
  esac
done

curl -fsS -L \
  "http://127.0.0.1:30010/v1/videos/${video_id}/content" \
  -o minimax-h3-t2va.mp4

ffprobe -v error \
  -show_entries stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels \
  -of json minimax-h3-t2va.mp4
```

预期结果是一个非空 MP4，其中包含一条 24 FPS 的 H.264 视频流，以及一条 32 kHz 的 AAC 立体声音频流。16:9、短边 768 像素配置对应 1344 × 768，时长约 5 秒。

## 能力与 checkpoint 矩阵

| 模型能力 | checkpoint 与 task | 本页状态 |
| :- | :- | :- |
| 文本生成音视频 | FL2VA，`task: "t2va"` | 固定 Quickstart 已覆盖 |
| 首帧、尾帧或首尾帧 | FL2VA，`task: "fl2va"` | 模型与 SGLang 上游支持；使用一或两个 `role: "keyframe"` 的图片条件 |
| 图片、视频或音频参考 | Ref2VA，`task: "ref2va"` | 模型与 SGLang 上游支持；需要独立 Ref2VA 服务 |
| 视频到视频 | Ref2VA，`task: "ref2va"` | 属于参考输入形式，不使用单独的 task 值 |
| Context-IR 与 2K 再生成 | H3-Base 不包含 | 需要 MiniMax 平台组件，不属于本自托管流程 |

H3-Base 输出时长为 4–15 秒，短边 768 像素，视频 24 FPS，音频为 32 kHz 立体声。Ref2VA 最多接受 9 张图片、3 个视频片段和 3 个音频片段；单文件及组合限制请查看模型卡。

如需提供 Ref2VA，请在同一模型 revision 下载 `"Ref2VA/*"`，并用 `--model-variant ref2va` 在另一个端口启动第二个服务。不要向 FL2VA 服务发送 `ref2va` 请求。

## SGLang 硬件与性能数据

只有 checkpoint、请求形状、推理步数、flow shift 和 quality level 相同时，性能数据才可以直接比较。

| 配置 | 负载 | 已公布结果 | 验证方 |
| :- | :- | :- | :- |
| 8 × B200、Ulysses 8、常驻、lossless | 本页 Quickstart 配置 | 未公布该精确配方的峰值显存与延迟 | SGLang 已验证拓扑；MiniMax 未公布 benchmark |
| 4 × H200、Ulysses 4、常驻、lossless | 1344 × 768、124 帧、24 FPS、50 步、5 秒 T2VA | 三组 prompt/seed 的平均推理延迟为 75.10 秒 | SGLang 上游 benchmark |
| 4 × H200、相同负载、`quality: "high"` | 审计过的 Cache-DiT 路径 | 平均推理延迟 53.70 秒；相对 lossless 视频的 SSIM 为 0.931、PSNR 为 28.16 dB | SGLang 上游 benchmark；仅适用于该精确负载 |

以下表格转录 SGLang 上游 benchmark。这些数据在上游构建上测得，而非本页固定的 commit，应作为拓扑和容量参考，不构成对固定基线的保证。除特别说明外，负载均为 Quickstart 配置：1344 × 768、124 帧、24 FPS、50 推理步、5 秒 T2VA、单请求。

### 8 × B300 精度与 encoder 放置 sweep

单节点 8 × B300、Ulysses degree 8、组件常驻的 12 配置 sweep，每格在 1 次 warmup 请求后实测 1 次请求。FP8 为在线量化的近似路径；只有 BF16 行属于 lossless 参考路径。

| Checkpoint | 精度 | Encoder 放置 | 推理延迟 | 单卡峰值显存 |
| :- | :- | :- | -: | -: |
| FL2VA | BF16 | `auto` | 19.04 s | 83,578 MB |
| FL2VA | BF16 | `fold` | 19.04 s | 83,578 MB |
| FL2VA | BF16 | `replicate` | 19.04 s | 124,158 MB |
| FL2VA | FP8 | `auto` | 18.03 s | 51,926 MB |
| FL2VA | FP8 | `fold` | 18.04 s | 51,926 MB |
| FL2VA | FP8 | `replicate` | 18.04 s | 92,506 MB |
| Ref2VA | BF16 | `auto` | 29.12 s | 83,968 MB |
| Ref2VA | BF16 | `fold` | 29.13 s | 83,968 MB |
| Ref2VA | BF16 | `replicate` | 29.13 s | 124,490 MB |
| Ref2VA | FP8 | `auto` | 27.12 s | 52,816 MB |
| Ref2VA | FP8 | `fold` | 27.12 s | 52,816 MB |
| Ref2VA | FP8 | `replicate` | 27.12 s | 93,396 MB |

batch size 为 1 时，`auto` 解析为相同的 fold 放置；`replicate` 多占用约 40 GB 峰值显存且没有延迟收益。在该拓扑上，FP8 主要换取显存余量，而非速度。

### 4 × H200 拓扑对比

同一台四卡 H200 主机上两种 lossless 常驻放置的连续对比，固定 prompt 和 seed。第二组增加 `--warmup-resolutions 1344x768`，使 warmup 覆盖实际服务分辨率。

| 拓扑 | Warmup | 端到端延迟 | 单卡峰值显存 |
| :- | :- | -: | -: |
| Ulysses 4 | 默认 | 84.14 s | 94,288 MB |
| TP 2 + Ulysses 2 | 默认 | 85.51 s | 63,490 MB |
| Ulysses 4 | `--warmup-resolutions 1344x768` | 74.38 s | 94,290 MB |
| TP 2 + Ulysses 2 | `--warmup-resolutions 1344x768` | 78.33 s | 63,490 MB |

Ulysses 4 是 H200 的延迟默认拓扑；TP 2 + Ulysses 2 的单卡峰值显存低约 30 GB，这也是它作为 80 GB H100 配方的原因。

### 4 × H100 拓扑对比

同一台四卡 H100 主机上的三种 lossless 放置。上游表格未公布这些行的请求形状，因此只应在表内互相比较。

| 拓扑 | Pipeline 延迟 | 单卡峰值显存 |
| :- | -: | -: |
| TP 2 + Ulysses 2 | 13.25 s | 66.04 GB |
| FSDP + Ulysses 4 | 13.36 s | 57.01 GB |
| TP 4 + Ulysses 1 | 13.86 s | 49.80 GB |

> [!WARNING]
>
> 2026 年 8 月 26 日审阅的上游 issue（[sgl-project/sglang#34227](https://github.com/sgl-project/sglang/issues/34227)）报告：使用 `--use-fsdp-inference true` 部署 H3 可能静默产生损坏的视频和音频，且服务端无任何报错。在该问题解决前，优先使用上表的 TP 和 Ulysses 放置；依赖 FSDP 前请先验证输出。

### 2 × 8 × H200 跨节点扩展

单节点 8 × H200（Ulysses 8）与双节点 16 卡（Ulysses 8 × Ring 2，节点间 InfiniBand）的受控 denoise 阶段对比，固定 prompt、seed 和步数。跨节点 H3 必须使用 `--encoder-parallel replicate`；`auto` 的 fold 决策不感知节点边界。

| 任务 | 单节点（Ulysses 8） | 跨节点（Ulysses 8 × Ring 2） | 变化 |
| :- | -: | -: | -: |
| T2VA 单步 denoise | 0.749 s | 0.477 s | −36.3% |
| Ref2VA/V2V 单步 denoise | 2.572 s | 1.494 s | −41.9% |

序列越长收益越大。跨节点输出在重复运行间是确定的，但不应期望与相同 prompt 和 seed 的单节点运行逐位一致。

### 消费级 GPU 与 Ascend NPU

| 配置 | 负载与模式 | 已公布结果 |
| :- | :- | :- |
| 2 × RTX 5090 32 GB、TP 2 + layerwise 卸载、lossless | Quickstart 配置、50 步 | 端到端 559.67 s（denoise 525.05 s、decode 33.61 s），单卡采样峰值 26.3 GiB |
| 1 × RTX 4090 24 GB、layerwise 卸载 + `kitchen_int8` | Quickstart 配置；在线 INT8 为近似路径 | GPU 峰值约 18 GB；延迟取决于主机内存与卸载带宽 |
| 8 × Ascend NPU、TP 2 + SP 4、Laser Attention + Cache-DiT | Quickstart 配置；Cache-DiT 为近似路径 | 端到端 55.07 s |
| 4 × Ascend NPU、TP 2 + SP 2、Laser Attention + Cache-DiT | Quickstart 配置；Cache-DiT 为近似路径 | 端到端 103.57 s |

消费级 GPU、卸载、量化、AMD 和多节点配方会独立演进。在 MiniMax 发布测试矩阵前，应将其视为 [SGLang 上游配置](https://docs.sglang.io/cookbook/diffusion/MiniMax/MiniMax-H3)，而不是 MiniMax 已验证硬件。

## SGLang 权重、缓存与离线部署

* 官方 Hugging Face 仓库为 [`MiniMaxAI/MiniMax-H3`](https://huggingface.co/MiniMaxAI/MiniMax-H3)。默认缓存根目录是 `~/.cache/huggingface`；本页通过 `HF_HOME` 覆盖它。
* 中国大陆镜像为 [`MiniMax/MiniMax-H3`](https://modelscope.cn/models/MiniMax/MiniMax-H3)。其 revision 与固定 Hugging Face commit 的一致性尚无公开说明，因此不用于本页可复现基线。
* 内网部署时，先在联网机器上执行固定的 `hf download` 命令，传输完整模型目录，并确认 `model_index.json` 及所选 `FL2VA/` 或 `Ref2VA/` 目录均存在。启动时设置 `HF_HUB_OFFLINE=1`。
* Hugging Face 下载中断后可以使用相同 revision 重新运行命令。如怀疑缓存损坏，使用 `hf download --force-download` 重新下载固定 revision，不要静默切换版本。
* 除非部署会同时提供两类能力，否则不要下载两个 checkpoint 分区；每个分区需要独立服务。

## SGLang 生产部署与安全

Quickstart 仅监听 `127.0.0.1`，不提供公网入口。如需对外暴露服务：

* 放在带鉴权的反向代理或 API gateway 后，并要求 API Key 或等价身份校验。
* 在入口终止 TLS，并通过防火墙、安全组或私有网络限制后端端口。
* 设置请求配额、并发任务限制、输出保留策略、审计日志，以及 H3 License 要求的滥用防护。
* 以只读方式挂载服务端参考素材，并仅允许专用目录，不要开放任意文件系统路径。
* 如入口会下载远程图片、视频或音频 URL，应先执行域名白名单、重定向次数、连接/读取超时、最大字节数、解码图片尺寸和媒体时长限制，再将本地文件交给 SGLang。

只有这些控制就绪后，才应将服务改为 `--host 0.0.0.0`。SGLang 的模型支持本身不提供 License 要求的安全措施。

## SGLang 故障排查

| 现象 | 可能原因 | 最短修复方式 |
| :- | :- | :- |
| `/liveness` 正常，但 `/health` 返回 503 | 模型仍在下载、加载或 warmup | 保持服务运行并检查日志；仅在 `/health` 返回 200 后发送生成请求 |
| 加载或 warmup 时 CUDA OOM | 放置或拓扑不同于参考配置，或其他进程占用显存 | 停止竞争 GPU 的进程，重试精确的 8 × B200 命令；否则从 SGLang Cookbook 选择有实测数据的配置 |
| 出现 import、CUDA kernel 或算子错误 | Python、驱动、CUDA 或 SGLang 源码偏离固定基线 | 新建 Python 3.12 环境，checkout 文档中的 commit，重新安装 `python[diffusion]` 并检查驱动兼容性 |
| NCCL 超时或 worker 启动失败 | GPU 之间不可达，或可见 GPU 数量与并行度不一致 | 检查 `nvidia-smi topo -m` 和 `CUDA_VISIBLE_DEVICES`；首次部署保持单节点 8 张可见 GPU |
| 任务立即因 task 或 condition 失败 | 请求发给了错误 checkpoint 分区，或条件集合无效 | 将 `t2va`/`fl2va` 发给 FL2VA，将 `ref2va` 发给 Ref2VA；Ref2VA 至少包含一个参考条件 |
| 模型文件缺失或损坏 | 下载不完整，或目录混入了其他 revision | 重新运行固定的 `hf download` 命令；必要时使用 `--force-download`，每个目录只保留一个 revision |
| 任务为 `completed` 但内容下载失败 | task ID 或端口属于另一服务，或结果已不可用 | 在同一 host 与 port 查询任务，检查返回 JSON，并在完成后立即下载 |

## 使用 vLLM-Omni 自托管

[vLLM-Omni](https://github.com/vllm-project/vllm-omni) 也通过 OpenAI 兼容的 `/v1/videos` API 提供 H3 服务，配方见其社区维护的 [MiniMax-H3 recipe](https://github.com/vllm-project/vllm-omni/blob/main/recipes/MiniMaxAI/MiniMax-H3.md)。它是上游备选路径，不是本页的可复现基线；上文的 SGLang Quickstart 仍是固定参考路径。

| 项目 | 审阅基线 |
| :- | :- |
| 状态 | **Experimental** — 社区维护的 recipe，2026 年 8 月 26 日审阅 |
| 框架 | vLLM `0.26.0` 搭配 vLLM-Omni；下方 RTX 5090 验证使用 vLLM-Omni `0.26.1.dev14+gae6577ea` |
| API | 同步 `/v1/videos/sync` 直接返回 MP4 响应体，另有异步 `/v1/videos` 任务流程 |
| 服务形态 | 单个合并服务可同时加载 FL2VA 与 Ref2VA 两个 DiT，并共享 text encoder 和 VAE；SGLang 则要求每个分区一个服务 |
| 存储 | 每个 checkpoint 分区磁盘占用约 135 GiB；本地保留两个分区约需 270 GiB |
| 消费级 GPU 主机内存 | 双 GPU 卸载配方要求至少 200 GiB 可用系统内存；推荐 384 GiB 主机 |
| 硬件路径 | 单 GPU + CPU 卸载；2 × RTX 5090/4090（TP 2 + 分布式 layerwise 卸载）；4 张大显存 GPU 无卸载；AMD ROCm（gfx942/gfx950） |

以下是转录自该 recipe 的上游实测数据。除非负载一致，不要与上文 SGLang 表格直接比较；其中多行使用 209 帧而非 Quickstart 的 124 帧配置。

| 配置 | 负载 | 已公布结果 |
| :- | :- | :- |
| 4 × B300、无卸载、Ulysses 4、VAE tile 并行 4、regional compile | FL2VA、1248 × 768、209 帧、50 步 | 平均客户端延迟 86.964 s，1 次 warmup 后测 3 次请求 |
| 同上配置 | 双视频 Ref2VA、1344 × 768、362 帧 | 模型阶段平均 784.394 s |
| 2 × RTX 5090 32 GB、TP 2 + 分布式 layerwise 卸载、eager | T2VA、1344 × 768、124 帧、50 步 | 客户端端到端 8 分 38 秒，单卡采样峰值约 22.6 GiB；单次验证运行，非预热后的多次 benchmark |
| 4 × MI300X（ROCm）、FLASH\_ATTN、Ulysses 4、text-encoder TP 4、VAE tile 并行 4 | T2VA、1344 × 768、209 帧、50 步 | 客户端端到端 267.42 s，1 次 warmup 后 3 次请求的均值 |
| 4 × H200、SP 4 + text-encoder TP 4、请求级 `quality` | 1344 × 768、124 帧、50 步 | `lossless` 中位数 85.49 s；`high`（Cache-DiT）中位数 63.36 s，1.35 ×，相对 lossless 的 SSIM 为 0.9709 |

来自该 recipe 的运维要点：H3 为 CFG 蒸馏模型，`--cfg-parallel-size` 必须保持 1；H3 VAE 只支持原生 `tile` 并行模式；纯 Ulysses 会在每个 rank 上复制完整 DiT，不能作为小显存 GPU 的容量路径；上游实测显示请求合批（`--step-execution --max-num-seqs 4`）不会提升 H3 同时到达的大请求吞吐。`ffmpeg` 和 `ffprobe` 必须在 `PATH` 中。

## 使用 miles-diffusion 对 H3 进行 LoRA 微调

[miles-diffusion](https://github.com/radixark/miles_diffusion) 发布了 H3-Base FL2VA 的端到端 LoRA SFT 配方，覆盖数据预处理约束、单命令训练脚本、学习率消融，以及导出回 SGLang 服务的路径。这是上游训练配方，不是 MiniMax 已验证基线；用于生产前请重新验证。

| 项目 | 固定基线 |
| :- | :- |
| 训练状态 | **Experimental** — 上游配方，2026 年 8 月 26 日按 miles-diffusion commit `578d5a571c4924787eb85f0e6eac0de381f3e54f` 审阅 |
| 基座 checkpoint | H3-Base FL2VA；`t2va` 配方只训练视频分支，音频参与 rollout 但不计入 loss |
| 配方 | `scripts/run_diffusion_sft_h3_t2va.py`，零参数、绑定数据集运行 |
| 参考数据集 | [`rockdu/WISA-80K-Practical-Dynamics-254`](https://huggingface.co/datasets/rockdu/WISA-80K-Practical-Dynamics-254)，254 个已对齐服务网格的精选窗口 |
| 参考硬件 | 单节点 8 × H200 |
| 配方默认值 | 学习率 3e-5、weight decay 0.01、LoRA rank 64 / alpha 128、rollout batch 32、`--fsdp-flow-shift 12.0`、`--diffusion-guidance-scale 1.0`、`--sft-offload-encoder` |

训练数据必须精确落在 H3 的服务网格上；encoder 会拒绝任何不合网格的输入：

| 项目 | 要求值 |
| :- | :- |
| 画布 | 短边 768；16:9 对应 1344 × 768 |
| 帧率 | 24 FPS，严格校验（±0.01） |
| 帧数 | `17n + 5` 网格，最少 107 帧（约 4.46 秒） |
| Manifest | JSONL，每行 `{"prompt": ..., "metadata": {"video": "clips/clip.mp4"}}`；相对媒体路径以 JSONL 所在目录为锚点 |

启动训练：

```bash theme={null}
export WANDB_API_KEY=...                       # 不设置时配方不提交任何 wandb 参数
python3 scripts/run_diffusion_sft_h3_t2va.py   # 首次运行下载参考数据集并开始训练
# 自定义数据：  --extra-args "--prompt-data /abs/train.jsonl"
# 延长训练：    --num-epoch 10                  # 配方默认为 3
```

### 训练性能参考

在 8 × H200 上使用 254 窗口参考数据集实测：

| 阶段 | 已公布结果 |
| :- | :- |
| Encoding | 每卡每 clip 约 15 s；首轮数据集遍历因缓存缺失每个 rollout 停顿约 110 s（rollout 0 为 230 s），从 rollout 8 起进入热缓存 |
| 缓存 | 按内容寻址，约为数据集大小的 2 倍，存放在 JSONL 旁的 `.sft_cache/`，跨运行复用 |
| Encoder 驻留 | 使用 `--sft-offload-encoder` 时，约 70 GB 的 encoder 常驻主机内存，仅在 encode 阶段占用 GPU |
| Optimizer step | 每步约 31 s，每个已编码 batch 执行 4 步（`--num-steps-per-rollout 4`） |
| 3 epochs（21 rollouts、84 steps） | 冷缓存 66 分钟 |
| 10 epochs（70 rollouts、280 steps） | 冷缓存 2 小时 50 分，热缓存 2 小时 31 分 |

Checkpoint 在每个 epoch 边界和最后一个 rollout 保存；`iter_N` 计数已完成的 rollout，不是 optimizer step。应观察分桶 loss（`--log-loss-sigma-bucket`）而非聚合曲线：DiT 的 loss 量级随抽到的噪声水平大幅波动。

### 学习率消融

上游消融固定数据与配置（rank 64 / alpha 128、254 窗口 × 10 epochs），学习率是最敏感的参数：

| 学习率 | 结果 |
| :- | :- |
| 3e-4 | 训练崩溃 |
| 1e-4 | 可见的画面退化 |
| 5e-5 | 首个 epoch 内出现过拟合迹象 |
| **3e-5** | **最佳结果；配方默认值** |
| 1e-5 | 欠拟合，与基座几乎无差异 |

### 导出并部署 LoRA

训练只产出 DCP checkpoint。导出为单个 safetensors 文件及其 `adapter_config.json` sidecar：

```bash theme={null}
python3 scripts/export_lora.py --ckpt-dir <run>/ckpt/iter_0000070 \
  --out my_h3_lora.safetensors --lora-rank 64 --lora-alpha 128
```

SGLang 通过 `--lora-path` 直接加载导出的 adapter。sidecar 必须与 safetensors 文件放在同一目录：加载时在该目录查找 sidecar，缺失时 alpha 会回退为 rank，即强度减半。对比未修改基线前，请记录 adapter 文件、rank、alpha 和基座 revision。

## License 与系统边界

[MiniMax H3 Community License Agreement](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) 包含地域、商业使用、分发、署名、托管服务安全措施和 Acceptable Use Policy 等条款。License 可能变化，应以链接中的文本为准。

| H3 组件 | 是否包含在开放发布中 | 作用 |
| :- | :- | :- |
| H3-Context-IR | 否 | 将自由形式多模态上下文转换成结构化表达 |
| H3-Base FL2VA / Ref2VA | 是 | 生成 768p 视频与同步立体声音频 |
| H3-Regenerate-2K | 否 | 根据原始上下文和 768p 结果再生成 2K 输出 |

模型卡、可复现示例、prompt 指南和 License Q\&A 请参阅 [`MiniMaxAI/MiniMax-H3` 仓库](https://huggingface.co/MiniMaxAI/MiniMax-H3)。高级硬件、精度、放置和性能配置请参阅 [SGLang MiniMax-H3 Cookbook](https://docs.sglang.io/cookbook/diffusion/MiniMax/MiniMax-H3)。
