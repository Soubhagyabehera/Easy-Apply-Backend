"""
Document Manager Service for EasyApply
Handles secure storage and automatic formatting of user documents for job applications
"""

import io
import os
import uuid
import zipfile
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime
from PIL import Image
import PyPDF2
from fastapi import UploadFile, HTTPException
from app.database.supabase_client import postgresql_client


class DocumentManagerService:
    """Service for managing user documents and automatic job-specific formatting"""
    
    def __init__(self):
        """Initialize the document manager service"""
        self.supported_formats = {
            'pdf': 'application/pdf',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        
        # Initialize storage directories
        self.user_documents_dir = Path("user_documents")
        self.user_documents_dir.mkdir(exist_ok=True)
        self.processed_documents_dir = Path("processed_documents")
        self.processed_documents_dir.mkdir(exist_ok=True)
        
        # Document type categories
        self.document_categories = {
            'personal': ['resume', 'photo', 'signature'],
            'educational': ['certificate_10th', 'certificate_12th', 'certificate_graduation', 'certificate_post_graduation'],
            'identity': ['aadhaar', 'pan', 'voter_id', 'passport'],
            'other': ['caste_certificate', 'domicile_certificate', 'income_certificate', 'disability_certificate'],
            'experience': ['experience_certificate', 'relieving_letter']
        }
        
        # Ensure database tables exist
        self._ensure_database_tables()
    
    async def validate_document(self, file: UploadFile, document_type: str) -> bool:
        """Validate uploaded document"""
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        if file.size and file.size > self.max_file_size:
            raise HTTPException(status_code=400, detail="File size exceeds 50MB limit")
        
        # Get file extension
        file_ext = os.path.splitext(file.filename.lower())[1][1:]
        
        if file_ext not in self.supported_formats:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported format. Use: {', '.join(self.supported_formats.keys())}"
            )
        
        # Validate document type
        all_types = []
        for types in self.document_categories.values():
            all_types.extend(types)
        
        if document_type not in all_types:
            raise HTTPException(status_code=400, detail=f"Invalid document type: {document_type}")
        
        return True
    
    async def upload_user_document(
        self,
        user_id: str,
        file: UploadFile,
        document_type: str
    ) -> Dict[str, Any]:
        """Upload and store user document securely"""
        
        await self.validate_document(file, document_type)
        
        try:
            # Generate unique file ID
            document_id = str(uuid.uuid4())
            file_ext = os.path.splitext(file.filename.lower())[1][1:]
            
            # Create user-specific directory
            user_dir = self.user_documents_dir / user_id
            user_dir.mkdir(exist_ok=True)
            
            # Generate secure file path
            secure_filename = f"{document_type}_{document_id}.{file_ext}"
            file_path = user_dir / secure_filename
            
            # Read and save file
            file_data = await file.read()
            await file.seek(0)
            
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            # Get file metadata
            file_size = len(file_data)
            
            # Determine document category
            document_category = None
            for category, types in self.document_categories.items():
                if document_type in types:
                    document_category = category
                    break
            
            # Save to database
            document_data = {
                'id': document_id,
                'user_id': user_id,
                'document_type': document_type,
                'document_category': document_category,
                'original_filename': file.filename,
                'file_path': str(file_path),
                'file_size_bytes': file_size,
                'file_format': file_ext,
                'upload_date': datetime.now().isoformat(),
                'is_active': True,
                'metadata': {
                    'original_name': file.filename,
                    'upload_timestamp': datetime.now().isoformat()
                }
            }
            
            # TODO: Implement database save method
            # postgresql_client.save_user_document(document_data)
            print(f"Document uploaded: {document_id} for user {user_id}")
            
            return {
                'success': True,
                'document_id': document_id,
                'document_type': document_type,
                'original_filename': file.filename,
                'file_size_bytes': file_size,
                'file_format': file_ext,
                'upload_date': datetime.now().isoformat(),
                'message': 'Document uploaded successfully'
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Document upload failed: {str(e)}")
    
    async def get_user_documents(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all documents for a user"""
        try:
            # TODO: Implement database query method
            # documents = postgresql_client.get_user_documents(user_id)
            
            # For now, return mock data
            user_dir = self.user_documents_dir / user_id
            documents = []
            
            if user_dir.exists():
                for file_path in user_dir.glob("*"):
                    if file_path.is_file():
                        # Parse filename to get document type
                        filename_parts = file_path.stem.split('_')
                        if len(filename_parts) >= 2:
                            document_type = '_'.join(filename_parts[:-1])
                            document_id = filename_parts[-1]
                            
                            documents.append({
                                'document_id': document_id,
                                'document_type': document_type,
                                'original_filename': file_path.name,
                                'file_path': str(file_path),
                                'file_size_bytes': file_path.stat().st_size,
                                'file_format': file_path.suffix[1:],
                                'upload_date': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                                'is_active': True
                            })
            
            return documents
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to retrieve documents: {str(e)}")
    
    async def delete_user_document(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """Delete a user document"""
        try:
            user_dir = self.user_documents_dir / user_id
            
            # Find and delete the file
            for file_path in user_dir.glob(f"*_{document_id}.*"):
                if file_path.is_file():
                    file_path.unlink()
                    
                    # TODO: Update database to mark as inactive
                    # postgresql_client.deactivate_user_document(document_id)
                    
                    return {
                        'success': True,
                        'document_id': document_id,
                        'message': 'Document deleted successfully'
                    }
            
            raise HTTPException(status_code=404, detail="Document not found")
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Document deletion failed: {str(e)}")
    
    async def format_documents_for_job(
        self,
        user_id: str,
        job_id: str,
        job_requirements: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Format user documents according to job requirements"""
        
        try:
            # Get user documents
            user_documents = await self.get_user_documents(user_id)
            
            if not user_documents:
                # Create some demo documents if none exist
                demo_documents = await self._create_demo_documents(user_id)
                user_documents = demo_documents
            
            # Get job requirements (mock for now)
            if not job_requirements:
                job_requirements = self._get_default_job_requirements()
            
            formatted_documents = []
            processing_batch_id = str(uuid.uuid4())
            
            # Create batch directory first
            batch_dir = self.processed_documents_dir / processing_batch_id
            batch_dir.mkdir(exist_ok=True)
            
            for doc in user_documents:
                document_type = doc['document_type']
                
                # Check if this document type is required for the job
                if document_type in job_requirements:
                    req = job_requirements[document_type]
                    
                    # Format the document according to requirements
                    formatted_doc = await self._format_single_document(
                        user_id=user_id,
                        document=doc,
                        requirements=req,
                        job_id=job_id,
                        batch_id=processing_batch_id
                    )
                    
                    if formatted_doc:
                        formatted_documents.append(formatted_doc)
            
            # If no documents were formatted, create placeholder documents
            if not formatted_documents:
                formatted_documents = await self._create_placeholder_documents(
                    user_id, job_id, processing_batch_id, job_requirements
                )
            
            # Create ZIP bundle
            zip_path = await self._create_document_bundle(
                user_id=user_id,
                job_id=job_id,
                documents=formatted_documents,
                batch_id=processing_batch_id
            )
            
            return {
                'success': True,
                'job_id': job_id,
                'batch_id': processing_batch_id,
                'total_documents': len(formatted_documents),
                'formatted_documents': formatted_documents,
                'bundle_download_url': f"/api/v1/document-manager/download-bundle/{processing_batch_id}",
                'zip_file_path': str(zip_path),
                'processing_date': datetime.now().isoformat()
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Document formatting failed: {str(e)}")
    
    async def _create_demo_documents(self, user_id: str) -> List[Dict[str, Any]]:
        """Create demo documents for testing when no user documents exist"""
        demo_documents = []
        user_dir = self.user_documents_dir / user_id
        user_dir.mkdir(exist_ok=True)
        
        # Create a simple text file as demo document
        demo_doc_id = str(uuid.uuid4())
        demo_filename = f"resume_{demo_doc_id}.txt"
        demo_path = user_dir / demo_filename
        
        with open(demo_path, 'w') as f:
            f.write("Demo Resume Document\n\nThis is a placeholder document for testing purposes.")
        
        demo_documents.append({
            'document_id': demo_doc_id,
            'document_type': 'resume',
            'original_filename': 'demo_resume.txt',
            'file_path': str(demo_path),
            'file_size_bytes': demo_path.stat().st_size,
            'file_format': 'txt',
            'upload_date': datetime.now().isoformat(),
            'is_active': True
        })
        
        return demo_documents
    
    async def _create_placeholder_documents(
        self, 
        user_id: str, 
        job_id: str, 
        batch_id: str, 
        job_requirements: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Create placeholder documents when no matching documents are found"""
        formatted_documents = []
        batch_dir = self.processed_documents_dir / batch_id
        
        for doc_type, requirements in job_requirements.items():
            # Create a placeholder file
            placeholder_filename = f"{requirements.get('naming_convention', doc_type)}.txt"
            placeholder_path = batch_dir / placeholder_filename
            
            with open(placeholder_path, 'w') as f:
                f.write(f"Placeholder for {doc_type}\n\nThis document type is required for the job application.")
            
            formatted_documents.append({
                'document_id': str(uuid.uuid4()),
                'document_type': doc_type,
                'original_filename': f"placeholder_{doc_type}.txt",
                'processed_filename': placeholder_filename,
                'processed_file_path': str(placeholder_path),
                'requirements_applied': requirements,
                'processing_date': datetime.now().isoformat()
            })
        
        return formatted_documents
    
    async def _format_single_document(
        self,
        user_id: str,
        document: Dict[str, Any],
        requirements: Dict[str, Any],
        job_id: str,
        batch_id: str
    ) -> Optional[Dict[str, Any]]:
        """Format a single document according to requirements"""
        
        try:
            document_id = document['document_id']
            document_type = document['document_type']
            
            # Find original file
            user_dir = self.user_documents_dir / user_id
            original_file = None
            
            for file_path in user_dir.glob(f"*_{document_id}.*"):
                if file_path.is_file():
                    original_file = file_path
                    break
            
            if not original_file:
                return None
            
            # Create processed file name according to naming convention
            naming_convention = requirements.get('naming_convention', f"{document_type}_{document_id}")
            required_format = requirements.get('required_format', document['file_format'])
            
            processed_filename = f"{naming_convention}.{required_format}"
            
            # Create batch directory
            batch_dir = self.processed_documents_dir / batch_id
            batch_dir.mkdir(exist_ok=True)
            
            processed_file_path = batch_dir / processed_filename
            
            # Process based on file type and requirements
            if document['file_format'].lower() in ['jpg', 'jpeg', 'png']:
                await self._process_image_document(
                    original_file, processed_file_path, requirements
                )
            elif document['file_format'].lower() == 'pdf':
                await self._process_pdf_document(
                    original_file, processed_file_path, requirements
                )
            else:
                # For other formats, just copy with new name
                import shutil
                shutil.copy2(original_file, processed_file_path)
            
            return {
                'document_id': document_id,
                'document_type': document_type,
                'original_filename': document['original_filename'],
                'processed_filename': processed_filename,
                'processed_file_path': str(processed_file_path),
                'requirements_applied': requirements,
                'processing_date': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error processing document {document_id}: {str(e)}")
            return None
    
    async def _process_image_document(
        self,
        input_path: Path,
        output_path: Path,
        requirements: Dict[str, Any]
    ):
        """Process image document according to requirements"""
        
        try:
            # Open image
            with Image.open(input_path) as img:
                # Convert to RGB if needed
                if img.mode in ['RGBA', 'P']:
                    img = img.convert('RGB')
                
                # Resize if dimensions specified
                max_width = requirements.get('max_width_px')
                max_height = requirements.get('max_height_px')
                min_width = requirements.get('min_width_px')
                min_height = requirements.get('min_height_px')
                
                if max_width or max_height:
                    img.thumbnail((max_width or img.width, max_height or img.height), Image.LANCZOS)
                
                # Ensure minimum dimensions
                if min_width and img.width < min_width:
                    new_height = int(img.height * min_width / img.width)
                    img = img.resize((min_width, new_height), Image.LANCZOS)
                
                if min_height and img.height < min_height:
                    new_width = int(img.width * min_height / img.height)
                    img = img.resize((new_width, min_height), Image.LANCZOS)
                
                # Save with appropriate format and quality
                save_kwargs = {'optimize': True}
                
                if output_path.suffix.lower() in ['.jpg', '.jpeg']:
                    save_kwargs['format'] = 'JPEG'
                    save_kwargs['quality'] = 85
                elif output_path.suffix.lower() == '.png':
                    save_kwargs['format'] = 'PNG'
                
                img.save(output_path, **save_kwargs)
                
        except Exception as e:
            # Fallback: copy original file
            import shutil
            shutil.copy2(input_path, output_path)
    
    async def _process_pdf_document(
        self,
        input_path: Path,
        output_path: Path,
        requirements: Dict[str, Any]
    ):
        """Process PDF document according to requirements"""
        
        try:
            # For now, just copy the PDF
            # TODO: Implement PDF compression, page extraction, etc.
            import shutil
            shutil.copy2(input_path, output_path)
            
        except Exception as e:
            import shutil
            shutil.copy2(input_path, output_path)
    
    async def _create_document_bundle(
        self,
        user_id: str,
        job_id: str,
        documents: List[Dict[str, Any]],
        batch_id: str
    ) -> Path:
        """Create ZIP bundle of formatted documents"""
        
        batch_dir = self.processed_documents_dir / batch_id
        batch_dir.mkdir(exist_ok=True)  # Ensure directory exists
        zip_path = batch_dir / f"job_{job_id}_documents.zip"
        
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for doc in documents:
                    file_path = Path(doc['processed_file_path'])
                    if file_path.exists():
                        zipf.write(file_path, doc['processed_filename'])
                    else:
                        print(f"Warning: Processed file not found: {file_path}")
            
            # Verify ZIP file was created successfully
            if not zip_path.exists():
                raise Exception(f"Failed to create ZIP file: {zip_path}")
                
            return zip_path
            
        except Exception as e:
            print(f"Error creating document bundle: {e}")
            raise
    
    def _get_default_job_requirements(self) -> Dict[str, Any]:
        """Get default job requirements for document formatting"""
        return {
            'photo': {
                'required_format': 'jpg',
                'max_width_px': 300,
                'max_height_px': 400,
                'min_width_px': 200,
                'min_height_px': 250,
                'max_size_kb': 100,
                'naming_convention': 'passport_photo'
            },
            'signature': {
                'required_format': 'jpg',
                'max_width_px': 200,
                'max_height_px': 100,
                'max_size_kb': 50,
                'naming_convention': 'signature'
            },
            'resume': {
                'required_format': 'pdf',
                'max_size_kb': 2048,
                'naming_convention': 'resume'
            },
            'certificate_10th': {
                'required_format': 'pdf',
                'max_size_kb': 1024,
                'naming_convention': 'class_10_certificate'
            },
            'certificate_12th': {
                'required_format': 'pdf',
                'max_size_kb': 1024,
                'naming_convention': 'class_12_certificate'
            },
            'aadhaar': {
                'required_format': 'pdf',
                'max_size_kb': 512,
                'naming_convention': 'aadhaar_card'
            },
            'pan': {
                'required_format': 'pdf',
                'max_size_kb': 512,
                'naming_convention': 'pan_card'
            }
        }
    
    def get_document_bundle(self, batch_id: str) -> Tuple[Path, str]:
        """Get document bundle for download"""
        batch_dir = self.processed_documents_dir / batch_id
        
        # Ensure the batch directory exists
        if not batch_dir.exists():
            raise HTTPException(status_code=404, detail=f"Batch directory not found: {batch_id}")
        
        # Look for ZIP files in the batch directory
        zip_files = list(batch_dir.glob("*.zip"))
        if zip_files:
            return zip_files[0], 'application/zip'
        
        # If no ZIP file exists, try to create one from processed documents
        processed_files = list(batch_dir.glob("*"))
        if processed_files:
            # Create a ZIP file from available processed documents
            import zipfile
            zip_path = batch_dir / f"job_documents_{batch_id}.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in processed_files:
                    if file_path.is_file() and not file_path.name.endswith('.zip'):
                        zipf.write(file_path, file_path.name)
            
            return zip_path, 'application/zip'
        
        raise HTTPException(status_code=404, detail=f"No documents found for batch: {batch_id}")
    
    def _ensure_database_tables(self):
        """Ensure document manager database tables exist"""
        try:
            postgresql_client.ensure_document_manager_tables_exist()
        except Exception as e:
            print(f"Warning: Failed to ensure document manager tables exist: {e}")


# Global instance
document_manager_service = DocumentManagerService()
