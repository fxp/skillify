# NOTES — Agent Plan AFP 剩余额度查询工具

## 交付物

| 文件 | 说明 |
|---|---|
| `ark_afp_quota.py` | 主程序 / 可 import 的模块。查询 5 小时 / 周 / 月（及日）AFP 窗口，剩余 ≤ 10% 打印 `[ALERT]`，退出码 0 正常 / 2 有告警 / 1 出错 |
| `test_ark_afp_quota.py` | 离线单测（`python3 -m unittest test_ark_afp_quota -v`），mock 网络，不需要凭证 |
| `requirements.txt` | 可选依赖（官方 SDK）；不装也能跑 |

用法：

```bash
export VOLC_ACCESSKEY=...   # 火山引擎 Access Key（建议 IAM 子用户、授予方舟权限）
export VOLC_SECRETKEY=...
python3 ark_afp_quota.py                 # 文本表格 + 告警
python3 ark_afp_quota.py --plan --json   # 附带 GetPersonalPlan 套餐状态，JSON 输出
python3 ark_afp_quota.py --threshold 20 --all-windows   # 改阈值，日窗口也参与告警
```

## 选了哪个 API、为什么

**结论：管控面 Action `GetAFPUsage`（`POST https://ark.cn-beijing.volcengineapi.com/?Action=GetAFPUsage&Version=2024-01-01`，body `{}`），可选再调 `GetPersonalPlan`（body `{"Plan":"AgentPlan"}`）拿套餐状态 / 到期时间。**

1. **AFP 额度是账号属性，不在数据面。** 数据面 `/api/plan/v3` 只有推理类 endpoint（`/chat/completions`、`/responses`、`/embeddings`、`/images/generations`…），`GET /models` 等都 404（skill 实测），响应 `usage` 里只有本次 token，不含套餐余量。skill 通用规则明说："想在代码里'查我的 Agent Plan 还剩多少 AFP'……走管控面，不要试图用 API Key。"
2. **`GetAFPUsage` 正好返回题目要的四个窗口**：`Result.AFPFiveHour / AFPDaily / AFPWeekly / AFPMonthly`，每个 `{Quota, Used, SubscribeTime, ResetTime}`，另有 `PlanType`。剩余 = `Quota - Used`。它是个人版专用（企业版席位要用 `GetSeatAFPUsage` / `ListSeatAFPUsage`，本工具不覆盖）。
3. `GetUsageDetails`（按模型 / 按小时明细）不适合：它给的是 token / 张数用量，不是 AFP 余量，还要自己乘抵扣系数，且明细延迟 0.5–1 天。
4. 日窗口只约束图片 / 视频 / 语音 / Harness（这些不受 5 小时 / 周限制），所以默认只对 5 小时 / 周 / 月做告警，日窗口仅展示；`--all-windows` 可纳入。

## 鉴权方案

- **火山引擎 AK/SK + HMAC-SHA256 签名**（Service `ark`、Region `cn-beijing`、Host `ark.cn-beijing.volcengineapi.com`）。管控面所有 Action 页面都写"仅支持 Access Key 鉴权"，方舟 API Key / Agent Plan 专属 Key 的 `Bearer` 在这里无效，所以工具**不读** `ARK_AGENT_PLAN_API_KEY`。
- 凭证只从环境变量 `VOLC_ACCESSKEY` / `VOLC_SECRETKEY`（可选 `VOLC_SESSION_TOKEN` → `X-Security-Token`）读取，与官方 SDK 示例同名；不写配置文件、不打日志。
- 两条传输路径，`--transport auto` 自动选：
  - **sdk**：`volcenginesdkcore.UniversalApi.do_call(UniversalInfo(method="POST", service="ark", version="2024-01-01", action=..., content_type="application/json"), body)`，签名 / 重试交给官方 SDK（skill 建议"用官方 SDK 签名，不要手写"）。
  - **stdlib**：SDK 未安装时，用标准库按官方签名算法（docs/6369/67269）自行签名 + `urllib`；签名头 `SignedHeaders=content-type;host;x-content-sha256;x-date`，Credential scope `<yyyyMMdd>/cn-beijing/ark/request`。对应单测固定时钟校验了头结构与确定性。
- 响应统一按信封处理：`ResponseMetadata.Error.{Code,Message}` → 抛 `ArkMgmtError(code, request_id, http_status)`；`Result` 解包；`Quota`/`Used` 是 **字符串**，用 `Decimal` 解析；时间戳是 **epoch 毫秒**，转本地时区显示。`ResourceNotFound.*` 提示"没有生效中的 Agent Plan"，401/403 或签名类错误提示检查 AK/SK。

## 与 skill 文档不一致 / 需要注意的点（doc-vs-reality）

- **官方 Python SDK 里没有 Plan 系列 Action 的生成方法。** 本地安装 `volcengine-python-sdk 5.0.48` 检查：`volcenginesdkark.ARKApi` 只有 17 个方法（endpoint / 批量推理 / 精调 / `get_api_key` 等），**没有** `get_afp_usage` / `get_personal_plan` / `list_model_rate_limit`。skill `management-api.md` §1 的骨架 `api.get_personal_plan(volcenginesdkark.GetPersonalPlanRequest(...))` 与 `errors-and-limits.md` §6 的 `api.list_model_rate_limit(...)` 在当前 SDK 版本会 `AttributeError`。正确的 SDK 路径是 `volcenginesdkcore.UniversalApi`（SDK 自带的通用 Action 调用器），本工具即采用此法。建议 skill 更新此骨架。
- 未做真实调用（无 AK/SK），因此 **`GetAFPUsage` 的响应字段名、`Quota`/`Used` 的字符串类型、毫秒时间戳** 均按文档实现；解析器对缺字段 / 非数字 / 空 `Result` 有防御，但真机第一次跑请用 `--verbose --json` 核对一次原始结构。
- 文档把 `GetAFPUsage` 页的 AFP 展开写成 "Agent Frame Point"，产品页是 "Agent Fuel Point"，不影响调用。
- 管控面响应信封的顶层结构（`ResponseMetadata` + `Result`）是火山引擎 OpenAPI 通用形态，skill 标注"文档未说明"；本工具同时兼容"整信封"和"已解包 Result"两种返回。
