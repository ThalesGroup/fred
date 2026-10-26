-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Platform sources are independent of pods. Configuration contains secret references only.
CREATE TABLE model_source (
    source_id text COLLATE "C" PRIMARY KEY CHECK (source_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'),
    configuration jsonb NOT NULL CHECK (
        jsonb_typeof(configuration) = 'object'
        AND configuration->>'source_id' = source_id
        AND (configuration->>'revision')::bigint > 0
    ),
    refresh_token uuid,
    state text NOT NULL DEFAULT 'not_observed'
        CHECK (state IN ('not_observed', 'ok', 'unavailable', 'invalid', 'incomplete')),
    error_code text,
    checked_at timestamptz,
    last_success_at timestamptz,
    snapshot_revision bigint NOT NULL DEFAULT 0 CHECK (snapshot_revision >= 0),
    snapshot_source_revision bigint
);

CREATE TABLE model_offer (
    source_id text COLLATE "C" NOT NULL REFERENCES model_source (source_id),
    upstream_model_id text COLLATE "C" NOT NULL
        CHECK (octet_length(upstream_model_id) BETWEEN 1 AND 256
               AND upstream_model_id = btrim(upstream_model_id)),
    metadata jsonb NOT NULL CHECK (jsonb_typeof(metadata) = 'object'),
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    advertised boolean NOT NULL,
    withdrawn_at timestamptz,
    PRIMARY KEY (source_id, upstream_model_id),
    CHECK (advertised = (withdrawn_at IS NULL))
);
