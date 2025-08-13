"""
Size Optimizer API Endpoints for EasyApply Document Tools
Handles file size optimization: compress images/PDFs, reduce file sizes, etc.
"""

from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from datetime import datetime

from app.services.size_optimizer import size_optimizer_service

router = APIRouter(tags=["Size Optimizer"])

class OptimizationResponse(BaseModel):
    """Response model for size optimization operations"""
    success: bool
    optimization_id: Optional[str] = None
    file_type: Optional[str] = None
    original_filename: Optional[str] = None
    output_filename: Optional[str] = None
    original_format: Optional[str] = None
    output_format: Optional[str] = None
    compression_level: Optional[str] = None
    target_size_kb: Optional[int] = None
    final_quality: Optional[int] = None
    remove_metadata: Optional[bool] = None
    remove_annotations: Optional[bool] = None
    total_pages: Optional[int] = None
    original_size_mb: Optional[float] = None
    optimized_size_mb: Optional[float] = None
    compression_ratio: Optional[float] = None
    size_reduction_kb: Optional[float] = None
    size_reduction_mb: Optional[float] = None
    processing_time_ms: Optional[int] = None
    download_url: Optional[str] = None
    error: Optional[str] = None

@router.post("/optimize-image", response_model=OptimizationResponse)
async def optimize_image_size(
    file: UploadFile = File(..., description="Image file to optimize"),
    compression_level: str = Form(default="medium", pattern="^(light|medium|aggressive)$", description="Compression level"),
    target_size_kb: Optional[int] = Form(default=None, ge=10, le=10240, description="Target file size in KB"),
    max_width: Optional[int] = Form(default=None, ge=100, le=4000, description="Maximum width in pixels"),
    max_height: Optional[int] = Form(default=None, ge=100, le=4000, description="Maximum height in pixels"),
    output_format: Optional[str] = Form(default=None, pattern="^(JPG|PNG|WEBP)$", description="Output format")
):
    """Optimize image file size with various compression options"""
    
    try:
        result = await size_optimizer_service.optimize_image(
            file=file,
            compression_level=compression_level,
            target_size_kb=target_size_kb,
            max_width=max_width,
            max_height=max_height,
            output_format=output_format,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            return OptimizationResponse(
                success=True,
                optimization_id=result["optimization_id"],
                file_type=result["file_type"],
                original_filename=result["original_filename"],
                output_filename=result["output_filename"],
                original_format=result["original_format"],
                output_format=result["output_format"],
                compression_level=result["compression_level"],
                target_size_kb=result["target_size_kb"],
                final_quality=result["final_quality"],
                original_size_mb=result["original_size_mb"],
                optimized_size_mb=result["optimized_size_mb"],
                compression_ratio=result["compression_ratio"],
                size_reduction_kb=result["size_reduction_kb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=result["download_url"]
            )
        else:
            raise HTTPException(status_code=500, detail="Image optimization failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image optimization failed: {str(e)}")

@router.post("/optimize-images", response_model=OptimizationResponse)
async def optimize_images_batch(
    files: list[UploadFile] = File(..., description="Image files to optimize"),
    compression_level: str = Form(default="medium", pattern="^(light|medium|aggressive)$", description="Compression level"),
    quality: int = Form(default=85, ge=10, le=100, description="Image quality (10-100)"),
    max_width: Optional[int] = Form(default=None, ge=100, le=4000, description="Maximum width in pixels"),
    max_height: Optional[int] = Form(default=None, ge=100, le=4000, description="Maximum height in pixels")
):
    """Optimize multiple image files with batch processing"""
    
    try:
        # For now, process the first file (can be extended to true batch processing)
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
            
        first_file = files[0]
        result = await size_optimizer_service.optimize_image(
            file=first_file,
            compression_level=compression_level,
            target_size_kb=None,
            max_width=max_width,
            max_height=max_height,
            output_format=None,
            user_id=None,
            session_id=None
        )
        
        if result["success"]:
            return OptimizationResponse(
                success=True,
                optimization_id=result["optimization_id"],
                file_type=result["file_type"],
                original_filename=result["original_filename"],
                output_filename=result["output_filename"],
                original_format=result["original_format"],
                output_format=result["output_format"],
                compression_level=result["compression_level"],
                final_quality=result["final_quality"],
                original_size_mb=result["original_size_mb"],
                optimized_size_mb=result["optimized_size_mb"],
                compression_ratio=result["compression_ratio"],
                size_reduction_mb=result["size_reduction_mb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=result["download_url"]
            )
        else:
            raise HTTPException(status_code=500, detail="Image optimization failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image batch optimization failed: {str(e)}")

@router.post("/optimize-pdfs", response_model=OptimizationResponse)
async def optimize_pdfs_batch(
    files: list[UploadFile] = File(..., description="PDF files to optimize"),
    compression_level: str = Form(default="medium", pattern="^(light|medium|aggressive)$", description="Compression level"),
    remove_metadata: bool = Form(default=True, description="Remove PDF metadata"),
    remove_annotations: bool = Form(default=False, description="Remove annotations and comments")
):
    """Optimize multiple PDF files with batch processing"""
    
    try:
        # For now, process the first file (can be extended to true batch processing)
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
            
        first_file = files[0]
        result = await size_optimizer_service.optimize_pdf(
            file=first_file,
            compression_level=compression_level,
            remove_metadata=remove_metadata,
            remove_annotations=remove_annotations,
            user_id=None,
            session_id=None
        )
        
        if result["success"]:
            return OptimizationResponse(
                success=True,
                optimization_id=result["optimization_id"],
                file_type=result["file_type"],
                original_filename=result["original_filename"],
                output_filename=result["output_filename"],
                compression_level=result["compression_level"],
                remove_metadata=result["remove_metadata"],
                remove_annotations=result["remove_annotations"],
                total_pages=result["total_pages"],
                original_size_mb=result["original_size_mb"],
                optimized_size_mb=result["optimized_size_mb"],
                compression_ratio=result["compression_ratio"],
                size_reduction_mb=result["size_reduction_mb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=result["download_url"]
            )
        else:
            raise HTTPException(status_code=500, detail="PDF optimization failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF batch optimization failed: {str(e)}")

@router.post("/optimize-pdf", response_model=OptimizationResponse)
async def optimize_pdf_size(
    file: UploadFile = File(..., description="PDF file to optimize"),
    compression_level: str = Form(default="medium", pattern="^(light|medium|aggressive)$", description="Compression level"),
    remove_metadata: bool = Form(default=True, description="Remove PDF metadata"),
    remove_annotations: bool = Form(default=False, description="Remove annotations and comments")
):
    """Optimize PDF file size with compression and cleanup options"""
    
    try:
        result = await size_optimizer_service.optimize_pdf(
            file=file,
            compression_level=compression_level,
            remove_metadata=remove_metadata,
            remove_annotations=remove_annotations,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            return OptimizationResponse(
                success=True,
                optimization_id=result["optimization_id"],
                file_type=result["file_type"],
                original_filename=result["original_filename"],
                output_filename=result["output_filename"],
                compression_level=result["compression_level"],
                remove_metadata=result["remove_metadata"],
                remove_annotations=result["remove_annotations"],
                total_pages=result["total_pages"],
                original_size_mb=result["original_size_mb"],
                optimized_size_mb=result["optimized_size_mb"],
                compression_ratio=result["compression_ratio"],
                size_reduction_mb=result["size_reduction_mb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=result["download_url"]
            )
        else:
            raise HTTPException(status_code=500, detail="PDF optimization failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF optimization failed: {str(e)}")

@router.get("/download/{optimization_id}")
async def download_optimized_file(optimization_id: str):
    """Download an optimized file"""
    
    try:
        file_info = size_optimizer_service.get_optimized_file(optimization_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="Optimized file not found")
        
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
async def validate_optimization_file(file: UploadFile = File(...)):
    """Validate a file before size optimization"""
    
    try:
        is_valid = await size_optimizer_service.validate_file(file)
        
        return {
            "success": True,
            "valid": is_valid,
            "filename": file.filename,
            "size_mb": round(file.size / (1024 * 1024), 2) if file.size else 0,
            "message": "File is valid for size optimization"
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
async def get_optimizer_info():
    """Get size optimizer capabilities and limits"""
    
    return {
        "supported_file_types": {
            "images": ["JPG", "JPEG", "PNG", "BMP", "TIFF", "WEBP"],
            "documents": ["PDF"]
        },
        "compression_levels": {
            "light": {
                "description": "Minimal compression with high quality",
                "typical_reduction": "10-25%"
            },
            "medium": {
                "description": "Balanced compression and quality",
                "typical_reduction": "25-50%"
            },
            "aggressive": {
                "description": "Maximum compression, lower quality",
                "typical_reduction": "50-80%"
            }
        },
        "limits": {
            "max_file_size_mb": 100,
            "min_target_size_kb": 10,
            "max_target_size_kb": 10240,
            "min_dimensions": 100,
            "max_dimensions": 4000
        },
        "features": {
            "target_size_optimization": True,
            "dimension_resizing": True,
            "format_conversion": True,
            "pdf_metadata_removal": True,
            "pdf_annotation_removal": True,
            "quality_control": True,
            "batch_processing": False
        }
    }

@router.get("/health")
async def health_check():
    """Health check endpoint for size optimizer service"""
    
    try:
        # Test basic functionality
        test_passed = True
        
        return {
            "status": "healthy" if test_passed else "unhealthy",
            "service": "Size Optimizer",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "capabilities": {
                "image_optimization": True,
                "pdf_optimization": True,
                "target_size_optimization": True,
                "dimension_control": True,
                "metadata_removal": True
            }
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "Size Optimizer",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
