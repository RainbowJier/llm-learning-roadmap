# Tool Calling工程模式

> 对应周次：Week 7-8 ｜ 投入：15小时 ｜ 前置：04_structured_output.md

---

## 本文档目标

实现生产级工具调用系统：工具注册（Schema自动生成）→ 执行循环 → 结果回喂 → 超时/重试/降级。工具是Agent的手脚，本文档保证手脚不会抽筋。

---

## Step 1: 工具定义——从手写JSON到自动生成（3小时）

**反面教材**：手写每个工具的JSON Schema → 和Python函数签名漂移，必出事故。

**正确做法：从函数签名+docstring自动生成**：

```python
import inspect, json
from pydantic import BaseModel, create_model

class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict          # JSON Schema

def tool(func):
    """装饰器：把函数注册成工具，Schema从类型提示自动推导"""
    sig = inspect.signature(func)
    fields, required = {}, []
    for pname, param in sig.parameters.items():
        ann = param.annotation
        default = ... if param.default is inspect.Parameter.empty else param.default
        if default is ...:
            required.append(pname)
        fields[pname] = (ann, default)

    # 用pydantic动态建Model → 直接得到标准JSON Schema
    args_model = create_model(f"{func.__name__}_args", **fields)
    schema = args_model.model_json_schema()
    schema.pop("title", None)
    for r in required:
        schema.setdefault("required", []).append(r)

    func.tool_spec = ToolSpec(
        name=func.__name__,
        description=inspect.getdoc(func) or "",   # docstring就是工具说明！
        parameters=schema)
    return func

# —— 定义业务工具：写函数=定义工具，一份代码两用 ——
@tool
async def query_order(order_id: str, field: str) -> dict:
    """查询订单信息。field可选: status/amount/logistics
    order_id: 订单号，形如SO开头的16位数字
    field: 要查询的字段名"""
    return await order_api.get(order_id, field)

@tool
async def search_policy(query: str) -> list[str]:
    """搜索公司制度文档，返回相关条款列表
    query: 检索关键词"""
    return await kb.search(query)

# 转成API要的格式
def to_api_tools(funcs) -> list[dict]:
    return [{"type": "function", "function": f.tool_spec.model_dump()}
            for f in funcs]
```

**docstring质量=工具调用质量**：LLM完全靠name+description+参数描述来决定何时、怎么调用。把"何时不该用"也写进去。

---

## Step 2: 执行循环（4小时）

```python
class ToolExecutor:
    def __init__(self, tools: list, max_rounds: int = 5):
        self.registry = {t.tool_spec.name: t for t in tools}
        self.max_rounds = max_rounds

    async def run(self, user_task: str, llm) -> str:
        messages = [{"role": "user", "content": user_task}]
        api_tools = to_api_tools(self.registry.values())

        for round_no in range(self.max_rounds):          # 硬上限！
            resp = await llm.chat(messages=messages, tools=api_tools)

            if not resp.tool_calls:                      # 不再调工具=结束
                return resp.content

            messages.append(assistant_msg_with_tool_calls(resp))
            for tc in resp.tool_calls:                   # 可能并行多工具
                result = await self._execute_safe(tc)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False)})
        return "（达到工具调用上限，强制收尾）请基于已有信息回答。"

    async def _execute_safe(self, tool_call) -> dict:
        """单工具执行：校验→超时→错误转结构化结果（不raise）"""
        name, raw_args = tool_call.name, tool_call.arguments
        if name not in self.registry:
            return {"error": f"unknown_tool: {name}"}
        try:
            args = json.loads(raw_args)
            func = self.registry[name]
            # 04文档的双保险思想：执行前再校验参数
            result = await asyncio.wait_for(func(**args), timeout=8)
            return {"ok": True, "data": result}
        except asyncio.TimeoutError:
            return {"error": "timeout", "hint": "工具响应超8秒，请换一种方式或告知用户稍后再试"}
        except TypeError as e:
            return {"error": f"bad_args: {e}"}       # LLM给的参数不匹配
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
```

**核心思想：错误也是信息**。工具失败不崩溃，把结构化错误喂回LLM，让它自己决定换路（这叫graceful degradation，比写死降级规则聪明得多）。

---

## Step 3: 工具设计规范（2小时）

好工具vs坏工具（决定Agent上限的不是模型是工具设计）：

| 规范 | 坏例子 | 好例子 |
|------|--------|--------|
| 粒度合适 | `run_sql(sql)` 危险且宽泛 | `query_order(order_id, field)` |
| 参数可枚举 | `field: str` 任意串 | `field: Literal["status","amount"]` |
| 返回紧凑 | 返回整个订单对象200字段 | 只返回请求字段+摘要 |
| 描述含反例 | "查订单" | "查订单。仅用于售后场景；查物流进度请用track_logistics" |
| 幂等标识 | `place_order` 无确认 | 只读工具自动安全；写操作拆confirm参数 |

**写操作三原则**：默认拒绝 → 必须带confirm参数 → 执行后返回可撤销信息（订单号）。

---

## Step 4: 工具调用接进LangGraph（3小时）

```python
async def tool_node(state: TicketState) -> dict:
    task = f"用户问题：{state['rewritten_query']}\n已知订单信息：{state.get('order_info')}"
    answer = await executor.run(task, llm)
    return {"tool_result": answer,
            "trace": ["tools:done"]}

# 图中位置：需要外部数据的分支走tool_node，然后进compose
```

与自由Agent loop的区别：**图里tool_node是一站式的**（内部有限循环），拓扑上仍然是03文档定义的确定路径——LLM的自由度被关在节点笼子里。

---

## Step 5: 观测与测试（3小时）

### 5.1 记录每次调用（Stage 4可观测性的种子）

```python
tool_log.append({
    "round": round_no, "tool": name, "args": args,
    "latency_ms": ..., "ok": "error" not in result,
})
# 汇总进state["trace"]，结束后可统计：调用次数分布/失败率/平均延迟
```

### 5.2 工具级测试矩阵（写进tests/）

| 用例 | 断言 |
|------|------|
| 正确参数 | 返回ok=True和预期数据 |
| LLM幻觉工具名 | 返回unknown_tool错误，不崩溃 |
| 参数类型错 | bad_args，循环继续 |
| 工具内部异常 | 结构化error，LLM收到后能换路 |
| 超时 | timeout错误，总耗时<10s |
| 5轮上限 | 强制收尾文案，无死循环 |

**验收指标**（跑50个真实任务）：工具选择正确率>95%、幻觉工具名0次崩溃、写操作0次无confirm执行。

---

## ✅ 验收清单

- [ ] @tool装饰器自动生成Schema（无手写JSON）
- [ ] 执行循环带硬上限+错误转结构化结果
- [ ] 至少5个业务工具（含2个只读+1个带confirm的写操作）
- [ ] 测试矩阵全绿
- [ ] tool_log完整记录

---

**下一篇** → [06_error_handling.md](./06_error_handling.md)
