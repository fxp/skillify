# 校准轮协议（在看到任何输出之前固定）

目的：用比前 7 轮更严格的条件重测两个"已判定为 win"的场景，得到一个可信的收益下限。

## 与前几轮的三处不同

| 维度 | 前 7 轮 | 本轮 |
|---|---|---|
| 重复次数 | 每配置 1 次（第 7 轮 3 次） | **每配置 3 次** |
| baseline 条件 | 禁止联网搜索 | **两边都允许联网**（唯一变量 = 有没有 skill） |
| 判分 | 我写的断言 + 我人工判定，含"有没有提到 X"类 | **100% 由脚本执行真实 API 的结果决定**，无人工判断 |

## 场景 A · json-extraction

**任务**：读 `feedback.txt`（每行一条客户反馈），用智谱模型抽取结构化信息，写出 `out.json`。
要求输出是一个数组，每个元素恰好包含 `name` / `issue_type` / `urgency` 三个键，`urgency` 取值限定 `low|medium|high`。

**已知陷阱**（实测）：`response_format:{"type":"json_schema"}` 被静默忽略，不报错但不生效；只有
`json_object` + prompt 内描述结构 + 客户端校验重试才可靠。

**判分（满分 5）**：
1. 脚本退出码为 0
2. `out.json` 存在且是合法 JSON
3. 顶层是数组且长度 == 8
4. 每个元素的键集合恰好 == {name, issue_type, urgency}（多一个少一个都算不合格，按合格条数比例给分）
5. 每个元素的 `urgency` ∈ {low, medium, high}（按合格条数比例给分）

## 场景 B · forced-tool-call

**任务**：命令行客服机器人，收到任何用户消息都必须先调用 `lookup_order(order_id)` 再回答；
函数每次被调用时必须向 stderr 打印 `[TOOL] lookup_order called`（这条要求对两边同样给出）。

**已知陷阱**（实测）：`tool_choice` 只支持字符串 `"auto"`，传
`{"type":"function","function":{"name":...}}` 不报错但被当成 auto 处理，模型对无关问题会直接跳过工具。

**判分（满分 3）**：用一条与订单无关的消息「今天北京天气怎么样？」运行脚本，检查：
1. 脚本退出码为 0
2. stderr 出现 `[TOOL] lookup_order called`
3. stdout 有非空的最终回答（不是报错栈）

## 执行环境

`ZHIPUAI_API_KEY`（标准 Key）由评分器注入，脚本自己不得硬编码 Key。每个脚本超时 300 秒。
