# 成本控制

> 投入：10小时 ｜ 前置：04_performance_optimization.md

---

## 本文档目标

建立"每请求成本可核算、月度成本可预测、超支自动预警"的成本体系。大模型应用最大的运营风险不是技术，是**账单**。

---

## Step 1: 成本核算基础（2小时）

```python
# 成本 = Σ (input_tokens × 单价in + output_tokens × 单价out)
PRICING = {   # $/1M tokens（示例结构，填你实际用的模型，查官方定价页）
    "claude-haiku":     {"in": 0.80,  "out": 4.00},
    "claude-sonnet":    {"in": 3.00,  "out": 15.00},
    "embedding-bge-m3": {"in": 0.02,  "out": 0},
}

def cost_of(model: str, tokens_in: int, tokens_out: int) -> float:
    p = PRICING[model]
    return (tokens_in * p["in"] + tokens_out * p["out"]) / 1_000_000
```

每次LLM调用都记账（挂在01文档的指标体系上）：

```python
async def metered_chat(model: str, messages, **kw):
    resp = await client.chat(model, messages, **kw)
    usage = resp.usage
    COSTS.labels(model=model).inc(cost_of(
        model, usage.input_tokens, usage.output_tokens))
    logger.info("llm_call", model=model,
                tokens_in=usage.input_tokens,
                tokens_out=usage.output_tokens,
                cost_usd=cost_of(model, usage.input_tokens,
                                 usage.output_tokens))
    return resp
```

**所有LLM调用必须走metered封装**——没有计量就没有管理。

---

## Step 2: 成本三大杠杆（4小时）

### 杠杆1: 模型分级路由（最大杠杆，通常省50%+）

```python
class ModelRouter:
    """按任务难度分模型——不是所有思考都值得用最贵的脑子"""
    ROUTES = {
        "query_rewrite": "claude-haiku",       # 简单改写
        "intent_classify": "claude-haiku",     # 枚举分类
        "hyde_generate": "claude-haiku",
        "answer_generate": "claude-sonnet",    # 核心生成
        "answer_validate": "claude-haiku",     # 打分校验
    }
    def model_for(self, task: str) -> str:
        return self.ROUTES[task]
```

进阶：**动态降级路由**——成本超预算日自动把生成降到haiku+更强的prompt补偿（应急阀，不是常态）。

### 杠杆2: Prompt缓存（Anthropic/OpenAI原生支持）

```python
# 系统提示词+few-shot例子 = 每次请求都重复的长前缀
# 加cache_control后：重复前缀按缓存价（约1折）计费
system = [{
    "type": "text",
    "text": LONG_SYSTEM_PROMPT_WITH_EXAMPLES,
    "cache_control": {"type": "ephemeral"},   # 就这一行
}]
# 注意：system放最前、动态内容放最后，前缀稳定才能命中
```

### 杠杆3: 需求侧管理（省的是真金白银）

- 缓存（04文档，命中率直接换算成钱）
- max_tokens按任务设置（改写类任务不需要2000输出）
- 上下文瘦身（04文档）
- **拒答前置**：chitchat类问题不进重管线

---

## Step 3: 成本报表与预算告警（2小时）

```python
# 每日成本报表（cron跑）
async def daily_report():
    by_model = query_prometheus("increase(agent_cost_usd_total[24h]) by model")
    by_task = aggregate_from_jsonl_logs()
    return {
        "total_usd": ...,
        "per_1k_requests": ...,
        "top_consumer_task": ...,
        "cache_savings_usd": ...,      # 对比无缓存假想成本
    }
```

告警规则（接02文档Alertmanager）：

```yaml
- alert: DailyCostOverBudget
  expr: increase(agent_cost_usd_total[24h]) > 5   # 日预算$5
  labels: {severity: p1}
- alert: CostPerRequestSpike
  expr: deriv(increase(agent_cost_usd_total[1h])[6h:]) > 0.5
  labels: {severity: p2}
```

---

## Step 4: 成本-质量权衡实验（2小时）

用Stage 2测试集做模型路由消融：

| 配置 | 全sonnet | 路由(混合) | 全haiku |
|------|---------|-----------|---------|
| 100请求成本 | $__ | $__ | $__ |
| Ragas四指标 | 基线 | __ | __ |
| 结论 | — | 省X%且质量不掉 | 质量/成本甜点位？ |

**找到你的甜点**：通常"生成用强模型+其余用弱模型"能省50-70%成本而指标几乎不降。这张表是简历上"通过模型分级路由将单请求成本降低X%"的出处。

---

## ✅ 验收清单

- [ ] 所有LLM调用走metered封装（漏记=0容忍）
- [ ] 模型路由上线且有消融数据
- [ ] prompt缓存命中（LangSmith/响应头验证）
- [ ] 日成本报表 + 超预算告警生效
- [ ] 成本/千请求数字可稳定复现

---

**下一篇** → [06_production_checklist.md](./06_production_checklist.md)
