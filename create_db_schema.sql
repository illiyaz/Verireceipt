-- VeriReceipt Database Schema
-- Run this when switching from CSV to Database backend

-- Receipts table
CREATE TABLE IF NOT EXISTS receipts (
    id SERIAL PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    file_hash VARCHAR(64),
    source_type VARCHAR(20),  -- 'pdf' or 'image'
    file_size_bytes INTEGER,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_receipts_file_name ON receipts(file_name);
CREATE INDEX idx_receipts_file_hash ON receipts(file_hash);

-- Analyses table
CREATE TABLE IF NOT EXISTS analyses (
    id SERIAL PRIMARY KEY,
    receipt_id INTEGER REFERENCES receipts(id) ON DELETE CASCADE,
    engine_label VARCHAR(20) NOT NULL,  -- 'real', 'suspicious', 'fake'
    engine_score FLOAT NOT NULL,
    engine_version VARCHAR(50),
    reasons TEXT[],
    minor_notes TEXT[],
    features JSONB,  -- Store all extracted features as JSON
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_analyses_receipt_id ON analyses(receipt_id);
CREATE INDEX idx_analyses_label ON analyses(engine_label);
CREATE INDEX idx_analyses_score ON analyses(engine_score);
CREATE INDEX idx_analyses_analyzed_at ON analyses(analyzed_at);

-- Feedback table
CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    receipt_id INTEGER REFERENCES receipts(id) ON DELETE CASCADE,
    analysis_id INTEGER REFERENCES analyses(id) ON DELETE CASCADE,
    given_label VARCHAR(20) NOT NULL,  -- Human-corrected label
    reviewer_id VARCHAR(255),
    comment TEXT,
    reason_code VARCHAR(50),
    is_override BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_feedback_receipt_id ON feedback(receipt_id);
CREATE INDEX idx_feedback_analysis_id ON feedback(analysis_id);
CREATE INDEX idx_feedback_given_label ON feedback(given_label);
CREATE INDEX idx_feedback_reviewer_id ON feedback(reviewer_id);
CREATE INDEX idx_feedback_created_at ON feedback(created_at);

-- Optional: Create views for common queries

-- View: Latest analysis per receipt
CREATE OR REPLACE VIEW latest_analyses AS
SELECT DISTINCT ON (r.id)
    r.id as receipt_id,
    r.file_name,
    a.id as analysis_id,
    a.engine_label,
    a.engine_score,
    a.analyzed_at
FROM receipts r
JOIN analyses a ON r.id = a.receipt_id
ORDER BY r.id, a.analyzed_at DESC;

-- View: Feedback with original predictions
CREATE OR REPLACE VIEW feedback_with_predictions AS
SELECT 
    f.id as feedback_id,
    r.file_name,
    a.engine_label as original_label,
    a.engine_score as original_score,
    f.given_label as corrected_label,
    f.reviewer_id,
    f.comment,
    f.reason_code,
    f.created_at
FROM feedback f
JOIN receipts r ON f.receipt_id = r.id
JOIN analyses a ON f.analysis_id = a.id;

-- View: Statistics
CREATE OR REPLACE VIEW analysis_statistics AS
SELECT 
    COUNT(*) as total_analyses,
    SUM(CASE WHEN engine_label = 'real' THEN 1 ELSE 0 END) as real_count,
    SUM(CASE WHEN engine_label = 'suspicious' THEN 1 ELSE 0 END) as suspicious_count,
    SUM(CASE WHEN engine_label = 'fake' THEN 1 ELSE 0 END) as fake_count,
    AVG(engine_score) as avg_score,
    MAX(analyzed_at) as last_analysis
FROM analyses;
