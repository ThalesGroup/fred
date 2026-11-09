-- A catalogue owns independent snapshots. No FK, identity or access decision
-- depends on the original prompt, skill or agent instance.
create table marketplace_entry (
    entry_id uuid primary key,
    marketplace_space_id uuid not null references space(id) on delete cascade,
    kind text not null check (kind in ('prompt', 'skill', 'agent')),
    published_proposal_id uuid,
    published_state text not null default 'approved' check (published_state = 'approved'),
    publication_version bigint not null default 0 check (publication_version >= 0),
    published_at timestamptz,
    withdrawn_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    unique (entry_id, marketplace_space_id, kind),
    check ((published_proposal_id is null) = (published_at is null)),
    check (published_proposal_id is null or withdrawn_at is null)
);
create index marketplace_catalogue on marketplace_entry(marketplace_space_id, entry_id)
    where published_proposal_id is not null;

create table marketplace_proposal (
    proposal_id uuid primary key,
    entry_id uuid not null,
    marketplace_space_id uuid not null,
    kind text not null,
    -- This relation grants ordinary space editors access to the proposal only.
    -- Removing the space detaches this access path, not the catalogue snapshot.
    proposing_space_id uuid references space(id) on delete set null,
    origin_name text not null,
    submitted_by text not null check (btrim(submitted_by) <> ''),
    request_key uuid not null,
    request_hash text not null check (request_hash ~ '^[a-f0-9]{64}$'),
    package jsonb not null check (jsonb_typeof(package) = 'object'),
    package_hash text not null check (package_hash ~ '^[a-f0-9]{64}$'),
    display_name text not null check (length(display_name) between 1 and 255),
    description text not null,
    submitted_at timestamptz not null default clock_timestamp(),
    state text not null default 'pending' check (state in ('pending', 'approved', 'rejected', 'cancelled')),
    decided_by text,
    decided_at timestamptz,
    decision_reason text check (length(decision_reason) <= 2000),
    foreign key (entry_id, marketplace_space_id, kind)
        references marketplace_entry(entry_id, marketplace_space_id, kind) on delete cascade,
    unique (entry_id, proposal_id, state),
    unique (submitted_by, request_key),
    check (package->>'kind' is not null and package->>'kind' = kind),
    check (octet_length(package::text) <= 50331648),
    check ((state = 'pending' and decided_by is null and decided_at is null and decision_reason is null)
        or (state <> 'pending' and decided_by is not null and btrim(decided_by) <> ''
            and decided_at is not null and decided_at >= submitted_at))
);
alter table marketplace_entry add foreign key (entry_id, published_proposal_id, published_state)
    references marketplace_proposal(entry_id, proposal_id, state) deferrable initially deferred;
create index marketplace_proposal_queue on marketplace_proposal(marketplace_space_id, state, proposal_id);
create index marketplace_proposal_source on marketplace_proposal(proposing_space_id, proposal_id);

create function protect_marketplace_entry() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if not exists (select 1 from space where id = new.marketplace_space_id and kind = 'organization')
            or new.published_proposal_id is not null or new.publication_version <> 0 then
            raise exception 'invalid initial marketplace entry' using errcode = '23514';
        end if;
    else
        if (new.entry_id, new.marketplace_space_id, new.kind, new.created_at)
            is distinct from (old.entry_id, old.marketplace_space_id, old.kind, old.created_at) then
            raise exception 'marketplace identity is immutable' using errcode = '23514';
        end if;
        if (new.published_proposal_id, new.published_at, new.withdrawn_at)
            is distinct from (old.published_proposal_id, old.published_at, old.withdrawn_at) then
            if new.publication_version <> old.publication_version + 1 then
                raise exception 'publication changes require the next version' using errcode = '23514';
            end if;
        elsif new.publication_version <> old.publication_version then
            raise exception 'publication version requires a change' using errcode = '23514';
        end if;
    end if;
    return new;
end $$;
create trigger marketplace_entry_identity before insert or update on marketplace_entry
    for each row execute function protect_marketplace_entry();

create function protect_marketplace_proposal() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.state <> 'pending' or not exists (
            select 1 from space where id = new.proposing_space_id and organization_id = new.marketplace_space_id
        ) then
            raise exception 'proposal requires a proposing space in its catalogue organization' using errcode = '23514';
        end if;
    else
        if (new.proposal_id, new.entry_id, new.marketplace_space_id, new.kind, new.origin_name,
            new.submitted_by, new.request_key, new.request_hash, new.package, new.package_hash,
            new.display_name, new.description, new.submitted_at)
            is distinct from (old.proposal_id, old.entry_id, old.marketplace_space_id, old.kind, old.origin_name,
            old.submitted_by, old.request_key, old.request_hash, old.package, old.package_hash,
            old.display_name, old.description, old.submitted_at) then
            raise exception 'submitted content and attribution are immutable' using errcode = '23514';
        end if;
        if new.proposing_space_id is distinct from old.proposing_space_id and
            (new.proposing_space_id is not null or exists(select 1 from space where id=old.proposing_space_id)) then
            raise exception 'only deletion detaches the proposing space' using errcode = '23514';
        end if;
        if old.state <> 'pending' and (new.state, new.decided_by, new.decided_at, new.decision_reason)
            is distinct from (old.state, old.decided_by, old.decided_at, old.decision_reason) then
            raise exception 'proposal decision is immutable' using errcode = '23514';
        end if;
    end if;
    return new;
end $$;
create trigger marketplace_proposal_immutable before insert or update on marketplace_proposal
    for each row execute function protect_marketplace_proposal();

-- Receipts keep historical identifiers and never recreate a deleted installation.
-- Live references protect current placement but cannot cascade to the resource.
alter table prompt add unique (prompt_id, space_id);
alter table skill add unique (skill_id, space_id);
create table marketplace_installation (
    installation_id uuid primary key,
    actor text not null,
    request_key uuid not null,
    request_hash text not null check (request_hash ~ '^[a-f0-9]{64}$'),
    entry_id uuid not null,
    proposal_id uuid not null,
    package_hash text not null,
    kind text not null check (kind in ('prompt', 'skill', 'agent')),
    space_id uuid not null,
    resource_id uuid not null,
    installed_at timestamptz not null default clock_timestamp(),
    live_space_id uuid references space(id) on delete set null,
    prompt_id uuid,
    skill_id uuid,
    agent_instance_id uuid,
    foreign key (prompt_id, live_space_id) references prompt(prompt_id, space_id) on delete set null (prompt_id),
    foreign key (skill_id, live_space_id) references skill(skill_id, space_id) on delete set null (skill_id),
    foreign key (agent_instance_id, live_space_id) references agent_instance(agent_instance_id, space_id) on delete set null (agent_instance_id),
    unique (actor, request_key),
    check (live_space_id is null or live_space_id = space_id),
    check (prompt_id is null or (kind = 'prompt' and prompt_id = resource_id)),
    check (skill_id is null or (kind = 'skill' and skill_id = resource_id)),
    check (agent_instance_id is null or (kind = 'agent' and agent_instance_id = resource_id))
);
create index marketplace_installation_space on marketplace_installation(live_space_id);
create index marketplace_installation_prompt on marketplace_installation(prompt_id, live_space_id) where prompt_id is not null;
create index marketplace_installation_skill on marketplace_installation(skill_id, live_space_id) where skill_id is not null;
create index marketplace_installation_agent on marketplace_installation(agent_instance_id, live_space_id) where agent_instance_id is not null;

create function protect_marketplace_installation() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.live_space_id is distinct from new.space_id
            or num_nonnulls(new.prompt_id, new.skill_id, new.agent_instance_id) <> 1
            or not exists (select 1 from marketplace_entry e join marketplace_proposal p
                on p.proposal_id=e.published_proposal_id join space s on s.id=new.space_id
                where e.entry_id=new.entry_id and p.proposal_id=new.proposal_id
                and p.package_hash=new.package_hash and e.kind=new.kind
                and s.organization_id=e.marketplace_space_id) then
            raise exception 'installation requires a published snapshot and a local destination' using errcode = '23514';
        end if;
    else
        if (new.installation_id,new.actor,new.request_key,new.request_hash,new.entry_id,new.proposal_id,
            new.package_hash,new.kind,new.space_id,new.resource_id,new.installed_at)
            is distinct from (old.installation_id,old.actor,old.request_key,old.request_hash,old.entry_id,old.proposal_id,
            old.package_hash,old.kind,old.space_id,old.resource_id,old.installed_at) then
            raise exception 'installation receipt is immutable' using errcode = '23514';
        end if;
        if (new.live_space_id is distinct from old.live_space_id and
                (new.live_space_id is not null or exists(select 1 from space where id=old.live_space_id)))
            or (new.prompt_id is distinct from old.prompt_id and
                (new.prompt_id is not null or exists(select 1 from prompt where prompt_id=old.prompt_id)))
            or (new.skill_id is distinct from old.skill_id and
                (new.skill_id is not null or exists(select 1 from skill where skill_id=old.skill_id)))
            or (new.agent_instance_id is distinct from old.agent_instance_id and
                (new.agent_instance_id is not null or exists(select 1 from agent_instance where agent_instance_id=old.agent_instance_id))) then
            raise exception 'only resource deletion detaches installation references' using errcode = '23514';
        end if;
    end if;
    return new;
end $$;
create trigger marketplace_installation_immutable before insert or update on marketplace_installation
    for each row execute function protect_marketplace_installation();

-- Fresh installations only: direct, live prompt publication has no remaining writer.
drop table prompt_publication;
drop function require_prompt_publication_destination();
