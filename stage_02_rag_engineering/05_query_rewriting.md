# 查询改写与多轮对话

> 对应周次：Week 8 ｜ 投入：10小时 ｜ 前置：04_hybrid_retrieval.md

---

## 本文档目标

解决多轮对话里"检索不到东西"的头号元凶：**指代不明和口语化**。实现查询改写器（Condense Question），并加上两个查询侧增强：HyDE和多重查询。

---

## Step 1: 问题定义（1小时）

三种必须改写的query形态：

| 用户输入 | 问题类型 | 改写后 |
|---------|---------|--------|
| "那去年的能攒到今年吗" | 指代缺失（"那"=年假） | 公司去年年假能否累计到今年休 |
| "咋报销啊" | 口语+缺宾语 | 员工差旅费用报销的流程和标准是什么 |
| "它跟A802比呢" | 指代+省略比较项 | A801-Pro与A802-Pro在参数上的区别 |

**判断标准**：改写器输出的问题必须**脱离对话历史也能被独立理解**（self-contained）。

---

## Step 2: 实现Condense改写器（3小时）

```python
import json
from pydantic import BaseModel

class RewrittenQuery(BaseModel):
    rewritten: str = Field(description="改写后的完整问题")

REWRITE_PROMPT = """基于以下对话历史，把用户的最新问题改写成一个不依赖上下文也能理解的完整问题。

规则：
1. 保留用户原意，不要回答问题
2. 把"它/那/这个"等指代替换成具体对象
3. 补全省略的主语和宾语
4. 如果最新问题本身已经完整，原样返回

对话历史：
{history}

最新问题：{question}

只输出改写后的问题，不要任何解释。"""


class QueryRewriter:
    def __init__(self, llm):     # llm: 任意支持chat的客户端封装
        self.llm = llm

    async def rewrite(self, question: str,
                      history: list[dict[str, str]]) -> str:
        if not history:          # 首轮无需改写，省一次LLM调用
            return question
        hist_text = "\n".join(
            f"{'用户' if m['role']=='user' else '助手'}: {m['content']}"
            for m in history[-4:])          # 只带最近2轮，控token
        resp = await self.llm.chat(
            REWRITE_PROMPT.format(history=hist_text, question=question))
        return resp.strip().strip('"')
```

**用小模型**（Haiku级）跑改写：延迟低、成本低，这活不需要聪明模型。

**验收测试**（写进单测，LLM可用mock）：

```python
history = [{"role": "user", "content": "公司年假怎么休"},
           {"role": "assistant", "content": "试用期5天，转正后10天..."}]
rewritten = await rewriter.rewrite("那去年的能攒到今年吗", history)
assert "年假" in rewritten          # 指代已消解
assert "那" not in rewritten         # 无残留指代词
```

---

## Step 3: 进阶增强一：HyDE（2小时）

**假设文档嵌入**：query和doc的"语言风格"差异大时（用户口语 vs 制度文本），先让LLM**假想一个答案**，用假答案的向量去检索（答案和文档在向量空间更近）。

```python
HYPE_PROMPT = """请写一段50字左右的假设性回答来回应这个问题（不需要真实数据，
风格模仿公司制度文档的措辞）：{question}"""

async def hyde_retrieve(self, question: str):
    fake_answer = await self.llm.chat(HYPE_PROMPT.format(question=question))
    return self.vec.search(fake_answer, top_k=50)   # 用假答案检索
```

**适用判断**：短query、术语少、语料是正式文体时HyDE有用；query已经很具体时反而添乱。**用你的语料实验后决定是否保留**（又一个消融点）。

---

## Step 4: 进阶增强二：多重查询（2小时）

一个query拆成3个不同角度，各检索一路，合并去重：

```python
MULTI_PROMPT = """把这个问题改写成3个不同角度的检索查询（每行一个，不要编号）：
{question}"""

async def multi_query_retrieve(self, question: str):
    variants = (await self.llm.chat(
        MULTI_PROMPT.format(question=question))).splitlines()
    all_hits = await asyncio.gather(          # 三路并发！Stage 1的功夫
        *[self._single_retrieve(v) for v in variants + [question]])
    return rrf_fuse(*all_hits)                # 复用04文档的RRF
```

代价：检索成本×4、延迟略增；收益：召回更稳。**同样用消融实验决定去留**。

---

## Step 5: 组装查询侧Pipeline（2小时）

```python
class QueryPipeline:
    """完整的查询侧处理：改写 → (可选增强) → 混合检索"""
    def __init__(self, rewriter, retriever):
        self.rewriter, self.retriever = rewriter, retriever

    async def run(self, question: str, history: list | None):
        # 1. 改写（首轮跳过）
        rewritten = await self.rewriter.rewrite(question, history or [])
        # 2. 检索（用改写后的query）
        results = await self.retriever.retrieve(rewritten, top_k=5)
        return {"rewritten": rewritten, "results": results}
```

**对比实验**（记录进日志）：取10个多轮对话型问题（必须带指代），对比"直接检索 vs 改写后检索"的top5命中率。预期改写后显著提升。

---

## ✅ 验收清单

- [ ] 指代消解测试通过（"那/它/这个"全部替换）
- [ ] 首轮问题跳过LLM（省成本逻辑）
- [ ] HyDE和多重查询各做过一次消融，去留有数据支撑
- [ ] 多轮对话场景命中率提升有量化记录

---

## 常见坑

| 坑 | 现象 | 解法 |
|----|------|------|
| 改写器自作主张回答了问题 | prompt里没强调"不要回答" | 加规则+few-shot示例 |
| 改写引入幻觉对象 | 历史太长，模型串台 | 只带最近2轮；改写后校验关键词是否在历史中出现过 |
| 多重查询延迟翻倍 | 串行执行 | asyncio.gather并发 |
| 改写后检索反而变差 | 过度改写偏离原意 | 保留原query一起参与融合（RRF天然支持） |

---

**下一篇** → [06_evaluation_framework.md](./06_evaluation_framework.md)
