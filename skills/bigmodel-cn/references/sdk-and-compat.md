# SDK 与生态兼容层

智谱开放平台的所有能力，底层都是对 `https://open.bigmodel.cn/api/` 下 RESTful 端点的 HTTP 调用（鉴权统一为请求头 `Authorization: Bearer <API_KEY>`，API Key 获取地址：https://bigmodel.cn/usercenter/proj-mgmt/apikeys）。在此基础上，智谱额外提供了若干"接入已有生态"的捷径：OpenAI SDK 兼容、Claude（Anthropic）API 兼容、LangChain 集成、以及官方 Python / Java SDK。本文档说明这几种方式怎么配置、彼此有什么差异，帮助已经在用某一套生态的开发者用最小改动切换到智谱模型。

具体的 endpoint、参数、请求 / 响应示例请查阅本技能包其它参考文件：对话补全见 `references/chat.md`，图像 / 视频 / 语音等多模态能力见 `references/media.md`，工具调用相关能力见 `references/tools.md`。本文件只讲"怎么用已有的 SDK/框架接进来"，不重复展开接口细节。

## 接入方式一览

| 接入方式 | 本质 | 典型使用者 | 迁移成本 |
| --- | --- | --- | --- |
| HTTP 原生调用 | 直接调用 RESTful API | 任意语言、无历史包袱的新项目 | 无，需要自行封装请求 |
| OpenAI SDK 兼容 | 官方 `openai` 库，改 `base_url` / `api_key` | 已经在用 OpenAI SDK 的项目 | 改 2 个构造参数 |
| Claude API 兼容 | 官方 `anthropic` SDK（含 Claude Code），改 `base_url` / `api_key` | 已经在用 Claude Code / Anthropic SDK 的项目 | 改 2-3 个构造参数 |
| LangChain 集成 | `langchain-openai` 的 `ChatOpenAI`，指向智谱 | 已有 LangChain 应用 | 改 `openai_api_key` / `openai_api_base` |
| 官方 Python SDK（`zai-sdk`） | 对 HTTP API 的官方 Python 封装 | 新 Python 项目，需要完整功能覆盖 | 无，原生支持 |
| 官方 Java SDK（`zai-sdk` for Java） | 对 HTTP API 的官方 Java 封装 | 新 Java 项目、企业级应用 | 无，原生支持 |

---

## 1. HTTP 原生调用

一句话说明：无论用什么编程语言，只要能发 HTTP 请求，就能调用智谱的模型服务；不需要额外安装任何 SDK。请求地址、鉴权方式、各类接口的参数与返回结构，参见 `references/chat.md`、`references/media.md`、`references/tools.md`。

**选型建议**：全新项目、目标语言没有官方 SDK（Go、Rust、PHP 等）、或希望完全掌控请求细节（自定义重试、日志、代理）时，直接用 HTTP 原生调用最灵活。

---

## 2. OpenAI SDK 兼容

智谱提供与 OpenAI API 兼容的接口：使用官方 `openai` SDK（Python / Node 等），只需要把 `api_key` 和 `base_url` 换成智谱的，其余调用代码基本不用改。这让已经用惯 OpenAI 生态（包括依赖 OpenAI 客户端协议的第三方工具）的项目可以最低成本迁移。

官方文档明确提示："某些场景下智谱与 OpenAI 接口仍存在差异，但不影响整体兼容性"——即整体协议兼容，但个别参数的取值范围/行为不完全对齐，实际调用中如遇到未预期的报错或行为，应对照 `references/chat.md` 核实参数名和取值范围。

### 环境要求

- Python 3.7.1 或更高版本
- `openai` SDK 版本不低于 1.0.0（旧版本可能有兼容性问题）

### 安装

```bash
pip install --upgrade 'openai>=1.0'

# 验证安装
python -c "import openai; print(openai.__version__)"
```

### 创建客户端

把 `base_url` 指向智谱的 `paas/v4` 端点即可，`api_key` 换成智谱的 API Key（建议通过环境变量注入，例如 `export ZAI_API_KEY=YOUR_API_KEY`）：

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.getenv("ZAI_API_KEY"),
    base_url="https://open.bigmodel.cn/api/paas/v4/"
)
```

### 基础调用示例

```python
completion = client.chat.completions.create(
    model="glm-5.3",
    messages=[
        {"role": "system", "content": "你是一个聪明且富有创造力的小说作家"},
        {"role": "user", "content": "请你作为童话故事大王，写一篇短篇童话故事"}
    ],
    top_p=0.7,
    temperature=0.9
)

print(completion.choices[0].message.content)
```

流式响应用法与 OpenAI SDK 完全一致：

```python
stream = client.chat.completions.create(
    model="glm-5.3",
    messages=[{"role": "user", "content": "写一首关于人工智能的诗"}],
    stream=True,
    temperature=0.8
)

for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### 兼容的高级功能

以下功能都可以直接用 OpenAI SDK 的标准调用方式使用，只是模型名和部分扩展参数是智谱专属的：

**推理（thinking）**：通过 `extra_body` 传入 `thinking` 参数开启：

```python
response = client.chat.completions.create(
    model='glm-5.2',
    messages=[
        {"role": "system", "content": "you are a helpful assistant"},
        {"role": "user", "content": "what is the revolution of llm?"}
    ],
    stream=True,
    extra_body={
        "thinking": {"type": "enabled"},
    }
)
for chunk in response:
    if chunk.choices[0].delta.reasoning_content:
        print(chunk.choices[0].delta.reasoning_content, end='')
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='')
```

**函数调用（Function Calling）**：`tools` / `tool_choice` 参数与 OpenAI 规范一致：

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定地点的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "地点名称，例如：北京、上海"}
                },
                "required": ["location"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="glm-5.3",
    messages=[{"role": "user", "content": "北京今天天气怎么样？"}],
    tools=tools,
    tool_choice="auto"
)

message = response.choices[0].message
if message.tool_calls:
    for tool_call in message.tool_calls:
        print(tool_call.function.name, tool_call.function.arguments)
```

**图像理解**：用 OpenAI 的多模态 `content` 数组格式，`image_url` 支持 `data:` base64 或公网 URL：

```python
import base64

def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

image_base64 = encode_image("path/to/your/image.jpg")

response = client.chat.completions.create(
    model="glm-5.3-flash",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请描述这张图片的内容"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
            ]
        }
    ],
    temperature=0.7
)
print(response.choices[0].message.content)
```

### 常用参数与差异点

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `model` | string | 必填 | 要使用的智谱模型名称 |
| `messages` | array | 必填 | 对话消息列表 |
| `temperature` | float | 0.6 | 控制输出随机性，区间为 `(0,1)` |
| `top_p` | float | 0.95 | 核采样参数（0-1） |
| `max_tokens` | integer | - | 最大输出 token 数 |
| `stream` | boolean | false | 是否使用流式输出 |
| `stop` | string/array | - | 停止生成的标记 |

> 已知差异：`temperature` 的合法区间是 `(0,1)`，OpenAI 调用中常见的 `do_sample=False`（即 `temperature=0`）在智谱这边并不适用。

### 从 OpenAI 迁移的最小改动

```python
# 原来的 OpenAI 代码
from openai import OpenAI

client = OpenAI(
    api_key="sk-...",  # OpenAI API Key
    # base_url 使用默认值
)

# 迁移到智谱，只需要修改两个地方
client = OpenAI(
    api_key="YOUR_API_KEY",  # 替换为智谱 API Key
    base_url="https://open.bigmodel.cn/api/paas/v4/"  # 添加智谱 base_url
)

# 其他代码保持不变
response = client.chat.completions.create(
    model="glm-5.3",  # 使用智谱模型
    messages=[{"role": "user", "content": "Hello!"}]
)
```

**选型建议**：项目已经用 `openai` SDK（或依赖 OpenAI 协议的第三方库/工具）时，这是迁移成本最低的方式——只改两个构造参数即可，其余业务代码不用动。

---

## 3. Claude API 兼容

智谱提供与 Claude（Anthropic）API 兼容的接口：使用官方 `anthropic` SDK（Python / TypeScript / Java），或直接用 Claude Code 等基于 Anthropic 协议的应用，只需要把 `base_url` 换成智谱的兼容端点、`api_key` 换成智谱的 API Key，模型编码换成智谱模型即可。这对已经在用 Claude Code、Claude Agent SDK 或 Anthropic 官方 SDK 的开发者尤其有用——可以在不改变现有 Agent/工具链代码结构的前提下，把请求路由到智谱模型。

官方文档同样提示："某些场景下智谱与 Claude 接口仍存在差异，但不影响整体兼容性"，未逐字段列出差异清单；文档没有给出具体的字段级差异说明，如果遇到 Claude 特有能力（例如某些扩展思维相关的细节参数）报错或行为不一致，建议先做小范围测试验证。

### 迁移方式

- 兼容端点：`https://open.bigmodel.cn/api/anthropic`
- 在[智谱开放平台](https://bigmodel.cn/usercenter/proj-mgmt/apikeys)申请 `api_key`
- 调用时把 `model` 换成智谱模型编码（如 `glm-5.3`），其余调用方式与原生 Anthropic SDK 一致

```python
# 原来的 Claude 代码
import anthropic

client = anthropic.Anthropic(
    base_url="your-base-url",
    api_key="YOUR_API_KEY",
)

# 迁移到智谱，只需要修改三个地方
client = anthropic.Anthropic(
    api_key="YOUR_API_KEY",  # 替换为智谱 API Key
    base_url="https://open.bigmodel.cn/api/anthropic"  # 配置智谱 base_url
)

# 模型编码使用智谱模型，其他代码保持不变
message = client.messages.create(
    model="glm-5.3",  # 使用智谱模型
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}]
)
```

建议将 API Key 设置为环境变量替代硬编码，例如 `export ANTHROPIC_API_KEY=YOUR_API_KEY`。Anthropic SDK / Claude Code 这类 CLI 工具通常也支持通过环境变量配置服务端点（例如 `ANTHROPIC_BASE_URL`）而不用改代码，具体变量名与用法请以所使用工具自身的文档为准；智谱官方文档为此单独提供了 Claude Code 接入指南（"畅玩 Claude Code"，见 `/cn/guide/develop/claude` 相关页面），如果目标是配置 Claude Code CLI 本身而不是写代码调用 SDK，应优先查阅该指南。

### 代码示例

**cURL**：

```bash
curl https://open.bigmodel.cn/api/anthropic/v1/messages \
     --header "x-api-key: YOUR_API_KEY" \
     --header "content-type: application/json" \
     --data \
'{
    "model": "glm-5.3",
    "max_tokens": 1024,
    "stream": true,
    "messages": [
        {"role": "user", "content": "Hello, ZHIPU"}
    ]
}'
```

**Python**（`pip install anthropic`）：

```python
import anthropic

client = anthropic.Anthropic(
    api_key="YOUR_API_KEY",
    base_url="https://open.bigmodel.cn/api/anthropic"
)

message = client.messages.create(
    model="glm-5.3",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello, ZHIPU"}]
)
print(message.content)
```

**TypeScript**（`npm install @anthropic-ai/sdk`）：

```typescript
import Anthropic from '@anthropic-ai/sdk';

const anthropic = new Anthropic({
  apiKey: 'YOUR_API_KEY',
  baseURL: 'https://open.bigmodel.cn/api/anthropic',
});

const msg = await anthropic.messages.create({
  model: 'glm-5.2',
  max_tokens: 1024,
  messages: [{ role: 'user', content: 'Hello, ZHIPU' }],
});
console.log(msg);
```

**Java**（Maven `com.anthropic:anthropic-java:2.6.0`）：`AnthropicOkHttpClient.builder().apiKey(...).baseUrl("https://open.bigmodel.cn/api/anthropic").build()`，其余调用方式与官方 Anthropic Java SDK 一致（`client.messages().create(params)`）。

### 支持的字段

从上述示例可确认兼容的核心字段：`model`（换成智谱模型编码）、`max_tokens`、`messages`（`role` + `content`）、`stream`。这些是 Anthropic Messages API 的基本调用面，属于官方文档给出的已验证兼容范围。

**选型建议**：项目已经用 Claude Code / Anthropic SDK（或任何基于 `x-api-key` + `/v1/messages` 协议的工具）时，改 `base_url` + `api_key` 是成本最低的迁移方式；如果目标是让 Claude Code CLI 本身接智谱，优先查阅智谱的 Claude Code 专属接入指南而不是自己拼 SDK 代码。

---

## 4. LangChain 集成

智谱没有提供独立的专用 `langchain-zhipu` 包，而是通过 **OpenAI 兼容层**接入 LangChain：用官方 `langchain_openai` 包里的 `ChatOpenAI` 类，把 `openai_api_key` 和 `openai_api_base` 指向智谱端点，就能获得 LangChain 的链式调用、Agent、记忆管理等全部能力。

### 环境要求

- Python 3.8 或更高版本
- `langchain_community` 版本在 0.0.32 以上（以获得最佳兼容性）

### 安装依赖

```bash
# 安装 LangChain 和相关依赖
pip install langchain langchainhub httpx_sse

# 安装 OpenAI 兼容包（LangChain 接智谱靠这个）
pip install langchain-openai
```

### 基础配置

```python
import os
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    temperature=0.6,
    model="glm-5.3",
    openai_api_key=os.getenv("ZAI_API_KEY"),
    openai_api_base="https://open.bigmodel.cn/api/paas/v4/"
)
```

### 简单对话

```python
from langchain.schema import HumanMessage, SystemMessage

messages = [
    SystemMessage(content="你是一个有用的 AI 助手"),
    HumanMessage(content="请介绍一下人工智能的发展历程")
]

response = llm(messages)
print(response.content)
```

### 提示模板与链

```python
from langchain.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个专业的{domain}专家"),
    ("human", "请解释一下{topic}的概念和应用")
])

chain = prompt | llm

response = chain.invoke({"domain": "机器学习", "topic": "深度学习"})
print(response.content)
```

### 智能代理（Agent）与自定义工具

```python
from langchain import hub
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import tool

@tool
def get_weather(city: str) -> str:
    """获取指定城市的天气信息"""
    return f"{city} 的天气：晴天，温度 25°C，湿度 60%"

tools = [get_weather]
prompt = hub.pull("hwchase17/react")
agent = create_react_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=3)

result = agent_executor.invoke({"input": "北京今天天气怎么样？"})
print(result['output'])
```

流式输出同样是原生 LangChain 用法：给 `ChatOpenAI` 传 `streaming=True` 并挂 `StreamingStdOutCallbackHandler()` 回调即可实时打印增量内容。

**选型建议**：项目已经用 LangChain（链、Agent、记忆管理等）时，用 `langchain_openai.ChatOpenAI` 指向智谱端点即可平滑接入，不需要额外的专用集成包；如果是全新项目且不需要 LangChain 的编排能力，直接用官方 `zai-sdk` 或 HTTP 调用会更轻量。

---

## 5. 官方 Python SDK（`zai-sdk`，注意与旧版 `zhipuai` 包的区别）

`zai-sdk` 是智谱当前官方维护的 Python SDK，本质上是**对 HTTP API 的封装**——`client.chat.completions.create(...)` 内部就是对 `POST /paas/v4/chat/completions` 的一次 HTTP 调用，参数、返回结构与直接调 HTTP API 是同一套。选择用 SDK 还是裸调用 HTTP，只是"要不要自己处理序列化/重试/流式解析"的取舍。

> **新旧包名提醒**：智谱较早期的 Python SDK 包名是 `zhipuai`（`pip install zhipuai`），当前官方 SDK 已经迁移为 **`zai-sdk`**（`pip install zai-sdk`，导入名为 `zai`）。二者是不同的包、不同的导入路径，写代码时不要把旧教程里的 `from zhipuai import ZhipuAI` 之类写法和新 SDK 的 `from zai import ZhipuAiClient` 混用；遇到旧代码或旧文章里的 `zhipuai` 用法，应统一按下文的 `zai-sdk` 用法改写。

### 安装

```bash
pip install zai-sdk
# 或指定版本
pip install zai-sdk==0.2.3

# 验证安装
python -c "import zai; print(zai.__version__)"
```

### 创建客户端

`zai` 包里同时暴露了 `ZhipuAiClient` 和 `ZaiClient` 两个客户端类；**国内 bigmodel.cn 平台请使用 `ZhipuAiClient`**，对应的国内 API 地址是 `https://open.bigmodel.cn/api/paas/v4/`。

```python
from zai import ZhipuAiClient
import os

# 从环境变量读取 API Key（推荐）
client = ZhipuAiClient(api_key=os.getenv("ZAI_API_KEY"))

# 或直接设置
client = ZhipuAiClient(api_key="YOUR_API_KEY")
```

### 基础对话 / 流式对话

```python
response = client.chat.completions.create(
    model="glm-5.3",
    messages=[{"role": "user", "content": "你好，请介绍一下自己!"}]
)
print(response.choices[0].message.content)

# 流式
response = client.chat.completions.create(
    model='glm-5.2',
    messages=[
        {'role': 'system', 'content': '你是一个 AI 作家.'},
        {'role': 'user', 'content': '讲一个关于 AI 的故事.'},
    ],
    stream=True,
)
for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='')
```

对话、多轮对话、函数调用、图像/视频理解与生成、文本嵌入等具体接口参数，参见本技能包的 `references/chat.md`、`references/media.md`、`references/tools.md`——SDK 里对应方法的参数与 HTTP 接口的请求体字段是一一对应的（例如 `client.images.generations(...)` 对应 `POST /paas/v4/images/generations`，`client.embeddings.create(...)` 对应嵌入接口）。

### 错误处理

```python
import zai
from zai import ZhipuAiClient

def robust_chat(message):
    client = ZhipuAiClient(api_key="YOUR_API_KEY")
    try:
        response = client.chat.completions.create(
            model="glm-5.3",
            messages=[{"role": "user", "content": message}]
        )
        return response.choices[0].message.content
    except zai.core.APIStatusError as err:
        return f"API 状态错误: {err}"
    except zai.core.APITimeoutError as err:
        return f"请求超时: {err}"
    except Exception as err:
        return f"其他错误: {err}"
```

高级配置（自定义超时、重试、连接池）通过构造参数直接传入即可：`ZhipuAiClient(api_key=..., base_url="https://open.bigmodel.cn/api/paas/v4/", timeout=httpx.Timeout(timeout=300.0, connect=8.0), max_retries=3, http_client=httpx.Client(...))`。

**选型建议**：新的 Python 项目、需要 SDK 帮忙处理类型提示/流式解析/重试的，直接用 `zai-sdk`；如果只是想快速验证一个接口或者项目不想引入额外依赖，直接 HTTP 调用也完全够用（两者底层是同一套 API）。看到 `zhipuai` 包名的旧代码，一律视为过时用法，改写为 `zai-sdk`。

---

## 6. 官方 Java SDK（`zai-sdk` for Java，Maven 坐标 `ai.z.openapi:zai-sdk`）

Java SDK 同样是对 HTTP API 的封装，面向需要类型安全、企业级高并发场景的 Java 项目。

### 添加依赖

Maven：

```xml
<dependency>
    <groupId>ai.z.openapi</groupId>
    <artifactId>zai-sdk</artifactId>
    <version>0.3.5</version>
</dependency>
```

Gradle：

```gradle
implementation 'ai.z.openapi:zai-sdk:0.3.5'
```

环境要求：Java 1.8 或更高版本，Maven 3.6+ 或 Gradle 6.0+。

### 创建客户端

同样使用 `ZhipuAiClient`（国内 bigmodel.cn 平台），API 地址为 `https://open.bigmodel.cn/api/paas/v4/`：

```java
import ai.z.openapi.ZhipuAiClient;

public class QuickStart {
    public static void main(String[] args) {
        // 从环境变量读取 API Key
        ZhipuAiClient client = ZhipuAiClient.builder().ofZHIPU()
            .apiKey(System.getenv("ZAI_API_KEY"))
            .build();
    }
}
```

### 基础对话

```java
import ai.z.openapi.ZhipuAiClient;
import ai.z.openapi.service.model.*;
import java.util.Arrays;

public class BasicChat {
    public static void main(String[] args) {
        ZhipuAiClient client = ZhipuAiClient.builder().ofZHIPU()
            .apiKey("YOUR_API_KEY")
            .build();

        ChatCompletionCreateParams request = ChatCompletionCreateParams.builder()
            .model("glm-5.3")
            .messages(Arrays.asList(
                ChatMessage.builder()
                    .role(ChatMessageRole.USER.value())
                    .content("你好，请介绍一下自己")
                    .build()
            ))
            .build();

        ChatCompletionResponse response = client.chat().createChatCompletion(request);

        if (response.isSuccess()) {
            Object reply = response.getData().getChoices().get(0).getMessage();
            System.out.println("AI 回复: " + reply);
        } else {
            System.err.println("错误: " + response.getMsg());
        }
    }
}
```

流式对话只需在构造请求时加 `.stream(true)`，响应通过 `response.getFlowable().subscribe(onNext, onError, onComplete)` 以 RxJava 风格订阅每个数据块（`data.getChoices().get(0).getDelta()` 取增量内容）。

函数调用、图像理解/生成、文本嵌入等能力的 Java 用法都遵循同样的模式——`client.<模块>().<方法>(request)` 对应 HTTP API 的一个端点，字段名与 `references/chat.md` / `references/media.md` / `references/tools.md` 中记录的请求体字段基本一一对应。

**选型建议**：Java / Kotlin 技术栈的新项目，尤其是企业级、高并发场景，优先用官方 `zai-sdk`（Maven `ai.z.openapi:zai-sdk`），可以获得完整的类型定义和编译期检查；如果只是轻量脚本或已有自建 HTTP 客户端封装，直接调 HTTP 接口也可以。
