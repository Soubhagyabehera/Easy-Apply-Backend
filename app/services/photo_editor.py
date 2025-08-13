"""
Photo Editor Service for EasyApply Document Tools
Handles image processing, resizing, format conversion, and background changes.
"""

import io
import os
import uuid
import time
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image, ImageDraw, ImageFilter
import img2pdf
from fastapi import UploadFile, HTTPException
from pathlib import Path
from datetime import datetime
from app.database.supabase_client import postgresql_client

class PhotoEditorService:
    """Service for handling photo editing operations"""
    
    def __init__(self):
        """Initialize the photo editor service"""
        self.supported_formats = ["JPG", "JPEG", "PNG", "PDF"]
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        self.max_dimension = 4000
        self.min_dimension = 50
        
        # Initialize database tables
        self._ensure_tables_exist()
        
        self.temp_dir = Path("temp_uploads")
        self.temp_dir.mkdir(exist_ok=True)
        self.processed_files_dir = Path("processed_files")
        self.processed_files_dir.mkdir(exist_ok=True)
        self.thumbnails_dir = Path("thumbnails")
        self.thumbnails_dir.mkdir(exist_ok=True)
        self.supported_input_formats = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
        self.supported_output_formats = {'JPG', 'PNG', 'PDF'}
    
    def _ensure_tables_exist(self):
        """Ensure photo editor database tables exist"""
        try:
            postgresql_client.ensure_photo_editor_tables_exist()
        except Exception as e:
            print(f"Warning: Could not initialize photo editor database tables: {e}")
    
    async def validate_image(self, file: UploadFile) -> bool:
        """Validate uploaded image file"""
        if file.size and file.size > self.max_file_size:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
        
        file_ext = Path(file.filename or "").suffix.lower()
        if file_ext not in self.supported_input_formats:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported format. Supported: {', '.join(self.supported_input_formats)}"
            )
        
        return True
    
    async def process_image(
        self,
        file: UploadFile,
        width: int = 200,
        height: int = 200,
        output_format: str = "JPG",
        background_color: Optional[str] = None,
        maintain_aspect_ratio: bool = False,
        max_file_size_kb: Optional[int] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process a single image with specified parameters"""
        
        start_time = time.time()
        file_id = str(uuid.uuid4())
        
        await self.validate_image(file)
        
        # Read image data
        image_data = await file.read()
        await file.seek(0)  # Reset file pointer
        
        try:
            # Open image with PIL
            with Image.open(io.BytesIO(image_data)) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create white background for transparent images
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Store original dimensions
                original_width, original_height = img.size
                
                # Handle aspect ratio
                if maintain_aspect_ratio:
                    img.thumbnail((width, height), Image.Resampling.LANCZOS)
                    new_width, new_height = img.size
                else:
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
                    new_width, new_height = width, height
                
                # Change background color if specified
                if background_color and background_color != "#ffffff":
                    # Convert hex to RGB
                    bg_color = tuple(int(background_color[i:i+2], 16) for i in (1, 3, 5))
                    background = Image.new('RGB', (new_width, new_height), bg_color)
                    background.paste(img, (0, 0))
                    img = background
                
                # Generate output
                output_buffer = io.BytesIO()
                
                if output_format.upper() == 'PDF':
                    # Convert to PDF using img2pdf
                    temp_img_buffer = io.BytesIO()
                    img.save(temp_img_buffer, format='JPEG', quality=95)
                    temp_img_buffer.seek(0)
                    
                    pdf_bytes = img2pdf.convert(temp_img_buffer.getvalue())
                    output_buffer.write(pdf_bytes)
                    content_type = "application/pdf"
                    file_extension = "pdf"
                else:
                    # Save as image format
                    save_format = 'JPEG' if output_format.upper() == 'JPG' else output_format.upper()
                    quality = 95
                    
                    # Optimize file size if max_file_size_kb is specified
                    if max_file_size_kb:
                        target_size = max_file_size_kb * 1024
                        quality = 95
                        while quality > 10:
                            temp_buffer = io.BytesIO()
                            img.save(temp_buffer, format=save_format, quality=quality)
                            if temp_buffer.tell() <= target_size:
                                break
                            quality -= 10
                    
                    img.save(output_buffer, format=save_format, quality=quality)
                    content_type = f"image/{output_format.lower()}"
                    file_extension = output_format.lower()
                
                output_buffer.seek(0)
                output_size = output_buffer.tell()
                output_buffer.seek(0)
                
                # Generate processed filename
                original_name = Path(file.filename or "image").stem
                processed_filename = f"processed_{width}x{height}_{original_name}.{file_extension}"
                
                # Calculate processing time
                processing_time_ms = int((time.time() - start_time) * 1000)
                
                # Save processed file to disk
                file_extension = "pdf" if output_format.upper() == 'PDF' else output_format.lower()
                stored_filename = f"{file_id}.{file_extension}"
                storage_path = self.processed_files_dir / stored_filename
                
                with open(storage_path, 'wb') as f:
                    f.write(output_buffer.getvalue())
                
                # Generate and save thumbnail
                thumbnail_path = None
                if output_format.upper() != 'PDF':  # Only generate thumbnails for images
                    try:
                        thumbnail_size = (150, 150)
                        thumbnail_img = img.copy()
                        thumbnail_img.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
                        
                        thumbnail_filename = f"{file_id}_thumb.jpg"
                        thumbnail_path = self.thumbnails_dir / thumbnail_filename
                        thumbnail_img.save(thumbnail_path, format='JPEG', quality=85)
                    except Exception as e:
                        print(f"Warning: Could not generate thumbnail: {e}")
                
                # Save processing history to database
                processing_data = {
                    "user_id": user_id,
                    "session_id": session_id or str(uuid.uuid4()),
                    "original_filename": file.filename or "unknown.jpg",
                    "original_size_bytes": len(image_data),
                    "original_width": original_width,
                    "original_height": original_height,
                    "original_format": Path(file.filename or "").suffix.upper().lstrip('.') or "JPG",
                    "target_width": width,
                    "target_height": height,
                    "output_format": output_format.upper(),
                    "background_color": background_color,
                    "maintain_aspect_ratio": maintain_aspect_ratio,
                    "max_file_size_kb": max_file_size_kb,
                    "processed_filename": processed_filename,
                    "processed_size_bytes": output_size,
                    "processed_width": new_width,
                    "processed_height": new_height,
                    "compression_ratio": round(output_size / len(image_data), 2) if len(image_data) > 0 else 1.0,
                    "processing_time_ms": processing_time_ms,
                    "success": True,
                    "error_message": None,
                    "file_id": file_id,
                    "storage_path": str(storage_path),
                    "thumbnail_path": str(thumbnail_path) if thumbnail_path else None
                }
                
                try:
                    postgresql_client.save_photo_processing_history(processing_data)
                except Exception as e:
                    print(f"Warning: Could not save processing history: {e}")
                
                return {
                    "success": True,
                    "file_id": file_id,
                    "original_filename": file.filename,
                    "processed_filename": processed_filename,
                    "original_dimensions": f"{original_width}x{original_height}",
                    "new_dimensions": f"{new_width}x{new_height}",
                    "original_size_kb": len(image_data) // 1024,
                    "processed_size_kb": output_size // 1024,
                    "format": output_format.upper(),
                    "content_type": content_type,
                    "processing_time_ms": processing_time_ms,
                    "file_data": output_buffer.getvalue()
                }
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")
    
    def get_processed_file(self, file_id: str) -> Optional[Tuple[Path, str]]:
        """Get processed file path and content type by file_id"""
        try:
            print(f"DEBUG: Looking for file_id: {file_id}")
            print(f"DEBUG: Processed files directory: {self.processed_files_dir}")
            
            # List all files in the directory for debugging
            if self.processed_files_dir.exists():
                files_in_dir = list(self.processed_files_dir.glob("*"))
                print(f"DEBUG: Files in directory: {[f.name for f in files_in_dir]}")
            
            # Check for different file extensions
            for ext, content_type in [
                ('jpg', 'image/jpeg'),
                ('png', 'image/png'),
                ('pdf', 'application/pdf')
            ]:
                file_path = self.processed_files_dir / f"{file_id}.{ext}"
                print(f"DEBUG: Checking for file: {file_path}")
                if file_path.exists():
                    print(f"DEBUG: Found file: {file_path}")
                    return file_path, content_type
            
            print(f"DEBUG: No file found for file_id: {file_id}")
            return None
        except Exception as e:
            print(f"Error retrieving file {file_id}: {e}")
            return None
    
    def get_thumbnail_file(self, file_id: str) -> Optional[Path]:
        """Get thumbnail file path by file_id"""
        try:
            thumbnail_path = self.thumbnails_dir / f"{file_id}_thumb.jpg"
            if thumbnail_path.exists():
                return thumbnail_path
            return None
        except Exception as e:
            print(f"Error retrieving thumbnail {file_id}: {e}")
            return None
    
    async def process_multiple_images(
        self,
        files: List[UploadFile],
        width: int = 200,
        height: int = 200,
        output_format: str = "JPG",
        background_color: Optional[str] = None,
        maintain_aspect_ratio: bool = False,
        max_file_size_kb: Optional[int] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Process multiple images with the same parameters"""
        
        if len(files) > 10:  # Limit batch processing
            raise HTTPException(status_code=400, detail="Maximum 10 files allowed per batch")
        
        results = []
        for file in files:
            try:
                result = await self.process_image(
                    file=file,
                    width=width,
                    height=height,
                    output_format=output_format,
                    background_color=background_color,
                    maintain_aspect_ratio=maintain_aspect_ratio,
                    max_file_size_kb=max_file_size_kb,
                    user_id=user_id,
                    session_id=session_id
                )
                results.append(result)
            except HTTPException as e:
                results.append({
                    "success": False,
                    "original_filename": file.filename,
                    "error": e.detail
                })
            except Exception as e:
                results.append({
                    "success": False,
                    "original_filename": file.filename,
                    "error": f"Processing failed: {str(e)}"
                })
        
        return results
    
    def create_thumbnail(self, image_data: bytes, size: Tuple[int, int] = (150, 150)) -> bytes:
        """Create a thumbnail from image data"""
        try:
            with Image.open(io.BytesIO(image_data)) as img:
                img.thumbnail(size, Image.Resampling.LANCZOS)
                
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                thumbnail_buffer = io.BytesIO()
                img.save(thumbnail_buffer, format='JPEG', quality=85)
                thumbnail_buffer.seek(0)
                return thumbnail_buffer.getvalue()
        except Exception:
            return b""
    
    def get_image_info(self, image_data: bytes) -> Dict[str, Any]:
        """Get information about an image"""
        try:
            with Image.open(io.BytesIO(image_data)) as img:
                return {
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                    "size_bytes": len(image_data)
                }
        except Exception as e:
            return {"error": str(e)}

# Global instance
photo_editor_service = PhotoEditorService()
