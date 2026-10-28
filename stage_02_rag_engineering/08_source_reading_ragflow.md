# 源码阅读：RagFlow

> 位置：Stage 2 收官扩展 ｜ 前置：07检验项目完成 ｜ 投入：2周集中（~20h）+ 每周2h并行偷师
> 方法论前置：[resources/source_reading_methodology.md](../resources/source_reading_methodology.md)

---

## 为什么读RagFlow

RagFlow 是开源项目里**文档解析管线做得最深**的：自研版面分析（deepdoc）、每个文档类型独立的解析策略（rag/app/）、关键词+向量混合检索。你刚在Stage 2手工踩过表格腰斩、OCR、双路融合所有的坑——现在去看工业界怎么系统性解决这些问题。

**注意**：仓库目录会随版本演进，本文给的是**定位关键词+阅读主线**，具体路径以你clone的main分支为准，用文中的grep命令找。

---

## 准备（Day 1）

```bash
git clone https://github.com/infiniflow/ragflow
cd ragflow

# 先看地图：README + docs/ 里的架构说明
# 建立目录心智模型（当前主线结构，仅供定位）:
#   deepdoc/   ← 文档解析核心（版面分析/OCR/表格识别）
#   rag/       ← 切分策略(按文档类型分模块) + 检索/nlp
#   api/       ← Web服务层
#   graphrag/  ← 图谱RAG（可后看）
#   agent/     ← Agent编排（Stage 3时回头看）

# 跑起来（官方docker，需要资源较多；机器吃紧就只跑解析部分单测）
```

**验收**：本地能跑通一次"上传PDF→解析→检索问答"，或至少能单独跑通 deepdoc 对一份样例PDF的解析单测。

---

## 主线一：一份带表格的PDF的一生（Day 2-5，核心）

驱动问题：**"PDF上传后，表格是在哪一步、被谁识别成结构化数据的？在哪个环节防止了表格被切碎？"**

```
追踪路径（自顶向下断点）:
API入口(文件上传) → task构建 → 解析调度
  → deepdoc/ 的版面分析: OCR + layout识别（页→区域: 文本块/表格/标题）
  → 表格结构识别（TSR: table structure recognition）
  → rag/app/ 下按文档类型分派的切分器
     （pdf/naive等各有专属chunking逻辑，"naive"是通用策略）
  → chunk结构入库（含keywords、向量、字段元数据）
```

阅读动作：
1. 断点跟一次完整调用链，画**函数级时序图**
2. 重点读的三个问题：
   - 表格区域识别成什么中间结构？怎么转成文本/HTML？（对比你的`table_to_markdown`）
   - 切分时表格chunk和普通文本chunk的边界规则差在哪？（对比你的`protect_tables`占位法）
   - 合并单元格、跨页表格这两个你记录过的BadCase，它有没有专门处理？（`git log -S "merge"`找相关提交）

```bash
# 定位技巧示例（路径变了也能找到）:
grep -rn "table" deepdoc/ --include="*.py" -l
grep -rn "def.*chunk" rag/app/ | head -20
git log --oneline -S "TSR" -- deepdoc/     # 表格识别的演进历史
```

**产出**：`notes/ragflow_parsing.md` 时序图 + 对比清单第一部分。

---

## 主线二：检索与融合（Day 6-8）

驱动问题：**"RagFlow的关键词检索和向量检索怎么融合？和我的RRF差在哪？重排怎么做？"**

```
追踪路径:
检索入口 → query处理(改写/分词/Hybrid配置)
  → 关键词路: 全文检索(ES-based)的打分
  → 向量路: embedding模型调用 + 相似度
  → 融合与重排: 加权? RRF? 可配置项有哪些默认值？
  → top_k裁剪与上下文组装
```

重点对比（填进对比清单）：

| 维度 | 我的实现 | RagFlow | 差异原因 |
|------|---------|---------|---------|
| 融合算法 | RRF(k=60) | ? | |
| 关键词检索 | rank_bm25(内存) | ? | 规模差异? |
| Rerank | bge-reranker-v2-m3 | ? | |
| 查询预处理 | LLM改写 | ? | |

**注意找它比我多做的**：比如检索前的实体/关键词抽取权重、chunk级别的keywords字段（解析时就为检索准备好的关键词）——这种"**索引期为查询期预付费**"的思路是自己做项目时想不到的。

---

## 主线三：按需选读（Day 9-10，二选一）

- **A. 评估与BadCase**：它怎么组织测试集和回归？（对照Stage 2-06）
- **B. Agent模块初览**：只看目录和入口，留个印象，Stage 3的08文档读完Dify后回来对比"RagFlow的Agent vs Dify的workflow"设计取舍

---

## 偷师清单（Day 11：回改自己项目）

48小时内，从下面（或你自己的发现）挑**至少2个**改回Stage 2/5的项目：

- [ ] 解析期为chunk预生成keywords字段并入向量库元数据
- [ ] 表格识别置信度低于阈值时降级为"行描述文本"（而不是硬转markdown）
- [ ] 检索参数（融合权重/top_k）做成可配置+评估集验证默认值
- [ ] 某个你踩过的边界case它的处理方式

改完跑一次评估，**看指标动没动**——动了（无论方向）都是博客素材。

---

## PR机会（Day 12-14 + 后续并行）

```
1. issue区搜 "good first issue" / "doc" / 你读代码时发现的真实bug
2. 最现实的三个方向:
   - deepdoc对某类中文PDF边角case的解析问题（你手上有脏语料！）
   - 文档/注释缺失模块的补充
   - 你二次开发中抽出的通用小工具
3. 流程: 先开issue描述+复现 → 维护者确认 → 再提PR（直接甩PR容易被拒）
```

---

## ✅ 验收清单

- [ ] 本地跑通+断点可用
- [ ] 主线一时序图（函数级）完成
- [ ] 对比清单填满（解析+检索两部分）
- [ ] ≥2个偷师点改回自己项目并有评估数据
- [ ] 三选一输出：博客 / PR / 魔改Demo录屏

---

**延伸阅读（时间富余）**：LlamaIndex 的 retrievers + node_postprocessors 抽象层（~1天，看接口设计如何把"检索→重排→过滤"做成可组合管道，对比你手写的HybridRetriever类）。

**下一站** → [../stage_03_agent_workflow/08_source_reading_dify_langgraph.md](../stage_03_agent_workflow/08_source_reading_dify_langgraph.md)
