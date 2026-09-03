# skillify

把 SaaS / 开放平台的开发者文档，变成 AI Agent 可以直接拿去写代码的 Claude Skill——不是"把文档丢给 Agent 转述一遍"，而是**读文档打草稿 → 用真实 API Key 逐条验证 → 用真实前后对照实验证明技能确实有用**再交付。

方法论本身也是一份 Skill：[`skills/generate-skill-from-api-docs`](skills/generate-skill-from-api-docs)。

## Skills

| # | Skill | 覆盖范围 | 状态 |
| :-- | :-- | :-- | :-- |
| 1 | [`bigmodel-cn`](skills/bigmodel-cn) | [智谱AI开放平台](https://bigmodel.cn)（`open.bigmodel.cn`）—— GLM 系列对话/多模态模型、图像与视频生成、语音识别合成、Embeddings/Rerank、联网搜索、文件与批处理、托管知识库、Agents API、GLM-Realtime、OpenAI/Claude/LangChain 兼容层 | ✅ 已生成，5 轮共 14 个场景真实 API 对照验证，7 处文档偏差已修正 |
| 2 | [`autodl`](skills/autodl) | [AutoDL 文档](http://www.autodl.com/docs/) —— GPU 算力租用平台的账户/容器实例/弹性部署 API | ⚠️ 已生成 + 文档保真度对照测试通过（100% vs 40%），**但未做真实调用验证**（没有可用的 API Token），内容忠实转录自官方文档 |

每个 skill 目录下都是一份可以直接安装使用的 SKILL.md + `references/`，外加一个 `data/` 目录留档对照测试的完整过程（prompt、打分依据、报错原文），不只是一个"通过率"数字。`autodl` 是刻意保留的反例——按同一套方法论走完了抓取、结构化撰写、对照测试三步，唯独跳过了最关键的"真实 API 验证"（没有测试用的 Token），SKILL.md 里也如实标注了这一点，而不是假装它和 `bigmodel-cn` 一样可信。

## 验证结果

**bigmodel-cn**（用真实 `open.bigmodel.cn` API 调用结果打分，不是靠代码审查猜测）：

- 14 个场景，7 个打平（预训练知识本身已经覆盖到）
- 7 个场景没装技能包的版本会在真实调用下失败——典型如：OpenAI 风格的强制 `tool_choice` 被静默降级成 `auto`；`response_format: json_schema` 不报错但被静默忽略；GLM-5.3 无法关闭深度思考（换成 GLM-5.2 又完全没这个限制）；Batch 只认一份和主力模型清单不重合的白名单；PDF 传进对话消息时 `purpose=agent`/`code-interpreter` 上传的文件会静默解析失败，只有 `purpose=user_data` 才行

详见 [`skills/bigmodel-cn/data/comparison-report.html`](skills/bigmodel-cn/data/comparison-report.html)。

**autodl**（没有真实 Token，改用"对照官方文档判定谁写对了"打分——这不能替代真实调用验证，只能说明"至少比凭空编强"）：

- 3 个场景，100% vs 40%——没装技能包的版本会编出这个平台并不存在的接口路径和字段：把 GPU 规格 ID 当成可以动态查询的接口（真实是静态文档表格）、账户余额换算系数套用国内支付类 API 常见的"除以100"习惯（真实是"除以1000"）、弹性部署的 `deployment_type` 猜成 `"fixed"`/`"scaling"` 这类通用云平台说法（真实取值是 `ReplicaSet`/`Job`/`Container`）
- 差距比 bigmodel-cn 更明显，因为 AutoDL 相对小众，公开语料对它 API 细节的覆盖比智谱这类头部平台少得多

详见 [`skills/autodl/data/iteration-1/review.html`](skills/autodl/data/iteration-1/review.html)。

## 用法

把某个 skill 目录整份复制到你的 Claude Skills 目录（或用 `skill-creator` 的 `package_skill.py` 打包成 `.skill` 文件安装），Agent 会在检测到相关任务时自动读取。
