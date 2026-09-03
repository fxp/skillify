# 设计说明：如何保证结构化 JSON 输出

## 关键事实（决定了整个设计）

查阅 `bigmodel-cn` 技能包的 `references/chat.md` 第五节后确认：**智谱开放平台目前没有类似
OpenAI `response_format.type = "json_schema"` 的原生"严格 JSON Schema 强约束"模式**。
`response_format` 只支持两个取值：

- `text`：普通文本
- `json_object`：保证返回内容是**语法合法**的 JSON 字符串，但**不保证**符合调用方给定的
  字段结构 / 类型 / 枚举值。

也就是说，"返回结果保证严格符合我给定 JSON Schema" 这件事，服务端无法从根本上保证，
必须在客户端补一层"逼近保证"的机制。这直接决定了脚本的三层设计：

## 三层保证机制

1. **Prompt 层 — 把 schema 明确写进 system message**
   把目标 JSON Schema（含字段名、类型、`enum` 枚举值、`required`）原样序列化后放进
   system prompt，并明确要求"只返回 JSON，不要输出任何多余文字/代码块标记"，
   同时开启 `response_format: {"type": "json_object"}`。这一步把模型跑偏的概率降到最低，
   但仍然只是"尽力而为"，不是强约束。

2. **协议层 — `json_object` 保底语法合法**
   开启 `json_object` 后，至少不用担心模型在 JSON 前后夹带"好的，以下是结果："之类的
   解释性文字，`json.loads` 不会因为多余文字而直接失败（这是该模式唯一能从服务端拿到的
   硬保证）。另外把 `temperature` 设为 `0.1`，降低格式随机跑偏的概率。

3. **应用层 — 二次 schema 校验 + 自动重试修复（真正兜住"合法且合规"的地方）**
   拿到 `content` 后：
   - 先 `json.loads`，失败则捕获 `JSONDecodeError`；
   - 再用 JSON Schema 校验字段是否齐全、类型是否正确、枚举值是否在允许范围内
     （若环境装了 `jsonschema` 库则优先用它做 Draft7 校验；没装则用脚本内置的
     轻量校验器兜底，覆盖 `required`/`type`/`enum`/`additionalProperties` 这几个
     本任务实际用到的 schema 特性，避免强制引入额外依赖）；
   - 任一步失败，把模型刚才的错误输出和具体错误原因作为新一轮 `assistant`/`user`
     消息追加进对话历史，要求模型"重新只输出一个符合 schema 的 JSON"，最多重试
     `MAX_REPAIR_ATTEMPTS`（默认 3）次；
   - 全部尝试失败后，函数**抛出异常**（`RuntimeError`），而不是返回一个可能不合规的
     半成品字典——调用方用 `try/except` 兜底（记日志、转人工等），绝不会把一个没通过
     校验的对象误当作"合法结果"传给下游系统。

这样，`extract_feedback()` 一旦正常返回，调用方可以保证拿到的 dict 一定通过了 schema
校验，不需要在业务代码里再写任何 `try/except json.JSONDecodeError` 或字段存在性判断；
所有容错逻辑都封装在这一个函数内部。

## 其它设计决定

- **模型固定用 `glm-5.3`**（用户指定），并显式设置 `reasoning_effort="low"`：
  `glm-5.3` 强制开启深度思考、无法关闭，只能用 `reasoning_effort` 调节强度
  （仅接受 `low`/`high`/`max`，见 `references/models.md`）。信息抽取是简单任务，
  选 `low` 优先保证延迟和成本；如果实测抽取质量不够稳定，可以调高。
- **API Key 通过环境变量 `ZHIPUAI_API_KEY` 读取**，脚本内没有任何硬编码 Key，
  未设置时会给出明确的中文报错并以非零状态码退出。
- **`issue_type` / `urgency` 的具体枚举取值是本脚本代拟的合理默认值**
  （`issue_type`: billing/technical/shipping/account/complaint/inquiry/other；
  `urgency`: low/medium/high/urgent），因为需求描述里没有给出实际业务方自己的分类体系。
  **这是本次任务中主要的不确定点** —— 落地前需要和真实业务口径核对并替换这几个枚举值。
- **HTTP 调用严格用标准库风格的 `requests`**，按用户要求没有引入智谱官方 SDK；
  `extract_feedback()` 额外支持传入 `requests.Session`，方便做单元测试时 mock HTTP 层
  （已用 mock 验证过：语法错误 JSON、枚举值不合规、始终失败三种场景下的重试与报错行为
   均符合预期）。
- **未实际调用真实 API**：环境中没有可用的 `ZHIPUAI_API_KEY`，按任务要求本脚本没有
  发出过真实网络请求，仅做了 `py_compile` 语法检查和基于 mock `requests.Session` 的
  离线逻辑验证（json 解析失败重试、schema 校验失败重试、多次失败后正确抛异常三个场景
  均通过）。真实联调时的实际输出格式仍需以 `docs.bigmodel.cn` 最新文档 / 实际报错为准。
