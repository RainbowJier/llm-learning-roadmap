# 状态机设计与业务建模

> 对应周次：Week 4 ｜ 投入：12小时 ｜ 前置：02_langgraph_fundamentals.md

---

## 本文档目标

学会把模糊的业务需求翻译成严谨的状态机：State字段设计、节点粒度划分、路由策略、循环上限。**这是从"会用LangGraph"到"能设计Agent"的分水岭**。

---

## Step 1: 设计流程四步法（2小时）

拿到需求后按这个顺序做，**先纸后码**：

```
1. 列出终点：这个流程的成功产出是什么？失败时用户看到什么？
2. 列出决策点：哪些地方有多种走向？每个走向的判断依据是什么？
3. 定义State：每个节点需要读什么、写什么 → 推出全部字段
4. 划分节点：一个节点 = 一次可独立重试/独立观测的原子动作
```

**节点粒度判断**：
- 太粗（一个节点干检索+生成+校验）→ 无法局部重试、无法观测
- 太细（"拼接字符串"也是节点）→ 图爆炸、延迟浪费
- **经验值**：一个节点对应一次LLM调用 或 一次外部IO 或 一次纯计算聚合

---

## Step 2: 实战建模——售后工单Agent（4小时）

需求："用户描述问题 → 判断是查订单/查政策/报修 → 执行对应工具 → 校验结果 → 回复；校验失败重试最多2次，工具挂了走人工通道。"

### 2.1 第一步：终点

```
成功: 带引用的解决方案
失败A: 重试2次仍差 → 降级模板回复
失败B: 工具不可用 → 转人工（生成工单号）
```

### 2.2 第二步：决策点

```
D1 分类路由: order_query | policy_query | repair_request | chitchat
D2 校验: 通过 | 不通过(且retry<2) | 不通过(且retry>=2)
D3 工具健康: 正常 | 超时/异常
```

### 2.3 第三步：State（完整定义）

```python
from typing import TypedDict, Annotated, Literal
import operator

class TicketState(TypedDict):
    # 输入
    user_input: str
    history: list[dict[str, str]]
    # 路由
    intent: Literal["order_query", "policy_query",
                    "repair_request", "chitchat"] | None
    # 数据
    rewritten_query: str
    order_info: dict | None          # 订单工具产出
    policy_context: list[dict]       # RAG产出
    draft_answer: str
    # 控制
    retry_count: int
    validation_ok: bool | None
    needs_human: bool
    # 输出与审计
    final_answer: str
    trace: Annotated[list[str], operator.add]   # 每节点append一行审计日志
```

### 2.4 第四步：节点清单与图

```
START → classify →(按intent)→ order_tool ──┐
                        ├─→ policy_rag ────┤→ compose → validate ─┬→ END
                        └─→ repair_tool ───┘          ↑           │
                             chitchat ────→ compose   └─(retry<2)─┘
                                            fallback → END
        （任何工具节点异常 → needs_human → human_handoff → END）
```

```python
async def classify_node(state: TicketState) -> dict:
    intent = await classify_intent(state["user_input"])     # 04文档实现
    return {"intent": intent, "trace": [f"classify→{intent}"]}

def route_by_intent(state: TicketState) -> str:
    return {
        "order_query": "order_tool",
        "policy_query": "policy_rag",
        "repair_request": "repair_tool",
        "chitchat": "compose",
    }[state["intent"]]      # 枚举查表：LLM已经选过了，路由本身是纯代码
```

---

## Step 3: 循环与上限的三层防线（2小时）

```python
MAX_RETRY = 2

async def validate_node(state: TicketState) -> dict:
    ok = await validate(state["draft_answer"],
                        state.get("policy_context", []))
    new_count = state["retry_count"] + (0 if ok else 1)
    return {"validation_ok": ok, "retry_count": new_count}

def route_after_validate(state: TicketState) -> str:
    if state["validation_ok"]:
        return "finalize"
    if state["retry_count"] >= MAX_RETRY:       # 防线1：业务层上限
        return "fallback"
    return "compose"                             # 带着失败原因重试

# 防线2：compose节点读取上次的校验反馈塞进prompt（有信息的重试，不是傻重试）
async def compose_node(state: TicketState) -> dict:
    feedback = ""
    if state["validation_ok"] is False:
        feedback = f"\n注意，上一次回答未通过校验，原因：{state.get('validation_feedback', '')}，请修正。"
    ...

# 防线3：全局递归限制
app = graph.compile()
await app.ainvoke(inputs, config={"recursion_limit": 15})
```

**重试要有信息增量**：单纯重新生成=碰运气；把校验失败原因喂回去=定向修正。

---

## Step 4: 异常路径设计（2小时）

```
原则：任何外部依赖的节点都可能挂。异常不try/catch吞掉，而是显式变成状态。

async def order_tool_node(state: TicketState) -> dict:
    try:
        info = await with_timeout(order_api(state["rewritten_query"]), timeout=5)
        return {"order_info": info, "trace": ["order_tool:ok"]}
    except Exception as e:
        return {"needs_human": True,
                "trace": [f"order_tool:FAIL({type(e).__name__})"]}
    # 注意：返回错误状态而不是raise —— 图继续走到human_handoff，
    # 而不是整个invoke崩溃（用户至少拿到工单号）

def route_after_order(state) -> str:
    return "human_handoff" if state["needs_human"] else "compose"
```

**决策**：什么错误走降级（fallback）、什么走人工（human）、什么该崩溃（配置错误类）——**写进设计文档**，别现场发挥。

---

## Step 5: 设计评审checklist（2小时）

画完图先自检，再动手写代码：

- [ ] 每个节点的输入输出字段在State里都有归属（无隐式全局变量）
- [ ] 所有循环都有明确出口和上限
- [ ] 每个外部依赖（LLM/API/DB）的失败都有路径
- [ ] LLM只出现在：节点内部 或 router的枚举分类；流程拓扑100%由代码定义
- [ ] 审计字段（trace）每个节点都append
- [ ] 能画出完整mermaid图并讲给外行听懂

**练习**：把你在01文档画的报销审批流程图，按本文四步法重做到通过全部checklist，然后用LangGraph实现跑通（mock外部依赖即可）。

---

## ✅ 验收清单

- [ ] 售后工单状态机完整实现（含4路路由、重试、降级、人工）
- [ ] 自己业务的图通过checklist并实现
- [ ] 异常成为状态（不是裸raise）
- [ ] 重试带失败原因反馈

---

**下一篇** → [04_structured_output.md](./04_structured_output.md)
