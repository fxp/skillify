# Batch API（离线批量推理）

> 状态：文档草稿，基于 2026-09-03 抓取的 platform.moonshot.cn/docs 官方文档 + /docs/openapi.json 撰写，**尚未用真实 API 调用验证**。

适合大规模、对实时性不敏感的任务；文档称相比实时调用可节省 40% 推理成本（定价细节见 docs/pricing/batch，本次未抓取）。

## 先看这三条硬约束（和 OpenAI Batch 的直觉不同）

1. **Batch 只支持 `kimi-k2.7-code` 和 `kimi-k2.6`，不支持 `kimi-k3`**（docs/guide/use-batch-api Note）。
2. 一个 JSONL 文件里**所有行的 `model` 必须相同**；`method` 固定 `POST`，`url` 固定 `/v1/chat/completions`。
3. `body` 里**不要写 `temperature` / `top_p` / `n` / `presence_penalty` / `frequency_penalty`**——这些模型的值不可修改，写了会出错。

流程：构造 JSONL → `POST /v1/files (purpose=batch)` → `POST /v1/batches` → 轮询 `GET /v1/batches/{id}` → `GET /v1/files/{output_file_id}/content` 解析结果。

---

## 1. 输入文件格式

每行一个 JSON 对象：

```json
{"custom_id": "request-1", "method": "POST", "url": "/v1/chat/completions",
 "body": {"model": "kimi-k2.6", "messages": [
   {"role": "system", "content": "你是一个文本分类助手"},
   {"role": "user", "content": "……"}]}}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `custom_id` | 是 | 自定义请求 ID，用于对齐结果，**文件内唯一** |
| `method` | 是 | 固定 `POST` |
| `url` | 是 | 固定 `/v1/chat/completions` |
| `body` | 是 | 与 Chat Completions 请求体一致（见 `chat-completions.md`） |

文件要求：`.jsonl`、非空且 ≤ 100MB；每行合法 JSON 且四个字段齐全；模型必须存在且账号有权限。

来源: docs/guide/use-batch-api

## 2. 上传输入文件

**Endpoint**: `POST /v1/files`，`purpose` **必须**为 `batch`。

```python
import os
from openai import OpenAI
client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

file_object = client.files.create(file=open("batch_requests.jsonl", "rb"), purpose="batch")
input_file_id = file_object.id
```
```bash
curl https://api.moonshot.cn/v1/files -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -F purpose="batch" -F file="@batch_requests.jsonl"
```

## 3. 创建批处理任务

**Endpoint**: `POST /v1/batches`
**用途**: 用已上传的 JSONL 创建异步任务。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `input_file_id` | string | 是 | `purpose=batch` 上传得到的 file id |
| `endpoint` | string | 是 | 枚举只有 `/v1/chat/completions` |
| `completion_window` | string | 是 | 语义化时长，如 `12h`、`24h`、`1d`、`3d`；**最小 12h，最大 7d** |
| `metadata` | object | 否 | ≤16 对；key ≤64 字符，value ≤512 字符 |

```python
batch = client.batches.create(
    input_file_id=input_file_id,
    endpoint="/v1/chat/completions",
    completion_window="24h",
    metadata={"job": "text-classification"},
)
print(batch.id, batch.status)     # 初始 status: validating
```
```bash
curl https://api.moonshot.cn/v1/batches -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input_file_id":"file_xxx","endpoint":"/v1/chat/completions","completion_window":"24h"}'
```

**响应（Batch 对象）**关键字段：
```json
{"id": "batch_xxx", "object": "batch", "endpoint": "/v1/chat/completions",
 "input_file_id": "file_xxx", "completion_window": "24h", "status": "validating",
 "output_file_id": null, "error_file_id": null,
 "created_at": 1720000000, "in_progress_at": null, "expires_at": null, "finalizing_at": null,
 "completed_at": null, "failed_at": null, "cancelling_at": null, "cancelled_at": null,
 "request_counts": {"total": 0, "completed": 0, "failed": 0}, "metadata": null}
```

**状态机**：`validating` → (`failed` | `in_progress`) → `finalizing` → `completed`；超出窗口 → `expired`；取消 → `cancelling` → `cancelled`。
文档提示：窗口越长，越可能在低峰期被调度完成；较短窗口不保证更快。

来源: docs/api/batch-create, schema/batch

## 4. 查询 / 列表 / 取消

| 功能 | Endpoint | 说明 |
|---|---|---|
| 详情 | `GET /v1/batches/{batch_id}` | 返回 Batch 对象；404 不存在 |
| 列表 | `GET /v1/batches?after=<last_batch_id>&limit=20` | 游标分页，响应含 `has_more` |
| 取消 | `POST /v1/batches/{batch_id}/cancel` | 仅 `validating` / `in_progress` / `finalizing` 可取消；先 `cancelling` 再 `cancelled` |

```python
b = client.batches.retrieve(batch.id)
page = client.batches.list(limit=20)          # page.data, page.has_more
client.batches.cancel(batch.id)
```

来源: docs/api/batch-retrieve, batch-list, batch-cancel

## 5. 轮询与取结果

结果文件是 JSONL，每行：
```json
{"custom_id": "request-1", "response": {"status_code": 200, "body": {…ChatCompletion…}}}
```
（`response.body` 就是普通 Chat Completions 响应；失败请求进 `error_file_id` 指向的文件。文档只演示了 `response.body.choices[0].message.content` 的读取，`response.status_code` / `error` 字段的精确结构未给出。）

```python
import time, json

while True:
    b = client.batches.retrieve(batch.id)
    done = b.request_counts.completed if b.request_counts else 0
    total = b.request_counts.total if b.request_counts else 0
    print(f"{b.status} ({done}/{total})")
    if b.status == "completed":
        break
    if b.status in ("failed", "expired", "cancelled"):
        raise RuntimeError(f"batch ended with {b.status}")
    time.sleep(10)

results = {}
for line in client.files.content(b.output_file_id).text.strip().splitlines():
    item = json.loads(line)
    results[item["custom_id"]] = item["response"]["body"]["choices"][0]["message"]["content"]

if b.error_file_id:
    errors = client.files.content(b.error_file_id).text
    print("failed requests:\n", errors)
```
```bash
curl https://api.moonshot.cn/v1/files/$OUTPUT_FILE_ID/content \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" -o results.jsonl
```

来源: docs/guide/use-batch-api §4-5, docs/api/files-content

## 6. 端到端最小示例

```python
import os, json, time
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")
MODEL = "kimi-k2.6"           # 不能用 kimi-k3

texts = ["这家餐厅的服务太差了", "物流很快，包装完好", "一般般吧"]
with open("batch_requests.jsonl", "w", encoding="utf-8") as f:
    for i, t in enumerate(texts):
        f.write(json.dumps({
            "custom_id": f"req-{i}", "method": "POST", "url": "/v1/chat/completions",
            "body": {"model": MODEL, "messages": [
                {"role": "system", "content": "你是文本情感分类助手，只回答 正面/负面/中性"},
                {"role": "user", "content": t}]},
        }, ensure_ascii=False) + "\n")

fid = client.files.create(file=open("batch_requests.jsonl", "rb"), purpose="batch").id
batch = client.batches.create(input_file_id=fid, endpoint="/v1/chat/completions", completion_window="24h")

while (batch := client.batches.retrieve(batch.id)).status not in ("completed", "failed", "expired", "cancelled"):
    time.sleep(10)
assert batch.status == "completed", batch.status

for line in client.files.content(batch.output_file_id).text.strip().splitlines():
    r = json.loads(line)
    print(r["custom_id"], r["response"]["body"]["choices"][0]["message"]["content"])
```

---

## 待验证疑点

- **K3 不能用 Batch**：实测传 `model: kimi-k3` 时是上传校验阶段报错（`failed` 状态）还是创建时直接 400，记录报错原文。
- `body` 里写 `temperature` 会怎样：整批 `failed`、单行进 error file、还是被忽略——文档只说"请勿设置"。
- `completion_window` 接受的格式：`24h` / `1d` / `7d` 都行？`30m`（<12h）的报错文案？
- 结果 JSONL 里 `response.status_code`、单行失败时的 `error` 结构文档未给出，需用一条故意出错的请求（例如超长上下文）实测 error file 格式。
- `output_file_id` 指向的文件是否出现在 `GET /v1/files` 列表里、是否计入 1000 个文件配额、能否删除。
- 结果行顺序是否与输入一致（OpenAI 不保证；文档未说明）——应始终按 `custom_id` 对齐。
- `GET /v1/batches` 的 `limit` 上限未说明。
- 40% 折扣的具体单价与是否计入 RPM/TPM 限速，需看 docs/pricing/batch（本次未抓取）。
- OpenAI SDK 的 `client.batches.*` 方法与本平台字段是否完全兼容（例如 SDK 校验 `completion_window` 只允许 `"24h"` 的字面量类型，传 `"3d"` 可能被 SDK 类型提示拒绝但运行时放行），需实测。
