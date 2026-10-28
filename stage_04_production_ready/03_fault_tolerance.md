# 容错复核与SLO

> 投入：8小时 ｜ 前置：02_monitoring_setup.md

---

## 本文档目标

把Stage 3的容错实现"指标化"：定义SLO，复验混沌实验，用数据证明系统达标。**从容错"做了"到"可证明地达标"**。

---

## Step 1: 定义SLI/SLO/错误预算（2小时）

```markdown
<!-- docs/slo.md -->
# 服务等级目标

## SLI（测量什么）
- 可用性: 非降级非错误请求占比
- 延迟: P95 < 3s（正常路径）；降级路径 P95 < 6s
- 质量: 答案评分 ≥ 4.0/5（周度抽检30条人工评）

## SLO（承诺什么）
- 98% 的请求走正常路径（降级+人工 ≤ 2%）
- 99.9% 的请求返回非5xx（任何故障组合下）
- P95 < 3s @ 50并发

## 错误预算
- 每月允许 2% × 总请求 次降级
- 预算耗尽 → 冻结新功能发布，只修稳定性（真实生产纪律！）
```

**为什么个人项目也要写SLO**：面试被问"你的系统可用性怎么样"时，"我定义了98%正常路径SLO，用混沌实验验证了错误预算"和"应该挺稳定的"之间差一个职级。

---

## Step 2: 混沌实验复验（3小时）

把Stage 3的错误预算表变成**可重复执行的实验脚本**：

```python
# tests/test_chaos.py
import pytest, httpx, asyncio

BASE = "http://localhost:8000"

@pytest.mark.parametrize("fault,expect_key", [
    ("llm_timeout",       "needs_human_or_fallback"),   # LLM全超时
    ("llm_garbage",       "no_500"),                    # 输出全是垃圾
    ("retrieval_down",    "circuit_open_fast_fail"),    # 检索挂
    ("order_tool_down",   "llm_explains"),              # 工具挂
    ("all_down",          "human_ticket"),              # 全挂→工单号
])
async def test_fault_tolerance(fault, expect_key, chaos_env):
    """chaos_env fixture: 通过环境变量让服务注入指定故障"""
    async with chaos_env(fault):
        resp = await asyncio.to_thread(
            httpx.post, f"{BASE}/agent/ask",
            json={"question": "我的订单SO123到哪了"}, timeout=30)
    # 断言矩阵
    assert resp.status_code < 500
    if expect_key == "human_ticket":
        assert "工单" in resp.json()["answer"]
    if expect_key == "no_500":
        assert resp.json()["answer"]           # 永远有答案
    ...  # 按错误预算表逐行断言
```

```bash
pytest tests/test_chaos.py -v --tb=short | tee reports/chaos_final.txt
```

**验收**：全部通过 + 每个case的实际耗时记录（验证"最大耗时"列没吹牛）。

---

## Step 3: 压测下的SLO验证（2小时）

```bash
# 50并发 × 2分钟，同时Prometheus记录指标
# 复用Stage 1压测脚本，结束后用PromQL核对：
#   - P95延迟是否 < 3s
#   - 错误率是否 < 0.1%
#   - 降级率是否 < 2%
#   - 内存/协程是否稳定（无泄漏）
```

**不达标的处理路径**（真实工程决策练习）：
- P95超标 → 04文档性能优化（缓存/并行/砍节点）
- 降级率超标 → 找到具体故障源修（而不是调SLO迁就）

---

## Step 4: 故障复盘模板（1小时）

预演一次完整事故管理（用演练中故意制造的最高级别故障）：

```markdown
<!-- reports/postmortem_demo.md -->
# 故障复盘：模拟LLM供应商全超时

- 时间/影响面: 演练窗口 / 30%请求降级
- 检测: HighErrorRate告警 2分钟触发（符合预期）
- 响应: 降级阶梯自动兜底，无5xx
- 根因: mock注入（真实场景=供应商故障）
- 做得好: 熔断器30s后进入half_open自动恢复
- 待改进: 降级模板答案的用户满意度未采集 → 加入TODO
```

---

## ✅ 验收清单

- [ ] SLO文档成文（SLI/SLO/错误预算三段式）
- [ ] 混沌实验脚本化可重复，全绿
- [ ] 50并发压测下SLO达标（PromQL数据佐证）
- [ ] 一次完整故障复盘文档

---

**下一篇** → [04_performance_optimization.md](./04_performance_optimization.md)
