# 网络：暴露端口与出站互联网访问

⚠ 全文档原文，未实测（抓取自 `docs.e2b.dev`，2026-09-21）。

目录：[暴露沙箱内运行的服务（公网 URL）](#暴露沙箱内运行的服务公网-url) · [沙箱内的 HTTPS 服务](#沙箱内的-https-服务) · [Host header 伪装](#host-header-伪装) · [限制谁能访问公网 URL](#限制谁能访问公网-url) · [控制沙箱自身的出站互联网访问](#控制沙箱自身的出站互联网访问)

## 暴露沙箱内运行的服务（公网 URL）

```python
from e2b import Sandbox
import requests

sandbox = Sandbox.create()
process = sandbox.commands.run("python -m http.server 3000", background=True)
host = sandbox.get_host(3000)      # 端口号必须始终显式传入——没有推断出的默认值
url = f"https://{host}"             # 例如 https://3000-i62mff4ahtrdfdkyn2esc.e2b.app
response = requests.get(url)
process.kill()
```

```typescript
import { Sandbox } from 'e2b'

const sandbox = await Sandbox.create()
const process = await sandbox.commands.run('python -m http.server 3000', { background: true })
const host = sandbox.getHost(3000)
const url = `https://${host}`       // 例如 https://3000-i62mff4ahtrdfdkyn2esc.e2b.app
const response = await fetch(url)
await process.kill()
```

**用途**：每个沙箱在每个端口上都可以通过一个公网 HTTPS URL 访问，**不需要显式的"暴露这个端口"步骤**——只要沙箱内部有东西开始监听某个端口，`getHost(port)`/`get_host(port)` 就会为它返回一个可用的主机名。端口号会成为 URL 最左边的子域名标签（`https://<port>-<sandboxId>.e2b.app`）。

**关键参数**：`getHost(port)`——端口是**必需的、显式的**参数，每次调用都要传；沙箱对象上没有"当前"或"默认"端口这种状态。

**注意事项**
- 这是一个纯反向代理，不是容器风格的自动端口发布——在 URL 能响应之前，你仍然需要真的在沙箱内部启动一个监听该端口的进程（比如上面的 `python -m http.server 3000`）。
- 公网 URL 只在沙箱处于 `Running` 状态时才有效；暂停沙箱会让它不可访问，并断开已有的客户端连接（见 `references/lifecycle-and-cost.md`）——恢复后重新可访问，但客户端需要自己重连。
- 一定要以后台方式启动服务进程（`background: true`）——否则 `commands.run()` 会一直阻塞等待这个（永远不会退出的）服务结束，你自己的代码根本走不到访问 URL 那一步。

## 沙箱内的 HTTPS 服务

```python
sandbox = Sandbox.create(network={"https_ports": [8443]})
# 沙箱内的服务监听 8443，自带 TLS（比如自签名证书）
url = f"https://{sandbox.get_host(8443)}"
```

```typescript
const sandbox = await Sandbox.create({ network: { httpsPorts: [8443] } })
const url = `https://${sandbox.getHost(8443)}`
```

**用途**：默认情况下，E2B 的代理和沙箱内部监听的服务之间说的是**纯 HTTP**（公网 URL 本身始终是 HTTPS——那是代理到客户端这一段，不是代理到沙箱这一段）。如果你沙箱内部的服务自己终结 TLS（对外提供 HTTPS，比如用一个自签名证书），就把这个端口列进 `httpsPorts`/`https_ports`，这样代理也会用 HTTPS 去连接*它*。

**注意事项**
- **这不是 TLS 透传。** 公网 URL 的 TLS 始终是在 E2B 代理这一端终结、再在进沙箱这一跳重新加密的——意味着下面提到的公网访问限制和 host header 伪装，对 `httpsPorts` 列出的端口和普通 HTTP 端口是完全一样生效的。
- 代理不会校验沙箱那一侧的证书，所以自签名证书在这里可以正常工作。
- `httpsPorts`/`https_ports` 是在 `Sandbox.create()` 时设置的，**创建之后不能修改**——会在 `getInfo()` 的 `network` 字段里如实反映出来。

## Host header 伪装

```python
sandbox = Sandbox.create(network={"mask_request_host": "localhost:${PORT}"})
# 打到沙箱公网 URL 的请求，沙箱内部收到的 Host 会是 localhost:<实际端口号>，比如 localhost:8080
```

**用途**：沙箱内的某些框架/服务会检查 `Host` header，一旦遇到意料之外的值（比如真实的公网主机名）就会拒绝请求或行为异常。`maskRequestHost`/`mask_request_host` 会改写沙箱内服务看到的 `Host` header；`${PORT}` 会被替换成实际请求的端口号。

## 限制谁能访问公网 URL

```python
sandbox = Sandbox.create(network={"allow_public_traffic": False})
print(sandbox.traffic_access_token)
sandbox.commands.run("python -m http.server 8080", background=True)
url = f"https://{sandbox.get_host(8080)}"
requests.get(url)                                                          # 403
requests.get(url, headers={"e2b-traffic-access-token": sandbox.traffic_access_token})  # 200
```

```typescript
const sandbox = await Sandbox.create({ network: { allowPublicTraffic: false } })
console.log(sandbox.trafficAccessToken)
```

**用途**：默认情况下，任何知道/猜到一个沙箱公网 URL 的人都能访问它。在创建时设置 `allowPublicTraffic: false`/`allow_public_traffic=False`，会要求每一个打到公网 URL 的请求都必须带上一个和 `sandbox.trafficAccessToken`/`sandbox.traffic_access_token`（SDK 生成并挂在沙箱对象上的一个值）匹配的 `e2b-traffic-access-token` header——不带的请求会拿到 `403`。

**注意事项**：这个限制的是**入站**访问，限的是你自己暴露出去的服务；和下面的 `allowInternetAccess`/`network.denyOut` 是两回事，后者限制的是沙箱自身的**出站**流量。不要把这两个搞混——一个沙箱完全可以同时拥有不受限的出站互联网访问和一个完全 token 门禁的公网 URL，反过来也一样。

## 控制沙箱自身的出站互联网访问

```python
sandbox = Sandbox.create(allow_internet_access=True)          # 默认
isolated = Sandbox.create(allow_internet_access=False)          # 完全没有出站网络

# 精细控制：拒绝一切，只放行特定 IP/CIDR
restricted = Sandbox.create(network={
    "deny_out": lambda ctx: [ctx.all_traffic],   # ctx.all_traffic == "0.0.0.0/0"
    "allow_out": ["1.1.1.1", "8.8.8.0/24"],
})

# 基于域名的白名单（必须搭配一个全部拒绝的规则）
domain_scoped = Sandbox.create(network={
    "allow_out": ["*.mydomain.com"],
    "deny_out": lambda ctx: [ctx.all_traffic],
})
```

```typescript
const sandbox = await Sandbox.create({ allowInternetAccess: true })  // 默认
const isolated = await Sandbox.create({ allowInternetAccess: false })

const restricted = await Sandbox.create({
  network: { denyOut: ({ allTraffic }) => [allTraffic], allowOut: ['1.1.1.1', '8.8.8.0/24'] },
})
```

**用途**：每个沙箱**默认开启**出站互联网访问；对安全敏感的代码执行场景可以完全禁用它，或者用允许/拒绝名单（IP、CIDR、域名、通配子域名）做精细控制。

**关键参数**
| 参数 | 说明 |
|---|---|
| `allowInternetAccess`/`allow_internet_access` | 一个简单的开关；`false` 在文档里被明确说等价于 `network.denyOut = ['0.0.0.0/0']`。 |
| `network.denyOut`/`deny_out` | 要拦截的 IP/CIDR。表达"拒绝一切"推荐用选择器回调的写法 `({ allTraffic }) => [allTraffic]` / `lambda ctx: [ctx.all_traffic]`，而不是硬编码 `'0.0.0.0/0'`——一个遗留的 `ALL_TRAFFIC` 常量出于向后兼容仍然可用。 |
| `network.allowOut`/`allow_out` | 要放行的 IP、CIDR，或者**域名**（包括 `*.通配符` 子域名）。 |

**注意事项**
- **基于域名的过滤必须搭配一个全部拒绝的规则。** 如果在 `allowOut` 里用了主机名，就必须同时设置 `denyOut` 为全部拒绝——域名只在允许名单里支持，拒绝名单不支持（这是故意设计成不对称的）。
- 只要 `allowOut` 里出现了任何域名（不只是 IP/CIDR），nameserver `8.8.8.8` 就会被**自动放行**，以便该域名的 DNS 解析能正常进行——即使在一个很严格的限制策略下，看到这个 IP 出现在实际流量里也不用意外。
- E2B 会**无条件地、在 guest 之外**拦截每个沙箱访问**私有和链路本地地址段**（`10.0.0.0/8`、`100.64.0.0/10`、`127.0.0.0/8`、`169.254.0.0/16`、`172.16.0.0/12`、`192.168.0.0/16`），**这个行为无法关闭**——不需要你自己在沙箱内写规则来实现这一点。如果你自己对这些地址段之一加了一条不加区分的 iptables drop 规则、又没有先放行 established/related 连接，会切断 E2B 自己和沙箱之间的控制通道，导致 SDK 连接失效（表现为模板构建时的一次就绪检查失败）。在任何自定义防火墙规则里，都要保留 loopback、入站 TCP `49983`（envd 控制通道）、以及入站 TCP `49999`（如果用了 Code Interpreter）的开放。
- 要限制*目的地*，用内建的 `network` 配置，而不是自己在沙箱内写防火墙规则——前者是文档给出的、官方支持的机制（`docs.e2b.dev/network/internet-access`），沙箱内自己写规则有像上面那样弄断控制通道的风险。
