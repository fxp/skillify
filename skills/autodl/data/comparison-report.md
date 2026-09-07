# autodl skill · 价值评测（GLM-5.3 基准）

## 口径声明

**本报告只包含由 GLM-5.3 作为执行 Agent 产出的实验。** 早期用 Claude 模型执行的轮次已从本报告中删除，不作为本基准的任何依据——执行器不同的结果不可合并统计。

- **执行 Agent**：GLM-5.3。Claude Code CLI 仅作 harness，`ANTHROPIC_BASE_URL` 指向智谱 `…/api/anthropic`，配 GLM Coding Plan Key。
- **判分**：100% 由脚本真实执行 `api.autodl.com` 决定。判分标准开跑前冻结于 `glm-round/PROTOCOL.md`。
- **对照**：两侧都能 WebFetch 查官方文档，唯一差异是有没有读 `autodl` 技能。
- **成本**：三个场景全部只读——不创建实例、不建部署、不存镜像，**零费用**。

| 指标 | 值 |
| :--- | :--- |
| 场景数 | 3 |
| 总运行次数 | 30 |
| 统计显著优势（Fisher 双尾 p < 0.05） | **1 / 3** |
| 打平 | 2 / 3 |
| 技能落后 | 0 |
| 实测查出并修正的文档错误 | 11 |

---

## 总表

| 场景 | n | skill | baseline | 满分率 | Fisher 双尾 p |
| :--- | :-: | :--- | :--- | :--- | :--- |
| `get-params-style` | 5 | **1.000 ± 0.000** | 0.550 ± 0.245 | **5/5 vs 0/5** | **0.0079** ✅ |
| `balance-unit` | 5 | 1.000 ± 0.000 | 1.000 ± 0.000 | 5/5 vs 5/5 | 1.0000 |
| `deployment-permission-probe` | 5 | 1.000 ± 0.000 | 1.000 ± 0.000 | 5/5 vs 5/5 | 1.0000 |

原始数据在 `glm-round/`，每次运行的 `outputs/main.py`、`exec_result.json`（含真实 stdout/stderr）、`grading.json` 全部保留。逐轮复盘见 `glm-round/RESULTS.md`。

---

## `get-params-style`：文档写错的地方，查文档救不了你

`GET /api/v1/dev/instance/pro/status` 的**官方文档示例把传参方式写成了"请求 Body"**。实测：

- `requests.get(url, params={...})` → `RecordNotFoundError` / "未查询到相关实例"（请求被正确解析）
- `requests.get(url, json={...})`（**文档示例的写法**）→ `RequestParameterIsWrong` / "请求参数错误"

评分器注入一个**故意不存在**的实例 UUID，"传参方式对不对"就变成两种可区分的真实响应。
任务要求"区分『实例不存在』和『请求本身写错了』"——这一句堵死了绕行路线。

| | 传参方式 | 结论 | 满分 |
| :--- | :--- | :--- | :-: |
| skill 版 | `params=` ×5 | 5/5 正确判为"实例不存在" | **5/5** |
| baseline | `json=` 为主；1 次同时传两种对冲 | 3 次误报成"请求参数错误" | **0/5** |

**两侧都能联网，baseline 也确实去查了官方文档——但文档本身是错的。**
这正是"说明书"相对"查文档"的差异所在：它记的是实测结果，不是文档原文。

那次对冲（同时传 `params=` 和 `json=`）拿到了正确结果却没拿满分：结果项通过，"代码用 `params=` 而非 `json=`"这项不通过。判分标准开跑前就冻结成这样，不为这次结果改动——对冲说明它并不知道正确答案，只是把两条路都试了。

## 两个打平，以及为什么

- **`balance-unit`**：金额是"元 × 1000"的整数（`assets=16800` → 16.80 元），且要减文档没提的 `blocked_asset`。
  本以为 baseline 会按国内支付类 API 常见的"÷100"习惯算错、导致 20 元阈值的告警永远不触发——
  但 baseline **5/5 都换算正确**并正常告警。这条规则联网查得到，不构成区分度。
- **`deployment-permission-probe`**：`deployment/list` 返回 `BadRequest / 无当前资源访问权限`，
  两侧都正确归因为"账号未企业认证"而非接口/服务问题，且都查到了真实 GPU 库存。打平。

两个打平都符合已知规律：**响亮报错 + 查得到的知识**没有区分度。技能的价值集中在文档本身写错、
或错误静默的地方。

---

## 评分器的两次自我纠错（如实记录）

判分过程中我自己写的评分器出过两个 bug，**都会把正确行为判成失败**，都已修正并全部重判：

1. **把否定当成主张**：`deployment-permission-probe` 一开始判成 **skill 0.850 输给 baseline 0.950**。
   真因是技能版明确写了"**不是**接口用错，也**不是**服务故障"，而我的错误归因词表用朴素子串匹配，
   直接命中了这两个**被否定**的词——而且恰好惩罚了更完整的回答（任务本就要求区分三种原因）。
   改为否定语境感知后，两侧都是 1.000。
2. **只读 stdout，对 stderr 视而不见**：`get-params-style` 的 `with_skill/run-2` 判了 2/4，
   但它其实全做对了——正确识别 `RecordNotFoundError`、正确报"实例不存在"、还给了排查建议，
   只是把诊断写到了 **stderr** 并以非零退出码收尾（这是正当的工程实践）。
   改为两个流一起读后该次变为满分；**这处修正对两侧对称生效，baseline 也因此涨了一次**。

两次都是"判分项在测量形式而不是结果"。**纯执行判分比断言判分客观，但评分器本身同样需要被审查。**

---

## 文档修正（11 条）

以下修正来自对真实 API 的直接调用（含一次真实的实例全生命周期实测，总花费约 5 元），与执行 Agent 无关。

| 文件 | 结论 |
| :--- | :--- |
| `instances.md` | GET 接口（`snapshot`、`status`）必须用 query string 传参——**官方文档自己的示例写的是 JSON body** |
| `instances.md` | 未实名认证的账号 `create` 会拿到 `TORealName`，是不可重试的独立错误码 |
| `instances.md` | `create` 会自动开机，不需要也不应该再调 `power_on` |
| `instances.md` | 状态流转有文档没列的中间态（`starting`、`shutting_down`） |
| `instances.md` | 未确认 `shutdown` 就 `release` 是 100% 失败，不是概率性的 |
| `instances.md` | `image/save` 要求实例**已关机**——文档完全没写这个前置条件 |
| `instances.md` | `power_on` 的响应结构与 `power_off`/`release` 不同（`data` 是对象不是 `null`） |
| `instances.md` | 已释放的实例会从"获取实例列表"里静默消失，无法再查回 |
| `account.md` | 余额响应有约 10 个文档没写的字段，包括冻结金额 `blocked_asset` |
| `elastic-deployment.md` | 企业认证门槛**按接口区分**，不是套在整个 API 上 |
| `elastic-deployment.md` | 弹性部署自己的"获取镜像列表"是另一个端点、字段名也不同，但列的是同一批私有镜像 |

### `instances.md` — GET 接口必须用 query string
官方文档给 `GET .../snapshot` 和 `GET .../status` 展示的是"请求 Body 示例"（JSON）。照着传返回
`{"code":"RequestParameterIsWrong","msg":"请求参数错误"}`，只有 `params=` 才行。
**这一条正是 GLM 轮次里唯一拉开显著差距的那个坑**——再认真读官方文档也读不对，因为文档本身是错的。

### `instances.md` — `create` 会自动开机
两次独立的真实创建都验证过：`create` 返回时（或稍后）实例已经是 `running`。
`power_on` 只用来重启一台之前关掉的实例。

### `instances.md` — `release` 必须先确认 `shutdown`
文档原文"否则可能无法释放"读起来像概率性警告。实测是确定性的：对
`starting`/`running`/`shutting_down` 状态释放，100% 被
`{"code":"BadRequest","msg":"请在实例关机状态下执行释放操作"}` 拒绝。

### `instances.md` — `image/save` 要求实例已关机
文档任何地方都没提。对 `running` 实例调用返回
`{"code":"InternalError","msg":"保存实例镜像前，请确保实例是关机状态"}`。
正确顺序是 `power_off` → 轮询确认 `shutdown` → 再 `image/save`。

### `account.md` — 余额字段远多于文档所写
文档写了 3 个字段，真实响应有 14 个，其中 `blocked_asset`（冻结金额）不能花，
只读 `assets` 会高估可用余额。推荐算 `(assets - blocked_asset) / 1000`。

### `elastic-deployment.md` — 认证门槛按接口区分
个人实名（非企业）账号可以正常调用弹性部署的只读接口（GPU 库存、私有镜像列表），
但只要碰到具体部署资源（创建、列表、容器操作、黑名单、时长包）就被
`{"code":"BadRequest","msg":"无当前资源访问权限"}` 拒绝——已对该账号能触达的每个接口逐个确认。

---

## 边界与未解决的问题

- **只测了 3 个场景**，且全部限于只读接口。涉及创建/释放的场景需要真实花钱并改动账号资源，本轮未纳入。
- baseline 有 2 次运行首轮未在 900 秒预算内交付脚本，以**完全相同的预算**重跑后补齐，未放宽任何条件。
- **弹性部署的创建接口及所有依赖 `deployment_uuid` 的管理接口仍未验证**——这是账号级硬阻塞：
  测试账号只有个人实名、没有企业认证，而 AutoDL 要求企业认证才能创建部署。
- n=5，场景由我设计，选题偏差存在。结论只针对 GLM-5.3 这一个执行器，不外推。
