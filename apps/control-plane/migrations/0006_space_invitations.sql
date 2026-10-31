-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Storage only: authorization still reads space_role_grant. Invitation roles
-- must never be copied there as permanent grants when invitations are enabled.
create table space_invitation (
    id uuid primary key,
    space_id uuid not null references space(id) on delete cascade,
    subject text not null check (length(btrim(subject)) > 0),
    invited_by text not null check (length(btrim(invited_by)) > 0),
    created_at timestamptz not null default now() check (isfinite(created_at)),
    expires_at timestamptz not null check (isfinite(expires_at)),
    revoked_at timestamptz check (isfinite(revoked_at)),
    revoked_by text check (length(btrim(revoked_by)) > 0),
    check (expires_at > created_at),
    check ((revoked_at is null) = (revoked_by is null)),
    check (revoked_at >= created_at)
);
-- Subjects belong to the identity provider, not to the local profile cache.
-- Expiration is a read predicate, never a persisted status or index predicate.
create index space_invitation_space on space_invitation (space_id, subject, created_at desc, id);
create index space_invitation_subject on space_invitation (subject, space_id, expires_at)
    where revoked_at is null;

create table space_invitation_role (
    invitation_id uuid not null references space_invitation(id) on delete cascade,
    role text not null check (role in ('member','editor','owner','analyst','organization_admin')),
    primary key (invitation_id, role)
);

create function require_space_invitation_scope() returns trigger language plpgsql as $$
begin
    if TG_OP = 'UPDATE' then
        if (new.id, new.space_id, new.subject, new.invited_by, new.created_at)
            is distinct from (old.id, old.space_id, old.subject, old.invited_by, old.created_at) then
            raise exception 'invitation identity is immutable' using errcode = '23514';
        end if;
    elsif exists (select 1 from space where id = new.space_id and kind = 'personal') then
        raise exception 'personal spaces cannot receive invitations' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger space_invitation_scope before insert or update on space_invitation
    for each row execute function require_space_invitation_scope();

create function require_space_invitation_role_scope() returns trigger language plpgsql as $$
begin
    if new.role = 'organization_admin' and exists (
        select 1 from space_invitation i join space s on s.id = i.space_id
        where i.id = new.invitation_id and s.kind <> 'organization'
    ) then
        raise exception 'organization admin requires an organization' using errcode = '23514';
    end if;
    return new;
end $$;
create trigger space_invitation_role_scope before insert or update on space_invitation_role
    for each row execute function require_space_invitation_role_scope();
