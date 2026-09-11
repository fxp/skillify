# Webhook 事件订阅与向 TAPD 推送事件

> 来源：`https://open.tapd.cn/document/api-doc/` 下「API文档/api_reference/webhook/webhook_document」「快速入门/开发应用/使用Webhook-云端」
> 「快速入门/开发应用/应用权限控制」「next/webhook/」「API文档/api_reference/open_app_events/push_events」（抓取于 2026-09-11）。
> **文档版，未用真实凭证验证，也没有真正收到过 TAPD 推送。** 报文结构全部是「文档原文，未实测」。

## 目录
1. 两条接入渠道，先分清
2. 渠道 A：开放应用「事件订阅」
3. 渠道 B：传统 Webhook（申请制）
4. 事件名与报文字段
5. 怎么验证请求来自 TAPD
6. 接收端参考实现（Flask）
7. 反向：`POST /open_app_events/hook` 向 TAPD 推送事件
8. ⚠ 本文件汇总

---

## 1. 两条接入渠道，先分清

| | 渠道 A：开放应用事件订阅 | 渠道 B：传统 Webhook |
|---|---|---|
| 在哪配置 | 开发者后台 → 选择应用 → 应用开发 → **事件订阅** | 左下角头像 → **问题反馈** 提交申请（提供项目 ID 或公司 ID、事件、URL、验证密码、数据格式） |
| 前置条件 | 申请应用发布 → 在项目内**安装应用**后才会推送 | 人工开通 |
| 数据格式 | `application/json` 或 `application/form` 可选 | `json` 或 `form`（x-www-form-urlencoded），**默认 form** |
| 事件范围 | 发布评审、缺陷、需求等；只推送应用有**应用权限**的模块 | 需求 / 缺陷 / 任务的创建、更新、状态变更、删除；发布评审创建、更新；前后置对象绑定 / 解绑 |
| 验证 | 可选 `secret`；另有「网关 Token」（TAPD 与目标机器网络不通时用） | 可选「验证密码」 |
| 来源页 | 使用Webhook-云端、next/webhook/ | webhook_document |

两条渠道的报文字段基本一致（见第 4 节），渠道 A 多出 `app_id`、`queue_id`、`referer`、`rio_token`、`devproxy_host` 等字段。

## 2. 渠道 A：开放应用「事件订阅」

配置参数（使用Webhook-云端.html 原文）：
- **URL**：Webhook 地址，输入后会自动检测连通性
- **触发事件**：支持发布评审、缺陷、需求等多个对象的相应事件
- **内容类型**：`application/json` 和 `application/form`
- **网关 Token（可选）**：TAPD 与目标机器网络不通时，开发者配置的应用网关 Token
- **secret（可选）**：验证密码

步骤：配置事件订阅 → 版本管理与发布，申请应用发布 → 在项目内安装应用 → 满足触发事件时推送。
next/webhook/ 还提到另一种方式「推送事件信息到用户自定义方法（需要进行代码配置）」，细节在插件开发文档，本 skill 不覆盖。

<!-- Gap: next/webhook/ 页链接的「事件映射」https://open.tapd.cn/document/api-doc/next/webhook/事件映射.html 与「配置webhook」.../next/webhook/配置webhook.html，无凭证探测（2026-09-11，两次一致）都返回站点兜底页（<title>快速开始 | 开放平台文档），不是事件列表。完整事件名清单在抓取到的文档里拿不到，只能用第 4 节列出的名字。 -->

## 3. 渠道 B：传统 Webhook（申请制）

webhook_document 原文：「现在支持需求、缺陷、任务、发布评审在创建、变更、删除后，往指定 URL POST 相关信息」。
申请时列出的可选事件：需求创建、需求更新、需求状态变更、需求删除、缺陷创建、缺陷更新、缺陷状态变更、缺陷删除、
任务创建、任务更新、任务状态变更、任务删除、发布评审创建、发布评审更新、前后置对象绑定、前后置对象解绑。

**默认数据格式是 form**（`key1=value1&key2=value2`，key、value 都经过 urlencode），不是 JSON——接收端只读 JSON body 会拿到空。

## 4. 事件名与报文字段

### 事件名（文档中出现过的全部写法）
| 对象 | 创建 | 更新 | 状态变更 | 删除 |
|---|---|---|---|---|
| 需求 | `story::create` | `story::update` | `story::status_change` | `story::delete` |
| 缺陷 | `bug::create` | `bug::update` | `bug::status_change` | `bug::delete` |
| 任务 | `task::create` | `task::update` | ⚠ 未给出事件名 | `task::delete` |
| 发布评审 | `launchform::create` | `launchform::update` | — | — |

- `*::status_change` 只在渠道 A 的字段说明里出现（「如：story::update、story::status_change、bug::update、bug::status_change等」）；
  渠道 B 的报文示例只列了 create / update / delete 三类 ⚠ 文档未说明渠道 B 的状态变更事件名。
  稳妥做法：同时处理 `*::status_change`，以及 `change_fields` 里含 `status` 的 `*::update`。
- 前后置对象绑定 / 解绑的事件名 ⚠ 文档未给出。

### 创建 / 删除类报文（webhook_document）
| 字段 | 类型 | 说明 |
|---|---|---|
| `event` | string | 事件名 |
| `event_from` | string | 触发来源：`web`、`api`（渠道 A 另有 `tpa-timer` 等） |
| `workspace_id` | integer | 项目 ID |
| `current_user` | string | 操作人昵称 |
| `event_id` | integer | 事件 ID |
| `id` | integer | 对象 ID，需求 / 缺陷 / 任务 / 发布评审都是 **19 位长 ID** |
| `secret` | string | 双方约定的验证密码 |
| `created` | datetime | 事件触发时间，格式 `Y-m-d H:i:s`，如 `2011-11-11 11:11:11` |

### 更新类报文额外字段
| 字段 | 类型 | 说明 |
|---|---|---|
| `old_*` | string | 一系列 `old_字段名`，**变更前**的值（如 `old_status`、`old_owner`） |
| `change_fields` | string | 发生变更的字段，`,` 分隔 |

文档原文：「如果需要拉取最新数据，建议配合 tapdapi 使用」——报文里**只有旧值，没有新值**。要拿新值，用 `id` 再调 `GET /bugs?workspace_id=&id=`（或 stories / tasks）。

**更新报文示例**（文档原文，form 解析后，精简）
```
[event] => task::update
[event_from] => web
[workspace_id] => 755
[id] => 1000000755500588953
[old_status] => open
[old_owner] => darohu;
[change_fields] => due
[secret] =>
[created] => 2017-04-14 16:20:52
```

**渠道 A JSON 报文示例**（文档原文）
```json
{
  "event": "story::create", "event_from": "web",
  "referer": "https://xxx/tapd_fe/xxx/story/list?useScene=storyList&groupType=&conf_id=xxx",
  "workspace_id": "xxx", "current_user": "xxx", "id": "1167870009001000028",
  "secret": "", "app_id": "3906", "rio_token": "", "devproxy_host": "http:/xxx.com",
  "queue_id": "130662", "event_id": "42079", "created": "2024-03-26 16:33:05"
}
```
- 字段表写 `id`、`event_id` 是 integer，JSON 示例里却都是**字符串** ⚠ 文档自相矛盾——两种都要能处理，并且一律按字符串存（19 位 ID 在 JS 里会丢精度）。
- 渠道 A 字段说明里有一行 `event.workspace_id`（「触发事件的项目ID」），示例报文中没有这个嵌套结构 ⚠ 文档未说明。
- `created` 不带时区 ⚠ 文档未说明时区。

## 5. 怎么验证请求来自 TAPD

文档里**唯一**的验证手段是报文里的 `secret` 字段：你在配置时填的验证密码，TAPD 原样放进 body 发回来。
- 文档**没有**任何签名 header、HMAC、时间戳或 nonce 的说明 ⚠ 文档未说明。不要照别家平台的习惯去算 `X-Signature` 之类的头——文档里不存在。
- 比较时用常量时间比较（`hmac.compare_digest`），并且**拒绝空 secret**：未配置验证密码时报文 `secret` 为空字符串，空对空会误判通过。
- secret 是明文随请求传输的，回调 URL 必须用 https。
- 重试次数、超时时间、失败重投、投递顺序 ⚠ 文档均未说明。接收端按「可能重复、可能乱序」设计：用 `event_id` 去重，处理前用 API 拉最新数据。

## 6. 接收端参考实现（Flask）

```python
import hmac, os
import requests
from flask import Flask, request

app = Flask(__name__)
SECRET = os.environ["TAPD_WEBHOOK_SECRET"]            # 配置事件订阅 / 申请 Webhook 时填的验证密码
BASE = "https://api.tapd.cn"
AUTH = (os.environ["TAPD_API_USER"], os.environ["TAPD_API_PASSWORD"])
_seen = set()                                          # 生产环境换成 Redis / 数据库唯一键

def parse_payload():
    # 渠道 B 默认 form；渠道 A 可选 json 或 form —— 两种都接
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return {k: ("" if v is None else str(v)) for k, v in data.items()}
    return request.form.to_dict()

@app.post("/tapd/webhook")
def tapd_webhook():
    p = parse_payload()
    if not SECRET or not hmac.compare_digest(p.get("secret", ""), SECRET):
        return "forbidden", 403
    eid = p.get("event_id", "")
    if eid in _seen:
        return "ok"                                    # 重复投递
    _seen.add(eid)

    event = p.get("event", "")
    changed = set(filter(None, p.get("change_fields", "").split(",")))
    if event == "bug::status_change" or (event == "bug::update" and "status" in changed):
        old_status = p.get("old_status")
        r = requests.get(f"{BASE}/bugs", auth=AUTH, timeout=10,
                         params={"workspace_id": p["workspace_id"], "id": p["id"], "fields": "id,title,status"})
        body = r.json()
        if body.get("status") == 1 and body["data"]:
            bug = body["data"][0]["Bug"]
            print(f"缺陷 {bug['id']} {bug['title']}: {old_status} -> {bug['status']}（操作人 {p.get('current_user')}）")
    return "ok"                                        # 尽快回 200；重活放队列
```
- 生产环境把「拉最新数据 + 通知」放到队列异步处理，回调里只做校验、去重、入队。
- `old_status` 等旧值和 API 返回的 `status` 都是英文 key，展示中文用 `GET /workflows/status_map?system=bug`（见 `bugs.md`）。

## 7. 反向：向 TAPD 推送事件（触发自动化规则）

**Endpoint**: `POST /open_app_events/hook`
**用途**: 应用把自己的事件推给 TAPD，触发 TAPD 自动化规则。一次一条。需要 scope `app.event`（scopes 表：「事件推送」）。

**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | 是 | 项目 ID（URL 写成 `?workspace_id=项目ID`） |
| `object_type` | string | 是 | 自动化对象名，如 `AutoDemo` |
| `event_key` | string | 是 | trigger 事件名，如 `trigger_demo` |
| 其他任意参数 | — | 否 | 原文：「其他参数不限，请在插件应用中提供 event_change.handle 方法，供TAPD将参数转为标准自动化规则事件参数」 |

**示例请求**（文档原文）
```bash
curl -u 'api_user:api_password' -d 'workspace_id=10158231&field1=value1&field2=value2' 'https://api.tapd.cn/open_app_events/hook'
```
```python
r = requests.post(f"{BASE}/open_app_events/hook", auth=AUTH, timeout=30,
                  params={"workspace_id": WS},
                  data={"workspace_id": WS, "object_type": "AutoDemo", "event_key": "trigger_demo", "build_id": "123"})
```
**示例响应**：`{"status":1,"info":"success"}`（无 `data` 字段）。

- ⚠ 文档自相矛盾：参数表 `object_type`、`event_key` 必填，文档 curl 示例都没传；URL 写 workspace_id 在 query，示例放在 body。上面的 Python 两处都放。
- 前提是插件应用实现了 `event_change.handle`（插件开发文档，本 skill 不覆盖）。

## 8. ⚠ 本文件汇总
- Gap 1 处：「事件映射」「配置webhook」链接指向不存在的页面，完整事件清单拿不到 — 第 2 节
- 任务状态变更、前后置绑定 / 解绑的事件名未给出；渠道 B 是否有 `*::status_change` 未说明 — 第 4 节
- `id` / `event_id` 字段表写 integer、示例是字符串 — 第 4 节
- `event.workspace_id` 字段含义与示例不符；`created` 无时区 — 第 4 节
- 无签名机制；重试、超时、顺序均未说明 — 第 5 节
- `open_app_events/hook` 必填参数与示例矛盾，workspace_id 位置不一致 — 第 7 节
