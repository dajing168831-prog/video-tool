# 退役脚本

这里放的是**已经被产品下线取代**的验收脚本，不参与回归，也不再运行。
保留原因：它们记录了当时"新实现 vs 旧实现逐帧等价"的验法，日后要复现可以读。

## 2026-10-23 · 字幕轨下线

主人拍板「也不烧字幕」→ 成片不再烧任何字幕（`tracks.CaptionTrack`、
`subtitle_ass`、`caption_components` 全部删除）。下面四个脚本的前提
（"三条轨道：画面 / 声音 / **字幕**"）不再成立，故整体退役：

| 脚本 | 原来验什么 |
|---|---|
| `track_p2_check.py` | 轨道模型 == 旧 `compose()`：配音+字幕 / 底音+遮罩 / 只有原声 / 定格补时长 四场景逐帧 PSNR |
| `track_p25_check.py` | 轨道模型 v2.5 的镜头重排 + 字幕 + 复制帧等价性 |
| `legacy_compose.py` | **冻结的旧实现**，当参照物用 |
| `legacy_assemble.py` | **冻结的旧镜头组装**，当参照物用 |

替代覆盖：`test_audio_modes`（三种声音模式）、`rehearse_render`（分段渲染）、
`test_auto_render`（自动渲染链路）、`test_render`（切片→合成冒烟）。
