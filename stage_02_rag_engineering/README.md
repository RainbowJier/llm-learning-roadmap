# Stage 2：RAG 工程

## 可运行基线

```bash
python -m pytest stage_02_rag_engineering/tests -q
python stage_02_rag_engineering/code_examples/01_toy_rag.py
```

当前 baseline 只使用标准库：

1. 文本切分
2. BM25 风格词法检索
3. 最小拒答逻辑
4. 可复现测试集

它不是生产向量检索器，也不代表最终效果。Embedding、Chroma、reranker、Ragas 和真实文档解析器都应在这个基线稳定后作为可选扩展加入。

## 评估边界

`datasets/test_set.json` 是小型示例集。正式实验必须记录数据来源、许可证、固定测试集、版本、基线和测量命令，避免把示例结果误写成生产指标。
