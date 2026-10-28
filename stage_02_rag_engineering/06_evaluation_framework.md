# RAG评估体系

> 对应周次：Week 9 ｜ 投入：12小时 ｜ 前置：02-05全部文档

---

## 本文档目标

建立"评估驱动开发"的闭环：构造测试集 → Ragas四指标跑分 → 定位瓶颈环节 → 针对性优化 → 复测验证。**这是整个Stage 2的灵魂文档**。

---

## Step 1: 构建测试集（3小时）

没有测试集，一切优化都是玄学。

### 1.1 生成-人工-修订三步法

```python
# 用LLM从语料自动生成QA对候选（每篇文档10-20条）
GEN_PROMPT = """基于以下文档内容，生成5个用户可能会问的问题和标准答案。
要求：
1. 问题口语化（模拟真实用户）
2. 答案必须能从文档中找到依据
3. 覆盖数字/表格类问题至少2个
4. 输出JSON数组: [{"question":..., "answer":..., "source_quote":"原文依据片段"}]

文档：{doc}"""
```

然后**人工逐条修订**（这步不能省，LLM生成的问题30%是无意义或答案错的）：

修订标准：
- [ ] 问题表述自然（真人会这么问）
- [ ] 答案100%正确且有原文依据（source_quote必须真实存在）
- [ ] 覆盖类型分布：事实型40% / 表格数字型20% / 多条件推理型20% / 边界型（文档没有的）20%

**边界型负样本特别重要**：故意加20%语料里没有答案的问题（"公司食堂几点开饭"），标准答案="应拒答"。**这是测幻觉的关键**。

### 1.2 测试集规模与格式

```json
// datasets/test_set.json —— 目标200条
{
  "id": "qa_001",
  "question": "试用期员工有几天年假？",
  "answer": "5天",
  "source_quote": "新员工试用期（6个月）享受5天年假",
  "doc_id": "hr_policy_v3",
  "type": "fact",          // fact | table | reasoning | unanswerable
  "expected": "answerable" // answerable | refuse
}
```

---

## Step 2: 四大指标精讲（2小时）

| 指标 | 测什么 | 诊断的环节 | 直觉解释 |
|------|--------|-----------|---------|
| **Context Recall** ↑ | 标准答案的依据是否被检索到 | 检索召回 | "该找到的找到了吗" |
| **Context Precision** ↑ | 检索结果里有多少真有用 | 检索精度 | "找到的里有多少是干货" |
| **Faithfulness** ↑ | 回答是否忠于检索内容 | 生成幻觉 | "编了吗" |
| **Answer Relevancy** ↑ | 回答是否切题 | 生成质量 | "答非所问了吗" |

**排障决策树**（背下来，面试和实战都用）：

```
Context Recall低?
 ├─ 是 → 检索问题：改chunking/加BM25/调top_k/HyDE
 └─ 否 → Context Precision低?
          ├─ 是 → 加reranker/减top_k
          └─ 否 → Faithfulness低?
                   ├─ 是 → prompt加"仅根据以下内容"+拒答机制/减无关上下文
                   └─ 否 → Answer Relevancy低 → 改生成prompt/温度调0
```

---

## Step 3: Ragas接入（3小时）

```bash
pip install ragas datasets
```

```python
import asyncio
from ragas import evaluate
from ragas.metrics import (
    context_recall, context_precision,
    faithfulness, answer_relevancy,
)
from datasets import Dataset

class RAGEvaluator:
    def __init__(self, rag_pipeline):     # 你的完整pipeline
        self.pipeline = rag_pipeline

    async def build_eval_dataset(self, test_set: list[dict]) -> Dataset:
        rows = []
        for item in test_set:
            result = await self.pipeline.run(item["question"])
            rows.append({
                "question": item["question"],
                "answer": result["answer"],
                "contexts": [r["context"] for r in result["results"][:5]],
                "ground_truth": item["answer"],
            })
        return Dataset.from_list(rows)

    async def evaluate(self, test_set) -> dict:
        ds = await self.build_eval_dataset(test_set)
        report = evaluate(ds, metrics=[
            context_recall, context_precision,
            faithfulness, answer_relevancy,
        ])
        return dict(report)

# 运行并保存基线
# report = await evaluator.evaluate(test_set)
# → {"context_recall": 0.72, "context_precision": 0.68,
#    "faithfulness": 0.85, "answer_relevancy": 0.81}
```

**再加一个Ragas没有的硬指标**——拒答正确率（unanswerable集上）：

```python
def refusal_rate(self, results_on_unanswerable: list[str]) -> float:
    """边界集上正确说"不知道"的比例"""
    keywords = ["未找到", "无法在", "没有相关", "文档中未"]
    return sum(any(k in r for k in keywords) for r in results) / len(results)
```

---

## Step 4: 指标追踪表与优化循环（3小时）

```markdown
<!-- progress/optimization_log.md 模板 -->
| 日期 | 版本 | 改动 | CR | CP | Faith | AR | 拒答率 | 结论 |
|------|------|------|----|----|-------|----|----|------|
| D1 | v0 | 纯向量+400硬切(基线) | 62 | 65 | 82 | 80 | 10% | 基线 |
| D2 | v1 | +父子切分 | 71 | 66 | 84 | 81 | 12% | CR↑ |
| D3 | v2 | +BM25混合 | 79 | 70 | 84 | 81 | 15% | CR↑ |
| D4 | v3 | +reranker | 80 | 85 | 86 | 82 | 15% | CP↑↑ |
| D5 | v4 | +查询改写 | 86 | 85 | 86 | 83 | 18% | 多轮场景↑ |
| D6 | v5 | +拒答prompt | 86 | 85 | 91 | 84 | 55% | Faith↑ |
```

规则：
1. **每次只改一个变量**，跑全量测试集
2. 指标降了就回滚（git tag每个版本）
3. 目标线：**CR≥85%, CP≥80%, Faith≥90%, AR≥85%, 拒答率≥50%**

---

## Step 5: BadCase分析工作流（1小时）

```python
def dump_bad_cases(evaluator, test_set, metric="context_recall",
                   threshold=0.5) -> list[dict]:
    """导出最差的20个case，逐个归因"""
    # Ragas支持per-sample输出：evaluate(..., ) 后用 report.scores
    # 归因分类：
    #   CHUNK_ISSUE    - 原文被切断/表格损坏 → 回02/03修
    #   RETRIEVE_MISS  - 相关chunk存在但没召回 → 回04调检索
    #   RERANK_MISS    - 召回了但被排到top5外 → 回04调rerank
    #   GENERATE_ERR   - 检索对了但答案错 → 回prompt
    #   LABEL_ERR      - 测试集本身标错 → 修测试集
```

**每周固定动作**：导出top20 BadCase → 归因 → 修复一个类别的issue → 复测。这个循环就是Stage 2后半程（Week 10-12）的日常。

---

## ✅ 验收清单

- [ ] 200条测试集（含40条unanswerable），人工修订过
- [ ] Ragas四指标 + 自定义拒答率全部能跑
- [ ] 优化日志有≥5个版本的完整记录（v0基线→v5）
- [ ] 至少做过一轮BadCase归因分析
- [ ] 达标：CR≥85 / CP≥80 / Faith≥90 / AR≥85

**达标即Stage 2核心毕业**，剩下的就是把它组装成完整系统（07文档）。

---

## 面试话术（把这张表背熟）

> "我在自建的200条测试集（含20%不可回答负样本）上用Ragas做评估驱动迭代：基线是纯向量+固定切分，CR只有62%；通过父子文档切分、BM25+向量RRF融合、bge-reranker-v2-m3重排、多轮查询改写四步迭代，最终CR 86%、CP 85%、Faithfulness 91%，拒答准确率55%。每步只改一个变量，全程git版本化。"

---

**下一篇** → [07_project_rag_qa.md](./07_project_rag_qa.md)
