# MiniMax H3 官方资料（公开来源）

抓取日 **2026-10-26**。全部是**公开文档**，不需要登录。

| 文件 | 来源 | 说明 |
|---|---|---|
| `official_manual_h3_full.txt` | 飞书 wiki（互联网公开） | **H3 模型使用手册全文**：4 章 / 22,883 汉字 / 36,835 字符 |
| `official_manual_h3_p1-ssr.md` | 同上，网页 SSR 载荷 | 只有**第一页**（239 块）的结构化还原：标题/表格/图片/附件 token，用来补全文里丢失的表格与素材名 |
| `official_video-generation.md` | `platform.minimaxi.com/docs/guides/video-generation.md` | 视频生成：模型规格与输入条件 |
| `official_video-prompt.md` | `…/guides/video-prompt.md` | H3 亮点功能示例（中文提示词 + 参考素材 + 成片） |
| `official_llms-index.txt` | `platform.minimaxi.com/docs/llms.txt` | 官方文档总索引 |
| `11f12610.txt` / `dfe52602.txt` | GitHub `MiniMax-AI/MiniMax-H3` | **两份官方完整 Ref2VA 六段式示例**（`ref-en` §7 与 README 里的 API 响应） |

## 取法（复现用）

```bash
# ① 公开文档站：must 带 -L（302 到 platform.minimax.cn）
curl -sSL "https://platform.minimaxi.com/docs/guides/video-generation.md" -o out.md

# ② 飞书 wiki：**必须带完整浏览器头**，裸 UA 会被 302 到 accounts.feishu.cn 登录页
curl -sSL -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" \
     -H "Accept: text/html" "https://vrfi1sk8a0.feishu.cn/wiki/FIWjwgL33ipnkekzk30crmKUnIh"

# ③ 全文要滚动加载（SSR 只有第一页，has_more=True）→ 无头 Chrome + CDP 滚到底
python D:/tmp/cdp_scroll_doc.py        # websockets 驱动，输出 D:/tmp/h3_manual_full.txt
```

⚠️ **`D:/tmp/h3_manual.html` 是无效文件**：那是裸 UA 抓下来的**飞书登录页空壳**
（92,197 字节，`<title>` 空、`<table>` 0 个），不是手册。别再拿它当资料。

## 完整性

- ✅ 四章正文全在（一、模型定位 / 二、模型功能信息 / 三、模型亮点能力&示例 / 四、如何更好地使用 H3），
  含 1.1–1.10、2.1–2.3、3.1–3.4、四章 1.1–1.5 与「特定风格」「最佳方式」全部小节。
- ⚠️ **顶部「持续更新中」callout 的更新日志**（9/1 新增…）没抓到（在滚动容器外），
  以 `official_manual_h3_p1-ssr.md` 为准。
- ⚠️ 浏览器全文里**夹着页面评论**（`用户NNNN` + `M月D日 H:MM` + 评论内容），那是读者留言，
  **不是官方原文**；引用时别把评论当规范。
- ⚠️ 个别符号有渲染差异（SSR 的 `16:9~9:16` 在浏览器里显示成 `16:9〜9:16`），比对时按句子比不要按字符比。

## 引用边界

🩸 **这本手册讲的是「用户手写入口」**（公式 = 参考素材说明 + 核心创意 + 画面过程说明，
素材用 `@图片1/@视频1/@音频1` 标注）。我们编译器产出的是**官方 skill 的 Ref2VA 六段式**
（`subject_definitions`…`non_diegetic_music`，标号是 `<Subject N>/<Picture N>`）。
**两种体裁，规则不能互相搬**；手册能用来核对"内容层"要求（台词长短、画外音、运镜词表），
不能拿来当六段式格式的判据。
