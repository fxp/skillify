# 报错和限制

⚠ 全文档原文，未实测（抓取自 `docs.e2b.dev`，2026-09-21）。下面这些异常行为没有一条是在真实沙箱上触发过的；把每一句"raised when..."都当成文档自己的说法，不是已确认的实测结果。

目录：[异常体系](#异常体系) · [HTTP 层面的报错](#http-层面的报错) · [限流和套餐限制](#限流和套餐限制) · [GPU 支持](#gpu-支持) · [常见配置报错](#常见配置报错)

## 异常体系

Python（`SandboxException`）和 JS（`SandboxError`）是同一套异常体系，只是语言各自的后缀不同（`...Exception` vs `...Error`）。如果错误来自一次 API 响应，两个 SDK 都会把 HTTP 状态码挂在 `status_code`/`statusCode` 上。

| Python | JS/TS | 触发条件（按文档所说） |
|---|---|---|
| `SandboxException` | `SandboxError` | 通用沙箱错误的基类。 |
| `TimeoutException` | `TimeoutError` | 发生了超时——Python 的 docstring 进一步区分了内部原因：`unavailable`（沙箱超时）、`canceled`（请求超过了超时时间）、`deadline_exceeded`（进程/watch 等操作超过了超时时间）、`unknown`（有时是沙箱超时导致请求没被正确处理引起的）。 |
| `InvalidArgumentException` | `InvalidArgumentError` | 传了一个无效参数。 |
| `NotEnoughSpaceException` | `NotEnoughSpaceError` | 磁盘空间不足。 |
| `NotFoundException`（已废弃） | `NotFoundError`（已废弃，JS 参考文档里已加删除线） | 已被下面两个更具体的子类取代——新代码不要再捕获这个。 |
| `FileNotFoundException` | `FileNotFoundError` | 沙箱内找不到某个文件/目录。 |
| `SandboxNotFoundException` | `SandboxNotFoundError` | 沙箱不存在或已经不在运行。 |
| `AuthenticationException` | `AuthenticationError` | 鉴权失败。 |
| `GitAuthException` | `GitAuthError` | Git 鉴权失败（git 集成相关操作）。 |
| `GitUpstreamException` | `GitUpstreamError` | 缺少 Git upstream 跟踪关系。 |
| `TemplateException` | `TemplateError` | 模板用的 `envd` 版本太旧，和当前 SDK 不兼容。 |
| `RateLimitException` | `RateLimitError` | 超过 API 限流。 |
| `BuildException` | `BuildError` | 模板构建失败。 |
| `FileUploadException`（继承自 `BuildException`） | `FileUploadError`（继承自 `BuildError`） | 文件上传失败（比如在模板构建过程中）。 |
| `VolumeException` | `VolumeError` | Volume 相关错误的基类（Volumes 功能——不在本 skill 覆盖范围内）。 |
| `ServiceBusyException`（灰度中） | `ServiceBusyError`（灰度中） | `pause()` 被拒绝，因为节点还在完成同一个沙箱之前的一次快照——此时沙箱**照样在运行、状态完好**，什么都没丢；稍等再重试。**不是** `SandboxException`/`SandboxError` 的子类——如果要按错误类型分支处理，需要单独捕获它。这个特性正在按 region 逐步灰度上线；在还没上线的 region，同样的情况会抛一个通用的 `SandboxError`/`SandboxException`，报错信息以 `503:` 开头，而不是这个专门的类型。 |

**注意事项**
- `NotFoundException`/`NotFoundError` 已经被明确标为废弃，官方推荐用更具体的两个子类——新代码应该捕获 `FileNotFoundException`/`SandboxNotFoundException`（或它们的 JS 版本），而不是这个已废弃的父类。
- 每个来自 API 响应的 SDK 错误都会带上 `status_code`/`statusCode`，如果你更喜欢按 HTTP 状态码而不是异常类型来分支判断，可以用这个。

## HTTP 层面的报错

REST API（`https://api.e2b.app`，鉴权用 `X-API-Key` header——见 SKILL.md）是 SDK 底层实际调用的东西。⚠ 本次没有逐条核实具体 endpoint 的错误响应体格式（这需要真实调用）；已知的是错误可能表现为标准 HTTP 状态码（比如上面 `ServiceBusyError` 对应的 503），而不是一个统一的错误码字段，但这一点未经证实。如果要写绕过 SDK 的原生 HTTP 调用，在没有核实真实响应之前，不要假设一个具体的 JSON 错误结构。

## 限流和套餐限制

| 限制项 | Hobby | Pro | Enterprise |
|---|---|---|---|
| 单沙箱最大 vCPU | 8 | 8+ | 自定义 |
| 单沙箱最大内存 | 8 GiB | 8+ GiB | 自定义 |
| 并发沙箱数 | 20 | 100–1,100 | 1,100+ |
| 沙箱创建速率 | 1/秒 | 5/秒 | 自定义 |
| 并发模板构建数 | 20 | 20 | 自定义 |
| 最大连续运行时长（不暂停） | 1 小时 | 24 小时 | 自定义 |

现象 → 大概率原因（按 E2B 官方面向 Agent 的 SKILL.md 排查表整理，这份表本身也是从文档推导的，本次未独立验证）：
- **并发或创建速率报错**：大概率是一个泄漏/被遗忘的、仍在运行的沙箱占用了并发名额，或者建沙箱的速度超过了套餐允许的创建速率。用 `e2b sandbox list`（CLI）或 `Sandbox.list()` 查一下，把不需要的 `kill()` 掉。
- **沙箱在任务中途突然消失**：超时到期了，`onTimeout` 用的是默认值 `"kill"`。这不是限流问题——见 `references/lifecycle-and-cost.md`。
- **`RateLimitException`/`RateLimitError`**：账号/key 超过了 API 限流（和上面套餐里的*沙箱数量*限制是两回事）——退避重试。

提额度：并发额度加购在 Pro 套餐下可以在控制台的 billing 页自助操作；更高的 Enterprise 额度要走销售（`enterprise@e2b.dev`），按 `faq/increase-concurrency` 页面的说法。

## GPU 支持

**E2B 的沙箱在任何档位都是纯 CPU 的，包括 BYOC。** SDK、CLI、REST API 或模板定义里都没有 GPU 这个维度，定价里也没有 GPU 这一行。不要写请求 GPU 的代码，也不要提出"换个大点的模板就行"这种 GPU 替代方案——这个选项根本不存在。如果一个工作负载需要 GPU 算力，沙箱仍然可以通过公网访问模型厂商的推理 API（沙箱默认有出站互联网访问），这是文档给出的、在纯 CPU 沙箱里使用 GPU 后端模型的正规做法。安装 ML 相关库时用 CPU-only 的包构建——这也是文档里给出的、解决模板构建时常见 `pip install` 失败问题的方法（`faq/pip-install-error`，本次未单独抓取）。

## 常见配置报错

来自 E2B 官方面向 Agent 的 `SKILL.md`（`e2b.dev/SKILL.md`）的排查章节——是从文档推导的，本次未独立验证：

| 现象 | 大概率原因 / 解法 |
|---|---|
| `npm` 对 `@e2b-dev/...` 返回 404 | scope 写错了——不存在 `@e2b-dev/` 这个 npm scope（那只是 GitHub 组织名）。用 `e2b` 或 `@e2b/code-interpreter`。 |
| Node 里报 "Cannot use import statement" / 顶层 `await` 报错 | 项目是 CommonJS 模块脚手架。用 `npx tsx` 跑脚本，或者存成 `.mjs` 文件；只在全新的 `package.json` 里设 `"type": "module"`，不要去改一个已存在的项目。 |
| "Unauthorized"，提示里提到 "expected the e2b_ prefix" | 实际传的值是一个沙箱/模板 ID，或者是别的服务的 token——不要去掉连字符或者加前缀来"修一下"；去控制台重新拿一个 `e2b_...` 开头的值。 |
| "Unauthorized"，提示里提到 "Cannot get the team" | 一个带 `e2b_` 前缀的值，要么复制时被截断了，要么已经被吊销，要么属于和 `E2B_DOMAIN` 指向的不是同一个 region。不要重试同一个值——重新粘贴或者换一个新 key。 |
| "API key is required" | 进程里看不到 `E2B_API_KEY`——SDK 本身**不会**读取 `.env` 文件；检查一下 `.env` 是怎么（或者有没有）被加载进来的（`node --env-file=.env`、`python-dotenv` 等）。 |
