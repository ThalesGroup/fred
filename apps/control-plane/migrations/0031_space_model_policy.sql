-- Local restrictions and preferences, never model grants. Depends on the model
-- catalogue and spaces in 0001; 0028 is reserved by the team-settings lot.
create table space_model_policy (
    space_id uuid primary key references space(id) on delete cascade,
    revision bigint not null check (revision > 0),
    default_source_id text collate "C",
    default_upstream_model_id text collate "C",
    updated_by text not null,
    updated_at timestamptz not null default clock_timestamp(),
    check ((default_source_id is null) = (default_upstream_model_id is null)),
    foreign key (default_source_id, default_upstream_model_id)
        references model_offer(source_id, upstream_model_id)
);
create table space_model_setting (
    space_id uuid not null references space_model_policy(space_id) on delete cascade,
    source_id text collate "C" not null,
    upstream_model_id text collate "C" not null,
    disabled boolean not null,
    reasoning_default_on boolean not null,
    primary key (space_id, source_id, upstream_model_id),
    foreign key (source_id, upstream_model_id) references model_offer(source_id, upstream_model_id),
    check (disabled or reasoning_default_on),
    check (not (disabled and reasoning_default_on))
);
create function require_local_model_policy() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from space where id=new.space_id and kind in ('team','project')) then
        raise exception 'local model policy requires a team or project' using errcode='23514';
    end if;
    return new;
end $$;
create trigger space_model_policy_kind before insert or update on space_model_policy
    for each row execute function require_local_model_policy();
comment on trigger space_model_policy_kind on space_model_policy is
    'assertion: consistency - local model policy belongs to a team or project';
