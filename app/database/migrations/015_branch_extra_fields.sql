ALTER TABLE tenant_branches
    ADD COLUMN IF NOT EXISTS mobile_number  VARCHAR(20),
    ADD COLUMN IF NOT EXISTS owner_name     VARCHAR(255),
    ADD COLUMN IF NOT EXISTS city_id        UUID REFERENCES master_city(city_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tenant_branches_city ON tenant_branches(city_id);
