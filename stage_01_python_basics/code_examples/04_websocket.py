"""Minimal WebSocket endpoint for the Stage 1 project.

The runnable application lives in projects/chat_service/app.py. This file
keeps the WebSocket handler small enough to study independently.
"""
from fastapi import WebSocket


async def echo_messages(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            await websocket.send_json({"echo": message})
    except Exception:
        await websocket.close()
