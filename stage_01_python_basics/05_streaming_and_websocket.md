# 流式输出与WebSocket实时通信

> 对应周次：Week 6-7 ｜ 预计投入：15小时 ｜ 前置：04_asyncio_deep_dive.md

---

## 本文档目标

实现大模型应用的两大实时通信能力：SSE流式输出（打字机效果）和WebSocket双向通信。学完后能在浏览器里看到token逐个蹦出来。

---

## Step 1: 理解SSE协议（1小时）

Server-Sent Events：**服务器 → 客户端的单向长连接流**。

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream

data: 你好

data: ，世界

data: [DONE]
```

协议要点：
- 每条消息以 `data: ` 开头，**空行分隔**
- 客户端用 `EventSource`（自动重连）
- 只能服务器单向推 → 对聊天场景刚刚好，比WebSocket轻量得多

**选型结论**：聊天回答流式 → SSE；实时协作/双向指令 → WebSocket。生产中大模型聊天90%用SSE。

---

## Step 2: FastAPI实现SSE（4小时）

### 2.1 基础版本

```python
# app/streaming.py
import asyncio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI()

class ChatRequest(BaseModel):
    query: str

async def fake_llm_stream(query: str):
    """模拟LLM逐token生成"""
    for token in ["年假", "规则", "如下", "：", "试用期", "5天", "。"]:
        await asyncio.sleep(0.15)
        yield f"data: {token}\n\n"          # SSE格式：data: + 内容 + 空行

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    return StreamingResponse(
        fake_llm_stream(req.query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",     # 禁止代理缓冲
            "X-Accel-Buffering": "no",       # nginx专用：关缓冲（部署必加）
        },
    )
```

### 2.2 结构化事件（实战版本：区分token/进度/完成）

```python
import json

async def chat_events(query: str):
    # 事件1：进度提示
    yield f"data: {json.dumps({'type': 'status', 'msg': '正在检索文档...'})}\n\n"
    await asyncio.sleep(0.3)
    docs = ["doc1.md", "doc2.md"]

    yield f"data: {json.dumps({'type': 'status', 'msg': '正在生成答案'})}\n\n"
    for token in ["检索到", "2篇", "相关", "文档"]:
        await asyncio.sleep(0.1)
        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    # 事件3：结束帧（携带元数据）
    yield f"data: {json.dumps({'type': 'done', 'sources': docs, 'latency_ms': 450})}\n\n"

@app.post("/chat/stream2")
async def chat_stream2(req: ChatRequest):
    return StreamingResponse(chat_events(req.query), media_type="text/event-stream")
```

### 2.3 客户端（HTML一行都不用框架）

```html
<!-- static/chat.html -->
<script>
async function chat(query) {
    const resp = await fetch("/chat/stream2", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query}),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        buf += decoder.decode(value, {stream: true});
        // SSE消息以空行分隔
        const parts = buf.split("\n\n");
        buf = parts.pop();
        for (const p of parts) {
            if (!p.startsWith("data: ")) continue;
            const evt = JSON.parse(p.slice(6));
            if (evt.type === "token") document.body.innerText += evt.content;
            if (evt.type === "done") console.log("sources:", evt.sources);
        }
    }
}
</script>
```

### 2.4 流中途出错怎么办（生产关键）

```python
async def safe_stream(query: str):
    try:
        async for evt in chat_events(query):
            yield evt
    except Exception as e:
        # 不能返回HTTP错误码了（头已发出），只能发错误事件
        yield f"data: {json.dumps({'type': 'error', 'msg': str(e)})}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"   # 依然发done让客户端收尾
```

**练习**：把流式接口接到真实LLM（OpenAI/Claude/国产API任一，用其stream参数），浏览器看到打字机效果。

---

## Step 3: WebSocket双向通信（4小时）

### 3.1 基础连接

```python
# app/ws.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()                    # 完成握手
    try:
        while True:
            data = await ws.receive_text()      # 收（阻塞式等待）
            await ws.send_text(f"echo: {data}") # 发
    except WebSocketDisconnect:
        print("客户端断开")
```

```html
<script>
const ws = new WebSocket("ws://127.0.0.1:8000/ws");
ws.onopen = () => ws.send("hello");
ws.onmessage = (e) => console.log(e.data);
ws.onclose = () => console.log("closed");
</script>
```

### 3.2 连接管理器（多用户广播，实战必备）

```python
from collections import defaultdict

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}       # user_id -> ws

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)

    async def send_to(self, user_id: str, message: str):
        ws = self.active.get(user_id)
        if ws:
            await ws.send_text(message)

    async def broadcast(self, message: str):
        for ws in list(self.active.values()):
            await ws.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/chat/{user_id}")
async def chat_ws(ws: WebSocket, user_id: str):
    await manager.connect(user_id, ws)
    try:
        while True:
            query = await ws.receive_text()
            # 逐token推给这个用户
            for token in ["回答", "的", "内容"]:
                await asyncio.sleep(0.1)
                await manager.send_to(user_id, token)
    except WebSocketDisconnect:
        manager.disconnect(user_id)
```

### 3.3 心跳与僵尸连接

```python
async def heartbeat(manager: ConnectionManager, interval: int = 30):
    """后台任务：定期ping，清理死连接（部署时必须有）"""
    while True:
        await asyncio.sleep(interval)
        for uid, ws in list(manager.active.items()):
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                manager.disconnect(uid)
```

---

## Step 4: SSE vs WebSocket 决策表（1小时）

| 维度 | SSE | WebSocket |
|------|-----|-----------|
| 方向 | 单向（服务器→客户端） | 双向 |
| 协议 | 纯HTTP | 升级协议（ws://） |
| 自动重连 | 浏览器内置 | 需自己实现 |
| 代理/CDN友好 | ✅（注意关缓冲） | 常需额外配置 |
| 适用 | 聊天回答流、进度、日志 | 协同编辑、游戏、语音 |

**大模型聊天默认选SSE**，除非客户端也需要高频上行。

---

## Step 5: 并发验证（2小时）

```bash
# 安装压测工具
pip install aiohttp

# 并发拉50个SSE流，验证不会互相阻塞
python - <<'EOF'
import asyncio, aiohttp, time

async def pull(session, i):
    async with session.post("http://127.0.0.1:8000/chat/stream",
                            json={"query": "test"}) as resp:
        async for chunk in resp.content.iter_chunked(64):
            pass
    return i

async def main():
    async with aiohttp.ClientSession() as s:
        start = time.time()
        await asyncio.gather(*[pull(s, i) for i in range(50)])
        print(f"50并发流式请求总耗时: {time.time()-start:.1f}s")

asyncio.run(main())
EOF
```

**验收标准**：50个流**同时**进行（总耗时 ≈ 单个流耗时 + 一点点），如果是串行（50倍耗时）说明流生成器里混了阻塞调用。

---

## ✅ 本文档验收清单

- [ ] SSE接口返回正确的 `text/event-stream` 和事件格式
- [ ] 结构化事件（status/token/done/error）四种类型都有处理
- [ ] 浏览器/脚本看到逐token输出
- [ ] WebSocket支持多用户隔离与广播
- [ ] 有心跳或断线清理逻辑
- [ ] 50并发流式测试通过（非串行）

---

## 常见坑

| 症状 | 原因 | 解法 |
|------|------|------|
| 前端一次收到全部内容 | 中间层缓冲 | nginx加 `X-Accel-Buffering: no`；开发模式用uvicorn直连测试 |
| 流报错后客户端永远转圈 | 错误后没发done帧 | 服务器except里必须补发 error + done 事件 |
| WebSocket部署后连不上 | 代理不支持或路径错 | nginx配置 `proxy_set_header Upgrade $http_upgrade` |
| 用户断开服务器还在生成 | 没监听断开 | try/except WebSocketDisconnect + 取消生成任务 |

---

**下一篇** → [06_project_chat_service.md](./06_project_chat_service.md)
