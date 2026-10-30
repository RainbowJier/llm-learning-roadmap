# Stage 1：Python 与后端基础

## 可运行基线

```bash
python -m pytest stage_01_python_basics/tests -q
uvicorn stage_01_python_basics.projects.chat_service.app:app --reload
```

服务提供：

- `GET /health`
- `POST /chat`：确定性的 mock 回复
- `POST /chat/stream`：SSE 事件流
- `WS /ws/chat/{user_id}`：最小 WebSocket 聊天
- `GET /admin/stats`：内存统计

这个项目故意不接数据库和真实 LLM，目标是先练习请求验证、异步、流式响应和测试。数据库、鉴权、真实 provider 和部署属于后续扩展。

## 文档顺序

1. `01_intro_and_goals.md`
2. `02_python_basics.md`
3. `03_fastapi_framework.md`
4. `04_asyncio_deep_dive.md`
5. `05_streaming_and_websocket.md`
6. `06_project_chat_service.md`
7. `每周计划.md`
