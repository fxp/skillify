# NOTES — 用 Agent Plan 额度批量生成笔记摘要

## 文件

| 文件 | 作用 |
|---|---|
| `summarize_notes.py` | 主脚本：`notes/**/*.md` → `summaries/**/*.md`，每篇三句话摘要 |
| `requirements.txt` | 仅依赖 `openai` SDK（方舟兼容 OpenAI Chat Completions 协议） |
| `.env.example` | 环境变量模板；复制成 `.env` 后 `source` |

```bash
pip install -r requirements.txt
cp .env.example .env && $EDITOR .env && source .env
python summarize_notes.py --dry-run          # 只列出要处理的文件，不发请求
python summarize_notes.py                    # 正式跑
python summarize_notes.py --force            # 重新生成已有摘要
```

## 三个关键选择

### 1. Base URL —— 这是"不扣后付费余额"的决定性因素

方舟的套餐（Coding Plan / Agent Plan）**不是**挂在普通 API Key 的余额上自动抵扣，而是走**独立的接入点**：

- 后付费（按量）接入点：`https://ark.cn-beijing.volces.com/api/v3`  → 扣余额
- 套餐接入点：控制台「Agent Plan / 套餐」页面上显示的 Base URL。Coding Plan 上线时使用的是 `https://ark.cn-beijing.volces.com/api/coding/v3`，脚本以此为默认值。

**请以控制台套餐页上显示的 Base URL 为准**，通过 `ARK_BASE_URL` 覆盖。我没有联网核对当前 Agent Plan 页面的具体路径，所以脚本把它做成显式配置而不是写死。

脚本层面的保护：
- `ARK_BASE_URL` 等于 `/api/v3` 后付费接入点时直接拒绝启动（除非显式加 `--allow-postpaid`）。
- Base URL 的 host 不是 `ark.cn-beijing.volces.com` 时打 warning。

### 2. API Key —— 从环境变量读，绝不落盘

- `ARK_API_KEY` 来自套餐页面绑定的那个 Key（方舟是"Key + 套餐接入点"绑定套餐，Key 本身仍是标准方舟 Key）。
- 脚本只从环境变量读取，不接受命令行参数、不读配置文件；日志只打印前 4 位和后 4 位。
- 加了一个防呆：Key 以 `Bearer ` / `sk-ant` / `sk-proj` 开头时报错（复制错了别家的 Key 或多带了前缀）。

### 3. 模型 —— `doubao-seed-2.0-lite`，并做白名单校验

- 用户指定 `doubao-seed-2.0-lite`；用 model 名直呼（套餐接入点接受 model 名，不需要 `ep-xxx` 推理接入点）。
- **套餐只覆盖套餐页列出的模型**。用套餐接入点调用不在套餐内的模型，要么报错，要么（更糟）回落到按量计费。脚本用 `ARK_PLAN_MODELS` 白名单做 fail-closed：模型不在名单里就拒绝跑。默认名单只含 `doubao-seed-2.0-lite`，请对照套餐页确认它确实在你的 Medium 套餐内，不在的话换成套餐内的同级模型。
- 模型名形如 `ep-...`（自建推理接入点）时打 warning，因为自建接入点是按接入点计费，不走套餐。
- 默认通过 `extra_body={"thinking": {"type": "disabled"}}` 关闭深度思考：三句话摘要不需要推理，关闭后省时延、也省套餐的输出 token 额度。如果接入点不认这个参数（400 提到 thinking），脚本自动去掉它重试一次；`--keep-thinking` 可保留模型默认行为。

## 其他防坑

| 风险 | 处理 |
|---|---|
| 套餐有 RPM / TPM / 5 小时窗口限额，并发太高直接 429 | 默认并发 3；429/超时/5xx 指数退避 + 抖动，尊重 `Retry-After`；最多 5 次 |
| 额度用尽后继续打请求 | 402/403/429 且报文含 "quota" 时立即抛错终止整批，不会静默继续 |
| 中途失败要重跑，重复消耗额度 | 已存在的 `summaries/x.md` 默认跳过，重跑只补失败的；`--force` 才覆盖 |
| 半写文件 | 先写 `.tmp` 再 `os.replace`，原子落盘 |
| 超长笔记撑爆额度 | `--max-input-chars` 默认 6 万字符截断（远低于 256k 上下文，但摘要够用），截断在输出注释里标记 |
| 非 UTF-8 文件 | 先 `utf-8-sig`，失败退 `gb18030` 并 warning |
| 模型不听话不是三句 | 系统提示词严格限定 + 输出清洗（去 "摘要："前缀、列表符号、多段合并）；句数 ≠ 3 时 warning 但仍保存 |
| 对账 | 每次成功调用追加一行到 `summaries/_usage.jsonl`（文件、模型、接入点、prompt/completion tokens），可与控制台套餐用量核对，验证确实没走余额 |
| 子目录 | `rglob` 递归，输出镜像目录结构 |
| 空文件 / 隐藏文件 | 跳过 |

## 上线前建议自查（因为我无法真实调用验证）

1. 打开方舟控制台 → Agent Plan 页面，核对 **Base URL**、**Key**、**支持模型列表**三项，填入 `.env`。
2. 先 `--dry-run` 看文件清单。
3. 先只放 1 个文件正式跑一次，然后去控制台看：套餐用量 +1、余额账单 **无**新增。确认后再放全量。
4. 如果第一次就报 `model not found`，几乎一定是模型不在套餐内或 Base URL 不对，而不是脚本问题。

## 未验证的假设（诚实声明）

- 套餐接入点路径默认取 `/api/coding/v3`。Agent Plan 若使用其他路径（例如独立的 agent 路径），以控制台为准，改 `ARK_BASE_URL` 即可，脚本逻辑不受影响。
- `thinking: {"type": "disabled"}` 是 doubao-seed 2.0 系列在按量接入点上的参数写法；套餐接入点应一致，脚本已做 400 自动降级兜底。
- `doubao-seed-2.0-lite` 是否包含在 Medium 套餐内需在套餐页确认。
