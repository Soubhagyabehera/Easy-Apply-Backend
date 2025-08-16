"""
Document Manager API Endpoints for EasyApply
Handles secure storage and automatic formatting of user documents for job applications
"""

import os
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from datetime import datetime
from app.services.document_manager import DocumentManagerService

router = APIRouter(tags=["Document Manager"])
security = HTTPBearer()

# Initialize the document manager service
document_manager_service = DocumentManagerService()

# Pydantic Models
class DocumentUploadResponse(BaseModel):
    """Response model for document upload"""
    success: bool
    document_id: str
    document_type: str
    original_filename: str
    file_size_bytes: int
    file_format: str
    upload_date: str
    message: str

class UserDocument(BaseModel):
    """Model for user document information"""
    document_id: str
    document_type: str
    original_filename: str
    file_size_bytes: int
    file_format: str
    upload_date: str
    is_active: bool

class DocumentListResponse(BaseModel):
    """Response model for user documents list"""
    success: bool
    user_id: str
    total_documents: int
    documents: List[UserDocument]

class JobDocumentBundle(BaseModel):
    """Response model for job-specific document bundle"""
    success: bool
    job_id: str
    batch_id: str
    total_documents: int
    formatted_documents: List[Dict[str, Any]]
    bundle_download_url: str
    processing_date: str

class DocumentTypesResponse(BaseModel):
    """Response model for available document types"""
    success: bool
    categories: Dict[str, List[str]]
    total_types: int

# Helper function to extract user ID from JWT token
async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Extract user ID from JWT token"""
    # TODO: Implement proper JWT token validation
    # For now, return a mock user ID for testing
    token = credentials.credentials
    if token == "demo_token":
        return "demo_user_123"
    
    # In production, validate JWT and extract user_id
    # jwt_payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    # return jwt_payload.get("user_id")
    
    return "demo_user_123"  # Mock for development

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    document_type: str = Form(..., description="Type of document (e.g., 'resume', 'photo', 'certificate_10th')"),
    file: UploadFile = File(..., description="Document file to upload"),
    user_id: str = Depends(get_current_user_id)
):
    """Upload a user document"""
    
    try:
        result = await document_manager_service.upload_user_document(
            user_id=user_id,
            file=file,
            document_type=document_type
        )
        
        return DocumentUploadResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document upload failed: {str(e)}")

@router.get("/documents", response_model=DocumentListResponse)
async def get_user_documents(
    user_id: str = Depends(get_current_user_id)
):
    """Get all documents for the authenticated user"""
    
    try:
        documents = await document_manager_service.get_user_documents(user_id)
        
        return DocumentListResponse(
            success=True,
            user_id=user_id,
            total_documents=len(documents),
            documents=[UserDocument(**doc) for doc in documents]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve documents: {str(e)}")

@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Delete a user document"""
    
    try:
        result = await document_manager_service.delete_user_document(user_id, document_id)
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document deletion failed: {str(e)}")

@router.post("/format-for-job/{job_id}", response_model=JobDocumentBundle)
async def format_documents_for_job(
    job_id: str,
    job_requirements: Optional[Dict[str, Any]] = None,
    user_id: str = Depends(get_current_user_id)
):
    """Format user documents according to job requirements"""
    
    try:
        result = await document_manager_service.format_documents_for_job(
            user_id=user_id,
            job_id=job_id,
            job_requirements=job_requirements
        )
        
        return JobDocumentBundle(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document formatting failed: {str(e)}")

@router.get("/download-bundle/{batch_id}")
async def download_document_bundle(
    batch_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Download formatted document bundle as ZIP"""
    
    try:
        zip_path, content_type = document_manager_service.get_document_bundle(batch_id)
        
        def file_generator():
            with open(zip_path, 'rb') as f:
                while chunk := f.read(8192):
                    yield chunk
        
        return StreamingResponse(
            file_generator(),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename=job_documents_{batch_id}.zip"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bundle download failed: {str(e)}")

@router.get("/document-types", response_model=DocumentTypesResponse)
async def get_document_types():
    """Get available document types and categories"""
    
    try:
        categories = {
            'personal': ['resume', 'photo', 'signature'],
            'educational': ['certificate_10th', 'certificate_12th', 'certificate_graduation', 'certificate_post_graduation'],
            'identity': ['aadhaar', 'pan', 'voter_id', 'passport'],
            'other': ['caste_certificate', 'domicile_certificate', 'income_certificate', 'disability_certificate'],
            'experience': ['experience_certificate', 'relieving_letter']
        }
        
        total_types = sum(len(types) for types in categories.values())
        
        return DocumentTypesResponse(
            success=True,
            categories=categories,
            total_types=total_types
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get document types: {str(e)}")

@router.get("/job-requirements/{job_id}")
async def get_job_document_requirements(job_id: str):
    """Get document requirements for a specific job"""
    
    try:
        # TODO: Implement job-specific requirements lookup
        # For now, return default requirements
        default_requirements = {
            'photo': {
                'required': True,
                'required_format': 'jpg',
                'max_width_px': 300,
                'max_height_px': 400,
                'min_width_px': 200,
                'min_height_px': 250,
                'max_size_kb': 100,
                'naming_convention': 'passport_photo'
            },
            'signature': {
                'required': True,
                'required_format': 'jpg',
                'max_width_px': 200,
                'max_height_px': 100,
                'max_size_kb': 50,
                'naming_convention': 'signature'
            },
            'resume': {
                'required': True,
                'required_format': 'pdf',
                'max_size_kb': 2048,
                'naming_convention': 'resume'
            },
            'certificate_10th': {
                'required': True,
                'required_format': 'pdf',
                'max_size_kb': 1024,
                'naming_convention': 'class_10_certificate'
            },
            'certificate_12th': {
                'required': True,
                'required_format': 'pdf',
                'max_size_kb': 1024,
                'naming_convention': 'class_12_certificate'
            },
            'aadhaar': {
                'required': True,
                'required_format': 'pdf',
                'max_size_kb': 512,
                'naming_convention': 'aadhaar_card'
            },
            'pan': {
                'required': True,
                'required_format': 'pdf',
                'max_size_kb': 512,
                'naming_convention': 'pan_card'
            }
        }
        
        return {
            'success': True,
            'job_id': job_id,
            'requirements': default_requirements,
            'total_required_documents': len([req for req in default_requirements.values() if req.get('required', False)])
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job requirements: {str(e)}")

@router.get("/health")
async def health_check():
    """Health check endpoint for document manager service"""
    
    return {
        'success': True,
        'service': 'Document Manager',
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'features': [
            'document_upload',
            'document_storage',
            'job_formatting',
            'bundle_download',
            'user_authentication'
        ]
    }

@router.get("/download/{document_id}")
async def download_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Download a specific document"""
    
    try:
        # Get user documents to verify ownership
        documents = await document_manager_service.get_user_documents(user_id)
        document = next((doc for doc in documents if doc['document_id'] == document_id), None)
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get the file path
        file_path = document.get('file_path')
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Document file not found")
        
        # Return the file
        return FileResponse(
            path=file_path,
            filename=document.get('original_filename', 'document'),
            media_type='application/octet-stream'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download document: {str(e)}")

@router.get("/stats")
async def get_service_stats(
    user_id: str = Depends(get_current_user_id)
):
    """Get document manager statistics for user"""
    
    try:
        documents = await document_manager_service.get_user_documents(user_id)
        
        # Calculate statistics
        total_documents = len(documents)
        total_size_bytes = sum(doc.get('file_size_bytes', 0) for doc in documents)
        
        # Calculate status breakdown
        verified_documents = sum(1 for doc in documents if doc.get('is_active', False))
        pending_documents = 0  # For now, all uploaded docs are either active or inactive
        rejected_documents = sum(1 for doc in documents if not doc.get('is_active', True))
        
        # Group by category
        category_counts = {}
        for doc in documents:
            doc_type = doc['document_type']
            # Find category for this document type
            for category, types in document_manager_service.document_categories.items():
                if doc_type in types:
                    category_counts[category] = category_counts.get(category, 0) + 1
                    break
        
        return {
            'success': True,
            'user_id': user_id,
            'total_documents': total_documents,
            'verified_documents': verified_documents,
            'pending_documents': pending_documents,
            'rejected_documents': rejected_documents,
            'total_size_mb': round(total_size_bytes / (1024 * 1024), 2),
            'category_breakdown': category_counts,
            'last_updated': datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")
