# 贡献与维护约定

## 文档

- 新增内容先说明目标、前置、预计核心小时和验收证据。
- 不把不存在的文件写成已提供资源；规划中的路径标记为“学习者创建”。
- 指标必须注明目标、示例、实测或待运行，并给出测量口径。

## 代码

- 示例保持小而可运行，默认不需要外部 API Key、GPU 或私有服务。
- 每个新示例配至少一个 pytest 测试和运行命令。
- 外部服务放在可选依赖中，避免破坏基础学习环境。

## 提交前检查

```bash
python -m pytest -q
python scripts/check_links.py
python scripts/check_course_metadata.py
python scripts/check_snippets.py
ruff check .
```
