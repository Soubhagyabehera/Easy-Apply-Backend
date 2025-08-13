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
            if compression_level == "high":
                pdf_writer.compress_identical_objects()
                pdf_writer.remove_duplication()
            elif compression_level == "medium":
                pdf_writer.compress_identical_objects()
            # For "low", no additional compression
            
            # Generate compressed output
            output_buffer = io.BytesIO()
            pdf_writer.write(output_buffer)
            output_buffer.seek(0)
            compressed_size = output_buffer.tell()
            output_buffer.seek(0)
            
            # Calculate compression ratio
            compression_ratio = round((1 - compressed_size / original_size) * 100, 1)
            
            # Save to disk
            processed_filename = f"compressed_{file.filename}"
            stored_filename = f"{file_id}.pdf"
            storage_path = self.processed_files_dir / stored_filename
            
            with open(storage_path, 'wb') as f:
                f.write(output_buffer.getvalue())
            
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


# Global instance
pdf_tools_service = PDFToolsService()
