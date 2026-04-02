"""Minimal mock WebSocket server for Live Activity testing.

Responds to iOS client:
1. Accepts any /ws?token=xxx connection
2. Sends connection_ack
3. On any text message → sends task_status sequence (planning→implementing→completed)
4. Echoes pong for ping

Usage: python3 scripts/mock_ws_server.py
"""

import asyncio
import json
import uuid
from urllib.parse import parse_qs, urlparse

import websockets
import websockets.server


async def handler(websocket: websockets.server.WebSocketServerProtocol) -> None:
    path = websocket.request.path if hasattr(websocket, 'request') else websocket.path
    print(f"[CONNECTED] {path}")

    # Send connection_ack
    ack = {
        "type": "connection_ack",
        "content": {
            "user_id": "7ccc2153-04bd-46c0-a2f8-5a01c10cd3ff",
            "session_id": str(uuid.uuid4()),
            "server_time": "2026-04-02T12:00:00Z",
        },
    }
    await websocket.send(json.dumps(ack))
    print("[SENT] connection_ack")

    async for raw in websocket:
        msg = json.loads(raw) if isinstance(raw, str) else {}
        msg_type = msg.get("type", "")
        print(f"[RECV] type={msg_type}")

        # Respond to ping with pong
        if msg_type == "ping":
            pong = {"type": "pong", "content": {"timestamp": "2026-04-02T12:00:00Z"}}
            await websocket.send(json.dumps(pong))
            continue

        # On text message → simulate task lifecycle
        if msg_type == "text":
            task_id = str(uuid.uuid4())
            print(f"[TASK] Creating task {task_id}")

            # 1. task_status: planning
            status1 = {
                "type": "task_status",
                "content": {
                    "task_id": task_id,
                    "status": "planning",
                    "current_step": "architect",
                    "progress_pct": 10,
                    "detail": "Planning started",
                    "completed_steps": 0,
                    "total_steps": 4,
                },
            }
            await websocket.send(json.dumps(status1))
            print("[SENT] task_status: planning (10%)")

            # 2. Progress message
            progress = {
                "type": "progress",
                "content": {
                    "task": "AI isliyor...",
                    "step": 1,
                    "total_steps": 3,
                    "percentage": 30,
                    "details": "Architect analyzing",
                    "phase": "architect",
                },
            }
            await websocket.send(json.dumps(progress))
            print("[SENT] progress: 30%")

            # 3. Typing indicator
            await websocket.send(json.dumps({"type": "typing_start", "content": {}}))

            await asyncio.sleep(3)

            # 4. task_status: implementing
            status2 = {
                "type": "task_status",
                "content": {
                    "task_id": task_id,
                    "status": "implementing",
                    "current_step": "developer",
                    "progress_pct": 50,
                    "detail": "Writing code",
                    "completed_steps": 1,
                    "total_steps": 4,
                },
            }
            await websocket.send(json.dumps(status2))
            print("[SENT] task_status: implementing (50%)")

            await asyncio.sleep(3)

            # 5. task_status: testing
            status3 = {
                "type": "task_status",
                "content": {
                    "task_id": task_id,
                    "status": "testing",
                    "current_step": "tester",
                    "progress_pct": 75,
                    "detail": "Running tests",
                    "completed_steps": 2,
                    "total_steps": 4,
                },
            }
            await websocket.send(json.dumps(status3))
            print("[SENT] task_status: testing (75%)")

            await asyncio.sleep(3)

            # 6. Stream response
            stream_msg = {
                "type": "chat.stream",
                "content": {
                    "message_id": str(uuid.uuid4()),
                    "delta": "Mock response: task completed successfully!",
                    "index": 0,
                },
            }
            await websocket.send(json.dumps(stream_msg))

            # 7. Stream end
            stream_end = {
                "type": "chat.stream_end",
                "content": {
                    "message_id": stream_msg["content"]["message_id"],
                    "full_text": "Mock response: task completed successfully!",
                    "type": "text",
                },
            }
            await websocket.send(json.dumps(stream_end))
            print("[SENT] stream response")

            await asyncio.sleep(2)

            # 8. task_status: completed
            status4 = {
                "type": "task_status",
                "content": {
                    "task_id": task_id,
                    "status": "completed",
                    "current_step": "completed",
                    "progress_pct": 100,
                    "detail": "Task completed",
                    "completed_steps": 4,
                    "total_steps": 4,
                },
            }
            await websocket.send(json.dumps(status4))
            print("[SENT] task_status: completed (100%)")


async def main() -> None:
    print("Mock WS server starting on 0.0.0.0:8000")
    print("iOS app will connect to ws://192.168.0.100:8000/ws")
    async with websockets.serve(handler, "0.0.0.0", 8000):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
