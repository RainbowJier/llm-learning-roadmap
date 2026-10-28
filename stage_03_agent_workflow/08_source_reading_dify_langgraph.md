# 源码阅读：LangGraph + Dify

> 位置：Stage 3 收官扩展 ｜ 前置：07检验项目完成 ｜ 投入：LangGraph 1周(~10h) + Dify 2周(~20h)
> 方法论前置：[resources/source_reading_methodology.md](../resources/source_reading_methodology.md)

---

## 为什么这个顺序：先LangGraph后Dify

- **LangGraph小而精**：你刚用它搭过完整工作流，读它的源码=搞懂你每天在用的`compile()/ainvoke()/reducer`到底怎么运转，投入产出比极高
- **Dify大而全**：它**没有用LangGraph而是自研了workflow engine**——读完你就能回答面试高级问题："Dify为什么自己造引擎？LangGraph的边界在哪？"

---

## Part 1: LangGraph（第1周）

### 驱动问题（三个，每个2-3天）

```
Q1: graph.compile()之后，ainvoke()的执行模型到底是什么？
Q2: 我写的 Annotated[list, operator.add] reducer 在哪生效？
Q3: checkpointer怎么做到"断点续跑"？存了什么、什么时候存？
```

### 阅读路径

```bash
pip show langgraph   # 确认版本
# 找到site-packages里的langgraph包（或clone仓库对照读）
```

**Q1 执行模型**（核心，2天）：
```
入口: graph.compile() / app.ainvoke()
  → 追"消息传递循环"是怎么实现的（Pregel超步模型的工程化:
     每一轮 = 找出所有可运行节点 → 执行 → 写channel → 看谁该跑下一轮）
  → 重点理解: 为什么条件边返回的是"下一批节点"而不是单个节点
             → 这就是并行fan-out的底层原因(你Stage 3-02用过的特性)
产出: 一张ainvoke执行时序图(引擎层,不是业务层)
```

**Q2 Channel与reducer**（1天）：
```
追: add_node/add_edge时, State的TypedDict被翻译成了什么数据结构
    (每个字段→一个channel, 带reducer的channel是"累积型")
验证: 写个最小实验——两个并行节点写同一个带operator.add的字段,
      单步调试看merge发生在哪个函数
这解释了你背过的铁律: "节点只返回partial update"的底层原因
```

**Q3 Checkpointer**（1-2天）：
```
追: 每个超步结束后, 什么被序列化进checkpoint(哪个函数)
    thread_id怎么路由到历史 / 恢复时怎么重建State
对照: 你Stage 3项目里的人机interrupt思路, 它的interrupt_before是怎么插进执行循环的
```

**验收**：三个问题的时序图/笔记；能向别人解释"ainvoke一步到底发生了什么"5分钟不磕巴。

---

## Part 2: Dify（第2-3周）

### 定位与地图（Day 1-2）

```bash
git clone https://github.com/langgenius/dify
# 心智模型(以main为准):
#   api/core/workflow/   ← 本轮主战场: 工作流引擎
#   api/core/rag/        ← RAG部分(配合Stage 2的RagFlow经验快速过)
#   api/core/tools/      ← 工具调用体系
#   api/core/model_runtime/  ← 模型供应商抽象层(重点彩蛋)
#   web/                 ← 前端(不看)
```

先跑起来（官方docker-compose），再在UI上搭一个"开始→LLM→条件分支→结束"的最小工作流，跑通一次——**这是后面所有断点的触发器**。

### 主线一：一次工作流执行的调度全流程（Day 3-7，核心）

驱动问题：**"点击运行后，Dify怎么决定节点执行顺序？事件怎么流回前端？失败怎么处理？"**

```
追踪路径:
API入口(run) → workflow实体构建
  → graph engine初始化: 工作流DSL(画布JSON)怎么变成可执行的调度结构
  → 执行循环: 节点选择 → 节点执行(每种节点一个类: llm/if-else/code...)
            → 变量传递(node outputs怎么喂给下一个node的inputs)
  → 事件队列: 每个节点执行产生的event(node_started/finished...)
            怎么变成SSE推给前端画布高亮   ← 这就是你Stage 1做的SSE!
  → 失败处理: 节点异常→重试/分支fallback的引擎级支持
```

重点回答（面试深挖点）：
1. **变量系统**：画布上 `{{#node.output#}}` 这种引用在引擎里怎么解析？（对照你State的显式字段设计——它为了产品化做了动态类型系统，代价是什么？）
2. **并发控制**：并行分支的节点谁先执行？有没有你Stage 3做过的"同字段竞态"问题、它怎么解决？
3. **版本与回放**：工作流DSL有版本管理吗？执行历史能回放吗？（产品化需求，你的checkpointer经验直接对应）

### 主线二：model_runtime抽象层（Day 8-9，彩蛋）

驱动问题：**"Dify怎么做到一套代码对接几十家模型供应商？"**

```
读: model_runtime的Provider/Model抽象接口
   → LLM/Embedding/Rerank各自的统一接口长什么样
   → 供应商差异(function calling支持度/流式格式)在哪一层被抹平
对照: 你Stage 4-05的模型路由+PRICING表,这是同一个问题的工业级答案
```

### 主线三：为什么自研引擎而不用LangGraph（Day 10，升华）

```
带着对比清单读(答案自己总结,不要背别人的结论):
| 维度 | LangGraph | Dify自研 |
|------|-----------|---------|
| 面向对象 | 开发者(代码即图) | 终端用户(画布即图) |
| 图定义时机 | 代码写死 | 运行时从DSL动态构建 |
| 可视化/回放 | 弱 | 原生(事件流) |
| 动态图(循环/条件) | 原生强支持 | ? |
| 生态耦合 | LangChain系 | 自成体系 |
这个对比 = 面试"你了解哪些Agent框架的取舍"的满分答案素材
```

---

## 二次开发练习（Day 11-14，简历句子的实体）

从易到难三选一（**本地跑通即算，不强求PR被merge**）：

```
Lv1: 写一个自定义节点类型(如"调用你学校的课表API"),注册进节点体系
Lv2: 给执行引擎加一个你项目里有而Dify没有的特性
     (如: 全局retry预算——整个工作流的重试总次数上限)
Lv3: 基于事件流做一个简化版执行路径可视化(呼应你Stage 3的trace高亮)
```

完成后：录屏3分钟 + 写清"改了哪些文件、为什么这么改"——这就是简历上 *"对Dify工作流引擎做过二次开发"* 的全部底气（面试官让你白板讲的时候，你讲得出文件名）。

**PR尝试**：同RagFlow文档的阶梯（issue先行）；Dify贡献者多、review快，good first issue竞争也大，心态放平。

---

## ✅ 验收清单

**LangGraph**
- [ ] 三问笔记+时序图
- [ ] reducer并行写入最小实验做过

**Dify**
- [ ] 本地跑通+断点触发
- [ ] 主线一调度全流程时序图（函数级）
- [ ] LangGraph vs Dify对比清单（自己的结论）
- [ ] 二次开发Lv1-3之一完成+录屏
- [ ] 48小时偷师清单：≥2个点回改自己项目（如变量解析容错、事件流式trace）

---

## 与主计划的时间关系

```
Stage 3项目(W10-12)完成 → 本文档(LangGraph 1周 + Dify 2周)
→ 带着"引擎视角"进入Stage 4: 你给自己的系统加监控时会发现
   Dify事件流和你的trace本质是同一种东西的两个精度
```
