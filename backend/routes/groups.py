from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from deps.auth import get_current_user
from models import User, Group, GroupMember, GroupMessage
from schemas import GroupCreate, GroupOut, GroupMessageCreate, GroupMessageOut
from realtime.sio import sio

router = APIRouter()


async def _require_membership(db: AsyncSession, group_id: int, user_id: int) -> None:
    membership_query = await db.execute(
        select(GroupMember).where(
            and_(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
        )
    )
    if not membership_query.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a member of the group")


@router.post("", response_model=GroupOut)
async def create_group(
    group: GroupCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    new_group = Group(name=group.name, created_by=current_user.id)
    db.add(new_group)
    await db.commit()
    await db.refresh(new_group)

    db.add(GroupMember(group_id=new_group.id, user_id=current_user.id))
    await db.commit()

    return new_group


@router.post("/{group_id}/messages", response_model=GroupMessageOut)
async def create_group_message(
    group_id: int,
    message: GroupMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_membership(db, group_id, current_user.id)

    new_message = GroupMessage(
        group_id=group_id,
        sender_id=current_user.id,
        content=message.content,
    )

    db.add(new_message)
    await db.commit()
    await db.refresh(new_message)

    room = f"group:{group_id}"
    payload = GroupMessageOut.model_validate(new_message).model_dump(mode="json")
    await sio.emit("message", {"room": room, "data": payload}, room=room)

    return new_message


@router.get("/{group_id}/messages", response_model=list[GroupMessageOut])
async def get_group_messages(
    group_id: int,
    current_user: User = Depends(get_current_user),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    await _require_membership(db, group_id, current_user.id)

    messages_query = await db.execute(
        select(GroupMessage)
        .where(GroupMessage.group_id == group_id)
        .order_by(desc(GroupMessage.created_at))
        .limit(limit)
    )
    return messages_query.scalars().all()


@router.get("", response_model=list[GroupOut])
async def list_user_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memberships_query = await db.execute(
        select(Group).join(GroupMember).where(GroupMember.user_id == current_user.id)
    )
    return memberships_query.scalars().all()
