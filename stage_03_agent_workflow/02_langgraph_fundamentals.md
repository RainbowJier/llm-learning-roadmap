# LangGraph基础

> 对应周次：Week 2-3 ｜ 投入：20小时 ｜ 前置：01_agent_design_paradigm.md

---

## 本文档目标

掌握LangGraph四要素：State / Node / Edge / 编译运行。学完能独立构建"改写→检索→生成→校验→条件循环"的完整工作流。

```bash
pip install langgraph
```

---

## Step 1: State——工作流的血液（3小时）

```python
from typing import TypedDict, Annotated
import operator

# State是所有节点共享的"黑板"：每个节点读它、往它写一部分
class AgentState(TypedDict):
    # 普通字段：节点返回什么就覆盖什么
    query: str
    rewritten: str
    context: list[dict]
    answer: str
    # Annotated+reducer：多节点写入时合并而不是覆盖
    messages: Annotated[list[str], operator.add]   # 追加语义
    retry_count: int
    error: str | None
```

**reducer是关键概念**：

```python
# 无reducer: 两个节点都返回 {"messages": [...]} → 后者覆盖前者
# 有reducer(operator.add): 两个节点的列表被拼接

def node_a(state) -> dict:
    return {"messages": ["from_a"]}      # 只返回要更新的字段！

def node_b(state) -> dict:
    return {"messages": ["from_b"]}
# 运行后 state["messages"] == ["from_a", "from_b"]
```

**铁律**：
1. 节点函数**只返回要更新的字段的子集**，不返回整个state
2. 需要跨节点累加的信息（轨迹、日志）用 `Annotated[list, operator.add]`
3. State字段类型一旦定下，全流程遵守（类型错误在compile时就该被发现）

---

## Step 2: Node与Edge（4小时）

```python
import asyncio
from langgraph.graph import StateGraph, START, END

# 节点 = 普通async函数：收state，返回partial update
async def rewrite_node(state: AgentState) -> dict:
    rewritten = await rewriter.rewrite(state["query"], [])
    return {"rewritten": rewritten}

async def retrieve_node(state: AgentState) -> dict:
    results = await retriever.retrieve(state["rewritten"], top_k=5)
    return {"context": results}

async def generate_node(state: AgentState) -> dict:
    answer = await generate_answer(state["rewritten"], state["context"])
    return {"answer": answer}

async def validate_node(state: AgentState) -> dict:
    ok = await check_answer(state["answer"], state["context"])
    return {"validation_ok": ok}

# ---- 组装图 ----
graph = StateGraph(AgentState)
graph.add_node("rewrite", rewrite_node)
graph.add_node("retrieve", retrieve_node)
graph.add_node("generate", generate_node)
graph.add_node("validate", validate_node)

graph.add_edge(START, "rewrite")              # 入口
graph.add_edge("rewrite", "retrieve")         # 固定边
graph.add_edge("retrieve", "generate")
graph.add_edge("generate", "validate")

# 条件边：校验不通过回炉（带硬上限防死循环！）
MAX_RETRY = 2

def route_after_validate(state: AgentState) -> str:
    if state["validation_ok"]:
        return END
    if state["retry_count"] >= MAX_RETRY:     # 硬上限，代码说了算
        return "fallback"
    return "generate"                          # 回炉重造

graph.add_conditional_edges(
    "validate",
    route_after_validate,
    {"generate": "generate", "fallback": "fallback"} ,
)

app = graph.compile()      # 编译成可执行对象（校验图完整性）

# ---- 运行 ----
result = await app.ainvoke({
    "query": "试用期年假几天",
    "retry_count": 0,
    "messages": [],
})
```

**注意**：`route_after_validate` 返回 `END` 时可简写在path_map外。fallback节点负责降级（返回FAQ答案），别忘了添加它。

---

## Step 3: 理解执行模型（2小时）

```
ainvoke内部发生的事：
1. 初始化state（用户输入 + 默认值）
2. 从START沿边找下一个节点
3. await该节点函数，把返回值merge进state（reducer规则）
4. 看该节点的出边：固定边直接走；条件边调用router函数
5. 重复直到END
```

**重要特性**：
- **单线程顺序执行**为主；`add_node`传入的函数若并行调度，靠下一条Step 4
- 条件路由函数是**纯Python**（不是LLM）——所以路由确定性可控；LLM可以出现在router函数**内部**做分类，但返回值仍是枚举

**调试三板斧**：

```python
# 1. 流式看每个节点的输出（排障神器）
async for event in app.astream({"query": "...", "retry_count": 0}):
    print(event)        # 每个节点完成时打印其partial update

# 2. 拿到图结构画出来
png = app.get_graph().draw_mermaid_png()
open("graph.png", "wb").write(png)

# 3. 递归限制（防死循环双保险）
app.ainvoke(state, config={"recursion_limit": 10})
```

---

## Step 4: 并行节点（fan-out/fan-in）（3小时）

```python
# 需求：同时查知识库 + 查订单系统，再汇总
async def search_kb(state) -> dict:
    return {"kb_results": await kb_search(state["rewritten"])}

async def query_order(state) -> dict:
    return {"order_info": await order_api(state["rewritten"])}

async def merge(state) -> dict:
    # 两个分支的结果都已在state里
    return {"merged": state["kb_results"] + [state["order_info"]]}

graph.add_node("search_kb", search_kb)
graph.add_node("query_order", query_order)
graph.add_node("merge", merge)

graph.add_edge("rewrite", "search_kb")     # fan-out：一进二
graph.add_edge("rewrite", "query_order")
graph.add_edge("search_kb", "merge")       # fan-in：merge等两个都完成
graph.add_edge("query_order", "merge")
# LangGraph在merge处自动等待所有入边完成（barrier语义）
```

State字段用**不同的key**（kb_results / order_info）避免写冲突——并行节点写同一个key会竞态。

---

## Step 5: 子图与Checkpointer（4小时）

### 5.1 子图复用

```python
# 把Stage 2的RAG整条管线包成一个子图
rag_subgraph = build_rag_graph().compile()

async def retrieve_node(state: AgentState) -> dict:
    rag_result = await rag_subgraph.ainvoke({"query": state["rewritten"]})
    return {"context": rag_result["results"]}
# 主图里rag就是普通节点 —— 分层设计，别把20个节点摊一张大图
```

### 5.2 Checkpointer：状态持久化（断点续跑）

```python
from langgraph.checkpoint.memory import MemorySaver
# 生产换 langgraph-checkpoint-postgres

checkpointer = MemorySaver()
app = graph.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "user_123"}}
await app.ainvoke(inputs, config)     # 执行到一半挂了？state已存

# 恢复：同thread_id再次invoke，从断点继续
# 还能拿历史快照做审计
for snap in app.get_state_history(config):
    print(snap.next, snap.values)
```

**人机协同场景**（面试加分）：`interrupt_before=["execute_payment"]` → 图在支付节点前暂停，人工确认后继续。

---

## Step 6: 动手实验（4小时）

实现并跑通这个完整图（**07项目的前身**）：

```
START → rewrite → retrieve → generate → validate ─┬→ END
                                        ↑          └→ (retry<2) generate
                                        └── fallback → END
```

验收断言：
- [ ] 正常query一次通过到END
- [ ] 构造一个必失败场景（如context为空），验证走2次重试后进fallback
- [ ] `astream` 能打出每步事件
- [ ] mermaid图能导出且和代码一致
- [ ] recursion_limit=5 时死循环图会抛GraphRecursionError而不是真死循环

---

## ✅ 验收清单

- [ ] 能解释reducer（operator.add）解决什么问题
- [ ] 节点只返回partial update已成肌肉记忆
- [ ] 条件路由的"硬上限"逻辑能默写
- [ ] 并行fan-out/fan-in跑通且无字段竞态
- [ ] 会用astream调试任一节点

---

## 常见坑

| 坑 | 现象 | 解法 |
|----|------|------|
| 节点返回了整个state | 后面的reducer全乱 | 只返回更新的字段 |
| 忘加retry上限 | GraphRecursionError | router里查retry_count |
| 并行节点写同一key | 结果互相覆盖 | 不同分支用不同字段 |
| sync节点里跑async代码 | 卡死/报错 | 节点全用async def + ainvoke |

---

**下一篇** → [03_state_machine_design.md](./03_state_machine_design.md)
