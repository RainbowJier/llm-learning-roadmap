# 检验项目：高并发聊天服务

> 对应周次：Week 8（项目周） ｜ 投入：40小时 ｜ 前置：全部前序文档

---

## 项目概述

把第一阶段学到的一切组装成一个真实可跑的服务：**模拟LLM后端的高并发聊天服务**，含SSE流式、WebSocket、并发限制、重试降级、监控中间件。

```
                 ┌────────────────────────────┐
   HTTP POST ──► │ /chat           普通问答    │
   SSE      ──► │ /chat/stream    流式回答    │    ┌──────────────┐
   WS       ──► │ /ws/chat/{uid}  双向聊天    ├───►│ 模拟LLM后端   │
                 │ /admin/stats    运行指标    │    │ (可换真API)   │
                 └────────────────────────────┘    └──────────────┘
```

---

## Day 1-2: 骨架与数据模型（8小时）

**目标**：项目结构立起来，`/chat` 普通接口可用。

```
chat_service/
├── app/
│   ├── __init__.py
│   ├── main.py               # 入口 + lifespan
│   ├── config.py             # pydantic-settings读.env
│   ├── models.py             # 所有Pydantic模型
│   ├── llm/
│   │   ├── backend.py        # 模拟LLM（可切换真API）
│   │   └── client.py         # 真实API封装（含重试）
│   ├── routers/
│   │   ├── chat.py           # /chat + /chat/stream
│   │   ├── ws.py             # WebSocket
│   │   └── admin.py          # /admin/stats
│   └── middleware/
│       └── metrics.py        # 计时 + 统计
├── tests/
│   ├── test_chat.py
│   ├── test_stream.py
│   └── test_ws.py
├── .env.example
├── requirements.txt
└── Dockerfile
```

关键代码——配置与模拟后端：

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    llm_backend: str = "mock"            # mock | openai | anthropic
    max_concurrent: int = 20             # 并发上限
    llm_timeout: float = 8.0
    class Config: env_file = ".env"

settings = Settings()

# app/llm/backend.py
import asyncio, random

async def mock_llm_stream(prompt: str):
    """模拟逐token输出，随机延迟，偶尔失败"""
    tokens = f"关于「{prompt}」的回答：".split() + ["这是", "模拟", "内容", "。"]
    for t in tokens:
        await asyncio.sleep(random.uniform(0.05, 0.2))
        if random.random() < 0.02:
            raise RuntimeError("模拟LLM抖动")
        yield t
```

**Day 2结束验收**：`POST /chat` 返回JSON答案；pytest通过。

---

## Day 3: 流式与降级（8小时）

实现 `POST /chat/stream`：
1. 调用 `mock_llm_stream`，包装成SSE结构化事件（status/token/done）
2. **失败重试**：流中断时自动重试一次（重试期间发status事件告知用户）
3. **最终降级**：重试仍失败 → 返回缓存/兜底文案，**必须发error+done帧**

```python
# routers/chat.py 核心逻辑骨架
async def stream_with_retry(query: str):
    for attempt in range(2):
        collected = []
        try:
            async for token in mock_llm_stream(query):
                collected.append(token)
                yield sse({"type": "token", "content": token})
            yield sse({"type": "done", "attempt": attempt})
            return
        except Exception as e:
            yield sse({"type": "status", "msg": f"重试中({attempt+1})..."})
    yield sse({"type": "error", "msg": "服务繁忙，请稍后再试"})
    yield sse({"type": "done", "fallback": True})
```

**验收**：把mock失败率调到30%，脚本测试100次，客户端**永远**能收到done帧。

---

## Day 4: WebSocket与连接管理（8小时）

实现 `WS /ws/chat/{user_id}`：
- [ ] ConnectionManager多用户隔离
- [ ] 收到消息后异步生成回答（逐token推回）
- [ ] 用户断开时取消进行中的生成任务（`asyncio.Task.cancel()`）
- [ ] 心跳后台任务清理僵尸连接

**验收**：两个浏览器标签页同时连接互不干扰；关闭标签页后服务器日志显示任务被取消。

---

## Day 5: 并发限制与监控（8小时）

```python
# middleware/metrics.py
import time, collections

class Metrics:
    def __init__(self):
        self.latencies: deque = collections.deque(maxlen=1000)
        self.counters: dict[str, int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)

metrics = Metrics()

@app.middleware("http")
async def track(request, call_next):
    start = time.time()
    response = await call_next(request)
    metrics.latencies.append(time.time() - start)
    metrics.counters[request.url.path] += 1
    return response

# /admin/stats 输出
def percentile(data, p):
    if not data: return 0
    s = sorted(data); k = int(len(s) * p / 100)
    return s[min(k, len(s)-1)]

# 返回 {"p50_ms":..., "p95_ms":..., "p99_ms":..., "qps":..., "errors":...}
```

并发限制：全局 `asyncio.Semaphore(settings.max_concurrent)` 包住LLM调用；超限请求排队或返回429。

**验收**：`/admin/stats` 能实时看到p95延迟、请求数、错误分布。

---

## Day 6: 压测调优（8小时）

```bash
# 100并发SSE流压测（复用05文档脚本，放大到100）
# 记录: 总耗时 / p95 / 错误数 / 限流生效情况
```

调优检查清单：
- [ ] 并发100时无请求卡死（有Semaphore兜底）
- [ ] p95 < 2秒（mock延迟已固定的情况下）
- [ ] 错误率 < 2%，且全部有降级响应
- [ ] 内存稳定（无协程泄漏：断开后任务都被取消）

---

## Day 7: Docker化与文档（8小时）

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY tests/ tests/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t chat-service .
docker run -p 8000:8000 chat-service
# 容器内跑一次冒烟: curl -N -X POST localhost:8000/chat/stream -H "Content-Type: application/json" -d '{"query":"hi"}'
```

README必须包含：架构图（ASCII）、启动方式、压测数据表、已知限制。

---

## 最终验收清单（全部通过才算Stage 1毕业）

**功能**
- [ ] `/chat`、`/chat/stream`(SSE)、`/ws/chat/{uid}`(WS)、`/admin/stats` 四组接口
- [ ] 结构化SSE事件 + 失败重试 + 降级兜底
- [ ] WS断开清理 + 心跳

**性能**
- [ ] 100并发流式压测通过，无卡死、无泄漏
- [ ] p95 < 2s（mock后端）
- [ ] Semaphore限流生效（429或排队）

**质量**
- [ ] pytest覆盖率 ≥ 80%
- [ ] mypy无error（`mypy app/`）
- [ ] Docker构建运行成功

**文档**
- [ ] README含压测数据表
- [ ] 提交git，写清楚commit

---

## 完成后

```bash
git add . && git commit -m "stage 1: high-concurrency chat service with SSE/WS"
```

然后写一篇学习总结（500字即可）：**Java转Python最不适应的三个点 / asyncio最大的坑 / 下一阶段想巩固什么**，存到 `progress/`。

**下一阶段** → `../stage_02_rag_engineering/01_rag_overview.md`
