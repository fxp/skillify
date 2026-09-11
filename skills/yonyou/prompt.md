把这份 skill 装进你的 Agent，让它写用友 YonBIP 开放平台的对接代码时不再凭记忆编签名串、网关域名和请求外壳。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill yonyou --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill yonyou --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/yonyou/yonyou.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」「照通用经验写容易错的地方」三节，开头写明只覆盖用友 YonBIP 公有云、不覆盖 YonBIP 高级版 / NC Cloud / U8 Cloud / NC / U8；
2. `references/` 下有 7 个 `.md`：`auth-and-gateway.md`、`organization.md`、`master-data.md`、`purchase-sales-orders.md`、`gl-voucher.md`、`events.md`、`errors-and-limits.md`；
3. `references/auth-and-gateway.md` 里有「签名算法（逐步）」和「无凭证探测结果」两节。

## 这份 skill 覆盖什么

用友 YonBIP 公有云（开放平台 API 文档里的「用友 YonBIP」产品线，接口形如 `{gatewayUrl}/yonbip/…?access_token=…`）：
按租户查数据中心网关与 access_token 的 HmacSHA256 签名、业务单元与部门、客户 / 供应商 / 物料档案与分配组织、
采购订单与销售订单的保存 / 提交 / 审核 / 删除、总账凭证与会计期间、事件订阅回调的验签与解密、返回码、MDD 幂等与限流。
**不覆盖** YonBIP 高级版、NC Cloud、U8 Cloud、NC、U8（需要网关客户端的私有部署产品线）——接口不同，别拿去对接它们。

最常见的坑都在 SKILL.md 顶部：没有固定 API 域名要先按租户查网关、签名串是「名+值」直接拼接再 Base64、
token 放 URL 参数、保存后还要提交审核、批量接口 `code 200` 也可能部分失败。

## 版本

文档版，抓取于 2026-09-11，未用真实凭证验证。内容来自 open.yonyoucloud.com 文档中心的公开页面和公开 JSON 接口，
以及官方 gitee 示例仓库的 README 与源码网页；只做了 25 次伪造参数的无凭证探测（确认了路径、鉴权失败的返回格式和 3 处文档错误）。
实际调用报错时，**以网关的真实返回为准**，并去 open.yonyoucloud.com 核实最新文档与公告。
