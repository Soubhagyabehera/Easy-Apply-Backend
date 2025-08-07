from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import api_router
from app.core.config import settings

app = FastAPI(
    title="JobBot API",
    description="JobBot Phase 1 Backend API",
    version="1.0.0",
)

origins = [
    "https://easy-apply-brown.vercel.app",  # Vercel frontend URL
]
# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # or ["*"] for all, not recommended for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "JobBot API is running!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
