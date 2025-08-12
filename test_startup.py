"""
Test script to verify backend startup without full configuration
"""
import os
import sys
import logging

# Add the app directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

# Set up basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """Test that all imports work correctly"""
    try:
        logger.info("Testing imports...")
        
        # Test core config
        from app.core.config import settings
        logger.info("✅ Core config imported successfully")
        
        # Test Gemini service
        from app.services.gemini_service import gemini_job_service
        logger.info("✅ Gemini service imported successfully")
        
        # Test Supabase client (should handle missing env vars gracefully)
        from app.database.supabase_client import supabase_client
        logger.info("✅ Supabase client imported successfully")
        
        # Test API endpoints
        from app.api.endpoints.jobs import router
        logger.info("✅ Jobs API endpoints imported successfully")
        
        # Test main app
        from app.main import app
        logger.info("✅ Main FastAPI app imported successfully")
        
        logger.info("🎉 All imports successful!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Import failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def test_config():
    """Test configuration values"""
    try:
        from app.core.config import settings
        
        logger.info("Testing configuration...")
        logger.info(f"GEMINI_API_KEY set: {'Yes' if settings.GEMINI_API_KEY else 'No'}")
        logger.info(f"SUPABASE_URL set: {'Yes' if settings.SUPABASE_URL else 'No'}")
        logger.info(f"SUPABASE_KEY set: {'Yes' if settings.SUPABASE_KEY else 'No'}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Config test failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("🚀 Starting Applyze Backend Test...")
    
    # Test imports
    if not test_imports():
        sys.exit(1)
    
    # Test configuration
    if not test_config():
        sys.exit(1)
    
    logger.info("✅ All tests passed! Backend is ready to start.")
    logger.info("💡 To start the server: uvicorn app.main:app --reload")
