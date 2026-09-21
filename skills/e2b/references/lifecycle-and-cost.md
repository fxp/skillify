# 沙箱生命周期与成本控制

⚠ 全文档原文，未实测（抓取自 `docs.e2b.dev`，2026-09-21）。下面每一个金额、每一个时间数字、每一个默认值都是文档自己的说法，不是实测结果。

目录：[状态机](#状态机) · [创建、连接、销毁](#创建连接销毁) · [超时——头号大坑](#超时头号大坑) · [暂停和恢复](#暂停和恢复) · [活动触发的自动唤醒](#活动触发的自动唤醒) · [快照（一对多的检查点）](#快照一对多的检查点) · [Fork](#fork) · [连续运行时长上限 vs 超时](#连续运行时长上限-vs-超时) · [计费——按用量、按秒](#计费按用量按秒) · [套餐限制表](#套餐限制表)

## 状态机

```
Sandbox.create ──► Running ──pause──► Paused ──connect──► Running
                      │                  │
                      ├──createSnapshot──┤ （短暂暂停，然后回到 Running）
                      │                  │
                      └──────kill────────┴──────► Killed （终态，无法恢复）
```

- **Running**：正在执行，消耗资源，计费。
- **Paused**：内存 + 文件系统都保留，不能执行代码，**不计费**，会被**无限期**保留，没有自动过期。
- **Snapshotting**：过渡态——短暂暂停、抓取状态、然后自动回到 Running。原沙箱保留自己的 ID 并继续运行；快照是一个独立的、可复用的产物。
- **Killed**：终态。资源已释放。在任何情况下都无法恢复。

## 创建、连接、销毁

```python
from e2b import Sandbox

sandbox = Sandbox.create(timeout=60)       # 单位是秒；默认模板 "base"；默认 2 vCPU / 512 MiB RAM
info = sandbox.get_info()                   # sandbox_id, template_id, name, metadata, started_at, end_at, cpu_count, memory_mb, state
sandbox.set_timeout(30)                     # 把倒计时从*此刻*起重置为 30 秒
again = sandbox.connect()                    # 或者从另一个进程调用 Sandbox.connect(sandbox.sandbox_id)
sandbox.kill()                               # 或者 Sandbox.kill(sandbox_id) —— 终态，释放资源
```

```typescript
import { Sandbox } from 'e2b'

const sandbox = await Sandbox.create({ timeoutMs: 60_000 })  // 单位毫秒
const info = await sandbox.getInfo()
await sandbox.setTimeout(30_000)
const again = await Sandbox.connect(sandbox.sandboxId)
await sandbox.kill()
```

**关键参数**（`Sandbox.create`）
| 参数 | 说明 |
|---|---|
| template（位置参数，可选） | 用来启动的模板 ID/别名，或者一个用于恢复精确状态的快照 ID。不传时默认是 `"base"`。 |
| `timeoutMs`/`timeout` | 初始存活时长；JS 是毫秒，Python 是秒。两者默认都是 **5 分钟**。 |
| `apiKey`/`api_key` | 只在这次调用里覆盖 `E2B_API_KEY`。 |
| `envs` | 整个沙箱级别的环境变量，这个沙箱生命周期内每次 `commands.run()`/`run_code()` 调用都能看到。 |
| `lifecycle` | `{ onTimeout, autoResume }` —— 见下面[超时](#超时头号大坑)一节。 |
| `secure` | 开启预签名上传/下载 URL —— 见 `references/filesystem.md`。 |
| `network` | 出站/入站网络配置 —— 见 `references/networking.md`。 |
| `metadata` | 任意键值对标签，可以通过 `getInfo()`/`Sandbox.list()` 取回。 |

**注意事项**
- 默认资源配额是 **2 vCPU、512 MiB RAM**（按计费 FAQ 里那个算例推算出来的），除非用了一个自定义了不同 `cpuCount`/`memoryMB` 的模板。
- `getInfo()`/`get_info()` 返回的 `cpuCount`/`cpu_count` 和 `memoryMB`/`memory_mb` ——在计算某个具体沙箱的计费公式时，用这两个实际值，不要靠猜。

## 超时——头号大坑

- **单位因语言而异**：`timeoutMs`（JS，毫秒）vs `timeout`（Python，秒）。把这两个搞混、相差 1000 倍，是一个很容易发生又不会报错的失误——不会报任何错，沙箱只是会活得比预期长 1000 倍或短 1000 倍。
- **默认是 5 分钟，到期时默认的处理方式是 `kill`**，也就是破坏性的。这*不是*一个"会话即将空闲"的警告状态——沙箱、它的文件系统、以及任何内存中的解释器状态都会直接消失。
- **`setTimeout()`/`set_timeout()`** 会把倒计时重置为传入的时长，**从调用那一刻算起**——可以定期调用它（比如一个 App 里每次用户交互都调一次）来让沙箱只按实际需要的时长存活。
- **`Sandbox.connect()` 的行为和 `setTimeout()` 不一样。** 它只会*延长*：新的到期时间 = `max(当前到期时间, now + 传给 connect 的 timeout)`。连接一个还剩 20 分钟的沙箱，就算传了 5 分钟的默认值，它还是停在 20 分钟——不会被缩短到 5 分钟。如果连接之后需要一个精确的（可能更短的）超时，要显式调用 `setTimeout()`/`set_timeout()`。
- **要避免一个长时间运行的 Agent 任务撞上这个破坏性默认值**，可以在创建时设置 `lifecycle: { onTimeout: "pause", autoResume: true }`（见下文），让空闲超时变成暂停（保留状态、停止计费）而不是销毁，沙箱会在下一次 SDK 调用或 HTTP 请求时自己醒过来。

```python
sandbox = Sandbox.create(
    timeout=10 * 60,
    lifecycle={"on_timeout": "pause", "auto_resume": True},
)
```

```typescript
const sandbox = await Sandbox.create({
  timeoutMs: 10 * 60 * 1000,
  lifecycle: { onTimeout: 'pause', autoResume: true },
})
```

**`lifecycle` 选项**
| 设置项 | 取值 | 说明 |
|---|---|---|
| `onTimeout`/`on_timeout` | `"kill"`（默认） | 沙箱在超时后被终止——不可恢复。 |
| | `"pause"` | 超时后做一次完整的内存 + 文件系统快照，可恢复。 |
| | `{ action: "pause", keepMemory: false }` | 只保留文件系统的自动暂停——更轻量，但恢复时会**冷启动**（内存丢失）。不能和 `autoResume` 一起用。 |
| `autoResume`/`auto_resume` | `false`（默认） | 已暂停的沙箱保持暂停状态，直到显式调用 `connect()`。 |
| | `true` | 已暂停的沙箱在下一次 `commands.run`、`files.read/write`，或者一个打到某个隧道端口 URL 的 HTTP 请求发生时会**自动醒过来**。只有在 `onTimeout` 是 `"pause"` **且**快照保留了内存（不是只保留文件系统）时才生效。 |

**注意事项**
- 自动唤醒之后，沙箱会以**至少 5 分钟**的超时重启，即使原来设置的更短（一个 2 分钟超时的沙箱自动唤醒之后，这一轮会被提到 5 分钟）；如果原来设置的更长（比如 1 小时），会原样保留。这个循环每次自动唤醒都会重复一遍——这是一个持续生效的生命周期配置，不是一次性的。
- 如果节点还在完成同一个沙箱之前的一次快照，暂停可能会被**拒绝**，抛出 `ServiceBusyError`/`ServiceBusyException`（HTTP 503）——这种情况下沙箱**并没有**丢失，它继续运行、状态完好；稍等一下再重试暂停，或者先继续用它，之后再暂停。⚠ 文档标注该行为"正在按 region 逐步灰度上线"——老版本 SDK/尚未灰度到的 region 可能会改为抛一个通用的 `SandboxError`/`SandboxException`，报错信息以 `503:` 开头，而不是这个专门的类型。
- 如果自动暂停本身（因为节点繁忙）被反复拒绝，持续大约两分钟超过了超时时间，E2B 会退化成一次**只保留文件系统**的暂停（丢内存，下次恢复会冷启动），而不是彻底丢掉这个沙箱——文档把这个记录为一种边缘情况，"正常情况下……不会发生"。

## 暂停和恢复

```python
sbx = Sandbox.create()
sbx.pause()          # Running → Paused；显式、手动触发（不是超时触发的）
sbx.connect()         # Paused → Running；如果处于暂停状态会自动恢复
sbx.kill()            # 任意状态 → Killed
```

```typescript
const sbx = await Sandbox.create()
await sbx.pause()
await sbx.connect()
await sbx.kill()
```

**用途**：手动给沙箱打一个检查点——保存文件系统和内存状态（所有运行中的进程、已加载的变量）——从而停止计费同时保留可恢复性，而不是等超时来做这件事。

**关键参数**：`pause({ keepMemory: false })` / `pause(keep_memory=False)` —— 只保留文件系统的暂停（和上面自动暂停的那个变体是同样的取舍：更轻量，但恢复时会冷启动）。

**注意事项**
- **暂停一个沙箱不会删除它，也不会启动任何清理倒计时。** 暂停的沙箱会被**无限期**保留——没有"N 天后自动 kill"这种选项。要真正移除一个暂停的沙箱，唯一的办法是显式调用 `kill()`（或者按 ID 调用 `Sandbox.kill(sandboxId)`）。如果你的应用把暂停沙箱当成一种省钱手段，那么如果不想让它们无限堆积，你需要自己负责一套回收策略（它们暂停时不花钱，但也不会被系统自动垃圾回收）。
- 如果沙箱被暂停时里面正跑着一个服务（比如一个 HTTP server），它所有的客户端连接都会断开，直到恢复之前都无法访问——客户端需要在恢复后自己重新连接，不会被排队等待。
- 列出/筛选暂停中的沙箱：`Sandbox.list({ query: { state: ['paused'] } })`（JS）/ `Sandbox.list(SandboxQuery(state=[SandboxState.PAUSED]))`（Python）——返回的是一个分页器（`hasNext`/`has_next` + `nextItems()`/`next_items()`），不是一个普通数组。
- 暂停大约耗时**每 1 GiB 内存 4 秒**；恢复大约耗时 **1 秒**。分配了大量内存的沙箱，暂停会明显比恢复慢得多——如果暂停操作在用户可感知的关键路径上，要把这个延迟考虑进去。

## 活动触发的自动唤醒

在上面[超时](#超时头号大坑)一节已经提到——`lifecycle.autoResume`/`auto_resume: true`（只在 `onTimeout: "pause"` 且保留内存时生效）。会触发唤醒的"活动"包括 `commands.run()`、`files.read()`/`files.write()`，以及打到某个隧道端口 URL（`getHost(port)`）的入站 HTTP 流量——如果配置了自动唤醒，不需要先调用 `Sandbox.connect()`，下一次支持的操作会自动、透明地把它恢复过来。

## 快照（一对多的检查点）

```python
sandbox = Sandbox.create()
snapshot = sandbox.create_snapshot()
new_sandbox = Sandbox.create(snapshot.snapshot_id)  # 从那个精确状态生成一个全新的沙箱
```

```typescript
const sandbox = await Sandbox.create()
const snapshot = await sandbox.createSnapshot()
const newSandbox = await Sandbox.create(snapshot.snapshotId)
```

**快照 vs. 暂停/恢复**
| | 暂停/恢复 | 快照 |
|---|---|---|
| 对原沙箱的影响 | 暂停它 | 短暂暂停，然后**继续运行** |
| 关系 | 一对一（恢复 = 还是同一个沙箱） | 一对多（从一个快照生成很多个新沙箱） |
| 用于 | 挂起/恢复单个沙箱 | 可复用的检查点、回滚点、并行分叉 |

**快照 vs. 模板**：模板是一个**声明式、可复现**的起点（同一个定义每次都产出同样的结果，冷启动更快，捕获时因为 guest OS 是干净重启的，内存压力也更小）；快照捕获的是**那一刻实际存在的运行时状态**（不能重新定义，但能捕获模板捕获不到的实时数据/进度）。如果希望每个沙箱都以完全相同的状态启动，优先用模板；如果需要保留依赖于实际执行过程的状态（一个 Agent 正在进行中的工作、一份已加载的数据集），优先用快照。

**关键参数 / 前提条件**：快照要求模板的 envd 版本是 `v0.5.0+`——一个在这之前构建的自定义模板需要重新构建。可以用 `e2b template list` 或控制台查看版本。

**注意事项**
- 快照创建过程中"短暂暂停再恢复"的这段时间里，所有的活跃连接（WebSocket、PTY、命令流）都会被**断开**——客户端要自己处理重连。
- 另外还有：`Sandbox.listSnapshots()`/`list_snapshots()`（分页，可选按 `sandboxId` 过滤）和 `Sandbox.deleteSnapshot(id)`/`delete_snapshot(id)`。

## Fork

`docs.e2b.dev/sandbox/fork` 讲的是"快照 + 一次调用从那个精确状态生成 N 个新沙箱"，用于从同一个检查点并行探索多种方案。⚠ 本次抓取没有深入阅读这个页面的具体方法签名——先当作"存在，去看文档"，不要当成已确认的 API 形状；如果需要用这个功能，先直接读 `docs.e2b.dev/sandbox/fork.md` 再写代码。

## 连续运行时长上限 vs 超时

**不要把这两个概念搞混：**

1. **超时**（单沙箱级别，可配置，默认 5 分钟）：管的是一个原本空闲、但没被显式 kill 的沙箱什么时候会被杀/暂停。可以随时用 `setTimeout()` 重置。
2. **最大连续运行时长**（套餐级别，不能针对单个沙箱配置）：一个沙箱在**从未被暂停过**的情况下能跑多久，哪怕它一直在持续活跃——**Hobby 1 小时，Pro 24 小时，Enterprise 自定义**。暂停再恢复会**重置**这个计时器，所以一个被定期暂停/恢复的沙箱理论上可以一直活下去；一个一直不停运行的沙箱，不管超时怎么设置，都无法超过这个上限。

⚠ 文档未明确说明：撞到连续运行时长上限时到底会发生什么（自动暂停？自动 kill？下一次调用报错？）——本次没有抓取到这个具体机制。在依赖这个 1 小时/24 小时边界上的"优雅处理"之前，先确认清楚。

## 计费——按用量、按秒

**公式**：`cost = (vCPU × $0.000014/秒 + RAM_GiB × $0.0000045/秒) × 运行的秒数`。费率取决于**分配到**的算力，不是实际利用率——一个空闲但在 Running 的 2 vCPU 沙箱，每秒花的钱和一个跑满 100% CPU 的沙箱是一样的。

**算例**（默认沙箱：2 vCPU，0.5 GiB RAM，跑 1 小时）：`2 × $0.0504/小时 + 0.5 × $0.0162/小时 ≈ $0.109/小时`；同样的沙箱跑 5 分钟 ≈ `$0.009`。⚠ 文档注明费率可能变化，以 `e2b.dev/pricing` 的计算器为准。

**什么情况下计费**
| 沙箱状态 | 计费？ | 算进并发限额？ |
|---|---|---|
| Running | **是**，按秒 | 是 |
| Paused | **否** | **否** |
| Killed | **否**（已经没了） | 否 |

这对一个 Agent 工作负载的成本控制含义是关键的：**`pause()` 停止计费同时保留状态；`kill()` 才是真正释放/永久移除。** 这两者都不是"默认更安全"的——放着一个沙箱 `Running` 忘了管会持续计费，还会一直占并发名额，直到撞上连续运行时长上限或被手动 kill；放着很多个沙箱 `Paused` 忘了管在算力上不花钱，但会无限堆积（没有自动清理），还可能撞上其他账号级别的限制（比如暂停沙箱数量上限，如果存在的话——⚠ 文档没有提到是否存在暂停沙箱数量上限，只明确了它不算入并发上限）。

**自己算成本需要的数据**：`getInfo()` 对一个运行中的沙箱返回 `cpuCount`/`memoryMB`。对于已经结束的运行，生命周期事件的 webhook（`sandbox.lifecycle.killed` / `sandbox.lifecycle.paused`）会带一个 `event_data.execution` 对象，里面一起给出 `vcpu_count`、`memory_mb`、`execution_time`（毫秒）和 `started_at`——`sandbox.lifecycle.created` 事件**不包含**资源配额信息，只有终止类事件才有。

**FAQ 里的事实**（⚠ 文档原文，未实测）：
- 在每月月初对上个月的用量自动扣费；新账号会获得一次性的 **$100 免费额度**。
- 额度用完会导致账号被锁，直到添加支付方式；可以在控制台的 budget 页设置消费上限。
- 升级到 Pro（基础价 $150/月）**不会**额外赠送额度——它提高的是套餐*限制*（并发、连续运行时长、资源上限），和按秒计费的算力成本本身是两回事。

## 套餐限制表

| | Hobby | Pro | Enterprise |
|---|---|---|---|
| 基础价格 | $0/月 | $150/月 | 自定义 |
| 免费额度 | $100 一次性 | 无额外额度 | 自定义 |
| 最大 vCPU | 8 | 8+（联系支持可以更多） | 自定义 |
| 最大内存 | 8 GiB | 8+ GiB | 自定义 |
| 磁盘 | 10 GiB | 20+ GiB | 自定义 |
| 最大连续运行时长 | 1 小时 | 24 小时 | 自定义 |
| 并发沙箱数 | 20 | 100–1,100（含 100，加购最高到 1,100，$500/月） | 1,100+ |
| 并发模板构建数 | 20 | 20 | 自定义 |
| 沙箱创建速率 | 1/秒 | 5/秒 | 自定义 |
| 暂停沙箱保留时长 | 无限 | 无限 | 无限 |

任何档位都**不提供** GPU，包括 Enterprise/BYOC——沙箱只按 vCPU + RAM 计量规格（见 `references/errors-and-limits.md`）。
