#!/usr/bin/env python3
"""
Railway deployment startup script for EasyApply Backend
"""
import os
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_environment():
    """Setup environment for Railway deployment"""
    # Ensure required directories exist
    directories = [
        "converted_files",
        "optimized_files", 
        "processed_documents",
        "processed_files",
        "processed_pdfs",
        "temp_uploads",
        "user_documents",
        "thumbnails",
        "signatures",
        "scanned_documents",
        "pdf_images"
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        logger.info(f"Ensured directory exists: {directory}")
    
    # Set default environment variables if not present
    env_defaults = {
        "SECRET_KEY": "railway-default-secret-key-change-in-production",
        "GEMINI_API_KEY": "",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
    }
    
    for key, default_value in env_defaults.items():
        if not os.getenv(key):
            os.environ[key] = default_value
            logger.info(f"Set default environment variable: {key}")

def main():
    """Main startup function"""
    logger.info("Starting EasyApply Backend on Railway...")
    
    # Setup environment
    setup_environment()
    
    # Import and start the FastAPI app
    try:
        import uvicorn
        from app.main import app
        
        # Get port from Railway environment
        port = int(os.getenv("PORT", 8000))
        host = "0.0.0.0"
        
        logger.info(f"Starting server on {host}:{port}")
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
