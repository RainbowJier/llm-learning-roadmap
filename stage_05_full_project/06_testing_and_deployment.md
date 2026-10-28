# 测试与部署

> 周次：Week 9 ｜ 投入：12小时 ｜ 前置：05_implementation_guide.md

---

## 目标

上线前的最后一道工序：全量回归、性能压测、生产部署固化、runbook成文。**这一周的质量决定内测的口碑**。

---

## Step 1: 全量回归测试（4小时）

```bash
# 一条命令跑完四层测试
pytest tests/ -v --cov=app --cov-report=term-missing | tee reports/regression_w9.txt
python scripts/evaluate.py --test-set datasets/test_set_150.json --tag v0.4
```

四层测试金字塔（全部要绿）：

| 层 | 内容 | 规模 | 关键指标 |
|----|------|------|---------|
| 单元测试 | 各模块函数级 | 覆盖≥80% | 全绿 |
| 组件测试 | 检索/意图/引用核验各自跑测试集 | 150条 | 各自达标 |
| 端到端 | API层全意图场景 | 30条场景脚本 | 全绿 |
| 混沌 | 5类故障注入 | 复用Stage 4 | 符合错误预算表 |

**重点盯意图边界10条**（02文档定义的）——分类错误是内测期最伤口碑的问题。

---

## Step 2: 性能与成本终测（3小时）

```bash
# 50并发×3分钟（模拟内测高峰: 50人×每天20问≈峰值集中10分钟)
python scripts/loadtest.py --concurrency 50 --duration 180 --url $URL
```

对照检查（Prometheus面板截图存档）：

| 指标 | 目标 | 实测 | SLO |
|------|------|------|-----|
| P95延迟 | <3s | __ | ✅/❌ |
| TTFT | <1s | __ | |
| 错误率 | <0.1% | __ | |
| 降级率 | <2% | __ | |
| 成本/千请求 | <$10 | __ | |
| 内存曲线 | 稳定 | __ | |

不达标→回Stage 4-04优化手册对症下药（缓存/并行/瘦身），**不带病上线**。

---

## Step 3: 生产部署固化（3小时）

```yaml
# 生产compose要点（在Stage 4基础上加）
services:
  app:
    restart: unless-stopped            # 崩溃自拉起
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
    logging: {max-size: "100m", max-file: "3"}   # 日志防撑爆磁盘
    deploy:
      resources:
        limits: {memory: 2G}           # 防内存失控
  backup:
    """每日: SQLite反馈表 + 爬取状态 + 索引配置 打包留7份"""
```

- [ ] HTTPS（Caddy反向代理一行搞定，或内网隧道自带）
- [ ] 备份cron跑通一次并演练**恢复**
- [ ] 域名/访问方式稳定（别让用户明天换地址）

---

## Step 4: Runbook（2小时）

```markdown
<!-- ops/runbook.md —— 给"半夜被叫醒的自己" -->
# 常见告警处置

## P0: HighErrorRate
1. grafana看错误分布(by intent/path) → 定位节点
2. 若LLM供应商问题 → 确认降级阶梯生效(用户无感) → 等恢复
3. 若自己代码 → 回滚: docker tag上一个版本号

## P1: DegradeSpike
1. 看是哪级降级(level标签)
2. level2高频 → 多为检索服务 → 重启检索容器
3. 持续 → 检查向量库磁盘

## 日常
- 每日看: 反馈👎Top3 + 成本 + BadCase新增
- 每周日: 跑爬虫增量 + 重建索引 + 全量回归
- 版本发布流程: tag → preflight → 回归 → compose up → 观察15分钟
```

---

## ✅ 验收清单

- [ ] 四层测试全绿，报告落盘
- [ ] 压测+SLO达标截图存档
- [ ] 生产栈固化（healthcheck/重启/备份/恢复演练）
- [ ] Runbook覆盖P0/P1告警与日常运维
- [ ] 内测公告文案+邀请码就绪 → **准备放用户进来**

---

**下一篇** → [07_user_feedback.md](./07_user_feedback.md)（真正的考验开始）
