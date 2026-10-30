<!-- 2.0 官方教程里与「写提示词」直接相关的章节，**逐字摘录**。
     摘录行号见每段标题下方；原文见 D:/tmp/official/sd20/ 同名文件。
     不写摘要 —— 裁节/改写 = 替官方写摘要，已栽过。 -->

<!-- 出处：tutorial.md:1845-1866（提示词技巧 / 提示词 Skill / 提示词规则） -->
# 提示词技巧
## 提示词 Skill

平台提供 **Seedance 2.0 提示词优化技能**，方便您对提示词进行调优。

* **配置方式**：推荐在本地项目中运行以下命令，通过方舟文档 Skills catalog 安装 `sd2-pe`：

    ```bash
    npx --yes skills@latest add "https://arkdocs.tos-cn-beijing.volces.com/skills/" \
      --skill sd2-pe \
      --yes
    ```

    如需手动安装，可以下载以下 `SKILL.md` 文件。以 OpenClaw 为例，将文件完整内容复制到对话输入框中，并发送“请帮我安装这个技能”，等待工具完成安装。

    [SKILL.md](https://arkdocs.tos-cn-beijing.volces.com/files/video-generation/SKILL.md)

* **使用方式**：在 AI 对话框输入 `/sd2-pe + 你的提示词内容`，开始调试提示词。

## 提示词规则

- 提示词中必须使用"**素材类型+序号**”格式引用素材，序号为请求体中该素材在同类素材中的排序。例如 「图片 n」指代`content`数组中第 n 个`type="image_url"`的参考图片（按数组顺序从1开始计数）。**注意不支持使用 Asset ID 指代素材**。

<!-- 出处：video-gen-tutorial.md:1555-1564（提示词建议） -->
## 提示词建议

* **提示词 = 主体 + 运动， 背景 + 运动，镜头 + 运动 ...**
* 用简洁准确的自然语言写出你想要的效果。
* 如果有较为明确的效果预期，建议先用生图模型生成符合预期的图片，再用图生视频进行视频片段的生成。
* 文生视频会有较大的结果随机性，可以用于激发创作灵感
* 图生视频时请尽量上传高清高质量的图片，上传图片的质量对图生视频影响较大。
* 当生成的视频不符合预期时，建议修改提示词，将抽象描述换成具象描述，并注意删除不重要的部分，将重要内容前置。
* 更多提示词的使用技巧请参见 [Doubao Seedance 2.0 系列提示词指南](/docs/seedance-2-0-prompt-guide)、[Seedance 1.0 系列提示词指南](/docs/seedance-1-0-pro-pro-fast)。
