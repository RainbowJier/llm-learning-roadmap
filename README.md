# LLM Learning Roadmap

一套面向 AI 应用工程的 62 周学习路线，主线是：

> Python 与后端基础 → RAG → Agent 工作流 → 生产化 → 毕业项目 → 作品集与面试

## 当前状态

本仓库分为两类内容：

- **课程文档**：六个阶段的讲义、周计划和项目设计。
- **离线可运行基线**：不依赖 GPU、真实 API Key 或外部生产服务的 Python 示例与测试。

完整企业项目仍然是学习任务和设计蓝图，不应被误读为已经部署的生产系统。

## 快速开始

要求 Python 3.11+：

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/check_links.py
python scripts/check_course_metadata.py
python scripts/check_snippets.py
```

不想安装可选依赖时，开发依赖已经足够运行基础示例。FastAPI、RAG、LangGraph 和生产观测依赖按 extras 分组，见 `pyproject.toml`。

## 六阶段路线

| 阶段 | 全局周次 | 主题 | 当前可运行基线 |
|---|---:|---|---|
| 1 | 1–8 | Python、FastAPI、asyncio、SSE/WebSocket | 内存聊天服务、异步和流式示例 |
| 2 | 9–20 | 文档处理、切分、检索、评估 | 纯 Python toy RAG |
| 3 | 21–32 | 状态机、工具调用、重试与降级 | 无模型依赖工作流 |
| 4 | 33–38 | 日志、指标、preflight、可靠性 | 标准库日志与离线检查 |
| 5 | 39–50 | 需求、数据、产品化与用户反馈 | 模板和项目蓝图 |
| 6 | 51–62 | 面试、作品集和表达 | 可填写的项目故事模板 |

详细周次见 [`WEEKLY_MASTER_PLAN.md`](WEEKLY_MASTER_PLAN.md)，从 [`START_HERE.md`](START_HERE.md) 开始学习。

## 目录约定

- `stage_XX/.../*.md`：课程材料。
- `code_examples/`：阶段最小示例，应该能独立运行。
- `tests/`：示例的自动化验收。
- `datasets/`：仅提交小型、可公开分发的样例数据；真实数据放在本地。
- `projects/`：学习者逐步完成的项目目录。
- `progress/`、`reports/`：本地学习记录和实验报告，默认不提交敏感数据。

## 学习前置

Stage 1 现在按“可以没有 Java 经验”设计，但仍建议先掌握基本终端操作。Java 对照内容是可选辅助，不是硬前置。真实 LLM API、向量数据库、LangGraph、Docker 和监控栈会在后续阶段作为可选扩展加入。

## 质量边界

文档中的指标分为四类：目标、示例、实测、待运行。没有报告或测试证据的数字只是目标，不代表本仓库已达到该指标。课程中的生产化设计需要结合自己的流量、数据、权限和部署环境验证。

## 贡献

请先阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。新增示例时必须同时提供运行说明和测试；修改周次、学时或指标时请同步更新主计划和入口文档。
