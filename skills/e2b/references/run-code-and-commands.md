# 运行代码与命令

⚠ 全文档原文，未实测（抓取自 `docs.e2b.dev`，2026-09-21）。下面的内容都没有在真实运行的沙箱上跑过。

目录：[两种执行方式](#两种执行方式) · [Code Interpreter：`runCode` / `run_code`](#code-interpreterruncode--run_code) · [流式输出代码执行结果](#流式输出代码执行结果) · [Code contexts——状态持久化，务必读一下](#code-contexts状态持久化务必读一下) · [Shell 命令：`commands.run`](#shell-命令commandsrun) · [流式输出命令结果](#流式输出命令结果) · [后台命令与跨进程重连](#后台命令与跨进程重连)

## 两种执行方式

| | 核心 SDK：`commands.run()` | Code Interpreter：`runCode()` / `run_code()` |
|---|---|---|
| 包 | `e2b` / `e2b`（JS） | `@e2b/code-interpreter`（JS） / `e2b-code-interpreter`（Python，导入为 `e2b_code_interpreter`） |
| 运行内容 | 任意 shell 命令，沙箱镜像支持的任何语言 | 专门跑 Python 或 JS/TS，跑在一个类 Jupyter 的 kernel 里 |
| 进程模型 | 每次调用一个全新进程 | 持久化的解释器进程（"code context"），跨调用共享 |
| 输出形式 | `stdout`、`stderr`、`exitCode`/`exit_code` | 结构化的 `Execution` 结果：logs、丰富的 `results`（图表/表格/图片）、`error` |
| 适用场景 | 装包、跑任意脚本/二进制文件、长 shell 管道 | LLM 工具调用的目标——"跑这段 Python，把输出/图表给我看" |

两者都是同一个 `Sandbox` 对象上的方法——不是选不同的沙箱类型，只是选不同的 SDK 入口（`Sandbox` 是从 `e2b` 导入还是从 `@e2b/code-interpreter` / `e2b_code_interpreter` 导入）。⚠ 文档未明确说明核心 SDK 的 `Sandbox` 和 Code Interpreter 的 `Sandbox` 底层用的模板是否完全一样（是否需要不同的 template id）；两者的导入路径和方法集不同，第一次用真实 key 跑通时应该确认一下。

## Code Interpreter：`runCode` / `run_code`

```python
from e2b_code_interpreter import Sandbox

sbx = Sandbox.create()  # code-interpreter 包自己的 Sandbox
execution = sbx.run_code("print('hello world')")
print(execution.logs)
```

```typescript
import { Sandbox } from '@e2b/code-interpreter'

const sbx = await Sandbox.create()
const execution = await sbx.runCode('print("hello world")')
console.log(execution.logs)
```

**用途**：运行一段 Python（或 JS/TS）代码片段，拿回结构化的输出——stdout/stderr 每一行、代码抛异常时的 `error` 对象、以及代码显示出来的任何东西对应的 `results`（通过 `plt.show()`/`display(plt.gcf())` 生成的 matplotlib 图表、pandas 表格等）。这个方法就是为了"LLM 写代码、工具调用执行它、Agent 把结果展示出来"这个场景设计的，不是一个通用的 shell 执行器。

**关键参数**
| 参数 | 说明 |
|---|---|
| `code`（位置参数） | 要执行的源码。 |
| `context` | 一个来自 `createCodeContext()`/`create_code_context()` 的显式 code context 对象/ID，代码会在这个 context 里跑，而不是用沙箱的默认 context。用这个来在同一个沙箱内并行跑几个互不相关的执行。 |
| `envs` | 只作用于这一次执行的环境变量（在操作系统层面不是私密的，除非同时在 `Sandbox.create()` 时把它设成沙箱级别的，否则不会带到下一次调用）。 |
| `onStdout`/`on_stdout`、`onStderr`/`on_stderr` | 流式回调——见下文。 |
| `onResult`/`on_result` | 富结果（图表、表格）产生时的流式回调，不用等整个执行结束。 |
| `onError`/`on_error` | 被执行代码自身抛出的运行时错误的回调（区别于 SDK/网络层面的错误）。 |

**注意事项**
- E2B 自己 cookbook 里给 LLM 的示例提示词写的是：*"CRITICAL: Your code MUST end with this exact line to display the plot: `display(plt.gcf())`"*——也就是说，一张图表只有在代码显式调用了 `display(...)`（或 `plt.show()`）之后才会被捕获进 `results`，光是创建一个 figure 对象是不够的。⚠ 文档原文，未实测。
- 除 Python/JS 之外还支持其他语言（R、Java、bash），见 `docs.e2b.dev/code-interpreting/supported-languages`——本 skill 没有抓取每种语言的具体细节；如果需要 Python/JS 以外的语言，请查那个页面。

## 流式输出代码执行结果

```python
sandbox = Sandbox.create()
sandbox.run_code(
    code_to_run,
    on_error=lambda error: print('error:', error),
    on_stdout=lambda data: print('stdout:', data),
    on_stderr=lambda data: print('stderr:', data),
)
```

```typescript
const sandbox = await Sandbox.create()
sandbox.runCode(codeToRun, {
  onError: error => console.error('error:', error),
  onStdout: data => console.log('stdout:', data),
  onStderr: data => console.error('stderr:', data),
})
```

**注意事项**
- `onStdout`/`on_stdout` 和 `onStderr`/`on_stderr` 是代码运行过程中逐行推送的（JS 里每次回调会带一个 `{ error, line, timestamp }`），不是等整个执行结束后拼出来的一整块——想在一个长时间运行的 cell 上展示进度而不是干等整个 `Execution` 对象，就用这两个。
- `onResult`/`on_result` 会在富结果（比如一张图表）刚产生时就推送，独立于 stdout/stderr 的流式输出——如果既想要实时文本又想要实时可视化输出，两个回调都传。

## Code contexts——状态持久化，务必读一下

这是 Code Interpreter 类 SDK 里开发者最常搞错的部分（见 SKILL.md 跨领域规则第 3 条）。

```python
from e2b_code_interpreter import Sandbox

sandbox = Sandbox.create()
context = sandbox.create_code_context(cwd='/home/user', language='python', request_timeout=60_000)
result = sandbox.run_code('print("Hello, world!")', context=context)
```

```typescript
import { Sandbox } from '@e2b/code-interpreter'

const sandbox = await Sandbox.create()
const context = await sandbox.createCodeContext({ cwd: '/home/user', language: 'python', requestTimeoutMs: 60_000 })
const result = await sandbox.runCode('print("Hello, world!")', { context })
```

**用途**：默认情况下，`run_code`/`runCode` 是在沙箱的**默认** code execution context 里执行的——一个长期存活的解释器进程。对同一个沙箱、同一个 context 的每一次 `run_code` 调用都共享这个解释器的内存：第一次调用里赋值的变量，第二次调用里可以直接读到；导入过的模块保持已导入状态；加载过的 dataframe 保持已加载状态。当你想在同一个沙箱里并行跑第二个、独立的解释器时（比如隔离两个互不相关的对话线程各自的 Python 状态），而不是共用默认 context 时，才需要创建一个**显式**的 context（`createCodeContext`/`create_code_context`）。

**关键参数**
| 参数 | 说明 |
|---|---|
| `cwd` | 在这个 context 里跑代码时用的工作目录。 |
| `language` | `python`（或其他支持的语言——context 是按语言划分的）。 |
| `requestTimeoutMs`/`request_timeout` | 创建 context 这个请求本身的超时。 |

**其他 context 相关操作**：`listCodeContexts()`/`list_code_contexts()`（查看当前有哪些活跃 context）、`restartCodeContext()`/`restart_code_context()`（清空状态，在同一个 context 里起一个全新的解释器——想故意清掉积累的状态又不想销毁整个沙箱时用这个）、`removeCodeContext()`/`remove_code_context()`。

**注意事项**
- ⚠ 文档未明确说明：默认 context 的状态在沙箱 `pause()`/`resume()` 之后是否会按 `references/lifecycle-and-cost.md` 里说的那种通用"内存持久化"保留下来。持久化那一页说暂停会保留"所有运行中的进程、已加载的变量、数据"，这按理说应该包括一个进行中的 code context 的解释器状态，但本次没有针对 code-interpreter 包单独确认这一点。在依赖一个假设"暂停/恢复后 Python 变量还在"的工作流之前，先验证一下。
- 重启一个 context 是文档给出的、在不重新创建整个沙箱的前提下、在沙箱生命周期中途重置状态的正规做法。

## Shell 命令：`commands.run()`

```python
from e2b import Sandbox

sandbox = Sandbox.create()
result = sandbox.commands.run('ls -l')
print(result)
```

```typescript
import { Sandbox } from 'e2b'

const sandbox = await Sandbox.create()
const result = await sandbox.commands.run('ls -l')
console.log(result)
```

**用途**：作为沙箱内的一个子进程运行任意 shell 命令——装包、git 操作、跑一个编译好的二进制文件，任何不特指"执行这段带结构化结果的 Python/JS 代码片段"的场景。

**关键参数**（⚠ 文档页面没有完整列出所有参数，下面是教程页里出现过的）
| 参数 | 说明 |
|---|---|
| `cmd`（位置参数） | 命令字符串，通过一个 shell 执行。 |
| `background` | `true`/`True` 表示立刻返回一个句柄而不是阻塞到命令结束——见下文。 |
| `envs` | 只作用于这一次命令的环境变量（不会持久化到下一次 `commands.run()` 调用）。 |
| `onStdout`/`on_stdout`、`onStderr`/`on_stderr` | 流式回调，和 Code Interpreter 的形状一样。 |
| `timeoutMs`/`timeout` | 单条命令的超时；`0` 表示不限时（见下面的后台任务示例）——和沙箱自身的生命周期超时是两回事。 |

**注意事项**
- 每次 `commands.run()` 调用都会起一个**全新进程**。任何 shell 状态（上一次 `cd` 过的当前目录、export 过的环境变量、上一次调用留下的后台任务）都不会自动带过来——只有在 `Sandbox.create()` 时设置的、整个沙箱级别的 `envs`，以及文件系统，才会跨调用持久化。如果需要多步骤的 shell 状态，把步骤串在同一个 `cmd` 字符串里（比如 `cd /x && ./build.sh`），不要假设第二次 `commands.run()` 调用会记得第一次的 `cd`。
- **永远不要把不可信输入直接拼进命令字符串。** 通过 `envs` 传进去，在命令里用 `"$VAR"` 引用；直接把原始输入拼进去，会让 `$(...)`/反引号被当成 shell 命令执行。E2B 自己的文档就是拿一个代码生成 prompt 的例子来演示这个模式的。

## 后台命令与跨进程重连

```python
sandbox = Sandbox.create()
command = sandbox.commands.run('echo hello; sleep 10; echo world', background=True)
for stdout, stderr, _ in command:
    if stdout: print(stdout)
    if stderr: print(stderr)
command.kill()
```

```typescript
const sandbox = await Sandbox.create()
const command = await sandbox.commands.run('echo hello; sleep 10; echo world', {
  background: true,
  onStdout: (data) => console.log(data),
})
await command.kill()
```

**用途**：启动一个长时间运行的进程，立刻拿回控制权，而不是阻塞整个调用直到它结束。

**跨进程重连模式**（文档给出的场景是"从一个 serverless handler 里起一个慢任务，之后再来收集结果"）：

```python
# 进程 A：启动任务，立刻返回。
def start_generation(prompt: str):
    sandbox = Sandbox.create(timeout=15 * 60)
    handle = sandbox.commands.run(
        'run-codegen "$PROMPT" > /home/user/gen.log 2>&1',
        background=True, timeout=0, envs={"PROMPT": prompt},
    )
    return {"sandbox_id": sandbox.sandbox_id, "pid": handle.pid}

# 进程 B（之后，可能是另一台机器）：重连并收集结果。
def collect_generation(sandbox_id: str, pid: int):
    sandbox = Sandbox.connect(sandbox_id)
    handle = sandbox.commands.connect(pid)
    handle.wait()
    return sandbox.files.read("/home/user/gen.log")
```

**注意事项**
- **流式的 `stdout`/`stderr` 只会推送给发起这个命令的进程。** 如果之后会有另一个不同的进程来重连（`Sandbox.connect()` + `commands.connect(pid)`），唯一能拿到输出的办法是在命令字符串里就把输出重定向到一个文件（`> /home/user/gen.log 2>&1`）——重连之后调用 `handle.wait()` 并不会把之前流式推送过的那些行补给你。
- 通过 `envs` + `"$PROMPT"` 传递不可信输入（比如一段 LLM 生成的 prompt），而不是直接拼进命令字符串，是文档给出的安全做法——见上面关于 shell 注入的警告。
- `timeout=0` / `timeoutMs: 0` 会关闭**这条命令自己**的超时，这样一个长任务不会中途被杀；这和**沙箱**的生命周期超时是分开的两件事，后者必须独立设置得足够长（或者配置成超时后暂停而不是销毁）才能撑过这个任务——见 `references/lifecycle-and-cost.md`。
- 如果不知道要重连哪个 `pid`，`sandbox.commands.list()` 会返回正在运行的进程列表。⚠ 具体参数细节本次抓取没有核实。
- `commands.kill()` 停止的是一个后台命令；这和 `sandbox.kill()` 不是一回事，后者销毁的是整个沙箱。
