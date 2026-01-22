from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from deps.auth import get_current_user
from models import User, PrivateMessage
from schemas import PrivateMessageCreate, PrivateMessageOut
from realtime.sio import sio
from realtime.events import dm_room

router = APIRouter()


@router.post("/private", response_model=PrivateMessageOut)
async def create_private_message(
    message: PrivateMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if message.receiver_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot message yourself")

    receiver_query = await db.execute(select(User).where(User.id == message.receiver_id))
    receiver = receiver_query.scalar_one_or_none()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")

    new_message = PrivateMessage(
        sender_id=current_user.id,
        receiver_id=message.receiver_id,
        content=message.content,
    )

    db.add(new_message)
    await db.commit()
    await db.refresh(new_message)

    room = dm_room(current_user.id, message.receiver_id)
    payload = PrivateMessageOut.model_validate(new_message).model_dump(mode="json")
    await sio.emit("message", {"room": room, "data": payload}, room=room)

    return new_message


@router.get("/private/{other_user_id}", response_model=list[PrivateMessageOut])
async def get_private_messages(
    other_user_id: int,
    current_user: User = Depends(get_current_user),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    messages_query = await db.execute(
        select(PrivateMessage)
        .where(
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
        )
        .order_by(PrivateMessage.created_at)
        .limit(limit)
    )
    return messages_query.scalars().all()
