---
name: e2b
description: "接入 E2B（e2b.dev / docs.e2b.dev）云沙箱平台的使用手册——在隔离的 Linux microVM 里运行 AI Agent 生成的代码、shell 命令和文件操作。覆盖以 SDK 为主的接入面：Python `e2b` / `e2b-code-interpreter`，JavaScript/TypeScript `e2b` / `@e2b/code-interpreter` / `@e2b/cli`——涵盖创建/连接沙箱、运行代码（Code Interpreter）和 shell 命令、文件系统读写/上传/下载、生命周期管理（超时、暂停/恢复/快照、自动唤醒）、通过公网 URL 暴露端口，以及按秒计费的用量计费模式。当用户提到 E2B、e2b.dev、`Sandbox.create`、`@e2b/code-interpreter`、`e2b-code-interpreter`，或提到在沙箱/microVM 里运行 AI 生成的代码，或要写代码调用 E2B 的 SDK/API 时，应主动使用本技能——不要凭记忆或套用其他沙箱平台（Modal、Daytona、Replit、CodeSandbox）的接口习惯去编方法名、超时默认值或计费规则，E2B 的生命周期模型和计价模型都和它们不一样。"
---

# E2B —— 面向 AI Agent 代码执行的云沙箱

E2B 让 AI Agent 拥有一个隔离的 Linux microVM（"沙箱"），可以在脱离宿主机的环境里运行生成的代码、shell 命令和文件操作。它几乎完全通过 **SDK** 使用（Python `e2b` / `e2b-code-interpreter`，JS/TS `e2b` / `@e2b/code-interpreter`），而不是手写 REST 调用——本 skill 以 SDK 方法调用作为主要接口来记录，底层 REST API 只在必要处提一句。这一页负责路由和跨领域规则；字段级细节和代码示例都在 `references/` 里。

## ⚠ 验证状态

**本 skill 里的任何内容都没有用真实的 E2B API key 或运行中的沙箱验证过。** 它只完成了 `create-doc-skill` 方法论的第 1–2 步（抓取真实文档、整理结构）——第 3 步（真实 API 验证）和第 4 步（有/无 skill 对照实验）因为撰写时（2026-09-21）没有可用的 API key 而被明确跳过。

- 下面每一条事实性陈述都是 `⚠ 文档原文，未实测`（来自 E2B 官方文档——`docs.e2b.dev` 和 `e2b.dev`，抓取于 2026-09-21），除非另有标注。没有一条经过真实 API 响应、真实报错信息或真实账单的确认。
- 不要把这里的任何代码示例或报错字符串当成"实际跑过"的东西呈现，它们都没有被执行过。
- `evals/evals.json` 里的场景是从文档推演出来的、可信的陷阱假设，不是已确认的失败模式。
- 一旦拿到真实的 `E2B_API_KEY`，在把这份 skill 用于生产之前，先过一遍 `../e2b-workspace/verification-plan.md`，并把每一处 `⚠` 标记就地更新为验证日期和证据。

## 用之前先确认 4 件事

1. **REST API 的 Base URL / 鉴权（如果绕过 SDK 直接调用）：** `https://api.e2b.app`，header 是 `X-API-Key: <key>`。大多数工作根本不需要直接碰这个——SDK 会处理。⚠ 文档原文，未实测（来自 OpenAPI 规范的 `securitySchemes`）。
2. **API key 格式：** 以 `e2b_` 开头。一个带连字符但*没有*这个前缀的值是沙箱/模板 ID，不是 key——不要去掉连字符或加前缀来"修正"它。在 `https://console.e2b.dev/?tab=keys` 获取。通过 `E2B_API_KEY` 环境变量传入（推荐）或构造函数选项 `apiKey`/`api_key`；SDK 本身**不会**读取 `.env` 文件。
3. **包名——不存在 `@e2b-dev/` 这个 npm scope**（那只是 GitHub 组织名）。准确的包名：
   | 运行时 | 核心沙箱 | Code Interpreter | CLI |
   |---|---|---|---|
   | Python (3.10+) | `pip install e2b` | `pip install e2b-code-interpreter`（导入为 `e2b_code_interpreter`） | — |
   | JS/TS（Node 20.18.1+ 或 22+，**不支持 21**） | `npm install e2b` | `npm install @e2b/code-interpreter` | `npm install -g @e2b/cli` 或 `brew install e2b` |
4. **最大的一个坑：默认生命周期短且是破坏性的。** 新建的沙箱默认 **5 分钟超时**，`onTimeout` 默认是 **`"kill"`**——不是暂停。一个跑超过 5 分钟又没有延长超时的 Agent 任务会永久丢失沙箱、它的文件系统和任何内存中的状态，无法恢复。见下面"跨领域的通用规则"和 `references/lifecycle-and-cost.md`。

## 30 秒跑通第一个请求

```python
from e2b import Sandbox

sandbox = Sandbox.create(timeout=120)  # Python 里单位是秒
try:
    print(sandbox.sandbox_id)
    result = sandbox.commands.run('echo "hello from e2b"')
    print(result.stdout, result.exit_code)
finally:
    sandbox.kill()  # 停止计费，释放沙箱
```

```typescript
import { Sandbox } from "e2b"

const sandbox = await Sandbox.create({ timeoutMs: 120_000 }) // JS 里单位是毫秒——注意和 Python 的单位不一样
try {
  console.log(sandbox.sandboxId)
  const result = await sandbox.commands.run('echo "hello from e2b"')
  console.log(result.stdout, result.exitCode)
} finally {
  await sandbox.kill()
}
```

预期输出 stdout 是 `hello from e2b`，退出码 0。`finally`/`try...finally` 这个结构不是装饰——沙箱在运行期间按秒计费，还会占用并发限额，一个没释放的沙箱会持续花钱，还可能挡住新沙箱的创建。⚠ 文档原文，未实测。

## 我要做什么 → 读哪一份

| 我想做什么... | 读 | 核心方法 / 端点 |
|---|---|---|
| 运行 AI 生成的 Python/JS 并拿到结构化结果（图表、表格、每个 cell 的 stdout），或运行任意 shell 命令 | `references/run-code-and-commands.md` | `Sandbox.create()`、`sandbox.runCode()` / `run_code()`、`sandbox.commands.run()`、后台命令、code contexts |
| 读写文件、在本地和沙箱之间上传/下载、监听目录变化、拿文件元信息 | `references/filesystem.md` | `sandbox.files.read/write/list/getInfo/watchDir/makeDir` |
| 控制沙箱存活多久、暂停/恢复/快照它、搞清楚它到底花多少钱 | `references/lifecycle-and-cost.md` | `Sandbox.create/connect/pause/kill`、`setTimeout()`、`createSnapshot()`、计费公式 |
| 把沙箱里运行的服务暴露到公网，或控制沙箱自身的出站互联网访问 | `references/networking.md` | `sandbox.getHost(port)`、`network.allowInternetAccess`、`network.allowOut/denyOut` |
| 处理 SDK 异常、限流、套餐限制（vCPU/RAM/并发/GPU） | `references/errors-and-limits.md` | `SandboxException`/`SandboxError` 异常体系、`RateLimitException`、套餐限制表 |

本 skill 未覆盖（按任务 brief 的范围排除——需要时直接查文档）：自定义**模板构建**（`Template.build`，类 Dockerfile 的模板定义）、**Volumes**（跨沙箱持久化存储）、**Secrets**（E2B 托管的、注入到出站请求里的凭证）、**Desktop/computer-use 沙箱**（`@e2b/desktop`）、预置的**编程 Agent 模板**（在沙箱里跑 Claude Code / Codex / Cursor）、**BYOC**（自带云部署）、以及 **MCP 网关**。这些都存在并且都有文档，在 `docs.e2b.dev` 上；本 skill 专注于创建 → 运行 → 读写文件 → 销毁这个核心循环。

## 跨领域的通用规则（写代码前必读）

这些是最容易让用惯了类似平台（"serverless 函数"心智模型、Docker、或普通 Jupyter kernel）的开发者踩坑的直觉陷阱。除非另有标注，全部 ⚠ 文档原文，未实测。

1. **超时的单位因语言而异，而且默认行为是破坏性的。** JS/TS：`timeoutMs`，单位**毫秒**。Python：`timeout`，单位**秒**。两者不设置时默认都是 5 分钟，到期后沙箱默认会被**杀掉**（`onTimeout: "kill"` 是默认值），不是暂停——状态直接消失，无法恢复。如果任务可能跑得比较久，要么传一个更长的超时，要么定期调用 `setTimeout()`/`set_timeout()`，要么在创建时设置 `lifecycle: { onTimeout: "pause", autoResume: true }`，让超时变成暂停而不是销毁，沙箱会在下一次请求时自己醒过来。见 `references/lifecycle-and-cost.md`。
2. **`Sandbox.connect()` 只会延长超时，永远不会缩短它。** 新的到期时间是 `max(当前到期时间, now + 传给 connect 的 timeout)`。一个还剩 20 分钟的沙箱，即使你用（5 分钟的）默认值去 connect，也还是停在 20 分钟不变。如果需要一个*精确*的超时——包括比当前更短的——要显式调用 `setTimeout()`/`set_timeout()`，不能依赖 `connect()`。
3. **`run_code`/`runCode` 和 `commands.run` 的状态持久性是不一样的。** `run_code()`/`runCode()`（Code Interpreter）在一个持久化的、类 Jupyter 的"code context"里执行，这个 context 绑定在沙箱上：一次调用里的变量、import、加载的数据，在**下一次调用里依然可见**——这和无状态的函数调用正相反，也是 code-interpreter 类 SDK 里最常被误解的地方。`commands.run()`（原生 shell）每次调用都会起一个**全新的进程**——上一次 `commands.run()` 调用里设的环境变量或 `cd` 过的目录，**不会**带到下一次调用里（只有在 `Sandbox.create()` 时设置的、整个沙箱级别的 `envs` 才会跨调用持久化）。不过沙箱的**文件系统**在两种调用之间（以及暂停/恢复之间）都会持久化，因为它们用的是同一块 VM 磁盘。不要假设上一次调用的 shell 状态会带到下一次；但可以假设 Python/JS 解释器里的变量会，只要还在同一个 context 里。
4. **暂停中的沙箱，它的 stdout 流和后台命令输出不会跨进程存活。** `background: true` 命令的 `onStdout`/`on_stdout` 流式回调只会推送给发起它的那个进程——如果你打算之后从另一个进程重新连接（比如一个 serverless handler 起了个长任务就立刻返回），要把输出重定向到文件（`> /home/user/out.log 2>&1`），之后用 `Sandbox.connect()` + `commands.connect(pid)` 重连后把文件读回来，不要指望原来的那个流还在。
5. **计费按秒、只在 `Running` 状态计费，而且不会自动停止。** Paused 和 Killed 状态的沙箱不花钱，Paused 状态也不占并发限额——但一个 Paused 的沙箱会被**无限期保留，没有自动删除或 TTL**。"暂停来省钱"是对的；"暂停了它总会自己清理掉"是错的——要真正删除一个沙箱，必须显式调用 `kill()`（传 ID 也行）。一个被遗忘的、仍在 *Running* 的沙箱会持续按秒计费，也会一直占并发限额（Hobby 20 个、Pro 100+），直到碰到连续运行时长上限或被手动 kill。
6. **"最大连续运行时长"（Hobby 1 小时 / Pro 24 小时）和单个沙箱的超时不是同一个限制。** 超时（默认 5 分钟，可配置）管的是一个*空闲*沙箱什么时候被杀/暂停。连续运行时长是一个独立的、套餐级别的上限，管的是一个沙箱在**完全不被暂停**的情况下能跑多久，哪怕它一直在活跃工作——暂停再恢复会重置这个计时器。不要把这两个限制搞混，尤其是在排查一个长期运行的沙箱为什么停止工作时。
7. **任何档位都不提供 GPU**，包括 BYOC。沙箱只按 vCPU + RAM 计量规格；不要写请求或假设 GPU 算力的代码，如果某个工作负载需要 GPU，E2B 在这一点上是硬性不支持，不是一个配置项没找到的问题。
8. **没有 `@e2b-dev/` 这个 npm scope，SDK 里的 API key 也不走 `Bearer` token。** SDK 从来不需要给沙箱 API key 传 `Authorization: Bearer` header——那个 header 是给更老的、现已废弃的 `E2B_ACCESS_TOKEN` CLI 登录流程用的。沙箱相关操作要么用 SDK 自己的选项传 `E2B_API_KEY`（`e2b_...`），要么在直接调用 REST API 时用 `X-API-Key`。
9. **不同 region 之间不共享状态。** 一个项目/API key 唯一属于一个 region（默认 US，Pro+ 可选 EU/APAC）；一个 region 里的沙箱、模板或快照 ID 在另一个 region 里解析不出来。不要假设一个沙箱 ID 在切换 `E2B_DOMAIN` 后还能用。
10. **暴露一个端口不需要显式的"开放端口"步骤**——`sandbox.getHost(port)` / `sandbox.get_host(port)` 对沙箱内任何正在监听的端口都会直接返回一个可用的 URL；*入站*流量没有白名单这一步（只有 `network.allowPublicTraffic`/token 校验，或者限制*出站*互联网访问，是单独的、需要主动开启的控制项）。反过来，端口要一直显式传——没有方法会替你推断一个"默认端口"。

## 目录结构

```
e2b/
├── SKILL.md
├── references/
│   ├── run-code-and-commands.md   # Code Interpreter run_code、shell commands.run、流式输出、后台任务、code contexts
│   ├── filesystem.md              # 读写、上传/下载、list/info、监听目录、批量文件
│   ├── lifecycle-and-cost.md      # create/connect、超时、暂停/恢复、快照/fork、自动唤醒、计费
│   ├── networking.md              # 公网 URL / 端口暴露、出站互联网访问控制、访问限制
│   └── errors-and-limits.md       # SDK 异常体系、限流、套餐限制表
└── evals/
    └── evals.json                 # 有/无 skill 对照实验场景草稿（还没跑，见 verification-plan.md）
```

内容整理自 `docs.e2b.dev` 和 `e2b.dev`（抓取于 2026-09-21，通过它们公开的 `llms.txt` 索引和 `docs.e2b.dev/openapi-public.yaml` 的 OpenAPI 规范），并参考了 E2B 官方的、面向 Agent 的 `https://e2b.dev/SKILL.md`（用于交叉核对，未直接照抄）。**没有一条经过真实 API 调用的验证。** 拿到真实 key 之后，以实际 SDK/API 的行为为准，不要迷信这里写的东西，并按 `../e2b-workspace/verification-plan.md` 更新 ⚠ 标记。
