# Stage 4：生产化基础

```bash
python -m pytest stage_04_production_ready/tests -q
python stage_04_production_ready/code_examples/01_logging_and_metrics.py
```

当前示例只使用标准库，练习：

- 结构化 JSON 日志
- request ID 字段
- 延迟记录
- 可注入的 preflight HTTP 客户端

`06_production_checklist.md` 中的上线清单仍是设计材料；真正的 Prometheus、OpenTelemetry、Grafana、告警、备份和混沌实验需要在具体部署环境中验证，不能把伪代码当作已完成的生产检查。
