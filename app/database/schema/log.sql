-- ============================================================
-- LOGS TABLES
-- logs_request_log, logs_audit_log, logs_audit_field_change
-- + immutability rules + write_audit() helper function
-- Depends on: tenant.sql, iam.sql, auth.sql
-- ============================================================


-- ============================================================
-- logs_request_log
-- One row per API request
--
-- NOTE: FK columns (user_id, session_id, company_id, branch_id) are
-- stored as plain UUID — NO FK constraints. Audit logs are immutable
-- historical records; adding FK constraints + immutability rules causes
-- PostgreSQL "unexpected result" errors when parent rows are deleted.
-- ============================================================
CREATE TABLE logs_request_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Who made the call (plain UUIDs — no FK constraints on log tables)
    user_id         UUID,
    session_id      UUID,
    company_id      UUID,
    branch_id       UUID,

    -- What was called
    method          VARCHAR(10) NOT NULL,
    path            TEXT        NOT NULL,
    query_params    JSONB       NOT NULL DEFAULT '{}',
    request_body    JSONB,

    -- Result
    status_code     SMALLINT    NOT NULL,
    error_message   TEXT,

    -- Context
    ip_address      INET,
    user_agent      TEXT,
    client_type     VARCHAR(30),   -- detected: browser | mobile | postman | curl | python_client | powershell | api_client | unknown
    duration_ms     INTEGER,
    correlation_id  UUID,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_logs_reqlog_user        ON logs_request_log(user_id, created_at DESC);
CREATE INDEX idx_logs_reqlog_path        ON logs_request_log(path, created_at DESC);
CREATE INDEX idx_logs_reqlog_status      ON logs_request_log(status_code, created_at DESC);
CREATE INDEX idx_logs_reqlog_company     ON logs_request_log(company_id, created_at DESC);
CREATE INDEX idx_logs_reqlog_correlation ON logs_request_log(correlation_id);
CREATE INDEX idx_logs_reqlog_client_type ON logs_request_log(client_type, created_at DESC);


-- ============================================================
-- logs_audit_log
-- One row per table-row created / updated / deleted
-- ============================================================
CREATE TABLE logs_audit_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link back to the HTTP call that caused this change (plain UUID — no FK)
    request_log_id  UUID,

    -- Who, where, when (plain UUIDs — no FK constraints on log tables)
    user_id         UUID,
    company_id      UUID,
    acted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- What table / row was affected
    table_schema    VARCHAR(63) NOT NULL,
    table_name      VARCHAR(63) NOT NULL,
    record_id       TEXT        NOT NULL,

    -- What kind of change
    action          VARCHAR(10) NOT NULL
                        CHECK (action IN ('INSERT', 'UPDATE', 'DELETE', 'SELECT')),

    -- Full before/after snapshots (NULL on INSERT / DELETE respectively)
    old_data        JSONB,
    new_data        JSONB,

    -- Human-readable summary for quick scanning
    summary         TEXT,
    meta            JSONB       NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_logs_audit_table   ON logs_audit_log(table_schema, table_name, record_id);
CREATE INDEX idx_logs_audit_user    ON logs_audit_log(user_id, acted_at DESC);
CREATE INDEX idx_logs_audit_company ON logs_audit_log(company_id, acted_at DESC);
CREATE INDEX idx_logs_audit_action  ON logs_audit_log(action, acted_at DESC);
CREATE INDEX idx_logs_audit_request ON logs_audit_log(request_log_id);
CREATE INDEX idx_logs_audit_at      ON logs_audit_log(acted_at DESC);


-- ============================================================
-- logs_audit_field_change
-- One row per column changed within an UPDATE
-- ============================================================
CREATE TABLE logs_audit_field_change (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_log_id    UUID        NOT NULL REFERENCES logs_audit_log(id) ON DELETE CASCADE,

    field_name      VARCHAR(63) NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    data_type       VARCHAR(63)
);

CREATE INDEX idx_logs_fieldchg_audit     ON logs_audit_field_change(audit_log_id);
CREATE INDEX idx_logs_fieldchg_field     ON logs_audit_field_change(field_name);
CREATE INDEX idx_logs_fieldchg_field_val ON logs_audit_field_change(field_name, new_value);


-- ============================================================
-- IMMUTABILITY — prevent editing or deleting logs
--
-- Implemented as BEFORE triggers (NOT rules). PostgreSQL RULES with
-- DO INSTEAD NOTHING silently suppress FK cascade operations, causing
-- "referential integrity query gave unexpected result" errors.
-- BEFORE triggers raise a clear exception instead.
-- ============================================================
CREATE OR REPLACE FUNCTION fn_logs_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Log records are immutable and cannot be % ed. table=%',
        TG_OP, TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER trg_no_update_logs_request_log
    BEFORE UPDATE OR DELETE ON logs_request_log
    FOR EACH ROW EXECUTE FUNCTION fn_logs_immutable();

CREATE TRIGGER trg_no_update_logs_audit_log
    BEFORE UPDATE OR DELETE ON logs_audit_log
    FOR EACH ROW EXECUTE FUNCTION fn_logs_immutable();

CREATE TRIGGER trg_no_update_logs_field_chg
    BEFORE UPDATE OR DELETE ON logs_audit_field_change
    FOR EACH ROW EXECUTE FUNCTION fn_logs_immutable();


-- ============================================================
-- HELPER FUNCTION: write_audit()
-- Call after any DML: writes logs_audit_log + logs_audit_field_change
-- ============================================================
CREATE OR REPLACE FUNCTION write_audit(
    p_request_log_id  UUID,
    p_user_id         UUID,
    p_company_id      UUID,
    p_table_schema    TEXT,
    p_table_name      TEXT,
    p_record_id       TEXT,
    p_action          TEXT,
    p_old_data        JSONB,
    p_new_data        JSONB,
    p_summary         TEXT  DEFAULT NULL,
    p_meta            JSONB DEFAULT '{}'
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_audit_id  UUID;
    v_key       TEXT;
BEGIN
    INSERT INTO logs_audit_log (
        request_log_id, user_id, company_id,
        table_schema, table_name, record_id,
        action, old_data, new_data, summary, meta
    )
    VALUES (
        p_request_log_id, p_user_id, p_company_id,
        p_table_schema, p_table_name, p_record_id,
        p_action, p_old_data, p_new_data, p_summary, p_meta
    )
    RETURNING id INTO v_audit_id;

    -- For UPDATEs, explode changed columns into logs_audit_field_change
    IF p_action = 'UPDATE' AND p_old_data IS NOT NULL AND p_new_data IS NOT NULL THEN
        FOR v_key IN
            SELECT key
            FROM jsonb_each_text(p_new_data) AS n(key, val)
            WHERE (p_old_data ->> key) IS DISTINCT FROM (p_new_data ->> key)
        LOOP
            INSERT INTO logs_audit_field_change (
                audit_log_id, field_name, old_value, new_value
            )
            VALUES (
                v_audit_id,
                v_key,
                p_old_data  ->> v_key,
                p_new_data  ->> v_key
            );
        END LOOP;
    END IF;

    RETURN v_audit_id;
END;
$$;
