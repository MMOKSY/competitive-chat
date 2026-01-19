import socketio

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=[],  # tighten later
)

socket_app = socketio.ASGIApp(sio)

# Import events so handlers register on import
from realtime import events  # noqa: E402,F401
