# 可观测性三支柱

> 投入：12小时 ｜ 前置：Stage 3项目完成

---

## 本文档目标

给Agent装"黑匣子"：结构化日志、分布式追踪、指标导出。**生产系统的第一原则：出了问题必须能在10分钟内定位是哪个环节**。

---

## Step 1: 可观测性三支柱在大模型场景的映射（1小时）

```
日志(Logs)    → 一次请求内每步发生了什么（细节）
追踪(Traces)  → 一次请求经过哪些节点、各耗多久（结构）
指标(Metrics) → 聚合视图：QPS/P95/错误率/Token/成本（趋势+告警）
```

大模型应用特有的第四维：**Token与成本**——每次LLM调用的input/output token都要记，它是"每请求成本"的数据源。

---

## Step 2: 结构化日志（3小时）

**铁律：日志写JSON，不写人看的散文**（机器可检索、可聚合）：

```python
# pip install structlog
import structlog, time, uuid

logger = structlog.get_logger()

# 中间件：注入request_id，所有日志自动携带（跨行关联一次请求）
@app.middleware("http")
async def request_context(request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    structlog.contextvars.bind_contextvars(request_id=request_id)
    start = time.time()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info("request_done", path=request.url.path,
                status=response.status_code,
                latency_ms=round((time.time() - start) * 1000))
    return response
```

节点级日志标准（每个LangGraph节点开头/结尾）：

```python
async def retrieve_node(state):
    log = logger.bind(node="retrieve", query=state["rewritten"][:50])
    start = time.time()
    results = await retriever.retrieve(state["rewritten"])
    log.info("node_done",
             duration_ms=round((time.time()-start)*1000),
             hits=len(results),
             top_score=results[0]["rerank_score"] if results else None)
    return {"context": results}
```

**字段规范**（全项目统一，违反就是埋雷）：

| 字段 | 说明 | 例 |
|------|------|----|
| request_id | 一次用户请求 | a3f8c2 |
| node | 节点名 | retrieve |
| duration_ms | 耗时 | 412 |
| llm_model / tokens_in / tokens_out | LLM调用 | sonnet / 850 / 210 |
| degraded / retry_count | 容错信号 | true / 2 |
| level | info/warn/error | 降级必须warn以上 |

---

## Step 3: 分布式追踪（4小时）

### 3.1 方案A：LangSmith（LangChain系首选）

```bash
pip install langsmith
# .env: LANGSMITH_TRACING=true LANGSMITH_API_KEY=... LANGSMITH_PROJECT=agent-v1
```

```python
# LangGraph自动被追踪：每个节点一个span
# 自定义工具/额外span：
from langsmith.run_helpers import traceable

@traceable(name="hybrid_retrieve")
async def retrieve(query: str):
    ...     # LangSmith上出现嵌套span，含输入输出和耗时
```

LangSmith面板能看到：每次请求的完整节点树、每步的输入输出原文、Token统计、延迟瀑布图。**免费额度够个人项目用**。

### 3.2 方案B：OpenTelemetry（无厂商锁定，更通用）

```python
# pip install opentelemetry-sdk opentelemetry-instrumentation-fastapi \
#            opentelemetry-exporter-otlp
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

tracer = trace.get_tracer("agent")

FastAPIInstrumentor.instrument_app(app)

async def generate_node(state):
    with tracer.start_as_current_span("generate") as span:
        span.set_attribute("gen.model", "sonnet")
        span.set_attribute("gen.tokens_out", 210)
        ...   # span自动计时，异常自动记录
```

**实践决策**：个人项目/求职演示 → LangSmith（10分钟接入，界面漂亮）；企业生产 → OTel（标准、可接任意后端如Jaeger/Tempo）。

---

## Step 4: 指标导出（3小时）

```python
# pip install prometheus-fastapi-instrumentator
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)   # /metrics端点就绪
```

业务自定义指标（大模型应用必备的五个）：

```python
from prometheus_client import Counter, Histogram, Gauge

REQUESTS = Counter("agent_requests_total", "总请求", ["intent", "status"])
LLM_TOKENS = Counter("agent_llm_tokens_total", "Token消耗",
                     ["model", "direction"])        # in/out分开记
LATENCY = Histogram("agent_latency_seconds", "端到端延迟",
                    buckets=[0.5, 1, 2, 3, 5, 10])
DEGRADES = Counter("agent_degrades_total", "降级次数", ["level"])
ACTIVE = Gauge("agent_active_requests", "进行中请求")

# 在API层和节点里埋点
REQUESTS.labels(intent=result["intent"], status="ok").inc()
LLM_TOKENS.labels(model="sonnet", direction="output").inc(210)
LATENCY.observe(elapsed)
```

---

## Step 5: 一次故障排查演练（1小时）

**验证可观测性是否合格的唯一标准**：模拟一次"用户说回答不对"，看你多快定位：

1. 用户反馈 + 时间点 → 按request_id过滤日志
2. 找到该请求trace → 看到retrieve节点hits=0
3. 看retrieve输入 → 发现改写节点把问题改歪了
4. 结论：改写prompt的某规则有问题 → 修复

**把这个演练过程截图存档**——面试讲"我的可观测性设计"时，这个故事比任何架构图都有说服力。

---

## ✅ 验收清单

- [ ] 全日志JSON结构化且带request_id
- [ ] LangSmith或OTel追踪覆盖所有节点（截图存档）
- [ ] 五大自定义指标可在/metrics看到
- [ ] 故障排查演练<10分钟定位根因（有记录）

---

**下一篇** → [02_monitoring_setup.md](./02_monitoring_setup.md)
