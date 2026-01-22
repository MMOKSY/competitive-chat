from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, and_, or_, desc

from schemas import (
    GroupCreate, GroupOut,
    GroupMessageCreate, GroupMessageOut,
    PrivateMessageCreate, PrivateMessageOut
)

from models import Group, GroupMember, GroupMessage, PrivateMessage

from core.security import hash_password, verify_password
from schemas import UserCreate, UserLogin
from database import get_db, engine, Base, AsyncSessionLocal
from models import User

from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from schemas import Token, UserOut  # you'll add these schemas
from core.security import hash_password, verify_password, create_access_token, decode_access_token

import socketio

# Lifespan event to create tables on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown (optional cleanup)

# Socket.IO server setup
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=[],  # tighten later when you have frontend origin
)

# wrap Socket.IO into ASGI app so FastAPI can mount it
socket_app = socketio.ASGIApp(sio)

# create FastAPI app and mount Socket.IO
app = FastAPI(lifespan=lifespan)
app.mount("/socket.io", socket_app)

###########################################################################################

@app.post("/auth/register")
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # Find existing user by username
    result = await db.execute(select(User).where(User.username == user.username))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return {"message": "User registered successfully", "id": new_user.id}

@app.post("/auth/login")
async def login_user(user: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user.username))
    existing_user = result.scalar_one_or_none()

    if not existing_user or not verify_password(user.password, existing_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid username or password")

    token = create_access_token(subject=str(existing_user.id))
    return {"access_token": token, "token_type": "bearer"}

# JWT authentication setup ########################################
# When a route uses this, look for an Authorization: Bearer <token> header.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    try:
        user_id = decode_access_token(token)  # returns "sub"
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user

@app.get("/users/me", response_model=UserOut)
async def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user

##### END JWT AUTH SETUP ##############################################################

# direct message room naming; user id based; only for private messages
def dm_room(a: int, b: int) -> str:
    """
    Ensures both sides compute the same room name:
    dm_room(2,1) == dm_room(1,2) == "dm:1:2"
    """
    x, y = (a, b) if a < b else (b, a)
    return f"dm:{x}:{y}"

# socket io authentication on connect
@sio.event
async def connect(sid, environ, auth):
    token: Optional[str] = None
    if isinstance(auth, dict):
            token = auth.get("token")

    if not token:
        return False  # reject connection

    async with AsyncSessionLocal() as db:
        try:
            user_id = decode_access_token(token)
        except Exception:
            return False

        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            return False
        
        # Save user_id on the socket session for later events
        await sio.save_session(sid, {"user_id": user.id})

        # Optional: personal room for user-level notifications later
        await sio.enter_room(sid, f"user:{user.id}")

    return True

@sio.event
async def disconnect(sid):
    pass

# socketio subscribe to a DM room
@sio.event
async def subscribe(sid, data):
    """
    Client sends:
      sio.emit("subscribe", {"room": "group:1"})
      sio.emit("subscribe", {"room": "dm:1:2"})

    Server checks authorization, then enters the room.
    """
    session = await sio.get_session(sid)
    user_id = session.get("user_id")

    room = (data or {}).get("room")
    if not isinstance(room, str):
        await sio.emit("error", {"message": "Missing room"}, to=sid)
        return

    async with AsyncSessionLocal() as db:
        allowed = False

        # Group authorization: user must be in group_members
        if room.startswith("group:"):
            try:
                group_id = int(room.split(":", 1)[1])
            except ValueError:
                allowed = False
            else:
                q = await db.execute(
                    select(GroupMember).where(
                        and_(
                            GroupMember.group_id == group_id,
                            GroupMember.user_id == user_id,
                        )
                    )
                )
                allowed = q.scalar_one_or_none() is not None

        # DM authorization: user must be one of the two participants
        elif room.startswith("dm:"):
            parts = room.split(":")
            if len(parts) == 3:
                try:
                    a = int(parts[1])
                    b = int(parts[2])
                except ValueError:
                    allowed = False
                else:
                    allowed = user_id in (a, b)

        if not allowed:
            await sio.emit("error", {"message": "Not authorized for room"}, to=sid)
            return

    await sio.enter_room(sid, room)
    await sio.emit("subscribed", {"room": room}, to=sid)


@sio.event
async def unsubscribe(sid, data):
    """
    Client sends:
      sio.emit("unsubscribe", {"room": "group:1"})
    """
    room = (data or {}).get("room")
    if not isinstance(room, str):
        await sio.emit("error", {"message": "Missing room"}, to=sid)
        return

    await sio.leave_room(sid, room)
    await sio.emit("unsubscribed", {"room": room}, to=sid)

# health endpoints
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/health/db")
async def db_health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"database": "ok"}
    except Exception as e:
        return {"database": "error", "details": str(e)}
    

# create private message
@app.post("/messages/private", response_model=PrivateMessageOut)
async def create_private_message(
    message: PrivateMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # checks to prevent messaging oneself
    if message.receiver_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot message yourself")

    receiver_query = await db.execute(select(User).where(User.id == message.receiver_id))
    receiver = receiver_query.scalar_one_or_none()

    # ensure receiver exists
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")

    new_message = PrivateMessage(
        sender_id=current_user.id,
        receiver_id=message.receiver_id,
        content=message.content,
    )

    # save to db
    db.add(new_message)
    await db.commit()
    await db.refresh(new_message)

    # Realtime: emit to DM room with socket.io
    room = dm_room(current_user.id, message.receiver_id)
    payload = PrivateMessageOut.model_validate(new_message).model_dump(mode="json")
    await sio.emit("message", {"room": room, "data": payload}, room=room)


    return new_message

# get private messages between current user and another user
@app.get("/messages/private/{other_user_id}", response_model=list[PrivateMessageOut])
async def get_private_messages(
    other_user_id: int,
    current_user: User = Depends(get_current_user),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    messages_query = await db.execute(
        select(PrivateMessage).where(
            or_(
                and_(
                    PrivateMessage.sender_id == current_user.id,
                    PrivateMessage.receiver_id == other_user_id,
                ),
                and_(
                    PrivateMessage.sender_id == other_user_id,
                    PrivateMessage.receiver_id == current_user.id,
                ),
            )
        ).order_by(PrivateMessage.created_at)
        .limit(limit)
    )
    messages = messages_query.scalars().all()
    return messages

# create group
@app.post("/groups", response_model=GroupOut)
async def create_group(
    group: GroupCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    new_group = Group(name=group.name, created_by=current_user.id)

    db.add(new_group)
    await db.commit()
    await db.refresh(new_group)

    # add creator as member
    membership = GroupMember(group_id=new_group.id, user_id=current_user.id)
    db.add(membership)
    await db.commit()

    return new_group

# create group message
@app.post("/groups/{group_id}/messages", response_model=GroupMessageOut)
async def create_group_message(
    group_id: int,
    message: GroupMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # check if user is a member of the group
    membership_query = await db.execute(
        select(GroupMember).where(
            and_(
                GroupMember.group_id == group_id,
                GroupMember.user_id == current_user.id,
            )
        )
    )
    membership = membership_query.scalar_one_or_none()

    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of the group")

    new_message = GroupMessage(
        group_id=group_id,
        sender_id=current_user.id,
        content=message.content,
    )

    db.add(new_message)
    await db.commit()
    await db.refresh(new_message)

    # Realtime: emit to group room
    room = f"group:{group_id}"
    payload = GroupMessageOut.model_validate(new_message).model_dump(mode="json")
    await sio.emit("message", {"room": room, "data": payload}, room=room)

    return new_message

# fetch group messages
@app.get("/groups/{group_id}/messages", response_model=list[GroupMessageOut])
async def get_group_messages(
    group_id: int,
    current_user: User = Depends(get_current_user),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    # check if user is a member of the group
    membership_query = await db.execute(
        select(GroupMember).where(
            and_(
                GroupMember.group_id == group_id,
                GroupMember.user_id == current_user.id,
            )
        )
    )
    membership = membership_query.scalar_one_or_none()

    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of the group")

    messages_query = await db.execute(
        select(GroupMessage)
        .where(GroupMessage.group_id == group_id)
        .order_by(desc(GroupMessage.created_at))
        .limit(limit)
    )
    messages = messages_query.scalars().all()
    return messages

# list groups current user is a member of
@app.get("/groups", response_model=list[GroupOut])
async def list_user_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memberships_query = await db.execute(
        select(Group)
        .join(GroupMember)
        .where(GroupMember.user_id == current_user.id)
    )
    groups = memberships_query.scalars().all()
    return groups