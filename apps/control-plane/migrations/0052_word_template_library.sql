-- Word originals use the same quota, staged receipt and retirement lifecycle as
-- PowerPoint. Slots bound a library to eight files; preparations remain per file.
alter table powerpoint_file add column capability_id text not null default 'ppt_builder'
    check (capability_id in ('ppt_builder','word_template'));
alter table powerpoint_file add column slot smallint not null default 0;
alter table powerpoint_file add column label text not null default '' check (length(label) <= 255);
alter table powerpoint_file add constraint template_slot check
    ((capability_id='ppt_builder' and slot=0) or (capability_id='word_template' and slot between 0 and 7));
drop index powerpoint_agent_current;
drop index powerpoint_organization_effective;
drop index powerpoint_organization_candidate;
create unique index powerpoint_agent_current on powerpoint_file(agent_instance_id,capability_id,slot)
    where status='stored' and agent_instance_id is not null;
create unique index powerpoint_organization_effective on powerpoint_file(space_id,runtime_id,capability_id,slot)
    where status='stored' and agent_instance_id is null and effective;
create unique index powerpoint_organization_candidate on powerpoint_file(space_id,runtime_id,capability_id,slot)
    where status='stored' and agent_instance_id is null and not effective;
alter table capability_preparation drop constraint capability_preparation_capability_id_check;
alter table capability_preparation add constraint capability_preparation_capability_id_check
    check (capability_id in ('ppt_builder','word_template'));
create function protect_template_scope() returns trigger language plpgsql as $$
begin
    if (new.capability_id,new.slot) is distinct from (old.capability_id,old.slot) then
        raise exception 'template scope is immutable' using errcode='23514';
    end if;
    return new;
end $$;
create trigger template_scope before update on powerpoint_file
    for each row execute function protect_template_scope();
create or replace function retire_powerpoint_settings() returns trigger language plpgsql as $$
begin
    if new.capability_id <> 'ppt_builder' then return new; end if;
    if new.status='retired' then
        delete from organization_powerpoint_settings where file_id=new.id;
    elsif new.effective and not old.effective and new.agent_instance_id is null then
        delete from organization_powerpoint_settings where organization_id=new.space_id
            and runtime_id=new.runtime_id and file_id is null;
    end if;
    return new;
end $$;
-- One visible readiness state covers every selected preparation. Per-file results
-- remain independent, and retries/cleanup never replace the admitted revision.
create function refresh_template_readiness() returns trigger language plpgsql as $$
declare agent uuid;
begin
    agent := new.agent_instance_id;
    if agent is not null then
        update agent_instance a set preparation_state = case
            when exists(select 1 from capability_preparation p where p.agent_instance_id=agent and p.configuration_revision=a.configuration_revision and p.state='failed') then 'failed'
            when exists(select 1 from capability_preparation p where p.agent_instance_id=agent and p.configuration_revision=a.configuration_revision and p.state='pending') then 'pending'
            else 'ready' end,
            preparation_error=(select error from capability_preparation p where p.agent_instance_id=agent and p.configuration_revision=a.configuration_revision and p.state='failed' order by created_at limit 1)
        where a.agent_instance_id=agent;
    end if;
    return new;
end $$;
create trigger template_readiness after insert or update of state,configuration_revision on capability_preparation
    for each row execute function refresh_template_readiness();
comment on trigger template_scope on powerpoint_file is
    'assertion: immutability - a template receipt keeps its capability and bounded library slot';
comment on trigger template_readiness on capability_preparation is
    'effect: recompute agent readiness from every current capability preparation';
