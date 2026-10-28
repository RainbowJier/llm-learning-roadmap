# 监控与告警搭建

> 投入：10小时 ｜ 前置：01_observability.md

---

## 本文档目标

用Prometheus + Grafana搭起生产级监控面板，配置分级告警。**监控不是给自己看的仪表盘，是"系统病了会主动叫人"的机制**。

---

## Step 1: docker-compose一键起栈（2小时）

```yaml
# docker-compose.yml
services:
  agent:
    build: .
    ports: ["8000:8000"]
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317

  prometheus:
    image: prom/prometheus
    volumes: ["./ops/prometheus.yml:/etc/prometheus/prometheus.yml"]
    ports: ["9090:9090"]

  grafana:
    image: grafana/grafana
    ports: ["3000:3000"]
    depends_on: [prometheus]

  alertmanager:
    image: prom/alertmanager
    ports: ["9093:9093"]
```

```yaml
# ops/prometheus.yml
scrape_configs:
  - job_name: "agent"
    scrape_interval: 15s
    static_configs:
      - targets: ["agent:8000"]     # 抓/app的/metrics
```

**验收**：`docker compose up` 后 Grafana(3000) 添加Prometheus数据源，能看到agent_targets_up=1。

---

## Step 2: 五张核心面板（4小时）

在Grafana建一个"Agent服务大盘"，**只放五张图**（多则乱）：

| # | 面板 | PromQL | 看什么 |
|---|------|--------|--------|
| 1 | QPS与错误率 | `rate(agent_requests_total[5m])` by intent/status | 流量健康度 |
| 2 | P95延迟 | `histogram_quantile(0.95, rate(agent_latency_seconds_bucket[5m]))` | 是否超标 |
| 3 | 降级率 | `rate(agent_degrades_total[5m]) / rate(agent_requests_total[5m])` | 容错触发频率 |
| 4 | Token/请求成本 | `rate(agent_llm_tokens_total[1h])` by model,direction | 成本趋势 |
| 5 | 活跃并发 | `agent_active_requests` | 容量水位 |

每张图配**说明文字**（为什么看这个、异常长什么样）——面板是给"半夜被叫醒的自己"看的。

---

## Step 3: 分级告警规则（3小时）

```yaml
# ops/alerts.yml（挂进prometheus）
groups:
  - name: agent-alerts
    rules:
      # P0：立刻处理（用户已受影响）
      - alert: HighErrorRate
        expr: sum(rate(agent_requests_total{status="error"}[5m]))
              / sum(rate(agent_requests_total[5m])) > 0.05
        for: 2m
        labels: {severity: p0}
        annotations: {summary: "错误率>5%持续2分钟"}

      - alert: P95LatencyHigh
        expr: histogram_quantile(0.95, rate(agent_latency_seconds_bucket[5m])) > 5
        for: 5m
        labels: {severity: p0}

      # P1：1小时内处理（成本/容量风险）
      - alert: DegradeSpike
        expr: sum(rate(agent_degrades_total[10m])) > 0.1
        for: 10m
        labels: {severity: p1}

      # P2：当天看一眼（趋势预警）
      - alert: TokenCostAnomaly
        expr: deriv(agent_llm_tokens_total[1h])[30m:] > 2 * 
              avg_over_time(agent_llm_tokens_total[1h][1d])
        labels: {severity: p2}
```

**分级原则**：
- P0 = 用户可感知（错误率/延迟）→ 推送到手机
- P1 = 质量劣化前兆（降级率上升）→ 即时消息群
- P2 = 成本/容量趋势 → 日报

告警疲劳是大敌：**宁可少配，不可错配**。每条告警要问"它响了我会真的行动吗？"不会就删。

---

## Step 4: 告警演练（1小时）

- [ ] 手动把mock LLM失败率调到50% → HighErrorRate应触发
- [ ] 加sleep模拟慢节点 → P95告警触发
- [ ] 全部恢复 → 告警自动resolved

把告警截图（firing→resolved全流程）存档。

---

## ✅ 验收清单

- [ ] docker-compose一键起完整监控栈
- [ ] 五张面板 + 说明文字
- [ ] P0/P1/P2三级告警规则生效（演练截图）
- [ ] 告警恢复（resolved）也能验证

---

**下一篇** → [03_fault_tolerance.md](./03_fault_tolerance.md)
