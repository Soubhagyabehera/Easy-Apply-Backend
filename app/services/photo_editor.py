"""
Photo Editor Service for EasyApply Document Tools
Handles advanced image processing, resizing, format conversion, background removal, and face detection.
"""

import io
import os
import uuid
import time
import numpy as np
import cv2
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import img2pdf
from fastapi import UploadFile, HTTPException
from pathlib import Path
from datetime import datetime
from app.database.supabase_client import postgresql_client

# Advanced image processing libraries
try:
    from rembg import remove, new_session
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False
    print("Warning: rembg not available. Background removal will use basic methods.")

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    print("Warning: mediapipe not available. Face detection will use OpenCV.")

try:
    from skimage import filters, morphology, segmentation
    SCIKIT_IMAGE_AVAILABLE = True
except ImportError:
    SCIKIT_IMAGE_AVAILABLE = False
    print("Warning: scikit-image not available. Advanced image processing limited.")

class PhotoEditorService:
    """Service for handling photo editing operations"""
    
    def __init__(self):
        """Initialize the photo editor service with advanced features"""
        self.supported_formats = ["JPG", "JPEG", "PNG", "PDF"]
        self.max_file_size = 10 * 1024 * 1024  # 10MB input limit
        self.min_output_size_kb = 10  # 10KB minimum output
        self.max_output_size_kb = 2048  # 2MB maximum output
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
        
        # Initialize advanced processing models
        self._init_face_detection()
        self._init_background_removal()
    
    def _ensure_tables_exist(self):
        """Ensure photo editor database tables exist"""
        try:
            postgresql_client.ensure_photo_editor_tables_exist()
        except Exception as e:
            print(f"Warning: Could not initialize photo editor database tables: {e}")
    
    def _init_face_detection(self):
        """Initialize face detection models"""
        self.face_cascade = None
        self.mp_face_detection = None
        self.mp_drawing = None
        
        try:
            # Try to load OpenCV face cascade
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            if os.path.exists(cascade_path):
                self.face_cascade = cv2.CascadeClassifier(cascade_path)
                print("OpenCV face detection initialized")
        except Exception as e:
            print(f"Warning: Could not initialize OpenCV face detection: {e}")
        
        try:
            # Try to initialize MediaPipe face detection
            if MEDIAPIPE_AVAILABLE:
                self.mp_face_detection = mp.solutions.face_detection.FaceDetection(
                    model_selection=0, min_detection_confidence=0.5
                )
                self.mp_drawing = mp.solutions.drawing_utils
                print("MediaPipe face detection initialized")
        except Exception as e:
            print(f"Warning: Could not initialize MediaPipe face detection: {e}")
    
    def _init_background_removal(self):
        """Initialize background removal models"""
        self.bg_removal_session = None
        
        try:
            if REMBG_AVAILABLE:
                # Initialize rembg session for better performance
                self.bg_removal_session = new_session('u2net')
                print("Background removal (rembg) initialized")
        except Exception as e:
            print(f"Warning: Could not initialize background removal: {e}")
    
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
    
    def _detect_faces(self, image: Image.Image) -> List[Tuple[int, int, int, int]]:
        """Detect faces in image and return bounding boxes"""
        faces = []
        
        # Convert PIL to OpenCV format
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        
        try:
            # Try MediaPipe first (more accurate)
            if self.mp_face_detection and MEDIAPIPE_AVAILABLE:
                rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
                results = self.mp_face_detection.process(rgb_image)
                
                if results.detections:
                    h, w, _ = rgb_image.shape
                    for detection in results.detections:
                        bbox = detection.location_data.relative_bounding_box
                        x = int(bbox.xmin * w)
                        y = int(bbox.ymin * h)
                        width = int(bbox.width * w)
                        height = int(bbox.height * h)
                        faces.append((x, y, width, height))
                        
            # Fallback to OpenCV if MediaPipe fails or not available
            elif self.face_cascade is not None:
                gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
                detected_faces = self.face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
                )
                faces = [(x, y, w, h) for (x, y, w, h) in detected_faces]
                
        except Exception as e:
            print(f"Warning: Face detection failed: {e}")
            
        return faces
    
    def _center_crop_face(self, image: Image.Image, target_width: int, target_height: int) -> Image.Image:
        """Center crop image around detected face for ID/passport style"""
        faces = self._detect_faces(image)
        
        if not faces:
            # No face detected, use center crop
            return self._center_crop(image, target_width, target_height)
        
        # Use the largest face detected
        largest_face = max(faces, key=lambda f: f[2] * f[3])
        x, y, w, h = largest_face
        
        # Calculate face center
        face_center_x = x + w // 2
        face_center_y = y + h // 3  # Slightly above center for better passport photo composition
        
        # Calculate crop area around face
        img_width, img_height = image.size
        
        # Determine crop size maintaining aspect ratio
        aspect_ratio = target_width / target_height
        
        if img_width / img_height > aspect_ratio:
            # Image is wider, crop width
            crop_height = img_height
            crop_width = int(crop_height * aspect_ratio)
        else:
            # Image is taller, crop height
            crop_width = img_width
            crop_height = int(crop_width / aspect_ratio)
        
        # Center crop around face
        left = max(0, face_center_x - crop_width // 2)
        top = max(0, face_center_y - crop_height // 2)
        right = min(img_width, left + crop_width)
        bottom = min(img_height, top + crop_height)
        
        # Adjust if crop goes out of bounds
        if right - left < crop_width:
            left = max(0, right - crop_width)
        if bottom - top < crop_height:
            top = max(0, bottom - crop_height)
        
        cropped = image.crop((left, top, right, bottom))
        return cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
    
    def _center_crop(self, image: Image.Image, target_width: int, target_height: int) -> Image.Image:
        """Standard center crop without face detection"""
        img_width, img_height = image.size
        
        # Calculate crop area
        aspect_ratio = target_width / target_height
        
        if img_width / img_height > aspect_ratio:
            # Image is wider, crop width
            crop_height = img_height
            crop_width = int(crop_height * aspect_ratio)
            left = (img_width - crop_width) // 2
            top = 0
        else:
            # Image is taller, crop height
            crop_width = img_width
            crop_height = int(crop_width / aspect_ratio)
            left = 0
            top = (img_height - crop_height) // 2
        
        right = left + crop_width
        bottom = top + crop_height
        
        cropped = image.crop((left, top, right, bottom))
        return cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
    
    def _remove_background(self, image: Image.Image, background_color: Optional[str] = None) -> Image.Image:
        """Remove background using optimized AI models with superior quality"""
        
        try:
            if self.bg_removal_session and REMBG_AVAILABLE:
                # Optimize image size for faster processing while maintaining quality
                original_size = image.size
                max_dimension = 1024  # Limit for faster processing
                
                if max(original_size) > max_dimension:
                    # Resize for processing, maintain aspect ratio
                    ratio = max_dimension / max(original_size)
                    process_size = (int(original_size[0] * ratio), int(original_size[1] * ratio))
                    process_image = image.resize(process_size, Image.Resampling.LANCZOS)
                else:
                    process_image = image
                    process_size = original_size
                
                # Convert to bytes with optimal format
                img_bytes = io.BytesIO()
                process_image.save(img_bytes, format='PNG', optimize=True)
                img_bytes.seek(0)
                
                # Remove background using rembg
                removed_bg_bytes = remove(img_bytes.getvalue(), session=self.bg_removal_session)
                removed_bg_image = Image.open(io.BytesIO(removed_bg_bytes))
                
                # Resize back to original dimensions if we downscaled
                if process_size != original_size:
                    removed_bg_image = removed_bg_image.resize(original_size, Image.Resampling.LANCZOS)
                
                # Ensure RGBA mode
                if removed_bg_image.mode != 'RGBA':
                    removed_bg_image = removed_bg_image.convert('RGBA')
                
                # Advanced edge refinement
                removed_bg_image = self._refine_background_edges(removed_bg_image)
                
                # Apply background color with high quality blending
                if background_color:
                    bg_color = self._parse_background_color(background_color)
                    return self._apply_background_color(removed_bg_image, bg_color)
                else:
                    return removed_bg_image
                    
        except Exception as e:
            print(f"Warning: Advanced background removal failed: {e}")
        
        # Fallback to optimized basic background removal
        return self._optimized_basic_background_removal(image, background_color)
    
    def _parse_background_color(self, background_color: str) -> tuple:
        """Parse background color from hex string"""
        try:
            if background_color.startswith('#') and len(background_color) == 7:
                return tuple(int(background_color[i:i+2], 16) for i in (1, 3, 5))
        except:
            pass
        return (255, 255, 255)  # Default white
    
    def _apply_background_color(self, image: Image.Image, bg_color: tuple) -> Image.Image:
        """Apply background color with high-quality alpha blending"""
        try:
            if image.mode != 'RGBA':
                return image
            
            # Create background
            background = Image.new('RGB', image.size, bg_color)
            
            # High-quality alpha compositing
            result = Image.alpha_composite(background.convert('RGBA'), image)
            return result.convert('RGB')
        except Exception as e:
            print(f"Warning: Background color application failed: {e}")
            return image.convert('RGB') if image.mode == 'RGBA' else image
    
    def _refine_background_edges(self, image: Image.Image) -> Image.Image:
        """Advanced edge refinement for cleaner background removal"""
        try:
            if image.mode != 'RGBA':
                return image
            
            img_array = np.array(image)
            alpha = img_array[:, :, 3].astype(np.float32) / 255.0
            
            # Apply bilateral filter for edge-preserving smoothing
            alpha_smooth = cv2.bilateralFilter((alpha * 255).astype(np.uint8), 9, 75, 75) / 255.0
            
            # Apply guided filter for better edge preservation
            rgb = img_array[:, :, :3].astype(np.float32) / 255.0
            gray = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY) / 255.0
            
            # Simple guided filter implementation
            eps = 0.01
            r = 4
            
            # Box filter
            def box_filter(img, r):
                return cv2.boxFilter(img, -1, (2*r+1, 2*r+1))
            
            mean_I = box_filter(gray, r)
            mean_p = box_filter(alpha_smooth, r)
            corr_Ip = box_filter(gray * alpha_smooth, r)
            cov_Ip = corr_Ip - mean_I * mean_p
            
            mean_II = box_filter(gray * gray, r)
            var_I = mean_II - mean_I * mean_I
            
            a = cov_Ip / (var_I + eps)
            b = mean_p - a * mean_I
            
            mean_a = box_filter(a, r)
            mean_b = box_filter(b, r)
            
            alpha_refined = mean_a * gray + mean_b
            alpha_refined = np.clip(alpha_refined, 0, 1)
            
            # Update alpha channel
            img_array[:, :, 3] = (alpha_refined * 255).astype(np.uint8)
            
            return Image.fromarray(img_array, 'RGBA')
        except Exception as e:
            print(f"Warning: Edge refinement failed: {e}")
            return image
    
    def _optimized_basic_background_removal(self, image: Image.Image, background_color: Optional[str] = None) -> Image.Image:
        """Fast and optimized basic background removal"""
        try:
            img_array = np.array(image)
            h, w = img_array.shape[:2]
            
            # Fast edge-based segmentation
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # Apply adaptive threshold for better edge detection
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            
            # Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Create mask from largest contour (assumed to be the subject)
            mask = np.zeros((h, w), dtype=np.uint8)
            if contours:
                # Find the largest contour
                largest_contour = max(contours, key=cv2.contourArea)
                
                # Fill the contour
                cv2.fillPoly(mask, [largest_contour], 255)
                
                # Smooth the mask
                mask = cv2.GaussianBlur(mask, (5, 5), 0)
                mask = mask.astype(np.float32) / 255.0
            else:
                # Fallback: assume center region is subject
                center_x, center_y = w // 2, h // 2
                radius = min(w, h) // 3
                y, x = np.ogrid[:h, :w]
                mask = ((x - center_x) ** 2 + (y - center_y) ** 2) <= radius ** 2
                mask = mask.astype(np.float32)
            
            # Apply background color
            if background_color:
                bg_color = self._parse_background_color(background_color)
                result = np.zeros_like(img_array)
                for i in range(3):
                    result[:, :, i] = img_array[:, :, i] * mask + bg_color[i] * (1 - mask)
                return Image.fromarray(result.astype(np.uint8))
            else:
                # Create RGBA with transparency
                result = np.zeros((h, w, 4), dtype=np.uint8)
                result[:, :, :3] = img_array
                result[:, :, 3] = (mask * 255).astype(np.uint8)
                return Image.fromarray(result, 'RGBA')
                
        except Exception as e:
            print(f"Warning: Optimized background removal failed: {e}")
            return image
    
    def _enforce_file_size_limits(self, image: Image.Image, output_format: str, target_size_kb: Optional[int] = None) -> Tuple[Image.Image, int]:
        """Enforce file size limits with better quality preservation"""
        
        min_size = self.min_output_size_kb * 1024
        max_size = target_size_kb * 1024 if target_size_kb else self.max_output_size_kb * 1024
        
        # Start with high quality
        quality = 95
        save_format = 'JPEG' if output_format.upper() == 'JPG' else output_format.upper()
        
        # For PNG, use optimize flag instead of quality
        save_kwargs = {'format': save_format}
        if save_format == 'JPEG':
            save_kwargs['quality'] = quality
            save_kwargs['optimize'] = True
        elif save_format == 'PNG':
            save_kwargs['optimize'] = True
        
        # Test current size
        test_buffer = io.BytesIO()
        image.save(test_buffer, **save_kwargs)
        current_size = test_buffer.tell()
        
        # If too small, enhance quality/size
        if current_size < min_size:
            if save_format == 'JPEG':
                # Try maximum quality
                test_buffer = io.BytesIO()
                image.save(test_buffer, format=save_format, quality=100, optimize=True)
                if test_buffer.tell() >= min_size:
                    return image, 100
            # For PNG or if JPEG still too small, enhance sharpness slightly
            enhanced = ImageEnhance.Sharpness(image).enhance(1.05)
            return enhanced, quality
        
        # If too large, reduce quality more gradually
        if save_format == 'JPEG':
            while current_size > max_size and quality > 60:  # Don't go below 60 for better quality
                quality -= 5  # Smaller steps for better quality control
                test_buffer = io.BytesIO()
                image.save(test_buffer, format=save_format, quality=quality, optimize=True)
                current_size = test_buffer.tell()
        
        # If still too large after quality reduction, resize more conservatively
        if current_size > max_size:
            # Calculate scale factor more conservatively
            scale_factor = min(0.95, (max_size / current_size) ** 0.5)  # Max 5% reduction per iteration
            new_width = max(50, int(image.width * scale_factor))  # Ensure minimum size
            new_height = max(50, int(image.height * scale_factor))
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            quality = max(75, quality)  # Maintain reasonable quality after resize
        
        return image, quality
    
    async def process_image(
        self,
        file: UploadFile,
        width: int = 200,
        height: int = 200,
        output_format: str = "JPG",
        background_color: Optional[str] = None,
        maintain_aspect_ratio: bool = True,  # Default to True for better results
        max_file_size_kb: Optional[int] = None,
        remove_background: bool = False,
        auto_face_crop: bool = False,
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
                
                # Step 1: Remove background if requested
                if remove_background:
                    img = self._remove_background(img, background_color)
                
                # Step 2: Handle cropping and resizing
                if auto_face_crop:
                    # Use face detection for intelligent cropping
                    img = self._center_crop_face(img, width, height)
                    new_width, new_height = width, height
                elif maintain_aspect_ratio:
                    # Calculate aspect ratio preserving dimensions
                    original_ratio = img.width / img.height
                    target_ratio = width / height
                    
                    if original_ratio > target_ratio:
                        # Image is wider, fit to width
                        new_width = width
                        new_height = int(width / original_ratio)
                    else:
                        # Image is taller, fit to height
                        new_height = height
                        new_width = int(height * original_ratio)
                    
                    # Resize with high-quality resampling
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Center on canvas of exact dimensions with appropriate background
                    if new_width != width or new_height != height:
                        # Use background color if specified, otherwise white
                        canvas_color = (255, 255, 255)  # Default white
                        if background_color and not remove_background:
                            try:
                                canvas_color = tuple(int(background_color[i:i+2], 16) for i in (1, 3, 5))
                            except:
                                canvas_color = (255, 255, 255)
                        
                        canvas = Image.new('RGB', (width, height), canvas_color)
                        x_offset = (width - new_width) // 2
                        y_offset = (height - new_height) // 2
                        canvas.paste(img, (x_offset, y_offset))
                        img = canvas
                        new_width, new_height = width, height
                else:
                    # Direct resize without maintaining aspect ratio
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
                    new_width, new_height = width, height
                
                # Step 3: Apply background color if specified (and not already done in background removal)
                if background_color and background_color != "#ffffff" and not remove_background:
                    # Convert hex to RGB
                    bg_color = tuple(int(background_color[i:i+2], 16) for i in (1, 3, 5))
                    background = Image.new('RGB', (new_width, new_height), bg_color)
                    background.paste(img, (0, 0))
                    img = background
                
                # Step 4: Ensure proper format compatibility before saving
                save_format = 'JPEG' if output_format.upper() == 'JPG' else output_format.upper()
                
                # Critical fix: Convert RGBA to RGB for JPEG compatibility
                if save_format == 'JPEG' and img.mode in ('RGBA', 'LA'):
                    # Create background with appropriate color
                    if background_color:
                        bg_color = self._parse_background_color(background_color)
                    else:
                        bg_color = (255, 255, 255)  # Default white
                    
                    # Create RGB background and composite
                    rgb_background = Image.new('RGB', img.size, bg_color)
                    if img.mode == 'RGBA':
                        rgb_background = Image.alpha_composite(rgb_background.convert('RGBA'), img).convert('RGB')
                    else:
                        rgb_background.paste(img, mask=img.split()[-1] if img.mode == 'LA' else None)
                    img = rgb_background
                elif img.mode not in ('RGB', 'L') and save_format in ('JPEG', 'PNG'):
                    # Ensure proper mode for other formats
                    img = img.convert('RGB')
                
                # Generate output
                output_buffer = io.BytesIO()
                
                if output_format.upper() == 'PDF':
                    # Convert to PDF using img2pdf
                    temp_img_buffer = io.BytesIO()
                    # Ensure RGB mode for PDF conversion
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    img.save(temp_img_buffer, format='JPEG', quality=95)
                    temp_img_buffer.seek(0)
                    
                    pdf_bytes = img2pdf.convert(temp_img_buffer.getvalue())
                    output_buffer.write(pdf_bytes)
                    content_type = "application/pdf"
                    file_extension = "pdf"
                else:
                    # Step 5: Enforce file size limits and optimize quality
                    img, quality = self._enforce_file_size_limits(img, output_format, max_file_size_kb)
                    
                    # Save with appropriate parameters
                    save_kwargs = {'format': save_format}
                    if save_format == 'JPEG':
                        save_kwargs['quality'] = quality
                        save_kwargs['optimize'] = True
                    elif save_format == 'PNG':
                        save_kwargs['optimize'] = True
                    
                    img.save(output_buffer, **save_kwargs)
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
        remove_background: bool = False,
        auto_face_crop: bool = False,
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
                    remove_background=remove_background,
                    auto_face_crop=auto_face_crop,
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
    
    def get_processed_file(self, file_id: str) -> Optional[Tuple[Path, str]]:
        """Get processed file path and content type by file_id"""
        try:
            # For now, we'll use a simple file storage approach
            # In production, this should query the database for file metadata
            
            # Check if file_id contains the full path (as returned by process methods)
            if "/" in file_id:
                # Extract just the filename from the path
                filename = file_id.split("/")[-1]
            else:
                filename = file_id
            
            # Look for the file in common output directories
            possible_paths = [
                Path(f"temp_output/{filename}"),
                Path(f"output/{filename}"),
                Path(f"processed/{filename}"),
                Path(filename)  # Current directory
            ]
            
            for file_path in possible_paths:
                if file_path.exists() and file_path.is_file():
                    # Determine content type based on file extension
                    extension = file_path.suffix.lower()
                    if extension in ['.jpg', '.jpeg']:
                        content_type = "image/jpeg"
                    elif extension == '.png':
                        content_type = "image/png"
                    elif extension == '.pdf':
                        content_type = "application/pdf"
                    else:
                        content_type = "application/octet-stream"
                    
                    return (file_path, content_type)
            
            # If not found in standard locations, try to find by pattern
            import glob
            for pattern in [f"*{filename}*", f"*{file_id}*"]:
                matches = glob.glob(pattern)
                if matches:
                    file_path = Path(matches[0])
                    if file_path.exists() and file_path.is_file():
                        extension = file_path.suffix.lower()
                        if extension in ['.jpg', '.jpeg']:
                            content_type = "image/jpeg"
                        elif extension == '.png':
                            content_type = "image/png"
                        elif extension == '.pdf':
                            content_type = "application/pdf"
                        else:
                            content_type = "application/octet-stream"
                        return (file_path, content_type)
            
            return None
            
        except Exception as e:
            print(f"Error getting processed file {file_id}: {e}")
            return None

# Global instance
photo_editor_service = PhotoEditorService()
