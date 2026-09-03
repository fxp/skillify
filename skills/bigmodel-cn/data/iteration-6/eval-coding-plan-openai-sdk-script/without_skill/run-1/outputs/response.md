# 用 GLM Coding Plan + openai SDK 批量补 docstring

脚本已写好：`glm_docstring.py`（同目录下还有 `requirements.txt`）。先说几个你一定要知道的点，再讲用法。

## 先看：三个重要提醒

**1. Coding Plan 用的是独立端点，不是普通 API 端点。**
GLM Coding Plan（Lite/Pro/Max）的 key 走的是 coding 专用地址：

- OpenAI 兼容：`https://open.bigmodel.cn/api/coding/paas/v4`
- （Anthropic 兼容：`https://open.bigmodel.cn/api/anthropic`，本脚本不用）

脚本默认就是这个地址。如果你把它填成普通的 `https://open.bigmodel.cn/api/paas/v4`，会走按量付费余额，而不是套餐额度（余额为 0 会直接报错）。反过来，如果你手里是普通按量付费 key，请用 `--base-url https://open.bigmodel.cn/api/paas/v4`。

**2. 套餐条款：Coding Plan 官方定位是"在编程工具（Claude Code / Cline / Roo Code / OpenCode 等）中使用"。**
用自己写的脚本直接调 coding 端点在技术上是通的（就是标准 OpenAI 协议），但它是否属于套餐允许的使用范围，请以你购买时的服务协议和 FAQ 为准。我的建议：这种"批量给一批文件写 docstring"的用途属于编码场景，一般没问题，但请不要把它当通用 API 去跑非编码任务，也不要拿去做高并发服务。另外套餐有 **每 5 小时的用量上限**（Pro 大约是 Lite 的 3 倍），批量跑几百个文件时注意 `--workers` 不要开太大，遇到 429 就降并发。

**3. 模型名请自己核对一下。**
你说的 `glm-5.3` 我按你给的名字写成了默认值，但我没法在线验证这个名字在你的套餐里是否可用。如果返回类似 "model not found / 无权限" 的错误，请到智谱控制台看 Coding Plan 当前支持的模型列表，用 `--model` 或环境变量 `GLM_MODEL` 改掉即可，脚本其他部分不用动。

## 安装与配置

```bash
pip install 'openai>=1.0'
export ZHIPU_API_KEY='xxxxxxxx.xxxxxxxx'   # 智谱控制台里的 API Key
```

脚本按顺序查找这几个环境变量：`ZHIPU_API_KEY` → `ZHIPUAI_API_KEY` → `GLM_API_KEY` → `ZAI_API_KEY`，任一有值即可。
可选环境变量：`GLM_MODEL`（默认 `glm-5.3`）、`GLM_BASE_URL`（默认 coding 端点）。

## 用法

```bash
# 1) 先预览：不改文件，只打印每个文件的 unified diff
python glm_docstring.py ./src

# 2) 确认没问题后真正写入，并保留 .bak 备份
python glm_docstring.py ./src --write --backup

# 也可以直接给文件列表、排除测试文件、英文 + NumPy 风格
python glm_docstring.py a.py b.py utils/ --exclude 'test_*.py' --lang en --style numpy --write
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--write` | 真正写回文件；不加只预览 diff |
| `--backup` | 写回前保存 `文件.bak` |
| `--lang zh/en` | docstring 语言，默认中文 |
| `--style google/numpy/sphinx/plain` | 风格，默认 Google |
| `--include-private` | 也给 `_private` 开头的函数/方法补 |
| `--no-module` | 不写模块级 docstring |
| `--overwrite` | 已有 docstring 的也重写（慎用） |
| `--exclude GLOB` | 排除文件，可重复 |
| `--workers N` | 并发数，默认 4；被限流就调小 |
| `--thinking` | 开启模型思考模式（默认关闭，补 docstring 用不着，关掉更快更省额度） |
| `--model` / `--base-url` | 覆盖模型名 / 接口地址 |

退出码：全部成功 0，有文件失败 2（失败的文件不会被写入，其余照常处理）。

## 脚本是怎么保证"只加 docstring、不动代码"的

很多"让模型返回整份改好的文件"的做法风险很大——模型顺手就把你的逻辑"优化"了。这个脚本不这么干：

1. 用 `ast` 扫描每个文件，找出 **缺少** docstring 的模块、类、函数、方法（`def f(): return 1` 这种单行定义会跳过），记下每个对象的插入行号和缩进。
2. 把源码和"需要补的限定名列表"发给模型，只要求它返回 `{"docstrings": {"Class.method": "文本", ...}}` 这样的 JSON。
3. 脚本自己按行号从后往前把 docstring 插进去（自动处理缩进、多行签名、装饰器、shebang/编码行、`from __future__`、含反斜杠时用 `r"""`）。
4. 插完用 `ast.parse` 再校验一遍，语法不通过的文件直接跳过不写入。
5. 模型漏返回的对象会在结果行里列出来（`模型未返回: ...`），你可以再跑一次只补那些。

所以 diff 里除了 `+` 号开头的 docstring 行（以及类/模块 docstring 后面补的一个空行），不会出现任何其它改动。

## 核心调用代码（如果你想拿去改）

```python
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["ZHIPU_API_KEY"],
    base_url="https://open.bigmodel.cn/api/coding/paas/v4",  # Coding Plan 专用
    timeout=180,
    max_retries=3,      # SDK 自动对 429 / 5xx / 网络错误退避重试
)

resp = client.chat.completions.create(
    model="glm-5.3",
    messages=[{"role": "system", "content": SYSTEM_PROMPT},
              {"role": "user", "content": user_prompt}],
    temperature=0.2,
    extra_body={"thinking": {"type": "disabled"}},  # GLM 默认开思考，这类任务关掉更快
)
text = resp.choices[0].message.content
```

`thinking` 是智谱的扩展参数，openai SDK 本身不认识，所以要通过 `extra_body` 传；如果你的模型/端点不支持该参数而报错，加 `--thinking` 就不会发送它。

## 其它注意事项

- 单文件默认上限 12 万字符（`--max-chars`），超过会跳过而不是硬塞给模型；GLM 上下文很大，一般够用，特别大的文件建议先拆。
- 非 UTF-8 文件、语法错误的文件会跳过并在结果里标 `SKIP` / `ERR`。
- 脚本自动跳过 `.git`、`venv`、`.venv`、`node_modules`、`build`、`dist`、`__pycache__` 等目录。
- 生成的 docstring 是模型写的，**请务必 review diff 再 `--write`**，尤其是对参数含义、异常类型的描述；模型只能看到当前文件，跨文件的上下文它不知道。
- 建议在 git 干净的工作区上跑，这样即使不加 `--backup` 也能 `git diff` / `git checkout` 回退。
