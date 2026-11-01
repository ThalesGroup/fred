-- Explicit platform assignments; discovery never grants organization access.
create table organization_model_source (
    organization_id uuid not null references space (id) on delete cascade,
    source_id text collate "C" not null references model_source (source_id),
    primary key (organization_id, source_id)
);
create trigger model_source_organization before insert or update of organization_id
    on organization_model_source for each row execute function require_model_policy_organization();

-- A row also remembers an administered policy, even after that policy is deleted.
-- completed_at additionally records completion of the one-time source assignment.
-- Neither deleting permissions/policy nor removing YAML resets this receipt.
create table organization_model_initialization (
    organization_id uuid primary key references space (id) on delete cascade,
    completed_at timestamptz
);
create trigger model_initialization_organization before insert or update of organization_id
    on organization_model_initialization for each row execute function require_model_policy_organization();

insert into organization_model_initialization (organization_id)
    select organization_id from organization_model_policy;

create function remember_model_policy_initialization() returns trigger language plpgsql as $$
begin
    insert into organization_model_initialization (organization_id) values (new.organization_id)
        on conflict (organization_id) do nothing;
    return new;
end $$;
create trigger remember_model_policy after insert on organization_model_policy
    for each row execute function remember_model_policy_initialization();

-- Preserve historical decisions without inventing assignments. NOT VALID permits
-- their retention, but protects every new write. Consumers deny unassigned sources
-- immediately. Initialization requires an explicit mapping covering every retained
-- permission before completing; it never replaces an administered policy.
alter table organization_model_permission
    add constraint organization_model_permission_source_assignment
    foreign key (organization_id, source_id)
    references organization_model_source (organization_id, source_id) not valid;
