-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Diagnostic contract only: predicates and effects remain unchanged.
-- TG_NAME keeps distinct rule names for functions shared by several triggers.
set local lock_timeout = '5s';

create or replace function forbid_space_move() returns trigger language plpgsql as $$
begin
    if (new.kind, new.personal_owner, new.organization_id, new.parent_id)
        is distinct from (old.kind, old.personal_owner, old.organization_id, old.parent_id) then
        raise exception 'space placement is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function forbid_folder_move() returns trigger language plpgsql as $$
begin
    if (new.space_id, new.parent_id, new.path) is distinct from (old.space_id, old.parent_id, old.path) then
        raise exception 'folder placement is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function forbid_document_move() returns trigger language plpgsql as $$
begin
    if (new.space_id, new.folder_id, new.session_id) is distinct from (old.space_id, old.folder_id, old.session_id) then
        raise exception 'document placement is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function protect_processing_identity() returns trigger language plpgsql as $$
begin
    if (new.actor,new.request_key,new.document_id,new.profile,new.workflow_id,new.retry_of,new.submission,new.profile_settings,new.preparation_seconds,new.extraction_seconds,new.indexing_seconds)
        is distinct from (old.actor,old.request_key,old.document_id,old.profile,old.workflow_id,old.retry_of,old.submission,old.profile_settings,old.preparation_seconds,old.extraction_seconds,old.indexing_seconds) then
        raise exception 'processing identity is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    if old.status in ('succeeded','failed') and (new.status,new.stage,new.completed_at,new.error_code) is distinct from (old.status,old.stage,old.completed_at,old.error_code) then
        raise exception 'processing outcome is final' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function protect_pending_document_uploads() returns trigger language plpgsql as $$
begin
    if TG_TABLE_NAME = 'folder' then
        if exists(select 1 from document_upload where folder_id = OLD.id and status = 'pending') then
            raise exception 'folder has pending document uploads' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
    elsif exists(select 1 from document_upload where space_id = OLD.id and status = 'pending') then
        raise exception 'space has pending document uploads' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return OLD;
end $$;

create or replace function require_model_policy_organization() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from space where id = new.organization_id and kind = 'organization') then
        raise exception 'model policy requires an organization' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function require_organization_space() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from space where id = new.organization_id and kind = 'organization') then
        raise exception '% requires an organization', TG_TABLE_NAME using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function require_space_hierarchy() returns trigger language plpgsql as $$
begin
    if new.kind <> 'organization' and not exists (
        select 1 from space where id = new.organization_id and kind = 'organization'
    ) then
        raise exception 'space requires an organization root' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    if new.kind = 'project' and not exists (
        select 1 from space where id = new.parent_id and kind = 'team'
    ) then
        raise exception 'project requires a team parent' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function require_space_role_scope() returns trigger language plpgsql as $$
declare
    target_kind space_kind;
    target_owner text;
begin
    select kind, personal_owner into target_kind, target_owner from space where id = new.space_id;
    if target_kind = 'personal' and target_owner <> new.subject then
        raise exception 'personal space roles require its owner' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    if new.role = 'organization_admin' and target_kind <> 'organization' then
        raise exception 'organization admin requires an organization' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function require_storage_budget_scope() returns trigger language plpgsql as $$
declare
    target_kind space_kind;
begin
    if TG_OP = 'UPDATE' then
        if (new.space_id, new.scope) is distinct from (old.space_id, old.scope) then
            raise exception 'storage budget identity is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        return new;
    end if;
    select kind into target_kind from space where id = new.space_id;
    if target_kind = 'project' then
        raise exception 'projects share their team storage budget' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    if new.scope = 'organization_total' and target_kind <> 'organization' then
        raise exception 'total storage budget requires an organization' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function protect_prompt_definition() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        new.updated_at := new.created_at;
        new.updated_by := new.created_by;
    else
        if (new.prompt_id, new.space_id, new.logical_name, new.created_at, new.created_by)
            is distinct from
            (old.prompt_id, old.space_id, old.logical_name, old.created_at, old.created_by) then
            raise exception 'prompt identity and creation metadata are immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if (new.display_name, new.description, new.text, new.category_id, new.tags)
            is distinct from (old.display_name, old.description, old.text, old.category_id, old.tags) then
            new.updated_at := clock_timestamp();
        else
            new.updated_at := old.updated_at;
            new.updated_by := old.updated_by;
        end if;
    end if;
    return new;
end $$;

create or replace function protect_agent_definition() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.created_by is null or btrim(new.created_by) = '' then
            raise exception 'agent creation requires an author' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        new.updated_at := new.created_at;
        new.updated_by := new.created_by;
    else
        if new.logical_name is distinct from old.logical_name then
            raise exception 'agent logical name is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if (new.agent_instance_id, new.space_id, new.template_id, new.source_runtime_id,
                new.source_agent_id, new.created_at, new.created_by)
            is distinct from
            (old.agent_instance_id, old.space_id, old.template_id, old.source_runtime_id,
                old.source_agent_id, old.created_at, old.created_by) then
            raise exception 'agent identity, placement and creation metadata are immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if (new.display_name, new.description, new.enabled, new.tuning)
            is distinct from (old.display_name, old.description, old.enabled, old.tuning) then
            if new.updated_by is null or btrim(new.updated_by) = '' then
                raise exception 'agent edit requires an author' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
            end if;
            new.updated_at := clock_timestamp();
        else
            new.updated_at := old.updated_at;
            new.updated_by := old.updated_by;
        end if;
    end if;
    return new;
end $$;

create or replace function protect_session_association() returns trigger language plpgsql as $$
declare
    deployment uuid;
    agent_organization uuid;
    chat_organization uuid;
    agent_template uuid;
    agent_runtime text;
begin
    if tg_op = 'INSERT' then
        -- Hold the association's sources through commit, including against concurrent purge.
        select a.space_id, sa.organization_id, sc.organization_id, a.template_id, a.source_runtime_id
            into deployment, agent_organization, chat_organization, agent_template, agent_runtime
            from agent_instance a
            join space sa on sa.id = a.space_id
            join space sc on sc.id = new.space_id
            where a.agent_instance_id = new.agent_instance_id
            for key share of a, sa, sc;
        if not found then
            raise exception 'conversation requires an existing agent and conversation space' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if (new.agent_space_id is not null and new.agent_space_id <> deployment)
            or agent_organization <> chat_organization
            or new.template_id <> agent_template or new.runtime_id <> agent_runtime then
            raise exception 'conversation agent association is inconsistent' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        new.agent_space_id := deployment;
    elsif (new.session_id, new.space_id, new.user_id, new.agent_instance_id,
            new.agent_space_id, new.template_id, new.runtime_id)
        is distinct from
          (old.session_id, old.space_id, old.user_id, old.agent_instance_id,
            old.agent_space_id, old.template_id, old.runtime_id) then
        raise exception 'conversation ownership and agent association are immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function protect_document_move() returns trigger language plpgsql as $$
declare
    source document%rowtype;
    source_organization uuid;
    destination_organization uuid;
begin
    if tg_op = 'INSERT' then
        if new.phase <> 'requested' or new.finished_at is not null then
            raise exception 'a document move starts as requested' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        select * into source from document where id = new.document_id for update;
        if not found then
            raise exception 'document move requires an existing document' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if source.session_id is not null or source.deletion_id is not null then
            raise exception 'only live drive documents can be moved' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if source.retrievable_pending or exists (
            select 1 from document_processing where document_id = source.id
                and status in ('pending', 'running')
        ) then
            raise exception 'document has unfinished processing or inclusion work' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        select organization_id into source_organization
            from space where id = source.space_id and deletion_id is null for share;
        if not found then
            raise exception 'source space must be live' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        select organization_id into destination_organization
            from space where id = new.destination_space_id and deletion_id is null for share;
        if not found then
            raise exception 'destination space must exist and be live' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if source_organization <> destination_organization then
            raise exception 'document move must stay within one organization' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if new.destination_folder_id is not null then
            perform 1 from folder where id = new.destination_folder_id
                and space_id = new.destination_space_id and deletion_id is null for share;
            if not found then
                raise exception 'destination folder must be live in destination space' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
            end if;
        end if;
        -- Always capture database facts, never source placement asserted by the caller.
        new.source_space_id := source.space_id;
        new.source_folder_id := source.folder_id;
        new.generation_id := source.published_generation;
    else
        if (new.id, new.document_id, new.actor, new.source_space_id, new.source_folder_id,
                new.destination_space_id, new.destination_folder_id, new.generation_id, new.created_at)
            is distinct from
            (old.id, old.document_id, old.actor, old.source_space_id, old.source_folder_id,
                old.destination_space_id, old.destination_folder_id, old.generation_id, old.created_at) then
            raise exception 'document move request is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if new.phase = old.phase then
            if new.finished_at is distinct from old.finished_at then
                raise exception 'document move outcome is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
            end if;
            return new;
        end if;
        if not ((old.phase = 'requested' and new.phase in ('projecting', 'cancelled'))
            or (old.phase = 'projecting' and new.phase = 'completed')) then
            raise exception 'invalid document move transition' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if new.phase in ('projecting', 'completed') then
            select * into source from document where id = new.document_id for update;
            if not found then
                raise exception 'document move requires an existing document' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
            end if;
            if (source.space_id, source.folder_id, source.published_generation)
                is distinct from
                (new.destination_space_id, new.destination_folder_id, new.generation_id)
                or source.session_id is not null or source.deletion_id is not null then
                raise exception 'document move placement or generation does not match' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
            end if;
        end if;
        if new.phase in ('completed', 'cancelled') then
            new.finished_at := clock_timestamp();
        end if;
    end if;
    return new;
end $$;

create or replace function require_local_capability_space() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from space where id = new.space_id and kind in ('team', 'project')) then
        raise exception 'local offer policy requires a team or project' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function protect_powerpoint_file() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if not exists (select 1 from space s where s.id = new.space_id
            and s.organization_id = new.organization_id and s.deletion_id is null
            and (new.agent_instance_id is not null or s.kind = 'organization')) then
            raise exception 'invalid PowerPoint owner' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if new.live_space_id is distinct from new.space_id
            or (new.live_agent_id is not null and new.live_agent_id is distinct from new.agent_instance_id)
            or new.status <> 'pending' then
            raise exception 'PowerPoint upload requires a live space' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
    else
        if (new.id, new.request_key, new.actor, new.organization_id, new.space_id,
            new.agent_instance_id, new.quota_owner, new.expected_file_id, new.name,
            new.mime, new.size, new.sha256, new.object_key, new.created_at, new.expires_at, new.runtime_id)
            is distinct from
           (old.id, old.request_key, old.actor, old.organization_id, old.space_id,
            old.agent_instance_id, old.quota_owner, old.expected_file_id, old.name,
            old.mime, old.size, old.sha256, old.object_key, old.created_at, old.expires_at, old.runtime_id)
            or (old.status = 'retired' and new.status <> 'retired')
            or (old.status = 'stored' and new.status = 'pending') then
            raise exception 'PowerPoint identity and terminal retirement are immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
    end if;
    return new;
end $$;

create or replace function protect_powerpoint_settings() returns trigger language plpgsql as $$
begin
    if new.file_id is not null and not exists (
        select 1 from powerpoint_file where id = new.file_id
        and space_id = new.organization_id and runtime_id = new.runtime_id
        and agent_instance_id is null and status = 'stored' and effective
    ) then
        raise exception 'PowerPoint settings require the effective organization file' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function forbid_session_recreation() returns trigger language plpgsql as $$
begin
    if exists (select 1 from deletion where target_kind = 'session' and target_id = new.session_id) then
        raise exception 'retired conversation identifier cannot be reused' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function protect_document_content() returns trigger language plpgsql as $$
begin
    if (new.id,new.document_id,new.kind,new.source_content_id,new.object_key,new.mime,new.size,new.sha256)
        is distinct from (old.id,old.document_id,old.kind,old.source_content_id,old.object_key,old.mime,old.size,old.sha256)
        or (old.published_at is not null and new.published_at is distinct from old.published_at)
        or (old.cleaned_at is not null and new.cleaned_at is distinct from old.cleaned_at) then
        raise exception 'file content is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    if new.cleaned_at is not null and exists(select 1 from document d where d.id=new.document_id
        and d.deletion_id is null and (d.current_content_id=new.id or d.current_content_id=new.source_content_id)) then
        raise exception 'current content cannot be cleaned' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function protect_document_current() returns trigger language plpgsql as $$
begin
    if new.current_content_id is not null and new.deletion_id is null and not exists
        (select 1 from document_content c where c.id=new.current_content_id and c.document_id=new.id
         and c.kind='primary' and c.published_at is not null and c.cleaned_at is null) then
        raise exception 'current file content must be published and owned' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    if tg_op='UPDATE' then
        if new.purpose is distinct from old.purpose or new.quota_owner is distinct from old.quota_owner or
            (old.purpose='source' and old.current_content_id is not null and new.deletion_id is null
             and new.current_content_id is distinct from old.current_content_id) then
            raise exception 'file purpose, quota owner and source content are immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
    end if;
    return new;
end $$;

create or replace function protect_document_preview() returns trigger language plpgsql as $$
begin
    if new.kind='preview' and not exists(select 1 from document_content
        where id=new.source_content_id and document_id=new.document_id and kind='primary') then
        raise exception 'preview requires its own primary content' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function change_storage_budget(owner uuid, used_delta bigint, reserved_delta bigint)
returns void language plpgsql as $$
declare org uuid; account record;
begin
    if used_delta=0 and reserved_delta=0 then return; end if;
    select organization_id into strict org from space where id=owner;
    for account in select * from storage_budget
        where (space_id=org and scope='organization_total') or (space_id=owner and scope='local')
        order by (scope='organization_total') desc,space_id for update loop
        if (used_delta+reserved_delta>0) and
            account.used_bytes+account.reserved_bytes+used_delta+reserved_delta>account.limit_bytes then
            raise exception 'storage quota exceeded' using errcode = 'FR001',
            constraint = 'storage_quota', table = 'storage_budget';
        end if;
        update storage_budget set used_bytes=used_bytes+used_delta,reserved_bytes=reserved_bytes+reserved_delta
            where space_id=account.space_id and scope=account.scope;
    end loop;
    if (select count(*) from storage_budget where
        (space_id=org and scope='organization_total') or (space_id=owner and scope='local')) <> 2 then
        raise exception 'storage budgets must be initialized' using errcode = '23514',
            constraint = 'storage_budgets_initialized', table = 'storage_budget';
    end if;
end $$;

create or replace function require_processing_source() returns trigger language plpgsql as $$
begin
    if not exists(select 1 from document where id=new.document_id and purpose='source') then
        raise exception 'only source documents may be ingested' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function require_upload_placement() returns trigger language plpgsql as $$
begin
    if new.target_document_id is not null and not exists(select 1 from document d
        where d.id=new.target_document_id and d.space_id=new.space_id
        and d.folder_id is not distinct from new.folder_id and d.session_id is not distinct from new.session_id
        and d.purpose=case when new.purpose='source' then 'source' else 'output' end) then
        raise exception 'file write must belong to its declared destination' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

create or replace function protect_wiki_revision() returns trigger language plpgsql as $$
begin
    if (new.revision_id,new.space_id,new.content_md,new.author_user_id,new.author_kind,
        new.agent_instance_id,new.session_id,new.created_at,new.expires_at,
        new.base_revision_id,new.proposed_title)
       is distinct from
       (old.revision_id,old.space_id,old.content_md,old.author_user_id,old.author_kind,
        old.agent_instance_id,old.session_id,old.created_at,old.expires_at,
        old.base_revision_id,old.proposed_title)
       or (old.page_id is not null and new.page_id is distinct from old.page_id)
       or (new.status<>old.status and not
           ((old.status='proposed' and new.status in ('published','rejected'))
             or (old.status='published' and new.status='superseded'))) then
        raise exception 'wiki revision content and provenance are immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
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
    return new;
end $$;

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
        if (new.proposal_id, new.entry_id, new.marketplace_space_id, new.kind, new.origin_name,
            new.submitted_by, new.request_key, new.request_hash, new.package, new.package_hash,
            new.display_name, new.description, new.submitted_at)
            is distinct from (old.proposal_id, old.entry_id, old.marketplace_space_id, old.kind, old.origin_name,
            old.submitted_by, old.request_key, old.request_hash, old.package, old.package_hash,
            old.display_name, old.description, old.submitted_at) then
            raise exception 'submitted content and attribution are immutable' using errcode = '23514',
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
    return new;
end $$;

create or replace function protect_marketplace_installation() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.live_space_id is distinct from new.space_id
            or num_nonnulls(new.prompt_id, new.skill_id, new.agent_instance_id) <> 1
            or not exists (select 1 from marketplace_entry e join marketplace_proposal p
                on p.proposal_id=e.published_proposal_id join space s on s.id=new.space_id
                where e.entry_id=new.entry_id and p.proposal_id=new.proposal_id
                and p.package_hash=new.package_hash and e.kind=new.kind
                and s.organization_id=e.marketplace_space_id) then
            raise exception 'installation requires a published snapshot and a local destination' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
    else
        if (new.installation_id,new.actor,new.request_key,new.request_hash,new.entry_id,new.proposal_id,
            new.package_hash,new.kind,new.space_id,new.resource_id,new.installed_at)
            is distinct from (old.installation_id,old.actor,old.request_key,old.request_hash,old.entry_id,old.proposal_id,
            old.package_hash,old.kind,old.space_id,old.resource_id,old.installed_at) then
            raise exception 'installation receipt is immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        if (new.live_space_id is distinct from old.live_space_id and
                (new.live_space_id is not null or exists(select 1 from space where id=old.live_space_id)))
            or (new.prompt_id is distinct from old.prompt_id and
                (new.prompt_id is not null or exists(select 1 from prompt where prompt_id=old.prompt_id)))
            or (new.skill_id is distinct from old.skill_id and
                (new.skill_id is not null or exists(select 1 from skill where skill_id=old.skill_id)))
            or (new.agent_instance_id is distinct from old.agent_instance_id and
                (new.agent_instance_id is not null or exists(select 1 from agent_instance where agent_instance_id=old.agent_instance_id))) then
            raise exception 'only resource deletion detaches installation references' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
    end if;
    return new;
end $$;

comment on trigger space_immutable on space is
    'assertion: immutability - space identity and hierarchy';
comment on trigger folder_immutable on folder is
    'assertion: immutability - folder placement';
comment on trigger document_immutable on document is
    'assertion: immutability - document placement';
comment on trigger document_processing_identity on document_processing is
    'assertion: immutability - processing identity and terminal outcome';
comment on trigger folder_pending_uploads on folder is
    'assertion: consistency - no folder removal with pending uploads';
comment on trigger space_pending_uploads on space is
    'assertion: consistency - no space removal with pending uploads';
comment on trigger model_policy_organization on organization_model_policy is
    'assertion: consistency - model policy belongs to an organization';
comment on trigger organization_capability_organization on organization_capability is
    'assertion: consistency - capability policy belongs to an organization';
comment on trigger space_hierarchy on space is
    'assertion: consistency - organization root and project team parent';
comment on trigger space_role_scope on space_role_grant is
    'assertion: consistency - personal owner and organization admin scope';
comment on trigger agent_template_policy_organization on agent_template_policy is
    'assertion: consistency - template policy belongs to an organization';
comment on trigger storage_budget_scope on storage_budget is
    'assertion: consistency - immutable budget owner and valid local or organization scope';
comment on trigger prompt_definition on prompt is
    'assertion: immutability - prompt identity and creation provenance';
comment on trigger agent_definition on agent_instance is
    'assertion: immutability - agent identity, placement and creation provenance; edit attribution';
comment on trigger session_association on session_metadata is
    'assertion: consistency - same-organization conversation association and immutable ownership';
comment on trigger document_move_identity on document_move is
    'assertion: consistency - live same-organization move endpoints, frozen request and valid transitions';
comment on trigger model_source_organization on organization_model_source is
    'assertion: consistency - model source belongs to an organization';
comment on trigger model_initialization_organization on organization_model_initialization is
    'assertion: consistency - model initialization belongs to an organization';
comment on trigger remember_model_policy on organization_model_policy is
    'effect: record organization model-policy initialization';
comment on trigger space_capability_policy_kind on space_capability_policy is
    'assertion: consistency - local capability policy belongs to a team or project';
comment on trigger powerpoint_file_identity on powerpoint_file is
    'assertion: immutability - PowerPoint identity and terminal retirement; live upload owner';
comment on trigger powerpoint_agent_retirement on agent_instance is
    'effect: retire the agent PowerPoint files and schedule cleanup';
comment on trigger powerpoint_space_retirement on space is
    'effect: retire the space PowerPoint files and schedule cleanup';
comment on trigger capability_file_retirement on powerpoint_file is
    'effect: mark file capability preparations obsolete';
comment on trigger capability_agent_retirement on agent_instance is
    'effect: mark agent capability preparations obsolete';
comment on trigger powerpoint_settings_organization on organization_powerpoint_settings is
    'assertion: consistency - PowerPoint settings belong to an organization';
comment on trigger powerpoint_settings_file on organization_powerpoint_settings is
    'assertion: consistency - settings reference the effective organization file';
comment on trigger powerpoint_settings_retirement on powerpoint_file is
    'effect: clear organization settings referencing a retired or ineffective file';
comment on trigger session_identity_not_reused on session_metadata is
    'assertion: immutability - retired conversation identifiers cannot be reused';
comment on trigger document_content_immutable on document_content is
    'assertion: immutability - content bytes and publication; no current-content cleanup';
comment on trigger document_current_valid on document is
    'assertion: consistency - published owned current content and fixed source identity';
comment on trigger document_preview_valid on document_content is
    'assertion: consistency - preview belongs to its primary content';
comment on trigger document_account on document is
    'effect: adjust local and organization used storage bytes';
comment on trigger document_upload_account on document_upload is
    'effect: adjust local and organization reserved storage bytes';
comment on trigger powerpoint_file_account on powerpoint_file is
    'effect: adjust local and organization used and reserved storage bytes';
comment on trigger processing_source on document_processing is
    'assertion: consistency - ingestion only accepts source documents';
comment on trigger document_contents_retirement on document is
    'effect: schedule cleanup of retired or superseded file contents';
comment on trigger upload_placement on document_upload is
    'assertion: consistency - upload target matches its declared destination';
comment on trigger document_updates_account on document is
    'effect: aggregate local and organization used storage byte changes';
comment on trigger wiki_revision_immutable on wiki_revision is
    'assertion: immutability - wiki revision content and provenance';
comment on trigger marketplace_entry_identity on marketplace_entry is
    'assertion: immutability - marketplace identity and successive publication versions';
comment on trigger marketplace_proposal_immutable on marketplace_proposal is
    'assertion: immutability - submitted package, attribution and final decision';
comment on trigger marketplace_installation_immutable on marketplace_installation is
    'assertion: immutability - installation receipt and snapshot provenance';
