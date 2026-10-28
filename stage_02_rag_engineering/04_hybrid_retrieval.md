# 混合检索与重排

> 对应周次：Week 6-7 ｜ 投入：20小时 ｜ 前置：03_chunking_strategies.md

---

## 本文档目标

实现完整的 `HybridRetriever`：BM25 + 向量双路召回 → 合并去重 → RRF融合 → CrossEncoder重排 → 取父块。这是RAG检索侧的最终形态。

---

## Step 1: BM25关键词检索（4小时）

### 1.1 原理直觉（面试要会讲）

> BM25 = 改进版TF-IDF。核心思想：词在当前文档出现越多越相关（但有饱和），词在越少的文档出现越值钱。**它是"字面精确匹配"的数学化**，恰好补向量检索的短板。

### 1.2 实现

```python
# pip install rank-bm25 jieba
import jieba
from rank_bm25 import BM25Okapi

class BM25Retriever:
    def __init__(self):
        self.bm25 = None
        self.docs: list[dict] = []

    def build(self, chunks: list[dict]):
        """chunks: [{'id':..., 'text':..., 'parent_id':...}]"""
        self.docs = chunks
        tokenized = [list(jieba.cut(c["text"])) for c in chunks]
        self.bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int = 50) -> list[tuple[dict, float]]:
        tokens = list(jieba.cut(query))
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(zip(self.docs, scores),
                        key=lambda x: x[1], reverse=True)[:top_k]
        return ranked
```

**验证实验**：构造语料含 `A801-Max` 和 `A802-Pro` 两段。分别用向量检索和BM25查 `A802-Pro参数`：
- BM25必中A802（字面命中）
- 向量可能返回A801（语义近似）
把两个结果都截图/记录进日志——这就是混合检索必要性的**第一手证据**。

---

## Step 2: 向量检索（4小时）

```python
# pip install chromadb sentence-transformers
import chromadb
from sentence_transformers import SentenceTransformer

class VectorRetriever:
    def __init__(self, model_name="BAAI/bge-m3",
                 persist_dir="./vec_db", collection="rag_v1"):
        self.model = SentenceTransformer(model_name)   # 中文首选bge系
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.col = self.client.get_or_create_collection(collection)

    def build(self, chunks: list[dict]):
        # bge系模型官方建议：query侧加指令前缀（m3不需要，bge-v1.5需要"为这个句子生成表示...")
        texts = [c["text"] for c in chunks]
        embs = self.model.encode(texts, normalize_embeddings=True,
                                 show_progress_bar=True)
        self.col.add(ids=[c["id"] for c in chunks],
                     embeddings=embs.tolist(),
                     documents=texts,
                     metadatas=[{"parent_id": c["parent_id"],
                                 "doc_id": c["doc_id"]} for c in chunks])

    def search(self, query: str, top_k: int = 50):
        q_emb = self.model.encode([query], normalize_embeddings=True)
        res = self.col.query(query_embeddings=q_emb.tolist(), n_results=top_k)
        return [{"id": i, "text": d, "meta": m, "score": s}
                for i, d, m, s in zip(res["ids"][0], res["documents"][0],
                                      res["metadatas"][0], res["distances"][0])]
```

要点：
- `normalize_embeddings=True` + 余弦距离，效果最稳
- 元数据必须带 `parent_id`（父子切分的钩子在这里用）
- Chroma够用到百万级；换Milvus的时机：数据量>100万或需要分布式

---

## Step 3: 双路融合：RRF（3小时）

两路分数**量纲不同**（BM25是0~几十，余弦是0~1），不能直接加。用RRF（Reciprocal Rank Fusion）只看排名：

```python
def rrf_fuse(list_a: list[dict], list_b: list[dict],
             k: int = 60, top_n: int = 100) -> list[dict]:
    """RRF: score(d) = Σ 1/(k + rank_i(d))，k=60是论文默认"""
    scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for lst in (list_a, list_b):
        for rank, item in enumerate(lst, start=1):
            did = item["id"]
            scores[did] = scores.get(did, 0) + 1.0 / (k + rank)
            doc_map.setdefault(did, item)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [{**doc_map[did], "fused_score": s} for did, s in ranked[:top_n]]
```

**直觉**：一个文档如果在两路里都排名靠前，它的RRF分就高——"两路都说是"比"一路说很棒"可信。

---

## Step 4: CrossEncoder重排（4小时）

### 4.1 为什么还要重排

向量检索是**双塔**：query和doc各自编码再算距离（快但粗）。Reranker是**交叉编码**：把(query, doc)拼一起过模型（慢但准，能读出"A802-Pro≠A801-Max"这种精确否定关系）。所以：粗召回用双塔保速度，精排用交叉保质量。

```python
# pip install sentence-transformers  (模型约2GB，首次自动下载)
from sentence_transformers import CrossEncoder

class Reranker:
    def __init__(self, model_name="BAAI/bge-reranker-v2-m3"):
        self.model = CrossEncoder(model_name, max_length=512)

    def rerank(self, query: str, candidates: list[dict],
               top_k: int = 5) -> list[dict]:
        pairs = [(query, c["text"][:1000]) for c in candidates]
        scores = self.model.predict(pairs)          # batch打分
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)
        return sorted(candidates, key=lambda x: x["rerank_score"],
                      reverse=True)[:top_k]
```

### 4.2 组装完整HybridRetriever

```python
class HybridRetriever:
    def __init__(self, bm25, vec, reranker, parent_store: dict[str, str]):
        self.bm25, self.vec, self.reranker = bm25, vec, reranker
        self.parent_store = parent_store

    async def retrieve(self, query: str, top_k: int = 5,
                       with_parents: bool = True):
        # 1. 双路召回（各50条）
        bm25_hits = self.bm25.search(query, top_k=50)
        vec_hits = self.vec.search(query, top_k=50)
        # 2. RRF融合成100条候选
        fused = rrf_fuse(bm25_hits, vec_hits, top_n=100)
        # 3. 重排取top_k
        top = self.reranker.rerank(query, fused, top_k=top_k)
        # 4. 换父块做上下文
        if with_parents:
            for t in top:
                pid = t["meta"]["parent_id"]
                t["context"] = self.parent_store.get(pid, t["text"])
        return top
```

---

## Step 5: 消融实验（5小时）

**逐个组件打开，记录指标变化**——这是本阶段最重要的实验，面试的杀手锏：

| 配置 | 实验 | 记录（10个问题人工判top5命中） |
|------|------|------------|
| A | 仅向量 top5 | __/10 |
| B | 仅BM25 top5 | __/10 |
| C | RRF融合 top5（无重排） | __/10 |
| D | 融合+重排 top5（完整） | __/10 |
| E | D + 父块上下文（回答完整性人工判） | __/10 |

预期规律（如果你的数据不符，分析原因更有价值）：
- C > A 且 C > B（融合优于单路）
- D ≥ C（重排再提一截）
- E 的"回答完整度"显著高于 D

**把这张表写进 `progress/optimization_log.md`，它就是你简历上"召回率从62%提到89%"的原始出处。**

---

## ✅ 验收清单

- [ ] BM25对精确型号查询必中（有实验记录）
- [ ] RRF融合实现正确（单测：构造两路排名，手算RRF验证）
- [ ] 完整链路：双路→融合→重排→父块，一次调用跑通
- [ ] 消融实验A-E数据完整记录

---

## 性能与成本提示

| 环节 | 耗时量级 | 优化手段 |
|------|---------|---------|
| BM25检索 | <10ms | 无需优化 |
| 向量检索 | 10-50ms | 索引HNSW，控制库规模 |
| Rerank 100条 | 300-800ms(CPU) | 降候选到50条/换GPU/截断长度 |

P95预算参考：检索+重排控制在 **1秒内**，给生成留时间。

---

**下一篇** → [05_query_rewriting.md](./05_query_rewriting.md)
