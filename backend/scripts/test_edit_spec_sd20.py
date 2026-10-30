"""火山 Seedance 2.0 的提示词自检（**只测 2.0**，别家的断言不许进这个文件）。

由 `test_edit_spec.py --model volc20` 调用；共用规则在 `test_edit_spec_common.py`。
不联网、不花钱。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import edit_spec  # noqa: E402
from app.services import models  # noqa: E402
# 🩸 2026-10-28：2.0 的认人尺（`sd20_locator` / `_landmark_phrase` / `_ref_feat`）
#   已从共用层搬进 2.0 自己的编译器 —— 判据跟着改引用，校验内容一个字没动。
from app.services.models import volc20_compile as _cmp20  # noqa: E402
import test_edit_spec_common as common  # noqa: E402
from test_edit_spec_common import (  # noqa: E402
    check, only_face, p, p1, p2, ppl2,
)

MODEL = "volc20"
LABEL = "火山 2.0"


def run() -> None:
    print("== 火山 2.0 提示词 ==")
    v = edit_spec.compile_prompt("volc", p, person_asset="asset-2026abc")
    # 官方 Seedance 2.5 提示词规则：「使用 @图片1、@视频1、@音频1 指代参考素材」
    check("用「@视频1/@图片1」", ("@视频1" in v and "@图片1" in v), True)
    check("不把 asset id 当指代", "asset-2026abc" not in v, True)
    # API 硬要求：提示词里必须有编辑意图词之一，否则被判成参考任务
    # （TaskTypeMismatch，钱花了才失败）。2.0 的编辑句式是「修改为」。
    check("含编辑意图词",
          any(k in v for k in ("编辑视频", "增加", "加上", "删除", "去掉",
                               "修改", "替换", "改成")), True)
    # 🩸 2026-10-28：2.0 的保留句 2026-10-27 起就是官方「单点编辑」原句
    #   （「保留原视频动作、位置、互动、镜头和背景。」），不再写「保持@视频1的…」。
    #   这条断言锚的是**淘汰掉的旧写法**，靠"编译时不传 model"才活着 = 假绿。
    check("含保留句", "保留原视频" in v, True)

    _p20 = edit_spec.compile_prompt("volc", p, model="doubao-seedance-2-0-mini")
    check("2.0 不写范围闭环（官方默认保持不变）",
          "其他可见人物、道具和背景元素保持原样" not in _p20, True)
    # 🩸 D6（2026-10-23）：官方是「多人 / 多主体场景必挂」（sd2-pe:101/:162）——
    # 单人画面没有第二张脸可撞，不该挂。多人那条在下面单独验。
    check("2.0 单人换人不挂双胞胎兜底", "禁止生成同款分身、双胞胎效果" not in _p20, True)
    # 🩸 2026-10-25：段内有原片切点时，换人必须点明「每一镜」（成对验）。
    # 现场：`052dcbf0` 13.885s 单人换人，4 个切点全在段内，提示词只说
    # 「将其中的人物替换为…」→ 0–11.2s 换了、11.333s 后两镜原样返回
    # （尾段 p90 0.288 / 同人占比 0.0，整段 p90 0.741 把它平均掉了）。
    _p20cut = edit_spec.compile_prompt("volc", p, model="doubao-seedance-2-0-mini",
                                       shot_cuts=[3.0, 6.9, 11.333])
    # 🩸 2026-10-26 撤回这条自造句：官方 2.0 三份文件里「每一个镜头 / 每一镜」
    # **0 次**，`sd2-pe:24` 的「其中的」本身就覆盖整条 @视频N。
    # 代价先说清楚：`052dcbf0` 那次是 4 个段内切点、尾段 11.333s 后没换
    # （尾段 p90 0.288），当时就是靠加这句"修"的 —— 但**那句没有任何官方出处**，
    # 现在按规矩撤掉，改由 `_p20cut` 保持官方 `:24` 原句。若真机再出现尾段
    # 不换，**必须拿 2.0 官方原句去解决，不许再自造**。
    check("2.0 单人 + 段内有切点 → 不写自造的「每一镜」范围句",
          "每一个镜头" not in _p20cut and "每一镜" not in _p20cut, True)
    _p20one = edit_spec.compile_prompt("volc", p, model="doubao-seedance-2-0-mini",
                                       shot_cuts=[])
    check("2.0 单人 + 一镜到底（无切点）→ 不写每一镜",
          "每一镜" not in _p20one, True)
    check("2.0 单人 + 没给切点信息 → 不写每一镜", "每一镜" not in _p20, True)
    # 这一刀里没出现那个人 → `_clauses` 不写换人句，范围句也不能挂
    _absent = [{"id": "P1", "present": False, "desc_zh": "穿红裙的女生"}]
    _p20abs = edit_spec.compile_prompt("volc", p, model="doubao-seedance-2-0-mini",
                                       source_people=_absent, shot_cuts=[3.0])
    check("2.0 人不在这一刀里 → 不写每一镜", "每一镜" not in _p20abs, True)

    _p2 = edit_spec.normalize({"person": True, "person_ids": ["P1", "P2"]})
    _p20m = edit_spec.compile_prompt("volc", _p2, model="doubao-seedance-2-0-mini",
                                     source_people=ppl2, slots=["person", "person2"])
    check("2.0 多人换人挂双胞胎兜底",
          "禁止生成同款分身、双胞胎效果" in _p20m, True)
    # 多人各有各的 <主体N>：说「每一镜里的人物」会把没被选中的那个人也换掉
    _p20multi = edit_spec.compile_prompt(
        "volc", _p2, model="doubao-seedance-2-0-mini", source_people=ppl2,
        slots=["person", "person2"], shot_cuts=[1.0])
    check("2.0 多人 + 有切点 → 不写「每一镜里的人物」（会误伤第二个人）",
          "每一镜里的人物" not in _p20multi, True)
    # 🩸 2026-10-25：**方位撞车不能当识别符**。现场 `6c51196b/3949eb3f`：
    # 男、女两个人都被盘点成 `position: "center"`，提示词拼成
    # 「将其中的**画面中央的人物**替换为@图片1中的人物」→ 谁也没指认到，
    # 整片一帧没换（六段 p90 0.09–0.19 全 not_swapped）。
    _dup = [{"id": "P1", "present": True, "position": "center",
             "desc_zh": "体型偏胖的男子，黑色头发束成发髻，身着浅青绿色古装"},
            {"id": "P2", "present": True, "position": "center",
             "desc_zh": "年轻女子，黑色长发梳成古装高髻，身着广袖古装"}]
    _p20dup = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "person_ids": ["P1"]}),
        model="doubao-seedance-2-0-mini", source_people=_dup,
        slots=["person", "person2_head"])
    check("两人同方位 → 不用方位当宾语（画面中央指认不到任何人）",
          "画面中央的人物" not in _p20dup, True)
    # 🩸 2026-10-26 22:xx **改判**（实测把"描述长度"这个变量单独拎出来了，
    # 台账 §13.13）：同素材 `494b1c28`、同参考图 `12a547` 的四条真机 ——
    #   15:46 / 16:20 / 16:42：**短定义 + 标签宾语** → 人眼核：**换上了**（3/3）
    #   19:43：一次定义 4 个主体、每条 20 字服装串 → 仍是原片演员
    #   20:13 / 20:20：把长特征串**直接塞进宾语** → 没换
    # ⇒ 致死的不是"有标签"，是标签后面跟了多长的定义。标签宾语只有 4 个字，
    #   正是主人要的「越简单越好」。所以多人画面单目标：**只给被换的那一位**
    #   发一个标签，宾语用它。
    # ⇒ 定义句**不写方位**（主人：「2.1 模型不会每次都知道那人在什么方向出现的」
    #   —— 复刻模板一上线，盘点给的 position 必然出错），只用官方 `:95` 的静态特征。
    # 🩸 2026-10-30 主人拍板：**一换一不发任何 `<主体N>` 定义**
    #   （`_person_tags_20` 停用；依据见那里：官方「编辑视频」三条句式都没有定义句，
    #    而定义句等于把原片那位的外观再讲一遍，正好抵消换脸）。
    #   指认改由**换人句宾语**承担，判据跟着搬。
    check("两人同方位 → 不再发 <主体N> 定义句",
          "定义为<主体" not in _p20dup, True)
    check("两人同方位 → 定义句不写方位", "画面中央" not in _p20dup, True)
    check("两人同方位 → 特征不带服装（换人后衣服会变）",
          "古装" not in _p20dup, True)
    check("两人同方位 → 宾语用特征短语指认原片那位",
          "将其中的体型偏胖的男子替换为@图片1中的人物" in _p20dup, True)
    # 🩸 2026-10-27 改判（主人：「我们要换的人他有可能不在中间，有可能不在左边，
    # 那我们怎么能让模型知道到底换谁」）：方位**是盘点逐条看画面给的**，不是我们
    # 假设的中心；在本片唯一时它就是官方 `:153` 的定位手段，写一句最短的就够。
    # 只有方位撞车/取不到时才补特征 —— 这是与上面"两人同方位"成对的那一档。
    _uniq = [dict(_dup[0], position="left"), dict(_dup[1], position="right")]
    _p20uniq = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "person_ids": ["P1"]}),
        model="doubao-seedance-2-0-mini", source_people=_uniq,
        slots=["person", "person2_head"])
    # 🩸 2026-10-30 主人拍板：**方位由「优先」降为「兜底」**（`sd20_locator` 三档）。
    # 两人描述互不相同 ⇒ 特征就能指认，这时定义句用特征（官方 `:95` 的形状），
    # 不再写方位。
    check("特征可分 → 宾语用特征短语（官方 :95）",
          "将其中的体型偏胖的男子替换为@图片1中的人物" in _p20uniq, True)
    check("特征可分 → 不写方位（方位是兜底档）",
          "画面左侧" not in _p20uniq and "画面右侧" not in _p20uniq, True)
    check("特征可分 → 不把外观串进指认", "古装" not in _p20uniq, True)
    # 兜底档（成对，不能只测一边）：两人描述**一模一样** ⇒ 特征指认不了，
    # 只剩方位能分，这时方位必须写。
    _samepair = [dict(_dup[0], id="P1", position="left"),
                 dict(_dup[0], id="P2", position="right")]
    _p20same = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "person_ids": ["P1"]}),
        model="doubao-seedance-2-0-mini", source_people=_samepair,
        slots=["person", "person2_head"])
    check("特征不可分 → 方位兜底写进宾语（官方 :153）",
          "将其中的画面左侧的人物替换为@图片1中的人物" in _p20same, True)
    # 🩸 成对：**标志性特征优先**（主人：「应该是带有标志性的。如果全部是黑人而且
    # 都长得一样呢？模型知道谁胖点瘦点？」）。真实盘点 `494b1c28` 的 P1：
    # 「留短黑发，佩戴黑框眼镜，身穿藏蓝色…外套的男性」——「留短黑发」全片三个人
    # 都成立，指认不了；眼镜才是二元、可数的标志。
    _land = [{"id": "P1", "present": True, "position": "center",
              "desc_zh": "留短黑发，佩戴黑框眼镜，身穿藏蓝色带白色字母印花、"
                         "红格纹连帽内衬的外套，内搭黑色上衣的男性"},
             {"id": "P2", "present": True, "position": "right",
              "desc_zh": "留短黑发，身穿黑色短袖高领上衣，搭配深色长裤配腰带的男性"}]
    # 🩸 2026-10-27 三档（成对，不能只测一边）：
    #   · 方位唯一 → **只用方位**，不叠一串外观；
    #   · 方位撞车 → 才退回标志性特征（眼镜这种二元、可数的才算标志）。
    # 🩸 2026-10-30：方位降为兜底。两人描述互不相同 ⇒ 用特征（含眼镜这个标志），
    # 不写方位；描述一样时才退回方位（见下面那条）。
    check("特征可分 → 用带标志的特征短语（不写方位）",
          _cmp20.sd20_locator(_land[0], _land), "留短黑发、佩戴黑框眼镜的男性")
    _landdup = [dict(_land[0], position="center"), dict(_land[1], position="center")]
    check("特征可分 → 方位撞车也不影响（本来就不写方位）",
          _cmp20.sd20_locator(_landdup[0], _landdup), "留短黑发、佩戴黑框眼镜的男性")
    _landsame = [dict(_land[0], id="P1", position="center"),
                 dict(_land[0], id="P2", position="right")]
    check("特征不可分 → 方位兜底（描述一模一样才用方位）",
          _cmp20.sd20_locator(_landsame[0], _landsame), "画面中央的人物")
    check("标志优先：挑不出标志时不硬编（体型/年龄不算）",
          _cmp20._landmark_phrase_20("体型偏胖的男子，黑色头发束成发髻"), "")
    # 🩸 成对两条（2026-10-24 实测：三版 2.0 换了人却一帧没变，提示词里那段
    # 原片外观写的全是衣服和道具，模型照着改那两样，脸不动）：
    #   · 盘点给了方位 → 只用方位点名，不写外观
    #   · 盘点没方位   → 必须靠外观认出换哪一位（否则会换错人）
    ppl2pos = [dict(ppl2[0], position="left"), dict(ppl2[1], position="right")]
    _p20p = edit_spec.compile_prompt("volc", _p2, model="doubao-seedance-2-0-mini",
                                     source_people=ppl2pos,
                                     slots=["person", "person2"])
    # 🩸 2026-10-27：方位唯一 → 两条定义各用各的方位（官方 `:153`）；
    # 方位撞车时才按官方 `:95` 换成特征短语（见上面 `_landdup` 那条）。
    # 🩸 2026-10-30：定义句停用 ⇒ 两条**换人句宾语**各用特征（官方 `:95`），不写方位。
    check("多人·特征可分：两条宾语各用特征",
          "将其中的穿红裙的女生替换为@图片1中的人物" in _p20p
          and "将其中的穿蓝衬衫的男生替换为@图片2中的人物" in _p20p
          and "画面左侧" not in _p20p and "画面右侧" not in _p20p, True)
    # 兜底档：两人描述一模一样 ⇒ 只剩方位能分，两条定义各用各的方位（官方 `:153`）。
    _samepair2 = [dict(ppl2[0], id="P1", position="left"),
                  dict(ppl2[0], id="P2", position="right")]
    _p20same2 = edit_spec.compile_prompt("volc", _p2,
                                         model="doubao-seedance-2-0-mini",
                                         source_people=_samepair2,
                                         slots=["person", "person2"])
    check("多人·特征不可分：两条宾语各用方位（官方 :153）",
          "将其中的画面左侧的人物替换为@图片1中的人物" in _p20same2
          and "将其中的画面右侧的人物替换为@图片2中的人物" in _p20same2, True)
    # 🩸 2026-10-26 18:xx（主人：「他指出了…能指出不算我们编」）：特征短语
    # **不许把盘点给的服饰截掉**。真实盘点 `494b1c28` 的两种形状：
    #   ① 服饰在末段里（「…的男性」之前那半句）
    #   ② 服饰自己占一段
    check("特征短语保留服饰（末段「的X」之前那半句）",
          edit_spec._feat_phrase("留短寸发型，身穿黑色长袖上衣的男性")
          == "留短寸发型、身穿黑色长袖上衣的男性", True)
    # 🩸 2026-10-27 主人拍板：封顶收到 **2**（官方 `:95` 是「2–3 个」，
    # 真机数据是 1 个 3/3 成功、3 个 0/2 失败，产品线取更严的 2）。
    # 这条仍然验原意：**服饰要被保留**，不能被当成"多余的第 N 段"整段丢掉。
    check("特征短语保留服饰（服饰独自成段）",
          edit_spec._feat_phrase(
              "留短黑发，身穿黑色短袖高领上衣，搭配深色长裤配腰带的男性")
          == "留短黑发、身穿黑色短袖高领上衣的男性", True)
    # 成对：官方 `:95`「2–3 个静态特征」→ 产品线 2，多于 2 段要封顶
    _long = edit_spec._feat_phrase(
        "留短黑发，佩戴黑框眼镜，身穿藏蓝色外套，内搭黑色上衣的男性")
    check("特征短语封顶 2 个（官方 2–3，产品线 2）", _long.count("、") + 1, 2)
    # 成对：第一段就以人称名词收尾的**原样返回**（已验证的写法不许被动）
    check("首段已是人称名词 → 原样返回",
          edit_spec._feat_phrase("体型偏胖的男子，黑色头发束成发髻，身着浅青绿色古装")
          == "体型偏胖的男子", True)
    # 成对：盘点没给描述时也能靠方位指认（不能因为没描述就写不出定义）
    _nofeat = [{"id": "P1", "present": True, "position": "left"},
               {"id": "P2", "present": True, "position": "right"}]
    _p20nf = edit_spec.compile_prompt("volc", _p2, model="doubao-seedance-2-0-mini",
                                      source_people=_nofeat,
                                      slots=["person", "person2"])
    check("没描述 → 方位照样能指认",
          "将其中的画面左侧的人物替换为@图片1中的人物" in _p20nf
          and "将其中的画面右侧的人物替换为@图片2中的人物" in _p20nf, True)
    # 🩸 2026-10-24 改：宾语**永远落在「人物」上**，不能是衣服/道具。
    # 旧版把方位和外观直接拼起来（「画面中央留黑色长直发…手枪替换为@图片1中的人物」），
    # 句子读起来是"把手枪换成一个人"，模型照字面执行，脸不动。
    # 🩸 2026-10-26 18:xx：宾语两侧分工固定 ——
    #   「其中的」那位是**原片里那个人**，用已定义的标签（`:109/:119`）；
    #   「替换为」那侧是**参考图里的人**，用图号 + 名词隔断（`:126`/`:17`）。
    # 🩸 2026-10-30：`<主体N>` 定义句停用 ⇒ 两侧都用图号/短语：
    #   「其中的」= 原片那位的指认短语；「替换为」= 参考图 `@图片N中的人物`（`:126`）。
    check("多人有方位：两句各绑各的图",
          "将其中的穿红裙的女生替换为@图片1中的人物" in _p20p
          and "将其中的穿蓝衬衫的男生替换为@图片2中的人物" in _p20p, True)
    _objs = [x.strip() for x in re.findall(
        r"将其中的(.{1,40}?)(?:完整)?替换为@图片\d+中的人物", _p20p)]
    check("换人句宾语是唯一指代（不是裸「人物」）",
          len(_objs) == 2 and all(o and o != "人物" for o in _objs), True)

    # 🩸 2026-10-25 成对闸门（本轮 2.0 改写专用，缺一条都不许提交）：
    #  ① 单人路径**逐字不变**：标签体系只在在场 ≥2 人时介入，
    #     单人那版是 `052dcbf0` 真机验过的（0–11.2s 换人成功）；
    #  ② 官方 `:56` 编辑任务禁止写「参考<视频N>」——写成那样会被判成参考任务，
    #     任务启动后异步报 TaskTypeMismatch，钱花了才失败。
    _one = [{"id": "P1", "present": True, "position": "center",
             "desc_zh": "体型偏胖的男子，黑色头发束成发髻，身着浅青绿色古装"}]
    _p20one = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "person_ids": ["P1"]}),
        model="doubao-seedance-2-0-mini", source_people=_one,
        slots=["person"])
    check("① 单人在场 → 不出标签（已验证的写法不许被动到）",
          "<主体" not in _p20one, True)
    check("① 单人单图 → 图职责句仍是官方两句原样",
          "参考@图片1中人物的面部特征和妆造" in _p20one, True)
    check("② 2.0 任何形态都不写「参考@视频1」（官方 :56）",
          all("参考@视频1" not in x for x in
              (_p20one, _p20dup, _p20uniq, _p20p, _p20m, _p20multi)), True)
    check("多人没方位：仍用外观定位（不然会换错人）",
          ppl2[0]["desc_zh"] in _p20m and ppl2[1]["desc_zh"] in _p20m, True)
    # 🩸 2026-10-25：2.0 逐句点名。官方 `:605` 的两人范例逐句点名
    # （「女性先说话，她说道"…"男性笑着回应"…"」），`:109/:119` 要求标签唯一
    # 且后续持续使用同一标签。以前整段只有一个 `who`，双人对话里所有台词
    # 挂同一个人（或全都不带说话人），模型只能猜谁动嘴。
    _desc2 = {"P1": {"zh": ppl2[0]["desc_zh"]},
              "P2": {"zh": ppl2[1]["desc_zh"]}}
    _two = edit_spec.normalize({"person": True, "person_ids": ["P1", "P2"],
                                "audio": "tts"})

    def _v20(lines: list) -> str:
        return edit_spec.compile_prompt(
            "volc", _two, model="doubao-seedance-2-0-mini",
            source_people=ppl2, slots=["person", "person2"],
            desc_by_id=_desc2, audio_ref=True, shot_cuts=[1.0],
            shot_lines=lines)

    _v20a = _v20([[{"start": 0.2, "end": 1.0, "text": "你来了", "lang": "zh",
                    "speaker": "P1"},
                   {"start": 1.2, "end": 2.0, "text": "我来了", "lang": "zh",
                    "speaker": "P2"}]])
    # 🩸 2026-10-27：图片侧先占号（官方 `20 双人全换`），原片侧两人从 `<主体3>` 起。
    # 🩸 2026-10-28 改：**说话人用替换之后的那个标签**。上面同一段已经写着
    #   「将其中的<主体3>替换为<主体1>；<主体1>的面部特征参考@图片1」——
    #   替换之后画面里这个人就是 `<主体1>`，再让 `<主体3>` 开口说话，
    #   等于把台词派给一张已经被换掉的脸（官方 `:119`「后续描述中需持续
    #   使用对应标签」、`:121`「避免语义冲突」）。
    # 🩸 2026-10-30：`<主体N>` 停用 ⇒ 被换的人用**参考图**指代（换完他就是那张脸）。
    check("2.0 逐句按说话人指名（第一句）",
          "@图片1中的人物使用@音频1的音色说{你来了}" in _v20a, True)
    check("2.0 逐句按说话人指名（第二句换人）",
          "@图片2中的人物使用@音频1的音色说{我来了}" in _v20a, True)
    # 判不出说话人：退回只带音色的句子（官方 skill `:196`），**不点错人、不并列**
    _v20b = _v20([[{"start": 0.2, "end": 1.0, "text": "你来了", "lang": "zh"},
                   {"start": 1.2, "end": 2.0, "text": "我来了", "lang": "zh"}]])
    check("2.0 判不出说话人：只带音色，不点错人",
          "使用@音频1的音色说{你来了}" in _v20b
          and "@图片1中的人物使用@音频1的音色说{你来了}" not in _v20b, True)
    check("2.0 判不出说话人：不并列两个人",
          "中的人物、@" not in _v20b, True)
    # 跨切：两半拼回一句、只一个 `{}`，且沿用前半定下的说话人
    _v20c = _v20([[{"start": 4.2, "end": 5.0, "text": "你来了", "lang": "zh",
                    "speaker": "P1", "part": "start"}],
                  [{"start": 0.0, "end": 0.8, "text": "我一直在等你",
                    "lang": "zh", "speaker": "P1", "part": "end"}]])
    check("2.0 跨切台词拼回一句（不说两遍）",
          _v20c.count("{你来了") == 1
          and "@图片1中的人物使用@音频1的音色说{你来了我一直在等你}" in _v20c, True)

    # 🩸 2026-10-28（第二十二轮覆盖率）：上面三条都是「说话人 = 这次换的人，
    #   且有 `<主体N>` 标签」。另外三条路一条判据都没有 —— 而 `7536fdb5` 那次
    #   「6 个人说的全挂到换上去那张脸」正是从这里漏的：
    #     · 说话人**没被换**（无标签）→ 只能用「@视频1中 + 主语短语」指认；
    #     · 盘点第一段**不是人称词**（是衣服/发型）→ `_head_noun` 空，
    #       必须走 `_feat_phrase` 兜底，否则这句返回空、整段退回同一个 who；
    #     · 说话人 id 在盘点里根本查不到 → 退回整段 who（不瞎编、不并列）。
    print("== 逐句说话人：换的人 / 没换的人 / 描述有没有人称词 ==")
    _sp_ppl = [{"id": "P1", "present": True, "position": "center",
                "desc_zh": "体型偏胖的男子，黑色头发束成发髻，身着深色长袍"},
               {"id": "P2", "present": True, "position": "left",
                "desc_zh": "一位穿红裙的年轻女子"}]
    _sp_one = edit_spec.normalize({"person": True, "person_ids": ["P1"],
                                   "audio": "tts"})
    _sp_dsc = {"P1": {"zh": _sp_ppl[0]["desc_zh"]},
               "P2": {"zh": _sp_ppl[1]["desc_zh"]}}

    def _spk(speaker: str, desc=None) -> str:
        return edit_spec.compile_prompt(
            "volc", _sp_one, model="doubao-seedance-2-0-mini",
            source_people=_sp_ppl, slots=["person"], audio_ref=True,
            desc_by_id=desc or _sp_dsc,
            shot_lines=[[{"text": "你好", "lang": "zh", "speaker": speaker}]])

    check("没被换的人说话 → 「@视频1中 + 主语短语」，不是图里的脸",
          "@视频1中一位穿红裙的年轻女子使用@音频1的音色说{你好}" in _spk("P2"), True)
    # 7536fdb5 的真实盘点：「穿黑色短袖高领上衣，深色短发，…」第一段是**衣服**
    _sp_wear = {"P1": {"zh": _sp_ppl[0]["desc_zh"]},
                "P2": {"zh": "穿黑色短袖高领上衣，深色短发，"
                             "腰间系有带银色方形扣的黑色皮带，穿深色牛仔裤"}}
    _sp_c = _spk("P2", _sp_wear)
    check("第一段是衣服 → `_feat_phrase` 兜底仍能点名（不再全挂到换上去那张脸）",
          "@视频1中深色短发" in _sp_c, True)
    check("兜底时**不把旧衣服**写进指认（换人后衣服会变）",
          "@视频1中穿黑色短袖" in _sp_c, False)
    _sp_d = _spk("P9")
    check("说话人 id 查不到 → 退回整段 who（不瞎编），且绝不并列两个人",
          "@图片1中的人物使用@音频1的音色说{你好}" in _sp_d
          and "中的人物、@" not in _sp_d, True)

    # 🩸 2026-10-28 修的真 bug：`_sd20_speaker_pic` 里拿**槽位下标**（int）去查
    #   `orig_tags`（键是**盘点 id**，str），恒为假 ⇒「已绑标签就继续用同一个标签」
    #   （官方 `:109`/`:119`）从来没生效。后果是同一个人在同一份提示词里有两个名字：
    #   定义句/编辑句写 `<主体2>`，台词句写「@图片1中的人物」。
    _sp_g = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "person_ids": ["P1"],
                                     "audio": "tts"}),
        model="doubao-seedance-2-0-mini", source_people=_sp_ppl,
        frame_people=_sp_ppl, slots=["person"], audio_ref=True,
        desc_by_id=_sp_dsc,
        shot_lines=[[{"text": "你好", "lang": "zh", "speaker": ""}]])
    # 🩸 2026-10-28 再改：**双人画面 + 没点名说话人 = 不知道谁在说**，
    #   这时既不写「@图片1中的人物」（同一个人两个名字），也不写 `<主体2>`
    #   （那是把一句可能是别人说的台词硬派给被换的那位 —— 实测
    #   `2f1f26d8`：两句台词都被写成「<主体2>说{…}」，其中一句其实是另一个人说的）。
    #   按官方 `:594`/skill `:196` 退回**只带音色**的一句，不猜人。
    check("双人画面只换一人、没点名说话人 → 不猜人，只带音色",
          "使用@音频1的音色说{你好}" in _sp_g
          and "<主体2>使用@音频1的音色说{你好}" not in _sp_g, True)
    check("🩸 不再写成「@图片1中的人物说」（同一个人两种指代）",
          "@图片1中的人物使用@音频1" in _sp_g, False)

    # 整段 who（`speaker_ids`，不是逐句）：点名的就是换的人 → 必须沿用 `<主体N>`
    # （官方 `:119`「后续描述持续使用同一标签」），不能半路改叫「@图片N中的人物」。
    print("== 整段说话人（speaker_ids）==")
    _sp_e = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "person_ids": ["P1"],
                                     "speaker_ids": ["P1"], "audio": "tts"}),
        model="doubao-seedance-2-0-mini", source_people=_sp_ppl,
        slots=["person"], audio_ref=True, desc_by_id=_sp_dsc,
        shot_lines=[[{"text": "你好", "lang": "zh", "speaker": ""}]])
    # 🩸 2026-10-28：沿用标签这一点不变，但要是**替换之后**那个标签 ——
    #   同一段前面写着「将其中的<主体2>替换为<主体1>；<主体1>的面部特征参考@图片1」，
    #   开口说话的人已经是 `<主体1>`（官方 `:119` 持续使用同一标签、`:121` 避免冲突）。
    check("整段点名的就是换的人 → 用参考图指代（换完就是那张脸）",
          "@图片1中的人物使用@音频1的音色说{你好}" in _sp_e, True)
    _sp_f = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "person_ids": ["P1"],
                                     "speaker_ids": ["P2"], "audio": "tts"}),
        model="doubao-seedance-2-0-mini", source_people=_sp_ppl,
        slots=["person"], audio_ref=True, desc_by_id=_sp_dsc,
        shot_lines=[[{"text": "你好", "lang": "zh", "speaker": ""}]])
    check("整段点名的是没被换的人 → 「@视频1中 + 主语短语」",
          "@视频1中一位穿红裙的年轻女子使用@音频1的音色说{你好}" in _sp_f, True)

    _s20 = edit_spec.compile_prompt("volc", edit_spec.normalize({"style": "anime"}),
                                    model="doubao-seedance-2-0-mini")
    check("2.0 不换人物不挂双胞胎兜底", "双胞胎" not in _s20, True)

    v_style = edit_spec.compile_prompt("volc", edit_spec.normalize({"style": "anime"}))
    # 🩸 2026-10-27：原来断言「含改成」，那是**跟 2.5 对齐**留下的跨型号搬运
    # （`edit_spec` 的注释自己写着「与 2.5 那一支对齐」）。2.0 官方有这句的写法：
    # `sd20-guide:713`「**整体风格为** 3D 赛博朋克科幻动画风格」。
    check("风格句用官方写法「整体风格为」", "整体风格为" in v_style, True)
    # 范围闭环里本来就带「不参与替换或删除」，这里验的是**指令动词**没跑出来
    check("只改风格不出现「替换为」", "替换为" not in v_style, True)
    # 🩸 2026-10-23：换风格要写成**具体风格锚定词**，不能只写媒介名 ——
    # 官方 `seedance-20-guide.md:354`「加入明确的风格约束词，例如'2D日漫风格'」、
    # `sd2-pe:163`「风格锚定（动漫 / 非写实场景必挂）」。
    check("风格写成官方锚定词", "2D日漫风格" in v_style, True)

    keep_off = edit_spec.normalize({
        "person": True, "person_desc": "女孩",
        "keep": {k: False for k in edit_spec.KEEP_LABELS},
    })
    _ko = edit_spec.compile_prompt("volc", keep_off)
    # 同上：保留句现在是「保留原视频…」句式，旧字符串判不出真假。
    check("保什么全关就不写保留句", "保留原视频" not in _ko, True)

    keep_part = edit_spec.normalize({"person": True, "keep": {"camera": False}})
    kp = edit_spec.compile_prompt("volc", keep_part)
    check("关掉运镜后不再要求保运镜", "运镜" not in kp, True)
    # 🩸 2026-10-28：官方「单点编辑」原句里动作/位置/互动是一个开关管三样，
    #   写出来是「保留原视频动作、位置、互动…」，没有「人物动作」这个词。
    check("没关的动作仍在保留句里", "动作" in kp, True)
    # 🩸 2026-10-23 回源：2.0 编辑视频公式（指南 :31-40）里没有音频参考这一项，
    # 口型是原片表演的一部分，靠同篇 :33「未提及的部分，默认保持不变」。
    # 🩸 2026-10-26：**不写「表情」**。官方两处编辑示例（`sd20-guide:941` /
    # `sd2-pe:126`）的保留句逐字是「动作和运镜不变」；「表情」在 2.0 官方
    # 没有一处是"要保持"的对象。换人要改脸，写"保持表情"等于让模型别动这张脸。
    check("2.0 不写口型要求", "口型" not in kp, True)
    check("保留句按官方只写动作，不写表情", "表情" not in kp, True)
    kp_orig = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "audio": "original"}))
    check("保留原声也不写表情", "表情" not in kp_orig, True)
    check("保留原声不写口型要求", "口型" not in kp_orig, True)

    # 火山侧同一条规则：只在真传了音频时写 @音频1（官方 2.5 skill：
    # `@音频1用于<角色或声音类型>的<音色、台词…>`）
    # 🩸 2026-10-23 回源更正：2.0 编辑任务**也收参考音频** ——
    #   `volc-api:35`「参考音频（0-3 个）…支持…编辑视频」；
    #   `sd20.md:550`「您可以提供待编辑的视频、参考图片或音频」。
    # 以前这条判据写的是"2.0 不写 @音频1"，依据是只看推荐句式、没看能力说明。
    v_p = edit_spec.normalize({"person": True, "audio": "tts"})
    v_aon = edit_spec.compile_prompt("volc", v_p, audio_ref=True)  # 默认 = 2.0
    v_aoff = edit_spec.compile_prompt("volc", v_p)                 # 默认 = 2.0
    check("2.0 不传音频就不写 @音频1", "@音频1" in v_aoff, False)
    check("2.0 传了音频才写 @音频1", "@音频1" in v_aon, True)
    # 2.0 组合任务句式（`seedance-20-guide.md:65`）：
    # 「参考<…>的[参考维度]，严格编辑<视频X>，[具体编辑内容]」
    check("2.0 按组合任务句式起头（参考@音频1中的音色）",
          (lambda t: "参考@音频1中的音色" in t and t.index("参考@音频1中的音色") < t.index("严格编辑@视频1"))(v_aon), True)
    # 🩸 2026-10-25（D11 ③）：口型句**只在能唯一点名说话人时**写。
    #   · 2.0 官方全文没有"口型与音频逐字同步"这种句子（`seedance-20-guide.md`
    #     grep 0 处）；官方让口型跟台词走的办法是**逐句点名说话人**（`:605`）；
    #   · 判不出人时以前写成「@图片1中的人物、@图片3中的人物…说」——把两个
    #     不同的人并成一个说话主体，官方没有任何一处这么写（`:109/:605/:594`）。
    # 这一条是**单人**（只勾了 person、没有第二个人）→ 没有歧义，口型句照写
    # 🩸 2026-10-26：2.0 官方四份文件 grep「口型」**0 次** ⇒ 2.0 一律不写口型句。
    check("2.0 单人也不写口型句（官方 0 处）",
          "口型与@音频1逐字同步" in v_aon, False)
    _two_u = edit_spec.normalize({"person": True, "person2": True, "audio": "tts",
                                  "person_ids": ["P1", "P2"], "speaker_ids": []})
    v_two_u = edit_spec.compile_prompt(
        "volc", _two_u, audio_ref=True,
        slots=["person", "person2"],
        shot_lines=[[{"text": "你好", "lang": "zh", "speaker": ""}]])
    check("2.0 判不出说话人 → 台词只写音色（官方 :531）",
          "使用@音频1的音色说{你好}" in v_two_u, True)
    check("2.0 判不出说话人 → 不并列两个人", "中的人物、@" in v_two_u, False)
    check("2.0 双人判不出说话人 → 不写口型句",
          "口型与@音频1逐字同步" in v_two_u, False)
    _two_k = edit_spec.normalize({"person": True, "person2": True, "audio": "tts",
                                  "person_ids": ["P2", "P1"], "speaker_ids": ["P2"]})
    v_two_k = edit_spec.compile_prompt(
        "volc", _two_k, audio_ref=True,
        slots=["person", "person2"],
        shot_lines=[[{"text": "你好", "lang": "zh", "speaker": ""}]])
    check("2.0 点名说话人 → 也不加口型句",
          "口型与@音频1逐字同步" in v_two_k, False)
    # 🩸 2026-10-26 18:xx：标签只从**原片侧**定义来；这条用例没有盘点
    # （`source_people` 为空）⇒ 没有标签 ⇒ 说话人用「@图片N中的人物」点名
    # （官方 `:17` 图号 + 名词隔断）。有盘点时走 `<主体N>`（见生产形状那段）。
    check("2.0 点名说话人 → 无盘点时用图内对象点名",
          "@图片1中的人物使用@音频1的音色说{你好}" in v_two_k, True)

    # 官方两个 skill 在"兜底包"上口径相反：
    #   sd2-pe  强制约束：最终输出必须包含稳定包 + 水印/Logo 兜底
    #   sd25-pe 原则 8：不得自动添加用户未要求的画质包/稳定包/水印/Logo/字幕
    v20 = edit_spec.compile_prompt("volc", p, model="doubao-seedance-2-0-260128")
    check("2.0 挂稳定包+水印兜底", "不要生成水印" in v20, True)
    check("2.0 兜底句在最后", v20.rstrip().endswith("Logo"), True)

    # 🩸 字幕兜底（sd2-pe:160「**非文字生成任务必挂**」）
    # 2026-10-23：画面内文字能力下线后，我们的任务**全部**是非文字生成任务，
    # 所以字幕兜底恒挂 —— 原来那条"有画面文字时不挂"的成对探针随之作废。
    check("2.0 挂字幕兜底", "保持无字幕，避免生成任何文字或字幕" in v20, True)

    print("== 火山 2.0 编辑句式 ==")
    # 2.0：sd2-pe「严格编辑 @视频N，将其中的<原特征>修改为<新特征>」
    check("2.0 用「严格编辑@视频1」开头", "严格编辑@视频1，" in v20, True)
    # 创建任务 API「视频编辑」硬要求：提示词里至少要有一个编辑意图词
    check("2.0 含编辑意图词",
          any(k in v20 for k in ("编辑视频", "增加", "加上", "删除", "去掉",
                                 "修改", "替换", "改成")), True)
    check("2.0 不会出现连写句号", "。。" in v20, False)

    print("== 补充说明顺序 ==")
    ep = edit_spec.compile_prompt("volc", common.ex)
    # 🩸 2026-10-28：这里原来找的是「保持@视频1」—— 那是淘汰掉的旧写法，
    #   只有"编译时不传 model"才会出现（真实出片一定带 model）。改成找现行写法。
    check("补充说明在保留句之前",
          ep.index("画面更亮一点") < ep.index("保留原视频"), True)

    print("== 一个人一张图（2026-10-26，台账 D48）==")
    # 🩸 以前这里断言「有大头照时追加全身照」，那是把官方 `sd20-guide:305`
    # 「人脸参考**不准确**」这一**问题章节**的补救增强当成了默认配置。
    # 回原文逐句复核：`sd2-pe:66`「角色图 1–2」= 一张合规；`sd20-guide:222`
    # 官方实战案例就是「@图片 1：女主半身照」一张打全片；`sd20-guide:414`
    # 「人物参考图优先使用单人独立照片」。⇒ 派生槽连参数一起删除。
    check("默认只发一张人物图", edit_spec.ref_order(only_face), [("person", "file")])
    check("人物素材 ID 也只有一张",
          edit_spec.ref_order(only_face, person_asset="asset://x"),
          [("person", "asset:asset://x")])
    one_p = edit_spec.compile_prompt("volc", only_face)
    # 🩸 2026-10-23：这句「@图片N是替换后人物的唯一身份来源…」出处是第三方
    # ReplicaPilot，官方原话不是这个写法 → 断言"不许回来"。
    check("不写第三方来源的身份锁句", "唯一身份来源" not in one_p, True)
    check("面部特征按官方句子写了", "参考@图片1中人物的面部特征和妆造" in one_p, True)
    # 🩸 2026-10-30：面部与妆造现在是**同一句参考句里的两个维度**
    #   （「参考@图片1中人物的面部特征和妆造」），不再拆成「…；妆造参考@图片1」。
    check("妆造也指同一张（官方只给妆造，没第二张就指回图片1）",
          "和妆造" in one_p and "@图片2" not in one_p, True)
    check("不写「体型」（官方只给妆造，加了会改景别）", "体型以@" not in one_p, True)
    check("不会冒出图里没有的 @图片2", "@图片2" in one_p, False)

    print("== 参考图外观描述（2.0 单目标不写主体定义）==")
    # 🩸 2026-10-26 21:xx 再改判（主人：「还是换不上人脸啊！衣服是换了 ——
    # 是否只换一个人的时候不需要主体？」）。两次真机都证明：**一换一时，
    # 主体定义块是负资产**——
    #   · 18:21 那条把原片 3 个人的衣服写成 `<主体2/3/4>` → 衣服换、脸不换（p90 0.297）；
    #   · 21:0x 那条再给参考图加 `<主体1>` 定义 → 仍然衣服换、脸不换。
    # 而以前跑成功过的那几条提示词都**没有** `<主体N>`（官方 `:88/:95` 的定义是给
    # **多主体**消歧用的，官方 `:121` 又要求"描述尽量简洁，避免冗余"）。
    # ⇒ 单目标一律不发；指认退回官方 `:153` 的方位 + `:95` 的发型/配饰，
    #   **服装分句不进宾语**（写衣服 → 模型去改衣服）。
    look = {"zh": "长黑发、蓝色开衫、细银项链",
            "en": "long dark hair, a blue cardigan, a thin silver necklace"}
    p_no = edit_spec.compile_prompt("volc", only_face)
    p_yes = edit_spec.compile_prompt("volc", only_face, subject_look=look)
    check("单目标不写 <主体N> 定义", "定义为<主体" not in p_yes, True)
    check("参考图描述不再改变 2.0 提示词", p_yes == p_no, True)
    check("替换宾语是图内对象（sd20-guide:126）",
          "替换为@图片1中的人物" in p_yes, True)
    check("职责句保留面部与妆造", "参考@图片1中人物的面部特征和妆造" in p_yes, True)

    print("== 换服装 ==")
    wd = edit_spec.normalize({"wardrobe": True, "wardrobe_desc": "米色风衣"})
    # 没给服装图：退回文字描述，和海外的产品/场景同一条退路
    # slots=[] = 真实路径里"勾了但没传图"时真正发出去的槽位（一张都没有）
    wd_txt = edit_spec.compile_prompt("volc", wd, slots=[])
    # 官方 `sd20-guide:39` 编辑句式是「将其中的<原特征>**修改为**<新特征>」
    check("没图时用文字描述", "的服装修改为米色风衣" in wd_txt, True)
    check("没图时不写 @图片1", "@图片1" not in wd_txt, True)
    # 给了图：按图换，序号跟着实际发出去的槽位走
    wd_both = edit_spec.normalize({"person": True, "wardrobe": True,
                                   "wardrobe_desc": "米色风衣"})
    slots_wd = [s for s, _ in edit_spec.ref_order(wd_both)]
    check("人物1 服装2", edit_spec.image_index(slots_wd), {"person": 1, "wardrobe": 2})
    wd_volc = edit_spec.compile_prompt("volc", wd_both)
    check("火山按图换服装", "服装换成@图片2中的服装" in wd_volc, True)

    # 🩸 2026-10-28（当前产出实测，真实盘点 × 全部可勾操作零成本矩阵）：
    #   换装目标和换人名单是**两张表**。勾「换 P1 的人 + 换 P2 的衣服」或
    #   「只换两人衣服（不换人）」时，换装目标不在 `people`（勾选换人的名单）里，
    #   `_per_i` 恒为 None ⇒ 三档指认（方位→特征→人称词）全落空 ⇒ 两个男人
    #   同框就是两句一模一样的「将其中的男性的服装换成…」，模型只能猜谁换哪套。
    _m1 = {"id": "P1", "present": True, "position": "left",
           "desc_zh": "留短黑发、佩戴黑框眼镜、身穿藏蓝外套的男性"}
    _m2 = {"id": "P2", "present": True, "position": "center",
           "desc_zh": "身穿黑色短袖高领上衣、深色长裤的男性"}
    _frame2 = [_m1, _m2]
    _db2 = {x["id"]: {"zh": x["desc_zh"]} for x in _frame2}
    _mix_spec = edit_spec.normalize({
        "person": True, "person_ids": ["P1"], "wardrobe": True,
        "wardrobe_ids": ["P2"], "wardrobe_desc_by_id": {"P2": "黑色皮夹克"}})
    _mix = edit_spec.compile_prompt(
        "volc", _mix_spec, model="seedance-2-0", source_people=[_m1],
        frame_people=_frame2, slots=["person", "wardrobe"], desc_by_id=_db2)
    # 🩸 2026-10-30：特征可分 ⇒ 用**他的特征**指认（不再写方位）。
    # 断言点不变：指认必须唯一落到换装目标身上，不能是泛称。
    check("换装目标不在换人名单里 → 用特征指认",
          "将其中的身穿黑色短袖高领上衣、深色长裤的男性的服装换成" in _mix, True)
    check("换装宾语不许是泛称「男性」",
          "将其中的男性的服装换成" in _mix, False)
    _w2_spec = edit_spec.normalize({
        "wardrobe": True, "wardrobe_ids": ["P1", "P2"],
        "wardrobe_desc_by_id": {"P1": "米色风衣", "P2": "黑色皮夹克"}})
    _w2 = edit_spec.compile_prompt(
        "volc", _w2_spec, model="seedance-2-0", frame_people=_frame2,
        slots=["wardrobe", "wardrobe2"], desc_by_id=_db2)
    check("只换两人衣服：第 1 句按特征指认",
          "将其中的留短黑发、佩戴黑框眼镜的男性的服装换成" in _w2, True)
    check("只换两人衣服：第 2 句按特征指认",
          "将其中的身穿黑色短袖高领上衣、深色长裤的男性的服装换成" in _w2, True)
    check("两个人的换装句不相同（不选人时也能分清谁换哪套）",
          _w2.count("将其中的男性的服装换成"), 0)
    # 同一个病在**逐句说话人**上：只换一个人、另一个人在说话时，说话人以前
    # 退回 `_head_noun` → 「@视频1中男性使用@音频1的音色说{…}」，两个男人同框
    # 谁在说没有唯一解（`sd2-pe:72` 的病灶）。
    _spk_spec = edit_spec.normalize({"person": True, "person_ids": ["P1"],
                                     "audio": "tts"})
    _spk = edit_spec.compile_prompt(
        "volc", _spk_spec, model="seedance-2-0", source_people=[_m1],
        frame_people=_frame2, slots=["person"], desc_by_id=_db2, audio_ref=True,
        shot_lines=[[{"text": "你站住", "lang": "zh", "speaker": "P1"},
                     {"text": "为什么", "lang": "zh", "speaker": "P2"}]])
    check("没被换的说话人用特征指认",
          "@视频1中身穿黑色短袖高领上衣、深色长裤的男性使用@音频1的音色说{为什么}" in _spk,
          True)
    check("说话人不许写成泛称「男性」",
          "@视频1中男性使用@音频1的音色说" in _spk, False)

    print("== 台词语言标签（2.0）==")
    th_lines = [[{"start": 0.2, "end": 1.0, "text": "สวัสดีครับ", "lang": "th"}]]
    v20_th = edit_spec.compile_prompt("volc", only_face, model="seedance-2-0",
                                      slots=["person"], source_people=[p1],
                                      audio_ref=True, shot_cuts=[], shot_lines=th_lines)
    check("2.0：泰语台词写「用泰语说道」", "用泰语说道{สวัสดีครับ}" in v20_th, True)

    print("== 换人提示词结构（2.0）==")
    src_face = {"id": "P1", "desc_zh": "棕色盘发、身穿浅灰长裙的女性",
                "desc_en": "the woman in a grey dress"}
    p20 = edit_spec.compile_prompt("volc", only_face, model="seedance-2-0",
                                   source_person=src_face)
    # 单人画面：不写原片描述（它写的是衣服，会把模型带成"只换衣服"）；
    # 多人画面才需要描述当定位词，见 p9 C2。
    check("单人画面直接用人称换人、不带原片描述",
          "@图片1中的人物" in p20
          and "这句只用来认出是哪一位" not in p20, True)
    # 🩸 2026-10-22 实测（25s 那条）：单人画面把原片人物的外观写进换人句，
    # 模型把「身着…和服」当成修改对象 → 只换衣服不换脸
    # （与原片同人 49/56 帧、与参考图 0/65 帧）。这条判据冻结的就是那一次。
    check("单人画面不写原片外表描述", src_face["desc_zh"] not in p20, True)
    # 🩸 官方有、我们之前漏写的一句（`seedance-20-guide.md:317` / `sd2-pe:139`）：
    #   「<主体1> 的面部特征参考 @图片1（大头照）」
    # 只有一张图时也要写。🩸 2026-10-25：句式从「只写面部特征」改成
    # 「面部特征 + 妆造都指这一张」—— 官方把「妆造」挂在第二张（全身照）上，
    # 没有第二张就**一个字都不写妆造 = 衣服不跟着换**（主人当场问出来的）。
    # 判据仍然守原意：**不许编一个不存在的图号**（只以 @图片1 为准）。
    check("换人句写明面部特征参考哪张图", "参考@图片1中" in p20 and "的面部特征" in p20, True)
    check("只有一张图时妆造也指同一张", "和妆造" in p20, True)
    check("只有一张图时不编不存在的图号", "@图片2" not in p20, True)
    # 🩸 2026-10-23：下面三句出处都是第三方（ReplicaPilot / 旧自造），
    # 两家官方说明书都没有 → 已删除。断言改成"不许回来"。
    check("不写第三方「场景一律取自」", "场景一律取自" not in p20, True)
    check("不写第三方「冲突时以它为准」", "与其他参考冲突时以它为准" not in p20, True)
    check("2.0 不写第三方换人负向", "不要恢复原片人物的脸" not in p20, True)
    # 换场景时不能同时写「场景取自@视频1」
    p_scene = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "scene": True}), model="seedance-2-0")
    check("换场景时不写场景锁", "场景一律取自@视频1" in p_scene, False)

    # 🩸 == 生产形状（2026-10-25 D24/D25 收口）==
    # 生产里 `source_people` 只含**勾选的人**（`video_edit._span_people`），
    # 整个画面要靠 `frame_people` 传。这两个不是一回事：
    # 以前所有多人测试都拿整个盘点当 `source_people`，测的路径生产里根本走不到。
    print("== 生产形状：只勾一部分人 ==")
    _fp1 = {"id": "P1", "present": True, "position": "center",
            "desc_zh": "体型偏胖的男子，黑色头发束成发髻，身着浅青绿色古装"}
    _fp2 = {"id": "P2", "present": True, "position": "center",
            "desc_zh": "年轻女子，黑色长发梳成古装高髻，身着广袖古装"}
    _fp2L = dict(_fp2, position="left")
    _fdesc = {"P1": {"zh": _fp1["desc_zh"]}, "P2": {"zh": _fp2["desc_zh"]}}

    def _prod(frame, picked, slots=("person",)):
        return edit_spec.compile_prompt(
            "volc", edit_spec.normalize({"person": True,
                                         "person_ids": [p["id"] for p in picked]}),
            model="doubao-seedance-2-0-mini", source_people=picked,
            frame_people=frame, desc_by_id=_fdesc, slots=list(slots))

    _p_clash = _prod([_fp1, _fp2], [_fp1])
    # 🩸 2026-10-26 22:xx 改判（见上面 `_p20dup` 那段的实测，台账 §13.13）：
    # 多人画面只换一个 → **只定义被换的那一位**，宾语用标签。
    # 21:xx 那版"一个都不发"是在不知道 15:46/16:20/16:42（标签式）其实换成了
    # 的前提下定的；现在看，标签不是病因，长定义才是。
    # 🩸 2026-10-27（主人：「按 2.0 模型给的输出改」）：判据改回**官方 12 条标准示例**
    # 的形状。官方 `20 双人只换一个` 原文：
    #   「将@图片1中的人物定义为<主体1>，将@视频1中体型偏胖的男子定义为<主体2>。
    #     严格编辑@视频1，将其中的<主体2>替换为<主体1>；
    #     <主体1>的面部特征参考@图片1，妆造参考@图片1」
    # ⇒ 图片侧也定义（零静态特征），编号图片在前、视频在后。
    # 旧断言（"参考图侧走内联、不发假定义"）当时的理由是「没有静态特征 = 违反
    # `:15`/`:95`」—— 但官方自己的标准示例就是零特征定义，那条理由站不住。
    # 🩸 2026-10-30：定义句停用（`_person_tags_20`）⇒ 在场 2 人也一条都不发，
    #   指认由换人句宾语承担（「将其中的<特征>替换为@图片N中的人物」）。
    check("在场 2 人只换 1 个 → 一条 <主体N> 定义都不发",
          "定义为<主体" not in _p_clash, True)
    check("在场 2 人只换 1 个 → 宾语用特征，不把服装写成待改对象",
          "将其中的体型偏胖的男子替换为@图片1中的人物" in _p_clash
          and "古装替换为" not in _p_clash, True)
    check("在场 2 人只换 1 个（方位撞车）→ 不写「画面中央的人物」",
          "画面中央的人物" in _p_clash, False)
    _p_uniq = _prod([_fp1, _fp2L], [_fp1])
    # 🩸 2026-10-27 三档：方位唯一 → 只用方位，也不再叠外观串。
    check("特征可分 → 宾语用特征、不写方位",
          "将其中的体型偏胖的男子替换为@图片1中的人物" in _p_uniq
          and "画面左侧的人物" not in _p_uniq
          and "古装" not in _p_uniq, True)
    check("方位唯一 → 仍然一条定义都不发",
          "定义为<主体" not in _p_uniq, True)
    _p_two = _prod([_fp1, _fp2], [_fp1, _fp2], ("person", "person2"))
    # 🩸 2026-10-27：官方 `20 双人全换` 原文是四条定义（图片 1、2 在前，视频 3、4 在后）。
    check("在场 2 人换 2 个 → 一条 <主体N> 定义都不发",
          "定义为<主体" not in _p_two, True)
    check("在场 2 人换 2 个 → 两句宾语各用各的特征",
          "将其中的体型偏胖的男子替换为@图片1中的人物" in _p_two
          and "将其中的年轻女子替换为@图片2中的人物" in _p_two, True)
    _p_solo = _prod([_fp1], [_fp1])
    check("在场 1 人 → 不出标签", "<主体" not in _p_solo, True)
    # 只勾第 2 个：索引必须跟着勾选走，不能拿盘点第 1 个顶替
    _prod_frame = [_fp1, dict(_fp2, position="right")]
    _p_second = _prod(_prod_frame, [_prod_frame[1]])
    # 🩸 这条断言的意图不变 —— 索引必须跟着勾选走，不许拿盘点第 1 个顶替别人。
    # 指认词按三档走（2026-10-30 方位降兜底：特征可分就用特征）：
    # P2 是「年轻女子」→ 定义句写它，第 1 位那位（体型偏胖的男子）一个字都不该出现。
    check("只勾第 2 个 → 指认指到**第 2 位**（不拿盘点第 1 个顶替）",
          "将其中的年轻女子替换为@图片1中的人物" in _p_second
          and "体型偏胖的男子" not in _p_second, True)

    # 🩸 尺子自证（A1，成对）：已知好样本不响、已知坏样本要响。
    # 判据改了机制（从"必须有标签"改成"两种指认方式都认"）就必须重证一次，
    # 否则新判据可能对任何输入都不响（对空对象报绿）。
    from ruler_sd20 import _sd_invariants  # noqa: E402
    _fr = [_fp1, _fp2]
    _pk = [_fp1]
    _base = "保持@视频1的人物动作、运镜和机位、剪辑节奏和时长、背景环境不变。"
    check("A1 好样本（定义过的标签）→ 不响",
          [x for x in _sd_invariants(
              "将@视频1中体型偏胖的男子定义为<主体1>。严格编辑@视频1，"
              "将其中的<主体1>替换为@图片1中的人物。" + _base, _fr, _pk)
           if x.startswith("A1")], [])
    check("A1 坏样本（引用了没定义的标签）→ 响",
          bool([x for x in _sd_invariants(
              "严格编辑@视频1，将其中的<主体1>替换为@图片1中的人物。" + _base,
              _fr, _pk) if x.startswith("A1")]), True)
    check("A1 坏样本（裸「人物」）→ 响",
          bool([x for x in _sd_invariants(
              "严格编辑@视频1，将其中的人物替换为@图片1中的人物。" + _base,
              _fr, _pk) if x.startswith("A1")]), True)
    check("A1 产品句不误伤（这一刀没选人 → 不归 A1 管）",
          [x for x in _sd_invariants(
              "严格编辑@视频1，将其中的香水替换为@图片1中的面霜。" + _base,
              _fr, []) if x.startswith("A1")], [])

    # 🩸 A6（成对）：替换宾语不许是空的。
    # 2026-10-26 20:01 / 20:07 两次真机出片发出去的就是
    # 「严格编辑@视频1，将其中的**替换为**@图片1中的人物」——盘点描述以服装
    # 开头时 `_head_noun` 返回空串，编译器把残句直接发了出去。
    # A1 的正则要求宾语至少一个字，**空宾语根本匹配不上**，只看 A1 抓不到。
    check("A6 坏样本（宾语是空的）→ 响",
          bool([x for x in _sd_invariants(
              "严格编辑@视频1，将其中的替换为@图片1中的人物。" + _base,
              _fr, _pk) if x.startswith("A6")]), True)
    check("A6 好样本（兜底成「人物」）→ 不响 A6",
          [x for x in _sd_invariants(
              "严格编辑@视频1，将其中的人物替换为@图片1中的人物。" + _base,
              _fr, _pk) if x.startswith("A6")], [])

    # 🩸 编译级复现（20:01 / 20:07 的真机形状）：盘点描述**以服装开头**，
    # 首个逗号前没有人称短语 → `_head_noun` 返回空串。同方位还有第二个人，
    # 所以方位也不能用。这条必须落到底线兜底，不能拼出残句。
    _cloth = {"id": "P1", "present": True, "position": "center",
              "desc_zh": "穿橙色连帽拉链外套，左胸带有白色标识，短发，"
                         "一侧脸颊与颈部有骷髅、玫瑰图案纹身，左耳佩戴黑色耳钉，"
                         "下巴处有一小撮灰白色胡须"}
    _other = {"id": "P2", "present": True, "position": "center",
              "desc_zh": "穿黑色短袖上衣，寸头发型，耳部佩戴耳钉"}
    _p = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "person_ids": ["P1"]}),
        model="doubao-seedance-2-0-mini-260615",
        source_people=[_cloth], slots=["person"],
        frame_people=[_cloth, _other])
    check("服装开头的盘点描述 → 宾语不许为空", "将其中的替换为" in _p, False)
    # 🩸 2026-10-27 改期望（人工审读真实盘点 `7536fdb5` 抓到的）：
    # 以前这里期望**落到底线兜底**「将其中的人物替换为…」—— 因为 `_feat_phrase`
    # 要求描述以「的男性/的女子」收尾，而这种盘点只写外观、没写人称词，
    # 于是整段返回空。后果：6 人素材勾全 6 个，有 2 个人被静默跳过，
    # **@图片1 一次没出现**（图白传），前端没有任何提示。
    # 现在缺人称词时补通用中心词「人物」，特征保住 ⇒ 指认唯一，比裸「人物」好。
    # ⚠️ 判据别写死「必须用 `<主体N>`」：单人不发标签体系（`_sd20_person_tags`
    # 只给多人场景定义），走的是「将其中的<特征>替换为…」。两种都算指认到位，
    # 只有落回裸「人物」才算坏。第一版写成 `"定义为<主体" in _p`，功能没问题却判红。
    check("服装开头的盘点描述 → 用非服装特征指认（不落裸「人物」）",
          "将其中的人物替换为" not in _p
          and "左胸带有白色标识" in _p, True)
    # 同时守住 2026-10-24 三版 + 10-26 18:21 两次真机的结论：
    # 服装分句写进指认短语 → 模型注意力跑到"改衣服"上（衣服换了、脸没换）。
    check("服装开头的盘点描述 → 指认短语里不含服装分句",
          "橙色连帽拉链外套" not in _p, True)

    # 🩸 出片前的可指认闸 —— D27（2026-10-25）：**只勾一个人也要判**。
    # 以前 `n <= 1` 直接放行，但"勾 1 个"不等于"画面里只有 1 个"：
    # 两个人同框、只换其中一个时，提示词仍要说出换的是哪一位。
    # 盘点对这个人既没方位（或方位撞车）又没描述 → 只能写「将其中的**人物**
    # 替换为…」，画面里两个人，这句谁也没指认（`ruler_sd20 --sweep` 第 ⑧ 组抓到）。
    print("== 可指认闸：只勾一个人（2.0 的闸，见 D27）==")
    from app.services import video_edit  # noqa: E402

    def _pp(i, pos="", zh="", ap=None):
        return {"id": f"P{i}", "present": True, "position": pos,
                "desc_zh": zh,
                "appearances": ap or [{"start": 0.0, "end": 5.0}]}

    def _gate(people, ids):
        # 🩸 2026-10-29（D70）：生产里由适配器把编译器那把尺传进闸
        #   （`models/volc20.py:_gate`）。这里不传就量不到生产行为。
        from app.services.models.volc20_compile import (
            sd20_locator, sd20_multi_locator)
        try:
            video_edit.require_identifiable_volc20(
                {"people": people}, ["person"], ids,
                locator=sd20_locator, locator_multi=sd20_multi_locator)
            return "pass"
        except video_edit.EditError:
            return "block"

    check("两人同框·都没描述·方位撞车 → 拦住",
          _gate([_pp(1, "center"), _pp(2, "center")], ["P1"]), "block")
    check("同上但描述不同 → 放行",
          _gate([_pp(1, "center", "体型偏胖的男子"),
                 _pp(2, "center", "年轻女子")], ["P1"]), "pass")
    # 🩸 2026-10-27 改判（主人：「我们要换的人他有可能不在中间，有可能不在左边」）：
    # 方位**是盘点逐条看画面给的**，唯一时就是官方 `:153` 的定位手段 ——
    # 编译器写得出「画面左侧的人物」，闸就放行。闸只做一件事：
    # 判编译器**到底写不写得出能区分的一句**，不能比编译器更严（那会拦掉好样本）。
    check("都没描述·方位唯一 → 放行（方位 = 官方 :153 的定位）",
          _gate([_pp(1, "left"), _pp(2, "right")], ["P1"]), "pass")
    check("两人从不同框（单人画面）→ 放行",
          _gate([_pp(1, "center", ap=[{"start": 0.0, "end": 2.0}]),
                 _pp(2, "center", ap=[{"start": 3.0, "end": 5.0}])], ["P1"]),
          "pass")
    check("勾的是第 2 个 → 按勾选判 P2（不是盘点第 1 个）",
          _gate([_pp(1, "center", "体型偏胖的男子"),
                 _pp(2, "center")], ["P2"]), "block")
    check("老盘点没有 appearances → 不因缺数据拦住",
          _gate([{"id": "P1", "position": "center", "desc_zh": ""},
                 {"id": "P2", "position": "center", "desc_zh": ""}], ["P1"]),
          "pass")

    # ------------------------------------------------------------------
    # 🩸 2026-10-27：`coverage` 报 `volc20_compile.py` 87%，缺的 19 条里有 7 条是
    #   **能走到的 2.0 分支**（三条 pending、几条 `_sd20_line` 支路），实测行为
    #   都对，但**没有任何判据守着** —— 改一次就可能悄悄坏掉。补上。
    from app.services.models import volc20_compile as V20C

    # `_sd20_line`（volc20_compile.py:102-132）的四条支路
    check("台词为空 → 不产出句子（不许留一个空 {}）",
          V20C._sd20_line("", "有人", "zh", False), "")
    check("没认出说话人·无音轨 → 裸台词（官方 :298 的 {} 写法）",
          V20C._sd20_line("她说好", "", "zh", False), "{她说好}")
    check("没认出说话人·要音色 → 只带音色的一句（官方 :531 句式）",
          V20C._sd20_line("她说好", "", "zh", True),
          "使用@音频1的音色说{她说好}")
    check("音色 + 小语种并排 → 两个官方句式用逗号断开（不许糊成「音色用日语说道」）",
          V20C._sd20_line("她说好", "", "ja", True),
          "使用@音频1的音色，用日语说道{她说好}")
    check("有说话人 + 无音轨 + 小语种 → 只写语种不写音色",
          V20C._sd20_line("她说好", "年轻女子", "ja", False),
          "年轻女子用日语说道{她说好}")

    # `_sd20_lines`（:133-186）的跨切台词三条路
    def _ln(t, part="", spk=""):
        d = {"text": t, "lang": "zh"}
        if part:
            d["part"] = part
        if spk:
            d["speaker"] = spk
        return d

    check("跨切台词 start+end → 拼回**一句**（拆成两个 {} 等于让人说两遍）",
          V20C._sd20_lines([[_ln("前半", "start"), _ln("后半", "end")]], "", False),
          ["{前半后半}"])
    check("只有 start 的下一句是普通句 → 前半先写出来，不许吞",
          V20C._sd20_lines([[_ln("前半", "start"), _ln("另外一句")]], "", False),
          ["{前半}", "{另外一句}"])
    check("全片最后一句只有 start（跨到片尾）→ 收尾也要写出来",
          V20C._sd20_lines([[_ln("正常一句"), _ln("只有前半", "start")]], "", False),
          ["{正常一句}", "{只有前半}"])

    # ------------------------------------------------------------------
    # 🩸 2026-10-27：换装「只写文字不传图」这条路（主人：「没图片的时候我是不是
    #   可以告诉他换颜色？那是不是需要输入」）。前端补了逐人输入框，后端闸门
    #   改成**逐个查**「有图 / 有描述」—— 以前只查第一个槽位，第 2、3 个人
    #   没图没描述会被静默跳过（图白传，用户看不出来）。这里锁住它。
    MM = "doubao-seedance-2-0-mini-260615"

    def _missing(chg, refs):
        sp = edit_spec.normalize(chg)
        # 🩸 2026-10-28：换装「逐个查」现在是**能力位**，不再由型号名判断
        #   （共用层认型号 = 厂商耦合，分离门会红）。2.0 的 caps 里是 True，
        #   生产入口会自己带上；这里是直接调函数，所以按 caps 取值传进去。
        return edit_spec.missing_material(
            sp, refs=refs, person_asset="", style_video=False,
            audio_files={}, model=MM,
            wardrobe_per_person=models.adapter_for(model=MM)
                                 .caps.wardrobe_check_per_person)

    _P1 = {"id": "P1", "present": True, "position": "center", "desc_zh": "男子"}
    _P2 = {"id": "P2", "present": True, "position": "right", "desc_zh": "女子"}
    check("换装·单人·没图也没描述 → 拦住",
          bool(_missing({"wardrobe": True, "wardrobe_ids": ["P1"]}, [])), True)
    check("换装·单人·没图但写了「红色连衣裙」→ 放行",
          _missing({"wardrobe": True, "wardrobe_ids": ["P1"],
                    "wardrobe_desc": "红色连衣裙"}, []), None)
    check("换装·两人·各写一套·都不传图 → 放行",
          _missing({"wardrobe": True, "wardrobe_ids": ["P1", "P2"],
                    "wardrobe_desc_by_id": {"P1": "米色风衣",
                                            "P2": "黑色皮夹克"}}, []), None)
    check("换装·两人·第 1 个传图、第 2 个只写文字 → 放行",
          _missing({"wardrobe": True, "wardrobe_ids": ["P1", "P2"],
                    "wardrobe_desc_by_id": {"P2": "黑色皮夹克"}}, ["wardrobe"]), None)
    check("换装·两人·第 1 个传图、第 2 个什么都没有 → 拦住（不许静默跳过）",
          bool(_missing({"wardrobe": True, "wardrobe_ids": ["P1", "P2"]},
                        ["wardrobe"])), True)
    check("换装·两人·各传一张图 → 放行",
          _missing({"wardrobe": True, "wardrobe_ids": ["P1", "P2"]},
                   ["wardrobe", "wardrobe2"]), None)

    # 签名：逐人服装描述是"会改变成片"的字段，必须进改动签名，
    # 否则「两人换了不同衣服」会和上次判成一样 → 直接复用旧片、白改一场。
    _sig = edit_spec.sig_change({"person": True, "wardrobe": True,
                                 "wardrobe_desc_by_id": {"P1": "米色风衣"}})
    check("逐人服装描述进了改动签名",
          _sig.get("wardrobe_desc_by_id") == {"P1": "米色风衣"}, True)
    check("老记录没有这个键 → 不因它失配（空值不进签名）",
          "wardrobe_desc_by_id" not in edit_spec.sig_change({"person": True}), True)

    # ------------------------------------------------------------------
    # 🩸 2026-10-27：`_ref_feat`（参考图里那个人的特征短语）没有判据守着。
    #   官方 `sd20-guide:95` 要「2–3 个静态特征」；`:107` 要求之后全程用同一标签。
    #   两件事在这里落地：① 只取前 3 个特征（多了是冗余，`:121`）；
    #   ② 服饰印字的引号必须摘掉 —— 2.0 里引号是台词/文字句法（`:298`），
    #   带引号会被读成"要生成这段文字"，而同一份指南要求「保持无字幕」。
    _rf = _cmp20._ref_feat_20(
        "短款黑色直发，圆润脸型，胸前带有同色压印“HAIRVERS”字样的黑色圆领短袖T恤")
    check("参考图特征：取前 3 个", _rf.count("、") == 2, True)
    check("参考图特征：服饰印字不带引号（防被判成台词）",
          "“" not in _rf and "”" not in _rf and "HAIRVERS" in _rf, True)
    check("参考图特征：末尾补称人词（写成名词短语，不裸接动词）",
          _rf.endswith("的人"), True)
    check("空描述 → 空串（不编造）", _cmp20._ref_feat_20(""), "")

    # ------------------------------------------------------------------
    # 🩸 2026-10-27：`subject_gate`（人数闸）的 warn/block 两支没有判据守着。
    #   2.0 官方 `sd20-guide:467`「>4 人稳定性下降」→ 2.0 的上下限都是 4。
    #   换 5 个人时不能硬发（出了也是残片），也不能只说"不行"（用户不知道怎么办）。
    def _gate_spec(n: int) -> dict:
        return edit_spec.normalize(
            {"person": True, "person_ids": [f"P{i}" for i in range(1, n + 1)]})

    _G4 = edit_spec.subject_gate(_gate_spec(4), model="doubao-seedance-2-0-mini-260615")
    _G5 = edit_spec.subject_gate(_gate_spec(5), model="doubao-seedance-2-0-mini-260615")
    check("换 4 人（2.0 上限内）→ 放行", _G4["level"], "ok")
    check("换 5 人（超 2.0 上限）→ 拦住", _G5["level"], "block")
    check("拦住时给出可执行的下一步（建议型号或分几条出）",
          bool(_G5["suggest_model"]) or "分几条" in _G5["message"], True)
    check("拦住时消息不为空（不许静默失败）", bool(_G5["message"].strip()), True)
    check("人数闸读的是该型号自己的上下限（不写死）",
          (_G4["stable"], _G4["max"]), (4, 4))

    # ------------------------------------------------------------------
    # 🩸 缺素材闸的其余槽位（换产品 / 换背景 / 风格图 / 风格视频 / 音频替换）。
    #   用户勾了但没给东西时，提示词会**静默忽略**这一项 —— 出完片才发现没变。
    check("换产品·没图也没描述 → 拦住",
          bool(_missing({"product": True}, [])), True)
    check("换产品·没图但写了「面霜」→ 放行",
          _missing({"product": True, "product_desc": "面霜"}, []), None)
    check("换产品·有图 → 放行",
          _missing({"product": True}, ["product"]), None)
    check("换背景·没图也没描述 → 拦住",
          bool(_missing({"scene": True}, [])), True)
    check("换背景·没图但写了「海边」→ 放行",
          _missing({"scene": True, "scene_desc": "海边"}, []), None)
    check("勾了风格参考图却没上传 → 拦住（风格没有「写一句话代替」的退路）",
          bool(_missing({"style_ref": True}, [])), True)
    check("勾了风格参考图且传了图 → 放行",
          _missing({"style_ref": True}, ["style_ref"]), None)
    _sp_sv = edit_spec.normalize({"style_video": True})
    check("勾了风格参考视频却没上传 → 拦住",
          bool(edit_spec.missing_material(_sp_sv, refs=[], person_asset="",
                                          style_video=False, audio_files={},
                                          model=MM)), True)

    # ------------------------------------------------------------------
    # 「勾了但没给素材」的另外三条（换人 / 换背景音乐 / 加音效）
    _person_lack = _missing({"person": True}, [])
    check("换人·没图也没 asset → 拦住", bool(_person_lack), True)
    check("换人拦截要说清后果（不是只写「缺素材」）",
          "原样再画一遍" in str(_person_lack), True)
    _sp_bgm = edit_spec.normalize({"bgm": "replace"})
    check("换成我上传的背景音乐·没文件 → 拦住",
          bool(edit_spec.missing_material(_sp_bgm, refs=[], person_asset="",
                                          style_video=False, audio_files={},
                                          model=MM)), True)
    _sp_sfx = edit_spec.normalize({"sfx": "add"})
    check("再加一段音效·没文件 → 拦住",
          bool(edit_spec.missing_material(_sp_sfx, refs=[], person_asset="",
                                          style_video=False, audio_files={},
                                          model=MM)), True)
    check("换背景音乐·给了文件 → 放行",
          edit_spec.missing_material(_sp_bgm, refs=[], person_asset="",
                                     style_video=False,
                                     audio_files={"bgm": "x.mp3"},
                                     model=MM), None)

    # ------------------------------------------------------------------
    # 🩸 火山没配好时**说哪一句**（2026-10-28 覆盖率补课）。
    #   `volc20.py:44` 的 docstring 记着这个 bug：以前写成两个 `if not _volc_ready()`，
    #   第一个永远先命中 ⇒ 缺 OSS 的用户看到「请设置 VT_ARK_API_KEY」，照着改改不对。
    #   这是**用户照着做**的文案，不是内部日志 —— 必须成对验两个分支。
    print("== 火山没配好时的报错（用户要能照着改对）==")
    import dataclasses

    import app.core.config as _cfg
    from app.services import oss as _oss
    from app.services.models import volc20 as _v20

    _old_cfg = _cfg.settings
    try:
        _cfg.settings = dataclasses.replace(
            _old_cfg, ark_api_key="", public_base_url="")
        _e1 = _v20._ready_error()
        check("没配 key → 明说缺 VT_ARK_API_KEY",
              "VT_ARK_API_KEY" in _e1, True)
        check("缺 key 时不提 OSS（别让人去配错东西）",
              "VT_OSS_ACCESS_KEY_ID" in _e1, False)

        _ok_oss = _oss.available
        _oss.available = lambda: False
        try:
            _cfg.settings = dataclasses.replace(
                _old_cfg, ark_api_key="sk-test", public_base_url="")
            _e2 = _v20._ready_error()
        finally:
            _oss.available = _ok_oss
        check("key 有了、OSS 没配 → 明说缺 OSS（不是再说一遍配 key）",
              "VT_OSS_ACCESS_KEY_ID" in _e2 and "VT_ARK_API_KEY" not in _e2, True)

        _cfg.settings = dataclasses.replace(
            _old_cfg, ark_api_key="sk-test", public_base_url="http://x")
        check("两项都配好 → 返回空串（成对的上半）", _v20._ready_error(), "")
    finally:
        _cfg.settings = _old_cfg

    # 🩸 报错翻译是真的转发到适配器了吗（2026-10-28）。
    #   `volc20._error_hint` 只是转发 `video_edit._volc_hint`，但**转发链断掉**
    #   用户看到的就是原始英文错误码 —— 这类"中间加一层忘了接"在本项目出过。
    print("== 报错翻译：适配器这一层真的接上了 ==")
    check("生成结果被判版权 → 提示说「更换输入内容」（不是参考片）",
          "更换输入内容" in _v20._error_hint(
              "OutputVideoSensitiveContentDetected.PolicyViolation"), True)
    check("参考片被判版权 → 提示里给换通道的办法",
          "MiniMax" in _v20._error_hint(
              "InputVideoSensitiveContentDetected.PolicyViolation"), True)
    check("真人脸被拦 → 提示里给 asset:// 的做法",
          "asset://" in _v20._error_hint("PrivacyInformation"), True)
    check("不认识的错误 → 不瞎编（空串，界面显示原文）",
          _v20._error_hint("some random error"), "")

    # 🩸 延长提交的参数透传（2026-10-28）。延长链出过「残句」那种 bug
    #   （`r25_dangling_generate`），但**发出去的参数**从没验过。用假 `ark` 接住。
    print("== 延长提交：发出去的参数 ==")
    from app.services import ark as _ark
    from app.services import video_edit as _ve_x

    _got: dict = {}
    _old_ex, _old_pu = _ark.extend_video, _ve_x._public_url
    try:
        _ark.extend_video = lambda p, **kw: _got.update(prompt=p, **kw)
        _ve_x._public_url = lambda p, cid: f"https://x/{Path(p).name}"
        _v20._extend_submit(
            prompt="向后延长@视频1，生成一个人走进来",
            ref_src=Path("ref.mp4"), seg=Path("out.mp4"),
            model="doubao-seedance-2-0-mini-260615", resolution="720p",
            seconds=5, with_audio=True, cid="c1")
    finally:
        _ark.extend_video, _ve_x._public_url = _old_ex, _old_pu
    check("提示词原样发出（不丢、不改）",
          _got.get("prompt"), "向后延长@视频1，生成一个人走进来")
    check("原片走公网 URL（火山只收 URL，不收本地路径）",
          str(_got.get("video_url") or "").startswith("https://"), True)
    check("型号/清晰度/时长原样透传",
          (_got.get("model"), _got.get("resolution"), _got.get("duration")),
          ("doubao-seedance-2-0-mini-260615", "720p", 5))
    check("with_audio → generate_audio=True（延长也要出声，不然口型对不上）",
          _got.get("generate_audio"), True)

    # 🩸 素材入库失败**不能把整段带崩**（2026-10-28）。入库是为了绕开火山对
    #   真人人脸的逐次拦截（400 PrivacyInformation）；入库服务抖一下就把整段
    #   出片打断，代价是一个已付过费的方案白算。兜底行为：退回直传 + 记录原因。
    print("== 素材入库异常：退回直传，不中断出片 ==")
    from app.services import ark_ingest as _ing
    from app.services import video_edit as _ve_y

    _sent = {}
    _old_pu2, _old_wr = _ve_y._public_url, _ve_y._write_request
    _old_av, _old_pv = _ing.available, _ing.prepare_video
    _old_ev = _ark.edit_video
    try:
        _ve_y._public_url = lambda p, cid: f"https://x/{Path(p).name}"
        _ve_y._write_request = lambda *a, **k: None
        _ing.available = lambda: True

        def _boom(*a, **k):
            raise RuntimeError("ingest down")
        _ing.prepare_video = _boom
        _ark.edit_video = lambda p, **kw: _sent.update(prompt=p, **kw)
        _ingest: dict = {}
        _sv, _sr, _si = _v20._submit({
            "seg": Path("seg.mp4"), "cid": "c1", "work": Path("work"), "n": 1,
            "plan": {"resolution": "720p",
                     "model": "doubao-seedance-2-0-mini-260615"},
            "dur": 5, "prompt": "严格编辑@视频1，将其中的产品替换为@图片1中的产品",
            "audio": None, "style_clip": None, "refs": [], "ingest": _ingest,
            "out": Path("out.mp4"),
        })
    finally:
        (_ve_y._public_url, _ve_y._write_request) = (_old_pu2, _old_wr)
        (_ing.available, _ing.prepare_video) = (_old_av, _old_pv)
        _ark.edit_video = _old_ev
    check("入库炸了仍然把这段发出去（不中断）",
          bool(_sent.get("prompt")), True)
    check("退回直传：用的还是原公网 URL", _sv, "https://x/seg.mp4")
    check("原因记进 sent_ingest（事后能查为什么没入库）",
          "ingest down" in str(_si.get("error") or ""), True)

    # ------------------------------------------------------------------
    # 🩸 2026-10-28（主人：「2.0呢？2.0可是有3个分支的」）：
    #   2.0 家族有**三台机型**（标准 / 极速 / Mini），共用同一个适配器。
    #   之前几百条判据全用 Mini 跑，另两台几乎没验。这里锁住"三台该怎么不同、
    #   该怎么相同"——差异只在**档位表**，编译口径必须逐字一样。
    from app.services import model_specs as _ms
    _M3 = ("doubao-seedance-2-0-260128",      # 标准
           "doubao-seedance-2-0-fast-260128",  # 极速
           "doubao-seedance-2-0-mini-260615")  # Mini
    check("2.0 家族是三台机型",
          [m for m, _ in _ms.MODELS["volc"] if "2-0" in m], list(_M3))
    check("三台的 edit_task_param 都是 False（都是 2.0 口径，不许某台被当 2.5 发）",
          {bool(_ms.volc(m)["edit_task_param"]) for m in _M3}, {False})
    check("三台人数上下限一致（4 人，官方 sd20-guide:467）",
          {_ms.subjects(m) for m in _M3}, {(4, 4)})

    _CHG3 = {"person": True, "product": True, "product_desc": "面霜",
             "style": "anime"}
    _P1x = {"id": "P1", "present": True, "position": "center",
            "desc_zh": "体型偏胖的男子"}
    _outs = {m: edit_spec.compile_prompt(
        "volc", edit_spec.normalize(_CHG3), model=m,
        source_people=[_P1x], frame_people=[_P1x],
        slots=["person", "product"]) for m in _M3}
    check("三台的提示词**逐字相同**（差异只在参数表，不在编译口径）",
          len(set(_outs.values())), 1)
    # 档位表**必须**不同，否则就是把 mini 的能力当成全家族的
    check("标准版有 1080p/4k 档",
          ("1080p" in _ms.volc(_M3[0])["resolutions"]
           and "4k" in _ms.volc(_M3[0])["resolutions"]), True)
    check("极速版和 Mini 只到 720p（拿 1080p 源要降档，不许硬发）",
          [sorted(_ms.volc(m)["resolutions"]) for m in _M3[1:]], [["480p", "720p"]] * 2)

    # ------------------------------------------------------------------
    # 从共用逻辑测试搬回来的 **2.0 单型号断言**（D43）
    # ------------------------------------------------------------------
    print("== 档位 / 清晰度 / 时长（2.0 系列）==")
    from app.core.config import settings as _st
    from app.services import video_edit as _ve

    check("2.0 Mini 区间", _ve.bounds_for("volc", "doubao-seedance-2-0-mini-260615"),
          (4.0, 15.0))
    for _model, _want, _got in (("doubao-seedance-2-0-mini-260615", "1080p", "720p"),
                                ("doubao-seedance-2-0-fast-260128", "4k", "720p")):
        _sp = edit_spec.defaults()
        _sp["resolution"] = _want
        check(f"{_model} {_want} → {_got}",
              _ve._resolution_for("volc", _sp, 1920, _model, width=1080), _got)
    _real_model = _st.ark_video_edit_model
    try:
        for _m in ("doubao-seedance-2-0-260128",
                   "doubao-seedance-2-0-fast-260128",
                   "doubao-seedance-2-0-mini-260615"):
            object.__setattr__(_st, "ark_video_edit_model", _m)
            check(f"{_m.split('-')[-2]}-{_m.split('-')[-1]} → 15s",
                  _ve._limit_for("volc"), 15.0)
    finally:
        object.__setattr__(_st, "ark_video_edit_model", _real_model)

    print("== build_prompt 的火山标号 ==")
    _v = _ve.build_prompt("volc", "换成一位白衬衫女性", subject_kind="file")
    check("火山用「@视频1/@图片1」不用 asset id",
          ("@视频1" in _v and "@图片1" in _v and "替换" in _v and "asset" not in _v), True)
    _v2 = _ve.build_prompt("volc", "换成一只橘猫", subject_kind="none")
    # 🩸 D53（2026-10-29 2.0 轮修）：原断言要求产出里出现「编辑视频」——
    #   那是 **2.5** 的判词前缀（`volc-api:442` 的 `omni_reference_task_type`），
    #   2.0 官方教程**零命中**；2.0 靠 `sd20-guide:39` 的句式定任务类型：
    #   「严格编辑<视频N>，将其中的<原特征>修改为<新特征>」。
    check("火山（2.0）无参考图用官方句式「严格编辑@视频1」",
          _v2.startswith("严格编辑@视频1"), True)
    check("火山（2.0）不出现 2.5 的「编辑视频」判词", "编辑视频" not in _v2, True)
    # `sd20-guide:52`「编辑 / 延长视频任务…请勿使用『参考<视频N>』，
    # 以免被误判为参考任务」—— 写错这一句会异步报 TaskTypeMismatch。
    check("火山（2.0）不写「参考@视频1」", "参考@视频1" not in _v2, True)

    print("== 边界帧（2.0 不带）==")
    check("2.0 mini 不带边界帧", _ve.boundary_allowed(
        "volc", "doubao-seedance-2-0-mini-260615"), False)
    check("2.0 标准版也不带", _ve.boundary_allowed(
        "volc", "doubao-seedance-2-0-260128"), False)
    _plan20 = {"ch": "volc", "model": "doubao-seedance-2-0-260128"}
    _spans20 = [(0.0, 10.0), (10.0, 20.0)]
    check("2.0 不带（型号不允许）", _ve._boundary_used(
        _plan20, _spans20, {_spans20[0]: ("change", [{"id": "P1"}])}), False)
