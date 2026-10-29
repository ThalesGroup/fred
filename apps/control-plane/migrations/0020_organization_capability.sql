-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- A row enables one pod offer for every space of the organization; no row denies it.
CREATE TABLE organization_capability (
    organization_id uuid NOT NULL REFERENCES space (id) ON DELETE CASCADE,
    runtime_id text NOT NULL,
    capability_id text NOT NULL,
    enabled_by text NOT NULL,
    enabled_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, runtime_id, capability_id),
    FOREIGN KEY (runtime_id, capability_id)
        REFERENCES runtime_capability (runtime_id, capability_id)
);

-- Space kind is immutable, so checking the referenced space on write is sufficient.
CREATE FUNCTION require_organization_space() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM space WHERE id = NEW.organization_id AND kind = 'organization') THEN
        RAISE EXCEPTION '% requires an organization', TG_TABLE_NAME USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER organization_capability_organization BEFORE INSERT OR UPDATE OF organization_id
    ON organization_capability FOR EACH ROW EXECUTE FUNCTION require_organization_space();
