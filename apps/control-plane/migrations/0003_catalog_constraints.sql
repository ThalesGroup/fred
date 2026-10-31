-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Missing JSON fields must not turn the existing consistency check into NULL.
alter table model_source add constraint model_source_required_configuration_fields check (
    configuration->>'source_id' is not null
    and configuration->>'revision' is not null
);

-- Reuse the same organization-kind invariant as capability policies.
do $$
begin
    if exists (
        select 1 from agent_template_policy p join space s on s.id = p.organization_id
        where s.kind <> 'organization'
    ) then
        raise exception 'agent_template_policy requires an organization' using errcode = '23514';
    end if;
end $$;

create trigger agent_template_policy_organization before insert or update of organization_id
    on agent_template_policy for each row execute function require_organization_space();
