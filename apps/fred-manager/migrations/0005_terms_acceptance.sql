-- Consent belongs to an authenticated subject, independently of directory or space membership.
create table terms_acceptance (
    user_id text primary key,
    version text not null check (length(version) between 1 and 128),
    accepted_at timestamptz not null default now()
);
