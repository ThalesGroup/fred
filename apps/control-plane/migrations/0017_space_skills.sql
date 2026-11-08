-- Space-owned instruction packages. A replacement commits all files together;
-- admission copies the package, so a running turn never mixes two revisions.
create table skill (
    skill_id uuid primary key,
    space_id uuid not null references space(id) on delete cascade,
    name text not null check (length(name) between 1 and 64 and name ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    summary jsonb not null check (jsonb_typeof(summary) = 'object'),
    files jsonb not null check (jsonb_typeof(files) = 'object' and files ? 'SKILL.md'),
    revision text not null check (revision ~ '^[a-f0-9]{64}$'),
    created_by text not null,
    updated_by text not null,
    created_at timestamptz not null default clock_timestamp(),
    updated_at timestamptz not null default clock_timestamp(),
    unique (space_id, name),
    check (summary->>'name' = name)
);

-- Immutable history remains; no live pod-owned skill diagnostics survive.
alter table runtime_catalog drop column skills_revision, drop column skills_availability;
