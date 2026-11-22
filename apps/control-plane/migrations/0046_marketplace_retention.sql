-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Retain only pending proposals and the current publication. Terminal receipts
-- keep request identity and the decision for retries, never an old definition.
set local lock_timeout = '5s';

alter table marketplace_proposal alter column package drop not null;
alter table marketplace_proposal drop constraint marketplace_proposal_check;
alter table marketplace_proposal add constraint marketplace_proposal_package_kind
    check (package is null or (package->>'kind' is not null and package->>'kind' = kind));
alter table marketplace_proposal drop constraint marketplace_proposal_display_name_check;
alter table marketplace_proposal add constraint marketplace_proposal_retained_content check (
    (package is not null and length(display_name) between 1 and 255 and state in ('pending','approved'))
    or (package is null and state <> 'pending' and display_name = '' and description = '' and origin_name = ''));

create or replace function protect_marketplace_proposal() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.state <> 'pending' or not exists (
            select 1 from space where id = new.proposing_space_id and organization_id = new.marketplace_space_id
        ) then
            raise exception 'proposal requires a proposing space in its catalogue organization' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
    else
        if (new.proposal_id, new.entry_id, new.marketplace_space_id, new.kind,
            new.submitted_by, new.request_key, new.request_hash, new.package_hash, new.submitted_at)
            is distinct from (old.proposal_id, old.entry_id, old.marketplace_space_id, old.kind,
            old.submitted_by, old.request_key, old.request_hash, old.package_hash, old.submitted_at) then
            raise exception 'submitted identity and attribution are immutable' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if (new.package, new.display_name, new.description, new.origin_name)
            is distinct from (old.package, old.display_name, old.description, old.origin_name)
            and not (old.package is not null and new.package is null and old.state = 'approved'
                and not exists (select 1 from marketplace_entry
                    where entry_id = old.entry_id and published_proposal_id = old.proposal_id)) then
            raise exception 'submitted content can only be retired after publication ends' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if new.proposing_space_id is distinct from old.proposing_space_id and
            (new.proposing_space_id is not null or exists(select 1 from space where id=old.proposing_space_id)) then
            raise exception 'only deletion detaches the proposing space' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if old.state <> 'pending' and (new.state, new.decided_by, new.decided_at, new.decision_reason)
            is distinct from (old.state, old.decided_by, old.decided_at, old.decision_reason) then
            raise exception 'proposal decision is immutable' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
    end if;
    if new.state in ('rejected','cancelled') or new.package is null then
        new.package := null;
        new.display_name := '';
        new.description := '';
        new.origin_name := '';
    end if;
    return new;
end $$;

create or replace function protect_marketplace_entry() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if not exists (select 1 from space where id = new.marketplace_space_id and kind = 'organization')
            or new.published_proposal_id is not null or new.publication_version <> 0 then
            raise exception 'invalid initial marketplace entry' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
    else
        if (new.entry_id, new.marketplace_space_id, new.kind, new.created_at)
            is distinct from (old.entry_id, old.marketplace_space_id, old.kind, old.created_at) then
            raise exception 'marketplace identity is immutable' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if (new.published_proposal_id, new.published_at, new.withdrawn_at)
            is distinct from (old.published_proposal_id, old.published_at, old.withdrawn_at) then
            if new.publication_version <> old.publication_version + 1 then
                raise exception 'publication changes require the next version' using errcode = '23514',
                    constraint = TG_NAME, table = TG_TABLE_NAME;
            end if;
        elsif new.publication_version <> old.publication_version then
            raise exception 'publication version requires a change' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
    end if;
    if exists (select 1 from marketplace_proposal
        where proposal_id = new.published_proposal_id and package is null) then
        raise exception 'a retired proposal cannot be published again' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

-- Replacing or withdrawing the catalogue pointer also retires its former content.
-- Installations have independent resources and receipts; neither is touched here.
create function retire_marketplace_publication() returns trigger language plpgsql as $$
begin
    update marketplace_proposal set package = null, display_name = '', description = '', origin_name = ''
        where proposal_id = old.published_proposal_id;
    return null;
end $$;
create trigger marketplace_publication_retirement after update of published_proposal_id on marketplace_entry
    for each row when (old.published_proposal_id is not null
        and new.published_proposal_id is distinct from old.published_proposal_id)
    execute function retire_marketplace_publication();

comment on trigger marketplace_publication_retirement on marketplace_entry is
    'effect: erase the former publication payload on replacement or withdrawal, preserving installation receipts';
