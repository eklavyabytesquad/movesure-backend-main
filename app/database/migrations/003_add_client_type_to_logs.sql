-- ============================================================
-- Migration 003: Add client_type column to logs_request_log
-- Run in Supabase SQL Editor.
-- ============================================================

ALTER TABLE logs_request_log
    ADD COLUMN IF NOT EXISTS client_type VARCHAR(30);

CREATE INDEX IF NOT EXISTS idx_logs_reqlog_client_type
    ON logs_request_log(client_type, created_at DESC);
