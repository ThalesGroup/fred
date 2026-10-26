-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Organization decisions are separate from platform observations and OpenFGA authority.
CREATE TABLE organization_model_policy (
    organization_id uuid PRIMARY KEY REFERENCES space (id) ON DELETE CASCADE,
    revision bigint NOT NULL CHECK (revision > 0),
    default_source_id text COLLATE "C",
    default_upstream_model_id text COLLATE "C",
    fallback_source_id text COLLATE "C",
    fallback_upstream_model_id text COLLATE "C",
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_by text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((default_source_id IS NULL) = (default_upstream_model_id IS NULL)),
    CHECK ((fallback_source_id IS NULL) = (fallback_upstream_model_id IS NULL))
);

CREATE TABLE organization_model_permission (
    organization_id uuid NOT NULL REFERENCES organization_model_policy (organization_id) ON DELETE CASCADE,
    source_id text COLLATE "C" NOT NULL,
    upstream_model_id text COLLATE "C" NOT NULL,
    PRIMARY KEY (organization_id, source_id, upstream_model_id),
    FOREIGN KEY (source_id, upstream_model_id) REFERENCES model_offer (source_id, upstream_model_id)
);

-- Defer membership checks until the atomic replacement is complete. A revocation must
-- explicitly clear or replace its selected default/fallback in that same transaction.
ALTER TABLE organization_model_policy
    ADD FOREIGN KEY (organization_id, default_source_id, default_upstream_model_id)
        REFERENCES organization_model_permission (organization_id, source_id, upstream_model_id)
        DEFERRABLE INITIALLY DEFERRED,
    ADD FOREIGN KEY (organization_id, fallback_source_id, fallback_upstream_model_id)
        REFERENCES organization_model_permission (organization_id, source_id, upstream_model_id)
        DEFERRABLE INITIALLY DEFERRED;

CREATE FUNCTION require_model_policy_organization() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM space WHERE id = NEW.organization_id AND kind = 'organization') THEN
        RAISE EXCEPTION 'model policy requires an organization' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER model_policy_organization BEFORE INSERT OR UPDATE OF organization_id
    ON organization_model_policy FOR EACH ROW EXECUTE FUNCTION require_model_policy_organization();
