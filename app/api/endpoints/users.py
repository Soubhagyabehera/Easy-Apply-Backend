"""
User management endpoints with authentication support
"""
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
import logging
import jwt
from datetime import datetime, timedelta
from google.oauth2 import id_token
from google.auth.transport import requests
from app.database.supabase_client import postgresql_client
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()

# JWT Configuration
JWT_SECRET = settings.SECRET_KEY
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

def create_access_token(user_data: dict) -> str:
    """Create JWT access token for user"""
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode = user_data.copy()
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT token and return user data"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/auth/google")
async def google_auth(request: dict):
    """
    Authenticate user with Google OAuth ID token
    Verifies the Google ID token and creates/returns user with JWT
    """
    try:
        # Extract the ID token from the request
        id_token_str = request.get("credential") or request.get("id_token")
        if not id_token_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing Google ID token"
            )
        
        # Verify the Google ID token
        try:
            idinfo = id_token.verify_oauth2_token(
                id_token_str, 
                requests.Request(), 
                settings.GOOGLE_CLIENT_ID
            )
            
            # Verify the issuer
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Wrong issuer.')
                
        except ValueError as e:
            logger.error(f"Invalid Google token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google token"
            )
        
        # Extract user information from the verified token
        user_email = idinfo.get('email')
        user_name = idinfo.get('name')
        user_picture = idinfo.get('picture')
        user_google_id = idinfo.get('sub')
        
        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not provided by Google"
            )
        
        # Ensure users table exists
        postgresql_client.ensure_users_table_exists()
        
        # Create or update user in Supabase database
        user_data_for_db = {
            "id": user_google_id,
            "email": user_email,
            "name": user_name or "Unknown User",
            "picture": user_picture or "",
            "is_active": True
        }
        
        # Store/update user in database
        stored_user = postgresql_client.create_or_update_user(user_data_for_db)
        
        if not stored_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store user information"
            )
        
        # Use the database user data for JWT token
        user_data = stored_user
        
        # Create JWT token using existing system
        access_token = create_access_token(user_data)
        
        logger.info(f"User authenticated via Google: {user_email}")
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Google authentication: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to authenticate with Google"
        )

@router.get("/me")
async def get_current_user(current_user: dict = Depends(verify_token)):
    """Get current authenticated user with fresh data from database"""
    try:
        # Get fresh user data from database using the user ID from JWT
        user_id = current_user.get('id')
        if user_id:
            fresh_user_data = postgresql_client.get_user_by_id(user_id)
            if fresh_user_data:
                return fresh_user_data
        
        # Fallback to JWT data if database lookup fails
        return current_user
        
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        # Fallback to JWT data
        return current_user

@router.put("/me")
async def update_current_user(
    user_update: dict,
    current_user: dict = Depends(verify_token)
):
    """Update current authenticated user profile"""
    try:
        user_id = current_user.get('id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User ID not found in token"
            )
        
        # Get current user data from database
        current_user_data = postgresql_client.get_user_by_id(user_id)
        if not current_user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in database"
            )
        
        # Update allowed fields (name, picture)
        update_data = {
            'id': user_id,
            'email': current_user_data['email'],  # Keep existing email
            'name': user_update.get('name', current_user_data['name']),
            'picture': user_update.get('picture', current_user_data['picture']),
            'is_active': current_user_data['is_active']
        }
        
        # Update user in database
        updated_user = postgresql_client.create_or_update_user(update_data)
        
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user information"
            )
        
        logger.info(f"Updated user profile: {updated_user['email']}")
        return updated_user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user profile"
        )

@router.get("/")
async def get_users(current_user: dict = Depends(verify_token)) -> List[dict]:
    """
    Get all users (dummy implementation for now)
    In production, this would fetch from database
    """
    try:
        # Dummy users for now - in Phase 2+, fetch from database
        dummy_users = [
            {
                "id": 1,
                "email": "user1@example.com",
                "name": "John Doe",
                "is_active": True,
                "created_at": "2024-01-01T00:00:00Z"
            },
            {
                "id": 2,
                "email": "user2@example.com", 
                "name": "Jane Smith",
                "is_active": True,
                "created_at": "2024-01-02T00:00:00Z"
            }
        ]
        
        logger.info(f"Retrieved {len(dummy_users)} users")
        return dummy_users
        
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch users"
        )

@router.get("/{user_id}")
async def get_user(user_id: int, current_user: dict = Depends(verify_token)):
    """Get user by ID (dummy implementation)"""
    try:
        # Dummy user data - in Phase 2+, fetch from database
        if user_id == 1:
            user = {
                "id": 1,
                "email": "user1@example.com",
                "name": "John Doe",
                "is_active": True,
                "created_at": "2024-01-01T00:00:00Z"
            }
        elif user_id == 2:
            user = {
                "id": 2,
                "email": "user2@example.com",
                "name": "Jane Smith", 
                "is_active": True,
                "created_at": "2024-01-02T00:00:00Z"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
            
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user"
        )

@router.put("/{user_id}")
async def update_user(
    user_id: int, 
    user_data: dict,
    current_user: dict = Depends(verify_token)
):
    """Update user (dummy implementation)"""
    try:
        # In production, update user in database
        updated_user = {
            "id": user_id,
            "email": user_data.get("email", "updated@example.com"),
            "name": user_data.get("name", "Updated Name"),
            "is_active": user_data.get("is_active", True),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"User {user_id} updated")
        return updated_user
        
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )

# Document management endpoints (dummy for Phase 2)
@router.get("/{user_id}/documents")
async def get_user_documents(user_id: int, current_user: dict = Depends(verify_token)):
    """Get user's documents (dummy for Phase 2)"""
    dummy_documents = [
        {
            "id": 1,
            "name": "Resume.pdf",
            "type": "resume",
            "size": 1024000,
            "uploaded_at": "2024-01-01T00:00:00Z"
        },
        {
            "id": 2,
            "name": "Cover_Letter.pdf", 
            "type": "cover_letter",
            "size": 512000,
            "uploaded_at": "2024-01-02T00:00:00Z"
        }
    ]
    return dummy_documents

@router.post("/{user_id}/documents")
async def upload_document(user_id: int, current_user: dict = Depends(verify_token)):
    """Upload document (dummy for Phase 2)"""
    return {
        "message": "Document upload endpoint - will be implemented in Phase 2",
        "status": "placeholder"
    }

@router.delete("/{user_id}/documents/{doc_id}")
async def delete_document(
    user_id: int, 
    doc_id: int, 
    current_user: dict = Depends(verify_token)
):
    """Delete document (dummy for Phase 2)"""
    return {
        "message": f"Document {doc_id} deleted for user {user_id}",
        "status": "placeholder"
    }
