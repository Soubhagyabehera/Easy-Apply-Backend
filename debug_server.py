#!/usr/bin/env python3
"""
Debug server for FastAPI backend
Run this file directly from your IDE to enable breakpoint debugging
"""

import uvicorn
from app.main import app

if __name__ == "__main__":
    # Run the server in debug mode
    # This allows IDE debugger to attach and hit breakpoints
    print("DEBUG: Starting FastAPI server in DEBUG mode...")
    print("DEBUG: Server will be available at: http://localhost:8000")
    print("DEBUG: Debugger breakpoints should work now!")
    print("=" * 60)
    
    uvicorn.run(
        "app.main:app",  # Use string import path for debugging
        host="127.0.0.1",  # Use localhost instead of 0.0.0.0
        port=8000,
        reload=False,  # Disable reload for debugging
        log_level="info"
    )
