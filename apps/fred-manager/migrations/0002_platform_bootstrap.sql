-- Durable root-bootstrap marker: the row exists once bootstrap has completed, and
-- never goes away. Not control-plane's `platformbootstrap`: both services share the
-- fred database and each keeps its own one-time bootstrap.
create table platform_bootstrap (
    singleton    boolean primary key default true check (singleton),
    completed_by text not null,
    completed_at timestamptz not null default now()
);
