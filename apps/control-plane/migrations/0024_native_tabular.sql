-- Internal Knowledge Flow is admitted directly, never an organization connection.
-- Fresh installations only; no conversion of historical selections or permissions.
drop index mcp_connection_tabular_service;
alter table mcp_connection add constraint mcp_external_authentication check (
    coalesce(configuration #>> '{authentication,kind}', '') in ('none', 'bearer', 'api_key')
);
