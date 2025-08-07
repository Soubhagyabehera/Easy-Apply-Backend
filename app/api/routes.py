from fastapi import APIRouter
from app.api.endpoints import jobs, users

api_router = APIRouter()

api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
