-- Profiles observed after authentication, as in Python's local user directory.
-- No grants or membership live here. Usernames are not unique at the provider.
create table user_identity (
    id uuid primary key,
    username text not null,
    email text,
    first_name text,
    last_name text,
    last_seen_at timestamptz not null default now()
);
create index user_identity_username on user_identity (username, id);
