-- Document Manager Database Schema for EasyApply
-- Secure storage of user documents with automatic formatting for job applications

-- User Documents Table - stores all user uploaded documents
CREATE TABLE IF NOT EXISTS user_documents (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL, -- 'resume', 'photo', 'signature', 'certificate_10th', etc.
    document_category VARCHAR(30) NOT NULL, -- 'personal', 'educational', 'identity', 'experience', 'other'
    original_filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL, -- Supabase storage path
    file_size_bytes INTEGER NOT NULL,
    file_format VARCHAR(10) NOT NULL, -- 'pdf', 'jpg', 'png', etc.
    upload_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}', -- Additional file metadata
    
    -- Ensure one active document per type per user
    UNIQUE(user_id, document_type) WHERE is_active = TRUE
);

-- Document Types Reference Table
CREATE TABLE IF NOT EXISTS document_types (
    id SERIAL PRIMARY KEY,
    type_code VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    category VARCHAR(30) NOT NULL,
    is_required BOOLEAN DEFAULT FALSE,
    description TEXT,
    accepted_formats TEXT[], -- ['pdf', 'jpg', 'png']
    max_size_mb INTEGER DEFAULT 10,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Job Document Requirements Table
CREATE TABLE IF NOT EXISTS job_document_requirements (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    job_id VARCHAR(100) NOT NULL, -- From jobs API
    document_type VARCHAR(50) NOT NULL,
    is_required BOOLEAN DEFAULT TRUE,
    required_format VARCHAR(10), -- 'pdf', 'jpg', etc.
    max_size_kb INTEGER,
    min_width_px INTEGER,
    min_height_px INTEGER,
    max_width_px INTEGER,
    max_height_px INTEGER,
    naming_convention VARCHAR(255), -- e.g., 'firstname_lastname_photo.jpg'
    special_requirements JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    FOREIGN KEY (document_type) REFERENCES document_types(type_code)
);

-- Document Processing History Table
CREATE TABLE IF NOT EXISTS document_processing_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id),
    job_id VARCHAR(100) NOT NULL,
    original_document_id UUID NOT NULL REFERENCES user_documents(id),
    processed_file_path TEXT NOT NULL,
    processing_type VARCHAR(50) NOT NULL, -- 'resize', 'format_convert', 'rename', etc.
    processing_parameters JSONB DEFAULT '{}',
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    download_count INTEGER DEFAULT 0,
    last_downloaded TIMESTAMP WITH TIME ZONE
);

-- Insert default document types
INSERT INTO document_types (type_code, display_name, category, is_required, description, accepted_formats, max_size_mb) VALUES
-- Personal Documents
('resume', 'Resume/Bio-data', 'personal', TRUE, 'Current resume or bio-data', ARRAY['pdf', 'doc', 'docx'], 5),
('photo', 'Passport Size Photograph', 'personal', TRUE, 'Recent passport size photograph', ARRAY['jpg', 'jpeg', 'png'], 2),
('signature', 'Signature', 'personal', TRUE, 'Digital signature', ARRAY['jpg', 'jpeg', 'png', 'pdf'], 1),

-- Educational Certificates
('certificate_10th', '10th Class Certificate', 'educational', TRUE, '10th standard/SSC certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
('certificate_12th', '12th Class Certificate', 'educational', TRUE, '12th standard/HSC certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
('certificate_graduation', 'Graduation Certificate', 'educational', TRUE, 'Bachelor degree certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
('certificate_post_graduation', 'Post-Graduation Certificate', 'educational', FALSE, 'Master degree certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),

-- Identity Documents
('aadhaar', 'Aadhaar Card', 'identity', TRUE, 'Aadhaar card copy', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 3),
('pan', 'PAN Card', 'identity', TRUE, 'PAN card copy', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 2),
('voter_id', 'Voter ID Card', 'identity', FALSE, 'Voter ID card copy', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 2),
('passport', 'Passport', 'identity', FALSE, 'Passport copy', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),

-- Certificates
('caste_certificate', 'Caste Certificate', 'other', FALSE, 'Caste/category certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
('domicile_certificate', 'Domicile Certificate', 'other', FALSE, 'Domicile/residence certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
('income_certificate', 'Income Certificate', 'other', FALSE, 'Income certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
('disability_certificate', 'Disability Certificate', 'other', FALSE, 'Disability certificate (if applicable)', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),

-- Experience Documents
('experience_certificate', 'Experience Certificate', 'experience', FALSE, 'Work experience certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
('relieving_letter', 'Relieving Letter', 'experience', FALSE, 'Relieving letter from previous employer', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5)

ON CONFLICT (type_code) DO NOTHING;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_user_documents_user_id ON user_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_user_documents_type ON user_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_user_documents_active ON user_documents(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_job_requirements_job_id ON job_document_requirements(job_id);
CREATE INDEX IF NOT EXISTS idx_processing_history_user_job ON document_processing_history(user_id, job_id);

-- Row Level Security (RLS) Policies
ALTER TABLE user_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_processing_history ENABLE ROW LEVEL SECURITY;

-- Users can only access their own documents
CREATE POLICY "Users can view own documents" ON user_documents
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own documents" ON user_documents
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own documents" ON user_documents
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own documents" ON user_documents
    FOR DELETE USING (auth.uid() = user_id);

-- Users can only access their own processing history
CREATE POLICY "Users can view own processing history" ON document_processing_history
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own processing history" ON document_processing_history
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Public read access for document types and job requirements
ALTER TABLE document_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_document_requirements ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view document types" ON document_types
    FOR SELECT USING (true);

CREATE POLICY "Anyone can view job requirements" ON job_document_requirements
    FOR SELECT USING (true);
