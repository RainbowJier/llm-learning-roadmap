# Python基础对标学习（Java → Python）

> 对应周次：Week 1-2 ｜ 预计投入：15小时 ｜ 前置：无

---

## 本文档目标

用你已经掌握的Java知识做跳板，只学Python里**和Java不一样、且后续RAG/Agent开发必须用到**的部分。学完即可进入FastAPI，不要恋战。

---

## Step 1: 环境搭建（1小时）

```bash
# 1. 确认Python版本（需要3.10+，match语法和新型类型提示）
python --version

# 2. 创建项目目录并初始化虚拟环境
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# 3. 安装基础工具链
pip install fastapi uvicorn pydantic python-dotenv pytest mypy

# 4. 导出依赖（对标 mvn dependency / build.gradle）
pip freeze > requirements.txt
```

**验收**：`python -c "import fastapi; print(fastapi.__version__)"` 输出版本号。

---

## Step 2: 语法差异速览（3小时）

只看差异，不通读教程。逐条在解释器里敲一遍：

| Java写法 | Python写法 | 备注 |
|---------|-----------|------|
| `String s = "hi";` | `s: str = "hi"` | 类型提示是可选但强烈建议 |
| `List<String> list = new ArrayList<>();` | `list: list[str] = []` | |
| `Map<String, Integer> m = new HashMap<>();` | `m: dict[str, int] = {}` | |
| `for (String s : list)` | `for s in list:` | 缩进即代码块 |
| `if (x == null)` | `if x is None:` | 用 `is` 判空 |
| `System.out.println(x)` | `print(x)` | |
| `/** javadoc */` | `"""docstring"""` | |
| `public class Foo` | `class Foo:` | 无访问修饰符，靠约定 `_private` |
| `interface Foo` | `class Foo(Protocol):` | 结构化鸭子类型 |
| `throw new RuntimeException(e)` | `raise RuntimeError(e)` | |
| 字符串拼接 `+` | f-string: `f"{name} is {age}"` | **高频使用** |
| lambda | `lambda x: x * 2` | |

### 2.1 必须掌握的Python特有结构（后续代码里天天见）

```python
# 1. 列表推导式（Java的stream.map().collect()）
squares = [x * 2 for x in range(10) if x % 2 == 0]
# 等价Java: list.stream().filter(x -> x%2==0).map(x -> x*2).collect(toList())

# 2. 字典推导式
scores = {name: len(name) for name in ["alice", "bob"]}

# 3. 解包（Java没有，Agent传参常用）
def query(order_id: str, phone: str): ...
args = ("12345", "13800138000")
query(*args)              # 按位置解包
kwargs = {"order_id": "12345", "phone": "138..."}
query(**kwargs)           # 按关键字解包 —— Tool Calling里解析LLM参数就这么干

# 4. 三元表达式
status = "ok" if score > 0.7 else "bad"   # Java: score>0.7?"ok":"bad"

# 5. None安全链
city = user and user.profile and user.profile.city   # Python 3.8
city = user.profile.city if user and user.profile else None

# 6. match语句（3.10+，对标Java的switch）
match tool_name:
    case "query_db":
        run_query()
    case "send_email" | "send_sms":     # 多值合并
        send_message()
    case _:
        raise ValueError(f"unknown tool: {tool_name}")
```

**练习**：写一个函数 `parse_tool_args(func_name: str, args: dict) -> str`，用match分发到3个不同的模拟函数，用 `**args` 解包传参。

---

## Step 3: 类型提示系统（2小时）

FastAPI/Pydantic的根基，**必须练到肌肉记忆**。

```python
from typing import Optional, Union, Literal, Generic, TypeVar, Protocol
from typing import List, Dict, Tuple

# 基础注解
def retrieve(query: str, top_k: int = 5) -> list[str]: ...

# Optional：可能为None（Java的 @Nullable）
def find_user(user_id: str) -> Optional[dict]:
    return None

# Union / 管道（3.10+）
def process(data: str | dict) -> str: ...

# Literal：限定取值（对标Java枚举的轻量版）
def set_level(level: Literal["debug", "info", "error"]) -> None: ...

# TypedDict：固定结构的dict（对标Java DTO）
from typing import TypedDict

class AgentState(TypedDict):
    query: str
    context: list[str]
    answer: str              # LangGraph的State就是这个

# Protocol：结构化接口（不需要显式implements）
class Retriever(Protocol):
    async def retrieve(self, query: str) -> list[str]: ...

# 任何有retrieve方法的类都自动满足，无需继承 —— 这就是鸭子类型

# 泛型（对标 <T>）
T = TypeVar("T")

def first(items: list[T]) -> T:
    return items[0]
```

**练习**：为一个"订单查询Agent"定义完整类型：`Order`（TypedDict）、`AgentState`（含订单列表和错误信息）、`Tool`（Protocol，含name属性和execute方法）。

---

## Step 4: 装饰器（2小时）

对标Java注解+AOP，但Python装饰器是**真函数**，能直接看懂它做了什么。

```python
import functools
import time

# 4.1 最简单的装饰器：给函数套一层
def timer(func):
    @functools.wraps(func)              # 保留原函数名和docstring
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        print(f"{func.__name__} took {time.time() - start:.3f}s")
        return result
    return wrapper

@timer
def slow_query():
    time.sleep(0.5)

# 等价于 slow_query = timer(slow_query)
# 和Java对比：@Override是给编译器看的标记；Python装饰器是真的把函数替换了

# 4.2 带参数的装饰器（三层嵌套）
def retry(max_retries: int = 3):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    print(f"retry {attempt + 1}/{max_retries}: {e}")
        return wrapper
    return decorator

@retry(max_retries=5)
def call_llm(): ...

# 4.3 异步装饰器（大模型开发高频）
def async_timer(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        print(f"{func.__name__} took {time.time() - start:.3f}s")
        return result
    return wrapper

@async_timer
async def retrieve(query: str): ...
```

**练习**：手写 `cache` 装饰器——相同参数直接返回缓存结果（用dict存），并用 `@timer` 验证第二次调用耗时≈0。

---

## Step 5: 上下文管理器与异常（2小时）

```python
# 5.1 with语句（对标Java try-with-resources）
with open("doc.txt", "r", encoding="utf-8") as f:
    content = f.read()
# 离开with块自动close，即使抛异常

# 5.2 异常处理：只catch需要的，finally清理
class LLMError(Exception):
    """自定义异常（对标 extends RuntimeException）"""

class RateLimitError(LLMError): ...

try:
    result = call_llm()
except RateLimitError:
    wait_and_retry()          # 精确处理
except LLMError as e:
    log_error(e)
    raise                     # 记录后继续抛出
except Exception:
    fallback()                # 兜底
finally:
    cleanup()

# 5.3 自定义上下文管理器（管理连接池、计时等）
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_connection():
    conn = await create_conn()
    try:
        yield conn            # with块内拿到的就是这个
    finally:
        await conn.close()    # 无论是否异常都会执行
```

**练习**：实现 `Timer` 上下文管理器，`with Timer("retrieval"): ...` 结束时打印耗时。

---

## Step 6: Pydantic数据校验（3小时）

这是Python世界里最像"带注解的Java Bean + 自动校验"的东西，**FastAPI和结构化输出都靠它**。

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime

# 6.1 基础模型（对标 @Data + @NotNull + @Min...）
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="用户问题")
    top_k: int = Field(default=5, ge=1, le=50)      # ge/gt/le/lt = 边界校验
    model: Literal["haiku", "sonnet"] = "sonnet"

# 自动完成：类型转换、校验、JSON序列化
req = QueryRequest(query="年假怎么算", top_k=10)
print(req.model_dump())          # 转dict：{'query': '年假怎么算', 'top_k': 10, ...}
print(req.model_dump_json())     # 转JSON字符串
print(QueryRequest.model_json_schema())  # 生成JSON Schema（Tool Calling直接用！）

# 6.2 校验失败自动抛异常
from pydantic import ValidationError
try:
    QueryRequest(query="", top_k=999)
except ValidationError as e:
    print(e.errors())   # [{'type': 'string_too_short', 'loc': ('query',), ...}]

# 6.3 自定义验证器
class EmployeeInfo(BaseModel):
    name: str
    salary: float

    @field_validator("salary")
    @classmethod
    def salary_must_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("薪资必须为正数")
        return v

# 6.4 嵌套模型（结构化输出的核心形态）
class ApprovalStep(BaseModel):
    approver: str
    status: Literal["pending", "approved", "rejected"]

class LeaveRequest(BaseModel):
    employee: str
    leave_type: Literal["sick", "personal", "annual"]
    steps: list[ApprovalStep]          # 一层嵌套
```

**练习**：定义 `OrderQueryResult`（订单号、状态枚举、金额、物流步骤列表），写3组测试数据：合法、类型错误、业务规则违反，观察 ValidationError 输出。

---

## Step 7: 包管理与项目结构（1小时）

```bash
# pip 基本操作（对标maven）
pip install fastapi          # = 引入依赖
pip install -r requirements.txt
pip list                     # = dependency:tree 的平铺版

# 可选进阶：用 uv（2024年后越来越主流，速度极快）
pip install uv
uv venv && uv pip install fastapi
```

推荐项目结构（后续所有项目沿用）：

```
my_project/
├── app/
│   ├── __init__.py
│   ├── main.py          # 入口，FastAPI实例
│   ├── models.py        # Pydantic模型
│   └── routers/         # 按功能拆分的路由
├── tests/
│   └── test_main.py
├── .env                 # 环境变量（API Key等，不进git）
├── requirements.txt
└── README.md
```

---

## ✅ 本文档验收清单

- [ ] 能用列表推导式改写一段Java stream代码
- [ ] 能解释 `*args` / `**kwargs` 解包（口头说出Tool Calling哪里用到它）
- [ ] 能定义 TypedDict 和 Protocol
- [ ] 能手写一个带参数的装饰器（retry）
- [ ] 能用Pydantic定义嵌套模型并触发校验错误
- [ ] `QueryRequest.model_json_schema()` 能跑通并看懂输出

全部打勾 → 进入 `03_fastapi_framework.md`。

---

## 常见坑

| 症状 | 原因 | 解法 |
|------|------|------|
| `ModuleNotFoundError` | 直接在脚本目录外运行 | 用 `python -m app.main` 或装 `pip install -e .` |
| mypy报一堆错 | 没加类型提示 | 至少给公开函数加返回类型 |
| 可变默认参数陷阱 | `def f(items=[])` | 永远用 `None` 占位再在函数体内初始化 |
| f-string里写复杂表达式 | 可读性差 | 先算好变量再插入 |

---

**下一篇** → [03_fastapi_framework.md](./03_fastapi_framework.md)
