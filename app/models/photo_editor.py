"""
Photo Editor Database Models for EasyApply Document Tools
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional

Base = declarative_base()

class PhotoProcessingHistory(Base):
    """Model for storing photo processing history and metadata"""
    
    __tablename__ = "photo_processing_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=True)  # Optional user tracking
    session_id = Column(String, index=True, nullable=False)  # Session tracking
    
    # Original file information
    original_filename = Column(String, nullable=False)
    original_size_bytes = Column(Integer, nullable=False)
    original_width = Column(Integer, nullable=False)
    original_height = Column(Integer, nullable=False)
    original_format = Column(String, nullable=False)
    
    # Processing parameters
    target_width = Column(Integer, nullable=False)
    target_height = Column(Integer, nullable=False)
    output_format = Column(String, nullable=False)  # JPG, PNG, PDF
    background_color = Column(String, nullable=True)  # Hex color
    maintain_aspect_ratio = Column(Boolean, default=False)
    max_file_size_kb = Column(Integer, nullable=True)
    
    # Output file information
    processed_filename = Column(String, nullable=False)
    processed_size_bytes = Column(Integer, nullable=False)
    processed_width = Column(Integer, nullable=False)
    processed_height = Column(Integer, nullable=False)
    compression_ratio = Column(Float, nullable=True)  # Original size / Processed size
    
    # Processing metadata
    processing_time_ms = Column(Integer, nullable=True)  # Processing time in milliseconds
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    
    # File storage information
    file_id = Column(String, unique=True, index=True, nullable=False)  # Unique file identifier
    storage_path = Column(String, nullable=True)  # Path to stored file
    thumbnail_path = Column(String, nullable=True)  # Path to thumbnail
    download_count = Column(Integer, default=0)  # Number of times downloaded
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # File expiration
    last_accessed = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<PhotoProcessingHistory(id={self.id}, file_id='{self.file_id}', original='{self.original_filename}')>"

class PhotoProcessingBatch(Base):
    """Model for storing batch processing information"""
    
    __tablename__ = "photo_processing_batches"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=True)  # Optional user tracking
    session_id = Column(String, index=True, nullable=False)  # Session tracking
    
    batch_id = Column(String, unique=True, index=True, nullable=False)  # Unique batch identifier
    total_files = Column(Integer, nullable=False)
    successful_files = Column(Integer, default=0)
    failed_files = Column(Integer, default=0)
    
    # Processing parameters (same for all files in batch)
    target_width = Column(Integer, nullable=False)
    target_height = Column(Integer, nullable=False)
    output_format = Column(String, nullable=False)
    background_color = Column(String, nullable=True)
    maintain_aspect_ratio = Column(Boolean, default=False)
    max_file_size_kb = Column(Integer, nullable=True)
    
    # Batch metadata
    total_processing_time_ms = Column(Integer, nullable=True)
    zip_file_path = Column(String, nullable=True)  # Path to batch ZIP file
    zip_file_size_bytes = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<PhotoProcessingBatch(id={self.id}, batch_id='{self.batch_id}', total={self.total_files})>"

class PhotoEditorSettings(Base):
    """Model for storing user photo editor preferences"""
    
    __tablename__ = "photo_editor_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True, nullable=False)
    
    # Default processing preferences
    default_width = Column(Integer, default=200)
    default_height = Column(Integer, default=200)
    default_output_format = Column(String, default="JPG")
    default_background_color = Column(String, default="#ffffff")
    default_maintain_aspect_ratio = Column(Boolean, default=False)
    default_max_file_size_kb = Column(Integer, nullable=True)
    
    # User preferences
    auto_optimize_size = Column(Boolean, default=True)
    preferred_quality = Column(Integer, default=95)  # JPEG quality 1-100
    save_processing_history = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<PhotoEditorSettings(user_id='{self.user_id}', default_format='{self.default_output_format}')>"
