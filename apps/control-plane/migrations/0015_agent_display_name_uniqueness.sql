-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Users address agents by display name within their space. Restore the original
-- case-insensitive uniqueness for creation and rename; logical references remain
-- independent and immutable. Existing duplicates must be resolved explicitly:
-- index creation fails without renaming agents or changing their references.
create unique index uq_agent_instance_space_name
    on agent_instance (space_id, lower(display_name));
