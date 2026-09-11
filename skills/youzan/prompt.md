把这份 skill 装进你的 Agent，让它写有赞云（有赞开放平台）的接入代码时照着文档写，不再凭记忆编参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill youzan --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill youzan --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/youzan/youzan.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「当前事实」和「照通用经验写容易错的地方（来自文档，未实测）」两节；
2. `references/` 下有 7 个 `.md`，其中 `auth-token.md` 讲自用型（silent）与工具型（authorization_code）两种换 access_token 的方式；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 1 处「文档与探测不符」的标记。

## 这份 skill 覆盖什么

有赞云开放平台（`doc.youzanyun.com`，接口域名 `open.youzanyun.com`）上商家和服务商最常接的部分：
自用型 / 工具型应用换取与刷新 access_token、订单列表与详情、发货、售后退款、商品创建查询与上下架、
客户 / 积分 / 标签、消息推送的订阅与验签、错误码与限流。
重点讲清 token 只放 URL、API 按“名称 + 版本号”拼路径、订单金额是“元”而商品价格是“分”、消息推送的 MD5 验签与去重。

## 版本

文档版，抓取于 2026-09-11，未用真实凭证验证。另做了无凭证探测（伪造 client_id / token，确认网关错误结构与 token 位置），
命令和结果见 `youzan-workspace/probe-log.md`。实际调用报错时**以 API 的真实返回为准**，并去 `doc.youzanyun.com` 核实最新情况。
