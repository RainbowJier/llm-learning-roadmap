# FastAPI框架详解

> 对应周次：Week 2-3 ｜ 预计投入：20小时 ｜ 前置：02_python_basics.md

---

## 本文档目标

掌握FastAPI全部核心能力：路由、Pydantic请求/响应模型、依赖注入、中间件、异常处理、自动文档。学完后能独立搭建一个结构规范的异步API服务。

**Java视角一句话**：FastAPI ≈ Spring Boot Web + Bean Validation + Swagger 的合体，但代码量是1/5。

---

## Step 1: 第一个应用与自动文档（1小时）

```python
# app/main.py
from fastapi import FastAPI

app = FastAPI(title="我的第一个AI服务", version="0.1.0")

@app.get("/")
async def root():
    return {"message": "hello"}

@app.get("/items/{item_id}")
async def get_item(item_id: int, q: str | None = None):
    # item_id自动从路径解析并校验为int，q是可选查询参数
    return {"item_id": item_id, "q": q}
```

```bash
uvicorn app.main:app --reload
```

**立刻打开这两个地址**（这是FastAPI相对Spring最大的爽点）：
- `http://127.0.0.1:8000/docs` — Swagger UI，可直接调试
- `http://127.0.0.1:8000/openapi.json` — 自动生成的OpenAPI规范

**验收**：故意访问 `/items/abc`，应返回422和明确的错误JSON（类型校验已自动生效）。

---

## Step 2: 请求体与响应模型（3小时）

```python
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Optional

app = FastAPI()

# 请求模型（对标 @RequestBody + DTO）
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="用户问题")
    top_k: int = Field(default=5, ge=1, le=50)
    stream: bool = False

# 响应模型（声明后：1.文档准确 2.多余字段自动过滤 3.类型保证）
class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    latency_ms: float

@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    # req已经是校验过的强类型对象，不需要手写任何校验代码
    answer = await do_retrieve_and_generate(req.query, req.top_k)
    return QueryResponse(
        answer=answer,
        sources=["doc_1.md"],
        latency_ms=123.4,
    )
```

要点：
1. **`response_model` 必写** —— 它会过滤掉函数内部返回的多余字段（如内部debug信息不会泄露给用户）
2. 请求体错误自动返回422 + 逐字段错误详情，前端直接可用
3. `status_code` 可自定义：`@app.post("/items", status_code=201)`

**练习**：写一个 `UserCreate` / `UserOut` 模型对——`UserCreate` 含password，`UserOut` 不含。验证response_model确实不会泄露password。

---

## Step 3: 依赖注入 Depends（3小时）

对标Spring的 `@Autowired`，但FastAPI是**显式函数式**的，一眼看懂数据从哪来。

```python
from fastapi import Depends, HTTPException, Header

# 3.1 基础依赖：数据库连接（yield写法 = 自动清理，对标try-with-resources）
async def get_db():
    db = FakeDB()
    try:
        yield db          # 请求期间使用
    finally:
        await db.close()  # 请求结束自动执行

@app.get("/users")
async def list_users(db: FakeDB = Depends(get_db)):
    return await db.list_users()

# 3.2 依赖可以嵌套（依赖里再依赖，Spring里叫注入链）
async def get_current_user(token: str = Header(...)) -> str:
    if not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid token")
    user = await decode_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    return user

async def get_admin_user(user: str = Depends(get_current_user)) -> str:
    if user != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return user

@app.get("/admin/stats")
async def admin_stats(admin: str = Depends(get_admin_user)):
    return {"secret": "only for admin"}

# 3.3 全局依赖（对标拦截器）：所有路由生效
app = FastAPI(dependencies=[Depends(verify_api_key)])
```

依赖函数里抛 `HTTPException` 会直接中断请求并返回错误——这是做鉴权、限流、日志的标准位置。

**练习**：实现 `get_premium_user` 依赖（嵌套在 `get_current_user` 之上，非会员返回403），并用 `/docs` 面板测试三种token的返回。

---

## Step 4: 中间件（2小时）

```python
import time
from fastapi import Request

# 4.1 计时中间件（对标HandlerInterceptor）
@app.middleware("http")
async def add_process_time(request: Request, call_next):
    start = time.time()
    response = await call_next(request)     # 放行到路由
    elapsed = time.time() - start
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    return response

# 4.2 全局CORS（前端联调必备）
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

执行顺序：`请求 → 中间件(洋葱外层) → 依赖 → 路由函数 → 中间件(内层返回)`。

---

## Step 5: 异常处理与生命周期（2小时）

```python
from contextlib import asynccontextmanager

# 5.1 全局异常处理器（对标 @ControllerAdvice）
from fastapi.responses import JSONResponse

class BusinessError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message

@app.exception_handler(BusinessError)
async def business_error_handler(request: Request, exc: BusinessError):
    return JSONResponse(
        status_code=400,
        content={"error_code": exc.code, "message": exc.message},
    )

@app.get("/order/{order_id}")
async def get_order(order_id: str):
    if order_id == "404":
        raise BusinessError("ORDER_NOT_FOUND", f"订单{order_id}不存在")
    return {"order_id": order_id}

# 5.2 生命周期事件：启动时加载模型/连接池，关闭时清理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # —— 启动逻辑（旧的@app.on_event("startup")已废弃）——
    app.state.embedder = await load_embedding_model()
    print("model loaded")
    yield
    # —— 关闭逻辑 ——
    await app.state.embedder.close()
    print("cleaned up")

app = FastAPI(lifespan=lifespan)

# 路由里使用：request.app.state.embedder
```

---

## Step 6: 项目组织与路由拆分（2小时）

项目大了以后不要全写在main.py（对标Spring的多Controller拆分）：

```python
# app/routers/query.py
from fastapi import APIRouter

router = APIRouter(prefix="/query", tags=["查询"])

@router.post("")
async def query(req: QueryRequest):
    ...

# app/main.py
from app.routers import query, admin

app = FastAPI()
app.include_router(query.router)
app.include_router(admin.router)
```

**练习**：把前面的所有例子重组为 `routers/` 结构，`/docs` 里应出现按tag分组的两组接口。

---

## Step 7: 测试（2小时）

```python
# tests/test_main.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)   # 不需要真正启动服务器

def test_get_item():
    resp = client.get("/items/42")
    assert resp.status_code == 200
    assert resp.json() == {"item_id": 42, "q": None}

def test_invalid_item():
    resp = client.get("/items/abc")
    assert resp.status_code == 422

def test_query_validation():
    resp = client.post("/query", json={"query": ""})   # 违反min_length
    assert resp.status_code == 422

def test_admin_forbidden():
    resp = client.get("/admin/stats", headers={"Authorization": "Bearer user123"})
    assert resp.status_code == 403
```

```bash
pytest tests/ -v
```

**验收**：测试覆盖率 ≥ 80%（`pip install pytest-cov && pytest --cov=app`）。

---

## ✅ 本文档验收清单

- [ ] 能解释response_model的三个作用
- [ ] 能实现嵌套依赖（token解析 → 用户 → 角色校验）
- [ ] 能写出yield形式的数据库依赖并解释清理时机
- [ ] 能注册全局异常处理器统一错误格式
- [ ] 能用lifespan在启动时加载资源
- [ ] 能用TestClient写通过率100%的测试

---

## Java ↔ FastAPI 速查表

| Spring | FastAPI | 备注 |
|--------|---------|------|
| `@RestController` | `APIRouter` + `include_router` | |
| `@GetMapping` | `@app.get()` | |
| `@RequestBody` | 函数参数: Pydantic模型 | 自动校验 |
| `@PathVariable` | 路径占位符 `{item_id}` + 类型注解 | |
| `@RequestHeader` | `Header(...)` | |
| `@Autowired` | `Depends(...)` | 显式声明 |
| `@ControllerAdvice` | `@app.exception_handler` | |
| `HandlerInterceptor` | `@app.middleware("http")` | |
| `application.yml` | `.env` + pydantic-settings | |
| Swagger注解 | **不需要，自动生成** | 核心爽点 |

---

## 常见坑

| 症状 | 原因 | 解法 |
|------|------|------|
| 路由函数里用了阻塞IO（requests、time.sleep） | 整个事件循环被卡死 | 换httpx.AsyncClient / asyncio.sleep |
| async函数里没有await | 白写异步，还比同步慢 | 链式IO务必await |
| response_model没写 | 内部字段泄露到线上 | 所有对外接口都声明response_model |
| 依赖里的db没释放 | 没用yield写法 | `yield` + `finally` |

---

**下一篇** → [04_asyncio_deep_dive.md](./04_asyncio_deep_dive.md)
