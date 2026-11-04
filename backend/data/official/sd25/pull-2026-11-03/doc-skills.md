# 文档 Skill

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

本文列出当前方舟文档提供的 Skill。

<span id="skill-list"></span>
## Skill 列表

| Skill | 功能 |
| --- | --- |
| `ark-docs-reader` | 根据目标站点已提供的入口读取最新官方正文，并列出实际来源 |
| `ark-model-benchmark` | 评测方舟模型的 TTFT、TPOT、E2E 和缓存命中率，并生成评测报告 |
| `ark-docs-assistant` | 分析模型升级或迁移方案，扫描项目中的模型引用并评估替换风险 |
| `sd25-pe` | 优化 Seedance 2.5 视频生成提示词 |
| `sd2-pe` | 优化 Seedance 2.0 视频生成提示词 |

<span id="install-skills"></span>
## 安装 Skill

安装前需准备 Node.js 22.20.0 或更高版本，以及 npm。安装完成后，重新打开 AI Agent 会话再使用 Skill。

<span id="ark-docs-reader"></span>
### ark-docs-reader

`ark-docs-reader` 用于检索并读取最新的方舟官方文档。Agent 会优先调用文档 MCP 搜索并获取正文；尚未接入文档 MCP 时，Skill 会推荐 Claude Code 或 Codex 对应的安装命令。MCP 不可用时，Skill 会通过火山方舟 `llms.txt` 继续完成当前检索。

执行以下命令安装 Skill：

```Bash
npx --yes skills@latest add "https://arkdocs.tos-cn-beijing.volces.com/skills/" \
  --skill ark-docs-reader \
  --yes
```

安装完成后，使用自然语言触发。例如：

```text
查找最新方舟官方文档，说明 Responses API 如何开启深度思考，并列出来源。
```

文档 MCP 的配置方法，详情请参见[文档 MCP](/docs/tutorials-mcp)。`llms.txt` 的文件地址和使用方式，详情请参见[llms.txt](/docs/read-ark-docs-with-llms-txt)。

<span id="ark-model-benchmark"></span>
### ark-model-benchmark

`ark-model-benchmark` 支持连通性检查、Prefix 前缀复用、多轮长上下文和完整测试，并在 `reports/` 目录中生成 Markdown 报告和 PNG 图表。

使用前需安装 Ark CLI 并完成 SSO 登录：

```bash
npm install -g @volcengine/ark-cli@latest
arkcli auth login volc-sso
```

执行以下命令安装 Skill：

```bash
npx --yes skills@latest add "https://arkdocs.tos-cn-beijing.volces.com/skills/" \
  --skill ark-model-benchmark \
  --yes
```

安装完成后，使用自然语言触发。例如：

```text
帮我压测一下方舟上豆包 Seed 2.0 Mini 模型的性能。
```

有关评测模式、参数和报告说明，详情请参见[模型接入指南（LLM） - 性能评测](/docs/go-live-benchmark-guide)。

<span id="ark-docs-assistant"></span>
### ark-docs-assistant

`ark-docs-assistant` 用于分析模型升级或迁移方案，也可以扫描代码项目中的模型引用，生成模型替换清单并评估迁移风险。

该 Skill 优先使用文档 MCP 获取信息；MCP 不可用时，会尝试使用 Ark CLI。文档 MCP 的配置方法，详情请参见[文档 MCP](/docs/tutorials-mcp)。

执行以下命令安装 Skill：

```bash
npx --yes skills@latest add "https://arkdocs.tos-cn-beijing.volces.com/skills/" \
  --skill ark-docs-assistant \
  --yes
```

安装完成后，使用自然语言触发。例如：

```text
扫描当前项目，将目标模型升级为最新模型，先给出迁移清单，不要直接修改。
```

有关模型迁移场景，详情请参见[Seed-Evolving](/docs/latest-model)。

<span id="sd25-pe"></span>
### sd25-pe

`sd25-pe` 可以处理文本、故事片段和多模态参考素材，并根据视频生成、关键帧、分镜、视频编辑、声音编辑或视频延长等任务组织提示词。

执行以下命令安装 Skill：

```bash
npx --yes skills@latest add "https://arkdocs.tos-cn-beijing.volces.com/skills/" \
  --skill sd25-pe \
  --yes
```

安装完成后，在 AI Agent 对话框中输入：

```text
/sd25-pe + 你的提示词内容
```

该 Skill 只负责生成或优化提示词，不会自行提交视频生成任务。有关 Seedance 2.5 提示词写法，详情请参见[Doubao Seedance 2.5 提示词指南](/docs/seedance-2-5-prompt-guide)。

<span id="sd2-pe"></span>
### sd2-pe

`sd2-pe` 可以根据任务类型整理 Seedance 2.0 视频生成提示词中的主体、动作、场景、镜头、风格和素材引用关系。

执行以下命令安装 Skill：

```bash
npx --yes skills@latest add "https://arkdocs.tos-cn-beijing.volces.com/skills/" \
  --skill sd2-pe \
  --yes
```

安装完成后，在 AI Agent 对话框中输入：

```text
/sd2-pe + 你的提示词内容
```

有关 Seedance 2.0 的模型能力和提示词规则，详情请参见[Doubao Seedance 2.0 系列教程](/docs/seedance-2-0)。
