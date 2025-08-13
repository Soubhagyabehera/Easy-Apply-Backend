"""
Size Optimizer Service for EasyApply Document Tools
Handles file size optimization: compress images/PDFs, reduce file sizes, etc.
"""

import io
import os
import uuid
import time
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageFilter
import PyPDF2
from PyPDF2 import PdfReader, PdfWriter
from fastapi import UploadFile, HTTPException
from app.database.supabase_client import postgresql_client


class SizeOptimizerService:
    """Service for handling file size optimization operations"""
    
    def __init__(self):
        """Initialize the size optimizer service"""
        self.supported_formats = {
            "images": ["JPG", "JPEG", "PNG", "BMP", "TIFF", "WEBP"],
            "documents": ["PDF"]
        }
        self.max_file_size = 100 * 1024 * 1024  # 100MB
        self.compression_levels = {
            "light": {"quality": 85, "optimize": True},
            "medium": {"quality": 70, "optimize": True},
            "aggressive": {"quality": 50, "optimize": True}
        }
        
        # Initialize directories
        self.temp_dir = Path("temp_uploads")
        self.temp_dir.mkdir(exist_ok=True)
        self.optimized_files_dir = Path("optimized_files")
        self.optimized_files_dir.mkdir(exist_ok=True)
        
        # Initialize database tables
        # self._ensure_tables_exist()  # Temporarily disabled to avoid DB errors
    
    def _ensure_tables_exist(self):
        """Ensure size optimizer database tables exist"""
        # TODO: Implement ensure_optimizer_tables_exist method in postgresql_client
        # Temporarily disabled to avoid DB errors
        # try:
        #     postgresql_client.ensure_optimizer_tables_exist()
        # except Exception as e:
        #     print(f"Warning: Could not initialize size optimizer database tables: {e}")
        print("Size optimizer database tables initialization skipped")
    
    async def validate_file(self, file: UploadFile) -> bool:
        """Validate uploaded file for size optimization"""
        if file.size and file.size > self.max_file_size:
            raise HTTPException(status_code=400, detail="File size exceeds 100MB limit")
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        file_ext = os.path.splitext(file.filename.lower())[1][1:]  # Remove dot
        
        # Check if format is supported
        all_formats = []
        for formats in self.supported_formats.values():
            all_formats.extend(formats)
        
        if file_ext.upper() not in all_formats:
            raise HTTPException(status_code=400, detail=f"Unsupported format. Use: {', '.join(all_formats)}")
        
        return True
    
    async def optimize_image(
        self,
        file: UploadFile,
        compression_level: str = "medium",
        target_size_kb: Optional[int] = None,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        output_format: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Optimize image file size"""
        
        start_time = time.time()
        optimization_id = str(uuid.uuid4())
        
        await self.validate_file(file)
        
        try:
            file_data = await file.read()
            await file.seek(0)
            original_size = len(file_data)
            
            # Load image
            image = Image.open(io.BytesIO(file_data))
            original_format = image.format or "JPEG"
            
            # Determine output format
            if output_format is None:
                output_format = original_format
            
            # Resize if dimensions specified
            if max_width or max_height:
                # Calculate new dimensions maintaining aspect ratio
                width, height = image.size
                
                if max_width and width > max_width:
                    ratio = max_width / width
                    width = max_width
                    height = int(height * ratio)
                
                if max_height and height > max_height:
                    ratio = max_height / height
                    height = max_height
                    width = int(width * ratio)
                
                image = image.resize((width, height), Image.LANCZOS)
            
            # Get compression settings
            compression_settings = self.compression_levels.get(compression_level, self.compression_levels["medium"])
            
            # Convert to RGB if saving as JPEG
            if output_format.upper() in ["JPG", "JPEG"] and image.mode in ["RGBA", "P"]:
                # Create white background
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            
            # Optimize file size
            optimized_data = None
            current_quality = compression_settings["quality"]
            
            if target_size_kb:
                # Iteratively reduce quality to meet target size
                target_size_bytes = target_size_kb * 1024
                min_quality = 20
                
                while current_quality >= min_quality:
                    output_buffer = io.BytesIO()
                    
                    if output_format.upper() in ["JPG", "JPEG"]:
                        image.save(output_buffer, format="JPEG", quality=current_quality, optimize=True)
                    elif output_format.upper() == "PNG":
                        image.save(output_buffer, format="PNG", optimize=True)
                    else:
                        image.save(output_buffer, format=output_format.upper(), optimize=compression_settings["optimize"])
                    
                    output_buffer.seek(0)
                    current_size = output_buffer.tell()
                    
                    if current_size <= target_size_bytes or current_quality <= min_quality:
                        output_buffer.seek(0)
                        optimized_data = output_buffer.getvalue()
                        break
                    
                    current_quality -= 5
            else:
                # Use specified compression level
                output_buffer = io.BytesIO()
                
                if output_format.upper() in ["JPG", "JPEG"]:
                    image.save(output_buffer, format="JPEG", quality=current_quality, optimize=True)
                elif output_format.upper() == "PNG":
                    image.save(output_buffer, format="PNG", optimize=True)
                else:
                    image.save(output_buffer, format=output_format.upper(), optimize=compression_settings["optimize"])
                
                output_buffer.seek(0)
                optimized_data = output_buffer.getvalue()
            
            if optimized_data is None:
                raise HTTPException(status_code=500, detail="Image optimization failed")
            
            optimized_size = len(optimized_data)
            compression_ratio = round((1 - optimized_size / original_size) * 100, 1)
            
            # Save to disk
            output_filename = f"optimized_{file.filename}"
            if output_format.upper() != original_format.upper():
                base_name = os.path.splitext(output_filename)[0]
                output_filename = f"{base_name}.{output_format.lower()}"
            
            storage_path = self.optimized_files_dir / f"{optimization_id}.{output_format.lower()}"
            
            with open(storage_path, 'wb') as f:
                f.write(optimized_data)
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save to database
            optimization_data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "optimization_id": optimization_id,
                "file_type": "image",
                "original_format": original_format.upper(),
                "output_format": output_format.upper(),
                "compression_level": compression_level,
                "target_size_kb": target_size_kb,
                "max_width": max_width,
                "max_height": max_height,
                "original_size": original_size,
                "optimized_size": optimized_size,
                "compression_ratio": compression_ratio,
                "final_quality": current_quality,
                "processing_time_ms": processing_time_ms,
                "storage_path": str(storage_path),
                "original_filename": file.filename,
                "success": True
            }
            
            try:
                postgresql_client.save_optimization_data(optimization_data)
            except Exception as e:
                print(f"Warning: Could not save optimization data: {e}")
            
            return {
                "success": True,
                "optimization_id": optimization_id,
                "file_type": "image",
                "original_filename": file.filename,
                "output_filename": output_filename,
                "original_format": original_format.upper(),
                "output_format": output_format.upper(),
                "compression_level": compression_level,
                "target_size_kb": target_size_kb,
                "final_quality": current_quality,
                "original_size_mb": round(original_size / (1024 * 1024), 2),
                "optimized_size_mb": round(optimized_size / (1024 * 1024), 2),
                "compression_ratio": compression_ratio,
                "size_reduction_kb": round((original_size - optimized_size) / 1024, 2),
                "processing_time_ms": processing_time_ms,
                "download_url": f"/size-optimizer/download/{optimization_id}",
                "file_data": optimized_data
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image optimization failed: {str(e)}")
    
    async def optimize_pdf(
        self,
        file: UploadFile,
        compression_level: str = "medium",
        remove_metadata: bool = True,
        remove_annotations: bool = False,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Optimize PDF file size"""
        
        start_time = time.time()
        optimization_id = str(uuid.uuid4())
        
        await self.validate_file(file)
        
        try:
            file_data = await file.read()
            await file.seek(0)
            original_size = len(file_data)
            
            # Read PDF
            pdf_reader = PdfReader(io.BytesIO(file_data))
            pdf_writer = PdfWriter()
            
            # Copy pages with optimization
            for page in pdf_reader.pages:
                if remove_annotations:
                    # Remove annotations
                    if "/Annots" in page:
                        del page["/Annots"]
                
                pdf_writer.add_page(page)
            
            # Apply compression based on level
            if compression_level == "aggressive":
                pdf_writer.compress_identical_objects()
                pdf_writer.remove_duplication()
                pdf_writer.remove_images()  # Remove embedded images for maximum compression
            elif compression_level == "medium":
                pdf_writer.compress_identical_objects()
                pdf_writer.remove_duplication()
            # For "light", minimal compression
            
            # Remove metadata if requested
            if remove_metadata:
                pdf_writer.add_metadata({})
            
            # Generate optimized PDF
            output_buffer = io.BytesIO()
            pdf_writer.write(output_buffer)
            output_buffer.seek(0)
            optimized_data = output_buffer.getvalue()
            optimized_size = len(optimized_data)
            
            compression_ratio = round((1 - optimized_size / original_size) * 100, 1)
            
            # Save to disk
            output_filename = f"optimized_{file.filename}"
            storage_path = self.optimized_files_dir / f"{optimization_id}.pdf"
            
            with open(storage_path, 'wb') as f:
                f.write(optimized_data)
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save to database
            optimization_data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "optimization_id": optimization_id,
                "file_type": "pdf",
                "original_format": "PDF",
                "output_format": "PDF",
                "compression_level": compression_level,
                "remove_metadata": remove_metadata,
                "remove_annotations": remove_annotations,
                "original_size": original_size,
                "optimized_size": optimized_size,
                "compression_ratio": compression_ratio,
                "total_pages": len(pdf_reader.pages),
                "processing_time_ms": processing_time_ms,
                "storage_path": str(storage_path),
                "original_filename": file.filename,
                "success": True
            }
            
            try:
                postgresql_client.save_optimization_data(optimization_data)
            except Exception as e:
                print(f"Warning: Could not save optimization data: {e}")
            
            return {
                "success": True,
                "optimization_id": optimization_id,
                "file_type": "pdf",
                "original_filename": file.filename,
                "output_filename": output_filename,
                "compression_level": compression_level,
                "remove_metadata": remove_metadata,
                "remove_annotations": remove_annotations,
                "total_pages": len(pdf_reader.pages),
                "original_size_mb": round(original_size / (1024 * 1024), 2),
                "optimized_size_mb": round(optimized_size / (1024 * 1024), 2),
                "compression_ratio": compression_ratio,
                "size_reduction_mb": round((original_size - optimized_size) / (1024 * 1024), 2),
                "processing_time_ms": processing_time_ms,
                "download_url": f"/size-optimizer/download/{optimization_id}",
                "file_data": optimized_data
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF optimization failed: {str(e)}")
    
    def get_optimized_file(self, optimization_id: str) -> Optional[Tuple[Path, str]]:
        """Get optimized file path and content type by optimization_id"""
        try:
            # Check for common formats
            for ext, content_type in [
                ("pdf", "application/pdf"),
                ("png", "image/png"),
                ("jpg", "image/jpeg"),
                ("jpeg", "image/jpeg"),
                ("bmp", "image/bmp"),
                ("tiff", "image/tiff"),
                ("webp", "image/webp")
            ]:
                file_path = self.optimized_files_dir / f"{optimization_id}.{ext}"
                if file_path.exists():
                    return file_path, content_type
            
            return None
        except Exception as e:
            print(f"Error retrieving optimized file {optimization_id}: {e}")
            return None


# Global instance
size_optimizer_service = SizeOptimizerService()
