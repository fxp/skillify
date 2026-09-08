# bigmodel-cn skill · 价值评测（GLM-5.3 基准）

## 口径声明

**本报告只包含由 GLM-5.3 作为执行 Agent 产出的实验。** 早期用 Claude 模型执行的轮次已从本报告中删除，不作为本基准的任何依据——执行器不同的结果不可合并统计。

- **执行 Agent**：GLM-5.3。Claude Code CLI 仅作 harness，`ANTHROPIC_BASE_URL` 指向 `…/api/anthropic`，配 Coding Plan Key。这是智谱官方支持的 Coding Plan 使用方式。
- **被测模型**：脚本自己调用的模型（`glm-5.x`、Batch、文件、Web Search 等）由每个场景决定，与执行 Agent 是两回事。
- **判分**：100% 由脚本真实执行 `open.bigmodel.cn` 决定，不看代码"看起来对不对"。判分标准在开跑前冻结于各轮 `PROTOCOL.md`。
- **对照**：两侧都能 WebFetch 查官方文档，唯一差异是有没有读 `bigmodel-cn` 技能。

| 指标 | 值 |
| :--- | :--- |
| 场景数 | 12 |
| 总运行次数 | 122 |
| 统计显著优势（Fisher 双尾 p < 0.05） | **4 / 12** |
| 打平 | 7 / 12（另 1 个领先但不显著） |
| 技能落后 | 0（修复技能自身缺陷前有 1 次，见下） |
| 四个区分场景合并满分率 | **skill 18/20 vs baseline 1/20，p = 5.8 × 10⁻⁸** |
| 全部 12 场景合并满分率 | skill 54/56 vs baseline 35/56，p = 9×10⁻⁶ |
| 实测查出并修正的文档错误 | 15 |

---

## 总表

| 场景 | n | skill | baseline | 满分率 | Fisher 双尾 p |
| :--- | :-: | :--- | :--- | :--- | :--- |
| batch-best-model | 5 | **1.000 ± 0.000** | 0.000 ± 0.000 | 5/5 vs 0/5 | **0.0079** ✅ |
| pdf-reuse-fileid | 5 | **0.900 ± 0.200** | 0.250 ± 0.000 | 4/5 vs 0/5 | **0.0476** ✅ |
| cited-web-answer（修技能后） | 5 | **0.933 ± 0.133** | 0.600 ± 0.133 | 4/5 vs 0/5 | **0.0476** ✅ |
| async-model-pinning | 5 | **1.000 ± 0.000** | 0.733 ± 0.133 | 5/5 vs 1/5 | **0.0476** ✅ |
| rag-index-embeddings | 5 | 1.000 ± 0.000 | 1.000 ± 0.000 | 5/5 vs 5/5 | 1.0000 |
| plan-1113-fix | 5 | 1.000 ± 0.000 | 1.000 ± 0.000 | 5/5 vs 5/5 | 1.0000 |
| batch-pipeline | 3 | 1.000 ± 0.000 | 1.000 ± 0.000 | 3/3 vs 3/3 | 1.0000 |
| pdf-contract | 3 | 1.000 ± 0.000 | 1.000 ± 0.000 | 3/3 vs 3/3 | 1.0000 |
| json-schema-not-enforced | 5 | 1.000 ± 0.000 | 0.850 ± 0.200 | 5/5 vs 3/5 | 0.4444 |
| token-budget-empty-answer | 5 | 1.000 ± 0.000 | 1.000 ± 0.000 | 5/5 vs 5/5 | 1.0000 |
| kb-id-validation-silent200 | 5 | 1.000 ± 0.000 | 1.000 ± 0.000 | 5/5 vs 5/5 | 1.0000 |
| forced-tool-choice-ignored | 5 | 1.000 ± 0.000 | 1.000 ± 0.000 | 5/5 vs 5/5 | 1.0000 |
| _cited-web-answer（修技能前）_ | 5 | _0.600 ± 0.133_ | _0.667 ± 0.000_ | _0/5 vs 0/5_ | _1.0000_ |

原始数据：`glm-round/`、`glm-round2/`、`glm-round3/`、`glm-round3b/`、`glm-round4/`、`glm-round5/`，每次运行的 `outputs/main.py`、`exec_result.json`（含真实 stdout/stderr）、`grading.json` 全部保留。

---

## 第一轮 — 两个打平，以及为什么

`glm-round/`，n=3，12 次运行。batch-pipeline 与 pdf-contract 双双 1.000 打平。

复盘原因很有价值：**坑要能区分，任务必须先堵死绕行路线**。

- batch 任务没说模型要求，两边都随手挑了便宜的老模型——恰好都在 Batch 白名单里，谁也没踩坑。
- pdf 任务没说要复用文件，6 次运行里有 5 次直接把 PDF 转 base64 内联进 prompt，整条上传链路根本没走到。

这不是技能没用，是题出得没有区分度。第二轮就是照着这个诊断重写任务的。

---

## 第二轮 — 第一次统计显著

`glm-round2/`，n=5，20 次运行。两个场景都从"打平"翻成显著。

### batch-best-model：模型选择的完美分离

任务加了一句真实用户会说的话——"质量要紧，用你能用的最好的模型"。

| | 选的模型 | 结果 |
| :--- | :--- | :--- |
| skill 版 | `glm-5.1` ×5 | 5/5 成功创建 batch |
| baseline | `glm-5.3` ×5 | 5/5 在**上传阶段**就 `400 / 1210 模型名称错误` |

`glm-5.3` 是平台旗舰，看上去就该是"最好的模型"——但 Batch 有一份**独立白名单**，旗舰不在其中，白名单里最强的是 `glm-5.1`。**这条信息只存在于报错信息里，官方文档正文没有列出。**

### pdf-reuse-fileid：静默失败的典型

任务加的约束是"后面还要问很多轮，先上传拿 `file_id` 复用，别每轮重传"——这一句堵死了 base64 内联。

| | `purpose` | 结果 |
| :--- | :--- | :--- |
| skill 版 | `user_data` ×5 | 4/5 满分（失分那次是平台侧 `500 / 1234`，重试三次仍失败，与知识无关） |
| baseline | `file-extract` / `agent` / 未指定 | 5/5 全部 `1210 文件解析失败` |

baseline 的失败方式最值得看：**上传那一步全部成功**，run-1 甚至打印了 `file_id` 并提示"后续可 export 免上传"——所有信号都显示正常，直到引用文件提问时才 400。

---

## 第三轮 — 评测查出了技能自己写错的一条建议

`glm-round3/` + `glm-round3b/`，n=5，20 次运行。

`rag-index-embeddings` 打平（1.000 vs 1.000）：64 条上限会**响亮报错**，而"分批"是任何称职工程师的默认习惯。这类"响亮且符合常识"的坑天然不具备区分度。

`cited-web-answer` 第一次跑出来是**技能输给 baseline**（0.600 vs 0.667）。10 个脚本代码全都写对了——设了 `search_result: true`、读了 `link` 字段——但运行时一条链接都拿不到。逐层排查定位到真因：

| search_engine | 返回条数 | `link` 非空 |
| :--- | :-: | :-: |
| `search_std` | 10 | **0** |
| `search_pro` | 10 | **0** |
| `search_pro_sogou` | 50 | 50 |
| `search_pro_quark` / `_jina` / `_bing` | 10 | 10 |

HTTP 200、条数正常、`title`/`content`/`publish_date` 全齐，唯独 `link` 是空字符串。而技能原文写的是"显式传 `search_engine`（如 `search_pro`）"——**5 个 skill 版忠实执行了这条错误建议，全部拿不到链接**。附带发现：`search_pro_jina`、`search_pro_bing` 这两个可用引擎在官方参数表里根本没有列出。

修正 `tools.md` / `chat.md` 后用同一场景重跑（3b），引擎选择完全分离：

| | 选的引擎 | 满分 |
| :--- | :--- | :-: |
| skill 版 | `search_pro_bing` / `search_pro_quark` ×3 / `search_pro_sogou` | 4/5 |
| baseline | `search_pro` ×5 | 0/5 |

**写错的说明书比没有说明书更糟**——它让 Agent 一致地犯同一个错，而 baseline 的分散反而让它偶尔蒙对。这是本次评测最重要的一条元结论。

---

## 第四轮 — 三个更贴近真实工程的场景

`glm-round4/`，n=5，20 次运行计入基准。

| 场景 | skill | baseline | 结论 |
| :--- | :--- | :--- | :--- |
| plan-1113-fix | 1.000 | 1.000 | 打平 |
| async-model-pinning | **1.000 ± 0.000** | **0.733 ± 0.133** | **5/5 vs 1/5，p = 0.0476** ✅ |

本轮还跑了第三个场景 `kb-upload-readiness`（知识库上传就绪校验），但**已从基准中剔除**：
测试账号的向量化是间歇性失败的（`embedding_stat=2` / `知识不可用，文档损坏`），
两侧满分率都是 3/5，测出来的是账号状态而不是技能差异。10 次运行的原始记录仍留在
`glm-round4/kb-upload-readiness/` 下，但不计入任何统计。

### async-model-pinning：新增的第四个显著场景

任务要求"用异步接口跑 `glm-4.6`，并核对返回里实际用的是不是这个模型"。实测事实是：`POST /async/chat/completions` 会**静默把 `glm-4.6` 换成 `glm-4.7`**（`glm-4.7` 则换成 `glm-4.7-ali`，一个文档里根本不存在的名字），同步接口从不替换。

skill 版 5/5 都读回了 echo 的 `model` 字段、检出不一致并报警；baseline 只有 1/5 做到——其余默认"请求什么就是什么"，直接把不存在的替换当成功路径走完。这类问题在计费对账和可复现性上是硬伤，而它不会报错。

### plan-1113-fix 为什么打平

给了一个报 `1113` 的 Coding Plan 脚本让其修好。`1113` 虽然文案是"余额不足"具有误导性，但它是**响亮的**——两边都能靠试错在换端点后跑通。响亮的错误不构成区分度。

---

## 第五轮 — 一次失败的扩证尝试（如实记录）

`glm-round5/`，n=5，40 次运行。目的是扩大证据面，结果是**四个新场景零显著**。

四个坑都在开跑前用真实探针复现过，全部是 HTTP 200 的静默失败——配方第 ③ 条满足得很干净。
复盘发现**第 ② 条没满足**：

| 场景 | 正确答案官方文档查得到吗 | baseline |
| :--- | :--- | :--- |
| `token-budget-empty-answer` | **查得到**（思考 token 计入 `max_tokens` 是文档写明的） | 5/5 自己关掉了思考 |
| `forced-tool-choice-ignored` | **查得到**（官方参数表写着 `tool_choice` 仅支持 `auto`） | 5/5 没盲目依赖强制调用 |
| `kb-id-validation-silent200` | **半查得到**（响应结构有 `code`；查业务码本就是防御习惯） | 5/5 判对 |
| `json-schema-not-enforced` | **最查不到的一个**（文档只说取值有 `text`/`json_object`，没说传 schema 会被静默忽略） | 3/5，最接近显著（p=0.44） |

**结论：「静默」是必要条件，不是充分条件。真正决定胜负的是第 ② 条——
正确答案在文档正文里查不到，或者文档写反了。** 前四轮那 4 个显著场景全都卡在第 ② 条上；
本轮四个坑有三个是"文档写了、只是容易忽略"，能联网的称职 Agent 自己就查得到，说明书对它没有增量。

这一轮把 bigmodel 的画像从 4/8 稀释到 **4/12**，但也让它更准确：
技能不提升通用编码准确率、不覆盖所有静默陷阱，它的可证明价值集中在
**官方文档查不到、或者文档写反了的静默失败**这一类很窄但很危险的问题上。

---

## 区分度配方（可复用的出题方法）

前后一共 4 个场景打平、4 个显著。对比之后，显著场景无一例外同时满足三个条件：

1. **任务约束堵死了绕行路线**——且这个约束是真实用户会提的（"要最好的模型" / "要复用 file_id" / "要可点击的来源" / "要核对实际模型"）
2. **正确答案不在文档正文里**——Batch 白名单只在报错里；`purpose` 限制与 OpenAPI 规范矛盾；两个可用搜索引擎没进参数表；异步替换全无记载
3. **错误是静默的或延迟暴露**——上传成功不代表能用；`link` 是空串但 HTTP 200；模型被换了但一切正常返回

反过来，**响亮报错 + 常识可解**的坑（embeddings 64 条上限、`1113` 换端点）必然打平。

第五轮进一步证明：**第 ② 条才是决定性的那一条**。四个纯粹"静默"但文档查得到的坑全部打平——
静默是必要条件，不充分。这正是本技能价值的边界：它不提升通用编码准确率，
也不覆盖所有静默陷阱，它专门规避**文档查不到或文档写反了**的那一类静默失败。

---

## 文档修正（15 条）

以下修正全部来自**对真实 API 的直接探针**（`coding-plan-probe.py`、`kb-probe.py` 等，日志见 `kb-verification-log.jsonl`）或上述 GLM 轮次的实跑，与执行 Agent 无关。每条都带实测日期与证明它的报错原文。

| 文件 | 结论 |
| :--- | :--- |
| `coding-plan.md`（新增） | Coding Plan 是独立 Key + 独立端点，不是折扣档 |
| `chat.md` / `models.md` | 异步接口**静默替换模型** |
| `tools.md` / `chat.md` | `search_engine` 决定 `link` 是否为空 |
| `agents-assistant-knowledge.md` | KB 接口任何情况都返回 HTTP 200，真状态在 `body.code` |
| `agents-assistant-knowledge.md` | 上传成功 ≠ 可检索，必须轮询 `embedding_stat` |
| `agents-assistant-knowledge.md` | `glm-4-assistant` 必须 `stream: true`，文档默认值写反 |
| `agents-assistant-knowledge.md` | Agent 响应 `content` 是对象不是字符串 |
| `sdk-and-compat.md` | SDK 调用可以成功却返回空字符串 |
| `chat.md` / `models.md` | "glm-5.3 思考不可关闭"只在标准端点成立 |
| `chat.md` | `web_search.search_engine` 在两个入口要求不一致 |
| `chat.md` | `web_search` 引用需显式 `search_result: true` 才返回 |
| `chat.md` | 聊天里引用文件必须 `purpose=user_data` |
| `files-batch.md` | Batch 只接受固定的带日期模型列表 |
| `files-batch.md` | `request_counts` 是嵌套对象；`custom_id` 有未文档化的 6 字符下限 |
| `realtime.md` | 连接后先到 `session.created`，规范里没有这个事件 |

### `coding-plan.md`（新增）— Coding Plan 是独立 Key + 独立端点

技能原来的首页、`sdk-and-compat.md`、`errors-and-limits.md`、`models.md` 都假设只有一套 Key 和一个 base URL。实测确认第二套体系：`…/api/coding/paas/v4`（OpenAI 兼容）与共用的 `…/api/anthropic`（Anthropic 兼容），Key 来自 Coding Plan 页面，仅 `glm-5.3` / `glm-5.3-flash`，配额走 5 小时 + 7 天双周期。探针另外查出三件文档没说的事：**标准 Key 在 coding 端点上全功能可用**（并非 plan 专属）；`glm-4.6`、`glm-4.5-air` 被静默重路由到 `glm-5.3-flash`；视觉模型 `glm-4.6v` / `glm-5v-turbo` 在 plan 下可用。

`1113` 这个错误码有三个完全不同的成因——用错端点、能力不在计划内、模型不在计划内——而文案统一是"余额不足"。技能里给了固定的三步排查顺序。

### `chat.md` / `models.md` — 异步接口静默替换模型

2026-09-07 实测，读回 echo 的 `model`：`POST /async/chat/completions` 把 `glm-4.6` 变成 `glm-4.7`，把 `glm-4.7` 变成 `glm-4.7-ali`（此名文档中不存在）；`glm-4.5-air` 与 `glm-5.3` 原样通过。同步端点从不替换。任何需要可复现性或计费对账的场景都必须读回 echo 的模型名。

### `agents-assistant-knowledge.md` — 上传成功不等于可检索

上传返回 `200` 加 `data.successInfos` 里的 `documentId`，读起来完全是成功。向量化随后在后台跑，失败时没有任何提示：`POST /knowledge/retrieve` 会永远返回 `200` + `{"code":200,"data":[]}`，和"没有相关内容"无法区分。唯一信号是 `GET /document/{id}` 的 `embedding_stat`（0 处理中 / 1 就绪 / 2 失败）与 `failInfo.embedding_msg`。测试账号上 `.pdf`/`.md`/`.txt` 三种格式都落在 `embedding_stat=2`（`知识不可用，文档损坏`），而存储只用了 5,000,000 字里的 6,196 字——可能是账号维度的问题，但无论如何结论是：**轮询到 `embedding_stat == 1` 再说，别假设**。

### `agents-assistant-knowledge.md` — KB 接口永远不返回失败状态码

`llm-application/open/*` 与 `/zrag/*` 下的每个端点即使调用失败也答 `HTTP 200`，真实结果在 body 的 `code` 里。查不存在的知识库返回 `200` + `{"code":100013,"message":"知识库不存在"}`；multipart 字段名写错返回 `200` + `{"code":400,...}`。`raise_for_status()` 永远不触发，按常规写法搭的 RAG 流水线会把错误静默地带下去。

### `agents-assistant-knowledge.md` — Assistant 示例照抄就报错

原文说 `stream` 默认 `true`，却给了一个 `"stream": false` 的同步示例。2026-09-07 对 `glm-4-assistant` 实测：**不传 `stream` 和传 `false` 都返回 `1212 当前模型不支持SYNC调用方式`**，只有 `true` 才给出 `text/event-stream`。文档默认值写反的方向恰好是会让代码挂掉的方向，而随附示例正是两种失败写法之一。参数表与两处示例均已改正。

### `sdk-and-compat.md` — 调用成功却拿到空字符串

`zai-sdk 0.2.3` + `glm-4.6` 实测：调用返回、`response.model` 正确回显、`choices[0].message.content` 是 `''`。思考 token 计入 `max_tokens`，小预算被推理吃光：

| 配置 | `finish_reason` | `content` | `reasoning_content` |
| :--- | :--- | :--- | :--- |
| `max_tokens=20`（默认开思考） | `length` | `''`（空） | 37 字 |
| `max_tokens=800`（默认开思考） | `stop` | `'巴黎'` | 105 字 |
| `max_tokens=20` + 关思考 | `stop` | `'巴黎'` | 0 字 |

判据是 `finish_reason`，不是空字符串本身。流式等价形式（只收集 `delta.content` 得到空缓冲）也已记录。同时确认 `ZhipuAiClient` → `open.bigmodel.cn`、`ZaiClient` → `api.z.ai`，两个 Maven 坐标均存在。

### `chat.md` / `models.md` — "思考不可关闭"只在标准端点成立

`thinking:{type:"disabled"}` 对 `glm-5.3` / `glm-5.3-flash` 在 `…/api/paas/v4` 返回 `1210`，但在 `…/api/coding/paas/v4` 被接受并返回 `reasoning_tokens: 0`——两种 Key 都是如此。两个端点的参数校验不一致，技能不再给出单一规则。

---

## 评分器的六次自我纠错（如实记录）

纯执行判分比断言判分客观，但**评分器本身同样需要被审查**。四个 bug 都会影响结论，都已修正并重判：

1. **把"声明不使用"误判成"使用了"**：用字符串匹配 `PyPDF2|pdfplumber` 判断是否本地解析 PDF，结果把注释里写着"本地不做任何 PDF 解析（不用 PyPDF2）"的脚本全判违规。改为 **AST 检测真实 import**。
2. **把 batch id 里的数字误判成错误码**：`"1210" in output` 会命中成功创建的 batch id `batch_2096812104876032000`（含子串 `81210`）→ 误扣分；同时另一次真实失败因报错正文未带 `1210` 而漏判。改为**结构化匹配** `code: 1210` 或已知报错文案。修正后 batch 场景 skill 均值从 0.933 变为 1.000。
3. **把正确的报警行为当成失败**：判分项写了"退出码必须为 0"，但脚本检出模型不一致后以非零退出码报警恰恰是正确的工程行为。改为"无未捕获异常"。修正后 async 场景 skill 均值从 0.667 变为 **1.000**。
4. **拿全局真值判每一次运行**：知识库向量化是间歇性的，评分器某一刻测到"不可用"就把所有宣称成功的运行判错——但 `with_skill/run-1` 实际检索到了内容。改为**按次自证**：宣称成功必须有该次运行自身检索到内容的证据，报失败必须有该次运行自身的失败信号。
5. **判实现形状而不是行为**（第五轮）：`forced-tool-choice-ignored` 一开始判成 **skill 0/5 满分输给 baseline 5/5**。原判分项要求代码里必须有 `tool_calls` 的条件分支——但**技能给的正确做法恰恰是"根本不要用 `tool_choice`，在代码里无条件构造工单"**，照做的脚本自然没有这个分支。技能版 5 次工单全部产出完美。改为判行为后 5/5 满分，与 baseline 打平。
6. **否定语境窗口太窄**（第五轮）：`kb-id-validation-silent200` 有 3 次被判成"误报为有效"，而它们的输出其实是「**无法确认**该知识库 ID **有效**，禁止上线」。窗口从 3 字放宽到 12 字后两侧全部满分，**baseline 也受益一次**。

> 第 5 个 bug 尤其值得记：不查就直接写报告，会得出"技能在工单场景显著劣于 baseline"这个**完全错误**的结论。
> **评分器本身就是实验仪器，不校准它，测出来的都是仪器的毛病。**

---

## 边界与未解决的问题

- **场景由我设计，选题偏差存在。** 区分度配方是从数据里总结出来的，但用它出题天然偏向技能擅长的方向。诚实的表述是：技能在"静默 + 未文档化"这一类问题上有 4/9 的显著优势，在其余类型上打平。
- **n=5 是能出 p<0.05 的最小样本量**（5/5 vs 0/5 → p=0.0079；4/5 vs 0/5 → p=0.0476）。任何单次平台抖动都会改变结论，pdf 场景那次 `500 / 1234` 就是例子——我没有为它改动已冻结的判分标准。
- **一个场景因账号状态污染被剔除**（`kb-upload-readiness`，向量化间歇失败）。剔除的理由与数据都写在上面，不是事后挑数据——它两侧同分，剔除既不增也不减技能的胜率。
- **12 个场景里 7 个打平、1 个领先但不显著**，显著优势集中在前四轮的 4 个场景。
- **只测了一个执行器（GLM-5.3）**，结论不外推到其他模型。
- **技能自身出过错**（`search_pro` 那条），说明这类"说明书"必须持续对真实 API 复验，否则会从资产变成负债。每次更新技能都应重跑本基准。

全部运行的转录、逐条判分与真实 stdout/stderr 都在 `bigmodel-cn-workspace/glm-round*/` 下。
