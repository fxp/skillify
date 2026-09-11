# access_token 与应用 secret

来源：`developer.work.weixin.qq.com/document/path/91039`（获取access_token）、`90665`（基本概念）、`90664`（开发前必读）、
`92520` / `92521`（接口 / 回调 IP 段）、`90487`（简易教程·debug 模式）、`90313`（错误码排查）、`96079`（通讯录同步接口调整）。
抓取于 2026-09-11。**未用真实凭证验证**；标「无凭证探测（2026-09-11）」的是用伪造参数打出来的结果，其余报错与行为均为「文档原文，未实测」。

企业微信服务端 API 的调用凭证只有一种形态：`access_token`，由 `corpid + corpsecret` 换取。难点不在换取本身，而在于
**corpsecret 有好几种、各自权限不同，token 不能混用**。

## 我该用哪个 secret

| 我要做什么 | 用哪个 secret 换 token | 前置配置（管理后台） | 用错时典型报错（文档原文，未实测） |
|---|---|---|---|
| 以应用身份发应用消息、读可见范围内通讯录、网页授权 | 该**自建应用**的 Secret | 应用管理 → 自建 → 进入应用；2022-06-20 后新建应用需配置「企业可信IP」 | `301002` token 所属应用与 agentid 不一致；`60020` IP 不可信 |
| 写通讯录（创建/更新/删除成员、部门） | **通讯录同步** Secret（管理工具 → 通讯录同步 → 开启 API 接口同步，选“编辑”权限） | 必须配置企业可信 IP（不允许服务商 IP） | `48002` 用了非通讯录同步的 token 写通讯录 |
| 客户联系（外部联系人、客户群、联系我、群发、欢迎语） | 已配置到「客户联系 → 可调用接口的应用」里的**自建应用** Secret | 客户联系 → 权限配置：使用范围 + 可调用接口的应用 | `48002`；文档：2023-12-01 起**不再支持用系统应用 secret 调接口**（存量企业暂不受影响） |
| 审批（模板详情、提交申请、拉审批单） | 已配置到「审批 → 可调用接口的应用」里的**自建应用** Secret | 审批应用 → API → 可调用接口的应用 | `301055` 无审批应用权限 |
| 群机器人（消息推送）发群消息 | **不需要 token**，用 webhook URL 里的 `key` | 群里添加消息推送，拿到 webhookurl | `93000` webhook url 不合法 |

要点：

- **每个应用的 token 独立**：「每个应用有独立的secret，获取到的access_token只能本应用使用，所以每个应用的access_token应该分开来获取」（91039 权限说明）。
  缓存 key 至少要包含 `(corpid, 应用标识)`，不能全局一个 token。
- **通讯录同步 secret 读不到详情**：2022-08-15 起，通讯录同步助手从“新 IP”（过去 90 天未用过的 IP）调「读取成员 / 获取部门成员（详情） / 获取部门列表 / 获取单个部门详情 / 导出」会被停用，只能用「获取成员ID列表」「获取部门ID列表」拿 ID（96079）。要读姓名等请用自建应用。错误码 `48009`（文档原文）。
- **通讯录同步 secret 不能发消息**：「通讯录同步助手的access_token，仅用于同步通讯录，不能用于发消息」（90313 · 48002 排查）。
- **应用可见范围 = 权限范围**：自建应用只能对可见范围内的成员 / 部门调接口（90665）。通讯录同步助手不需要配置可见范围，默认全公司。

## 获取 access_token

**Endpoint**: `GET https://qyapi.weixin.qq.com/cgi-bin/gettoken`
**用途**: 用 corpid + 应用 secret 换调用凭证。所有业务接口的第一步。

**关键参数**（query string）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| corpid | string | 是 | — | 企业ID（管理后台“我的企业 → 企业信息 → 企业ID”） |
| corpsecret | string | 是 | — | 应用的凭证密钥，**应用需要是启用状态** |

**示例请求**

```bash
curl -s "https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=${WECOM_CORP_ID}&corpsecret=${WECOM_APP_SECRET}"
```

```python
import os, requests

resp = requests.get(
    "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
    params={"corpid": os.environ["WECOM_CORP_ID"], "corpsecret": os.environ["WECOM_APP_SECRET"]},
    timeout=10,
).json()
if resp.get("errcode", 0) != 0:
    raise RuntimeError(resp)
token, ttl = resp["access_token"], resp["expires_in"]
```

**示例响应**（文档原文）

```json
{"errcode": 0, "errmsg": "ok", "access_token": "accesstoken000001", "expires_in": 7200}
```

| 字段 | 说明 |
|---|---|
| access_token | 凭证，**最长 512 字节**，存储至少预留 512 字节 |
| expires_in | 有效秒数，正常为 7200 |

**注意事项**

- **必须缓存**，「不能频繁调用gettoken接口，否则会受到频率拦截」。具体上限 ⚠ 文档未说明（访问频率限制页 90312 没有单列 gettoken）。
- 平台「可能会出于运营需要，提前使access_token失效」→ 除按 `expires_in` 过期外，还要在收到 `40014` / `42001` 时重取一次再重试。
- 「请勿将 access_token 返回给前端」，所有调用由后台发起。
- 45009 排查（文档原文，未实测）：「如果应用的secret错误多次，会导致同一个IP被禁用一小时」——重置了 secret 却忘改配置的旧进程，会把整台机器的出口 IP 拖进封禁。
- 无凭证探测（2026-09-11）：
  - 不带任何参数 → `{"errcode":41004,"errmsg":"corpsecret missing, ..."}`（先校验 secret，再校验 corpid）；
  - `corpid=test&corpsecret=test` → `{"errcode":40013,"errmsg":"invalid corpid, hint: [...], more info at https://open.work.weixin.qq.com/devtool/query?e=40013"}`，HTTP 200；
  - 用 `http://` 访问 → nginx `301 Moved Permanently`。

## 调用业务接口时 token 放哪里

**只能拼在 URL query 里**：`https://qyapi.weixin.qq.com/cgi-bin/<path>?access_token=ACCESS_TOKEN`。

- 文档（41001 排查）：「access_token需要拼接在URL中，不能放在请求包体中」。
- 无凭证探测（2026-09-11）：把 token 放 `Authorization: Bearer FAKE_TOKEN` header 调 `GET /cgi-bin/user/get` →
  `{"errcode":41001,"errmsg":"access_token missing, ..."}`；放进 JSON body 调 `POST /cgi-bin/user/list_id` → 同样 `41001`。
  也就是说服务端完全不看 header / body 里的 token，按 OAuth 习惯写 `Authorization` 头一定失败。
- 放 URL 意味着 token 会出现在访问日志 / 代理日志里，日志脱敏要把 `access_token=` 过滤掉。

## 推荐的 token 缓存实现

```python
import os, time, threading, requests

BASE = "https://qyapi.weixin.qq.com/cgi-bin"

class WeComToken:
    """一个应用一个实例：corpid + 该应用 secret。多个应用就建多个实例。"""
    def __init__(self, corpid: str, secret: str, margin: int = 300):
        self.corpid, self.secret, self.margin = corpid, secret, margin
        self._token, self._exp = None, 0.0
        self._lock = threading.Lock()

    def get(self, force: bool = False) -> str:
        with self._lock:
            if force or not self._token or time.time() > self._exp - self.margin:
                r = requests.get(f"{BASE}/gettoken",
                                 params={"corpid": self.corpid, "corpsecret": self.secret},
                                 timeout=10).json()
                if r.get("errcode", 0) != 0:
                    raise RuntimeError(f"gettoken failed: {r}")
                self._token, self._exp = r["access_token"], time.time() + r["expires_in"]
            return self._token

def call(tok: WeComToken, method: str, path: str, *, params=None, json=None):
    """统一调用：token 进 query；40014/42001 时强制刷新重试一次；errcode 非 0 抛错。"""
    for attempt in range(2):
        q = dict(params or {}, access_token=tok.get(force=attempt == 1))
        r = requests.request(method, f"{BASE}/{path}", params=q, json=json, timeout=10)
        r.raise_for_status()                      # 未知路径是 HTTP 404（无凭证探测 2026-09-11）
        data = r.json()
        code = data.get("errcode", 0)             # 部分接口成功时不带 errcode
        if code in (40014, 42001) and attempt == 0:
            continue
        if code != 0:
            raise RuntimeError(f"{path} -> {code} {data.get('errmsg')}")
        return data

app_tok = WeComToken(os.environ["WECOM_CORP_ID"], os.environ["WECOM_APP_SECRET"])
contact_tok = WeComToken(os.environ["WECOM_CORP_ID"], os.environ["WECOM_CONTACT_SYNC_SECRET"])
```

多进程 / 多机部署时，把 token 放共享缓存（Redis 等）并加分布式锁，避免每个进程各自调 gettoken 触发频率拦截——
这是由「必须缓存、不能频繁调用」推出的工程建议，文档没有给出具体阈值。

## 可信 IP

- 「从2022年6月20号20点之后，新开启的通讯录同步助手与新创建的自建应用必须在管理端配置可信IP，仅配置的可信IP能调用接口」（90664）。
- 60020 排查（文档原文，未实测）：自建应用 / 通讯录同步助手需把本企业服务器 IP 配置到应用详情的“企业可信IP”；**第三方服务商 IP 不能调用**；配置后 **1 分钟**生效。
- 所以本地开发机直接调接口多半会 60020——要么把出口 IP 加进可信 IP，要么在已配置 IP 的服务器上跑。

## 获取企业微信接口 IP 段（出方向防火墙）

**Endpoint**: `GET https://qyapi.weixin.qq.com/cgi-bin/get_api_domain_ip?access_token=ACCESS_TOKEN`
**用途**: 取 `qyapi.weixin.qq.com` 的解析 IP 段，给**你调用企业微信**的出方向防火墙放行用。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| access_token | string | 是 | 任意应用 token，「权限说明：无限定」 |

响应（文档原文）：`{"ip_list": ["182.254.11.176", "182.254.78.66"], "errcode": 0, "errmsg": "ok"}`

- 「IP段有变更可能，当IP段变更时，新旧IP段会同时保留一段时间。建议企业每天定时拉取IP段」。
- 无凭证探测（2026-09-11）：假 token → `{"ip_list":[],"errcode":40014,"errmsg":"invalid access_token, hint: [...]"}`。

## 获取企业微信回调 IP 段（入方向防火墙）

**Endpoint**: `GET https://qyapi.weixin.qq.com/cgi-bin/getcallbackip?access_token=ACCESS_TOKEN`
**用途**: 企业微信**推送回调到你的服务器**时使用的出口 IP 段，给入方向白名单用。和上一个接口方向相反，不要混。

响应（文档原文，两处示例格式不同）：90930 示例为 `{"ip_list":["1.2.3.4","2.3.3.3"],"errcode":0,"errmsg":"ok"}`，
90238 示例为 `{"ip_list":["101.226.103.*","101.226.62.*"]}`——⚠ 文档自相矛盾：IP 段是否可能带 `*` 通配符，两处写法不一致，
解析时两种都要兼容。

- 无凭证探测（2026-09-11）：假 token → `{"ip_list":[],"errcode":40014,...}`，路径存在。

## debug 模式

- 在请求 URL 加 `debug=1`，失败时从 errmsg 复制 `hint`，到 `https://open.work.weixin.qq.com/devtool/query` 查询完整请求（含 header 与 body）（90487）。
- 「debug模式有使用频率限制，同一个api每分钟不能超过5次」，上线前必须去掉。暂不支持微盘接口。
- 无凭证探测（2026-09-11）：token 无效时加 `debug=1` 返回与不加一致（`{"errcode":40014,"errmsg":"invalid access_token"}`），没有额外 hint。

## 与 access_token 相关的错误码（摘自全局错误码，文档原文，未实测）

| errcode | 含义 | 处理 |
|---|---|---|
| 40001 | 不合法的 secret 参数（没传 / corpid 与 secret 不匹配 / 重置过 secret / 应用已停用） | 检查配置，**不要循环重试**（会导致 IP 封禁一小时） |
| 40013 | 不合法的 CorpID | 检查 corpid |
| 40014 | 不合法的 access_token（过期、含非法字符、类型不对） | 强制刷新一次 |
| 41001 | 缺少 access_token 参数（**token 必须在 URL 里**） | 检查拼接方式 |
| 41004 | 缺少 secret 参数 | — |
| 42001 | access_token 已过期 | 强制刷新一次 |
| 45009 | 接口调用超过限制 | 见 `errors-and-limits.md` |
| 48002 | API 接口无权限调用（token 所属应用不具备该接口权限） | 换对 secret / 检查“可调用接口的应用”配置 |
| 50003 | 应用已禁用 | 管理端重新启用 |
| 60020 | 不安全的访问 IP | 配置企业可信 IP，1 分钟后生效 |
| 301002 | 无权限操作指定的应用（agentid 与 token 所属应用不一致） | 用该 agentid 对应应用的 secret |
