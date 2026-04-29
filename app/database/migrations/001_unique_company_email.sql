-- ============================================================
-- Migration 001: Enforce unique email on tenant_companies
--
-- NOTE: Log table FK/rule fixes are in 002_fix_log_tables.sql
-- Run order: 001 → 002
-- ============================================================

BEGIN;

-- ── Step 1: Delete duplicate companies (keep oldest per email) ─
DELETE FROM tenant_companies
WHERE company_id NOT IN (
    SELECT DISTINCT ON (email) company_id
    FROM   tenant_companies
    WHERE  email IS NOT NULL
    ORDER  BY email, created_at ASC
);

-- ── Step 2: Add UNIQUE constraint on tenant_companies.email ────
ALTER TABLE tenant_companies
    ADD CONSTRAINT uq_tenant_companies_email UNIQUE (email);

-- Drop the old plain index if it exists (superseded by the constraint above)
DROP INDEX IF EXISTS idx_tenant_companies_email;

COMMIT;
