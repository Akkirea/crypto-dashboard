from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.get("/api/market/snapshot")
async def snapshot(request: Request) -> dict[str, object]:
    return request.app.state.market_state.snapshot()


@router.websocket("/ws/market")
async def market_ws(websocket: WebSocket) -> None:
    app = websocket.app
    state = app.state.market_state
    broadcaster = app.state.broadcaster

    await broadcaster.connect(websocket)
    state.client_count = len(broadcaster.clients)
    await websocket.send_json(state.snapshot())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await broadcaster.disconnect(websocket)
        state.client_count = len(broadcaster.clients)
