# FAQ 检索脚本说明

## 功能说明
这个脚本实现了两种 FAQ 检索方案：
1. **托管知识库方案**：使用智谱 AI 的托管知识库服务，自动上传 FAQ 文档并检索
2. **自建方案**：使用 Embedding + Rerank API 实现的替代方案

## 运行要求
- 设置环境变量：`export ZHIPUAI_API_KEY="your_api_key_here"`
- Python 3.x
- requests 库（通常会自动安装）

## 运行方式
```bash
cd /Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/paired-eval/v1/kb-fallback/run-4/outputs
python3 main.py
```

## 脚本特点
1. **优先尝试托管知识库**：如果可用，会使用更高效的托管知识库服务
2. **自动降级**：如果托管知识库不可用，自动切换到自建 embedding + rerank 方案
3. **资源清理**：运行完成后会自动清理临时文件和知识库资源
4. **详细输出**：显示每个步骤的执行情况和检索结果

## 检索结果
无论使用哪种方案，脚本都会打印出使用"退换货政策的有效期是多久"这个问题检索到的原文片段，并显示相似度分数。

## 注意事项
- 如果托管知识库因权限、配额等原因不可用，脚本会自动尝试替代方案
- 脚本包含了错误处理和超时机制，确保不会无限等待
- 所有 API 调用都会检查返回状态码，避免静默失败