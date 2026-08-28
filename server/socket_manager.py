import socketio

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


async def emit_market_update(event: str, data: dict) -> None:
    try:
        await sio.emit(event, data)
    except Exception:
        pass


def register_socket_events() -> None:
    @sio.event
    async def connect(sid, environ, auth):
        await sio.emit("connected", {"status": "ok"}, to=sid)

    @sio.event
    async def disconnect(sid):
        pass

    @sio.event
    async def subscribe(sid, data):
        asset = data.get("asset") if isinstance(data, dict) else data
        room = f"asset:{asset}"
        await sio.enter_room(sid, room)

    @sio.event
    async def unsubscribe(sid, data):
        asset = data.get("asset") if isinstance(data, dict) else data
        room = f"asset:{asset}"
        await sio.leave_room(sid, room)