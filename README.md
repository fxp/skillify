# skillify

把 SaaS / 开放平台的开发者文档，变成 AI Agent 可以直接拿去写代码的 Claude Skill——不是"把文档丢给 Agent 转述一遍"，而是**读文档打草稿 → 用真实 API Key 逐条验证 → 用真实前后对照实验证明技能确实有用**再交付。

方法论本身也是一份 Skill：[`skills/generate-skill-from-api-docs`](skills/generate-skill-from-api-docs)。

## Skills

| # | Skill | 覆盖范围 | 状态 |
| :-- | :-- | :-- | :-- |
| 1 | [`bigmodel-cn`](skills/bigmodel-cn) | [智谱AI开放平台](https://bigmodel.cn)（`open.bigmodel.cn`）—— GLM 系列对话/多模态模型、图像与视频生成、语音识别合成、Embeddings/Rerank、联网搜索、文件与批处理、托管知识库、Agents API、GLM-Realtime、OpenAI/Claude/LangChain 兼容层 | ✅ 已生成，5 轮共 14 个场景真实 API 对照验证，7 处文档偏差已修正 |
| 2 | `autodl` | [AutoDL 文档](http://www.autodl.com/docs/) —— GPU 算力租用平台的 API | 🚧 下一个案例，尚未生成 |

每个 skill 目录下都是一份可以直接安装使用的 SKILL.md + `references/`；`bigmodel-cn` 额外带了 `data/` 目录，是生成过程中 5 轮真实 API 对照测试的完整留档（prompt、打分依据、真实调用报错原文），不只是一个"通过率"数字。

## bigmodel-cn 的验证结果

用同一个 prompt 分别跑"读了 skill 的 Agent"和"完全凭自己知识写代码的 Agent"，用真实 `open.bigmodel.cn` API 调用结果打分，不是靠代码审查猜测：

- **14 个场景，7 个场景两版代码打平**（说明预训练知识本身已经覆盖到，技能包在这些地方不构成差异）
- **7 个场景里，没装技能包的版本会在真实调用下失败**——典型如：OpenAI 风格的强制 `tool_choice` 在这个平台被静默降级成 `auto`；`response_format: json_schema` 不报错但被静默忽略；GLM-5.3 无法关闭深度思考（换成 GLM-5.2 又完全没这个限制）；Batch 批处理接口只认一份和主力模型清单完全不重合的模型白名单；把 PDF 直接传进对话消息时，`purpose=agent`/`code-interpreter` 上传的文件会在解析阶段静默失败，只有 `purpose=user_data` 才行

详见 [`skills/bigmodel-cn/data/comparison-report.html`](skills/bigmodel-cn/data/comparison-report.html)。

## 用法

把某个 skill 目录整份复制到你的 Claude Skills 目录（或用 `skill-creator` 的 `package_skill.py` 打包成 `.skill` 文件安装），Agent 会在检测到相关任务时自动读取。
