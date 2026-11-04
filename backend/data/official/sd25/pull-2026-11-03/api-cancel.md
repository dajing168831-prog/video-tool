# 取消或删除视频生成任务

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

`DELETE https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{id}`

取消排队中的视频生成任务，或者删除视频生成任务记录。

## 鉴权

本接口支持鉴权方式如下，详情请参见 [Base URL 及鉴权](/docs/base-url-and-authentication)。

* API Key 鉴权，请在 [API Key 管理](https://ark.volcengine.com/region:cn-beijing/apiKey) 页面，获取长效 API Key。

---

<span id="request-parameters"></span>
## 请求参数

### Path 参数

**id** `string` `必选` | 任务 ID

需要取消或者删除的视频生成任务 ID。

任务状态不同，调用 `DELETE` 接口，执行的操作有所不同，具体说明如下：

| 当前任务状态 | 是否支持 DELETE 操作 | 操作含义 | DELETE 操作后任务状态 |
| --- | --- | --- | --- |
| `queued` | 是 | 任务取消排队，任务状态被变更为 `cancelled` | `cancelled` |
| `running` | 否 | — | — |
| `succeeded` | 是 | 删除视频生成任务记录，后续将不支持查询 | — |
| `failed` | 是 | 删除视频生成任务记录，后续将不支持查询 | — |
| `cancelled` | 是 | 删除视频生成任务记录，后续将不支持查询 | — |
| `expired` | 是 | 删除视频生成任务记录，后续将不支持查询 | — |

## 响应参数
本接口无特有的返回参数，成功时 HTTP 状态码为 `200`，返回结构中 `Result` 为空对象 `{}`。


## 代码示例

## 默认

### cURL


#### Request

```bash
TASK_ID="your_task_id"
curl -X DELETE "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY"
```
#### Response

```
{}
```

### Python


#### Request

```python
import os
from arkruntime import Ark

client = Ark(
    api_key=os.environ.get("ARK_API_KEY"),
    base_url="https://ark.cn-beijing.volces.com/api/v3",
)

if __name__ == "__main__":
    try:
        client.content_generation.tasks.delete(
            task_id="<TASK_ID>",
        )
    except Exception as e:
        print(f"failed to delete task: {e}")
```

#### Response

```
{}
```

### Go


#### Request

```go
package main

import (
	"context"
	"fmt"
	"os"

	"github.com/volcengine/ark-runtime-go/arkruntime"
)

func main() {
	client := arkruntime.NewClientWithApiKey(
		os.Getenv("ARK_API_KEY"),
		arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
	)
	ctx := context.Background()

	req := "<TASK_ID>"
	err := client.DeleteContentGenerationTask(ctx, req)
	if err != nil {
		fmt.Printf("delete content generation task error: %v\n", err)
		return
	}
}
```

#### Response

```
{}
```

### Java


#### Request

```java
package com.ark.sample;

import com.volcengine.ark.runtime.models.content_generation.*;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.volcengine.ark.runtime.service.ArkService;
import java.util.concurrent.TimeUnit;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

public class Sample {

    static String apiKey = System.getenv("ARK_API_KEY");

    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service =
            ArkService.builder()
                    .dispatcher(dispatcher)
                    .connectionPool(connectionPool)
                    .apiKey(apiKey)
                    .baseUrl("https://ark.cn-beijing.volces.com/api/v3")
                    .build();

    public static void main(String[] args) throws JsonProcessingException {

        String req =
                "<TASK_ID>";

        service.deleteContentGenerationTask(req);

        service.shutdownExecutor();
    }
}
```

#### Response

```
{}
```
