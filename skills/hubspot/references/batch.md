# 批量操作：一次请求处理多条记录

目录：[对象 batch 端点](#对象-batch-端点标准对象--自定义对象通用) · [硬上限——不是自动分页](#硬上限——不是自动分页会直接报错) · [Multi-status 错误](#multi-status-错误批量创建时定位哪条失败了) · [大批量同步的节流建议](#大批量同步的节流建议) · [关联的 batch 端点](#关联的-batch-端点另见-associationsmd)

全部内容 ⚠ 文档原文，未实测（整理自 `docs/api-reference/latest/crm/using-object-apis`、`crm/objects/contacts/batch/create-contacts`、`crm/objects/custom-objects/guide`，抓取于 2026-09-21）。

## 对象 batch 端点（标准对象 + 自定义对象通用）

```
POST /crm/objects/v3/{objectType}/batch/create
POST /crm/objects/v3/{objectType}/batch/read
POST /crm/objects/v3/{objectType}/batch/update
POST /crm/objects/v3/{objectType}/batch/upsert
POST /crm/objects/v3/{objectType}/batch/archive
```

标准对象（contacts/companies/deals/...）和自定义对象共用这一套端点形状，唯一区别是 `{objectType}` 换成对应的 `objectTypeId`。

**批量创建**：请求体是 `inputs` 数组，每项和单条创建的请求体形状一样：

```json
{
  "inputs": [
    { "properties": { "email": "one@test.com", "firstname": "Test", "lastname": "One" } },
    { "properties": { "email": "two@test.com", "firstname": "Test", "lastname": "Two" } }
  ]
}
```

**批量读**：`inputs` 数组每项只需要 `{"id": "..."}`；可选顶层 `properties`（数组，限定返回字段）、`idProperty`（用自定义唯一属性代替内部 ID 定位）：

```json
{ "properties": ["dealname", "dealstage"], "idProperty": "uniqueordernumber", "inputs": [{"id": "0001111"}] }
```

用 `POST` 而不是 `GET` 纯粹是因为一次最多传 100 个 ID，容易超出 URL 长度限制，语义上仍然是"只读查询"。**批量读不支持 `associations` 参数**，想要连带关联信息一起批量取回，要用 `references/associations.md` 里的批量关联读端点分开调。

**批量更新**：`inputs` 数组每项 `{"id": "...", "properties": {...}}`。

**批量 upsert**：`inputs` 数组每项 `{"id": "<唯一属性值>", "idProperty": "<属性名>", "properties": {...}}`——用哪个唯一属性判断"存在则更新、不存在则创建"由每一项自己指定，同一批请求里不同项可以用不同的 `idProperty`。

**批量归档（删除）**：`inputs` 数组每项 `{"id": "..."}`，效果同单条 DELETE，移入回收站而非永久删除。

## 硬上限——不是自动分页，会直接报错

**所有对象 batch 端点（不分创建/读/更新/upsert/归档，标准对象和自定义对象一样）单请求最多 100 条 `inputs`。**

超过 100 条**不是**客户端友好地自动分页处理，官方原文明确写"Object API batch endpoints are limited to 100 inputs per request"，超限的具体报错行为⚠ 文档没有给出报错码/报错体样例（是直接 400，还是只处理前 100 条静默丢弃剩余，未实测,是本 skill 优先验证项之一,见 `hubspot-workspace/verification-plan.md`）。**保守假设是会报错而不是静默截断**，写批量导入/同步代码时必须自己在客户端按 100 条一批切分并循环调用，不要假设传 500 条会被自动拆成 5 批处理。

**注意这个 100 条上限只适用于对象 batch 端点**，关联（associations）的 batch 端点是完全不同的一套上限（读 1,000、创建 2,000、归档/移除标签 100，见 `references/associations.md`），不要把两者的上限数字搞混、也不要假设关联 batch 端点也是 100。

## Multi-status 错误（批量创建时定位哪条失败了）

批量创建默认是"全部处理，成功的成功、失败的失败，响应里合并展示"，但要清楚知道**哪一条输入对应哪一条失败结果**，需要给每个 input 加一个自己生成的唯一字符串 `objectWriteTraceId`：

```json
{
  "inputs": [
    { "objectWriteTraceId": "549b1c2a9350", "properties": { "hs_pipeline_stage": "1" } },
    { "objectWriteTraceId": "549b1c2a9351", "properties": { "missing": "1" } }
  ]
}
```

响应里 `results` 数组放成功的记录，`errors` 数组放失败的，每个失败项的 `context.objectWriteTraceId` 对应回你传入的那个 ID，`numErrors` 给失败总数；HTTP 状态码是 **`207 Multi-Status`**（不是 200 也不是纯 400），代码里判断"批量创建是否全部成功"要看 `numErrors`/`errors` 数组是否为空，不能只看 HTTP 状态码是 2xx 就认为全部成功。

不传 `objectWriteTraceId` 时,⚠ 文档未明确说明批量创建遇到部分失败的默认行为是"整批回滚"还是"能成功的照样成功、只是没法定位是哪条失败"，未实测，建议一律带上这个字段以获得确定性行为。

## 大批量同步的节流建议

- 短时间内对同一批记录发起大量 upsert（官方原文举例"几千条公司记录短时间内批量 upsert"）可能触发 **`423 Locked`**，这是一个乐观锁冲突,不是限流,官方建议在收到 423 后**至少等待 2 秒**再重试,而不是立刻重试或者当成致命错误直接终止。
- 大量数据导入场景应优先使用批量端点而不是循环调用单条端点——这不只是效率问题,单条循环调用同样的记录数会更快撞上每 10 秒的 burst 限流(见 `references/errors-and-limits.md`),批量端点每次调用只算一次限流请求,不管里面装了多少条 `inputs`。
- 高频重复读取同一批设置类数据（如属性列表、owners 列表、pipeline 配置）应该在客户端缓存,不要每次业务操作都重新拉一遍——这是官方限流页明确给出的"如果频繁撞限流该怎么办"的第一条建议。

## 关联的 batch 端点（另见 associations.md）

关联相关的批量操作（批量建关联、批量读关联、批量移除关联/标签）走的是完全不同的路径前缀 `/crm/associations/v3/{fromObjectType}/{toObjectType}/batch/*`，**不是** `/crm/objects/v3/.../batch/*` 的变体，上限数字也不同（1,000/2,000/100，不是 100）。完整端点列表、请求体形状、上限对照表见 `references/associations.md` 的"批量关联端点"一节，这里不重复。
