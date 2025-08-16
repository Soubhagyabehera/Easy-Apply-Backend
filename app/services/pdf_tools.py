"""
PDF Tools Service for EasyApply Document Tools
Handles PDF operations: merge, split, compress, extract pages, etc.
"""

import io
import os
import uuid
import time
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime
import PyPDF2
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image
import img2pdf
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
import fitz  # PyMuPDF for PDF to image conversion
from fastapi import UploadFile, HTTPException
from app.database.supabase_client import postgresql_client


class PDFToolsService:
    """Service for handling PDF operations"""
    
    def __init__(self):
        """Initialize the PDF tools service"""
        self.supported_formats = ["PDF"]
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self.max_pages = 1000  # Maximum pages per PDF
        
        # Initialize directories
        self.temp_dir = Path("temp_uploads")
        self.temp_dir.mkdir(exist_ok=True)
        self.processed_files_dir = Path("processed_pdfs")
        self.processed_files_dir.mkdir(exist_ok=True)
        self.pdf_images_dir = Path("pdf_images")
        self.pdf_images_dir.mkdir(exist_ok=True)
        
        # Initialize database tables
        self._ensure_tables_exist()
    
    def _ensure_tables_exist(self):
        """Ensure PDF tools database tables exist"""
        try:
            postgresql_client.ensure_pdf_tools_tables_exist()
        except Exception as e:
            print(f"Warning: Could not initialize PDF tools database tables: {e}")
    
    async def validate_pdf(self, file: UploadFile) -> bool:
        """Validate uploaded PDF file"""
        if file.size and file.size > self.max_file_size:
            raise HTTPException(status_code=400, detail="File size exceeds 50MB limit")
        
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        return True
    
    async def merge_pdfs(
        self,
        files: List[UploadFile],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Merge multiple PDF files into one"""
        
        start_time = time.time()
        file_id = str(uuid.uuid4())
        
        if len(files) < 2:
            raise HTTPException(status_code=400, detail="At least 2 PDF files required for merging")
        
        if len(files) > 20:
            raise HTTPException(status_code=400, detail="Maximum 20 files allowed for merging")
        
        try:
            # Validate all files
            for file in files:
                await self.validate_pdf(file)
            
            # Create merged PDF
            pdf_writer = PdfWriter()
            total_pages = 0
            original_sizes = []
            
            for file in files:
                file_data = await file.read()
                await file.seek(0)
                original_sizes.append(len(file_data))
                
                pdf_reader = PdfReader(io.BytesIO(file_data))
                total_pages += len(pdf_reader.pages)
                
                if total_pages > self.max_pages:
                    raise HTTPException(status_code=400, detail=f"Total pages exceed {self.max_pages} limit")
                
                for page in pdf_reader.pages:
                    pdf_writer.add_page(page)
            
            # Generate output
            output_buffer = io.BytesIO()
            pdf_writer.write(output_buffer)
            output_buffer.seek(0)
            output_size = output_buffer.tell()
            output_buffer.seek(0)
            
            # Save to disk
            processed_filename = f"merged_{len(files)}_files.pdf"
            stored_filename = f"{file_id}.pdf"
            storage_path = self.processed_files_dir / stored_filename
            
            with open(storage_path, 'wb') as f:
                f.write(output_buffer.getvalue())
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save to database
            processing_data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "operation_type": "merge",
                "input_files": len(files),
                "total_input_size": sum(original_sizes),
                "output_size": output_size,
                "total_pages": total_pages,
                "processing_time_ms": processing_time_ms,
                "success": True,
                "error_message": None,
                "file_id": file_id,
                "storage_path": str(storage_path),
                "original_filenames": [f.filename for f in files]
            }
            
            try:
                postgresql_client.save_pdf_processing_history(processing_data)
            except Exception as e:
                print(f"Warning: Could not save processing history: {e}")
            
            return {
                "success": True,
                "file_id": file_id,
                "processed_filename": processed_filename,
                "total_pages": total_pages,
                "input_files": len(files),
                "original_size_mb": round(sum(original_sizes) / (1024 * 1024), 2),
                "processed_size_mb": round(output_size / (1024 * 1024), 2),
                "processing_time_ms": processing_time_ms,
                "file_data": output_buffer.getvalue()
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF merge failed: {str(e)}")
    
    async def split_pdf(
        self,
        file: UploadFile,
        split_type: str = "pages",  # "pages", "range", "bookmarks"
        split_config: Dict[str, Any] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Split PDF into multiple files"""
        
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        
        await self.validate_pdf(file)
        
        if split_config is None:
            split_config = {}
        
        try:
            file_data = await file.read()
            await file.seek(0)
            
            pdf_reader = PdfReader(io.BytesIO(file_data))
            total_pages = len(pdf_reader.pages)
            
            if total_pages < 2:
                raise HTTPException(status_code=400, detail="PDF must have at least 2 pages to split")
            
            output_files = []
            
            if split_type == "pages":
                # Split each page into separate file
                pages_per_file = split_config.get("pages_per_file", 1)
                
                for i in range(0, total_pages, pages_per_file):
                    pdf_writer = PdfWriter()
                    end_page = min(i + pages_per_file, total_pages)
                    
                    for page_num in range(i, end_page):
                        pdf_writer.add_page(pdf_reader.pages[page_num])
                    
                    output_buffer = io.BytesIO()
                    pdf_writer.write(output_buffer)
                    output_buffer.seek(0)
                    
                    file_id = str(uuid.uuid4())
                    filename = f"page_{i+1}_to_{end_page}.pdf"
                    
                    # Save to disk
                    storage_path = self.processed_files_dir / f"{file_id}.pdf"
                    with open(storage_path, 'wb') as f:
                        f.write(output_buffer.getvalue())
                    
                    output_files.append({
                        "file_id": file_id,
                        "filename": filename,
                        "pages": f"{i+1}-{end_page}",
                        "size": output_buffer.tell(),
                        "storage_path": str(storage_path)
                    })
            
            elif split_type == "range":
                # Split by page ranges
                ranges = split_config.get("ranges", [])
                if not ranges:
                    raise HTTPException(status_code=400, detail="Page ranges required for range split")
                
                for idx, page_range in enumerate(ranges):
                    start_page = page_range.get("start", 1) - 1  # Convert to 0-based
                    end_page = page_range.get("end", total_pages)
                    
                    if start_page < 0 or end_page > total_pages or start_page >= end_page:
                        continue
                    
                    pdf_writer = PdfWriter()
                    for page_num in range(start_page, end_page):
                        pdf_writer.add_page(pdf_reader.pages[page_num])
                    
                    output_buffer = io.BytesIO()
                    pdf_writer.write(output_buffer)
                    output_buffer.seek(0)
                    
                    file_id = str(uuid.uuid4())
                    filename = f"pages_{start_page+1}_to_{end_page}.pdf"
                    
                    # Save to disk
                    storage_path = self.processed_files_dir / f"{file_id}.pdf"
                    with open(storage_path, 'wb') as f:
                        f.write(output_buffer.getvalue())
                    
                    output_files.append({
                        "file_id": file_id,
                        "filename": filename,
                        "pages": f"{start_page+1}-{end_page}",
                        "size": output_buffer.tell(),
                        "storage_path": str(storage_path)
                    })
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save batch processing data
            batch_data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "operation_type": "split",
                "batch_id": batch_id,
                "input_files": 1,
                "output_files": len(output_files),
                "total_input_size": len(file_data),
                "total_output_size": sum(f["size"] for f in output_files),
                "total_pages": total_pages,
                "processing_time_ms": processing_time_ms,
                "success": True,
                "original_filename": file.filename
            }
            
            try:
                postgresql_client.save_pdf_batch_processing(batch_data)
            except Exception as e:
                print(f"Warning: Could not save batch processing data: {e}")
            
            return {
                "success": True,
                "batch_id": batch_id,
                "operation": "split",
                "input_filename": file.filename,
                "total_pages": total_pages,
                "output_files": len(output_files),
                "files": output_files,
                "processing_time_ms": processing_time_ms
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF split failed: {str(e)}")
    
    async def compress_pdf(
        self,
        file: UploadFile,
        compression_level: str = "medium",  # "low", "medium", "high"
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Compress PDF file to reduce size"""
        
        start_time = time.time()
        file_id = str(uuid.uuid4())
        
        await self.validate_pdf(file)
        
        try:
            file_data = await file.read()
            await file.seek(0)
            original_size = len(file_data)
            
            pdf_reader = PdfReader(io.BytesIO(file_data))
            pdf_writer = PdfWriter()
            
            # Add all pages to writer
            for page in pdf_reader.pages:
                pdf_writer.add_page(page)
            
            # Apply compression based on level
            try:
                if compression_level == "high":
                    # Try advanced compression methods if available
                    if hasattr(pdf_writer, 'compress_identical_objects'):
                        pdf_writer.compress_identical_objects()
                    if hasattr(pdf_writer, 'remove_duplication'):
                        pdf_writer.remove_duplication()
                elif compression_level == "medium":
                    # Try basic compression if available
                    if hasattr(pdf_writer, 'compress_identical_objects'):
                        pdf_writer.compress_identical_objects()
                # For "low", no additional compression
            except Exception as compression_error:
                # If compression methods fail, continue without them
                print(f"Warning: Compression method failed: {compression_error}")
                pass
            
            # Generate compressed output
            output_buffer = io.BytesIO()
            pdf_writer.write(output_buffer)
            compressed_size = output_buffer.tell()
            output_buffer.seek(0)
            
            # Save to disk
            processed_filename = f"compressed_{file.filename}"
            stored_filename = f"{file_id}.pdf"
            storage_path = self.processed_files_dir / stored_filename
            
            with open(storage_path, 'wb') as f:
                f.write(output_buffer.getvalue())
            
            # Calculate compression ratio
            compression_ratio = round((1 - compressed_size / original_size) * 100, 1) if original_size > 0 else 0
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save processing data
            processing_data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "operation_type": "compress",
                "input_files": 1,
                "total_input_size": original_size,
                "output_size": compressed_size,
                "compression_ratio": compression_ratio,
                "compression_level": compression_level,
                "processing_time_ms": processing_time_ms,
                "success": True,
                "error_message": None,
                "file_id": file_id,
                "storage_path": str(storage_path),
                "original_filenames": [file.filename]
            }
            
            try:
                postgresql_client.save_pdf_processing_history(processing_data)
            except Exception as e:
                print(f"Warning: Could not save processing history: {e}")
            
            return {
                "success": True,
                "file_id": file_id,
                "original_filename": file.filename,
                "processed_filename": processed_filename,
                "original_size_mb": round(original_size / (1024 * 1024), 2),
                "compressed_size_mb": round(compressed_size / (1024 * 1024), 2),
                "compression_ratio": compression_ratio,
                "compression_level": compression_level,
                "processing_time_ms": processing_time_ms,
                "file_data": output_buffer.getvalue()
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF compression failed: {str(e)}")
    
    def get_processed_file(self, file_id: str) -> Optional[Tuple[Path, str]]:
        """Get processed PDF file path and content type by file_id"""
        try:
            file_path = self.processed_files_dir / f"{file_id}.pdf"
            if file_path.exists():
                return file_path, "application/pdf"
            return None
        except Exception as e:
            print(f"Error retrieving PDF file {file_id}: {e}")
            return None
    
    async def combine_documents_to_pdf(
        self,
        files: List[UploadFile],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Combine different document types (images, PDFs) into a single PDF"""
        
        start_time = time.time()
        file_id = str(uuid.uuid4())
        
        if not files or len(files) < 2:
            raise HTTPException(status_code=400, detail="At least 2 files required for combining")
        
        if len(files) > 20:
            raise HTTPException(status_code=400, detail="Maximum 20 files allowed")
        
        try:
            pdf_writer = PdfWriter()
            original_sizes = []
            processed_files = []
            
            for file in files:
                file_data = await file.read()
                await file.seek(0)
                original_sizes.append(len(file_data))
                
                file_extension = Path(file.filename).suffix.lower()
                
                if file_extension == '.pdf':
                    # Handle PDF files
                    pdf_reader = PdfReader(io.BytesIO(file_data))
                    for page in pdf_reader.pages:
                        pdf_writer.add_page(page)
                    processed_files.append({"filename": file.filename, "type": "pdf", "pages": len(pdf_reader.pages)})
                    
                elif file_extension in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif']:
                    # Handle image files - convert to PDF
                    try:
                        # Convert image to PDF using img2pdf
                        image_pdf_bytes = img2pdf.convert(file_data)
                        image_pdf_reader = PdfReader(io.BytesIO(image_pdf_bytes))
                        for page in image_pdf_reader.pages:
                            pdf_writer.add_page(page)
                        processed_files.append({"filename": file.filename, "type": "image", "pages": 1})
                    except Exception as img_error:
                        # Fallback: use PIL and reportlab
                        image = Image.open(io.BytesIO(file_data))
                        if image.mode != 'RGB':
                            image = image.convert('RGB')
                        
                        # Create PDF page with image
                        img_buffer = io.BytesIO()
                        c = canvas.Canvas(img_buffer, pagesize=A4)
                        
                        # Calculate image dimensions to fit A4
                        img_width, img_height = image.size
                        page_width, page_height = A4
                        
                        # Scale image to fit page while maintaining aspect ratio
                        scale = min(page_width / img_width, page_height / img_height) * 0.8
                        scaled_width = img_width * scale
                        scaled_height = img_height * scale
                        
                        # Center image on page
                        x = (page_width - scaled_width) / 2
                        y = (page_height - scaled_height) / 2
                        
                        # Save image temporarily
                        temp_img_path = self.temp_dir / f"temp_{uuid.uuid4()}.jpg"
                        image.save(temp_img_path, 'JPEG')
                        
                        c.drawImage(str(temp_img_path), x, y, scaled_width, scaled_height)
                        c.save()
                        
                        # Clean up temp image
                        temp_img_path.unlink()
                        
                        img_buffer.seek(0)
                        img_pdf_reader = PdfReader(img_buffer)
                        for page in img_pdf_reader.pages:
                            pdf_writer.add_page(page)
                        processed_files.append({"filename": file.filename, "type": "image", "pages": 1})
                else:
                    raise HTTPException(status_code=400, detail=f"Unsupported file format: {file_extension}")
            
            # Generate combined PDF
            output_buffer = io.BytesIO()
            pdf_writer.write(output_buffer)
            output_buffer.seek(0)
            
            # Save to disk first to get actual file size
            processed_filename = f"combined_documents.pdf"
            stored_filename = f"{file_id}.pdf"
            storage_path = self.processed_files_dir / stored_filename
            
            with open(storage_path, 'wb') as f:
                f.write(output_buffer.getvalue())
            
            # Get actual file size from disk
            output_size = storage_path.stat().st_size
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            total_pages = sum([f["pages"] for f in processed_files])
            
            return {
                "success": True,
                "file_id": file_id,
                "processed_filename": processed_filename,
                "total_pages": total_pages,
                "input_files": len(files),
                "original_size_mb": round(sum(original_sizes) / (1024 * 1024), 2),
                "processed_size_mb": round(output_size / (1024 * 1024), 2),
                "processing_time_ms": processing_time_ms,
                "processed_files": processed_files
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Document combination failed: {str(e)}")
    
    async def pdf_to_images(
        self,
        file: UploadFile,
        image_format: str = "png",  # "png", "jpg", "jpeg"
        dpi: int = 150,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Convert each page of PDF to individual images"""
        
        start_time = time.time()
        batch_id = str(uuid.uuid4())
        
        await self.validate_pdf(file)
        
        if image_format.lower() not in ['png', 'jpg', 'jpeg']:
            raise HTTPException(status_code=400, detail="Supported formats: png, jpg, jpeg")
        
        if dpi < 72 or dpi > 300:
            raise HTTPException(status_code=400, detail="DPI must be between 72 and 300")
        
        try:
            file_data = await file.read()
            await file.seek(0)
            
            # Use PyMuPDF for better image quality
            pdf_document = fitz.open(stream=file_data, filetype="pdf")
            total_pages = pdf_document.page_count
            
            if total_pages > 100:
                raise HTTPException(status_code=400, detail="PDF has too many pages (max 100 for image conversion)")
            
            output_images = []
            
            for page_num in range(total_pages):
                page = pdf_document[page_num]
                
                # Render page to image
                mat = fitz.Matrix(dpi/72, dpi/72)  # Scale matrix for DPI
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PIL Image
                img_data = pix.tobytes("ppm")
                image = Image.open(io.BytesIO(img_data))
                
                # Convert format if needed
                if image_format.lower() in ['jpg', 'jpeg']:
                    if image.mode != 'RGB':
                        image = image.convert('RGB')
                    format_ext = 'JPEG'
                    file_ext = 'jpg'
                else:
                    format_ext = 'PNG'
                    file_ext = 'png'
                
                # Save image
                image_id = str(uuid.uuid4())
                filename = f"page_{page_num + 1}.{file_ext}"
                storage_path = self.pdf_images_dir / f"{image_id}.{file_ext}"
                
                image.save(storage_path, format_ext, quality=95 if format_ext == 'JPEG' else None)
                
                output_images.append({
                    "image_id": image_id,
                    "filename": filename,
                    "page_number": page_num + 1,
                    "format": image_format,
                    "size": storage_path.stat().st_size,
                    "storage_path": str(storage_path),
                    "width": image.width,
                    "height": image.height
                })
            
            pdf_document.close()
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                "success": True,
                "batch_id": batch_id,
                "input_filename": file.filename,
                "total_pages": total_pages,
                "output_images": len(output_images),
                "image_format": image_format,
                "dpi": dpi,
                "images": output_images,
                "processing_time_ms": processing_time_ms
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF to images conversion failed: {str(e)}")
    
    async def combine_pdfs(
        self,
        files: List[UploadFile],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Combine multiple PDF files into one (enhanced version of merge_pdfs)"""
        
        start_time = time.time()
        file_id = str(uuid.uuid4())
        
        if not files or len(files) < 2:
            raise HTTPException(status_code=400, detail="At least 2 PDF files required for combining")
        
        if len(files) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 PDF files allowed")
        
        try:
            pdf_writer = PdfWriter()
            original_sizes = []
            pdf_info = []
            total_pages = 0
            
            for file in files:
                await self.validate_pdf(file)
                file_data = await file.read()
                await file.seek(0)
                original_sizes.append(len(file_data))
                
                pdf_reader = PdfReader(io.BytesIO(file_data))
                pages_count = len(pdf_reader.pages)
                total_pages += pages_count
                
                # Add all pages from this PDF
                for page in pdf_reader.pages:
                    pdf_writer.add_page(page)
                
                pdf_info.append({
                    "filename": file.filename,
                    "pages": pages_count,
                    "size_mb": round(len(file_data) / (1024 * 1024), 2)
                })
            
            if total_pages > self.max_pages:
                raise HTTPException(status_code=400, detail=f"Total pages exceed limit ({self.max_pages})")
            
            # Generate combined PDF
            output_buffer = io.BytesIO()
            pdf_writer.write(output_buffer)
            output_buffer.seek(0)
            output_size = output_buffer.tell()
            output_buffer.seek(0)
            
            # Save to disk
            processed_filename = f"combined_{len(files)}_pdfs.pdf"
            stored_filename = f"{file_id}.pdf"
            storage_path = self.processed_files_dir / stored_filename
            
            with open(storage_path, 'wb') as f:
                f.write(output_buffer.getvalue())
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                "success": True,
                "file_id": file_id,
                "processed_filename": processed_filename,
                "total_pages": total_pages,
                "input_files": len(files),
                "original_size_mb": round(sum(original_sizes) / (1024 * 1024), 2),
                "processed_size_mb": round(output_size / (1024 * 1024), 2),
                "processing_time_ms": processing_time_ms,
                "pdf_info": pdf_info
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF combination failed: {str(e)}")
    
    def get_processed_image(self, image_id: str) -> Optional[Tuple[Path, str]]:
        """Get processed image file path and content type by image_id"""
        try:
            # Check for different image formats
            for ext, content_type in [('.png', 'image/png'), ('.jpg', 'image/jpeg'), ('.jpeg', 'image/jpeg')]:
                file_path = self.pdf_images_dir / f"{image_id}{ext}"
                if file_path.exists():
                    return file_path, content_type
            return None
        except Exception as e:
            print(f"Error retrieving image file {image_id}: {e}")
            return None


# Global instance
pdf_tools_service = PDFToolsService()
