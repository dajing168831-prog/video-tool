# 使用视频生成 API 创作版权 IP 视频

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

视频生成 API 支持使用已授权的商用版权 IP 或版权 IP 模板，通过 Doubao Seedance 2.0 和 Doubao Seedance 2.5 生成含版权 IP 的视频。方舟会在生成前校验授权、版权放行策略和模板素材，帮助您合规使用版权形象。

<span id="copyright-usage-modes"></span>
## 使用方式

版权视频生成支持两种方式：

| 使用方式 | 场景 | 流程简述 |
|---|---|---|
| **模板创作** | 模板结构明确，只需替换指定素材。 | 1. 调用 `ListIPTemplates` 接口获取版权 IP 模板信息。| \
||| 2. 调用视频生成 API，在 `moderation_options.commercial_ip_template` 中传入模板 ID，并在 `content` 中按要求传入替换素材。|
| **自由创作** | 需要使用版权 IP 形象进行自由创作。 | 1. 在 **体验中心 > 版权库** 获取已授权的版权 IP ID。| \
||| 2. 调用视频生成 API，在 `moderation_options.commercial_ips` 中传入一个或多个 IP ID，并在 `content` 中自由传入提示词和参考素材。|

<span id="copyright-ip-concepts"></span>
## 相关概念

| 概念 | 说明 |
|---|---|
| 版权 IP | 平台提供的已授权用于视频生成的版权 IP，例如电影角色、真人形象或其他视觉形象。每个 IP 拥有唯一 ID。 |
| 版权 IP 模板 | 包含版权 IP、固定提示词、固定素材和可替换素材的视频生成模板。每个模板拥有唯一 ID。单个版权 IP 可关联多个模板。 |
| 可替换素材 | 版权 IP 模板中允许替换的素材。调用 `ListIPTemplates` API，可在返回的 `template_content` 中查看素材类型、`role` 和用途说明。 |

<span id="copyright-ip-example"></span>
### 示例

- 版权 IP：电影《长江七号》中的周星驰形象。
- 版权 IP 模板：围绕该形象设计的视频生成模板。
- 可替换素材：每个模板中，均提供可替换素材。

下方视频展示了两个模板：

  [视频](https://arkdocs.tos-cn-beijing.volces.com/videos/video-generation/template-sample.mp4)

> **说明**
>
> 可在 [控制台体验中心](https://ark.volcengine.com/region:cn-beijing/experience/gen_video?model=doubao-seedance-2-5-260628) 的版权库中查看更多版权 IP 和模板。

<span id="copyright-video-usage-scenarios"></span>
## 版权视频使用场景说明

按生成视频是否用于盈利目的，不同版权 IP 允许的使用场景不同。以下为对“盈利性”和“非盈利性”场景的定义，您可在体验中心的版权库查看具体版权 IP 的可用范围。

| 场景 | 说明 |
|---|---|
| 盈利性场景 | 用户或商业主体使用版权 IP 形象进行具有直接或间接商业目的的内容创作，包括但不限于商品销售、品牌推广、付费引导、商业活动宣传、企业营销等任何以获取经济收益为目标的使用行为。 |
| 非盈利性场景 | 用户基于个人兴趣、社交表达或娱乐目的，使用版权 IP 形象进行非商业性质的内容创作，不涉及任何直接或间接的经济收益获取行为。 |

> **警告**
>
> - 平台强制禁止的场景：禁止生成可能对版权 IP 形象造成不可逆损害、引发公关危机、导致法律纠纷，或严重损害版权方商业利益与公众形象的视频内容。
>
> - 您需确保上传素材和提示词符合版权授权范围、平台规则和相关法律法规。传入未经授权的版权素材或不合规的视频生成指令，将导致视频生成任务失败。

<span id="copyright-calling-methods"></span>
## 调用方式

<span id="copyright-prerequisites"></span>
### 前置条件：开通并领取版权 IP

1. 前往控制台 > [开通管理](https://ark.volcengine.com/region:cn-beijing/openManagement?advancedActiveKey=copyrightIpCommercial) > **版权 IP 商用** 页签，开通版权 IP 功能。
2. 前往 [控制台体验中心](https://ark.volcengine.com/region:cn-beijing/experience/gen_video?model=doubao-seedance-2-5-260628)，在 **版权库** > **视觉版权** 模块中领取需要使用的版权 IP。

> **注意**
>
> 使用视频生成 API 生成版权视频前，需先领取对应版权 IP。领取后，可使用该 IP 进行自由创作，也可使用该 IP 下的可用模板进行创作。

<span id="copyright-template-creation"></span>
### 方式一：使用模板创作

<span id="copyright-template-workflow"></span>
#### 调用流程

![copy-right-flow-2.png](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/copy-right-flow-2.png)

1. 调用 `ListIPTemplates` 获取当前账号可用的模板列表。
2. 从返回的 `items` 中选择模板并记录 `template_id`，再根据 `template_content` 中的 `type`、`role` 和 `description` 准备替换素材。
3. 调用 [创建视频生成任务 API](/docs/create-video-generation-task-api)，在 `moderation_options.commercial_ip_template` 中传入 `template_id`，并在 `content` 中传入需要替换的素材。
4. 调用 [查询视频生成任务 API](/docs/get-video-generation-task-api) 轮询任务状态。任务成功后，从 `content.video_url` 获取生成视频。

<span id="copyright-get-template-information"></span>
#### 示例：获取模板信息

> **说明**
>
> - `ListIPTemplates` API 需使用 AK/SK 鉴权，详情参考 [API 访问密钥管理](https://docs.volcengine.com/docs/6257/64983?lang=zh)。
>
> - 有关 `ListIPTemplates` API 的具体信息，请查看 [`ListIPTemplates` API 参考文档](/docs/list-ip-templates-api)。

以下示例使用 Python 语言，您可按需替换为其他编程语言。

安装 `requests`，并将 AK/SK 配置到环境变量：

```bash
pip install requests
export VOLC_ACCESS_KEY="ACCESS_KEY"
export VOLC_SECRET_KEY="SECRET_KEY"
```

获取版权 IP 模板信息：

```Python
import datetime
import hashlib
import hmac
import json
import os
from urllib.parse import quote

import requests

HOST = "open.volcengineapi.com"
REGION = "cn-beijing"
SERVICE = "ark"
ACTION = "ListIPTemplates"
VERSION = "2024-01-01"


def hash_sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hmac_sha256(key, value):
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


def canonical_query(params):
    return "&".join(
        f"{quote(key, safe='-_.~')}={quote(str(value), safe='-_.~')}"
        for key, value in sorted(params.items())
    )


def main():
    access_key = os.environ["VOLC_ACCESS_KEY"]
    secret_key = os.environ["VOLC_SECRET_KEY"]

    body = json.dumps({}, separators=(",", ":"))
    query = {"Action": ACTION, "Version": VERSION}
    x_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short_date = x_date[:8]
    payload_hash = hash_sha256(body)

    signed_headers = "content-type;host;x-content-sha256;x-date"
    canonical_headers = "\n".join(
        [
            "content-type:application/json",
            f"host:{HOST}",
            f"x-content-sha256:{payload_hash}",
            f"x-date:{x_date}",
        ]
    )
    canonical_request = "\n".join(
        [
            "POST",
            "/",
            canonical_query(query),
            canonical_headers,
            "",
            signed_headers,
            payload_hash,
        ]
    )

    credential_scope = f"{short_date}/{REGION}/{SERVICE}/request"
    string_to_sign = "\n".join(
        [
            "HMAC-SHA256",
            x_date,
            credential_scope,
            hash_sha256(canonical_request),
        ]
    )

    signing_key = hmac_sha256(secret_key.encode("utf-8"), short_date)
    signing_key = hmac_sha256(signing_key, REGION)
    signing_key = hmac_sha256(signing_key, SERVICE)
    signing_key = hmac_sha256(signing_key, "request")
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    headers = {
        "Authorization": (
            f"HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "Content-Type": "application/json",
        "Host": HOST,
        "X-Content-Sha256": payload_hash,
        "X-Date": x_date,
    }

    response = requests.post(
        f"https://{HOST}/",
        params=query,
        headers=headers,
        data=body,
        timeout=30,
    )
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    response.raise_for_status()


if __name__ == "__main__":
    main()
```

> **说明**
>
> `ListIPTemplates` API 支持按 IP ID（`Filter.IPIds[]`）筛选结果。

以下响应示例仅供参考。为避免临时链接失效，已将素材 URL 替换为示例地址。

```
{
  "ResponseMetadata": {
    "RequestId": "REQUEST_ID",
    "Action": "ListIPTemplates",
    "Version": "2024-01-01",
    "Service": "ark",
    "Region": "cn-beijing"
  },
  "Result": {
    "items": [
      {
        "template_id": "ip-prompt-tpl_07e85a74b23d48dcbd21da3b********",
        "default_params": {
          "ratio": "9:16",
          "resolution": "1080p",
          "duration": 8,
          "watermark": true
        },
        "display_content": [
          {
            "type": "text",
            "text": "竖屏 9:16，8 秒，1080p。\n用户上传人像图片3作为主角脸部参考，只使用用户上传图片中的脸部身份特征生成主角，保留五官辨识度和本人气质，但进行自然商业美化。主角性别、发型和穿搭应与用户人像自然匹配。\n0-1.3s：心仔图片1竖着拿智能手机拍摄。蛋小黄图片2用动作指挥站位，不能说话，不能出现字幕气泡。1.3s 心仔按下快门，咔嚓闪光，白光覆盖进入海滩咖啡店。\n1.3-6.8s：热带海滩咖啡店，棕榈叶、白云、碧蓝海面和冰咖啡。主角穿适合本人气质的度假穿搭，例如轻薄衬衫套装、亚麻上衣、休闲短裤、阔腿裤、度假长裙或宽松外套，由模型根据用户人像自然选择，不强制裙装。面料随风飘动，发型干净蓬松有光泽，肤色健康明亮。主角站在棕榈树旁，先抬起手臂伸展身体，再轻轻转圈回头大笑，表情欢快大方。心仔收起手机，躺在左侧沙滩椅上喝冰咖啡，随后坐起和主角一起摆度假 pose；蛋小黄戴墨镜站在右侧脚边，穿白色毛绒绒短袜，用小扇子指挥主角并一起摆 pose。棕榈叶作为前景扫过，阳光形成 lens flare。\n6.8-8s：阳光穿过棕榈叶形成爆点，定格成主角居中、心仔和蛋小黄悠闲互动的热带度假拍立得照片。明显白色边框、下方宽白边、清透 instant photo 滤镜。\n比例：主角最高，心仔低于主角肩线，蛋小黄只到主角腰线附近。蛋小黄穿白色毛绒绒短袜。蛋仔的手部不能五指化，不要出现长短不齐的问题。蛋仔和心仔有且只有一个，不能出现透视、重叠问题。",
            "order": -1
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://example.com/xinzai.png"
            },
            "role": "reference_image",
            "replaceable": false,
            "order": -1
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://example.com/danxiaohuang.png"
            },
            "role": "reference_image",
            "replaceable": false,
            "order": -1
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://example.com/user-portrait.jpg"
            },
            "role": "reference_image",
            "replaceable": true,
            "order": 0
          }
        ],
        "template_content": [
          {
            "type": "image_url",
            "image_url": {
              "url": "https://example.com/user-portrait.jpg"
            },
            "role": "reference_image",
            "order": 0,
            "description": "Information of the replaceable image."
          }
        ],
        "ip_id": "ip-c-example"
      }
    ],
    "total": 1
  }
}
```

`items` 数组返回模板列表。其中每个元素是一条可用模板。重点字段说明如下：

| 所属对象 | 字段 | 说明 |
| --- | --- | --- |
| `items[]` | `template_id` | 模板 ID。创建视频生成任务时，需传入 `moderation_options.commercial_ip_template`。 |
|^^| | | \
| | `default_params` | 部分模板会返回推荐的生成参数，例如 `ratio`、`resolution`、`duration` 和 `watermark`。如视频生成请求中不传入对应参数，则默认使用模板返回的 `default_params` 参数值。您可在请求中根据需求指定其他值。 |
|^^| | | \
| | `display_content` | 模板完整内容，用于展示模板内置提示词、固定素材和可替换素材。<br> `replaceable` 为 `true` 的元素表示可替换；`replaceable` 为 `false` 为模板固定内容，不需在视频生成请求中传入。 |
|^^| | | \
| | `template_content` | 需要由调用方准备并传入视频生成 API 的可替换素材列表。每个元素包含素材 `type`、`role`、`order` 和 `description`。 |
|^^| | | \
| | `ip_id` | 模板关联的 IP ID，由版权 ID 转换得到。 |
| `template_content[]` | `type` | 素材类型，例如 `image_url`、`video_url` 或 `audio_url`。视频生成请求中替换素材的结构必须与该类型一致。 |
|^^| | | \
| | `role` | 素材在视频生成请求中的角色。将 `template_content` 中的 `role` 原样填入 `content` 条目。 |
|^^| | | \
| | `order` | 可替换素材顺序。同一个模板存在多个可替换素材时，按 `order` 从小到大准备并传入。 |
|^^| | | \
| | `description` | 可替换素材的用途说明，例如用户主形象图、商品图或场景参考。 |

> **说明**
>
> - 平台会自动组装模板内置的提示词、固定素材和版权配置。**视频生成请求的 `content` 只需包含 `template_content` 声明的可替换素材**，**无需**传入 `display_content` 中的完整提示词或固定素材。
> - **素材要求**：按 `template_content` 的占位要求传入素材。素材缺失、类型不匹配或包含未知占位时，请求会被拒绝。
> - **参数要求**：部分模板会返回视频生成默认参数 `default_params`，可包含 `ratio`、`duration`、`resolution` 和 `watermark` 等。如视频生成请求中不传入对应参数，则默认使用模板返回的参数值；您也可以在请求中根据需求指定其他值。

<span id="copyright-call-video-api-with-template"></span>
#### 示例：调用视频生成 API

根据 `template_content` 准备素材，调用视频生成 API。

例如，当需要使用的 `template_content` 只包含一张图片素材时，只需向视频生成 API 的 `content` 传入一个图片素材，并沿用模板返回的 `role`。

```Bash
curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-0-260128",
    "content": [
        {
            "type": "image_url",
            "image_url": {
                "url": "https://example.com/user-character.png"
            },
            "role": "reference_image"
        }
    ],
    "ratio": "9:16",
    "resolution": "1080p",
    "duration": 8,
    "watermark": true,
    "moderation_options": {
        "commercial_ip_template": "IP_TEMPLATE_ID"
    },
    "safety_identifier": "USER_IDENTIFIER"
}'
```

<span id="copyright-free-creation"></span>
### 方式二：自由创作

<span id="copyright-free-creation-workflow"></span>
#### 调用流程

![copy-right-flow-1.png](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/copy-right-flow-1.png)

1. 前往 [控制台体验中心](https://ark.volcengine.com/region:cn-beijing/experience/gen_video?model=doubao-seedance-2-5-260628)，从 **版权库** 模块中获取版权 IP ID。
2. 按视频生成方式准备提示词、图片、视频或音频素材。
3. 调用 [创建视频生成任务 API](/docs/create-video-generation-task-api)，在 `moderation_options.commercial_ips` 中传入需要使用的版权 IP ID。
  > 支持传入多个 IP ID。最多可传入 5 个 IP ID。
4. 调用 [查询视频生成任务 API](/docs/get-video-generation-task-api) 轮询任务状态。任务成功后，从 `content.video_url` 获取生成视频。

<span id="copyright-call-video-api-for-free-creation"></span>
#### 调用视频生成 API

在 `content` 中传入提示词和素材，并在 `moderation_options.commercial_ips` 中传入要使用的版权 IP ID。

```Bash
curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-0-260128",
    "content": [
        {
            "type": "text",
            "text": "TEXT_PROMPT"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://example.com/character.png"
            },
            "role": "reference_image"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://example.com/product.png"
            },
            "role": "reference_image"
        }
    ],
    "ratio": "9:16",
    "duration": 15,
    "watermark": true,
    "moderation_options": {
        "commercial_ips": [
            "IP_ID"
        ]
    },
    "safety_identifier": "USER_IDENTIFIER"
}'
```

<span id="copyright-ip-response-fields"></span>
### 版权 IP 相关返回字段

任务完成后，查询任务接口会返回生成视频地址。若请求中声明了版权 IP 或模板，还会返回 `moderation_results`。

模板创作会返回任务应用的商用版权 IP ID 和请求中声明的模板 ID：

```json
{
  "id": "cgt-2026****-****",
  "model": "doubao-seedance-2-0-260128",
  "status": "succeeded",
  "content": {
    "video_url": "https://ark-content-generation-cn-beijing.tos-cn-beijing.volces.com/xxx"
  },
  "usage": {
    "completion_tokens": 108900,
    "total_tokens": 108900
  },
  "created_at": 1779348818,
  "updated_at": 1779348874,
  "seed": 78674,
  "resolution": "720p",
  "ratio": "16:9",
  "duration": 5,
  "framespersecond": 24,
  "service_tier": "default",
  "execution_expires_after": 172800,
  "generate_audio": true,
  "draft": false,
  "priority": 0,
  "moderation_results": {
    "applied_commercial_ips": [
      "IP_ID"
    ],
    "applied_commercial_ip_template": "IP_TEMPLATE_ID"
  }
}
```

自由创作会返回请求时声明的商用版权 IP ID：

```json
{
  "id": "cgt-2026****-****",
  "model": "doubao-seedance-2-0-260128",
  "status": "succeeded",
  "content": {
    "video_url": "https://ark-content-generation-cn-beijing.tos-cn-beijing.volces.com/xxx"
  },
  "usage": {
    "completion_tokens": 108900,
    "total_tokens": 108900
  },
  "created_at": 1779348818,
  "updated_at": 1779348874,
  "seed": 78674,
  "resolution": "720p",
  "ratio": "16:9",
  "duration": 5,
  "framespersecond": 24,
  "service_tier": "default",
  "execution_expires_after": 172800,
  "generate_audio": true,
  "draft": false,
  "priority": 0,
  "moderation_results": {
    "applied_commercial_ips": [
      "IP_ID"
    ]
  }
}
```

<span id="copyright-ip-fields"></span>
## 版权 IP 相关字段说明

视频生成 API 通过 `moderation_options` 接收版权 IP 或模板，并通过 `moderation_results` 返回任务应用的商用版权 IP 和请求中声明的模板。

<span id="copyright-request-fields"></span>
### 请求字段

在 [创建视频生成任务 API](/docs/create-video-generation-task-api) 中，`moderation_options` 支持以下版权相关字段：

| 字段 | 类型 | 必选 | 说明 |
| --- | --- | --- | --- |
| `commercial_ip_template` | String | 否 | 商用版权模板 ID。模板创作时填写，仅支持传入 1 个模板 ID。 |
| `commercial_ips` | Array of String | 否 | 商用版权 IP ID 列表，最多支持 5 个。自由创作时用于声明要使用的商用版权 IP；模板创作时，可额外声明模板以外的商用版权 IP。 |

<span id="copyright-response-fields"></span>
### 响应字段

在 [查询视频生成任务 API](/docs/get-video-generation-task-api) 和 [查询视频生成任务列表 API](/docs/list-video-generation-tasks-api) 中，任务对象可能返回 `moderation_results`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `applied_commercial_ips` | Array of String | 任务应用的商用版权 IP ID 列表。模板创作时包含模板关联的版权 IP ID；如果请求额外声明了模板以外的商用版权 IP，也会一并返回。 |
| `applied_commercial_ip_template` | String | 请求中声明的商用版权模板 ID。自由创作时不返回。 |

<span id="copyright-billing"></span>
## 计费说明

使用商用版权 IP 和模板生成视频时，版权费用按各输入 IP 的单价和视频时长（秒）求和：

`单条视频版权费用 = Σ（每个输入 IP 的单价 × 视频时长（秒））`

IP 单价的计价单位需与视频时长单位一致。具体单价、授权范围和使用限制，以控制台展示、商务协议或相关价格说明为准。

<span id="copyright-related-documents"></span>
## 相关文档

- [视频生成 API](/docs/create-video-generation-task-api)
- [Seedance 2.5 教程](/docs/seedance-2-5)
- [Seedance 2.0 教程](/docs/seedance-2-0)
- [虚拟人像库指南](/docs/private-virtual-avatar-library-guide-preview)
- [真人人像库指南](/docs/guide-preview)
