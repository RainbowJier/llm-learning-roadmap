# 生产上线检查清单

> 投入：8小时 ｜ 前置：01-05全部文档 ｜ 本阶段毕业文档

---

## 本文档目标

把上线前的所有检查固化为**可执行的自检脚本+人检清单**。上线不是感觉良好，是**每项打勾**。

---

## Step 1: 自动化自检脚本设计（3小时）

> 以下代码是教学骨架，不是可直接上线的完整脚本；其中 `ask` 和若干 `...` 需要按你的服务契约实现。可运行的离线抽象见 `code_examples/02_preflight.py`。

```python
# scripts/preflight.py —— 教学骨架：按服务契约补齐后再使用
import asyncio, httpx, sys, json

BASE_URL = "http://127.0.0.1:8000"
CHECKS = []

def check(name):
    def deco(fn):
        CHECKS.append((name, fn)); return fn
    return deco

@check("服务健康")
async def health():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.get("/health")
    return r.status_code == 200

@check("指标端点")
async def metrics():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.get("/metrics")
    return r.status_code == 200 and "agent_requests_total" in r.text

@check("trace注入")
async def trace_id():
    r = await ask("测试问题")
    return "X-Request-ID" in r.headers

@check("结构化日志")
async def json_logs():
    # 抓最近一行日志验证是合法JSON且带request_id
    ...

@check("SLO达标(P95)")
async def slo_latency():
    # 连发20请求统计P95 < 3s
    ...

@check("混沌注入不产生5xx")
async def chaos():
    ...

@check("成本计量")
async def cost_metered():
    # 发1请求后/metrics里cost指标增长
    ...

async def main():
    passed = 0
    for name, fn in CHECKS:
        try:
            ok = await fn()
            print(f"{'✅' if ok else '❌'} {name}")
            passed += ok
        except Exception as e:
            print(f"❌ {name}: {e}")
    print(f"\n{passed}/{len(CHECKS)} 通过")
    sys.exit(0 if passed == len(CHECKS) else 1)

if __name__ == "__main__":
    asyncio.run(main())
```

**任何一项❌都不上线**——这是目标流程；真实使用前必须补齐所有占位检查并在目标环境演练。

---

## Step 2: 人工检查清单（2小时）

```markdown
## 上线人检清单

### 安全
- [ ] API Key不在代码/日志/前端（.env + 日志脱敏）
- [ ] 所有端点有鉴权（除健康检查）
- [ ] 写操作工具有confirm机制 + 权限校验
- [ ] CORS只开需要的源
- [ ] prompt注入防护：检索内容/工具结果视为不可信数据（有基本隔离说明）
- [ ] 用户输入长度/频率限制（防滥用烧钱）

### 数据
- [ ] 对话日志脱敏策略明确（存什么、存多久）
- [ ] 向量库/父块库有备份与重建脚本（build_index幂等✓）
- [ ] 测试集与生产数据隔离

### 运维
- [ ] docker-compose全栈可一键冷启动
- [ ] 配置全部环境变量化（无硬编码）
- [ ] 告警接收人已确认（P0到手机）
- [ ] 回滚方案：镜像tag + 索引版本可回退
- [ ] 日志保留策略与磁盘空间预估

### 文档
- [ ] README含架构图/SLO/成本数字/复现步骤
- [ ] runbook：常见告警的处理动作写好
```

---

## Step 3: 灰度上线方案（2小时）

个人项目也要练"分批放量"：

```
Day 1-2  内测5人     → 每日看BadCase，修prompt级问题
Day 3-7  50人        → 观察降级率/成本是否在预期内
Week 2   全量        → SLO周报开始
```

灰度期每日检查三件事：**错误预算消耗、成本/千请求、Top3 BadCase**。

---

## Step 4: 阶段收官——简历素材清单（1小时）

Stage 4结束，你的简历弹药库应包含这些**带数字的句子**（全部有报告佐证）：

```
✅ 全链路可观测：LangSmith/Prometheus，每请求trace含分步延迟与Token成本
✅ SLO: 99.9%非5xx / P95<3s@50并发，混沌实验5类故障注入全部通过
✅ 性能: P95 2.8s→__s，TTFT 2.6s→__s（缓存+并行+模型路由）
✅ 成本: 模型分级路由+prompt缓存，单请求成本降__%
✅ 运维: docker-compose监控栈一键部署，P0-P2三级告警
```

---

## ✅ Stage 4毕业标准

- [ ] preflight脚本全绿（CI里也跑）
- [ ] 人检清单全部打勾
- [ ] 灰度方案执行（至少5人内测过）
- [ ] 简历数字清单成文且每条有报告出处

---

**下一阶段** → [Stage 5 README](../stage_05_full_project/README.md)：用全部功力做一个有真实用户的可演示生产原型。
