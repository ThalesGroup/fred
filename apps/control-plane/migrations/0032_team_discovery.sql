-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Schema construction step for fresh installations, applied after 0001..0031.
-- No upgrade or data conversion from an existing Swift/Weaver is supported.
-- Discovery and self-enrollment are team settings, with the space's lifecycle.
-- Neither setting publishes resources or changes existing direct roles.
alter table space add column visibility text not null default 'hidden';
alter table space add column joining_mode text not null default 'invite_only';
alter table space add constraint space_team_discovery check (
    visibility in ('visible', 'hidden') and joining_mode in ('invite_only', 'open')
    and (kind = 'team' or (visibility = 'hidden' and joining_mode = 'invite_only'))
);
-- The existing organization index bounds catalogue scans (target: 100 teams/org).
-- A hidden open team retains its preference, but self-enrollment requires visible.
