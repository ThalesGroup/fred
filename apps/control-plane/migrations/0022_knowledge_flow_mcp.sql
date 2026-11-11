-- One trusted service, one central offer, shared by all compatible pods.
-- No seeded authorization, selection or legacy-data conversion.
create unique index mcp_connection_tabular_service on mcp_connection
    ((configuration #>> '{authentication,kind}'))
    where configuration #>> '{authentication,kind}' = 'knowledge_flow_tabular';
