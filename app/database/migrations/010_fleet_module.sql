-- ============================================================
-- Migration 010: Fleet Module
-- Adds fleet + fleet_staff tables.
-- Adds fleet FK columns to existing challan and
-- challan_trip_sheet tables.
--
-- Safe to re-run: all statements use IF NOT EXISTS / IF EXISTS.
-- ============================================================

-- ============================================================
-- fleet_staff
-- ============================================================
CREATE TABLE IF NOT EXISTS fleet_staff (
    staff_id                UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id              UUID            NOT NULL
                                REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id               UUID
                                REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,
    name                    VARCHAR(100)    NOT NULL,
    role                    VARCHAR(20)     NOT NULL
                                CHECK (role IN ('OWNER','DRIVER','CONDUCTOR','CLEANER','MECHANIC')),
    mobile                  VARCHAR(15),
    alternate_mobile        VARCHAR(15),
    email                   VARCHAR(150),
    address                 TEXT,
    aadhar_no               VARCHAR(20),
    pan_no                  VARCHAR(10),
    license_no              VARCHAR(30),
    license_expiry          DATE,
    license_type            VARCHAR(10)
                                CHECK (license_type IS NULL OR license_type IN ('LMV','HMV','BOTH')),
    badge_no                VARCHAR(30),
    date_of_birth           DATE,
    date_of_joining         DATE,
    emergency_contact_name  VARCHAR(100),
    emergency_contact_mobile VARCHAR(15),
    bank_account_no         VARCHAR(30),
    bank_ifsc               VARCHAR(15),
    bank_name               VARCHAR(100),
    profile_photo_url       TEXT,
    notes                   TEXT,
    metadata                JSONB           NOT NULL DEFAULT '{}',
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_fleet_staff_company  ON fleet_staff(company_id);
CREATE INDEX IF NOT EXISTS idx_fleet_staff_branch   ON fleet_staff(company_id, branch_id);
CREATE INDEX IF NOT EXISTS idx_fleet_staff_role     ON fleet_staff(company_id, role);
CREATE INDEX IF NOT EXISTS idx_fleet_staff_mobile   ON fleet_staff(mobile) WHERE mobile IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fleet_staff_license  ON fleet_staff(license_no) WHERE license_no IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fleet_staff_active   ON fleet_staff(company_id, is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_fleet_staff_license_expiry ON fleet_staff(license_expiry)
    WHERE license_expiry IS NOT NULL AND is_active = TRUE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_fleet_staff_updated_at'
    ) THEN
        CREATE TRIGGER trg_fleet_staff_updated_at
            BEFORE UPDATE ON fleet_staff
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;


-- ============================================================
-- fleet
-- ============================================================
CREATE TABLE IF NOT EXISTS fleet (
    fleet_id                UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id              UUID            NOT NULL
                                REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id               UUID
                                REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,
    vehicle_no              VARCHAR(20)     NOT NULL,
    vehicle_type            VARCHAR(20)     NOT NULL DEFAULT 'TRUCK'
                                CHECK (vehicle_type IN ('TRUCK','TRAILER','MINI_TRUCK','PICKUP','TANKER','OTHER')),
    make                    VARCHAR(100),
    model                   VARCHAR(100),
    year_of_manufacture     INTEGER         CHECK (year_of_manufacture > 1900),
    body_type               VARCHAR(20)
                                CHECK (body_type IS NULL OR body_type IN ('OPEN','CLOSED','CONTAINER','FLATBED','TANKER','OTHER')),
    capacity_kg             NUMERIC         CHECK (capacity_kg IS NULL OR capacity_kg > 0),
    color                   VARCHAR(50),
    engine_no               VARCHAR(50),
    chassis_no              VARCHAR(50),
    rc_no                   VARCHAR(50),
    rc_expiry               DATE,
    insurance_no            VARCHAR(50),
    insurance_company       VARCHAR(100),
    insurance_expiry        DATE,
    permit_no               VARCHAR(50),
    permit_type             VARCHAR(20)
                                CHECK (permit_type IS NULL OR permit_type IN ('NATIONAL','STATE','LOCAL')),
    permit_expiry           DATE,
    fitness_no              VARCHAR(50),
    fitness_expiry          DATE,
    puc_no                  VARCHAR(50),
    puc_expiry              DATE,
    current_owner_id        UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    current_driver_id       UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    current_conductor_id    UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    status                  VARCHAR(20)     NOT NULL DEFAULT 'ACTIVE'
                                CHECK (status IN ('ACTIVE','IN_TRANSIT','MAINTENANCE','INACTIVE')),
    notes                   TEXT,
    metadata                JSONB           NOT NULL DEFAULT '{}',
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    CONSTRAINT uq_fleet_vehicle_no UNIQUE (company_id, vehicle_no)
);

CREATE INDEX IF NOT EXISTS idx_fleet_company          ON fleet(company_id);
CREATE INDEX IF NOT EXISTS idx_fleet_branch           ON fleet(company_id, branch_id);
CREATE INDEX IF NOT EXISTS idx_fleet_vehicle_no       ON fleet(vehicle_no);
CREATE INDEX IF NOT EXISTS idx_fleet_status           ON fleet(company_id, status);
CREATE INDEX IF NOT EXISTS idx_fleet_type             ON fleet(company_id, vehicle_type);
CREATE INDEX IF NOT EXISTS idx_fleet_driver           ON fleet(current_driver_id)  WHERE current_driver_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fleet_owner            ON fleet(current_owner_id)   WHERE current_owner_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fleet_active           ON fleet(company_id, is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_fleet_rc_expiry        ON fleet(rc_expiry)          WHERE rc_expiry IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fleet_insurance_expiry ON fleet(insurance_expiry)   WHERE insurance_expiry IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fleet_permit_expiry    ON fleet(permit_expiry)      WHERE permit_expiry IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fleet_fitness_expiry   ON fleet(fitness_expiry)     WHERE fitness_expiry IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fleet_puc_expiry       ON fleet(puc_expiry)         WHERE puc_expiry IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_fleet_updated_at'
    ) THEN
        CREATE TRIGGER trg_fleet_updated_at
            BEFORE UPDATE ON fleet
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;


-- ============================================================
-- Add fleet FK columns to challan
-- ============================================================
ALTER TABLE challan
    ADD COLUMN IF NOT EXISTS fleet_id       UUID REFERENCES fleet(fleet_id)       ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS driver_id      UUID REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS owner_id       UUID REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS conductor_id   UUID REFERENCES fleet_staff(staff_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_challan_fleet     ON challan(fleet_id)     WHERE fleet_id     IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_challan_driver    ON challan(driver_id)    WHERE driver_id    IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_challan_owner     ON challan(owner_id)     WHERE owner_id     IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_challan_conductor ON challan(conductor_id) WHERE conductor_id IS NOT NULL;


-- ============================================================
-- Add fleet FK columns to challan_trip_sheet
-- ============================================================
ALTER TABLE challan_trip_sheet
    ADD COLUMN IF NOT EXISTS fleet_id       UUID REFERENCES fleet(fleet_id)       ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS driver_id      UUID REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS owner_id       UUID REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS conductor_id   UUID REFERENCES fleet_staff(staff_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_trip_sheet_fleet     ON challan_trip_sheet(fleet_id)     WHERE fleet_id     IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_trip_sheet_driver    ON challan_trip_sheet(driver_id)    WHERE driver_id    IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_trip_sheet_owner     ON challan_trip_sheet(owner_id)     WHERE owner_id     IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_trip_sheet_conductor ON challan_trip_sheet(conductor_id) WHERE conductor_id IS NOT NULL;
