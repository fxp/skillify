# NOTES — Agent Plan（Medium）批量生图 + 图生视频脚本

文件：`generate.py`（主脚本）、`requirements.txt`、`prompts.example.txt`。

```bash
pip install -r requirements.txt
export ARK_AGENT_PLAN_API_KEY='<Agent Plan 专属 Key>'
cp prompts.example.txt prompts.txt   # 或写自己的
python generate.py --dry-run          # 先看 AFP 估算
python generate.py                    # 生图到 out/，然后探测一次视频
python generate.py --size 2k --downscale 1024   # 想拿 1K 尺寸产物
```

## 1. 入口 / Key / 模型：为什么是这三个值

| 项 | 取值 | 理由 |
|---|---|---|
| Base URL | `https://ark.cn-beijing.volces.com/api/plan/v3` | Agent Plan 专属入口（OpenAI 协议）。**不能用 `/api/v3`**：控制台原话「请勿使用 …/api/v3，接入会产生额外费用」；实测 Agent Plan Key 打 `/api/v3` 或 `/api/coding/v3` 直接 401。脚本对 `/api/v3` 做了硬拒绝。 |
| Key | 环境变量 `ARK_AGENT_PLAN_API_KEY` | Agent Plan 控制台第 3 步「配置专属 API Key」生成的那一把（只有一把，可轮换）。它和「API Key 管理」里的方舟 API Key、Coding Plan 用的 Key **互不通用**，拿错 → `401 AuthenticationError`。Key 只走环境变量，不落盘。 |
| 图片模型 | `doubao-seedream-5.0-lite` | Agent Plan 内**唯一**的生图模型，四档均可用。Plan 入口用小写 Model Name（带点），不是标准入口的 `doubao-seedream-5-0-lite-260128`。 |
| 视频模型 | 默认 `doubao-seedance-2.0-mini` | 2.0 系列里 AFP 系数最低（115 / 万 token）。但 **Medium 档不可用**，见 §3。 |

鉴权头统一 `Authorization: Bearer <KEY>`。脚本用 `requests` 直调而不是 `openai` SDK，是为了拿到原始错误 body 里的 `error.code` 做精确分流（`UnsupportedModel` / `QuotaExceeded` / 限流码），SDK 会把它们都包成通用异常。

## 2. 「1K 的图」为什么做不到，脚本怎么处理

- `doubao-seedream-5.0-lite` 的 `size` 只接受 `2k` / `3k` / `4k` 或 `WIDTHxHEIGHT`，且像素下限是 **2560×1440 = 3,686,400**。**实测**（Agent Plan Medium，2026-09-04）传 `"1K"` 返回 `400 InvalidParameter: size must be one of 'WIDTHxHEIGHT', '2k', '3k', or '4k'`。支持 `1K` 档的是 Seedream 5.0 pro / 4.0，但这两个**不在 Agent Plan 里**，只能走标准后付费。
- 因此脚本默认 `--size 2k`（服务端回显 `2048x2048`，小写 `2k` 是实测通过的写法，大写 `2K` 未测），并提供 `--downscale 1024` 用 Pillow 在本地缩成 1K 长边。传 `--size 1k` 会直接报错并给出这条提示，避免白发请求。
- AFP 按**张**计（99 AFP / 张成功图），与像素、`output_tokens` 无关，所以 2k 和缩放后 1K 花的一样多，没有更便宜的办法。
- 其他固定参数：`response_format: url`（URL 是 24 小时有效的 TOS 签名链接，脚本拿到立刻下载）、`output_format: png`（可 `--format jpeg`）、`watermark: false`（默认是 `true`，会加「AI 生成」水印）、`sequential_image_generation: disabled`（防止模型自行出组图多扣 AFP）。
- 不传 `seed` / `guidance_scale`：图片 API 参数表里没有这两个字段。

## 3. 视频：Medium 套餐的现实

- 文档《套餐概览》明确「Small、Medium 套餐仅供轻量化体验，**不支持视频生成**」。**实测**（Medium，2026-09-04）`POST /api/plan/v3/contents/generations/tasks` + `doubao-seedance-2.0-mini` → `404 UnsupportedModel`（文案与套餐外模型完全相同，没有专门的「档位不够」错误码，别被误导去查额度）。
- 用户的原话是「如果还能用视频模型」，所以脚本**保留了探测逻辑**：图片全部完成后提交一次视频任务；收到 `404 UnsupportedModel` 就打印解释并正常退出（返回码 0，不扣 AFP，因为任务没建成）。这样同一份脚本升到 Large / Max 后无需改动即可出视频。`--skip-video` 可直接跳过。
- 同页表格里 `doubao-seedance-1.5-pro` 在 Medium 列打了 √，与正文矛盾，且标注「即将下线」，未实测。想赌一把可以 `--video-model doubao-seedance-1.5-pro --video-resolution 720p`（1.5-pro 系数无声 36 / 有声 72，比 2.0 系列便宜很多），成功与否以 API 返回为准。
- Medium 想稳定出视频的两条路：升 Large（500 元/月）/ Max（1000 元/月）；或走标准后付费 `/api/v3` + 方舟 API Key + `doubao-seedance-2-0-mini-260615`（5 秒 720p 约 2.5 元/个，需先在「开通管理」开通模型）。后者是另一套入口与 Key，脚本没有混进去。

视频参数（Large / Max 下生效）：`content` = 文案 + 第一张图（`role: first_frame`，图生视频）；`duration: 5`；`ratio: adaptive`（跟随首帧宽高比，避免居中裁剪）；`resolution: 720p`（`-fast` / `-mini` 只到 720p，脚本会校验）；`generate_audio` 默认 `false`（`--video-audio` 开启，2.0 系列 AFP 不区分有声无声）；`watermark: false`。流程是异步：创建拿 `cgt-` 任务 id → 每 10 秒 `GET /contents/generations/tasks/{id}`（查询 QPS 上限 20）→ `succeeded` 后下载 `content.video_url`（24 小时有效）。任务记录保留 7 天，超时脚本会把 id 打出来供手动再查。

首帧图来源：同一次运行直接复用刚返回的 TOS URL；`--video-only --video-from out/001-xxx.png` 重跑时改用本地文件 base64 data URI（请求体 ≤ 64 MB，2k png 几 MB 没问题）。

## 4. 额度与计费口径（Medium）

- Medium：200 元/月，**100,000 AFP / 月**；文本模型另受 5 小时 10,000、周 35,000 限额。**图片 / 视频不受 5 小时与周限额**，只受「日额度 = 月额度一半 = 50,000 AFP」和月额度约束（日额度每日 0 点刷新，月额度订阅月首日刷新）。
- 99 AFP / 张 → 理论上一天最多约 505 张、一个月 1,010 张（不算文本消耗）。`--dry-run` 会把总消耗和日额度对比并告警。
- **图片 / 视频模型不支持「超额后付费」**：额度耗尽返回 `429 QuotaExceeded`（message 含 `You have exceeded the … usage quota. It will reset at …`），不会从余额扣钱。脚本遇到这个码立即停止、不重试，已完成的图片和 manifest 都保留，等刷新后直接重跑即可续传（按 manifest 跳过已完成项，`--force` 重做）。
- 使用条款：Agent Plan 的**文本 / 向量化模型**「不可用于 API 调用」，但**图片 / 视频 / 语音模型官方就是让 Agent 通过 API 调的**（《接入视觉模型》页），本脚本只调图片 / 视频，不涉及违规风险。

## 5. 健壮性设计

- 错误判别只看 `error.code`，不解析 message（`error.type` 实测可能为空串）。`/api/plan/v3` 下不存在的路径返回 404 且 body 为空，脚本先判空再解析 JSON。
- 重试：429 限流类（`RateLimitExceeded.*`、`ModelAccount*RateLimitExceeded`、`ModelAccountIpmRateLimitExceeded`、`AccountRateLimitExceeded`、`ServerOverloaded`、`RequestBurstTooFast`）、429 排队超限（`QuotaExceeded` + `The request has exceeded the quota`）、5xx、网络超时 → 指数退避 + 抖动，最多 4 次；限流请求不计费。400 参数 / 审核类（`*SensitiveContentDetected`）、401、403、404、Plan 额度耗尽 → 不重试。
- 并发默认 2（IPM 上限 500，问题不在限流而在别一口气烧完日额度）。
- `out/manifest.jsonl` 逐行记录每张图的 prompt、本地文件、原始 URL、`data[].size`、`usage.output_tokens`、AFP，以及失败项和视频任务；支持断点续传。
- 文件名 `NNN-<文案前 40 字>.png`，中文保留。

## 6. 未实测 / 需要留意的点

- 本脚本本次**没有真实调用**（无 Key）；参数与错误码来自 skill 内标注「已用真实 API 验证（2026-09-04，Agent Plan Medium）」的记录，未标注部分为文档转录。
- `size` 大写 `2K` 未测，脚本统一转小写。
- Large / Max 档视频请求体的实际行为未测（Medium 在建任务这一步就被 404）。
- 平台模型周级上下线、抵扣系数有限时活动，报「参数非法 / 模型不存在」时以 API 返回为准并去 `www.volcengine.com/docs/82379/2366394` 核对套餐模型表。
