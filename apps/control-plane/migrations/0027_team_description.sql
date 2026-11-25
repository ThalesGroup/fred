-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Absence is the reminder state; no synthetic description or separate flag.
alter table space add column description text;
alter table space add constraint space_team_description check (
    description is null or (
        kind = 'team' and char_length(description) between 20 and 500
        and description = btrim(description)
    )
);
