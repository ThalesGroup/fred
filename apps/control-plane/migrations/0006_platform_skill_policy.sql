-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Global packaged-skill opt-outs apply at the next turn's admission.
create table platform_skill_policy (
    name text primary key check (
        length(name) between 1 and 64
        and name ~ '^[a-z0-9]+(-[a-z0-9]+)*$'
    ),
    enabled boolean not null,
    updated_by text not null,
    updated_at timestamptz not null default now()
);
