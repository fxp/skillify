# GLM Coding Plan 视觉识别测试

## 项目说明

本项目测试使用 GLM Coding Plan 编程套餐的额度进行图片识别（发票OCR）的能力。

## 脚本文件

### main.py（主脚本）
- **用途**：使用 GLM Coding Plan 套餐额度识别 invoice.png 图片内容
- **模型**：glm-5.3-flash（支持多模态）
- **API端点**：`https://open.bigmodel.cn/api/coding/paas/v4`
- **环境变量**：`GLM_CODING_PLAN_API_KEY`

### test_standard_api.py（对比测试脚本）
- **用途**：使用标准API（非套餐）测试视觉识别能力（仅用于对比）
- **模型**：glm-5.3-flash
- **API端点**：`https://open.bigmodel.cn/api/paas/v4`
- **环境变量**：`ZHIPUAI_API_KEY`

## 使用方法

### 1. 设置环境变量
```bash
export GLM_CODING_PLAN_API_KEY="你的Coding Plan API Key"
```

### 2. 准备图片文件
将需要识别的发票图片命名为 `invoice.png`，放在同一目录下。

### 3. 运行脚本
```bash
python3 main.py
```

## 重要说明

### 关于 GLM Coding Plan 套餐的限制

根据参考资料，GLM Coding Plan 套餐有以下限制：

1. **只能使用特定模型**：
   - `glm-5.3`
   - `glm-5.3-flash`（支持视觉）
   - 其他模型会被自动路由或报错

2. **不支持的能力**：
   - Embeddings
   - Rerank
   - 图像生成
   - 语音识别/合成
   - 文件解析（除了chat/completions中的reader）
   - 独立的web_search

3. **视觉能力限制**：
   - 虽然 `glm-5.3-flash` 支持多模态，但官方文档没有明确说明Coding Plan套餐是否包含视觉识别能力
   - 可能会出现 1113 或 429 错误，表示该能力不在套餐范围内

### 预期结果分析

1. **如果成功**：
   - 脚本会正常识别发票内容
   - 显示实际使用的模型名称
   - 显示Token使用情况

2. **如果失败（预期情况）**：
   - 可能出现 1113 错误（余额不足）
   - 可能出现 429 错误（额度用完或能力不在套餐内）
   - 这说明 GLM Coding Plan 套餐可能不支持视觉识别能力

## 结论

根据参考资料分析：
- GLM Coding Plan 套餐主要针对编程对话场景
- 虽然套餐Key可以访问 `glm-5.3-flash` 模型，但该套餐可能**不支持**视觉识别能力
- 如果需要视觉识别功能，应该使用标准API Key调用专门的视觉模型（如 `glm-4.6v`）

## 验证方法

运行 `main.py` 后，观察输出：
1. 如果成功识别发票 → 套餐支持视觉能力
2. 如果出现 1113/429 错误 → 套餐不支持视觉能力