# Stage 3：Agent 工作流

```bash
python -m pytest stage_03_agent_workflow/tests -q
python stage_03_agent_workflow/code_examples/01_state_machine.py
```

本阶段的 baseline 不需要 LLM：

- 状态字段显式声明
- 路由和工具白名单
- 写操作需要批准
- 工具调用产生审计记录
- 重试次数有硬上限
- 失败时进入可观察的 fallback

LangGraph、checkpoint、真实 provider 和人工中断属于可选扩展。任何有副作用的工具都应在真实系统中增加身份、租户、幂等键和权限校验。
