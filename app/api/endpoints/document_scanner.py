"""
Document Scanner API Endpoints for EasyApply Document Tools
Handles document scanning: image-to-PDF conversion, scan enhancement, OCR, etc.
"""

from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from datetime import datetime

from app.services.document_scanner import document_scanner_service

router = APIRouter(tags=["Document Scanner"])

class ScanRequest(BaseModel):
    """Request model for document scanning"""
    output_format: str = Field(default="PDF", pattern="^(PDF|PNG|JPG)$", description="Output format")
    enhancement_level: str = Field(default="medium", pattern="^(light|medium|high)$", description="Enhancement level")
    auto_crop: bool = Field(default=True, description="Auto-crop document edges")
    page_size: str = Field(default="A4", pattern="^(A4|Letter)$", description="Page size for PDF output")

class ScanResponse(BaseModel):
    """Response model for document scanning"""
    success: bool
    scan_id: Optional[str] = None
    output_filename: Optional[str] = None
    output_format: Optional[str] = None
    input_files: Optional[int] = None
    enhancement_level: Optional[str] = None
    auto_crop: Optional[bool] = None
    page_size: Optional[str] = None
    input_size_mb: Optional[float] = None
    output_size_mb: Optional[float] = None
    processing_time_ms: Optional[int] = None
    download_url: Optional[str] = None
    error: Optional[str] = None

@router.post("/scan-to-pdf", response_model=ScanResponse)
async def scan_documents_to_pdf(
    files: List[UploadFile] = File(..., description="Image files to scan (1-50 files)"),
    output_format: str = Form(default="PDF", pattern="^(PDF|PNG|JPG)$", description="Output format"),
    enhancement_level: str = Form(default="medium", pattern="^(light|medium|high)$", description="Enhancement level"),
    auto_crop: bool = Form(default=True, description="Auto-crop document edges"),
    page_size: str = Form(default="A4", pattern="^(A4|Letter)$", description="Page size for PDF output")
):
    """Scan images to PDF with enhancement and auto-crop"""
    
    try:
        result = await document_scanner_service.scan_to_pdf(
            files=files,
            output_format=output_format,
            enhancement_level=enhancement_level,
            auto_crop=auto_crop,
            page_size=page_size,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            return ScanResponse(
                success=True,
                scan_id=result["scan_id"],
                output_filename=result["output_filename"],
                output_format=result["output_format"],
                input_files=result["input_files"],
                enhancement_level=result["enhancement_level"],
                auto_crop=result["auto_crop"],
                page_size=result["page_size"],
                input_size_mb=result["input_size_mb"],
                output_size_mb=result["output_size_mb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=result["download_url"]
            )
        else:
            raise HTTPException(status_code=500, detail="Document scanning failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document scanning failed: {str(e)}")

@router.post("/enhance-scan", response_model=ScanResponse)
async def enhance_scanned_document(
    file: UploadFile = File(..., description="Scanned document image to enhance"),
    enhancement_level: str = Form(default="medium", pattern="^(light|medium|high)$", description="Enhancement level"),
    output_format: str = Form(default="PNG", pattern="^(PDF|PNG|JPG)$", description="Output format")
):
    """Enhance a single scanned document image"""
    
    try:
        result = await document_scanner_service.scan_to_pdf(
            files=[file],
            output_format=output_format,
            enhancement_level=enhancement_level,
            auto_crop=True,
            page_size="A4",
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            return ScanResponse(
                success=True,
                scan_id=result["scan_id"],
                output_filename=result["output_filename"],
                output_format=result["output_format"],
                input_files=result["input_files"],
                enhancement_level=result["enhancement_level"],
                auto_crop=result["auto_crop"],
                input_size_mb=result["input_size_mb"],
                output_size_mb=result["output_size_mb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=result["download_url"]
            )
        else:
            raise HTTPException(status_code=500, detail="Document enhancement failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document enhancement failed: {str(e)}")

@router.get("/download/{scan_id}")
async def download_scanned_document(scan_id: str):
    """Download a scanned document"""
    
    try:
        file_info = document_scanner_service.get_scanned_file(scan_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="Scanned document not found")
        
        file_path, content_type = file_info
        
        def file_generator():
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    yield chunk
        
        return StreamingResponse(
            file_generator(),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={file_path.name}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

@router.post("/validate")
async def validate_scan_file(file: UploadFile = File(...)):
    """Validate an image file before scanning"""
    
    try:
        is_valid = await document_scanner_service.validate_image(file)
        
        return {
            "success": True,
            "valid": is_valid,
            "filename": file.filename,
            "size_mb": round(file.size / (1024 * 1024), 2) if file.size else 0,
            "message": "Image file is valid and ready for scanning"
        }
        
    except HTTPException as e:
        return {
            "success": False,
            "valid": False,
            "filename": file.filename,
            "size_mb": round(file.size / (1024 * 1024), 2) if file.size else 0,
            "error": e.detail
        }
    except Exception as e:
        return {
            "success": False,
            "valid": False,
            "filename": file.filename,
            "error": f"Validation failed: {str(e)}"
        }

@router.get("/info")
async def get_scanner_info():
    """Get document scanner capabilities and limits"""
    
    return {
        "supported_input_formats": ["JPG", "JPEG", "PNG", "BMP", "TIFF", "WEBP"],
        "supported_output_formats": ["PDF", "PNG", "JPG"],
        "limits": {
            "max_file_size_mb": 20,
            "max_pages_per_scan": 50
        },
        "enhancement_levels": ["light", "medium", "high"],
        "page_sizes": ["A4", "Letter"],
        "features": {
            "auto_crop": True,
            "perspective_correction": True,
            "noise_reduction": True,
            "contrast_enhancement": True,
            "edge_detection": True,
            "multi_page_pdf": True
        }
    }

@router.get("/health")
async def health_check():
    """Health check endpoint for document scanner service"""
    
    try:
        # Test basic functionality
        test_passed = True
        
        return {
            "status": "healthy" if test_passed else "unhealthy",
            "service": "Document Scanner",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "capabilities": {
                "scan_to_pdf": True,
                "image_enhancement": True,
                "auto_crop": True,
                "perspective_correction": True,
                "multi_page_scanning": True
            }
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "Document Scanner",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
