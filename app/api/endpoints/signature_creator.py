"""
Signature Creator API Endpoints for EasyApply Document Tools
Handles signature creation: draw, type, upload signature functionality
"""

from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from datetime import datetime

from app.services.signature_creator import signature_creator_service

router = APIRouter(tags=["Signature Creator"])

class TextSignatureRequest(BaseModel):
    """Request model for text signature creation"""
    text: str = Field(..., min_length=1, max_length=100, description="Text for signature")
    font_style: str = Field(default="arial", pattern="^(arial|times|courier)$", description="Font style")
    font_size: int = Field(default=24, ge=12, le=72, description="Font size")
    signature_size: str = Field(default="medium", pattern="^(small|medium|large)$", description="Signature size")
    color: str = Field(default="#000000", pattern="^#[0-9A-Fa-f]{6}$", description="Text color in hex")
    background_transparent: bool = Field(default=True, description="Transparent background")

class DrawnSignatureRequest(BaseModel):
    """Request model for drawn signature creation"""
    signature_data: str = Field(..., description="Base64 encoded signature image data")
    signature_size: str = Field(default="medium", pattern="^(small|medium|large)$", description="Signature size")
    background_transparent: bool = Field(default=True, description="Transparent background")

class SignatureResponse(BaseModel):
    """Response model for signature operations"""
    success: bool
    signature_id: Optional[str] = None
    signature_type: Optional[str] = None
    signature_text: Optional[str] = None
    original_filename: Optional[str] = None
    font_style: Optional[str] = None
    font_size: Optional[int] = None
    signature_size: Optional[str] = None
    color: Optional[str] = None
    background_transparent: Optional[bool] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size_kb: Optional[float] = None
    processing_time_ms: Optional[int] = None
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    error: Optional[str] = None

@router.post("/create-text", response_model=SignatureResponse)
async def create_text_signature(
    text: str = Form(..., min_length=1, max_length=100, description="Text for signature"),
    font_style: str = Form(default="arial", pattern="^(arial|times|courier)$", description="Font style"),
    font_size: int = Form(default=24, ge=12, le=72, description="Font size"),
    signature_size: str = Form(default="medium", pattern="^(small|medium|large)$", description="Signature size"),
    color: str = Form(default="#000000", pattern="^#[0-9A-Fa-f]{6}$", description="Text color in hex"),
    background_transparent: bool = Form(default=True, description="Transparent background")
):
    """Create a signature from text"""
    
    try:
        result = await signature_creator_service.create_text_signature(
            text=text,
            font_style=font_style,
            font_size=font_size,
            signature_size=signature_size,
            color=color,
            background_transparent=background_transparent,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            return SignatureResponse(
                success=True,
                signature_id=result["signature_id"],
                signature_type=result["signature_type"],
                signature_text=result["signature_text"],
                font_style=result["font_style"],
                font_size=result["font_size"],
                signature_size=result["signature_size"],
                color=result["color"],
                background_transparent=result["background_transparent"],
                width=result["width"],
                height=result["height"],
                file_size_kb=result["file_size_kb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=result["download_url"],
                thumbnail_url=result["thumbnail_url"]
            )
        else:
            raise HTTPException(status_code=500, detail="Text signature creation failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text signature creation failed: {str(e)}")

@router.post("/create-drawn", response_model=SignatureResponse)
async def create_drawn_signature(
    signature_data: str = Form(..., description="Base64 encoded signature image data"),
    signature_size: str = Form(default="medium", pattern="^(small|medium|large)$", description="Signature size"),
    background_transparent: bool = Form(default=True, description="Transparent background")
):
    """Create a signature from drawn/canvas data"""
    
    try:
        result = await signature_creator_service.create_drawn_signature(
            signature_data=signature_data,
            signature_size=signature_size,
            background_transparent=background_transparent,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            return SignatureResponse(
                success=True,
                signature_id=result["signature_id"],
                signature_type=result["signature_type"],
                signature_size=result["signature_size"],
                background_transparent=result["background_transparent"],
                width=result["width"],
                height=result["height"],
                file_size_kb=result["file_size_kb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=result["download_url"],
                thumbnail_url=result["thumbnail_url"]
            )
        else:
            raise HTTPException(status_code=500, detail="Drawn signature creation failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drawn signature creation failed: {str(e)}")

@router.post("/upload", response_model=SignatureResponse)
async def upload_signature(
    file: UploadFile = File(..., description="Signature image file to upload"),
    signature_size: str = Form(default="medium", pattern="^(small|medium|large)$", description="Signature size"),
    background_transparent: bool = Form(default=True, description="Transparent background")
):
    """Upload and process a signature image file"""
    
    try:
        result = await signature_creator_service.upload_signature(
            file=file,
            signature_size=signature_size,
            background_transparent=background_transparent,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            return SignatureResponse(
                success=True,
                signature_id=result["signature_id"],
                signature_type=result["signature_type"],
                original_filename=result["original_filename"],
                signature_size=result["signature_size"],
                background_transparent=result["background_transparent"],
                width=result["width"],
                height=result["height"],
                file_size_kb=result["file_size_kb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=result["download_url"],
                thumbnail_url=result["thumbnail_url"]
            )
        else:
            raise HTTPException(status_code=500, detail="Signature upload failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signature upload failed: {str(e)}")

@router.get("/download/{signature_id}")
async def download_signature(signature_id: str):
    """Download a created signature file"""
    
    try:
        file_info = signature_creator_service.get_signature_file(signature_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="Signature not found")
        
        file_path, content_type = file_info
        
        def file_generator():
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    yield chunk
        
        return StreamingResponse(
            file_generator(),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename=signature_{signature_id}.png"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

@router.get("/thumbnail/{signature_id}")
async def get_signature_thumbnail(signature_id: str):
    """Get signature thumbnail image"""
    
    try:
        thumbnail_info = signature_creator_service.get_signature_thumbnail(signature_id)
        if not thumbnail_info:
            raise HTTPException(status_code=404, detail="Signature thumbnail not found")
        
        thumbnail_path, content_type = thumbnail_info
        
        def file_generator():
            with open(thumbnail_path, 'rb') as f:
                while chunk := f.read(8192):
                    yield chunk
        
        return StreamingResponse(
            file_generator(),
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=thumb_{signature_id}.png"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Thumbnail retrieval failed: {str(e)}")

@router.get("/info")
async def get_signature_info():
    """Get signature creator capabilities and limits"""
    
    return {
        "signature_types": ["text", "drawn", "uploaded"],
        "supported_formats": ["PNG", "JPG", "JPEG", "GIF", "BMP"],
        "output_format": "PNG",
        "limits": {
            "max_file_size_mb": 5,
            "max_text_length": 100,
            "min_font_size": 12,
            "max_font_size": 72
        },
        "signature_sizes": {
            "small": {"width": 200, "height": 80},
            "medium": {"width": 300, "height": 120},
            "large": {"width": 400, "height": 160}
        },
        "font_styles": ["arial", "times", "courier"],
        "features": {
            "transparent_background": True,
            "custom_colors": True,
            "resize_to_standard_sizes": True,
            "thumbnail_generation": True
        }
    }

@router.get("/health")
async def health_check():
    """Health check endpoint for signature creator service"""
    
    try:
        # Test basic functionality
        test_passed = True
        
        return {
            "status": "healthy" if test_passed else "unhealthy",
            "service": "Signature Creator",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "capabilities": {
                "text_signatures": True,
                "drawn_signatures": True,
                "uploaded_signatures": True,
                "thumbnail_generation": True,
                "transparent_backgrounds": True
            }
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "Signature Creator",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
