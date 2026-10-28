# 代码与场景设计题

> 周次：Week 5-6 ｜ 投入：20小时

---

## 目标

应对一面二面的手写代码和"场景怎么办"题。这类题不考算法竞赛，考**工程直觉**——恰恰是你12个月项目的主场。

---

## Part A: 高频代码题（手写级熟练）

### A1: 带超时+重试+降级的LLM调用器（近乎必考）

```python
# 15分钟内写出：面试官想看到的三要素
async def call_llm_safe(prompt, timeout=8, retries=3, fallback=None):
    for i in range(retries):
        try:
            return await asyncio.wait_for(llm(prompt), timeout)   # ①超时
        except asyncio.TimeoutError:
            continue
        except RateLimitError:
            await asyncio.sleep(2 ** i + random.random())         # ②退避+抖动
    return fallback if fallback else raise LastError              # ③降级
# 追问点: 为什么抖动？/ 哪些错误不该重试？(永久性错误)
```

### A2: RRF融合（你的项目原题）

```python
def rrf(lists, k=60):
    scores, seen = {}, {}
    for lst in lists:
        for rank, item in enumerate(lst, 1):
            scores[item.id] = scores.get(item.id, 0) + 1 / (k + rank)
    return sorted(seen.values(), key=..., reverse=True)
# 追问点: 为什么k=60？(经验值,平滑头部权重) 为什么不能直接加分数？(量纲不同)
```

### A3: 并发限制的批量嵌入

```python
async def batch_embed(texts, limit=5):
    sem = asyncio.Semaphore(limit)
    async def one(t):
        async with sem:
            return await embed(t)
    return await asyncio.gather(*[one(t) for t in texts])
# 追问: gather vs TaskGroup？(后者一处失败全取消)
```

### A4: 用Pydantic定义+校验LLM输出（04文档原样）

### A5: 简单LRU缓存（正经算法题，唯一一道传统题）

```python
from functools import lru_cache   # 先说标准库,再手写双向链表版
```

**练法**：每天手写2题×60分钟，一周后不看提示全对。

---

## Part B: 场景"怎么办"题（结构化作答）

答题模板：**现象诊断→根因假设(排序)→验证方法→解法→代价**。

### B1: "Agent上線后偶尔死循环/超时，怎么查？"

```
诊断: 先看trace确定卡在哪个节点(可观测性不是摆设)
假设: ①重试环上限失效 ②工具超时配置错 ③LLM输出触发路由震荡
验证: 按trace分布定位, 复现对应case
解法: 修复具体根因 + 加recursion_limit双保险 + 告警
代价: recursion_limit会截断极少数合法长流程(可接受)
```

### B2: "检索结果明明有正确文档，但答案错了"

```
分层定位: Rerank把它排出top5? → 生成prompt没强调引用? →
         上下文太长被截断? → 模型能力不足?
每层都有检测手段(评估集/trace里的score/上下文日志)
（= Stage 2-06排障决策树的现场版）
```

### B3: "老板要求答案100%准确"

```
不接: 概率组件没有100%
工程化: ①高风险领域加确定性校验(规则引擎复核LLM结论)
       ②拒答+人工兜底(错误预算思维)
       ③分级承诺: 高频问题集100%(测试集覆盖), 长尾95%+反馈通道
讲trade-off: 100%承诺=人工成本, 给老板算账
```

### B4: "Token费用突然翻倍"

```
定位: 成本按model/task维度拆(我项目里有metered记账)
常见根因: 上下文膨胀(新增节点塞太多) / 路由失效(简单题走了大模型)
        / 攻击性滥用(缺限流) / prompt缓存失效(前缀被改动)
解法对应: 瘦身/修路由/加频控/稳定前缀
```

### B5: "怎么防Prompt注入（检索内容里藏指令）"

```
分层防御:
① 输入面: 用户输入长度/格式限制
② 数据面: 检索内容视为不可信数据(分隔标记+指令"以下仅为参考资料")
③ 权限面: 工具白名单+写操作confirm+敏感工具不暴露给LLM自由调用
④ 输出面: 结构化输出约束+输出校验
承认: 无法100%防, 所以纵深防御+最小权限
```

---

## Part C: 基础概念快问快答（一面开场常考）

| 问题 | 30秒答案要点 |
|------|-------------|
| temperature是什么，你设多少？ | 采样随机性；事实问答0，改写0.3，创意0.7 |
| Function Calling原理？ | 把工具schema给模型，模型输出结构化调用意图，**执行永远在应用侧** |
| 向量检索的余弦相似度？ | 夹角衡量语义方向不衡量长度；先归一化再点积 |
| TTFT？ | 首token时间，流式下用户体感延迟的真相 |
| 上下文窗口大还需要RAG吗？ | 要：成本/延迟/权限/更新时效四原因（02文档题三） |
| sync和async的def在FastAPI区别？ | async跑事件循环(不能阻塞)，sync被丢线程池(阻塞无碍但慢) |

---

## ✅ 验收清单

- [ ] A1-A5不看材料手写通过
- [ ] B1-B5每个都能按五段模板脱口讲2分钟
- [ ] 快问快答30题全部30秒内答中要点
- [ ] 每道代码题的"追问点"都能接住

---

**下一篇** → [04_technical_articles.md](./04_technical_articles.md)
