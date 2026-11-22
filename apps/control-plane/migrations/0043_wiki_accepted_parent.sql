-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Fresh installations only. Pending creations depend on their proposed destination;
-- accepted content belongs to its entry and follows only its current placement.
set local lock_timeout = '5s';

alter table wiki_revision add constraint wiki_revision_accepted_parent check (
    status = 'proposed' or proposed_parent_page_id is null);

create or replace function protect_wiki_revision() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        -- Agent provenance and file bytes come only from a conversation: such a proposal,
        -- even a person's own, is born a draft and a person's own is detached at once.
        if new.session_id is null and (new.agent_instance_id is not null or new.document_id is not null) then
            raise exception 'agent provenance and Wiki files come from a conversation' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        -- A draft carries its live conversation's owner and agent, as the person saw it.
        if new.session_id is not null and not exists(select 1 from session_metadata m
            where m.session_id = new.session_id and m.space_id = new.space_id
            and m.user_id = new.author_user_id and m.deletion_id is null
            and m.agent_instance_id = new.agent_instance_id and m.agent_display_name = new.agent_name) then
            raise exception 'a draft belongs to its author''s live conversation' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        -- A file revision owns one live Wiki copy of the same space, holding exactly the
        -- current bytes of an output of its conversation.
        if new.document_id is not null and not exists(select 1 from document d
            join document_content c on c.id = d.current_content_id
            join document o on o.session_id = new.session_id and o.space_id = d.space_id
                and o.purpose = 'output' and o.deletion_id is null
            join document_content oc on oc.id = o.current_content_id
            where d.id = new.document_id and d.space_id = new.space_id and d.purpose = 'wiki'
            and d.deletion_id is null and (oc.size, oc.sha256, oc.mime) = (c.size, c.sha256, c.mime)) then
            raise exception 'a file revision owns a live Wiki copy of its conversation''s output' using errcode = '23514',
                constraint = TG_NAME, table = TG_TABLE_NAME;
        end if;
        return new;
    end if;
    if (new.revision_id, new.space_id, new.entry_kind, new.content_md, new.document_id,
        new.author_user_id, new.agent_instance_id, new.agent_name, new.created_at,
        new.base_revision_id, new.proposed_title)
       is distinct from
       (old.revision_id, old.space_id, old.entry_kind, old.content_md, old.document_id,
        old.author_user_id, old.agent_instance_id, old.agent_name, old.created_at,
        old.base_revision_id, old.proposed_title)
       -- Only acceptance releases the proposed destination; content and provenance stay immutable.
       or (new.proposed_parent_page_id is distinct from old.proposed_parent_page_id
           and not (old.status = 'proposed' and new.status = 'published'
               and new.proposed_parent_page_id is null))
       or (old.page_id is not null and new.page_id is distinct from old.page_id)
       -- Confirmation only detaches a draft from its conversation.
       or (new.session_id is distinct from old.session_id and new.session_id is not null)
       or ((new.reviewed_at, new.reviewed_by) is distinct from (old.reviewed_at, old.reviewed_by)
           and old.status <> 'proposed')
       or (new.status <> old.status and not
           ((old.status = 'proposed' and new.status = 'published')
             or (old.status = 'published' and new.status = 'superseded'))) then
        raise exception 'wiki revision content and provenance are immutable' using errcode = '23514',
            constraint = TG_NAME, table = TG_TABLE_NAME;
    end if;
    return new;
end $$;

comment on trigger wiki_revision_immutable on wiki_revision is
    'assertion: immutability - wiki revision content and provenance; conversation provenance only through a draft of its owner''s live conversation; file revisions copy one of its outputs; only acceptance clears the proposed parent';
