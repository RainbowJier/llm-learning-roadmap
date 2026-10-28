# 性能优化

> 投入：12小时 ｜ 前置：03_fault_tolerance.md

---

## 本文档目标

掌握大模型应用的性能三板斧：**缓存、并行、减负**。每招都先测量、再优化、后对比——没有数据的优化是玄学。

---

## Step 1: 先测量——延迟分解（2小时）

用Stage 4-01的trace数据，把一次请求拆成瀑布图：

```
总延迟 2.8s 分解:
  ├─ 改写LLM调用     0.8s (29%)
  ├─ 混合检索        0.4s (14%)
  ├─ Rerank         0.5s (18%)
  ├─ 生成LLM调用     1.0s (36%)
  └─ 其他            0.1s
→ 优化优先级一目了然: LLM调用占65%，先优化它
```

**规则：优化哪一段，由瀑布图决定，不由直觉决定。**

---

## Step 2: 缓存三层（4小时）

### 2.1 精确缓存：相同问题直接回

```python
import hashlib, json
import redis.asyncio as redis

r = redis.Redis()

async def cached_answer(question: str, ttl: int = 3600):
    key = f"ans:{hashlib.md5(question.encode()).hexdigest()}"
    if (hit := await r.get(key)):
        return json.loads(hit), True                    # 命中
    answer = await full_pipeline(question)
    await r.setex(key, ttl, json.dumps(answer))
    return answer, False
```

### 2.2 语义缓存：意思一样的问题也回（大模型应用特色）

```python
async def semantic_cache(question: str, threshold: float = 0.95):
    q_emb = embed(question)
    # 向量库里查 "问题→答案" 缓存集合
    hits = await cache_col.query(query_embeddings=[q_emb], n_results=1)
    if hits["distances"][0][0] < (1 - threshold):       # 余弦够近
        return json.loads(hits["metadatas"][0][0]["answer"]), True
    answer = await full_pipeline(question)
    await cache_col.add(ids=[...], embeddings=[q_emb],
                        documents=[question],
                        metadatas=[{"answer": json.dumps(answer)}])
    return answer, False
```

**风险**：阈值太松 → 相似但不同的问题拿到错答案（"A801价格" vs "A802价格"距离就很近）。**先精确缓存上线，语义缓存作为消融实验**，用测试集验证无污染再开。

### 2.3 组件缓存：嵌入与检索结果

- query embedding缓存（改写后query重复率高时收益大）
- 检索结果缓存（文档没变、query没变 → 结果必然没变，可缓存长TTL）

**缓存指标进监控**（命中率是核心KPI）：`CACHE_HITS / (CACHE_HITS + CACHE_MISSES)`，目标>30%。

---

## Step 3: 并行化（3小时）

```python
# 串行版: 0.8 + 0.5 = 1.3s
rewritten = await rewrite(q)
context = await retrieve(rewritten)

# 并行版: max(0.8, 0.5) = 0.8s
# 技巧1: 改写和"用原query的粗检索"并行，改写完再精检索补一路
async def parallel_first_hop(q):
    rewrite_task = asyncio.create_task(rewrite(q))
    coarse_task = asyncio.create_task(retrieve(q, top_k=20))   # 原query先粗搜
    rewritten = await rewrite_task
    coarse = await coarse_task
    fine = await retrieve(rewritten, top_k=20)                  # 改写后精搜
    return rrf_fuse(coarse, fine)                               # 复用RRF！

# 技巧2: 三路multi-query并发（Stage 2-05已实现）
# 技巧3: fan-out工具调用（Stage 3-02已实现）
# 技巧4: 流式输出隐藏延迟 —— 首token时间(TTFT)才是用户体感指标
```

**TTFT思维**：总时长不变，但用户0.5秒看到第一个字，体感延迟就从3s变成0.5s。把**首token延迟**加进监控面板。

---

## Step 4: 减负三招（2小时）

```python
# 1. 模型分级路由: 简单任务用小模型（05_cost_control详述）
rewritten = await llm_haiku.rewrite(q)     # 改写用haiku
answer = await llm_sonnet.generate(...)    # 生成用sonnet

# 2. 上下文瘦身: 检索结果去冗余
def dedup_context(results: list[dict], max_chars: int = 3000) -> list[dict]:
    seen_parents, kept, total = set(), [], 0
    for r in sorted(results, key=lambda x: -x["rerank_score"]):
        if r["parent_id"] in seen_parents:
            continue
        seen_parents.add(r["parent_id"])
        if total + len(r["context"]) > max_chars:     # token预算硬顶
            break
        kept.append(r); total += len(r["context"])
    return kept

# 3. 输出长度约束: max_tokens按需设置 + prompt要求简洁
```

---

## Step 5: 优化闭环实验（1小时）

| 版本 | 改动 | P95 | TTFT | 缓存命中率 |
|------|------|-----|------|-----------|
| 基线 | — | 2.8s | 2.6s | 0% |
| +精确缓存 | 相同问题命中 | __ | __ | __% |
| +并行首跳 | 改写与粗检并行 | __ | __ | — |
| +模型路由 | 改写用haiku | __ | __ | — |
| +上下文瘦身 | 3000字顶 | __ | __ | — |

填满这张表，把它放进项目README——**"P95从2.8s优化到1.4s，TTFT从2.6s到0.6s"**是简历金句。

---

## ✅ 验收清单

- [ ] 延迟瀑布图（基于真实trace）
- [ ] 精确缓存上线且命中率>30%
- [ ] 语义缓存做过消融（留或删有数据）
- [ ] 并行首跳实现并回归测试通过
- [ ] 优化前后对比表完整

---

**下一篇** → [05_cost_control.md](./05_cost_control.md)
