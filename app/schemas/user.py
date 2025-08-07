from pydantic import BaseModel, EmailStr
from typing import List, Optional

class UserProfile(BaseModel):
    skills: List[str]
    experience_years: int
    location: str

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    profile: Optional[UserProfile] = None

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    profile: Optional[UserProfile] = None
    is_active: Optional[bool] = None

class User(UserBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True
