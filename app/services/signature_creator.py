"""
Signature Creator Service for EasyApply Document Tools
Handles signature creation: draw, type, upload signature functionality
"""

import io
import os
import uuid
import time
import base64
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import img2pdf
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from fastapi import UploadFile, HTTPException
from app.database.supabase_client import postgresql_client


class SignatureCreatorService:
    """Service for handling signature creation operations"""
    
    def __init__(self):
        """Initialize the signature creator service"""
        self.supported_formats = ["PNG", "JPG", "PDF"]
        self.max_signature_size = 5 * 1024 * 1024  # 5MB
        self.signature_dimensions = {
            "small": (200, 80),
            "medium": (300, 120),
            "large": (400, 160)
        }
        
        # Initialize directories
        self.temp_dir = Path("temp_uploads")
        self.temp_dir.mkdir(exist_ok=True)
        self.signatures_dir = Path("signatures")
        self.signatures_dir.mkdir(exist_ok=True)
        
        # Initialize database tables
        self._ensure_tables_exist()
    
    def _ensure_tables_exist(self):
        """Ensure signature creator database tables exist"""
        try:
            postgresql_client.ensure_signature_tables_exist()
        except Exception as e:
            print(f"Warning: Could not initialize signature creator database tables: {e}")
    
    async def create_text_signature(
        self,
        text: str,
        font_style: str = "arial",
        font_size: int = 24,
        signature_size: str = "medium",
        color: str = "#000000",
        background_transparent: bool = True,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a signature from text"""
        
        start_time = time.time()
        signature_id = str(uuid.uuid4())
        
        if not text or len(text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Signature text cannot be empty")
        
        if len(text) > 100:
            raise HTTPException(status_code=400, detail="Signature text too long (max 100 characters)")
        
        try:
            # Get signature dimensions
            width, height = self.signature_dimensions.get(signature_size, self.signature_dimensions["medium"])
            
            # Create image
            if background_transparent:
                image = Image.new('RGBA', (width, height), (255, 255, 255, 0))
            else:
                image = Image.new('RGB', (width, height), (255, 255, 255))
            
            draw = ImageDraw.Draw(image)
            
            # Try to load font
            try:
                if font_style.lower() == "times":
                    font = ImageFont.truetype("times.ttf", font_size)
                elif font_style.lower() == "courier":
                    font = ImageFont.truetype("cour.ttf", font_size)
                else:  # arial or default
                    font = ImageFont.truetype("arial.ttf", font_size)
            except:
                # Fallback to default font
                try:
                    font = ImageFont.load_default()
                except:
                    font = None
            
            # Calculate text position (center)
            if font:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            else:
                text_width = len(text) * 10  # Rough estimate
                text_height = 20
            
            x = (width - text_width) // 2
            y = (height - text_height) // 2
            
            # Parse color
            try:
                if color.startswith('#'):
                    color_rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
                else:
                    color_rgb = (0, 0, 0)  # Default black
            except:
                color_rgb = (0, 0, 0)
            
            # Draw text
            draw.text((x, y), text, fill=color_rgb, font=font)
            
            # Save as PNG
            png_buffer = io.BytesIO()
            image.save(png_buffer, format='PNG')
            png_buffer.seek(0)
            png_size = png_buffer.tell()
            png_buffer.seek(0)
            
            # Save to disk
            signature_filename = f"text_signature_{signature_id}.png"
            storage_path = self.signatures_dir / signature_filename
            
            with open(storage_path, 'wb') as f:
                f.write(png_buffer.getvalue())
            
            # Create thumbnail
            thumbnail = image.copy()
            thumbnail.thumbnail((100, 40), Image.Resampling.LANCZOS)
            thumbnail_buffer = io.BytesIO()
            thumbnail.save(thumbnail_buffer, format='PNG')
            thumbnail_buffer.seek(0)
            
            # Save thumbnail
            thumbnail_filename = f"thumb_{signature_id}.png"
            thumbnail_path = self.signatures_dir / thumbnail_filename
            
            with open(thumbnail_path, 'wb') as f:
                f.write(thumbnail_buffer.getvalue())
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save to database
            signature_data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "signature_id": signature_id,
                "signature_type": "text",
                "signature_text": text,
                "font_style": font_style,
                "font_size": font_size,
                "signature_size": signature_size,
                "color": color,
                "background_transparent": background_transparent,
                "file_size": png_size,
                "processing_time_ms": processing_time_ms,
                "storage_path": str(storage_path),
                "thumbnail_path": str(thumbnail_path),
                "success": True
            }
            
            try:
                postgresql_client.save_signature_data(signature_data)
            except Exception as e:
                print(f"Warning: Could not save signature data: {e}")
            
            return {
                "success": True,
                "signature_id": signature_id,
                "signature_type": "text",
                "signature_text": text,
                "font_style": font_style,
                "font_size": font_size,
                "signature_size": signature_size,
                "color": color,
                "background_transparent": background_transparent,
                "width": width,
                "height": height,
                "file_size_kb": round(png_size / 1024, 2),
                "processing_time_ms": processing_time_ms,
                "download_url": f"/signature-creator/download/{signature_id}",
                "thumbnail_url": f"/signature-creator/thumbnail/{signature_id}"
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Text signature creation failed: {str(e)}")
    
    async def create_drawn_signature(
        self,
        signature_data: str,  # Base64 encoded image data
        signature_size: str = "medium",
        background_transparent: bool = True,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a signature from drawn/canvas data"""
        
        start_time = time.time()
        signature_id = str(uuid.uuid4())
        
        if not signature_data:
            raise HTTPException(status_code=400, detail="Signature data cannot be empty")
        
        try:
            # Decode base64 image data
            if signature_data.startswith('data:image'):
                # Remove data URL prefix
                signature_data = signature_data.split(',')[1]
            
            image_bytes = base64.b64decode(signature_data)
            
            if len(image_bytes) > self.max_signature_size:
                raise HTTPException(status_code=400, detail="Signature image too large (max 5MB)")
            
            # Load image
            image = Image.open(io.BytesIO(image_bytes))
            
            # Get target dimensions
            target_width, target_height = self.signature_dimensions.get(signature_size, self.signature_dimensions["medium"])
            
            # Resize image to target size
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Convert to RGBA if needed
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # Make background transparent if requested
            if background_transparent:
                # Convert white/light backgrounds to transparent
                data = image.getdata()
                new_data = []
                for item in data:
                    # If pixel is white or very light, make it transparent
                    if item[0] > 240 and item[1] > 240 and item[2] > 240:
                        new_data.append((255, 255, 255, 0))
                    else:
                        new_data.append(item)
                image.putdata(new_data)
            
            # Save as PNG
            png_buffer = io.BytesIO()
            image.save(png_buffer, format='PNG')
            png_buffer.seek(0)
            png_size = png_buffer.tell()
            png_buffer.seek(0)
            
            # Save to disk
            signature_filename = f"drawn_signature_{signature_id}.png"
            storage_path = self.signatures_dir / signature_filename
            
            with open(storage_path, 'wb') as f:
                f.write(png_buffer.getvalue())
            
            # Create thumbnail
            thumbnail = image.copy()
            thumbnail.thumbnail((100, 40), Image.Resampling.LANCZOS)
            thumbnail_buffer = io.BytesIO()
            thumbnail.save(thumbnail_buffer, format='PNG')
            thumbnail_buffer.seek(0)
            
            # Save thumbnail
            thumbnail_filename = f"thumb_{signature_id}.png"
            thumbnail_path = self.signatures_dir / thumbnail_filename
            
            with open(thumbnail_path, 'wb') as f:
                f.write(thumbnail_buffer.getvalue())
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save to database
            signature_data_db = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "signature_id": signature_id,
                "signature_type": "drawn",
                "signature_size": signature_size,
                "background_transparent": background_transparent,
                "file_size": png_size,
                "processing_time_ms": processing_time_ms,
                "storage_path": str(storage_path),
                "thumbnail_path": str(thumbnail_path),
                "success": True
            }
            
            try:
                postgresql_client.save_signature_data(signature_data_db)
            except Exception as e:
                print(f"Warning: Could not save signature data: {e}")
            
            return {
                "success": True,
                "signature_id": signature_id,
                "signature_type": "drawn",
                "signature_size": signature_size,
                "background_transparent": background_transparent,
                "width": target_width,
                "height": target_height,
                "file_size_kb": round(png_size / 1024, 2),
                "processing_time_ms": processing_time_ms,
                "download_url": f"/signature-creator/download/{signature_id}",
                "thumbnail_url": f"/signature-creator/thumbnail/{signature_id}"
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Drawn signature creation failed: {str(e)}")
    
    async def upload_signature(
        self,
        file: UploadFile,
        signature_size: str = "medium",
        background_transparent: bool = True,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload and process a signature image file"""
        
        start_time = time.time()
        signature_id = str(uuid.uuid4())
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Validate file type
        allowed_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp']
        file_ext = os.path.splitext(file.filename.lower())[1]
        if file_ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use PNG, JPG, GIF, or BMP")
        
        if file.size and file.size > self.max_signature_size:
            raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")
        
        try:
            # Read file data
            file_data = await file.read()
            await file.seek(0)
            
            # Load image
            image = Image.open(io.BytesIO(file_data))
            
            # Get target dimensions
            target_width, target_height = self.signature_dimensions.get(signature_size, self.signature_dimensions["medium"])
            
            # Resize image to target size
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Convert to RGBA if needed
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # Make background transparent if requested
            if background_transparent:
                # Convert white/light backgrounds to transparent
                data = image.getdata()
                new_data = []
                for item in data:
                    # If pixel is white or very light, make it transparent
                    if item[0] > 240 and item[1] > 240 and item[2] > 240:
                        new_data.append((255, 255, 255, 0))
                    else:
                        new_data.append(item)
                image.putdata(new_data)
            
            # Save as PNG
            png_buffer = io.BytesIO()
            image.save(png_buffer, format='PNG')
            png_buffer.seek(0)
            png_size = png_buffer.tell()
            png_buffer.seek(0)
            
            # Save to disk
            signature_filename = f"uploaded_signature_{signature_id}.png"
            storage_path = self.signatures_dir / signature_filename
            
            with open(storage_path, 'wb') as f:
                f.write(png_buffer.getvalue())
            
            # Create thumbnail
            thumbnail = image.copy()
            thumbnail.thumbnail((100, 40), Image.Resampling.LANCZOS)
            thumbnail_buffer = io.BytesIO()
            thumbnail.save(thumbnail_buffer, format='PNG')
            thumbnail_buffer.seek(0)
            
            # Save thumbnail
            thumbnail_filename = f"thumb_{signature_id}.png"
            thumbnail_path = self.signatures_dir / thumbnail_filename
            
            with open(thumbnail_path, 'wb') as f:
                f.write(thumbnail_buffer.getvalue())
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save to database
            signature_data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "signature_id": signature_id,
                "signature_type": "uploaded",
                "original_filename": file.filename,
                "signature_size": signature_size,
                "background_transparent": background_transparent,
                "file_size": png_size,
                "processing_time_ms": processing_time_ms,
                "storage_path": str(storage_path),
                "thumbnail_path": str(thumbnail_path),
                "success": True
            }
            
            try:
                postgresql_client.save_signature_data(signature_data)
            except Exception as e:
                print(f"Warning: Could not save signature data: {e}")
            
            return {
                "success": True,
                "signature_id": signature_id,
                "signature_type": "uploaded",
                "original_filename": file.filename,
                "signature_size": signature_size,
                "background_transparent": background_transparent,
                "width": target_width,
                "height": target_height,
                "file_size_kb": round(png_size / 1024, 2),
                "processing_time_ms": processing_time_ms,
                "download_url": f"/signature-creator/download/{signature_id}",
                "thumbnail_url": f"/signature-creator/thumbnail/{signature_id}"
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Signature upload failed: {str(e)}")
    
    def get_signature_file(self, signature_id: str) -> Optional[Tuple[Path, str]]:
        """Get signature file path and content type by signature_id"""
        try:
            file_path = self.signatures_dir / f"text_signature_{signature_id}.png"
            if file_path.exists():
                return file_path, "image/png"
            
            file_path = self.signatures_dir / f"drawn_signature_{signature_id}.png"
            if file_path.exists():
                return file_path, "image/png"
            
            file_path = self.signatures_dir / f"uploaded_signature_{signature_id}.png"
            if file_path.exists():
                return file_path, "image/png"
            
            return None
        except Exception as e:
            print(f"Error retrieving signature file {signature_id}: {e}")
            return None
    
    def get_signature_thumbnail(self, signature_id: str) -> Optional[Tuple[Path, str]]:
        """Get signature thumbnail path and content type by signature_id"""
        try:
            thumbnail_path = self.signatures_dir / f"thumb_{signature_id}.png"
            if thumbnail_path.exists():
                return thumbnail_path, "image/png"
            return None
        except Exception as e:
            print(f"Error retrieving signature thumbnail {signature_id}: {e}")
            return None


# Global instance
signature_creator_service = SignatureCreatorService()
