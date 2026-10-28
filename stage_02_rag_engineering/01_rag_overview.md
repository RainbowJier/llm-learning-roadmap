# RAG系统概述：从玩具到工业级

> 对应周次：Week 1（本阶段） ｜ 投入：8小时 ｜ 前置：Stage 1完成

---

## 本文档目标

建立对RAG的正确全局认知：数据流全景、玩具级和工业级的差距在哪、每个环节的工程问题是什么。**本阶段所有后续文档都是这张地图的放大**。

---

## Step 1: RAG数据流全景图（2小时）

```
【离线索引管线】                        【在线查询管线】

原始文档(PDF/Word/HTML)                 用户问题
      │                                     │
      ▼                                     ▼
 ① 解析 Parsing ────► 结构化文本      ⑤ 查询改写 Rewrite（多轮对话时）
      │                                     │
      ▼                                     ▼
 ② 清洗 Cleaning ──► 纯净Markdown    ⑥ 混合检索 Hybrid Retrieve
      │                                  ├─ 向量检索 top50
      ▼                                  └─ BM25检索 top50
 ③ 切分 Chunking（父子文档）                │
      │                                     ▼
      ▼                              ⑦ 重排 Rerank → top5
 ④ 索引 Indexing                        │
      ├─ Embedding → 向量库               ▼
      └─ 全文 → 倒排索引              ⑧ 生成 Generate（LLM+上下文）
                                          │
                                          ▼
                                    ⑨ 评估/日志（Ragas、BadCase收集）
```

**记忆口诀**：索引侧"解析-清洗-切分-索引"四步；查询侧"改写-检索-重排-生成"四步。

---

## Step 2: 玩具级 vs 工业级对照（2小时）

| 环节 | 玩具级（会被面试官秒杀） | 工业级（本文档系列要达到的） |
|------|----------------------|--------------------------|
| 解析 | `pypdf` 全文直出，表格成乱码 | 版面分析+表格转Markdown/JSON |
| 切分 | 每500字硬切 | 父子文档/语义切分，表格不腰斩 |
| 检索 | 纯向量top5 | BM25+向量双路top50，合并去重 |
| 重排 | 无 | CrossEncoder精排取top5 |
| 改写 | 无（多轮对话必挂） | 结合历史的指代消解 |
| 生成 | "请根据以下内容回答" | 引用来源+拒答机制+格式约束 |
| 评估 | 自己问几个看看 | 200条测试集+Ragas四指标持续追踪 |

### 三个典型翻车场景（面试常问，务必能复述）

**场景1：表格腰斩**
> 财务制度PDF里的差旅补贴表被500字切分拦腰截断，检索只命中表头，金额行丢了，LLM开始编造数字。
> → 根因：解析层没有把表格识别为原子单元；切分层对表格要整块保留。

**场景2：型号混淆**
> 用户查 `A802-Pro` 的参数，向量检索返回了 `A801-Max`（语义空间太近）。
> → 根因：向量模型对精确token不敏感；BM25能精确命中，所以必须混合检索。

**场景3：指代丢失**
> 用户先问"年假怎么休"，接着问"去年的能攒到今年吗"。第二句缺主语，检索不到任何东西。
> → 根因：查询侧没做改写；需要用小模型结合历史补全问题。

---

## Step 3: 技术选型清单（2小时）

### 3.1 组件选型（2026主流，先记结论后动手验证）

| 组件 | 推荐起步 | 生产可选 | 选型理由 |
|------|---------|---------|---------|
| 文档解析 | PyMuPDF(fitz) + Unstructured | MinerU / RagFlow deepdoc | 先手动踩坑再上重武器 |
| Embedding | BAAI/bge-m3（本地） | 阿里text-embedding / OpenAI | 中文效果好，m3支持稠密+稀疏 |
| 向量库 | Chroma（零配置起步） | Milvus / Qdrant / pgvector | 项目量级<100万Chroma够用 |
| BM25 | rank_bm25（内存版） | Elasticsearch / MeiliSearch | 先理解原理再上ES |
| Reranker | BAAI/bge-reranker-v2-m3 | Jina/Cohere Rerank | 中文场景标配 |
| 评估 | Ragas | DeepEval / 自建 | 社区标准 |
| 分词(jieba) | jieba | —— | BM25中文分词用 |

### 3.2 一句话原则

> **先用最简单的组合把端到端跑通（Chroma + rank_bm25 + bge-m3），拿到第一版基线指标，然后每个环节替换升级，用评估指标证明每次改进。**

这就是"评估驱动开发"，是本阶段的灵魂。

---

## Step 4: 动手跑通玩具级基线（2小时）

不写工业级代码，先让全链路转起来，**留好它当基线**：

```bash
pip install chromadb sentence-transformers rank-bm25 jieba openai
```

```python
# toy_rag.py —— 玩具级基线，仅用于对照
import chromadb
from sentence_transformers import SentenceTransformer

docs = [
    "第二章 年假管理：新员工试用期享受5天年假，转正后10天，满三年15天。",
    "第三章 报销制度：差旅住宿一线城市上限500元/晚，二线400元/晚。",
    "第四章 考勤规定：迟到30分钟以内扣款50元，超过30分钟按半天事假处理。",
]
queries = ["试用期年假几天", "北京出差住宿标准", "迟到怎么扣钱"]

model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
client = chromadb.PersistentClient(path="./chroma_db")
col = client.get_or_create_collection("toy")

col.add(
    ids=[f"doc_{i}" for i in range(len(docs))],
    documents=docs,
    embeddings=model.encode(docs).tolist(),
)

for q in queries:
    res = col.query(query_embeddings=model.encode(q).tolist(), n_results=1)
    print(f"Q: {q}\n→ {res['documents'][0][0][:40]}...\n")
```

**验收**：3个问题全部命中正确文档。把它存为 `baseline_v0.py`，本阶段结束时你会回来嘲笑它。

---

## Step 5: 本阶段作战地图（对齐后续文档）

| 文档 | 主题 | 产出 |
|------|------|------|
| 02_document_parsing.md | 解析+清洗 | 能正确处理带表格的PDF |
| 03_chunking_strategies.md | 切分策略 | 父子文档切分器 |
| 04_hybrid_retrieval.md | 混合检索+重排 | HybridRetriever类 |
| 05_query_rewriting.md | 查询改写 | 多轮对话改写器 |
| 06_evaluation_framework.md | 评估体系 | Ragas四指标报告 |
| 07_project_rag_qa.md | 检验项目 | 完整问答系统v1 |

---

## ✅ 验收清单

- [ ] 能白板画出9步数据流（索引侧4步+查询侧4步+评估）
- [ ] 能复述三个翻车场景的根因和解法
- [ ] 玩具级基线跑通并保存
- [ ] 知道每个组件的起步选型和升级路径

**下一篇** → [02_document_parsing.md](./02_document_parsing.md)
