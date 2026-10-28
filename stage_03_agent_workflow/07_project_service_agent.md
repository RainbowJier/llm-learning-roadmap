# 检验项目：智能售后服务Agent

> 对应周次：Week 10-12 ｜ 投入：60小时 ｜ 前置：01-06全部文档

---

## 项目概述

把Stage 3全部能力组装成完整生产形态Agent：意图路由 + RAG子图（复用Stage 2）+ 工具调用 + 校验循环 + 完整容错。

```
用户问题
   │
   ▼
[classify 意图分类(结构化输出)]
   │
   ├─ order_query    → [order_tool 查单工具] ──┐
   ├─ policy_query   → [rag 子图(Stage2复用)] ─┤
   ├─ repair_request → [repair_tool 报修+确认] ─┼→ [compose 生成] → [validate 校验]
   └─ chitchat       → [compose 直接回复] ──────┘        ▲              │
                                                          └──(retry<2)──┤
        任何节点异常 → [human_handoff 转人工] ←──(retry≥2) [fallback 降级] 
   │
   ▼
[final_answer + trace + tool_log] → FastAPI → Streamlit
```

---

## Week 10: 核心图实现（20小时）

### Day 1-2: State与骨架

按03文档设计实现 `workflow/graph.py`：

- [ ] `TicketState` 完整定义（含trace reducer）
- [ ] 8个节点函数骨架（先pass，跑通拓扑）
- [ ] 图编译成功，mermaid导出
- [ ] astream能走通chitchat路径（最短路径先通）

### Day 3-4: 三条业务路径

- [ ] classify接结构化输出（04文档方案）
- [ ] rag子图：把Stage 2的QueryPipeline包成子图接入
- [ ] order_tool/repair_tool：05文档的@tool体系
- [ ] compose生成：综合context+tool_result+校验失败反馈

### Day 5: 循环与容错

- [ ] validate→compose重试环（带feedback）
- [ ] 06文档降级阶梯接入fallback
- [ ] 熔断器包住order_tool

**Week 10验收**：四类意图各3个问题共12条，全部走对路径并得到合理回复（允许mock工具）。

---

## Week 11: API + 观测 + 测试（20小时）

### Day 1-2: FastAPI封装

```python
@app.post("/agent/ask", response_model=AgentResponse)
async def agent_ask(req: AgentRequest):
    start = time.time()
    result = await agent_app.ainvoke({
        "user_input": req.question,
        "history": req.history or [],
        "retry_count": 0, "needs_human": False, "trace": [],
    })
    return AgentResponse(
        answer=result["final_answer"],
        intent=result.get("intent"),
        path=result["trace"],                    # 执行路径！
        needs_human=result["needs_human"],
        latency_ms=(time.time() - start) * 1000)
```

### Day 3-4: 观测与指标统计

```python
# 从trace和tool_log统计每次请求的执行画像
def summarize_run(result: dict) -> dict:
    return {
        "path": "→".join(result["trace"]),
        "llm_calls": result["trace"].count("llm"),
        "tool_calls": len(result.get("tool_log", [])),
        "retries": result["retry_count"],
        "degraded": "fallback" in str(result["trace"]),
    }
# 存进jsonl文件，一周后你会看到路径分布、重试率、降级率
```

### Day 5: 测试矩阵

**功能性**（每类意图10条）：

| 维度 | 指标 | 目标 |
|------|------|------|
| 意图分类准确率 | classify vs 人工标注 | >95% |
| 路径正确率 | 实际路径 vs 预期 | >95% |
| 端到端答案质量 | 人工评分(1-5) | ≥4.0 |
| 单请求延迟P95 | — | <3s |
| Token消耗/请求 | — | <500 |

**容错性**（混沌注入）：

| 注入 | 期望 |
|------|------|
| order_tool一直超时 | needs_human=True + 工单号 |
| LLM每次输出垃圾 | 2次重试后fallback，无500 |
| 检索服务挂 | 熔断，其他意图不受影响 |
| 并发50请求 | 无卡死（复用Stage 1压测脚本） |

---

## Week 12: 打磨 + 文档 + 发布（20小时）

### Day 1-3: BadCase迭代

跑100条混合测试集 → 归因（分类错/检索错/生成错/工具错）→ 修最集中的类别 → 复测。至少完成2轮。

### Day 4: Streamlit演示界面

聊天界面 + **执行路径可视化**（把trace画成流程高亮）——这个演示效果在面试里是核弹级：

```
用户: 我的订单SO20241201到哪了
意图: order_query (0.97)
路径: classify → order_tool → compose → validate → END
工具: query_order(238ms) ✓
延迟: 1.8s | Token: 312
```

### Day 5: 交付物打包

```
agent_system/
├── app/
│   ├── workflow/          # graph.py + nodes.py
│   ├── tools/             # @tool定义
│   ├── models/            # State + 输出Schema
│   ├── resilience/        # 熔断/降级/重试
│   └── api.py
├── rag/                   # Stage 2管线（子图）
├── tests/                 # 功能+混沌双矩阵
├── reports/
│   ├── chaos_results.md   # 混沌实验记录
│   └── eval_100.md        # 100条测试报告
├── ui/app.py
└── README.md
```

README核心表格（简历直接引用）：

| 指标 | 结果 |
|------|------|
| 意图分类准确率 | __% |
| 端到端答案评分 | __/5 |
| 混沌注入下无500率 | 100% |
| P95延迟 | __s |
| Token/请求 | __ |

---

## ✅ 最终验收清单

**功能**
- [ ] 四类意图路由正确
- [ ] RAG子图 + 工具调用 + 校验循环全通
- [ ] 执行路径（trace）可展示
- [ ] 降级阶梯最底层（转人工）永不失败

**指标**
- [ ] 分类>95%，评分≥4.0，P95<3s，Token<500
- [ ] 混沌矩阵全部符合错误预算表预期

**质量**
- [ ] 测试覆盖≥80%（功能+混沌）
- [ ] README含指标表和复现步骤
- [ ] git tag: v1.0-agent

---

## 完成后

1. 技术博客第2篇：《从59%到99%：Agent稳定性的工程手段》
2. 你现在拥有：**RAG系统（指标硬核）+ Agent系统（容错完整）** —— 两个简历大项
3. 进入 Stage 4：给它们装上生产环境的眼睛（可观测性）
