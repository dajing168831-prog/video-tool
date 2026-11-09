"""商品短剧 · 内置素人主播库（6 个预设）。

🩸 **照抄，不是我们写的。** 2026-11-06 主人：「他的能力远不止剧情，也有主播预设功能。
如果你这样就是直接阉割功能了。」
来源：clipforge `src/lib/presenters.ts:57-106`（`PRESENTER_PRESETS`）与
`:167-172`（`presenterPromptBlock`）。六个字一个字没改，只把 `goodFor` 换成 `good_for`。

作用（也是竞品文件头写的 `presenters.ts:16-18`）：让剧本模型有个**可挑的起点** ——
「可直接选用其一或在其基础上微调，也可自创」，避免每次都由模型临场编一个
普通到没人味的「30 岁女性」。

和另外三组规则的分工（别以为漏抄了）：
  · 反「AI 网红脸」/ 处境痕迹 / 口语台词 → 已进 skill 的 `output_script.md`
  · 人物画面首帧真实感 → 已进 skill 的 `output_storyboard.md`
  那三组是**全局约束**，skill 每次都会注入；这里只放**可选的库**，避免同一段话
  在一份提示词里出现三四遍。
"""
from __future__ import annotations

#: 六个素人主播原型。`good_for` = 这类人卖什么好卖。
PRESETS: list[dict] = [
    {
        "id": "neighbor_sister",
        "name": "邻家姐姐",
        "gender": "female",
        "persona": "实在爱吐槽，先挑刺后真香",
        "appearance": "32 岁左右居家女性，清爽耐看有亲和力，松散低马尾带自然碎发，日常淡妆，"
                      "皮肤自然真实，穿浅色宽松居家服，左手腕上套着一根用旧的发圈",
        "good_for": "家居日用 / 食品",
    },
    {
        "id": "office_lady",
        "name": "通勤上班族",
        "gender": "female",
        "persona": "理性种草，讲成分讲证据",
        "appearance": "35 岁左右上班族女性，耐看有气质，齐肩发自然垂落，日常淡妆，"
                      "皮肤自然真实不磨皮，穿简洁衬衫，右侧袖口随手挽起一截",
        "good_for": "美妆护肤 / 数码 3C",
    },
    {
        "id": "student_girl",
        "name": "大学生妹妹",
        "gender": "female",
        "persona": "活泼真实，反应大",
        "appearance": "22 岁左右邻家女生，清爽可爱戴细框眼镜，高马尾有自然碎发，淡妆，"
                      "笑容有感染力，穿普通棉 T 恤，胸前挂着挂绳耳机",
        "good_for": "零食 / 平价好物",
    },
    {
        "id": "practical_mom",
        "name": "实在宝妈",
        "gender": "female",
        "persona": "精打细算，只认性价比",
        "appearance": "38 岁左右亲切妈妈，及肩自然卷发，温和耐看，素净淡妆，皮肤自然真实，"
                      "系着围裙或穿家常外套，围裙口袋里露出半截小毛巾",
        "good_for": "母婴 / 食品 / 家居日用",
    },
    {
        "id": "tech_bro",
        "name": "理工直男",
        "gender": "male",
        "persona": "参数党，嘴硬心软真香现场",
        "appearance": "30 岁左右干净利落的普通男性，短发，长相端正亲切，皮肤自然真实，"
                      "穿格子衬衫或纯色 T 恤，领口别着一支笔",
        "good_for": "数码 3C / 工具",
    },
    {
        "id": "honest_uncle",
        "name": "实在大叔",
        "gender": "male",
        "persona": "话糙理不糙，自用推荐",
        "appearance": "45 岁左右和善大叔，短发略带花白，面相憨厚可靠，皮肤自然真实，"
                      "穿普通 polo 衫，胸前口袋插着老花镜",
        "good_for": "食品 / 农产 / 工具",
    },
]

#: 模式里根本不出人的两种：给了库也没用，还会让模型硬塞一个人进来。
_NOBODY_MODES = ("产品特写", "图文混剪")


def names() -> list[str]:
    return [p["name"] for p in PRESETS]


def by_name(name: str) -> dict | None:
    n = (name or "").strip()
    return next((p for p in PRESETS if p["name"] == n), None)


def public() -> list[dict]:
    """给界面用的精简列表（不含内部 id）。"""
    return [{"name": p["name"], "gender": p["gender"], "persona": p["persona"],
             "good_for": p["good_for"], "appearance": p["appearance"]} for p in PRESETS]


def prompt_block(picked: str = "", mode: str = "") -> str:
    """注入剧本提示词的那段。

    `picked` = 使用者指定了某一位 → 只写这一位，并要求主角照它写；
    没指定 → 列全库，由模型挑或自创（竞品原话「可直接选用其一或在其基础上微调，
    也可自创」）。
    """
    if mode in _NOBODY_MODES:
        return ""
    fixed = by_name(picked)
    if fixed:
        return (
            f"出镜人物固定用「{fixed['name']}」（{fixed['persona']}）：{fixed['appearance']}"
            f"（适合{fixed['good_for']}）。\n"
            "主角的外观、年龄、气质就按这一位写；另一个角色由故事需要决定，"
            "但必须同样是普通素人长相，不能写网红脸。"
        )
    lines = "\n".join(
        f"- {p['name']}（{'女' if p['gender'] == 'female' else '男'}，{p['persona']}）："
        f"{p['appearance']}（适合{p['good_for']}）"
        for p in PRESETS
    )
    return (
        "内置素人主播库（角色外观可直接选用其一或在其基础上微调，也可自创——"
        "但必须保持同样的「普通素人」真实感）：\n" + lines
    )
