# 错误处理与限流

> ⚠ 本文件全部内容转录自 docs.stripe.com（抓取于 2026-09-21），未经真实 API 调用验证。

## 目录

- [HTTP 状态码](#http-状态码)
- [Error 对象字段](#error-对象字段)
- [四种错误类型](#四种错误类型)
- [卡拒付测试(decline)](#卡拒付测试decline)
- [限流](#限流)
- [SDK 异常映射](#sdk-异常映射)

## HTTP 状态码

| 状态码 | 含义 | 说明 |
|---|---|---|
| `200` | 成功 | — |
| `400` | Bad Request | 常见于缺少必填参数 |
| `401` | Unauthorized | API key 无效或缺失 |
| `402` | Request Failed | 参数本身合法,但请求执行失败(比如卡被拒付) |
| `403` | Forbidden | 这个 key(通常是权限受限的 Restricted Key)没有权限执行该操作 |
| `404` | Not Found | 资源不存在——**包括"用错模式的 key 查询另一个模式的对象 ID"这种情况**,见 [auth-and-modes.md](auth-and-modes.md#test-模式-vs-live-模式两个完全隔离的世界) |
| `409` | Conflict | 请求和另一个正在处理的请求冲突(比如复用了同一个 idempotency key) |
| `424` | External Dependency Failed | 依赖的外部服务出问题导致请求无法完成 |
| `429` | Too Many Requests | 触发限流,见下方"限流"一节,建议指数退避重试 |
| `500`/`502`/`503`/`504` | Server Errors | Stripe 服务端问题,文档原文说"极少见",处理方式见 [idempotency-and-retries.md](idempotency-and-retries.md) |

## Error 对象字段

请求失败时,响应体里的 `error` 对象常见字段：

| 字段 | 说明 |
|---|---|
| `type` | 四种错误大类之一,见下 |
| `code` | 程序可判断处理的简短错误码(如 `card_declined`、`resource_missing`) |
| `decline_code` | 仅卡错误场景:发卡行给出的具体拒付原因(如 `insufficient_funds`) |
| `param` | 若错误跟某个具体参数相关,指出是哪个参数 |
| `message` | 人类可读的错误说明,卡错误场景下**可以直接展示给终端用户** |
| `doc_url` | 指向该错误码说明页面的链接 |
| `request_log_url` | 指向 Dashboard 里这次请求详细日志的链接,排查问题时很有用 |
| `payment_intent` / `setup_intent` / `payment_method` | 若错误发生在涉及这些对象的请求上,带上当时的对象快照 |

## 四种错误类型

| `type` 值 | 含义 | 代码应该怎么处理 |
|---|---|---|
| `card_error` | 最常见的错误类型,客户的卡因为某种原因无法扣款 | 把 `message` 展示给用户,引导换一张卡或换一种支付方式;可以用 `decline_code` 做更细粒度的提示(比如余额不足 vs 卡过期,文案不同) |
| `invalid_request_error` | 请求参数本身不合法(缺必填字段、格式错误等) | 说明是集成代码的 bug,应该在开发/测试阶段就修掉,不应该在生产环境批量出现 |
| `idempotency_error` | 复用了 idempotency key,但这次请求的参数跟第一次不一致 | 检查是不是误用了同一个 key 表示两个不同的操作,生成新 key 重试 |
| `api_error` | Stripe 服务端内部问题,文档原文说"极其少见" | 走重试逻辑,必要时联系 Stripe 支持并附上 `request_log_url` |

## 卡拒付测试(decline)

测试模式下用这些卡号模拟不同拒付原因,完整表见 [Stripe 测试文档](https://docs.stripe.com/testing.md#declined-payments)(⚠ 文档原文,未实测)：

| 场景 | 卡号 | `error code` | `decline_code` |
|---|---|---|---|
| 通用拒付 | `4000000000000002` | `card_declined` | `generic_decline` |
| 余额不足 | `4000000000009995` | `card_declined` | `insufficient_funds` |
| 挂失卡 | `4000000000009987` | `card_declined` | `lost_card` |
| 被报失窃卡 | `4000000000009979` | `card_declined` | `stolen_card` |
| 过期卡 | `4000000000000069` | `expired_card` | — |
| CVC 错误 | `4000000000000127` | `incorrect_cvc` | — |
| 处理错误 | `4000000000000119` | `processing_error` | — |
| 频率超限 | `4000000000006975` | `card_declined` | `card_velocity_exceeded` |

⚠ 提示:CVC 检查只有在请求里**实际传了 CVC** 时才会执行;不传 CVC 的话 CVC 校验直接跳过,不会失败——这意味着"CVC 错误拒付"这张测试卡必须配合传一个三位数 CVC 才能触发预期行为。

拒付卡不能被 `attach` 到 Customer 对象;要模拟"卡能成功绑定、但后续扣款失败"这种场景,用专门的 `4000000000000341`(Decline after attaching)测试卡。

## 限流

| 资源 | 限制 |
|---|---|
| 全局限流(live 模式) | 每秒 100 次请求 |
| 全局限流(sandbox/测试模式) | 每秒 25 次请求 |
| 单个 API endpoint(未特别说明的) | 每秒 25 次请求(`POST /v1/x` 和 `GET /v1/x/{id}` 算不同 endpoint,但同一 endpoint 下不同 ID 的请求算同一个限流桶) |
| PaymentIntents | 每个 PaymentIntent 对象每小时最多 1000 次更新请求 |
| Subscriptions | 每订阅每分钟 10 张新发票 / 每天 20 张新发票 / 每小时 200 次数量更新 |
| Search API | 每秒 20 次读请求(数据密集型分析建议改用 Sigma/Data Pipeline) |

**429 响应**会带一个 `Stripe-Rate-Limited-Reason` header 说明具体撞到了哪类限制(`global-rate`/`endpoint-rate`/`global-concurrency`/`endpoint-concurrency`/`resource-specific`)——如果 429 响应**没有**这个 header,说明限流不是触发原因,可能是对象锁超时(lock timeout)等其他问题。

**处理建议**:指数退避重试;不要用测试环境做压力测试/负载测试(容易触发限流干扰正常联调),需要做负载测试查官方 [load testing 指南](https://docs.stripe.com/rate-limits.md#load-testing)。

## SDK 异常映射

官方 SDK 会把非 2xx 响应转换成语言原生的异常/错误类型,而不需要手动检查 HTTP 状态码,典型模式(以 Python/Node 为例,⚠ 文档原文,未实测)：

```python
try:
    client.v1.payment_intents.create(params=...)
except stripe.CardError as e:
    # 对应 card_error,可以把 e.user_message 展示给用户
    ...
except stripe.InvalidRequestError as e:
    # 对应 invalid_request_error,通常是代码 bug
    ...
except stripe.StripeError as e:
    # 兜底捕获其他 Stripe 相关错误(idempotency_error、api_error 等子类)
    ...
except Exception as e:
    # 非 Stripe 相关的问题(比如网络库本身抛出的异常)
    ...
```

```javascript
try {
  const paymentIntent = await stripe.paymentIntents.create(args);
} catch (e) {
  switch (e.type) {
    case 'StripeCardError':
      // 对应 card_error
      break;
    // 其他 e.type: StripeInvalidRequestError / StripeAPIError / StripeIdempotencyError ...
  }
}
```

具体异常类名以官方 SDK 当前版本为准,不同语言 SDK 命名风格不同,生成代码时按目标语言核对一次官方文档而不是套用其他语言的命名习惯。
