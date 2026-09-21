# 模板与 React Email

> ⚠ 本文件的全部内容都是 `⚠ 文档原文，未实测`——整理自 `resend.com/docs`（抓取于 2026-09-21），未经真实 API 调用确认。见 SKILL.md 里的验证状态说明。

本 skill 在这一块刻意写得比较浅——React Email 是一个独立的开源库（`react.email`），有自己完整的文档；这份文件只覆盖它怎么和 Resend 的发信 API 对接，以及 Resend 自己的托管 Templates 功能。不要把这份文件当成 React Email 的参考手册。

## 三种构建邮件正文的方式——每次发送选一种

`POST /emails` 只接受一种内容模式；**`html`/`text`/`react` 和 `template` 互斥**（见 `sending-emails.md`)——`template` 和另外三者中任意一个同时出现都会返回校验错误。

| 模式 | 是什么 | 什么时候用 |
|---|---|---|
| 纯 `html`（+ 可选 `text`） | 请求体里的原始 HTML 字符串。 | 简单邮件，或者 HTML 是由 React 以外的东西生成的（服务端模板、CMS 等）。 |
| `react` | 一个 React 组件，**以已渲染/已调用组件的形式传入，不是 JSX**——`react: WelcomeEmail({ name: 'John' })`，不是 `react: <WelcomeEmail name="John" />`（依据 Resend 自己的 AI onboarding 防护文档）。**仅 Node.js SDK 支持**——其他语言 SDK 或原生 HTTP API 都不接受这个字段。 | 已经在 Node/TypeScript 代码库里，想用 React Email 的组件库（`react-email`/`@react-email/components` 里的 `Body`、`Container`、`Button`、`Tailwind` 等）构建类型安全、组件化的邮件正文。 |
| `template`（`{id, variables}`） | 一个 **Resend 托管的 Template**——通过 dashboard、API 创建，或者通过 CLI 从一个 React Email 项目上传——发送时按 id/别名引用，用 `variables` 填充 `{{{VARIABLE}}}` 占位符。 | 团队里的非开发人员需要改文案又不想走发布流程；想要模板的版本历史；想让同一个模板在多个触发点复用，不必每次都在代码里重新定义 HTML。 |

## React Email —— 这个库本身（简要）

[React Email](https://react.email) 是 Resend 的配套开源项目：用于构建邮件的 React 组件（支持 Tailwind）、一个本地热重载预览服务器，以及渲染成邮件安全的 HTML/纯文本。由 Resend 团队维护，但是一个**独立的包/库**，不是 `resend` SDK 的一部分。

- 脚手架初始化一个项目：`npx create-email@latest`（或 `yarn create email` / `pnpm create email` / `bun create email`)。
- 在 `emails/` 下写组件，从 `react-email`（或 `@react-email/components`）导入。
- 本地热重载预览：`npm run email:dev` → `localhost:3000`。预览服务器的工具栏里自带一个 linter、一个基于 `caniemail` 的兼容性检查器，以及一个垃圾邮件评分检查器。
- 直接用 Node SDK 的 `react` 字段（见上表）从源码发送——不需要额外的构建/上传步骤就能发。

## 把一个 React Email 模板上传到 Resend Templates

只有想把模板**存到 Resend 上**（可在 dashboard 编辑、带版本历史、能被任意语言的 SDK 通过 `template.id` 复用，不只是 Node）才需要这一步。通过 React Email CLI：

```bash
npx react-email@latest resend setup   # prompts for a Full-Access API key, one-time
```

然后在正在运行的预览服务器工具栏上，在 "Resend" 标签页里选 **Upload** 或 **Bulk Upload**。断开连接：`npx react-email@latest resend reset`。

## Resend Templates API（供任意语言通过 `template.id` 发送）

不在本 skill 的深入覆盖范围内（这是一个很小、自成一体的增删改查接口集合)——端点包括 `POST /templates`、`GET /templates`、`GET /templates/{id}`、`PATCH /templates/{id}`、`DELETE /templates/{id}`、`POST /templates/{id}/publish`、`POST /templates/{id}/duplicate`。用之前值得知道的几件事：

- **发送时只能用*已发布*的模板**——一个草稿模板的 `id` 在 `POST /emails` 的 `template.id` 里用不了。具体会报什么错——⚠ 文档原文，未实测，文档未说明。
- 变量的 key：仅限 ASCII 字母/数字/`_`，最长 50 个字符；**`FIRST_NAME`、`LAST_NAME`、`EMAIL`、`UNSUBSCRIBE_URL` 是保留名**，不能当自定义变量的 key 用。
- 变量的值：字符串最长 2,000 个字符，或数字最大 2^53 − 1。
- 如果模板的 HTML 里引用了一个发送时 `variables` 没有传的变量，发送调用会抛出/返回一个校验错误,而不是静默渲染成空白/占位符——依据是 `POST /emails` 的 API 参考文档。
- 发送时 payload 里传的 `from`、`subject`、`reply_to` 会**覆盖**模板自己的默认值;如果模板对某个字段没有默认值，你必须在 payload 里提供，否则发送会失败。

## 快速参考 —— 接下来该查哪份文档

- React Email 组件目录：`react.email/docs/components/html`
- Resend Templates dashboard 功能（变量、版本历史）：`resend.com/docs/dashboard/templates/introduction`
- 把 React Email 可视化编辑器嵌入你自己的应用：`resend.com/docs/knowledge-base/embed-react-email-editor`
