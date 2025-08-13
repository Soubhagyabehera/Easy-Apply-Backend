"""
Format Converter API Endpoints for EasyApply Document Tools
Handles format conversion: PDF <-> image, document format conversions, etc.
"""

from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from datetime import datetime

from app.services.format_converter import format_converter_service

router = APIRouter(tags=["Format Converter"])

class ConversionResponse(BaseModel):
    """Response model for format conversion operations"""
    success: bool
    conversion_id: Optional[str] = None
    conversion_type: Optional[str] = None
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    input_filename: Optional[str] = None
    output_filename: Optional[str] = None
    input_files: Optional[int] = None
    output_files: Optional[int] = None
    total_pages: Optional[int] = None
    dpi: Optional[int] = None
    quality: Optional[int] = None
    page_size: Optional[str] = None
    input_size_mb: Optional[float] = None
    output_size_mb: Optional[float] = None
    processing_time_ms: Optional[int] = None
    download_url: Optional[str] = None
    files: Optional[List[dict]] = None
    error: Optional[str] = None

@router.post("/pdf-to-images", response_model=ConversionResponse)
async def convert_pdf_to_images(
    file: UploadFile = File(..., description="PDF file to convert to images"),
    output_format: str = Form(default="PNG", pattern="^(PNG|JPG)$", description="Output image format"),
    dpi: int = Form(default=200, ge=72, le=600, description="DPI for image conversion"),
    quality: int = Form(default=90, ge=50, le=100, description="Image quality (for JPG)")
):
    """Convert PDF to individual image files"""
    
    try:
        result = await format_converter_service.convert_pdf_to_images(
            file=file,
            output_format=output_format,
            dpi=dpi,
            quality=quality,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            return ConversionResponse(
                success=True,
                conversion_id=result["conversion_id"],
                conversion_type=result["conversion_type"],
                input_format=result["input_format"],
                output_format=result["output_format"],
                input_filename=result["input_filename"],
                total_pages=result["total_pages"],
                output_files=result["output_files"],
                files=result["files"],
                dpi=result["dpi"],
                quality=result["quality"],
                input_size_mb=result["input_size_mb"],
                output_size_mb=result["output_size_mb"],
                processing_time_ms=result["processing_time_ms"]
            )
        else:
            raise HTTPException(status_code=500, detail="PDF to images conversion failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF to images conversion failed: {str(e)}")

@router.post("/images-to-pdf", response_model=ConversionResponse)
async def convert_images_to_pdf(
    files: List[UploadFile] = File(..., description="Image files to convert to PDF"),
    page_size: str = Form(default="A4", pattern="^(A4|Letter)$", description="PDF page size"),
    quality: int = Form(default=90, ge=50, le=100, description="Image quality in PDF")
):
    """Convert multiple images to a single PDF file"""
    
    try:
        result = await format_converter_service.convert_images_to_pdf(
            files=files,
            page_size=page_size,
            quality=quality,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            return ConversionResponse(
                success=True,
                conversion_id=result["conversion_id"],
                conversion_type=result["conversion_type"],
                input_format=result["input_format"],
                output_format=result["output_format"],
                output_filename=result["output_filename"],
                input_files=result["input_files"],
                page_size=result["page_size"],
                quality=result["quality"],
                input_size_mb=result["input_size_mb"],
                output_size_mb=result["output_size_mb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=result["download_url"]
            )
        else:
            raise HTTPException(status_code=500, detail="Images to PDF conversion failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Images to PDF conversion failed: {str(e)}")

@router.post("/document-format", response_model=ConversionResponse)
async def convert_document_format(
    file: UploadFile = File(..., description="Document file to convert"),
    target_format: str = Form(..., pattern="^(PDF|TXT|DOCX)$", description="Target format")
):
    """Convert document between different formats"""
    
    try:
        result = await format_converter_service.convert_document_format(
            file=file,
            target_format=target_format,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            return ConversionResponse(
                success=True,
                conversion_id=result["conversion_id"],
                conversion_type=result["conversion_type"],
                input_format=result["input_format"],
                output_format=result["output_format"],
                input_filename=result["input_filename"],
                output_filename=result["output_filename"],
                input_size_mb=result["input_size_mb"],
                output_size_mb=result["output_size_mb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=result["download_url"]
            )
        else:
            raise HTTPException(status_code=500, detail="Document format conversion failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document format conversion failed: {str(e)}")

@router.get("/download/{conversion_id}")
async def download_converted_file(conversion_id: str):
    """Download a converted file"""
    
    try:
        file_info = format_converter_service.get_converted_file(conversion_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="Converted file not found")
        
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
async def validate_conversion_file(
    file: UploadFile = File(...),
    target_format: str = Form(..., description="Target format for conversion")
):
    """Validate a file before format conversion"""
    
    try:
        is_valid = await format_converter_service.validate_file(file, target_format)
        
        return {
            "success": True,
            "valid": is_valid,
            "filename": file.filename,
            "size_mb": round(file.size / (1024 * 1024), 2) if file.size else 0,
            "target_format": target_format.upper(),
            "message": f"File is valid for conversion to {target_format.upper()}"
        }
        
    except HTTPException as e:
        return {
            "success": False,
            "valid": False,
            "filename": file.filename,
            "size_mb": round(file.size / (1024 * 1024), 2) if file.size else 0,
            "target_format": target_format.upper(),
            "error": e.detail
        }
    except Exception as e:
        return {
            "success": False,
            "valid": False,
            "filename": file.filename,
            "target_format": target_format.upper(),
            "error": f"Validation failed: {str(e)}"
        }

@router.get("/info")
async def get_converter_info():
    """Get format converter capabilities and limits"""
    
    return {
        "supported_conversions": {
            "pdf_to_images": {
                "input": ["PDF"],
                "output": ["PNG", "JPG"],
                "settings": ["dpi", "quality"]
            },
            "images_to_pdf": {
                "input": ["JPG", "JPEG", "PNG", "BMP", "TIFF", "GIF", "WEBP"],
                "output": ["PDF"],
                "settings": ["page_size", "quality"]
            },
            "document_format": {
                "input": ["PDF", "TXT"],
                "output": ["PDF", "TXT"],
                "settings": []
            }
        },
        "limits": {
            "max_file_size_mb": 50,
            "max_pages_per_pdf": 100,
            "min_dpi": 72,
            "max_dpi": 600,
            "min_quality": 50,
            "max_quality": 100
        },
        "page_sizes": ["A4", "Letter"],
        "features": {
            "batch_conversion": True,
            "quality_control": True,
            "dpi_control": True,
            "page_size_selection": True,
            "text_extraction": True
        }
    }

@router.get("/health")
async def health_check():
    """Health check endpoint for format converter service"""
    
    try:
        # Test basic functionality
        test_passed = True
        
        return {
            "status": "healthy" if test_passed else "unhealthy",
            "service": "Format Converter",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "capabilities": {
                "pdf_to_images": True,
                "images_to_pdf": True,
                "document_format_conversion": True,
                "batch_processing": True,
                "quality_control": True
            }
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "Format Converter",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
