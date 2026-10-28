# 架构设计

> 周次：Week 2 ｜ 投入：10小时 ｜ 前置：02_requirement_analysis.md

---

## 目标

完成可直接照着写代码的架构设计：系统拓扑、Agent工作流图、数据模型、目录结构。**90%复用前四个阶段的资产**，新写的只是业务层。

---

## Step 1: 系统拓扑（2小时）

```
微信/QQ群消息流(可选) ─┐
Streamlit Web ─────────┤
                       ▼
                 [FastAPI 网关]
                 鉴权/限流/日志/指标
                       │
                       ▼
            [Agent编排层 LangGraph]  ←── 复用Stage 3骨架
             │      │      │
             ▼      ▼      ▼
         [RAG子图] [工具集] [校验环]   ←── 复用Stage 2管线
             │      │                   复用Stage 3容错
             ▼      ▼
        [向量库+BM25] [课表API]
             ▲
             │ 离线索引管线(周更)       ←── 复用Stage 2-02/03
        [原始文件仓 datasets/]
                       │
                       ▼
          [监控栈 Prometheus/Grafana]  ←── 复用Stage 4
          [反馈后台 BadCase表]
```

**复用清单**（明确标注，防止重复造轮子）：

| 模块 | 来源 | 改动量 |
|------|------|--------|
| DocumentParser | Stage 2-02 | 换语料适配器 |
| ParentChildChunker | Stage 2-03 | 参数微调 |
| HybridRetriever+RRF+Rerank | Stage 2-04 | 几乎零改动 |
| QueryRewriter | Stage 2-05 | 换prompt |
| Ragas评估 | Stage 2-06 | 新测试集 |
| TicketState/工作流骨架 | Stage 3-03 | 改意图枚举 |
| 结构化输出 | Stage 3-04 | 新Schema |
| @tool体系 | Stage 3-05 | 新工具 |
| 熔断/降级/重试 | Stage 3-06 | 零改动 |
| 监控/告警/成本 | Stage 4全部 | 换指标标签 |

---

## Step 2: Agent工作流定稿（3小时）

```
START → [classify 意图分类(haiku,结构化)]
          │
          ├─ policy_query/multi_condition/process_guide
          │      ↓
          │  [rag_subgraph 改写→混合检索→重排→父块]
          │      ↓ (multi_condition加一步: [decompose 拆条件→逐条检索])
          │      ↓
          │  [compose 生成(带引用+条款号)]
          │
          ├─ tool_query → [route_tool] → [schedule_tool|calendar_tool]
          │                              ↓
          └─ chitchat → [polite_refuse]  ↓
                                        ▼
                                   [validate 校验(faithfulness抽查)]
                                     │通过        │失败<2次→回compose
                                     ▼            │失败≥2
                                    END ←── [fallback 模板+反馈入口]
```

新增的两个业务节点设计：

```python
# decompose节点：多条件推理的核心（02需求US-02）
async def decompose_node(state) -> dict:
    """把复合问题拆成原子问题，逐条检索后合并证据"""
    # 例: "挂科重修85分绩点3.2能评二等奖学金吗"
    # → ["二等奖学金评定条件", "挂科对评奖的影响", "重修成绩如何计算"]
    sub_queries = await llm_haiku.structured(
        DECOMPOSE_PROMPT.format(q=state["rewritten_query"]),
        schema=SubQueries)                    # 结构化输出list[str]
    evidences = await asyncio.gather(          # 并行逐条检索
        *[retriever.retrieve(sq, top_k=3) for sq in sub_queries.queries])
    return {"evidences": list(zip(sub_queries.queries, evidences))}

# validate节点升级：引用核验
async def validate_node(state) -> dict:
    # 抽查答案中的[1][2]引用是否真的支撑对应论断
    ok, feedback = await llm_haiku.structured(
        CHECK_CITATIONS_PROMPT.format(
            answer=state["draft_answer"],
            context=state["evidences"]),
        schema=Validation)
    return {"validation_ok": ok.passed,
            "validation_feedback": feedback if not ok.passed else ""}
```

---

## Step 3: 数据模型与目录结构（3小时）

```python
# 新增持久化表（SQLite起步够用）
FEEDBACK = """  -- 反馈，本阶段最重要的表
CREATE TABLE feedback (
  id INTEGER PRIMARY KEY,
  request_id TEXT, question TEXT, answer TEXT,
  intent TEXT, rating INTEGER,          -- 1赞/-1踩
  reason TEXT,                          -- 答错了/引用错/看不懂
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)"""
BAD_CASES = """   -- 由feedback+人工归因生成
CREATE TABLE bad_cases (
  id INTEGER PRIMARY KEY, feedback_id INTEGER,
  root_cause TEXT,      -- CHUNK/RETRIEVE/RERANK/GEN/CLASSIFY/LABEL
  fix_status TEXT DEFAULT 'open', fixed_version TEXT
)"""
```

```
campus_assistant/
├── app/
│   ├── api.py                 # 网关
│   ├── workflow/              # LangGraph（复用+新节点）
│   ├── rag/                   # Stage 2管线直接搬
│   ├── tools/                 # schedule.py calendar.py ...
│   ├── models/                # State + 业务Schema
│   ├── resilience/            # Stage 3容错直接搬
│   └── feedback/              # 反馈API+后台
├── scripts/
│   ├── crawl_docs.py          # 数据采集（01阶段的爬虫工程化）
│   ├── build_index.py
│   ├── evaluate.py
│   └── preflight.py           # Stage 4自检
├── ops/                       # docker-compose + 监控配置
├── ui/app.py                  # Streamlit
├── datasets/ tests/ reports/
└── README.md
```

---

## Step 4: 设计评审（2小时）

复用Stage 3-05的checklist + 追加三条：

- [ ] 每个意图的路径在图上有唯一归宿（含失败路径）
- [ ] 反馈数据能回流到测试集（闭环打通）
- [ ] 复用模块零复制粘贴（import，不是Ctrl+C）

**输出**：架构文档（含mermaid图）+ 复用清单表。发给技术朋友评一次再动工。

---

## ✅ 验收清单

- [ ] 系统拓扑图+复用清单成文
- [ ] 工作流图含全部意图路径与失败分支
- [ ] decompose/validate新节点有设计说明
- [ ] 目录结构与数据表定稿
- [ ] 通过设计评审

---

**下一篇** → [04_data_preparation.md](./04_data_preparation.md)
