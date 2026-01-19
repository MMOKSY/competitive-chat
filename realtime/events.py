from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models import User, GroupMember
from core.security import decode_access_token
from realtime.sio import sio


def dm_room(a: int, b: int) -> str:
    x, y = (a, b) if a < b else (b, a)
    return f"dm:{x}:{y}"


@sio.event
async def connect(sid, environ, auth):
    token: Optional[str] = None
    if isinstance(auth, dict):
        token = auth.get("token")

    if not token:
        return False

    async with AsyncSessionLocal() as db:
        try:
            user_id = decode_access_token(token)
        except Exception:
            return False

        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            return False

        await sio.save_session(sid, {"user_id": user.id})
        await sio.enter_room(sid, f"user:{user.id}")

    return True


@sio.event
async def disconnect(sid):
    pass


@sio.event
async def subscribe(sid, data):
    session = await sio.get_session(sid)
    user_id = session.get("user_id")

    room = (data or {}).get("room")
    if not isinstance(room, str):
        await sio.emit("error", {"message": "Missing room"}, to=sid)
        return

    async with AsyncSessionLocal() as db:
        if not await _is_allowed_room(db, user_id, room):
            await sio.emit("error", {"message": "Not authorized for room"}, to=sid)
            return

    await sio.enter_room(sid, room)
    await sio.emit("subscribed", {"room": room}, to=sid)


@sio.event
async def unsubscribe(sid, data):
    room = (data or {}).get("room")
    if not isinstance(room, str):
        await sio.emit("error", {"message": "Missing room"}, to=sid)
        return

    await sio.leave_room(sid, room)
    await sio.emit("unsubscribed", {"room": room}, to=sid)


async def _is_allowed_room(db: AsyncSession, user_id: int, room: str) -> bool:
    # Group authorization
    if room.startswith("group:"):
        try:
            group_id = int(room.split(":", 1)[1])
        except ValueError:
            return False

        q = await db.execute(
            select(GroupMember).where(
                and_(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
            )
        )
        return q.scalar_one_or_none() is not None

    # DM authorization
    if room.startswith("dm:"):
        parts = room.split(":")
        if len(parts) != 3:
            return False
        try:
            a = int(parts[1])
            b = int(parts[2])
        except ValueError:
            return False
        return user_id in (a, b)

    return False
