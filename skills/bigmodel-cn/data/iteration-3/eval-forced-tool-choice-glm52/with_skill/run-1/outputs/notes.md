# 设计说明：如何保证 lookup_order 一定被调用

## 关键约束

查阅 `bigmodel-cn` 技能包的 `references/chat.md`（第 436 行）确认：智谱 GLM
`chat/completions` 接口的 `tool_choice` 参数**目前只支持字符串 `"auto"`**，
不支持像 OpenAI 那样传 `{"type": "function", "function": {"name": "..."}}`
去强制模型必须调用某个指定函数。也就是说，"模型必须先查订单再回答"这个业务
规则，**没有任何 API 参数可以从模型侧强制保证**——就算 system prompt 写得
再严格，模型仍然有概率对它认为"无关"的问题（比如打招呼、问天气、问它是谁）
直接跳过工具调用。

## 设计决策：把"强制调用"从模型层移到代码层

因为 API 不提供强制单函数调用，本方案不把这件事的保证寄托在模型的自觉性上，
而是在应用层（Python 代码）无条件执行：

1. 每一轮用户消息进来后，**不询问模型的意见**，代码直接调用真正的
   `lookup_order(order_id)`；
2. 把这次查询伪装成一次标准的 function-calling 回合写回对话历史：先追加一条
   `role="assistant"` 且带 `tool_calls` 的消息（内容是代码自己构造的调用
   请求），再追加一条对应的 `role="tool"` 消息（内容是真实查询结果，
   `tool_call_id` 与上一步对齐）；
3. 之后才把这份已经包含查询结果的完整 `messages` 发给 GLM，模型只是"基于
   已经存在的工具结果"生成最终自然语言回复。

因为 GLM 的 `chat/completions` 是无状态接口——每次请求都是把完整的
`messages` 数组当作历史发过去，服务端并不会校验某条 `assistant` 消息里的
`tool_calls` 是否真的来自上一次模型的真实响应。所以可以由应用层"代替"模型
完成这次调用，模型在语义上完全无法感知区别。

## 为什么这样能做到"绝对不能跳过"

- 这不是一条 prompt 指令，而是 `OrderSupportBot.handle_user_message()` 里
  一段无条件执行的代码路径（`self._force_lookup_order(order_id_for_lookup)`），
  在任何分支下都会先跑一次，跟用户这句话的内容完全无关（哪怕提取不到订单号，
  也会用 `"UNKNOWN"` 占位调用一次，返回"请提供订单号"）。
- 即便 `lookup_order()` 本身抛异常（比如订单系统超时），代码也用 `try/except`
  捕获后把"查询失败"的结果照样写回上下文，而不是静默跳过——保证"工具结果
  （无论成功或失败）先于自然语言回复存在于对话历史中"这一不变量永远成立。
- 之后如果模型自己又想再调用一次 `lookup_order`（比如用户中途提供了新的
  订单号），仍然走标准 function-calling 循环正常处理（`_run_model_loop`），
  这部分保留了 `tools`/`tool_choice: "auto"` 的正常语义，不影响模型的额外
  自主工具调用能力。

## 验证方式

由于没有可用的真实 API Key，未对 `https://open.bigmodel.cn` 发起真实请求。
改为用 `unittest.mock` 风格的手工打桩（替换 `requests.Session.post`）做了一次
离线联调：构造一个完全与订单无关的用户消息（"你好，请问你是谁呀？"），断言
真正发给模型的 `messages` 数组里，在 `user` 消息之后、模型给出任何回复之前，
已经出现了 `assistant(tool_calls=lookup_order)` + `tool(结果)` 这一对消息。
测试通过，证明该机制与用户输入内容无关，100% 触发。

## 其它实现细节

- 订单号识别：`extract_order_id()` 用正则从用户文本里尽力提取订单号（带
  "订单号:" 前缀的和裸字符串两种模式），仅用于确定"查哪个订单"，**不用于
  判断要不要查**——不管有没有提取到，`lookup_order` 都会被调用（提取不到时
  用 `"UNKNOWN"` 占位，`lookup_order` 会返回"未提供有效订单号"）。
- 订单查询本体 `lookup_order()` 当前用内存字典模拟订单数据（`MOCK_ORDER_DB`），
  函数签名和返回结构与真实后端一致，生产环境只需把函数体换成对真实订单系统
  的 HTTP/RPC 调用。
- 错误处理：区分 4xx（配置/参数错误，直接抛出不重试）与 429/5xx（限流/过载，
  按 `references/errors-and-limits.md` 的建议做指数退避重试），符合技能包
  里"必须实现重试与退避""区分错误类型再重试"的通用规则。
- API Key 只从环境变量 `ZHIPUAI_API_KEY` 读取，不硬编码。
