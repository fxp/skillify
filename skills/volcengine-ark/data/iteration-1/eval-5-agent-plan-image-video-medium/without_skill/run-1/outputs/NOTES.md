# NOTES — 火山方舟 批量出图 + 首图转 5 秒视频

> 无 API Key，本脚本未做真实调用。以下参数基于对火山方舟（Volcengine Ark）公开 API 的了解整理；
> 首次运行前请对照控制台 **模型广场 / 套餐详情** 页面核对模型 ID 与套餐权益（见末尾"务必核对"）。

## 文件

| 文件 | 说明 |
|---|---|
| `generate.py` | 主脚本：读 `prompts.txt` → Seedream 出 1K 图 → 保存 `out/NNN.jpg` → （可选）首图用 Seedance 生成 5s 视频 `out/video_001.mp4`；结果写 `out/manifest.jsonl` |
| `requirements.txt` | 仅依赖 `requests` |
| `prompts.example.txt` | 示例文案，复制为 `prompts.txt` |

```bash
pip install -r requirements.txt
cp prompts.example.txt prompts.txt      # 换成你自己的文案
export ARK_API_KEY="<你的方舟 API Key>"
python generate.py                      # 出图 + 视频（视频尽力而为，不可用会自动跳过）
python generate.py --no-video           # 只出图
```

## Base URL / 鉴权

- **Base URL**：`https://ark.cn-beijing.volces.com/api/v3`（脚本默认，可用 `ARK_BASE_URL` 覆盖）。
  方舟的图像、视频接口都挂在这个 v3 前缀下，和对话接口共用一把 Key。
- **鉴权**：`Authorization: Bearer $ARK_API_KEY`。Key 在 控制台 → API Key 管理 里创建；Agent Plan 的
  Key 也是同一格式，套餐权益绑定在账号/Key 上，而不是靠不同的 URL 区分。
- 脚本**只从环境变量**读取 Key，不落盘、不打日志。

## 接口与模型选择

### 图片：`POST /images/generations`
- 模型：默认 `doubao-seedream-4-0-250828`（Seedream 4.0，`ARK_IMAGE_MODEL` 可换）。
  选 4.0 而不是 3.0 的原因：4.0 直接支持 `size: "1K" | "2K" | "4K"` 档位，正好对应"1K 一张图"的需求；
  3.0（`doubao-seedream-3-0-t2i-250415`）只接受 `WxH`，脚本检测到模型名含 `seedream-3` 会自动改用 `1024x1024`。
- 关键参数：
  - `size: "1K"` — 需求指定 1K；4.0 会按提示词自适应长宽比，总像素约 1K 档。
  - `response_format: "b64_json"` — 一次请求拿到图，避免 `url` 模式返回链接 24 小时过期、还要二次下载。
  - `watermark: false` — 去掉右下角"AI 生成"水印（商用素材通常不要）。
  - `sequential_image_generation: "disabled"` — 明确"一条文案一张图"，防止 4.0 的组图模式一次返回多张、多扣额度。
- 输出为 JPEG，保存为 `out/001.jpg, 002.jpg ...`（按 prompts.txt 行号）。

### 视频：`POST /contents/generations/tasks` + `GET /contents/generations/tasks/{id}`
- 视频生成是**异步任务**：先创建任务拿 `id`，再轮询直到 `status` 变为 `succeeded / failed / cancelled / expired`，
  成功后从 `content.video_url` 下载（链接同样 24h 过期，脚本立即下载）。
- 模型：默认 `doubao-seedance-1-0-pro-250528`（支持图生视频/首帧参考；`ARK_VIDEO_MODEL` 可换成
  `doubao-seedance-1-0-lite-i2v-250428` 更省额度，或更新的 `doubao-seedance-1-5-pro-*`）。
- 首图以 `data:image/jpeg;base64,...` 形式作为 `image_url` 传入（1K JPEG 远小于 10MB 限制），无需先上传到公网。
- 生成控制走 Seedance 的文本指令：`--duration 5 --resolution 720p --ratio adaptive --camerafixed false --watermark false`。
  `--duration 5` 就是需求里的 5 秒；`--ratio adaptive` 让画幅跟随首图；720p 是额度最省的实用档。
- 轮询间隔 5s，最长等 15 分钟。

## 健壮性
- 幂等：`out/NNN.jpg` / `video_001.mp4` 已存在就跳过，可随时中断重跑。
- 重试：429 / 5xx / 网络错误 指数退避最多 5 次，尊重 `Retry-After`。
- 内容审核（`*SensitiveContentDetected`）、参数错误 只记录该条并继续，不中断全批。
- 权益类错误（`ModelNotOpen` / `QuotaExceeded` / `AccountOverdueError` / 401 / 403）：
  - 出图阶段 → 立即中止（说明这把 Key 不能用该图片模型，继续跑只会全失败），退出码 2；
  - 视频阶段 → 记为 `unavailable`，图片结果保留，退出码 0。这正是"如果还能用视频模型"的落地方式。
- `--workers` 默认 1；套餐 Key 有 RPM 上限，建议 ≤ 2。

## 套餐（Agent Plan · Medium）对可行性的影响 —— 务必核对

我无法在没有 Key 的情况下查询你账号的实际权益，以下是需要你在控制台确认的三点，脚本已按"先试、不行就降级"设计：

1. **Agent Plan 额度是否覆盖 Seedream（图片）**
   方舟的订阅制套餐（Coding Plan / Agent Plan）核心权益是文本/编程模型的调用量，多模态模型是否包含、
   包含哪个版本（3.0 / 4.0），各档位（Lite / Medium / Pro）并不相同。
   → 在 控制台 → 套餐 → 权益详情 里看"可用模型列表"。若 Seedream 4.0 不在其中但 3.0 在，
   `export ARK_IMAGE_MODEL=doubao-seedream-3-0-t2i-250415` 即可（脚本自动改用 `1024x1024`）。
   若都不在，图片会走**按量计费**（Seedream 4.0 约 0.2 元/张 1K 图量级），Key 所在账号需有余额/开通该模型。

2. **视频（Seedance）大概率不在套餐内**
   视频模型按输出 token 计费、单价高，据我所知一般不放进订阅套餐额度，而是按量付费。
   所以"如果还能用视频模型"这一步：脚本会真实发起一次创建任务请求，收到 `ModelNotOpen` 等权益错误就打印提示并跳过；
   若账号已开通按量并有余额，则正常生成。5 秒 720p 一段大约几毛到一两元人民币。

3. **Medium 档位的限速**
   套餐 Key 通常按 5 小时/日 窗口限额、且有 RPM 上限。批量出图请保持 `--workers 1~2`；
   触发 429 脚本会自动退避，若持续 429 说明窗口额度用尽，等窗口刷新再重跑（幂等，不会重复出图）。

**一句话结论**：出图部分大概率可用（套餐内或按量），视频部分请视为"额外按量消费"，脚本已做自动探测与降级。
运行结束看 `out/manifest.jsonl`：每行一条记录，`status` 为 `ok / skipped / failed / unavailable`，`usage` 字段能对账实际消耗。

## 可选：改用官方 SDK
如更喜欢官方 SDK：`pip install 'volcengine-python-sdk[ark]'`，对应调用为
`Ark(api_key=...).images.generate(...)` 与 `client.content_generation.tasks.create/get(...)`，
参数名与本脚本的 HTTP 字段一一对应。这里用裸 `requests` 是为了少一层依赖、错误码看得更清楚。
