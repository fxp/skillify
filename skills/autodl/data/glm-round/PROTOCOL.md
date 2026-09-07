# autodl · GLM-5.3 执行轮 · 协议（开跑前冻结）

## 口径

- **执行 Agent**：GLM-5.3。Claude Code CLI 仅作 harness，`ANTHROPIC_BASE_URL` 指向智谱 `…/api/anthropic`，配 GLM Coding Plan Key。
- **被测平台**：AutoDL 开放 API（`https://api.autodl.com`）。
- **对照**：两侧都能 WebFetch 查官方文档；唯一差异是 `with_skill` 先读 `autodl/SKILL.md` 及其 references，`without_skill` 被明确禁止读取该目录与任何 `.skill` 文件。
- **n = 5**，3 场景 × 2 配置 × 5 = **30 次运行**。
- **判分 100% 由脚本真实执行决定**。

## 成本与安全边界（重要）

**三个场景全部只调只读接口**——查余额、查实例状态、查 GPU 库存、查部署列表。
**不创建任何实例、不创建任何部署、不保存镜像、不释放资源**，因此**不产生任何费用**，
也不会改动账号里的任何资源。评分器执行脚本时的环境变量只注入 `AUTODL_TOKEN` 与一个
**故意不存在的** `AUTODL_INSTANCE_UUID`（见场景 2）。

## 场景与冻结判分标准

### 1. `balance-unit`

**任务**：写一个给运维用的余额告警脚本——查账户余额，**可用余额低于 20 元就报警**，并打印可用余额（单位：元）。

**踩的坑**：`wallet/balance` 返回的 `assets` / `blocked_asset` 等金额字段都是**整数，除以 1000 才是"元"**
（实测：真实余额 29.29 元 → `assets = 29290`）。国内支付类 API 常见的是"除以 100"，按那个习惯换算会把
29.29 元显示成 292.90 元，**告警永远不会触发**。而且 `blocked_asset`（冻结金额）文档完全没提，
可用余额应算 `(assets - blocked_asset) / 1000`。整个过程 HTTP 200、无任何报错。

| # | 判分项 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 无未捕获异常 | stdout+stderr 无 `Traceback` |
| 2 | 真的查到了余额 | stdout 出现金额数字 |
| 3 | **换算正确（÷1000）** | stdout 中出现的元值与评分器独立查得的 `assets/1000` 相差 < 0.02 |
| 4 | **扣掉了冻结金额** | 代码中出现 `blocked_asset`，或打印值等于 `(assets-blocked_asset)/1000` |

### 2. `get-params-style`

**任务**：写一个脚本查某台实例的状态，实例 UUID 从环境变量 `AUTODL_INSTANCE_UUID` 读；
要求能**区分「实例不存在」和「请求本身写错了」两种情况**并分别给出提示。

**踩的坑**：`GET /api/v1/dev/instance/pro/status` 的**官方文档示例把传参方式写错了**——文档展示的是
"请求 Body 示例"（JSON），但实测把参数放进 `requests.get(url, json={...})` 会直接返回
`{"code":"RequestParameterIsWrong","msg":"请求参数错误"}`；必须用 `requests.get(url, params={...})`。

评分器注入一个**故意不存在**的 UUID，于是两种写法产生两种可区分的真实响应：

- 传参方式**对** → `RecordNotFoundError` / "未查询到相关实例" → 证明请求被正确解析了
- 传参方式**错** → `RequestParameterIsWrong` / "请求参数错误"

| # | 判分项 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 无未捕获异常 | 无 `Traceback` |
| 2 | **传参方式正确** | stdout 出现 `RecordNotFoundError` 或"未查询到相关实例"，且**不出现** `RequestParameterIsWrong` |
| 3 | 正确判定为"实例不存在"而非"参数错误" | stdout 的结论文字指向"实例不存在/未找到"，不指向"参数错误" |
| 4 | 代码用 query string 传参 | 代码中 `requests.get(...)` 使用 `params=`，未对该 GET 使用 `json=` |

### 3. `deployment-permission-probe`

**任务**：我们准备上弹性部署跑推理服务，先探路——**确认账号现在能不能创建部署**，
顺便查一下有没有 4090 库存。要求明确告诉我"不能建"时到底是什么原因。

**踩的坑**：企业认证门槛**不是套在整个弹性部署 API 上，而是按接口区分**——
`POST /deployment/list` 这类涉及账号自有部署资源的接口，未企业认证返回
`{"code":"BadRequest","msg":"无当前资源访问权限"}`；但 `POST /machine/region/gpu_stock`、
`POST /image/private/list` 这类只读查询，个人认证账号照样能调。
把 `BadRequest` 误读成"接口不存在 / 参数写错 / 服务故障"，就会给出完全错误的结论。

| # | 判分项 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 无未捕获异常 | 无 `Traceback` |
| 2 | 真的查到了 GPU 库存数据 | stdout 出现库存查询的真实返回内容（非空 `data`） |
| 3 | **把 `BadRequest` 正确归因为账号认证等级** | stdout 出现"认证"（企业认证/实名认证）作为原因，而非"参数错误/接口不存在/服务异常" |
| 4 | 结论明确（能不能建部署给了确定答复） | stdout 出现明确的能/不能结论 |

## 事前声明

- 判分标准以本文件为准，跑完不再修改。若发现评分器 bug，修正后**全部重判**并在报告中如实记录。
- 只读接口的返回随账号状态变化（余额、库存）。评分器在判分时**独立再查一次真值**做对照，而不是拿写死的数字比。
