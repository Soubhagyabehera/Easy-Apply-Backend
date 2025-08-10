from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import api_router
from app.core.config import settings
from app.database.supabase_client import postgresql_client
import logging

app = FastAPI(
    title="JobBot API",
    description="JobBot Phase 1 Backend API",
    version="1.0.0",
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

@app.on_event("startup")
async def startup_event():
    """Initialize database and other startup tasks"""
    logger = logging.getLogger(__name__)
    logger.info("Starting JobBot API...")
    
    try:
        # Initialize PostgreSQL database
        logger.info("Initializing PostgreSQL database...")
        postgresql_client.ensure_jobs_table_exists()
        logger.info("PostgreSQL database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL database: {e}")
        # Don't fail startup, just log the error
        logger.warning("Continuing startup without database initialization")

@app.get("/")
async def root():
    return {"message": "JobBot API is running!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
