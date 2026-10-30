# 检验项目：企业文档智能问答系统 v1

> 全局周次：Week 19-20 ｜ 阶段内周次：Week 11-12 ｜ 这是扩展项目蓝图，不计入核心必修小时 ｜ 前置：01-06全部文档

---

## 项目概述

把Stage 2所有组件组装成一个可演示、可评估、可迭代的完整系统。

```
用户 ⇄ Streamlit UI
          │
          ▼
    FastAPI 服务 ──► QueryPipeline（改写→混合检索→重排→父块）
          │                        │
          │                   向量库(Chroma) + BM25 + Reranker
          ▼                        ▲
    LLM生成(带引用+拒答)      离线索引管线(解析→切分→入库)
          │
          ▼
    评估报告（Ragas）+ BadCase管理
```

---

## Week 10: 索引管线工程化（20小时）

### Day 1-2: 离线pipeline脚本

```python
# scripts/build_index.py —— 一键重建索引
"""用法: python scripts/build_index.py --docs datasets/documents/ --version v5"""
import argparse, hashlib, json
from pathlib import Path
from app.parsing.parser import DocumentParser
from app.chunking.parent_child import ParentChildChunker
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.vector import VectorRetriever

async def build(docs_dir: str, version: str):
    parser, chunker = DocumentParser(), ParentChildChunker()
    all_children, parent_store = [], {}

    for f in Path(docs_dir).glob("**/*"):
        if f.suffix.lower() not in {".pdf", ".docx", ".html", ".md", ".txt"}:
            continue
        doc = await parser.parse(str(f))
        parents, children = chunker.split(doc["elements"], doc["doc_id"])
        parent_store.update(dict(parents))
        all_children.extend(
            [{"id": f"{c.parent_id}_c{i}", "text": c.child,
              "parent_id": c.parent_id, "doc_id": doc["doc_id"]}
             for i, c in enumerate(children)])

    # 幂等：同名collection先删再建
    VectorRetriever(collection=f"rag_{version}").rebuild(all_children)
    BM25Retriever().build(all_children)
    json.dump(parent_store, open(f"datasets/parents_{version}.json", "w"))
    print(f"indexed {len(all_children)} children, {len(parent_store)} parents")

if __name__ == "__main__":
    import asyncio
    p = argparse.ArgumentParser()
    p.add_argument("--docs", default="datasets/documents/")
    p.add_argument("--version", default="v1")
    a = p.parse_args()
    asyncio.run(build(a.docs, a.version))
```

要求：**可重复运行、有版本号、输出统计信息**（chunk数、父块数、平均长度）。

### Day 3-4: 生成模块（引用+拒答）

```python
GENERATE_PROMPT = """严格根据以下参考内容回答问题。

规则：
1. 只使用参考内容中的信息，禁止使用任何外部知识
2. 回答末尾用[1][2]标注引用了哪些参考
3. 如果参考内容不足以回答，只回复："根据现有文档无法回答该问题。"

参考内容：
{context}

问题：{question}

回答："""

async def generate(question: str, results: list[dict]) -> dict:
    ctx = "\n\n".join(
        f"[{i+1}] ({r['doc_id']}) {r['context']}"
        for i, r in enumerate(results))
    answer = await llm.chat(
        GENERATE_PROMPT.format(context=ctx, question=question),
        temperature=0)                        # 事实型问答温度=0
    return {"answer": answer,
            "sources": [r["doc_id"] for r in results]}
```

### Day 5: API层

```python
# app/api.py
@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    result = await pipeline.run(req.question)       # 改写+检索+父块
    gen = await generate(result["rewritten"], result["results"])
    return AskResponse(answer=gen["answer"],
                       rewritten_query=result["rewritten"],
                       sources=gen["sources"],
                       latency_ms=...)
```

**Week 10验收**：`POST /ask` 全链路跑通，返回答案+引用+改写后的问题。

---

## Week 11: UI + 评估面板（20小时）

### Streamlit界面（Day 1-3，不求美，求能演示）

```python
# ui/app.py
import streamlit as st, httpx

st.title("企业知识库问答")
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:            # 渲染历史
    st.chat_message(m["role"]).write(m["content"])

if q := st.chat_input("提问："):
    st.chat_message("user").write(q)
    resp = httpx.post("http://localhost:8000/ask",
                      json={"question": q}).json()
    st.chat_message("assistant").write(resp["answer"])
    st.caption(f"改写后: {resp['rewritten_query']} | "
               f"来源: {', '.join(set(resp['sources']))} | "
               f"{resp['latency_ms']:.0f}ms")
    st.session_state.messages.extend([
        {"role": "user", "content": q},
        {"role": "assistant", "content": resp["answer"]},
    ])
```

侧边栏加：重建索引按钮 / 跑评估按钮 / BadCase列表展示。

### 评估CLI + 报告（Day 4-5）

```bash
python scripts/evaluate.py --test-set datasets/test_set.json --out reports/v5.json
# 输出: 四指标 + 拒答率 + 最差20个case明细
```

**Week 11验收**：演示动线完整——界面提问→看答案和引用→侧栏一键跑评估→看到指标。

---

## Week 12: 最后一轮优化 + 文档（20小时）

### Day 1-4: 按BadCase归因做最后冲刺

从06文档的评估日志里挑还没达标的指标，针对性修：
- 还差CR → 检查chunking边界case / top_k / HyDE
- 还差Faith → 检查拒答prompt / 无关上下文过滤
- 还差拒答率 → 明确"不可回答"判定规则，宁可多拒不可编

### Day 5: 交付物打包

```
rag_system_v1/
├── app/                      # 完整代码
├── scripts/                  # build_index.py / evaluate.py
├── datasets/
│   ├── documents/            # 原始脏语料
│   ├── parents_v1.json
│   └── test_set.json         # 200条
├── reports/
│   ├── optimization_log.md   # v0→v5全记录（简历素材！）
│   └── eval_v5.json
├── ui/app.py
├── tests/                    # 覆盖率≥80%
└── README.md                 # 架构图+指标表+复现步骤
```

README必备的指标表（最终版）：

| 指标 | v0基线 | v5最终 |
|------|-------|--------|
| Context Recall | 62% | __% |
| Context Precision | 65% | __% |
| Faithfulness | 82% | __% |
| Answer Relevancy | 80% | __% |
| 拒答正确率 | 10% | __% |
| P95延迟 | - | __ms |

---

## ✅ 最终验收清单

**功能**
- [ ] 一键重建索引（幂等、带版本）
- [ ] `/ask` 返回答案+引用+改写query+延迟
- [ ] Streamlit界面可完整演示
- [ ] 评估一键跑出报告

**指标（硬门槛）**
- [ ] CR ≥ 85%，CP ≥ 80%，Faith ≥ 90%，AR ≥ 85%
- [ ] 拒答正确率 ≥ 50%
- [ ] P95延迟 < 1.5s

**质量**
- [ ] pytest覆盖 ≥ 80%
- [ ] optimization_log 完整（≥5个版本演进）
- [ ] README可让陌生人复现

**Git**
- [ ] 提交历史清晰（每版本一个tag）
- [ ] `git tag v0-baseline` … `git tag v5-final`

---

## 完成后的动作

1. 写技术博客《从62%到86%：我的RAG检索优化实录》——**这篇就是你的第一篇面试作品**
2. 学习总结存 `progress/`
3. 进入 Stage 3：`../stage_03_agent_workflow/01_agent_design_paradigm.md`
