"""
Format Converter Service for EasyApply Document Tools
Handles format conversion: PDF <-> image, document format conversions, etc.
"""

import io
import os
import uuid
import time
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime
from PIL import Image
import PyPDF2
from PyPDF2 import PdfReader, PdfWriter
from pdf2image import convert_from_bytes
import img2pdf
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from docx import Document
from openpyxl import Workbook, load_workbook
from fastapi import UploadFile, HTTPException
from app.database.supabase_client import postgresql_client


class FormatConverterService:
    """Service for handling format conversion operations"""
    
    def __init__(self):
        """Initialize the format converter service"""
        self.supported_input_formats = {
            "images": ["JPG", "JPEG", "PNG", "BMP", "TIFF", "GIF", "WEBP"],
            "documents": ["PDF", "DOCX", "TXT"],
            "spreadsheets": ["XLSX", "CSV"]
        }
        self.supported_output_formats = {
            "images": ["JPG", "PNG", "PDF"],
            "documents": ["PDF", "DOCX", "TXT"],
            "spreadsheets": ["XLSX", "CSV", "PDF"]
        }
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self.max_pages = 100  # Maximum pages for PDF conversion
        
        # Initialize directories
        self.temp_dir = Path("temp_uploads")
        self.temp_dir.mkdir(exist_ok=True)
        self.converted_files_dir = Path("converted_files")
        self.converted_files_dir.mkdir(exist_ok=True)
        
        # Initialize database tables
        self._ensure_tables_exist()
    
    def _ensure_tables_exist(self):
        """Ensure format converter database tables exist"""
        try:
            postgresql_client.ensure_converter_tables_exist()
        except Exception as e:
            print(f"Warning: Could not initialize format converter database tables: {e}")
    
    async def validate_file(self, file: UploadFile, target_format: str) -> bool:
        """Validate uploaded file for format conversion"""
        if file.size and file.size > self.max_file_size:
            raise HTTPException(status_code=400, detail="File size exceeds 50MB limit")
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        file_ext = os.path.splitext(file.filename.lower())[1][1:]  # Remove dot
        
        # Check if input format is supported
        all_input_formats = []
        for formats in self.supported_input_formats.values():
            all_input_formats.extend(formats)
        
        if file_ext.upper() not in all_input_formats:
            raise HTTPException(status_code=400, detail=f"Unsupported input format: {file_ext}")
        
        # Check if target format is supported
        all_output_formats = []
        for formats in self.supported_output_formats.values():
            all_output_formats.extend(formats)
        
        if target_format.upper() not in all_output_formats:
            raise HTTPException(status_code=400, detail=f"Unsupported output format: {target_format}")
        
        return True
    
    async def convert_pdf_to_images(
        self,
        file: UploadFile,
        output_format: str = "PNG",
        dpi: int = 200,
        quality: int = 90,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Convert PDF to image files"""
        
        start_time = time.time()
        conversion_id = str(uuid.uuid4())
        
        await self.validate_file(file, output_format)
        
        try:
            file_data = await file.read()
            await file.seek(0)
            
            # Convert PDF to images
            images = convert_from_bytes(file_data, dpi=dpi, fmt=output_format.lower())
            
            if len(images) > self.max_pages:
                raise HTTPException(status_code=400, detail=f"PDF has too many pages (max {self.max_pages})")
            
            converted_files = []
            total_output_size = 0
            
            for idx, image in enumerate(images):
                # Save each page as separate image
                page_buffer = io.BytesIO()
                
                if output_format.upper() == "JPG":
                    # Convert RGBA to RGB for JPEG
                    if image.mode == 'RGBA':
                        image = image.convert('RGB')
                    image.save(page_buffer, format='JPEG', quality=quality)
                else:
                    image.save(page_buffer, format=output_format.upper(), quality=quality)
                
                page_buffer.seek(0)
                page_size = page_buffer.tell()
                page_buffer.seek(0)
                total_output_size += page_size
                
                # Save to disk
                page_filename = f"page_{idx+1}.{output_format.lower()}"
                file_id = f"{conversion_id}_page_{idx+1}"
                storage_path = self.converted_files_dir / f"{file_id}.{output_format.lower()}"
                
                with open(storage_path, 'wb') as f:
                    f.write(page_buffer.getvalue())
                
                converted_files.append({
                    "file_id": file_id,
                    "filename": page_filename,
                    "page_number": idx + 1,
                    "size": page_size,
                    "storage_path": str(storage_path)
                })
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save to database
            conversion_data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "conversion_id": conversion_id,
                "conversion_type": "pdf_to_images",
                "input_format": "PDF",
                "output_format": output_format.upper(),
                "input_files": 1,
                "output_files": len(converted_files),
                "total_input_size": len(file_data),
                "total_output_size": total_output_size,
                "dpi": dpi,
                "quality": quality,
                "processing_time_ms": processing_time_ms,
                "original_filename": file.filename,
                "success": True
            }
            
            try:
                postgresql_client.save_conversion_data(conversion_data)
            except Exception as e:
                print(f"Warning: Could not save conversion data: {e}")
            
            return {
                "success": True,
                "conversion_id": conversion_id,
                "conversion_type": "pdf_to_images",
                "input_format": "PDF",
                "output_format": output_format.upper(),
                "input_filename": file.filename,
                "total_pages": len(images),
                "output_files": len(converted_files),
                "files": converted_files,
                "dpi": dpi,
                "quality": quality,
                "input_size_mb": round(len(file_data) / (1024 * 1024), 2),
                "output_size_mb": round(total_output_size / (1024 * 1024), 2),
                "processing_time_ms": processing_time_ms
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF to images conversion failed: {str(e)}")
    
    async def convert_images_to_pdf(
        self,
        files: List[UploadFile],
        page_size: str = "A4",
        quality: int = 90,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Convert multiple images to a single PDF"""
        
        start_time = time.time()
        conversion_id = str(uuid.uuid4())
        
        if len(files) == 0:
            raise HTTPException(status_code=400, detail="No files provided")
        
        if len(files) > self.max_pages:
            raise HTTPException(status_code=400, detail=f"Too many images (max {self.max_pages})")
        
        try:
            # Validate all files
            for file in files:
                await self.validate_file(file, "PDF")
            
            image_bytes_list = []
            total_input_size = 0
            
            for file in files:
                file_data = await file.read()
                await file.seek(0)
                total_input_size += len(file_data)
                
                # Load and process image
                image = Image.open(io.BytesIO(file_data))
                
                # Convert to RGB if needed
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Save as JPEG bytes for img2pdf
                img_buffer = io.BytesIO()
                image.save(img_buffer, format='JPEG', quality=quality)
                img_buffer.seek(0)
                image_bytes_list.append(img_buffer.getvalue())
            
            # Create PDF
            if page_size.upper() == "A4":
                layout_fun = img2pdf.get_layout_fun(img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
            else:  # Letter
                layout_fun = img2pdf.get_layout_fun(img2pdf.in_to_pt(8.5), img2pdf.in_to_pt(11))
            
            pdf_bytes = img2pdf.convert(image_bytes_list, layout_fun=layout_fun)
            
            # Save to disk
            pdf_filename = f"converted_images_to_pdf.pdf"
            storage_path = self.converted_files_dir / f"{conversion_id}.pdf"
            
            with open(storage_path, 'wb') as f:
                f.write(pdf_bytes)
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save to database
            conversion_data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "conversion_id": conversion_id,
                "conversion_type": "images_to_pdf",
                "input_format": "IMAGES",
                "output_format": "PDF",
                "input_files": len(files),
                "output_files": 1,
                "total_input_size": total_input_size,
                "total_output_size": len(pdf_bytes),
                "page_size": page_size,
                "quality": quality,
                "processing_time_ms": processing_time_ms,
                "original_filenames": [f.filename for f in files],
                "success": True
            }
            
            try:
                postgresql_client.save_conversion_data(conversion_data)
            except Exception as e:
                print(f"Warning: Could not save conversion data: {e}")
            
            return {
                "success": True,
                "conversion_id": conversion_id,
                "conversion_type": "images_to_pdf",
                "input_format": "IMAGES",
                "output_format": "PDF",
                "output_filename": pdf_filename,
                "input_files": len(files),
                "page_size": page_size,
                "quality": quality,
                "input_size_mb": round(total_input_size / (1024 * 1024), 2),
                "output_size_mb": round(len(pdf_bytes) / (1024 * 1024), 2),
                "processing_time_ms": processing_time_ms,
                "download_url": f"/format-converter/download/{conversion_id}",
                "file_data": pdf_bytes
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Images to PDF conversion failed: {str(e)}")
    
    async def convert_document_format(
        self,
        file: UploadFile,
        target_format: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Convert document between different formats"""
        
        start_time = time.time()
        conversion_id = str(uuid.uuid4())
        
        await self.validate_file(file, target_format)
        
        try:
            file_data = await file.read()
            await file.seek(0)
            
            input_ext = os.path.splitext(file.filename.lower())[1][1:]
            output_data = None
            content_type = "application/octet-stream"
            
            # Handle different conversion types
            if input_ext.upper() == "TXT" and target_format.upper() == "PDF":
                # Text to PDF
                output_buffer = io.BytesIO()
                c = canvas.Canvas(output_buffer, pagesize=letter)
                
                text_content = file_data.decode('utf-8', errors='ignore')
                lines = text_content.split('\n')
                
                y_position = 750
                for line in lines:
                    if y_position < 50:  # Start new page
                        c.showPage()
                        y_position = 750
                    c.drawString(50, y_position, line[:80])  # Limit line length
                    y_position -= 15
                
                c.save()
                output_buffer.seek(0)
                output_data = output_buffer.getvalue()
                content_type = "application/pdf"
                
            elif input_ext.upper() == "PDF" and target_format.upper() == "TXT":
                # PDF to Text (basic extraction)
                pdf_reader = PdfReader(io.BytesIO(file_data))
                text_content = ""
                
                for page in pdf_reader.pages:
                    text_content += page.extract_text() + "\n"
                
                output_data = text_content.encode('utf-8')
                content_type = "text/plain"
                
            else:
                raise HTTPException(status_code=400, detail=f"Conversion from {input_ext.upper()} to {target_format.upper()} not supported")
            
            if output_data is None:
                raise HTTPException(status_code=500, detail="Conversion failed - no output generated")
            
            # Save to disk
            output_filename = f"converted.{target_format.lower()}"
            storage_path = self.converted_files_dir / f"{conversion_id}.{target_format.lower()}"
            
            with open(storage_path, 'wb') as f:
                f.write(output_data)
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save to database
            conversion_data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "conversion_id": conversion_id,
                "conversion_type": "document_format",
                "input_format": input_ext.upper(),
                "output_format": target_format.upper(),
                "input_files": 1,
                "output_files": 1,
                "total_input_size": len(file_data),
                "total_output_size": len(output_data),
                "processing_time_ms": processing_time_ms,
                "original_filename": file.filename,
                "success": True
            }
            
            try:
                postgresql_client.save_conversion_data(conversion_data)
            except Exception as e:
                print(f"Warning: Could not save conversion data: {e}")
            
            return {
                "success": True,
                "conversion_id": conversion_id,
                "conversion_type": "document_format",
                "input_format": input_ext.upper(),
                "output_format": target_format.upper(),
                "input_filename": file.filename,
                "output_filename": output_filename,
                "input_size_mb": round(len(file_data) / (1024 * 1024), 2),
                "output_size_mb": round(len(output_data) / (1024 * 1024), 2),
                "processing_time_ms": processing_time_ms,
                "download_url": f"/format-converter/download/{conversion_id}",
                "file_data": output_data
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Document format conversion failed: {str(e)}")
    
    def get_converted_file(self, conversion_id: str) -> Optional[Tuple[Path, str]]:
        """Get converted file path and content type by conversion_id"""
        try:
            # Check for common formats
            for ext, content_type in [
                ("pdf", "application/pdf"),
                ("png", "image/png"),
                ("jpg", "image/jpeg"),
                ("jpeg", "image/jpeg"),
                ("txt", "text/plain"),
                ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            ]:
                file_path = self.converted_files_dir / f"{conversion_id}.{ext}"
                if file_path.exists():
                    return file_path, content_type
            
            return None
        except Exception as e:
            print(f"Error retrieving converted file {conversion_id}: {e}")
            return None


# Global instance
format_converter_service = FormatConverterService()
