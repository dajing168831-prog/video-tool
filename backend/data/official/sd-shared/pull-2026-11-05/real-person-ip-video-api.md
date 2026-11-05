# 使用视频生成 API 创作真人 IP 视频

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

视频生成 API 支持使用平台已授权的真人 IP 和对应参考图，通过 Doubao Seedance 2.0 和 Doubao Seedance 2.5 生成真人 IP 视频。方舟会在生成前校验真人 IP 的授权状态、参考图归属和内容合规性。

真人 IP 使用真实演员形象，具有以下优势：

- 商业营销：真实、自然的人物形象更容易建立信任，适合种草、导购和广告推荐等需要真人表达的内容。
- 短剧制作：可选择具有不同外形和气质的演员形象，适合对角色塑造和人物辨识度有较高要求的短剧内容。

<span id="real-person-ip-example"></span>
## 真人 IP 示例

真人 IP 是平台获得授权的真人演员形象。每个真人 IP 拥有唯一的 IP ID，并关联一个或多个固定形象。每个形象代表该演员的一套固定妆造，可以提供一张或多张参考图。

例如，一位演员可同时提供“古装皇后”和“古装宫女”等不同形象。不同形象的妆造、气质不同。生成视频时，需要选择符合创作场景的形象及参考图，模型会按照所选形象的固定妆造生成演员画面。

| 对象 | 说明 |
| --- | --- |
| 真人 IP | 对应一位已获得授权的真人演员。领取后，可以复制该演员的 IP ID，并在视频生成请求中通过 `moderation_options.commercial_ips` 传入。 |
| 形象 | 真人 IP 下的一套固定妆造，包含形象名称和标签。单个真人 IP 可提供多个形象。 |
| 参考图 | 形象下可用于视频生成的图片，单个形象可以提供多张参考图。 |

> **说明：IP 信息说明**
>
> - 在 [控制台体验中心](https://ark.volcengine.com/region:cn-beijing/experience/gen_video?model=doubao-seedance-2-5-260628) **版权库** > **真人版权** 模块中，可以领用、查看真人 IP 详细信息，并快速体验视频生成效果。
>
> - 您需按照真人 IP 的授权场景和使用协议创作内容。超出授权范围或使用非平台提供的真人 IP 素材，可能导致任务失败。关于使用场景的详细信息，请参考 [版权视频使用场景说明](/docs/copyright-video-api#copyright-video-usage-scenarios)。
>
> - 控制台实际展示信息以真人 IP 的版权方配置和授权范围为准。不同真人 IP 提供的形象数量、参考图、适用题材和授权场景可能不同。
>
> - 单个真人 IP 可以提供多个固定形象及参考图。生成视频时，应使用平台提供的参考图，不支持更换真人 IP 的固定妆造。

<span id="real-person-ip-calling-methods"></span>
## 调用方式

<span id="real-person-ip-workflow"></span>
### 调用流程

1. 首次使用前，开通真人 IP 服务。
2. 在控制台 **版权库** > **真人版权** 模块中选择真人 IP，并复制 IP ID。
3. 调用 `ClaimCommercialIPs` 领用真人 IP。
4. 调用 `ListAuthorizedCommercialIPIds`，将 `IPCategory` 设置为 `REAL_PERSON`，查询当前账号已领用且仍然有效的真人 IP 信息。
5. 调用 `ListCommercialIPReferences` 查询指定真人 IP 的可用参考图信息。
6. 调用 [创建视频生成任务 API](/docs/create-video-generation-task-api)。
    - 在 `content` 中传入提示词和参考图。
    - 在 `moderation_options.commercial_ips` 中传入真人 IP ID。
7. 调用 [查询视频生成任务 API](/docs/get-video-generation-task-api) 轮询任务状态。任务成功后，从 `content.video_url` 获取生成视频。

<span id="real-person-ip-prerequisites"></span>
### 前置条件

1. 前往控制台 > [开通管理](https://ark.volcengine.com/region:cn-beijing/openManagement?advancedActiveKey=copyrightIpCommercial)，开通真人 IP 服务。

2. 前往 [控制台体验中心](https://ark.volcengine.com/region:cn-beijing/experience/gen_video?model=doubao-seedance-2-5-260628)，在 **版权库** > **真人版权** 模块中查看真人 IP，并复制需要领用的 IP ID。

> **注意**
>
> - 即使当前账号已经开通商用版权 IP 服务，也需单独开通真人 IP 服务。
> - 生成视频前，当前账号必须已领取对应真人 IP，且授权处于有效期内。

<span id="claim-real-person-ip"></span>
### 领用真人 IP

领用和查询真人 IP 需要使用 AK/SK 鉴权。有关鉴权方式的详细信息，请参考 [Base URL 及鉴权](/docs/base-url-and-authentication)。

以下示例使用 Python。安装 `requests`，并将 AK/SK 和要领用的真人 IP ID 配置到环境变量：

```bash
pip install requests
export VOLC_ACCESS_KEY="ACCESS_KEY"
export VOLC_SECRET_KEY="SECRET_KEY"
export COMMERCIAL_IP_ID="ip-c-example"
```

调用 `ClaimCommercialIPs`，仅在 `IpIds` 中传入需要领用的真人 IP ID。

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
ACTION = "ClaimCommercialIPs"
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
    commercial_ip_id = os.environ["COMMERCIAL_IP_ID"]

    body = json.dumps(
        {
            "IpIds": [commercial_ip_id],
        },
        separators=(",", ":"),
    )
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
    result = response.json()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    response.raise_for_status()

    failed_items = [
        item
        for item in result.get("Result", {}).get("Items", [])
        if not item.get("Success")
    ]
    if failed_items:
        raise RuntimeError(f"Failed to claim commercial IPs: {failed_items}")


if __name__ == "__main__":
    main()
```

响应示例：

```
{
  "ResponseMetadata": {
    "RequestId": "REQUEST_ID",
    "Action": "ClaimCommercialIPs",
    "Version": "2024-01-01",
    "Service": "ark",
    "Region": "cn-beijing"
  },
  "Result": {
    "Items": [
      {
        "IpId": "ip-c-example",
        "Success": true,
        "GrantId": "grant-example"
      }
    ]
  }
}
```

接口会为每个 IP 独立返回领取结果。`Items[].Success` 为 `true` 时，`Items[].GrantId` 返回对应的授权 ID；领取失败时，通过 `Items[].ErrorCode` 和 `Items[].ErrorMessage` 查看失败原因。

有关接口字段的详细信息，请参考 [领用商业 IP](https://docs.volcengine.com/docs/ark/claim-commercial-ips-api)。

<span id="query-real-person-ip"></span>
### 查询真人 IP

<span id="list-authorized-commercial-ip-ids"></span>
#### 查询已授权真人 IP

调用 `ListAuthorizedCommercialIPIds`，将 `IPCategory` 设置为 `REAL_PERSON`，查询当前账号已领用且仍然有效的真人 IP 信息。

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
ACTION = "ListAuthorizedCommercialIPIds"
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

    body = json.dumps({"IPCategory": "REAL_PERSON"}, separators=(",", ":"))
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

响应示例：

```
{
  "ResponseMetadata": {
    "RequestId": "REQUEST_ID",
    "Action": "ListAuthorizedCommercialIPIds",
    "Version": "2024-01-01",
    "Service": "ark",
    "Region": "cn-beijing"
  },
  "Result": {
    "Items": [
      {
        "IpId": "ip-c-example",
        "IPCategory": "REAL_PERSON",
        "IPName": "真人 IP 示例",
        "DescriptionCN": "真人 IP 中文说明",
        "DescriptionEN": "Real-person IP description",
        "SupportsAuthLetterApplication": true
      }
    ]
  }
}
```

`Result.Items` 返回当前账号可用的真人 IP 信息。记录需要使用的 `Items[].IpId`，并将其用于查询参考图和创建视频生成任务。

部分 IP 可能不返回 `Items[].DescriptionCN` 或 `Items[].DescriptionEN` 字段。`Items[].SupportsAuthLetterApplication` 表示该 IP 是否支持授权书申请；如需在视频生成后获取授权书，请选择该字段为 `true` 的真人 IP。

有关接口字段的详细信息，请参考 [查询已授权商业 IP 列表](/docs/list-authorized-commercial-ip-ids-api)。

<span id="list-commercial-ip-references"></span>
#### 查询 IP 参考图

调用 `ListCommercialIPReferences`，在请求体的 `IpId` 中传入真人 IP ID。

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
ACTION = "ListCommercialIPReferences"
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
    commercial_ip_id = os.environ["COMMERCIAL_IP_ID"]

    body = json.dumps({"IpId": commercial_ip_id}, separators=(",", ":"))
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

响应示例：

```
{
  "ResponseMetadata": {
    "RequestId": "REQUEST_ID",
    "Action": "ListCommercialIPReferences",
    "Version": "2024-01-01",
    "Service": "ark",
    "Region": "cn-beijing"
  },
  "Result": {
    "IpId": "ip-c-example",
    "References": [
      {
        "DisplayName": "古装形象正面照",
        "SortOrder": 1,
        "IsMainView": true,
        "PublicURL": "https://ark-copyright-cn-beijing.tos-cn-beijing.volces.com/submission/xxx",
        "PublicURLExpireAt": 1788019200
      }
    ]
  }
}
```

从 `Result.References` 中选择符合创作场景的形象和参考图，并记录 `PublicURL`。

> **注意**
>
> - `PublicURL` 为有效期 1 天的 TOS 签名 URL。请在 `PublicURLExpireAt` 指定的时间前使用；URL 过期后，重新调用接口获取。
> - 查询参考图不要求当前账号已领取指定 IP，但使用该 IP 生成视频前必须完成领取。
> - 真人 IP 的不同参考图可能对应不同固定形象或妆造。可根据 `DisplayName` 和 `IsMainView` 选择参考图。

有关接口字段的详细信息，请参考 [查询商业 IP 参考图列表](https://docs.volcengine.com/docs/ark/list-commercial-ip-references-api)。

<span id="generate-real-person-ip-video"></span>
### 生成真人 IP 视频

调用 [创建视频生成任务 API](/docs/create-video-generation-task-api) 生成视频。

- 在 `content` 中传入提示词、真人 IP 参考图和其他创作素材。
- 在 `moderation_options.commercial_ips` 中传入参考图所属的真人 IP ID。

```Bash
curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-0-260128",
    "content": [
        {
            "type": "text",
            "text": "图片 1 中的人物自然地介绍图片 2 中的产品，人物居中且人脸清晰。"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "COMMERCIAL_IP_REFERENCE_PUBLIC_URL"
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
    "duration": 10,
    "watermark": true,
    "moderation_options": {
        "commercial_ips": [
            "ip-c-example"
        ]
    },
    "safety_identifier": "USER_IDENTIFIER"
}'
```

示例中的图片顺序如下：

1. 图片 1：`ListCommercialIPReferences` 返回的真人 IP 参考图 `PublicURL`。
2. 图片 2：用户提供的商品参考图。

提交任务后，调用 [查询视频生成任务 API](/docs/get-video-generation-task-api) 轮询任务状态。

> **注意**
>
> - 真人 IP 参考图必须来自 `ListCommercialIPReferences`，并与 `moderation_options.commercial_ips` 中声明的真人 IP ID 匹配。
> - 请求包含多张真人 IP 参考图时，每张参考图都必须属于请求中声明的真人 IP。任一参考图不匹配，任务将失败。
> - `moderation_options.commercial_ips` 最多支持传入 5 个 IP ID。

<span id="real-person-ip-api-fields"></span>
## API 字段说明

<span id="real-person-ip-request-fields"></span>
### 请求字段

在 [创建视频生成任务 API](/docs/create-video-generation-task-api) 中，以下字段用于真人 IP 视频生成：

| 字段 | 类型 | 必选 | 说明 |
| --- | --- | --- | --- |
| `content[].image_url.url` | String | 条件必选 | 传入 `ListCommercialIPReferences` 返回的 `PublicURL`。该 URL 对应真人 IP 的固定形象和参考图。 |
| `content[].role` | String | 条件必选 | 真人 IP 参考图需设置为 `reference_image`。 |
| `moderation_options.commercial_ips` | Array of String | 是 | 真人 IP ID 列表。必须包含请求中所有真人 IP 参考图所属的 IP ID，最多支持 5 个。 |

<span id="real-person-ip-response-fields"></span>
### 响应字段

任务完成后，[查询视频生成任务 API](/docs/get-video-generation-task-api) 返回生成视频地址和任务应用的真人 IP：

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
      "ip-c-example"
    ]
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `content.video_url` | String | 生成视频的临时访问地址。 |
| `moderation_results.applied_commercial_ips` | Array of String | 任务应用的真人 IP ID 列表。 |

<span id="real-person-ip-billing"></span>
## 计费说明

使用真人 IP 生成视频时，版权视频生成费用按各输入 IP 的单价和视频时长（秒）求和：

`单条视频真人 IP 版权费用 = Σ（每个输入 IP 的单价 × 视频时长（秒））`

一次请求传入多个真人 IP ID 时，分别计算每个 IP 的版权费用后求和。具体单价、授权范围和使用限制，以控制台展示、商务协议或相关价格说明为准。

<span id="real-person-ip-related-documents"></span>
## 相关文档

- [领用商业 IP](https://docs.volcengine.com/docs/ark/claim-commercial-ips-api)
- [查询已授权商业 IP 列表](/docs/list-authorized-commercial-ip-ids-api)
- [查询商业 IP 参考图列表](https://docs.volcengine.com/docs/ark/list-commercial-ip-references-api)
- [创建视频生成任务 API](/docs/create-video-generation-task-api)
- [查询视频生成任务 API](/docs/get-video-generation-task-api)
- [Seedance 2.5 教程](/docs/seedance-2-5)
- [Seedance 2.0 教程](/docs/seedance-2-0)
