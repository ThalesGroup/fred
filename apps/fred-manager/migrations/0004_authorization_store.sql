-- Roles remain in OpenFGA. This pointer publishes a completely initialized store;
-- it never stores grants, permissions or pending mutations.
create table authorization_store (
    singleton boolean primary key default true check (singleton),
    configured_store text not null,
    source_store text not null,
    active_store text not null,
    model_id text not null
);
