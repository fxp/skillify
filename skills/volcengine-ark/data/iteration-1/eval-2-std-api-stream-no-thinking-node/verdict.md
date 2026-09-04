Result: tie

**Task**: 写一个 Node.js 脚本，用火山方舟标准 API（`/api/v3` + 方舟 API Key）调用豆包 Seed 2.0 lite 做客服问答，要求关闭深度思考、流式输出、结束时打印 token 用量。

**Why**: 两个 run 都 5/5 通过全部断言，故判 tie。baseline 之所以能全对，是因为这个任务的四个关键点在预训练数据里都属常见形态：`https://ark.cn-beijing.volces.com/api/v3` 是方舟被引用最广的一条 Base URL；`stream_options.include_usage` 是 OpenAI 兼容协议的标准写法，与方舟无关；`thinking: {"type": "disabled"}` 是豆包 Seed 1.6 起就广泛出现在博客与示例里的方舟私有字段（baseline 的 NOTES 甚至自己写明「1.6 系列确认支持」）；而 `developer` role 属于「不主动去用就不会错」的断言 —— baseline 只是碰巧没用，并不知道方舟会返回 400，代码里也没有任何校验或说明。相比之下 with_skill 有 `ALLOWED_ROLES` 本地白名单校验 + 专门测试用例，是「知道不能用」，但这个差异被断言的写法抹平了。

baseline 唯一接近失误的地方是模型版本号：它默认 `doubao-seed-2-0-lite-260215`，NOTES 自陈「本文件里的后缀是我凭记忆写的」；with_skill 用的是 skill 模型列表里的 `doubao-seed-2-0-lite-260428`。这不构成失分，因为断言只约束「带日期版本号的 Model ID 形式」而不约束取值，且巧合的是 `260215` 确实是真实存在的版本字符串（verification-findings.md B1 显示 Agent Plan 入口实际服务的就是它）。是否会在生产上出事无法裁定：`/api/v3` 对 Model ID 的精确匹配行为在 ground truth 中属未验证区（§G），Plan 入口的实测（B2）反而显示带日期 Model ID 会被静默换版本 —— 所以「猜错版本号」到底是 404 还是静默降级，本次无从判断。既然无法证明 baseline 会真实失败，按 tie 处理。若要标记，这属于 [guessed-wrong] 的风险面（官方文档确有权威模型列表，agent 没查、凭记忆猜了一个旧版本号），而非 [doc-contradiction]。

需要显式声明的评分口径：本 eval 全部 5 条断言都落在 ground truth 的未验证区间 —— 测试账号只有 Agent Plan Medium 套餐、没有标准 Ark Key，`/api/v3` 的所有行为（Model ID 精确匹配、小写 Model Name 是否被接受、developer role、`stream_options` 语义）均未经真实调用验证。三条被引用为支撑的实测结论（C1 developer → 400、C5 `thinking.disabled` 在 doubao-seed-2.0-lite 上生效、C9 流式 usage 只在末尾 chunk）全部来自 `/api/plan/v3` 入口，用于标准入口属跨入口推断。因此两份 grading.json 的每条 evidence 都按**文档保真度**判定并已注明。这也意味着本 eval 目前只能证明「两个 run 都符合官方文档」，不能证明「两个 run 都能跑通」；拿到标准 Ark Key 后应优先补测 `/api/v3` 的 Model ID 匹配行为，再重跑本 eval。
