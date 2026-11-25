-- An HTTP service origin is owned by one organization, including across UI/API roles.
-- Fresh installations only; no ownership is inferred for existing destinations.
create table application_service (
    origin text primary key,
    organization_id uuid not null references space(id) on delete cascade,
    unique(origin, organization_id)
);
create index application_service_organization on application_service(organization_id);

alter table application
    add column ui_origin text generated always as (substring(ui_base_url from '^https?://[^/]+')) stored,
    add column api_origin text generated always as (substring(api_base_url from '^https?://[^/]+')) stored,
    add foreign key(ui_origin, organization_id) references application_service(origin, organization_id) deferrable initially deferred,
    add foreign key(api_origin, organization_id) references application_service(origin, organization_id) deferrable initially deferred;

comment on table application_service is
    'Exclusive organization ownership of canonical HTTP origins; deployment isolation and DNS aliases remain operator responsibilities.';
