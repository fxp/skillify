# FAQ 检索脚本

## 功能说明
该脚本实现了基于智谱AI embedding-3模型的FAQ检索系统：

1. 读取`faq.txt`文件（位于run-2目录）
2. 使用embedding-3模型将每条FAQ向量化
3. 保存向量数据到`vectors.json`
4. 使用"发票怎么开"作为查询词计算余弦相似度
5. 返回top-3最相似的结果并打印到stdout

## 使用方法

1. 设置环境变量：
```bash
export ZHIPUAI_API_KEY="your_api_key_here"
```

2. 运行脚本：
```bash
python3 main.py
```

## 输出说明
脚本会输出：
- FAQ条数统计
- 向量化进度
- 保存向量文件确认
- 查询词
- Top-3相似结果，包含相似度和原文

## 文件说明
- `main.py`: 主程序脚本
- `vectors.json`: 生成的向量数据文件
- `README.md`: 本说明文件