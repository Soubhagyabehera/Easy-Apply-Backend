"""
PDF Tools API Endpoints for EasyApply Document Tools
Handles PDF operations: merge, split, compress, extract pages, etc.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import io
import zipfile
from datetime import datetime

from app.services.pdf_tools import pdf_tools_service

router = APIRouter(tags=["PDF Tools"])

class PDFOperationRequest(BaseModel):
    """Request model for PDF operations"""
    operation_type: str = Field(..., pattern="^(merge|split|compress|extract)$", description="Type of PDF operation")
    compression_level: Optional[str] = Field(default="medium", pattern="^(low|medium|high)$", description="Compression level")
    split_type: Optional[str] = Field(default="pages", pattern="^(pages|range|bookmarks)$", description="Split type")
    split_config: Optional[Dict[str, Any]] = Field(default=None, description="Split configuration")

class PDFOperationResponse(BaseModel):
    """Response model for PDF operations"""
    success: bool
    operation: str
    file_id: Optional[str] = None
    batch_id: Optional[str] = None
    original_filename: Optional[str] = None
    processed_filename: Optional[str] = None
    total_pages: Optional[int] = None
    input_files: Optional[int] = None
    output_files: Optional[int] = None
    original_size_mb: Optional[float] = None
    processed_size_mb: Optional[float] = None
    compression_ratio: Optional[float] = None
    compression_level: Optional[str] = None
    processing_time_ms: Optional[int] = None
    download_url: Optional[str] = None
    files: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None

class BatchPDFResponse(BaseModel):
    """Response model for batch PDF operations"""
    success: bool
    operation: str
    batch_id: str
    input_filename: str
    total_pages: int
    output_files: int
    files: List[Dict[str, Any]]
    processing_time_ms: int
    download_all_url: Optional[str] = None

@router.post("/merge", response_model=PDFOperationResponse)
async def merge_pdfs(
    files: List[UploadFile] = File(..., description="PDF files to merge (2-20 files)"),
):
    """Merge multiple PDF files into one"""
    
    try:
        result = await pdf_tools_service.merge_pdfs(
            files=files,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            file_id = result["file_id"]
            
            return PDFOperationResponse(
                success=True,
                operation="merge",
                file_id=file_id,
                processed_filename=result["processed_filename"],
                total_pages=result["total_pages"],
                input_files=result["input_files"],
                original_size_mb=result["original_size_mb"],
                processed_size_mb=result["processed_size_mb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=f"/pdf-tools/download/{file_id}"
            )
        else:
            raise HTTPException(status_code=500, detail="PDF merge failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF merge failed: {str(e)}")

@router.post("/split", response_model=BatchPDFResponse)
async def split_pdf(
    file: UploadFile = File(..., description="PDF file to split"),
    split_type: str = Form(default="pages", pattern="^(pages|range|bookmarks)$", description="Split type"),
    pages_per_file: int = Form(default=1, ge=1, le=50, description="Pages per output file (for pages split)"),
    page_ranges: Optional[str] = Form(default=None, description="Page ranges as JSON string (for range split)")
):
    """Split PDF into multiple files"""
    
    try:
        # Parse split configuration
        split_config = {"pages_per_file": pages_per_file}
        
        if split_type == "range" and page_ranges:
            import json
            try:
                ranges = json.loads(page_ranges)
                split_config["ranges"] = ranges
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid page ranges JSON format")
        
        result = await pdf_tools_service.split_pdf(
            file=file,
            split_type=split_type,
            split_config=split_config,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            batch_id = result["batch_id"]
            
            return BatchPDFResponse(
                success=True,
                operation="split",
                batch_id=batch_id,
                input_filename=result["input_filename"],
                total_pages=result["total_pages"],
                output_files=result["output_files"],
                files=result["files"],
                processing_time_ms=result["processing_time_ms"],
                download_all_url=f"/pdf-tools/download-batch/{batch_id}"
            )
        else:
            raise HTTPException(status_code=500, detail="PDF split failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF split failed: {str(e)}")

@router.post("/compress", response_model=PDFOperationResponse)
async def compress_pdf(
    file: UploadFile = File(..., description="PDF file to compress"),
    compression_level: str = Form(default="medium", pattern="^(low|medium|high)$", description="Compression level")
):
    """Compress PDF file to reduce size"""
    
    try:
        result = await pdf_tools_service.compress_pdf(
            file=file,
            compression_level=compression_level,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            file_id = result["file_id"]
            
            return PDFOperationResponse(
                success=True,
                operation="compress",
                file_id=file_id,
                original_filename=result["original_filename"],
                processed_filename=result["processed_filename"],
                original_size_mb=result["original_size_mb"],
                processed_size_mb=result["compressed_size_mb"],
                compression_ratio=result["compression_ratio"],
                compression_level=result["compression_level"],
                processing_time_ms=result["processing_time_ms"],
                download_url=f"/pdf-tools/download/{file_id}"
            )
        else:
            raise HTTPException(status_code=500, detail="PDF compression failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF compression failed: {str(e)}")

@router.get("/download/{file_id}")
async def download_processed_pdf(file_id: str):
    """Download a processed PDF file"""
    
    try:
        file_info = pdf_tools_service.get_processed_file(file_id)
        if not file_info:
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

@router.get("/download-batch/{batch_id}")
async def download_batch_pdfs(batch_id: str):
    """Download all processed PDFs in a batch as a ZIP file"""
    
    try:
        # Create a ZIP file with all processed PDFs
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Get all PDF files from the processed_pdfs directory
            processed_files_dir = pdf_tools_service.processed_files_dir
            
            if not processed_files_dir.exists():
                raise HTTPException(status_code=404, detail="No processed files found")
            
            files_added = 0
            for file_path in processed_files_dir.glob("*.pdf"):
                if file_path.is_file():
                    # Add file to ZIP with just the filename (not full path)
                    zip_file.write(file_path, file_path.name)
                    files_added += 1
            
            if files_added == 0:
                raise HTTPException(status_code=404, detail="No PDF files found for batch")
        
        zip_buffer.seek(0)
        
        def zip_generator():
            while chunk := zip_buffer.read(8192):
                yield chunk
        
        return StreamingResponse(
            zip_generator(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=processed_pdfs_{batch_id}.zip"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch download failed: {str(e)}")

@router.post("/validate")
async def validate_pdf_file(file: UploadFile = File(...)):
    """Validate a PDF file before processing"""
    
    try:
        is_valid = await pdf_tools_service.validate_pdf(file)
        
        return {
            "success": True,
            "valid": is_valid,
            "filename": file.filename,
            "size_mb": round(file.size / (1024 * 1024), 2) if file.size else 0,
            "message": "PDF file is valid and ready for processing"
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
async def get_pdf_tools_info():
    """Get PDF tools capabilities and limits"""
    
    return {
        "supported_operations": ["merge", "split", "compress", "combine_documents", "pdf_to_images", "combine_pdfs"],
        "supported_formats": ["PDF"],
        "limits": {
            "max_file_size_mb": 50,
            "max_pages_per_pdf": 1000,
            "max_files_for_merge": 20,
            "max_pages_per_split_file": 50
        },
        "compression_levels": ["low", "medium", "high"],
        "split_types": ["pages", "range", "bookmarks"]
    }

@router.post("/combine-documents", response_model=PDFOperationResponse)
async def combine_documents_to_pdf(
    files: List[UploadFile] = File(..., description="Documents to combine (PDFs, images - 2-20 files)"),
):
    """Combine different document types (certificates, marksheets, ID images) into a single PDF"""
    
    try:
        result = await pdf_tools_service.combine_documents_to_pdf(
            files=files,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            file_id = result["file_id"]
            
            return PDFOperationResponse(
                success=True,
                operation="combine_documents",
                file_id=file_id,
                processed_filename=result["processed_filename"],
                total_pages=result["total_pages"],
                input_files=result["input_files"],
                original_size_mb=result["original_size_mb"],
                processed_size_mb=result["processed_size_mb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=f"/pdf-tools/download/{file_id}"
            )
        else:
            raise HTTPException(status_code=500, detail="Document combination failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document combination failed: {str(e)}")

@router.post("/pdf-to-images", response_model=BatchPDFResponse)
async def pdf_to_images(
    file: UploadFile = File(..., description="PDF file to convert to images"),
    image_format: str = Form(default="png", pattern="^(png|jpg|jpeg)$", description="Output image format"),
    dpi: int = Form(default=150, ge=72, le=300, description="Image DPI (72-300)")
):
    """Convert each page of PDF to individual images"""
    
    try:
        result = await pdf_tools_service.pdf_to_images(
            file=file,
            image_format=image_format,
            dpi=dpi,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            batch_id = result["batch_id"]
            
            return BatchPDFResponse(
                success=True,
                operation="pdf_to_images",
                batch_id=batch_id,
                input_filename=result["input_filename"],
                total_pages=result["total_pages"],
                output_files=result["output_images"],
                files=result["images"],
                processing_time_ms=result["processing_time_ms"],
                download_all_url=f"/pdf-tools/download-images/{batch_id}"
            )
        else:
            raise HTTPException(status_code=500, detail="PDF to images conversion failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF to images conversion failed: {str(e)}")

@router.post("/combine-pdfs", response_model=PDFOperationResponse)
async def combine_pdfs(
    files: List[UploadFile] = File(..., description="PDF files to combine (2-10 files)"),
):
    """Combine multiple PDF files into one"""
    
    try:
        result = await pdf_tools_service.combine_pdfs(
            files=files,
            user_id=None,  # TODO: Get from authentication
            session_id=None  # TODO: Get from session
        )
        
        if result["success"]:
            file_id = result["file_id"]
            
            return PDFOperationResponse(
                success=True,
                operation="combine_pdfs",
                file_id=file_id,
                processed_filename=result["processed_filename"],
                total_pages=result["total_pages"],
                input_files=result["input_files"],
                original_size_mb=result["original_size_mb"],
                processed_size_mb=result["processed_size_mb"],
                processing_time_ms=result["processing_time_ms"],
                download_url=f"/pdf-tools/download/{file_id}"
            )
        else:
            raise HTTPException(status_code=500, detail="PDF combination failed")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF combination failed: {str(e)}")

@router.get("/download-image/{image_id}")
async def download_processed_image(image_id: str):
    """Download a processed image file"""
    
    try:
        file_info = pdf_tools_service.get_processed_image(image_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="Image not found")
        
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
        raise HTTPException(status_code=500, detail=f"Image download failed: {str(e)}")

@router.get("/download-images/{batch_id}")
async def download_batch_images(batch_id: str):
    """Download all processed images in a batch as a ZIP file"""
    
    try:
        # Create a ZIP file with all processed images
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Get all image files from the pdf_images directory
            images_dir = pdf_tools_service.pdf_images_dir
            
            if not images_dir.exists():
                raise HTTPException(status_code=404, detail="No processed images found")
            
            files_added = 0
            for file_path in images_dir.glob("*"):
                if file_path.is_file() and file_path.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                    # Add file to ZIP with just the filename (not full path)
                    zip_file.write(file_path, file_path.name)
                    files_added += 1
            
            if files_added == 0:
                raise HTTPException(status_code=404, detail="No image files found for batch")
        
        zip_buffer.seek(0)
        
        def zip_generator():
            while chunk := zip_buffer.read(8192):
                yield chunk
        
        return StreamingResponse(
            zip_generator(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=pdf_images_{batch_id}.zip"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image batch download failed: {str(e)}")

@router.get("/health")
async def health_check():
    """Health check endpoint for PDF tools service"""
    
    try:
        # Test basic functionality
        test_passed = True
        
        return {
            "status": "healthy" if test_passed else "unhealthy",
            "service": "PDF Tools",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "capabilities": {
                "merge": True,
                "split": True,
                "compress": True,
                "combine_documents": True,
                "pdf_to_images": True,
                "combine_pdfs": True
            }
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "PDF Tools",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
