# 用 GLM Coding Plan（Pro）+ openai SDK 批量补写 Python docstring

脚本文件：`add_docstrings.py`（同目录）。下面先说 Coding Plan 用户最容易踩的几个坑，再讲用法。

## 一、先看这几点，和标准 API 不一样

你手里是 **GLM Coding Plan 套餐 Key**，它和开放平台"按量付费"的 Key 是两套隔离的体系，写代码时有四处必须对上：

| 项目 | Coding Plan 套餐（你的情况） | 开放平台标准 API |
| :--- | :--- | :--- |
| Key 来源 | `https://bigmodel.cn/coding-plan/personal/overview` 里新建 | `https://bigmodel.cn/usercenter/proj-mgmt/apikeys` |
| OpenAI 兼容 Base URL | `https://open.bigmodel.cn/api/coding/paas/v4`（**多一层 `/coding`**） | `https://open.bigmodel.cn/api/paas/v4` |
| 可用模型 | `glm-5.3`、`glm-5.3-flash` | 全部模型 |
| 计费 | 套餐额度：5 小时窗口 + 每周额度双重重置，用完不扣余额 | 按 token 扣余额 / 资源包 |

- **最常见的报错**：套餐 Key 打到了 `…/api/paas/v4`，会返回 HTTP 429 + 业务码 `1113 余额不足或无可用资源包`。**这不是要你充值**，是 Base URL 用错了。脚本默认就是 Coding 端点，而且遇到 1113 会直接停下来打印这条提示，不会盲目重试。
- **Base URL 后面不要再拼 `/v1`**：智谱端点没有 `/v1` 这一级，多拼会 404。`openai` SDK 不会自动追加，直接填到 `…/coding/paas/v4` 即可。
- **`glm-5.3` 强制开启深度思考，无法关闭**（传 `thinking.type=disabled` 会报 1210）。只能用 `reasoning_effort` 调档，且只接受 `low` / `high` / `max`。写 docstring 不需要重推理，脚本默认 `low`——实测 `low` 档思考 token 基本为 0，而套餐额度里输出 token 权重最高（`输入×6.9 + 输出×24`），所以这一项直接决定你的额度消耗。
- **结构化输出**：`response_format: json_schema` 目前会被静默忽略，所以脚本用 `json_object` + 在 prompt 里描述结构 + 客户端解析校验（解析失败 / 漏 key 会自动补一轮）。
- **速率限制按并发数算，不是 QPS**。脚本默认并发 2，对 429（1302/1305/1308/1310）和 5xx 做指数退避；401/403/400 这类配置错误直接终止，不浪费额度。
- **条款提醒（重要）**：官方写明"套餐仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode、Kilo Code、Cherry Studio 等）。自己写脚本打 Coding 端点在技术上能通，但属于条款之外的用法，是否消耗套餐额度、会不会被限制以官方为准；如果这是生产流程，建议用开放平台标准 Key（脚本加 `--standard-api` 即可切换）。

## 二、脚本是怎么工作的（为什么安全）

模型**不直接改写你的代码**。流程是：

1. `ast` 解析每个 `.py`，找出缺 docstring 的模块 / 类 / 函数 / 方法（默认跳过 `_` 开头的私有成员和单行定义 `def f(): return 1`）；
2. 把带行号的源码和目标列表发给 `glm-5.3`，只要它返回 `{"docstrings": {"<key>": "<文本>"}}`；
3. 脚本按每个目标的真实缩进把 docstring 插进去，再 `ast.parse` 校验一遍，通过才写文件。

默认是**预览模式**——只在终端打印 unified diff，不动任何文件。确认没问题再加 `--in-place`（自动备份 `.bak`）或 `--out-dir`。

## 三、安装与运行

```bash
pip install --upgrade "openai>=1.0"

# 套餐 Key，从环境变量读，不要写进代码
export GLM_CODING_PLAN_API_KEY="你的 Coding Plan Key"

# 1) 预览：递归扫描 src/，打印 diff，不写文件
python add_docstrings.py src/

# 2) 确认后原地写回（每个文件先备份成 .py.bak）
python add_docstrings.py src/ --in-place

# 3) 写到另一个目录、英文 NumPy 风格、排除测试文件
python add_docstrings.py src/ --out-dir docstringed/ --lang en --style numpy --exclude 'test_*.py'

# 4) 想省额度：换 glm-5.3-flash
python add_docstrings.py src/ --model glm-5.3-flash --in-place --no-backup
```

跑完会汇总：补写了多少处、失败多少、总输入/输出/思考 token 数，方便你估算套餐额度消耗。

### 常用参数

| 参数 | 默认 | 说明 |
| :--- | :--- | :--- |
| `--in-place` / `--out-dir DIR` | 预览 diff | 写回原文件 / 写到新目录（二选一） |
| `--no-backup` | 关 | 配合 `--in-place`，不生成 `.bak` |
| `--style google\|numpy\|sphinx` | `google` | docstring 风格 |
| `--lang zh\|en` | `zh` | docstring 语言 |
| `--include-private` | 关 | 也处理 `_xxx` 成员 |
| `--skip-module` | 关 | 不补模块级 docstring |
| `--exclude GLOB` | — | 排除文件，可重复 |
| `--model` | `glm-5.3` | 套餐内还可用 `glm-5.3-flash` |
| `--reasoning-effort low\|high\|max` | `low` | 思考强度，无法关闭 |
| `--max-tokens` | 16384 | 单次输出上限（模型上限 131072）；文件很大时调高 |
| `--concurrency` | 2 | 并发文件数，别开太大 |
| `--retries` / `--retry-delay` | 5 / 2s | 429/5xx 指数退避 |
| `--standard-api` | 关 | 改用开放平台 Key（`ZHIPUAI_API_KEY`）和 `…/api/paas/v4` |
| `--api-key-env` / `--base-url` | — | 自定义环境变量名 / 端点 |

## 四、核心调用代码（脚本里的关键片段）

```python
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["GLM_CODING_PLAN_API_KEY"],           # 套餐 Key
    base_url="https://open.bigmodel.cn/api/coding/paas/v4",   # 注意 /coding，末尾不要 /v1
    timeout=300, max_retries=0,   # 退避由脚本接管：SDK 自带重试不认识 1113 这类业务码
)
resp = client.chat.completions.create(
    model="glm-5.3",
    messages=[...],
    temperature=0.3,                                 # 合法区间 (0,1)
    max_tokens=16384,
    response_format={"type": "json_object"},         # json_schema 目前不生效
    extra_body={"reasoning_effort": "low"},          # glm-5.3 思考不可关，只能调档
)
```

## 五、已知限制

- 单行定义（`def f(): return 1`）、语法错误的文件、非 UTF-8 文件会跳过并在日志里说明。
- 每个文件一次请求（1M 上下文足够放整个文件）；超过 `--max-file-chars`（默认 20 万字符）的文件会跳过，可调大或拆分。
- 模型偶尔会漏掉个别目标，脚本会补一轮（`--json-retries`），仍缺的会在日志里标出"N 处模型未返回"，其余照常写入。
- docstring 内容是模型生成的，插入前只做了语法校验，没有做语义核对——写回前请过一遍 diff，尤其是 Args/Raises 部分。
- 5 小时套餐额度用完会收到 429，脚本会退避重试几次后报错退出；额度重置时间是动态的，等一会儿再跑即可。
