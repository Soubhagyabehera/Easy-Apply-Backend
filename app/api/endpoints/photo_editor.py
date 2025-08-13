"""
Photo Editor API Endpoints for EasyApply Document Tools
Handles image processing, resizing, format conversion, and background changes.
"""

from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import io
import zipfile
from datetime import datetime

from app.services.photo_editor import photo_editor_service

router = APIRouter(tags=["Photo Editor"])

class ProcessImageRequest(BaseModel):
    """Request model for image processing parameters"""
    width: int = Field(default=200, ge=50, le=4000, description="Output width in pixels")
    height: int = Field(default=200, ge=50, le=4000, description="Output height in pixels")
    output_format: str = Field(default="JPG", pattern="^(JPG|PNG|PDF)$", description="Output format")
    background_color: Optional[str] = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$", description="Background color in hex format")
    maintain_aspect_ratio: bool = Field(default=False, description="Maintain original aspect ratio")
    max_file_size_kb: Optional[int] = Field(default=None, ge=50, le=2048, description="Maximum output file size in KB")

class ProcessImageResponse(BaseModel):
    """Response model for processed image"""
    success: bool
    original_filename: str
    processed_filename: str
    original_dimensions: str
    new_dimensions: str
    original_size_kb: int
    processed_size_kb: int
    format: str
    download_url: str
    thumbnail_url: Optional[str] = None
    error: Optional[str] = None

class BatchProcessResponse(BaseModel):
    """Response model for batch processing"""
    total_files: int
    successful: int
    failed: int
    results: List[ProcessImageResponse]
    download_all_url: Optional[str] = None

@router.post("/process-single", response_model=ProcessImageResponse)
async def process_single_image(
    file: UploadFile = File(..., description="Image file to process"),
    width: int = Form(200, ge=50, le=4000, description="Output width in pixels"),
    height: int = Form(200, ge=50, le=4000, description="Output height in pixels"),
    output_format: str = Form("JPG", pattern="^(JPG|PNG|PDF)$", description="Output format"),
    background_color: Optional[str] = Form(None, description="Background color in hex format"),
    maintain_aspect_ratio: bool = Form(False, description="Maintain original aspect ratio"),
    max_file_size_kb: Optional[int] = Form(None, ge=50, le=2048, description="Maximum output file size in KB")
):
    """Process a single image with specified parameters"""
    
    try:
        result = await photo_editor_service.process_image(
            file=file,
            width=width,
            height=height,
            output_format=output_format,
            background_color=background_color,
            maintain_aspect_ratio=maintain_aspect_ratio,
            max_file_size_kb=max_file_size_kb,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            # Use the file_id from the service result
            file_id = result["file_id"]
            
            return ProcessImageResponse(
                success=True,
                original_filename=result["original_filename"],
                processed_filename=result["processed_filename"],
                original_dimensions=result["original_dimensions"],
                new_dimensions=result["new_dimensions"],
                original_size_kb=result["original_size_kb"],
                processed_size_kb=result["processed_size_kb"],
                format=result["format"],
                download_url=f"/photo-editor/download/{file_id}",
                thumbnail_url=f"/photo-editor/thumbnail/{file_id}"
            )
        else:
            raise HTTPException(status_code=500, detail="Image processing failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.post("/process-batch", response_model=BatchProcessResponse)
async def process_batch_images(
    files: List[UploadFile] = File(..., description="Image files to process"),
    width: int = Form(200, ge=50, le=4000, description="Output width in pixels"),
    height: int = Form(200, ge=50, le=4000, description="Output height in pixels"),
    output_format: str = Form("JPG", pattern="^(JPG|PNG|PDF)$", description="Output format"),
    background_color: Optional[str] = Form(None, description="Background color in hex format"),
    maintain_aspect_ratio: bool = Form(False, description="Maintain original aspect ratio"),
    max_file_size_kb: Optional[int] = Form(None, ge=50, le=2048, description="Maximum output file size in KB")
):
    """Process multiple images with the same parameters"""
    
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files allowed per batch")
    
    try:
        results = await photo_editor_service.process_multiple_images(
            files=files,
            width=width,
            height=height,
            output_format=output_format,
            background_color=background_color,
            maintain_aspect_ratio=maintain_aspect_ratio,
            max_file_size_kb=max_file_size_kb,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        processed_results = []
        successful = 0
        failed = 0
        
        for result in results:
            if result["success"]:
                successful += 1
                # Use the file_id from the service result, not a generated one
                file_id = result["file_id"]
                
                processed_results.append(ProcessImageResponse(
                    success=True,
                    original_filename=result["original_filename"],
                    processed_filename=result["processed_filename"],
                    original_dimensions=result["original_dimensions"],
                    new_dimensions=result["new_dimensions"],
                    original_size_kb=result["original_size_kb"],
                    processed_size_kb=result["processed_size_kb"],
                    format=result["format"],
                    download_url=f"/photo-editor/download/{file_id}",
                    thumbnail_url=f"/photo-editor/thumbnail/{file_id}"
                ))
            else:
                failed += 1
                processed_results.append(ProcessImageResponse(
                    success=False,
                    original_filename=result["original_filename"],
                    processed_filename="",
                    original_dimensions="",
                    new_dimensions="",
                    original_size_kb=0,
                    processed_size_kb=0,
                    format="",
                    download_url="",
                    error=result.get("error", "Processing failed")
                ))
        
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        download_all_url = f"/photo-editor/download-batch/{batch_id}" if successful > 1 else None
        
        return BatchProcessResponse(
            total_files=len(files),
            successful=successful,
            failed=failed,
            results=processed_results,
            download_all_url=download_all_url
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {str(e)}")

@router.get("/download/{file_id}")
async def download_processed_image(file_id: str):
    """Download a processed image file"""
    
    try:
        print(f"DEBUG: Attempting to download file_id: {file_id}")
        file_info = photo_editor_service.get_processed_file(file_id)
        if not file_info:
            print(f"DEBUG: File not found for file_id: {file_id}")
            raise HTTPException(status_code=404, detail="File not found")
        
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

@router.get("/thumbnail/{file_id}")
async def get_image_thumbnail(file_id: str):
    """Get a thumbnail of the processed image"""
    
    try:
        thumbnail_path = photo_editor_service.get_thumbnail_file(file_id)
        if not thumbnail_path:
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        
        def file_generator():
            with open(thumbnail_path, 'rb') as f:
                while chunk := f.read(8192):
                    yield chunk
        
        return StreamingResponse(
            file_generator(),
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f"inline; filename={thumbnail_path.name}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Thumbnail retrieval failed: {str(e)}")

@router.get("/download-batch/{batch_id}")
async def download_batch_zip(batch_id: str):
    """Download all processed images in a batch as a ZIP file"""
    
    try:
        # Create a ZIP file with all processed images
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Get all files from the processed_files directory
            processed_files_dir = photo_editor_service.processed_files_dir
            
            if not processed_files_dir.exists():
                raise HTTPException(status_code=404, detail="No processed files found")
            
            files_added = 0
            for file_path in processed_files_dir.glob("*"):
                if file_path.is_file():
                    # Add file to ZIP with just the filename (not full path)
                    zip_file.write(file_path, file_path.name)
                    files_added += 1
            
            if files_added == 0:
                raise HTTPException(status_code=404, detail="No files found for batch")
        
        zip_buffer.seek(0)
        
        def zip_generator():
            while chunk := zip_buffer.read(8192):
                yield chunk
        
        return StreamingResponse(
            zip_generator(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=processed_images_{batch_id}.zip"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch download failed: {str(e)}")

@router.post("/validate-image")
async def validate_image_file(file: UploadFile = File(...)):
    """Validate an image file before processing"""
    
    try:
        is_valid = await photo_editor_service.validate_image(file)
        
        # Get image info
        image_data = await file.read()
        image_info = photo_editor_service.get_image_info(image_data)
        
        return {
            "valid": is_valid,
            "filename": file.filename,
            "content_type": file.content_type,
            "size_bytes": len(image_data),
            "size_kb": len(image_data) // 1024,
            "image_info": image_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")

@router.get("/formats")
async def get_supported_formats():
    """Get list of supported input and output formats"""
    
    return {
        "input_formats": list(photo_editor_service.supported_input_formats),
        "output_formats": list(photo_editor_service.supported_output_formats),
        "max_file_size_mb": photo_editor_service.max_file_size // (1024 * 1024),
        "max_batch_size": 10
    }

@router.get("/health")
async def health_check():
    """Health check endpoint for photo editor service"""
    
    return {
        "status": "healthy",
        "service": "photo-editor",
        "timestamp": datetime.now().isoformat(),
        "features": {
            "image_processing": True,
            "format_conversion": True,
            "batch_processing": True,
            "background_change": True,
            "aspect_ratio_control": True
        }
    }
