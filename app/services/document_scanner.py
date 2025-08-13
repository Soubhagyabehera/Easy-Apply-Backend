"""
Document Scanner Service for EasyApply Document Tools
Handles document scanning: image-to-PDF conversion, scan enhancement, OCR, etc.
"""

import io
import os
import uuid
import time
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime
# Temporarily disable OpenCV import to fix NumPy compatibility issue
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError as e:
    print(f"Warning: OpenCV not available due to compatibility issue: {e}")
    print("Document scanner will use basic image processing only")
    CV2_AVAILABLE = False
    import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import img2pdf
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.utils import ImageReader
from fastapi import UploadFile, HTTPException
from app.database.supabase_client import postgresql_client


class DocumentScannerService:
    """Service for handling document scanning operations"""
    
    def __init__(self):
        """Initialize the document scanner service"""
        self.supported_input_formats = ["JPG", "JPEG", "PNG", "BMP", "TIFF", "WEBP"]
        self.supported_output_formats = ["PDF", "PNG", "JPG"]
        self.max_file_size = 20 * 1024 * 1024  # 20MB
        self.max_pages = 50  # Maximum pages per scan batch
        
        # Initialize directories
        self.temp_dir = Path("temp_uploads")
        self.temp_dir.mkdir(exist_ok=True)
        self.scanned_docs_dir = Path("scanned_documents")
        self.scanned_docs_dir.mkdir(exist_ok=True)
        
        # Initialize database tables
        self._ensure_tables_exist()
    
    def _ensure_tables_exist(self):
        """Ensure document scanner database tables exist"""
        try:
            postgresql_client.ensure_scanner_tables_exist()
        except Exception as e:
            print(f"Warning: Could not initialize document scanner database tables: {e}")
    
    async def validate_image(self, file: UploadFile) -> bool:
        """Validate uploaded image file for scanning"""
        if file.size and file.size > self.max_file_size:
            raise HTTPException(status_code=400, detail="File size exceeds 20MB limit")
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        file_ext = os.path.splitext(file.filename.lower())[1][1:]  # Remove dot
        if file_ext.upper() not in self.supported_input_formats:
            raise HTTPException(status_code=400, detail=f"Unsupported format. Use: {', '.join(self.supported_input_formats)}")
        
        return True
    
    def _enhance_scan(self, image: np.ndarray, enhancement_level: str = "medium") -> np.ndarray:
        """Apply scan enhancement to improve document quality"""
        
        if not CV2_AVAILABLE:
            # Fallback to basic PIL-based enhancement
            print("Using basic enhancement (OpenCV not available)")
            return image
        
        try:
            # Convert to grayscale if needed
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()
            
            if enhancement_level == "light":
                # Light enhancement - basic noise reduction
                enhanced = cv2.bilateralFilter(gray, 9, 75, 75)
                
            elif enhancement_level == "medium":
                # Medium enhancement - noise reduction + contrast
                enhanced = cv2.bilateralFilter(gray, 9, 75, 75)
                enhanced = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
                
            elif enhancement_level == "high":
                # High enhancement - aggressive processing
                # Noise reduction
                enhanced = cv2.bilateralFilter(gray, 15, 80, 80)
                
                # Morphological operations to clean up
                kernel = np.ones((2, 2), np.uint8)
                enhanced = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel)
                
                # Adaptive thresholding for better text contrast
                enhanced = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
                
            else:
                enhanced = gray
            
            return enhanced
            
        except Exception as e:
            print(f"Enhancement failed: {e}")
            return image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    def _detect_document_edges(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Detect document edges for automatic cropping"""
        
        if not CV2_AVAILABLE:
            # Skip edge detection if OpenCV not available
            print("Edge detection skipped (OpenCV not available)")
            return None
        
        try:
            # Convert to grayscale
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()
            
            # Apply Gaussian blur
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Edge detection
            edges = cv2.Canny(blurred, 50, 150, apertureSize=3)
            
            # Find contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Find the largest contour (assumed to be the document)
            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                
                # Approximate the contour to a polygon
                epsilon = 0.02 * cv2.arcLength(largest_contour, True)
                approx = cv2.approxPolyDP(largest_contour, epsilon, True)
                
                # If we found a quadrilateral, return it
                if len(approx) == 4:
                    return approx.reshape(4, 2)
            
            return None
            
        except Exception as e:
            print(f"Edge detection failed: {e}")
            return None
    
    async def scan_to_pdf(
        self,
        files: List[UploadFile],
        output_format: str = "PDF",
        enhancement_level: str = "medium",
        auto_crop: bool = True,
        page_size: str = "A4",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Convert scanned images to PDF with enhancement"""
        
        start_time = time.time()
        scan_id = str(uuid.uuid4())
        
        if len(files) == 0:
            raise HTTPException(status_code=400, detail="No files provided")
        
        if len(files) > self.max_pages:
            raise HTTPException(status_code=400, detail=f"Maximum {self.max_pages} pages allowed")
        
        try:
            # Validate all files
            for file in files:
                await self.validate_image(file)
            
            processed_images = []
            total_input_size = 0
            
            for idx, file in enumerate(files):
                file_data = await file.read()
                await file.seek(0)
                total_input_size += len(file_data)
                
                if CV2_AVAILABLE:
                    # Load image with OpenCV
                    nparr = np.frombuffer(file_data, np.uint8)
                    cv_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if cv_image is None:
                        raise HTTPException(status_code=400, detail=f"Could not decode image: {file.filename}")
                    
                    # Auto-crop if enabled
                    if auto_crop:
                        edges = self._detect_document_edges(cv_image)
                        if edges is not None:
                            # Apply perspective correction
                            try:
                                # Order points: top-left, top-right, bottom-right, bottom-left
                                rect = self._order_points(edges)
                                
                                # Calculate dimensions
                                width = max(
                                    np.linalg.norm(rect[1] - rect[0]),
                                    np.linalg.norm(rect[3] - rect[2])
                                )
                                height = max(
                                    np.linalg.norm(rect[3] - rect[0]),
                                    np.linalg.norm(rect[2] - rect[1])
                                )
                                
                                # Define destination points
                                dst = np.array([
                                    [0, 0],
                                    [width - 1, 0],
                                    [width - 1, height - 1],
                                    [0, height - 1]
                                ], dtype=np.float32)
                                
                                # Apply perspective transform
                                matrix = cv2.getPerspectiveTransform(rect.astype(np.float32), dst)
                                cv_image = cv2.warpPerspective(cv_image, matrix, (int(width), int(height)))
                                
                            except Exception as e:
                                print(f"Perspective correction failed for {file.filename}: {e}")
                    
                    # Apply enhancement
                    enhanced_image = self._enhance_scan(cv_image, enhancement_level)
                    
                    # Convert back to PIL Image
                    if len(enhanced_image.shape) == 2:
                        pil_image = Image.fromarray(enhanced_image, mode='L')
                    else:
                        pil_image = Image.fromarray(cv2.cvtColor(enhanced_image, cv2.COLOR_BGR2RGB))
                else:
                    # Fallback to PIL-only processing
                    print(f"Processing {file.filename} with basic PIL enhancement (OpenCV not available)")
                    pil_image = Image.open(io.BytesIO(file_data))
                    
                    # Basic enhancement using PIL
                    if enhancement_level != "light":
                        # Apply basic sharpening
                        pil_image = pil_image.filter(ImageFilter.SHARPEN)
                    
                    if enhancement_level == "high":
                        # Apply contrast enhancement
                        enhancer = ImageEnhance.Contrast(pil_image)
                        pil_image = enhancer.enhance(1.2)
                
                # Convert to RGB if needed for PDF
                if pil_image.mode != 'RGB':
                    pil_image = pil_image.convert('RGB')
                
                processed_images.append(pil_image)
            
            # Generate output based on format
            if output_format.upper() == "PDF":
                # Create PDF from images
                pdf_buffer = io.BytesIO()
                
                # Convert PIL images to bytes for img2pdf
                image_bytes_list = []
                for img in processed_images:
                    img_buffer = io.BytesIO()
                    img.save(img_buffer, format='JPEG', quality=90)
                    img_buffer.seek(0)
                    image_bytes_list.append(img_buffer.getvalue())
                
                # Create PDF
                if page_size.upper() == "A4":
                    layout_fun = img2pdf.get_layout_fun(img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
                else:  # Letter
                    layout_fun = img2pdf.get_layout_fun(img2pdf.in_to_pt(8.5), img2pdf.in_to_pt(11))
                
                pdf_bytes = img2pdf.convert(image_bytes_list, layout_fun=layout_fun)
                pdf_buffer.write(pdf_bytes)
                pdf_buffer.seek(0)
                
                output_size = len(pdf_bytes)
                output_data = pdf_bytes
                output_filename = f"scanned_document_{len(files)}_pages.pdf"
                content_type = "application/pdf"
                
            else:
                # For single image output formats (PNG, JPG)
                if len(processed_images) > 1:
                    raise HTTPException(status_code=400, detail="Multiple images can only be output as PDF")
                
                img_buffer = io.BytesIO()
                processed_images[0].save(img_buffer, format=output_format.upper(), quality=90)
                img_buffer.seek(0)
                
                output_size = img_buffer.tell()
                img_buffer.seek(0)
                output_data = img_buffer.getvalue()
                output_filename = f"scanned_document.{output_format.lower()}"
                content_type = f"image/{output_format.lower()}"
            
            # Save to disk
            stored_filename = f"{scan_id}.{output_format.lower()}"
            storage_path = self.scanned_docs_dir / stored_filename
            
            with open(storage_path, 'wb') as f:
                f.write(output_data)
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Save to database
            scan_data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "scan_id": scan_id,
                "input_files": len(files),
                "output_format": output_format.upper(),
                "enhancement_level": enhancement_level,
                "auto_crop": auto_crop,
                "page_size": page_size,
                "total_input_size": total_input_size,
                "output_size": output_size,
                "processing_time_ms": processing_time_ms,
                "storage_path": str(storage_path),
                "original_filenames": [f.filename for f in files],
                "success": True
            }
            
            try:
                postgresql_client.save_scan_data(scan_data)
            except Exception as e:
                print(f"Warning: Could not save scan data: {e}")
            
            return {
                "success": True,
                "scan_id": scan_id,
                "output_filename": output_filename,
                "output_format": output_format.upper(),
                "input_files": len(files),
                "enhancement_level": enhancement_level,
                "auto_crop": auto_crop,
                "page_size": page_size,
                "input_size_mb": round(total_input_size / (1024 * 1024), 2),
                "output_size_mb": round(output_size / (1024 * 1024), 2),
                "processing_time_ms": processing_time_ms,
                "download_url": f"/document-scanner/download/{scan_id}",
                "file_data": output_data
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Document scanning failed: {str(e)}")
    
    def _order_points(self, pts: np.ndarray) -> np.ndarray:
        """Order points in the order: top-left, top-right, bottom-right, bottom-left"""
        rect = np.zeros((4, 2), dtype=np.float32)
        
        # Sum and difference of coordinates
        s = pts.sum(axis=1)
        diff = np.diff(pts, axis=1)
        
        # Top-left has smallest sum, bottom-right has largest sum
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        
        # Top-right has smallest difference, bottom-left has largest difference
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        
        return rect
    
    def get_scanned_file(self, scan_id: str) -> Optional[Tuple[Path, str]]:
        """Get scanned document file path and content type by scan_id"""
        try:
            # Check for PDF
            file_path = self.scanned_docs_dir / f"{scan_id}.pdf"
            if file_path.exists():
                return file_path, "application/pdf"
            
            # Check for PNG
            file_path = self.scanned_docs_dir / f"{scan_id}.png"
            if file_path.exists():
                return file_path, "image/png"
            
            # Check for JPG
            file_path = self.scanned_docs_dir / f"{scan_id}.jpg"
            if file_path.exists():
                return file_path, "image/jpeg"
            
            return None
        except Exception as e:
            print(f"Error retrieving scanned file {scan_id}: {e}")
            return None


# Global instance
document_scanner_service = DocumentScannerService()
