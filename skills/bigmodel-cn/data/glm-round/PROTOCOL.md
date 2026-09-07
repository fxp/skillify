# GLM-5.3 执行器轮 · 协议（开跑前冻结）

**变量**：执行 Agent 从 Claude 换成 **GLM-5.3**（Claude Code CLI 作为 harness，
`ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic` + Coding Plan Key，
`ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.3`）。Claude Code 是智谱官方列出的套餐支持工具。

**保持不变**：两边都能用 WebFetch 查官方文档（已验证在 GLM-5.3 下可用）；每配置 3 次；
判分 100% 由脚本执行真实 API 的结果决定。

两个场景都比前几轮复杂：多步骤、中间态会静默出错、且**官方文档本身写错或没写**。
被测脚本用的是**标准 API Key**（Batch 与文件接口不在套餐内），经环境变量 `ZHIPUAI_API_KEY` 注入。

## 场景 A · batch-pipeline

把 `comments.txt` 的 20 条评论用 **Batch API** 批量做情感分类（省一半钱），
构造 `.jsonl` → 上传 → 创建 batch → 打印 batch id。不要求等结果返回。

**实测确认的两个坑**（2026-09-07 复核仍成立，都在**上传阶段**就报 `1210`）：
- Batch 只认一份白名单，**旗舰模型 `glm-5.3` 不在其中**（报错原文列出白名单：
  `glm-5.1, glm-5-turbo, glm-4, glm-4-0520, glm-4-plus, glm-4-long, glm-4-air, glm-4-air-250414 …`）
- `custom_id` **最短 6 个字符**，写 `r1` / `1` 这类短编号直接被拒（`custom id 长度不足, 最短: 6`）

**判分（满分 3）**：① 退出码 0 ② stdout 出现形如 `batch_数字` 的任务 id ③ 全程无 `1210`

## 场景 B · pdf-contract

从 `contract.pdf` 抽取**合同编号**与**合同总金额**并打印，**不许本地解析 PDF**
（不得使用 PyPDF2/pdfplumber 等），只能上传给模型读。

**实测确认的两个坑**：
- 上传时 `purpose` 必须是 `user_data`；用 `agent` / `code-interpreter` 上传**不报错**，
  但拿它的 `file_id` 去 chat 引用时必定返回 `1210 文件解析失败`
- 必须选支持多模态 `file` 类型的模型（如 `glm-5.3-flash`），纯文本模型读不了

**判分（满分 3）**：① 退出码 0 ② stdout 出现合同编号 `HT-2026-0917-XJ`
③ stdout 出现合同金额（`4870000` / `4,870,000` / `487万` 任一形式）

## 执行环境
每个脚本超时 300 秒；工作目录提供所需素材；Key 仅经环境变量注入，评分器对输出脱敏。
