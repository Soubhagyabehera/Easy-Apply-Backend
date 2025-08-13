-- Photo Editor Tables for EasyApply Document Tools
-- Run this SQL script in your Supabase database

-- Photo Processing History Table
CREATE TABLE IF NOT EXISTS photo_processing_history (
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    session_id TEXT NOT NULL,
    
    -- Original file information
    original_filename TEXT NOT NULL,
    original_size_bytes INTEGER NOT NULL,
    original_width INTEGER NOT NULL,
    original_height INTEGER NOT NULL,
    original_format TEXT NOT NULL,
    
    -- Processing parameters
    target_width INTEGER NOT NULL,
    target_height INTEGER NOT NULL,
    output_format TEXT NOT NULL CHECK (output_format IN ('JPG', 'PNG', 'PDF')),
    background_color TEXT,
    maintain_aspect_ratio BOOLEAN DEFAULT FALSE,
    max_file_size_kb INTEGER,
    
    -- Output file information
    processed_filename TEXT NOT NULL,
    processed_size_bytes INTEGER NOT NULL,
    processed_width INTEGER NOT NULL,
    processed_height INTEGER NOT NULL,
    compression_ratio DECIMAL(5,2),
    
    -- Processing metadata
    processing_time_ms INTEGER,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    
    -- File storage information
    file_id TEXT UNIQUE NOT NULL,
    storage_path TEXT,
    thumbnail_path TEXT,
    download_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    last_accessed TIMESTAMP WITH TIME ZONE
);

-- Photo Processing Batches Table
CREATE TABLE IF NOT EXISTS photo_processing_batches (
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    session_id TEXT NOT NULL,
    
    batch_id TEXT UNIQUE NOT NULL,
    total_files INTEGER NOT NULL,
    successful_files INTEGER DEFAULT 0,
    failed_files INTEGER DEFAULT 0,
    
    -- Processing parameters (same for all files in batch)
    target_width INTEGER NOT NULL,
    target_height INTEGER NOT NULL,
    output_format TEXT NOT NULL CHECK (output_format IN ('JPG', 'PNG', 'PDF')),
    background_color TEXT,
    maintain_aspect_ratio BOOLEAN DEFAULT FALSE,
    max_file_size_kb INTEGER,
    
    -- Batch metadata
    total_processing_time_ms INTEGER,
    zip_file_path TEXT,
    zip_file_size_bytes INTEGER,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Photo Editor User Settings Table
CREATE TABLE IF NOT EXISTS photo_editor_settings (
    id SERIAL PRIMARY KEY,
    user_id TEXT UNIQUE NOT NULL,
    
    -- Default processing preferences
    default_width INTEGER DEFAULT 200,
    default_height INTEGER DEFAULT 200,
    default_output_format TEXT DEFAULT 'JPG' CHECK (default_output_format IN ('JPG', 'PNG', 'PDF')),
    default_background_color TEXT DEFAULT '#ffffff',
    default_maintain_aspect_ratio BOOLEAN DEFAULT FALSE,
    default_max_file_size_kb INTEGER,
    
    -- User preferences
    auto_optimize_size BOOLEAN DEFAULT TRUE,
    preferred_quality INTEGER DEFAULT 95 CHECK (preferred_quality BETWEEN 1 AND 100),
    save_processing_history BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_photo_history_user_id ON photo_processing_history(user_id);
CREATE INDEX IF NOT EXISTS idx_photo_history_session_id ON photo_processing_history(session_id);
CREATE INDEX IF NOT EXISTS idx_photo_history_file_id ON photo_processing_history(file_id);
CREATE INDEX IF NOT EXISTS idx_photo_history_created_at ON photo_processing_history(created_at);

CREATE INDEX IF NOT EXISTS idx_photo_batches_user_id ON photo_processing_batches(user_id);
CREATE INDEX IF NOT EXISTS idx_photo_batches_session_id ON photo_processing_batches(session_id);
CREATE INDEX IF NOT EXISTS idx_photo_batches_batch_id ON photo_processing_batches(batch_id);
CREATE INDEX IF NOT EXISTS idx_photo_batches_created_at ON photo_processing_batches(created_at);

CREATE INDEX IF NOT EXISTS idx_photo_settings_user_id ON photo_editor_settings(user_id);

-- Create triggers to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_photo_editor_settings_updated_at
    BEFORE UPDATE ON photo_editor_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add Row Level Security (RLS) policies if needed
-- Uncomment and modify these if you want to enable RLS

-- ALTER TABLE photo_processing_history ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE photo_processing_batches ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE photo_editor_settings ENABLE ROW LEVEL SECURITY;

-- Example RLS policies (modify as needed)
-- CREATE POLICY "Users can view their own photo processing history" ON photo_processing_history
--     FOR SELECT USING (auth.uid()::text = user_id);

-- CREATE POLICY "Users can insert their own photo processing history" ON photo_processing_history
--     FOR INSERT WITH CHECK (auth.uid()::text = user_id);

-- CREATE POLICY "Users can view their own photo processing batches" ON photo_processing_batches
--     FOR SELECT USING (auth.uid()::text = user_id);

-- CREATE POLICY "Users can insert their own photo processing batches" ON photo_processing_batches
--     FOR INSERT WITH CHECK (auth.uid()::text = user_id);

-- CREATE POLICY "Users can view their own photo editor settings" ON photo_editor_settings
--     FOR SELECT USING (auth.uid()::text = user_id);

-- CREATE POLICY "Users can update their own photo editor settings" ON photo_editor_settings
--     FOR UPDATE USING (auth.uid()::text = user_id);

-- CREATE POLICY "Users can insert their own photo editor settings" ON photo_editor_settings
--     FOR INSERT WITH CHECK (auth.uid()::text = user_id);

-- Grant necessary permissions
-- GRANT ALL ON photo_processing_history TO authenticated;
-- GRANT ALL ON photo_processing_batches TO authenticated;
-- GRANT ALL ON photo_editor_settings TO authenticated;

-- Insert default settings for existing users (optional)
-- INSERT INTO photo_editor_settings (user_id) 
-- SELECT DISTINCT user_id FROM users 
-- WHERE user_id NOT IN (SELECT user_id FROM photo_editor_settings)
-- ON CONFLICT (user_id) DO NOTHING;
