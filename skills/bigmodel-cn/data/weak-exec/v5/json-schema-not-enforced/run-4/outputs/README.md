# 智谱 GLM 情感分析脚本

## 使用方法

1. **设置环境变量**
   ```bash
   export ZHIPUAI_API_KEY="your_api_key_here"
   ```

2. **运行脚本**
   ```bash
   python3 main.py
   ```

## 功能说明

该脚本使用智谱 GLM-4 模型对以下 3 条文本进行情感分析：
- "这家店服务太差了，再也不来了"
- "东西还行吧，没什么特别的"
- "太惊喜了，比我预期好太多，强烈推荐"

## 输出格式

输出严格按照数据库要求：
```json
{
  "sentiment": "正面"/"负面"/"中性",
  "score": 0到1之间的数字
}
```

## 依赖

- Python 3.6+
- requests 库

## 注意事项

- 确保已设置有效的 ZHIPUAI_API_KEY 环境变量
- 脚本会输出分析结果并保存到 sentiment_results.json 文件
- 所有情感分析结果都会严格验证格式，确保符合数据库要求