# Asyncio异步编程深度指南

> 对应周次：Week 4-5 ｜ 预计投入：20小时 ｜ 前置：03_fastapi_framework.md

---

## 本文档目标

Asyncio是Java转Python**最大的思维转换点**，也是大模型应用（IO密集型）的性能生命线。本文档从模型对比讲到工程模式，学完能正确写出高并发异步代码，并知道每一步为什么。

---

## Step 1: 思维模型转换（2小时）

### 1.1 Java vs Python 并发模型对照

```
Java：
  Thread(线程) ── OS调度，真正并行，切换开销大
  CompletableFuture ── 基于线程池
  适用：CPU密集 + IO密集都行

Python（CPython）：
  Coroutine(协程) ── 单线程内协作式调度，遇到await主动让出
  Event Loop(事件循环) ── 唯一的"调度员"
  适用：IO密集（网络请求/数据库/LLM调用）✅
        CPU密集 ❌（GIL限制，要用ProcessPool）
```

### 1.2 核心类比：一个服务员的故事

- Event Loop = 一个服务员
- Coroutine = 一桌客人
- `await` = 客人说"菜等5分钟再上"→ 服务员立刻去服务别的桌
- **IO等待时间被复用**，而不是干等

大模型API调用平均3-10秒 = 极长的"等菜时间" → 异步收益最大化。

### 1.3 一条铁律

> **同步与异步混用是事故之源。** 在async函数里调用任何阻塞函数（requests、time.sleep、同步DB驱动），整个服务所有并发用户一起卡死。

| 场景 | ❌阻塞 | ✅异步 |
|------|-------|-------|
| HTTP请求 | requests | httpx.AsyncClient |
| 睡眠 | time.sleep | asyncio.sleep |
| PostgreSQL | psycopg2 | asyncpg |
| Redis | redis-py同步 | redis.asyncio |
| 文件IO | open() | asyncio.to_thread(open...) 或 aiofiles |

---

## Step 2: 核心原语逐个击破（4小时）

```python
import asyncio

# 2.1 协程函数与协程对象 —— 调用不等于执行！
async def fetch(url: str) -> str:
    await asyncio.sleep(1)        # 模拟IO
    return f"data from {url}"

coro = fetch("a")        # 此时什么都没发生（对标：创建了Future还没执行）
# coro必须被 await / asyncio.run / create_task 之一驱动才会跑

# 2.2 await：等待并让出控制权
async def main():
    result = await fetch("a")     # 等待期间事件循环可跑别的协程
    print(result)

asyncio.run(main())     # 创建事件循环并运行（程序唯一入口）

# 2.3 Task：并发调度的最小单位
async def main():
    task = asyncio.create_task(fetch("a"))   # 立刻被调度执行（后台跑）
    print("task已启动，不用等它")
    result = await task                      # 需要结果时再等
    print(result)

# 2.4 gather：并发执行N个协程并收集结果（最常用！）
async def main():
    # ❌ 串行写法：3秒
    # r1 = await fetch("a"); r2 = await fetch("b"); r3 = await fetch("c")

    # ✅ 并发写法：1秒（最慢的那个决定总时长）
    results = await asyncio.gather(
        fetch("a"), fetch("b"), fetch("c")
    )
    print(results)    # 顺序与传入顺序一致，与完成顺序无关

# 2.5 TaskGroup（3.11+，官方推荐的gather替代）：一处失败全部取消
async def main():
    async with asyncio.TaskGroup() as tg:
        t1 = tg.create_task(fetch("a"))
        t2 = tg.create_task(fetch("b"))
    print(t1.result(), t2.result())   # 离开with块时全部完成

# 2.6 as_completed：谁先完成先处理谁（流式场景）
async def main():
    tasks = [fetch(f"u{i}") for i in range(5)]
    for coro in asyncio.as_completed(tasks):
        print(await coro)      # 完成顺序打印
```

**练习**：用 `time.time()` 实测串行3个fetch vs gather 3个fetch的耗时对比，确认3秒 → 1秒。

---

## Step 3: 工程模式五件套（5小时）

这些模式在后面RAG/Agent项目里**每天都会写**。

### 3.1 超时控制

```python
async def fetch_with_timeout(url: str, timeout: float = 5.0):
    try:
        return await asyncio.wait_for(fetch(url), timeout=timeout)
    except asyncio.TimeoutError:
        return None        # 或返回降级结果/抛业务异常
```

### 3.2 重试 + 指数退避（调用LLM的标配）

```python
import random

async def retry_async(coro_factory, max_retries: int = 3, base: float = 1.0):
    """coro_factory: 每次重试需要新建协程，所以传工厂函数而不是协程对象"""
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = base * (2 ** attempt) + random.random()   # 1s,2s,4s + 抖动
            print(f"attempt {attempt + 1} failed ({e}), retry in {wait:.1f}s")
            await asyncio.sleep(wait)

# 用法：注意是lambda/函数，不是直接传协程
result = await retry_async(lambda: call_llm(prompt), max_retries=3)
```

### 3.3 Semaphore并发限流（防止打爆下游API）

```python
sem = asyncio.Semaphore(5)       # 任意时刻最多5个在飞

async def bounded_fetch(url: str):
    async with sem:              # 抢不到槽位就排队等
        return await fetch(url)

async def main():
    urls = [f"u{i}" for i in range(100)]
    # 100个任务排队，但同时在跑的永远≤5
    results = await asyncio.gather(*[bounded_fetch(u) for u in urls])
```

### 3.4 生产者-消费者（异步队列，对标BlockingQueue）

```python
async def producer(q: asyncio.Queue):
    for i in range(10):
        await q.put(f"task_{i}")
    await q.put(None)            # 毒丸，通知消费者退出

async def consumer(q: asyncio.Queue, worker_id: int):
    while True:
        item = await q.get()
        if item is None:
            await q.put(None)    # 传递毒丸给下一个消费者
            break
        await asyncio.sleep(0.5) # 处理任务
        print(f"worker{worker_id} done {item}")

async def main():
    q = asyncio.Queue(maxsize=3)
    await asyncio.gather(producer(q), consumer(q, 1), consumer(q, 2))
```

### 3.5 优雅取消（Agent工作流中断的基础）

```python
async def long_task():
    try:
        await asyncio.sleep(100)
    except asyncio.CancelledError:
        print("被取消，清理现场")
        raise                    # 取消异常必须继续抛出

async def main():
    task = asyncio.create_task(long_task())
    await asyncio.sleep(1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("task已终止")
```

---

## Step 4: 异步生成器与流式思维（3小时）

大模型逐token输出 = 异步生成器，**这是流式输出的底层机制**。

```python
# async generator: 用yield产出，用await等待
async def token_stream(n: int):
    for i in range(n):
        await asyncio.sleep(0.1)      # 模拟LLM生成延迟
        yield f"token_{i}"

# 消费方式1：async for
async def main():
    async for token in token_stream(5):
        print(token, end=" ")

# 消费方式2：手动next（FastAPI的SSE底层就是这么写的）
async def main():
    gen = token_stream(5)
    while True:
        try:
            token = await gen.__anext__()
            print(token)
        except StopAsyncIteration:
            break

# 实战形态：包装LLM流式响应
async def llm_stream(prompt: str):
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", API_URL, json={"prompt": prompt}) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    yield line[6:]     # 剥掉SSE前缀
```

---

## Step 5: 并发性能实验（3小时）

**自己动手做这个实验，胜过读十篇教程**：

```python
# benchmark.py
import asyncio, time, httpx

async def fetch_one(client: httpx.AsyncClient, i: int):
    resp = await client.get(f"https://httpbin.org/delay/1?id={i}")  # 每个请求服务端延迟1秒
    return resp.status_code

async def run(limit: int | None, total: int = 20):
    sem = asyncio.Semaphore(limit) if limit else None

    async def bounded(i: int):
        if sem:
            async with sem:
                return await fetch_one(client, i)
        return await fetch_one(client, i)

    async with httpx.AsyncClient() as client:
        start = time.time()
        results = await asyncio.gather(*[bounded(i) for i in range(total)])
        print(f"limit={limit}: {time.time()-start:.1f}s, ok={sum(r==200 for r in results)}")

if __name__ == "__main__":
    asyncio.run(run(None))     # 不限流
    asyncio.run(run(5))        # 限流5
```

**观察并记录**：不限流的总耗时 vs 限流5的总耗时；httpbin可能限速，观察错误率。把结论写进学习日志。

---

## Step 6: 排错指南（1小时）

| 报错/症状 | 含义 | 处理 |
|----------|------|------|
| `RuntimeError: coroutine was never awaited` | 创建了协程但没驱动 | 检查是否漏了await/create_task |
| `RuntimeError: asyncio.run() cannot be called from a running event loop` | 在异步环境里又调asyncio.run | Jupyter里用`await main()`；嵌套循环用nest_asyncio或重构 |
| 接口并发量一上来全部超时 | async函数里混了阻塞调用 | 全链路替换为异步库 |
| gather中一个失败全崩 | 默认fail-fast | 需要容错时用 `return_exceptions=True` 逐个检查 |
| CPU计算没变快 | GIL | `await asyncio.to_thread(cpu_func)` 或ProcessPoolExecutor |

---

## ✅ 本文档验收清单

- [ ] 能画出Event Loop + Coroutine + await的执行时序（口头讲给同事听）
- [ ] 知道为什么重试要传协程工厂而不是协程对象
- [ ] Semaphore限流实验跑通并记录数据
- [ ] 能写异步生成器并用async for消费
- [ ] 100并发压测下（Step 5实验放大到100）服务不卡死
- [ ] 能一眼识别"async函数里的阻塞调用"

---

**下一篇** → [05_streaming_and_websocket.md](./05_streaming_and_websocket.md)
