-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Weaver starts with a new database: there is no label-derived backfill or
-- transitional writer. Creation supplies the immutable space-local identity.
alter table agent_instance alter column logical_name set not null;
alter table agent_instance alter column created_by set not null;
alter table agent_instance alter column updated_by set not null;
drop index uq_agent_instance_space_name;
