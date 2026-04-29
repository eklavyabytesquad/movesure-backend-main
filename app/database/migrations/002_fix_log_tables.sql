-- ============================================================
-- Migration 002: Fix log tables
--
-- Changes:
--   1. Drop FK constraints from logs_request_log and logs_audit_log
--      (audit logs are immutable history — IDs must never be nulled out)
--   2. Drop DO INSTEAD NOTHING rules (they break FK cascade operations)
--   3. Replace with BEFORE triggers that raise a clear exception
-- ============================================================

BEGIN;

-- ── 1. Drop FK constraints from logs_request_log ─────────────
ALTER TABLE logs_request_log
    DROP CONSTRAINT IF EXISTS logs_request_log_user_id_fkey,
    DROP CONSTRAINT IF EXISTS logs_request_log_session_id_fkey,
    DROP CONSTRAINT IF EXISTS logs_request_log_company_id_fkey,
    DROP CONSTRAINT IF EXISTS logs_request_log_branch_id_fkey;

-- ── 2. Drop FK constraints from logs_audit_log ───────────────
ALTER TABLE logs_audit_log
    DROP CONSTRAINT IF EXISTS logs_audit_log_request_log_id_fkey,
    DROP CONSTRAINT IF EXISTS logs_audit_log_user_id_fkey,
    DROP CONSTRAINT IF EXISTS logs_audit_log_company_id_fkey;

-- ── 3. Drop the broken immutability rules ────────────────────
DROP RULE IF EXISTS no_update_logs_request_log ON logs_request_log;
DROP RULE IF EXISTS no_delete_logs_request_log ON logs_request_log;

DROP RULE IF EXISTS no_update_logs_audit_log   ON logs_audit_log;
DROP RULE IF EXISTS no_delete_logs_audit_log   ON logs_audit_log;

DROP RULE IF EXISTS no_update_logs_field_chg   ON logs_audit_field_change;
DROP RULE IF EXISTS no_delete_logs_field_chg   ON logs_audit_field_change;

-- ── 4. Create immutability trigger function ───────────────────
CREATE OR REPLACE FUNCTION fn_logs_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Log records are immutable and cannot be % ed. table=%',
        TG_OP, TG_TABLE_NAME;
END;
$$;

-- ── 5. Attach immutability triggers to all three log tables ───
DROP TRIGGER IF EXISTS trg_no_update_logs_request_log ON logs_request_log;
CREATE TRIGGER trg_no_update_logs_request_log
    BEFORE UPDATE OR DELETE ON logs_request_log
    FOR EACH ROW EXECUTE FUNCTION fn_logs_immutable();

DROP TRIGGER IF EXISTS trg_no_update_logs_audit_log ON logs_audit_log;
CREATE TRIGGER trg_no_update_logs_audit_log
    BEFORE UPDATE OR DELETE ON logs_audit_log
    FOR EACH ROW EXECUTE FUNCTION fn_logs_immutable();

DROP TRIGGER IF EXISTS trg_no_update_logs_field_chg ON logs_audit_field_change;
CREATE TRIGGER trg_no_update_logs_field_chg
    BEFORE UPDATE OR DELETE ON logs_audit_field_change
    FOR EACH ROW EXECUTE FUNCTION fn_logs_immutable();

COMMIT;
