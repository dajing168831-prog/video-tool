# 获取真人 IP 版权视频授权书 API 教程

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

本教程面向需要在自有平台接入授权书能力的方舟客户。终端用户在您的平台中使用已领用的真人 IP 生成版权视频后，可以打开免登申请链接，填写资料并提交授权书申请。您通过服务端查询申请结果，并在申请成功后下载授权书。

> **注意**
>
> 本功能仅用于视频生成后获取授权书，不用于在视频生成前取得真人 IP 的使用授权。使用真人 IP 生成视频前，您仍需调用 `ClaimCommercialIPs` 领用对应 IP。详情请参见 [使用视频生成 API 创作真人 IP 视频](/docs/real-person-ip-video-api)。

<span id="right-auth-letter-call-flow"></span>
## 调用流程

按以下流程调用接口：

1. 调用 [`ListAuthorizedCommercialIPIds`](/docs/list-authorized-commercial-ip-ids-api)，查询当前账号已领用且支持授权书申请的真人 IP。
2. 调用 [`CreateRightAuthLetterApplicationSession`](/docs/create-right-auth-letter-application-session-api)，为终端用户创建授权书免登申请链接。
3. 通过结果回调接收通知（可选），调用 [`GetRightAuthLetterApplicationSession`](/docs/get-right-auth-letter-application-session-api) 查询申请结果。
4. 查询成功后，使用 `File.URL` 下载授权书文件。

具体流程如下图所示：

![真人 IP 版权视频授权书免登申请流程](https://arkdocs.tos-cn-beijing.volces.com/images/resources/get-auth-letter-for-copyright-ip.png)

<span id="right-auth-letter-prerequisites"></span>
## 前提条件

- 已开通真人 IP 服务，并已调用 `ClaimCommercialIPs` 领用目标真人 IP。
- 终端用户已在您的平台中使用该真人 IP 生成版权视频。
- 已获取具有相关 API 调用权限的火山引擎账号 AK/SK。详情请参见 [Base URL 及鉴权](/docs/base-url-and-authentication)。

<span id="right-auth-letter-list-applicable-ips"></span>
## 步骤 1、查询支持申请的真人 IP

调用 [`ListAuthorizedCommercialIPIds`](/docs/list-authorized-commercial-ip-ids-api)，将 `IPCategory` 设置为 `REAL_PERSON`，查询当前账号已领用且授权有效的真人 IP。

```json
{
  "IPCategory": "REAL_PERSON",
  "ProjectName": "default"
}
```

响应中的 `Items[]` 直接返回真人 IP 信息：

```json
{
  "Result": {
    "Items": [
      {
        "IpId": "ip-c-example-a",
        "IPCategory": "REAL_PERSON",
        "IPName": "示例演员甲",
        "SupportsAuthLetterApplication": true
      },
      {
        "IpId": "ip-c-example-b",
        "IPCategory": "REAL_PERSON",
        "IPName": "示例演员乙",
        "SupportsAuthLetterApplication": false
      }
    ]
  }
}
```

| `SupportsAuthLetterApplication` | 您的处理方式 |
| --- | --- |
| `true` | 该 IP 支持申请授权书，可以向终端用户展示申请入口。 |
| `false` | 该 IP 暂不支持申请授权书，不展示申请入口。 |
| 未返回 | 尚不能确认该 IP 是否支持申请授权书，不展示申请入口。 |

终端用户选择 IP 后，将同一条记录的 `IpId` 传给创建接口的 `IpId`。

> **说明：支持申请不等于获得使用授权**
>
> `SupportsAuthLetterApplication` 不能替代当前账号的 IP 领用资格检查，也不保证提交申请一定成功。创建申请时，火山方舟仍会校验 IP 上下架状态、当前账号领用状态和申请资料。

**完成本步骤后，需确认**：目标记录的 `IPCategory` 为 `REAL_PERSON`，`IpId` 与终端用户生成视频时使用的 IP ID 一致，并且 `SupportsAuthLetterApplication` 明确为 `true`。

<span id="right-auth-letter-create-session"></span>
## 步骤 2、创建免登申请会话

调用 [`CreateRightAuthLetterApplicationSession`](/docs/create-right-auth-letter-application-session-api)，为一个真人 IP 和一个被授权方创建申请。

| 请求字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `IpId` | string | 是 | 本次申请对应的单个 IP ID。值不能为空或包含首尾空白，UTF-8 编码后最多 64 字节。 |
| `AuthorizedSubject` | object | 是 | 被授权方主体信息。当前仅需填写 `SubjectName`。 |
| `AuthorizedSubject.SubjectName` | string | 是 | 授权书中的真实被授权方主体名称。值不能为空或仅包含空白，不从签名账号的实名资料自动取值。 |
| `ProjectName` | string | 否 | 资源所属项目，默认值为 `default`。传入时不能为空，UTF-8 编码后最多 255 字节。该字段不是终端用户填写的作品或商业项目标题。 |
| `Callback` | object | 否 | 申请结果回调配置。启用时必须同时提供 `Callback.URL` 和 `Callback.Secret`。 具体使用方式，请参考下文**配置结果回调**。 |

请求示例：

```json
{
  "IpId": "ip-c-example",
  "AuthorizedSubject": {
    "SubjectName": "示例文化传媒有限公司"
  },
  "ProjectName": "default"
}
```

响应示例：

```
{
  "ResponseMetadata": {
    "RequestId": "example-request-id"
  },
  "Result": {
    "SessionId": "example-session-id",
    "ApplicationURL": "https://<APPLICATION_PAGE>/?token=<OPAQUE_TOKEN>",
    "FirstAccessExpireAt": 1800000600,
    "SessionExpireAt": 1800086400
  }
}
```

创建成功后，保存以下返回值：

| 返回字段 | 类型 | 说明 |
| --- | --- | --- |
| `SessionId` | string | 申请会话 ID。用于查询申请状态和识别回调通知，不要自行生成或修改。 |
| `ApplicationURL` | string | 提供给指定终端用户的完整免登申请链接。该字段仅在创建成功时返回，查询接口不会补发。 |
| `FirstAccessExpireAt` | int64 | 终端用户首次成功进入申请页面的截止时间，UTC Unix 时间戳，单位为秒。 |
| `SessionExpireAt` | int64 | 免登申请入口的总访问截止时间，UTC Unix 时间戳，单位为秒。该时间从会话创建时开始计算，不会在终端用户首次打开链接后重新计时。 |

> **说明：按接口返回值处理访问时限**
>
> - 当前默认首次访问时限为创建后 10 分钟，默认总访问时限为创建后 24 小时。服务端配置可能调整，请以接口返回的时间和平台实际校验结果为准，不要在您的平台中固定时限。
> - 终端用户打开链接时，火山方舟会校验链接是否仍然有效。
> - 您的服务端查询申请状态不计为终端用户进入申请页面。

> **注意：保存链接并避免重复创建**
>
> - `ApplicationURL` 包含访问凭证，仅在创建成功时返回。查询接口无法找回该链接。请妥善保存，不要公开或写入普通日志。
> - 每次调用创建接口都会生成新的申请记录和链接。创建请求超时或返回 `InternalError` 时，不要自动连续重试。确需重新创建时，只向终端用户提供新的链接。

**完成本步骤后，需确认**：响应包含非空的 `SessionId` 和 `ApplicationURL`，两个截止时间均晚于创建时间。不要由您的服务端打开 `ApplicationURL` 进行验证，该链接应由指定终端用户打开。

<span id="right-auth-letter-share-application-url"></span>
## 步骤 3、提供申请链接

将 `ApplicationURL` 原样提供给指定终端用户，不要自行拼接或修改。根据 `FirstAccessExpireAt` 和 `SessionExpireAt` 提醒终端用户及时办理。

终端用户打开链接后，在免登页面填写授权书申请资料并提交，无需登录火山方舟账号。

<span id="right-auth-letter-query-session"></span>
## 步骤 4、查询申请结果

使用创建申请时的同一个方舟账号调用 [`GetRightAuthLetterApplicationSession`](/docs/get-right-auth-letter-application-session-api)，传入已保存的 `SessionId`。

`SessionId` 为必填字符串，不得包含首尾空白，UTF-8 编码后最多 64 字节。

```json
{
  "SessionId": "example-session-id"
}
```

申请成功且授权书未作废时，查询接口返回文件信息：

```json
{
  "ResponseMetadata": {
    "RequestId": "example-request-id"
  },
  "Result": {
    "Session": {
      "SessionId": "example-session-id",
      "Status": "SUCCEEDED",
      "File": {
        "FileName": "授权书.pdf",
        "URL": "https://<FILE_SERVICE_HOST>/<SIGNED_PATH>"
      }
    }
  }
}
```

当 `Session.Status` 为 `CREATED` 或 `PROCESSING` 时，建议每隔 5～10 秒查询一次，并为单轮等待设置上限。查询暂时出错或本轮等待超时不代表申请失败。保存 `SessionId`，稍后继续查询同一个 Session，不要因此重复创建申请。

<span id="right-auth-letter-query-status-and-errors"></span>
## 查询接口状态和错误码

以下申请状态和错误码均由 `GetRightAuthLetterApplicationSession` 查询接口返回。

| `Session.Status` | 含义 | 您的处理方式 |
| --- | --- | --- |
| `CREATED` | 申请入口已创建，终端用户尚未完成提交。 | 引导终端用户打开已保存的申请链接，并继续查询。 |
| `PROCESSING` | 终端用户已提交资料，火山方舟正在处理申请或生成授权书。 | 继续查询，不要为同一申请重复创建入口。 |
| `SUCCEEDED` | 授权书已生成成功且未作废。 | 使用 `File.URL` 下载授权书。 |
| `FAILED` | 授权书申请处理失败。 | 停止本轮等待。业务确认仍需申请后，创建新的 Session。 |
| `EXPIRED` | 终端用户未提交资料，申请入口已超过首次进入期限或总访问期限。 | 旧入口不能继续使用。仍需申请时，创建新的 Session。 |
| `VOIDED` | 已生成的授权书被作废。 | 不再展示或下载该文件。 |

> **说明：申请入口过期不等于授权书失效**
>
> 终端用户已经提交的申请仍可继续处理。状态为 `SUCCEEDED` 的授权书在被作废前仍可获取文件。

| HTTP 状态码 | 查询接口错误码 | 说明 | 处理建议 |
| --- | --- | --- | --- |
| 400 | `MissingParameter.SessionId` | 未传入申请会话 ID。 | 补充 `SessionId` 后重新查询。 |
| 400 | `InvalidParameter.*` | `SessionId` 不合法。 | 确认 `SessionId` 非空、UTF-8 编码后不超过 64 字节且不含首尾空白。 |
| 404 | `ResourceNotFound.RightAuthLetterApplicationSession` | 当前账号下找不到指定 Session。 | 检查调用账号和 `SessionId`。已清理的记录无法查询。 |
| 500 | `InternalError` | 服务内部异常。 | 稍后重试查询。多次重试仍失败时，记录 `ResponseMetadata.RequestId` 并联系技术支持。 |

> **注意**
>
> 失败或过期的申请记录从 Session 创建起保留 15 天，之后可能无法查询。及时保存所需的业务结果。

<span id="right-auth-letter-configure-callback"></span>
## 步骤 5、配置结果回调

如需火山方舟主动通知申请结果，在创建会话时同时传入 `Callback.URL` 和 `Callback.Secret`。未配置回调时，主动查询申请结果。

```json
{
  "Callback": {
    "URL": "https://callback.example.com/auth-letter",
    "Secret": "<43_CHARACTER_BASE64URL_SECRET>"
  }
}
```

- `Callback.URL`：您的公网 HTTPS 回调地址，最多 2048 个字符。地址应使用默认端口或 `443`，不得包含用户名、密码或 URL 片段，也不应发生重定向。
- `Callback.Secret`：您生成并保存在服务端的共享密钥。先生成 32 字节安全随机数，再编码为不带末尾等号的 43 字符 Base64URL 字符串。不要记录日志或返回给终端用户。

可以使用以下命令生成 `Callback.Secret`：

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

火山方舟通过 HTTP POST 发送通知。通知不包含授权书文件，收到通知后仍需调用查询接口获取最新状态和下载地址。

```json
{
  "SessionId": "example-session-id",
  "Status": "SUCCEEDED",
  "ApplicationId": "example-application-id"
}
```

- 通知体总是返回 `SessionId` 和 `Status`，可能返回 `ApplicationId`。`Status` 仅可能为 `SUCCEEDED` 或 `FAILED`。
- 终端用户未提交且申请入口过期时，通知可能不包含 `ApplicationId`。此时，通知状态可能为 `FAILED`，查询状态为 `EXPIRED`。
- 处理中和授权书作废时不发送通知。回调可能重复或未送达，不要只等待回调，最终状态以查询接口为准。

验签时，读取请求头 `X-Ark-Auth-Letter-Timestamp` 和 `X-Ark-Auth-Letter-Signature`。签名格式为 `v1=<signature>`，其中 `<signature>` 是 64 位小写十六进制 HMAC-SHA256 签名。将 `Callback.Secret` 解码为 32 字节密钥，并对 `<timestamp>.<原始 HTTP 请求体字节>` 计算签名。不要解析 JSON 后重新序列化请求体再验签。

建议结合服务端时钟校验时间窗口，防止重放。验签成功后，按 `SessionId` 和 `Status` 幂等保存通知，并尽快返回 HTTP 2xx，建议在 3 秒内完成。火山方舟对部分发送失败最多发送 4 次。

**完成本步骤后，需确认**：使用测试通知确认您的服务端会拒绝错误签名和超出时间窗口的通知，并能幂等处理重复通知。验签成功后，使用 `SessionId` 查询最新结果。

<span id="right-auth-letter-download-file"></span>
## 步骤 6、下载授权书

查询接口返回 `SUCCEEDED` 时，`Session.File` 包含：

- `FileName`：授权书文件名。
- `URL`：授权书的短期 HTTPS 签名下载地址。

使用 `File.URL` 下载文件时，无需携带 OpenAPI AK/SK。下载地址可以直接访问授权书，不得公开或写入普通日志。链接失效后，重新查询同一个 `SessionId` 获取新地址，无需重新申请。

保存文件时，由您的程序指定本地路径，不要直接使用远端 `FileName` 作为路径。向终端用户提供文件前，校验终端用户是否有权访问对应业务记录。

**完成本步骤后，需确认**：下载的文件非空且可以正常打开。重新查询时，`Session.Status` 仍为 `SUCCEEDED`。

<span id="right-auth-letter-code-example"></span>
## 示例代码

以下 Python 示例使用研发提供的火山引擎 Python SDK 完成 AK/SK 签名，并按接入环节分段展示。

<span id="right-auth-letter-install-dependencies"></span>
### 安装依赖并配置环境变量

使用 Python 3.10 或更高版本，安装依赖：

```bash
python -m pip install --upgrade volcengine requests
```

通过您的密钥管理系统配置环境变量：

```bash
export VOLC_ACCESSKEY="<ACCESS_KEY>"
export VOLC_SECRETKEY="<SECRET_KEY>"
```

使用临时访问凭证时，配置 `VOLC_SESSION_TOKEN`。如需覆盖默认地域 `cn-beijing`，配置 `VOLC_REGION`。

<span id="right-auth-letter-api-client"></span>
### 定义 API 调用函数

以下代码定义 IP 筛选、创建申请、查询状态和下载文件所需的函数。

```Python
import json
import math
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from volcengine.Credentials import Credentials
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request

HOST = "open.volcengineapi.com"
VERSION = "2024-01-01"


def call_api(action, payload):
    region = os.getenv("VOLC_REGION", "cn-beijing")
    credentials = Credentials(
        os.environ["VOLC_ACCESSKEY"],
        os.environ["VOLC_SECRETKEY"],
        "ark",
        region,
        os.getenv("VOLC_SESSION_TOKEN", ""),
    )
    request = Request()
    request.schema = "https"
    request.host = HOST
    request.path = "/"
    request.method = "POST"
    request.query = {"Action": action, "Version": VERSION}
    request.headers = {"Host": HOST, "Content-Type": "application/json"}
    request.body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    SignerV4.sign(request, credentials)

    try:
        # Send the same UTF-8 body that was signed without serializing it again.
        response = requests.post(
            request.build(),
            headers=request.headers,
            data=request.body.encode("utf-8"),
            timeout=(5, 30),
            allow_redirects=False,
        )
    except requests.RequestException:
        message = f"{action} network error"
        if action == "CreateRightAuthLetterApplicationSession":
            message += "; do not automatically retry this request"
        raise RuntimeError(message) from None

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(
            f"API returned non-JSON content: HTTP {response.status_code}"
        ) from None

    metadata = data.get("ResponseMetadata", {})
    error = metadata.get("Error")
    if not 200 <= response.status_code < 300 or error:
        code = (error or {}).get("Code", "UnknownError")
        request_id = metadata.get("RequestId", "")
        raise RuntimeError(f"API error {code}; RequestId={request_id}")
    result = data.get("Result")
    if not isinstance(result, dict):
        raise RuntimeError(f"{action} response does not contain Result")
    return result


def list_applicable_ips(project_name="default"):
    result = call_api(
        "ListAuthorizedCommercialIPIds",
        {
            "IPCategory": "REAL_PERSON",
            "ProjectName": project_name,
        },
    )
    items = result.get("Items")
    if not isinstance(items, list):
        raise RuntimeError(
            "ListAuthorizedCommercialIPIds response does not contain Items"
        )
    return [item for item in items if item.get("SupportsAuthLetterApplication") is True]


def create_entry(ip_id, subject_name, callback=None):
    payload = {
        "IpId": ip_id,
        "AuthorizedSubject": {"SubjectName": subject_name},
        "ProjectName": "default",
    }
    if callback is not None:
        payload["Callback"] = callback
    return call_api("CreateRightAuthLetterApplicationSession", payload)


def get_session(session_id):
    return call_api(
        "GetRightAuthLetterApplicationSession",
        {"SessionId": session_id},
    )["Session"]


def wait_for_file(session_id, wait_seconds=120, interval_seconds=5):
    # Reaching the polling deadline does not mean the application failed.
    if wait_seconds < 0:
        raise ValueError("wait_seconds must be non-negative")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    deadline = time.monotonic() + wait_seconds
    max_attempts = max(1, math.ceil(wait_seconds / interval_seconds) + 1)
    for _ in range(max_attempts):
        session = get_session(session_id)
        status = session["Status"]
        if status == "SUCCEEDED":
            file_info = session.get("File")
            if not file_info or not file_info.get("URL"):
                raise RuntimeError("Successful response does not contain a file URL")
            return file_info
        if status in {"FAILED", "EXPIRED", "VOIDED"}:
            raise RuntimeError(f"Application status: {status}")
        if status not in {"CREATED", "PROCESSING"}:
            raise RuntimeError("Unknown status; keep the SessionId and contact support")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(interval_seconds, remaining))
    return None


def download_file(file_info, output_path):
    # Choose the local path in your application; do not trust a remote filename.
    url = file_info["URL"]
    parsed_url = urlsplit(url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise RuntimeError("File URL is not a valid HTTPS URL")

    try:
        # Do not attach OpenAPI credentials or follow redirects.
        with requests.get(
            url,
            timeout=(5, 60),
            allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(
                    f"File download returned HTTP {response.status_code}; "
                    "query the session again for a new URL"
                )
            if not response.content:
                raise RuntimeError("Downloaded file is empty")
            with Path(output_path).open("xb") as output:
                output.write(response.content)
    except requests.RequestException:
        # Do not expose an exception that may contain the signed URL.
        raise RuntimeError(
            "Download network error; query the session again before retrying"
        ) from None


if __name__ == "__main__":
    eligible_ips = list_applicable_ips()
    safe_items = [
        {"IpId": item.get("IpId"), "IPName": item.get("IPName")}
        for item in eligible_ips
    ]
    print(json.dumps({"Items": safe_items}, ensure_ascii=False, indent=2))
```

<span id="right-auth-letter-select-and-create"></span>
### 选择 IP 并创建链接

调用 `list_applicable_ips` 获取支持授权书申请的真人 IP。终端用户选择 IP 后，调用 `create_entry` 创建申请。

```python
import secrets

ips = list_applicable_ips()
# Present ips to the terminal user and obtain the selected IP ID.

callback = None
# To enable callbacks, replace CALLBACK_URL and securely store the secret:
# callback = {
#     "URL": "<CALLBACK_URL>",
#     "Secret": secrets.token_urlsafe(32),
# }

created = create_entry(
    "<COMMERCIAL_IP_ID>",
    "<AUTHORIZED_SUBJECT_NAME>",
    callback=callback,
)
session_id = created["SessionId"]
application_url = created["ApplicationURL"]
```

保存 `SessionId`、`ApplicationURL` 和两个截止时间。将 `ApplicationURL` 安全地提供给指定终端用户，不要打印或写入普通日志。

<span id="right-auth-letter-query-and-download"></span>
### 查询并下载

终端用户提交申请后，或收到并验证回调后，使用已保存的 `SessionId` 查询。以下代码最多等待两分钟；返回 `None` 仅表示本轮未等到结果。

```python
file_info = wait_for_file("<SESSION_ID>", wait_seconds=120)
if file_info is not None:
    download_file(file_info, "authorization-letter.pdf")
```

稍后可以继续查询同一 Session，不要因为本轮等待超时而重新创建申请。

<span id="right-auth-letter-verify-callback"></span>
### 验证回调签名

将收到的原始请求体字节传给 `verify_callback`，不要重新序列化 JSON 后再验签。

```Python
import base64
import hashlib
import hmac
import re
import time


def verify_callback(raw_body, timestamp, signature, secret):
    if not isinstance(raw_body, bytes):
        return False
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", secret):
        return False
    if not re.fullmatch(r"[0-9]{1,12}", timestamp):
        return False
    if abs(time.time() - int(timestamp)) > 300:
        return False
    if not re.fullmatch(r"v1=[0-9a-f]{64}", signature):
        return False

    key = base64.urlsafe_b64decode(secret + "=")
    if len(key) != 32:
        return False
    message = timestamp.encode("ascii") + b"." + raw_body
    expected = "v1=" + hmac.new(key, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

> **注意**
>
> 运行创建申请的代码会写入真实申请记录。正式接入前，使用具备接口权限的账号完成端到端验证。创建请求超时后不要自动重试。

<span id="right-auth-letter-integration-notes"></span>
## 接入注意事项

- 申请链接只提供给指定终端用户。申请链接和下载链接均可直接访问相应内容，不要公开或写入普通日志。
- AK/SK 和 `Callback.Secret` 仅保存在您的服务端，不要发送给浏览器或终端用户。
- `ApplicationURL` 用于填写申请，`File.URL` 用于下载授权书，不要混用。
- 保存您的订单或业务编号与 `SessionId` 的对应关系。向终端用户提供下载文件前，确认终端用户有权查看该业务记录。

> **说明：正式接入前验证完整流程**
>
> 确认账号权限和页面入口已开通，并验证选择 IP、创建链接、终端用户填写提交、接收通知、查询结果和下载文件的完整流程。同时验证申请过期、处理失败和授权书作废时的业务提示。

<span id="right-auth-letter-faq"></span>
## 常见问题

<span id="right-auth-letter-faq-ip-unavailable"></span>
### 已领用真人 IP 但不能申请授权书

已领用且授权有效仅表示当前账号可以使用该真人 IP。只有 `SupportsAuthLetterApplication` 明确为 `true` 时，该 IP 才支持申请授权书。

<span id="right-auth-letter-faq-expired-callback"></span>
### 失败回调对应的查询状态是 `EXPIRED`

终端用户未提交且申请入口过期时，回调状态可能为 `FAILED`，查询状态为 `EXPIRED`。回调用于触发处理，最终状态以查询接口为准。

<span id="right-auth-letter-faq-create-timeout"></span>
### 创建接口超时后能否直接重试

不能。超时不表示服务端一定未创建 Session，直接重试可能产生多个申请记录和链接。根据业务记录和服务端日志确认结果；确需重新创建时，只向终端用户提供新链接。

<span id="right-auth-letter-related-documents"></span>
## 相关文档

- [使用视频生成 API 创作真人 IP 视频](/docs/real-person-ip-video-api)
- [查询已授权商业 IP 列表](/docs/list-authorized-commercial-ip-ids-api)
- [创建授权书免登申请会话](/docs/create-right-auth-letter-application-session-api)
- [查询授权书免登申请会话](/docs/get-right-auth-letter-application-session-api)
