from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.api.v1 import api_v1
from app.core.events import lifespan
from app.notifiers.websocket_manager import ws_manager

app = FastAPI(
    title="iApps Notification Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_v1)

INDEX_HTML = Path(__file__).parent / "index.html"


@app.get("/", response_class=FileResponse)
def serve_ui():
    return FileResponse(INDEX_HTML)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws/notifications")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
