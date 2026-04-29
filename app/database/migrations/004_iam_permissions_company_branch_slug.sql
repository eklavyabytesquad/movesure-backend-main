-- ============================================================
-- Migration 004: Add company_id, branch_id, slug to iam_permission
--                Add company_id, branch_id to iam_user_permission
-- Run this against your Supabase SQL editor.
-- ============================================================

-- ── iam_permission ────────────────────────────────────────────
ALTER TABLE iam_permission
    ADD COLUMN IF NOT EXISTS company_id  UUID    REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS branch_id   UUID    REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS slug        VARCHAR(150);  -- optional, e.g. "master:city:create"

-- Slug should be unique when set (partial unique index ignores NULLs)
CREATE UNIQUE INDEX IF NOT EXISTS uq_iam_permission_slug
    ON iam_permission(slug)
    WHERE slug IS NOT NULL;

-- Useful lookup indexes
CREATE INDEX IF NOT EXISTS idx_iam_permission_company  ON iam_permission(company_id);
CREATE INDEX IF NOT EXISTS idx_iam_permission_branch   ON iam_permission(company_id, branch_id);

-- ── iam_user_permission ───────────────────────────────────────
ALTER TABLE iam_user_permission
    ADD COLUMN IF NOT EXISTS company_id  UUID    REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS branch_id   UUID    REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_iam_user_perm_company  ON iam_user_permission(company_id);
CREATE INDEX IF NOT EXISTS idx_iam_user_perm_branch   ON iam_user_permission(company_id, branch_id);
