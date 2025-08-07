from fastapi import APIRouter, HTTPException
from typing import List
from app.schemas.user import User, UserCreate, UserUpdate

router = APIRouter()

# Mock data for Phase 1
mock_users = [
    {
        "id": 1,
        "email": "john.doe@example.com",
        "full_name": "John Doe",
        "is_active": True,
        "profile": {
            "skills": ["Python", "FastAPI", "React"],
            "experience_years": 5,
            "location": "San Francisco, CA"
        }
    }
]

@router.get("/", response_model=List[User])
async def get_users():
    """Get all active users"""
    return [user for user in mock_users if user["is_active"]]

@router.get("/{user_id}", response_model=User)
async def get_user(user_id: int):
    """Get a specific user by ID"""
    user = next((user for user in mock_users if user["id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.post("/", response_model=User)
async def create_user(user: UserCreate):
    """Create a new user"""
    new_user = {
        "id": len(mock_users) + 1,
        **user.dict(),
        "is_active": True
    }
    mock_users.append(new_user)
    return new_user

@router.put("/{user_id}", response_model=User)
async def update_user(user_id: int, user_update: UserUpdate):
    """Update an existing user"""
    user_index = next((i for i, user in enumerate(mock_users) if user["id"] == user_id), None)
    if user_index is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    updated_user = {**mock_users[user_index], **user_update.dict(exclude_unset=True)}
    mock_users[user_index] = updated_user
    return updated_user
