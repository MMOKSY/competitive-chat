from datetime import datetime
from pydantic import BaseModel, EmailStr

# This defines what the client must send to create a new user
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# This defines what the client will receive when requesting user info
class UserOut(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool

    class Config:
        from_attributes = True

class PrivateMessageCreate(BaseModel):
    receiver_id: int
    content: str

class PrivateMessageOut(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    content: str
    created_at: datetime   

    # Enables ORM mode to work with SQLAlchemy models
    class Config:
        from_attributes = True

class GroupCreate(BaseModel):
    name: str

class GroupOut(BaseModel):
    id: int
    name: str
    created_at: datetime   
    created_by: int

    class Config:
        from_attributes = True

class GroupMessageCreate(BaseModel):
    content: str

class GroupMessageOut(BaseModel):
    id: int
    group_id: int
    sender_id: int
    content: str
    created_at: datetime

    class Config:
        from_attributes = True