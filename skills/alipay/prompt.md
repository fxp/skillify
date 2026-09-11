把这份 skill 装进你的 Agent，让它写支付宝收款的接入代码时不再凭记忆编参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill alipay --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill alipay --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/alipay/alipay.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」「照通用经验写容易错的地方（来自文档，未实测）」三节；
2. `references/` 下有 7 个 `.md`，其中 `signing-and-protocols.md` 讲的是旧版 gateway.do 网关与新版 v3 两套协议的签名，`notify-and-verify.md` 讲的是异步通知验签与 success 应答；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 6 处「文档与无凭证探测不符」的标记。

## 这份 skill 覆盖什么

支付宝开放平台（`opendocs.alipay.com`）的商户收款：旧版网关与 v3 的签名（公钥模式 / 公钥证书模式）、
当面付（付款码、订单码、轮询与撤销）、电脑网站 / 手机网站 / APP 支付、交易查询 / 退款 / 退款查询 / 关单 / 对账单、
异步通知验签、沙箱环境、错误码。
最常见的坑是把 `code=10000` 当成付款或退款成功、回调验签没去掉 `sign_type`、回调没回纯文本 `success`——
这些都在 `SKILL.md` 的规则层里直接写明。

小程序 / JSAPI 支付、商家扣款、预授权、分账、转账到支付宝账户不在本 skill 范围内。

## 版本

文档版，抓取于 **2026-09-11**，**未用真实凭证验证**：只做了无凭证探测（伪造 app_id 的只读请求），
签名能否通过、业务错误码、异步通知的真实报文都没有实测过。实际调用报错时**以 API 的真实返回为准**，
并去 `opendocs.alipay.com` 核实最新情况。
