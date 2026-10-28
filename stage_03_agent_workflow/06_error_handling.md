# 错误处理与降级

> 对应周次：Week 9 ｜ 投入：12小时 ｜ 前置：05_tool_calling.md

---

## 本文档目标

建立Agent的完整容错体系：错误分类 → 逐层防线（重试/超时/熔断/降级）→ 用户永远拿到合理响应。**目标：任何单点故障都不会让用户看到500**。

---

## Step 1: 错误分类学（2小时）

处理错误前先分类，**不同错误不同药方**：

| 类别 | 例子 | 正确处理 | 错误处理 |
|------|------|---------|---------|
| **瞬态错误** | 网络抖动、429限流、500偶发 | 指数退避重试 | 直接降级（浪费） |
| **持久错误** | API Key失效、schema不兼容 | 快速失败+告警 | 无脑重试（烧钱） |
| **超时** | LLM/工具响应慢 | 超时→降级路径 | 干等（拖垮全链路） |
| **业务错误** | 订单不存在、无权限 | 把错误信息给LLM让它解释 | 当系统错误处理 |
| **数据错误** | LLM输出不合法 | 结构化回炉（04文档） | 直接抛给用户 |

```python
class ErrorKind(str, Enum):
    TRANSIENT = "transient"     # 重试
    PERSISTENT = "persistent"   # 降级+告警
    TIMEOUT = "timeout"         # 降级
    BUSINESS = "business"       # 交给LLM解释
    PARSE = "parse"             # 结构化回炉

def classify_error(e: Exception) -> ErrorKind:
    if isinstance(e, (RateLimitError,)): return ErrorKind.TRANSIENT
    if isinstance(e, asyncio.TimeoutError): return ErrorKind.TIMEOUT
    if isinstance(e, AuthError): return ErrorKind.PERSISTENT
    if isinstance(e, NotFoundError): return ErrorKind.BUSINESS
    ...
```

---

## Step 2: 重试策略进阶（3小时）

Stage 1学过基础重试，生产版要加三个东西：

```python
import random
from collections.abc import Awaitable, Callable

async def smart_retry(
    fn: Callable[[], Awaitable],
    max_retries: int = 3,
    base_delay: float = 1.0,
    retry_on: set[ErrorKind] = {ErrorKind.TRANSIENT},
    on_give_up: Callable | None = None,
):
    """带错误分类的重试：只重试该重试的，其余立刻走on_give_up"""
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            kind = classify_error(e)
            if kind not in retry_on or attempt == max_retries:
                if on_give_up:
                    return await on_give_up(e)     # 降级回调
                raise
            delay = base_delay * (2 ** attempt) + random.random()  # 抖动防雪崩
            await asyncio.sleep(delay)
```

**抖动(jitter)的作用**：100个请求同时429 → 退避1s后同时重试 → 再429。加随机抖动把重试时间打散。

---

## Step 3: 熔断器（2小时）

下游持续故障时，与其每次都等8秒超时，不如**先停止调用，歇一会再试探**：

```python
import time

class CircuitBreaker:
    """三态: CLOSED(正常) → OPEN(熔断) → HALF_OPEN(试探)"""
    def __init__(self, failure_threshold=5, reset_timeout=30):
        self.failures = 0
        self.threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.opened_at: float | None = None
        self.state = "closed"

    def allow(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.opened_at > self.reset_timeout:
                self.state = "half_open"           # 冷静期过了，试探
                return True
            return False                            # 熔断中，快速失败
        return True                                 # half_open放行一次

    def record(self, success: bool):
        if success:
            self.failures, self.state = 0, "closed"
        else:
            self.failures += 1
            if self.failures >= self.threshold:
                self.state, self.opened_at = "open", time.time()

# 用法：包在工具执行外层
breaker = CircuitBreaker()

async def call_with_breaker(fn, fallback):
    if not breaker.allow():
        return await fallback("circuit_open")       # 不等超时，秒级降级
    try:
        result = await fn()
        breaker.record(True)
        return result
    except Exception as e:
        breaker.record(False)
        return await fallback(str(e))
```

**面试一句话**：*"熔断把'每次都等超时'变成'快速失败直接降级'，保护用户延迟体验和下游恢复。"*

---

## Step 4: 降级阶梯设计（3小时）

**降级不是一种，是阶梯**——按质量递减排好，逐级尝试：

```python
class DegradeLadder:
    """售后Agent的降级阶梯示例"""

    async def level_0_full(self, query):        # 完整：改写+检索+生成+校验
        return await full_pipeline(query)

    async def level_1_no_rewrite(self, query):  # 砍改写（省1次LLM调用）
        return await full_pipeline(query, skip_rewrite=True)

    async def level_2_template(self, query):    # 检索top1+模板填空（0次生成调用）
        top = await retriever.retrieve(query, top_k=1)
        return f"相关制度参考：\n{top[0]['context'][:500]}\n（AI生成暂不可用）"

    async def level_3_faq(self, query):         # FAQ精确匹配
        return await faq_lookup(query)

    async def level_4_human(self, query):       # 转人工
        ticket = await create_ticket(query)
        return f"已为您转人工，工单号 {ticket}。"

    async def handle(self, query):
        for level in (self.level_0_full, self.level_1_no_rewrite,
                      self.level_2_template, self.level_3_faq):
            try:
                return await with_timeout(level(query), timeout=6)
            except Exception:
                continue                          # 滑到下一级
        return await self.level_4_human(query)    # 兜底永远是人工
```

**设计原则**：
1. 每级**延迟预算递减**（6s→4s→2s→0.5s）
2. 最底层（转人工/致歉+工单）**永不失败**
3. 降级发生必须打日志+计数（Stage 4监控告警的信号源）

---

## Step 5: 全链路错误预算表（2小时）

把所有防线落成一张表，写进设计文档（07项目必交）：

| 故障点 | 检测 | 第一响应 | 第二响应 | 用户所见 | 最大耗时 |
|--------|------|---------|---------|---------|---------|
| LLM超时 | wait_for 8s | smart_retry×2 | 降级L2模板 | 模板答案 | ~20s |
| LLM限流 | 429 | 退避重试 | 换备用模型 | 正常答案 | ~5s |
| 检索服务挂 | 熔断器open | 跳过检索 | FAQ/人工 | 转人工 | ~1s |
| 工具API挂 | 工具级熔断 | 结构化错误喂LLM | LLM解释+人工 | 带说明的回复 | ~8s |
| 结构化解析失败 | Pydantic异常 | 节点内回炉×2 | 图级fallback | 标准致歉 | ~15s |
| 上游全挂 | 降级阶梯走完 | —— | level_4人工 | 工单号 | <1s |

**练习**：对你的售后工单Agent，逐项注入故障（mock抛异常/超时），验证每行的实际行为与表格一致。这份"混沌实验记录"是简历上"设计并验证了完整容错体系"的证据。

---

## ✅ 验收清单

- [ ] 错误分类函数覆盖五大类
- [ ] smart_retry带jitter和降级回调
- [ ] 熔断器实现并有单测（closed→open→half_open全转换）
- [ ] 降级阶梯≥4级且最底层永不失败
- [ ] 错误预算表完成混沌实验验证

---

**下一篇** → [07_project_service_agent.md](./07_project_service_agent.md)
