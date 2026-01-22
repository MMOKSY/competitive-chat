from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import engine, Base
from realtime.sio import socket_app  # mounts /socket.io
from routes.auth import router as auth_router
from routes.health import router as health_router
from routes.messages import router as messages_router
from routes.groups import router as groups_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)

    # realtime
    app.mount("/socket.io", socket_app)

    # http routes
    app.include_router(health_router)
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(messages_router, prefix="/messages", tags=["messages"])
    app.include_router(groups_router, prefix="/groups", tags=["groups"])

    return app


app = create_app()
