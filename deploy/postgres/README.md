# PostgreSQL component boundary

`bootstrap.sql` is the canonical administrator-owned initialization source.
The chart's `files/bootstrap.sql` is a generated copy, packaged by
`make generate-chart-schema`. Never edit the packaged copy. The k3d factory reads
the source directly from the Fred checkout.

| Login | Owned schemas | Cross-component SELECT (through its NOLOGIN reader group) |
| --- | --- | --- |
| fred_cp | control_plane, cp_read | None required |
| fred_kf | knowledge | document_visibility, published_artifact, space_state, folder_path, conversation |
| fred_runtime | runtime | terms_acceptance |
| fred_monitor | None | platform_role_grant |

All view names above are qualified by `cp_read`. Consumers have USAGE on cp_read,
SELECT on their own views, no write grants on those views, and no privileges on
control_plane. No blanket default SELECT grants are used. All four logins have
CONNECT only at database level, no CREATEROLE/CREATEDB/superuser/BYPASSRLS, and no
public schema privileges. Monitor also defaults to read-only transactions and
has a four-connection limit; ACLs still deny writes when it disables that default.
Knowledge's vector extension is installed by the administrator, not KF.

Connections explicitly select their owning schema. Thus unqualified owner DDL
lands in that schema, never in public; a schema-qualified CREATE in public fails.
A literal ban on all unqualified CREATE would contradict the owner's search_path
and the existing SQLx/Alembic migrations; schema ACLs enforce the intended boundary.

## Managed installation

1. Provision a fresh database and a PostgreSQL server with the vector extension
   available. Use an administrative session connected to that database. Retain
   required old data separately; this procedure does not migrate it.
2. Run `psql -X -v ON_ERROR_STOP=1 -v database=fred -d fred -f deploy/postgres/bootstrap.sql`.
   Use your protected connection environment or pgpass file for authentication,
   not a password in the command. Serialize bootstrap executions per cluster.
3. Set four distinct login passwords with `ALTER ROLE ... PASSWORD ...` through
   protected stdin or a secret-management client; disable statement and error SQL
   logging for that session. Audit extensions must also redact these statements.
   Do not store passwords in values files. Supply the component keys declared in
   `postgresSecrets`, and a URL-encoded monitor DATABASE_URL using fred_monitor.
   Helm's migration URL interpolation requires URI-safe component passwords
   (the factory generates them with token_urlsafe); the admin password has no
   such restriction because psql receives it through PGPASSWORD.
4. Run `control-plane initialize-schema` as fred_cp with DATABASE_URL provided
   through the environment. This installs control_plane tables/history, cp_read
   views and their SELECT grants.
5. Run `python -m fred_runtime migrate` as fred_runtime. When using DATABASE_URL
   without application config, also set DATABASE_SCHEMA=runtime. Alembic history,
   session history, turn steering, web research and checkpoints belong to runtime.
6. Start applications. KF uses fred_kf/knowledge; pgvector can create its own tables
   there but cannot create extensions. HTTP authorize/scope remains authoritative
   for a person's permissions.

The optional `postgresBootstrap.enabled=true` Helm hook automates steps 2-3 using
an existing admin Secret and four existing component password keys. Its hook
weights are ConfigMap -30, bootstrap -20, migration credential -15, Control Plane
schema -10, runtime migration 0. With the default false, the DBA performs steps
2-3 before Helm. Secrets must exist before any pre-install hook runs.

Bootstrap is replayable on the new layout. It reapplies restrictive role flags,
checks memberships, sets owners and schema ACLs, and never overwrites passwords.
It refuses a vector extension in another schema. It does not drop old tables,
objects or accounts: an old public installation requires explicit recreation.
Review existing explicit ACLs, PUBLIC grants and ownership before reusing a
previously administered database. Revoking PUBLIC alone does not remove direct
privileges of unrelated legacy roles, nor empty public. In particular the old
fred login and any old monitor-database Secret are removed manually after their
consumers are gone; first transfer database ownership away from fred if necessary.
No automatic DROP OWNED or data deletion is performed.

Integration tests use this exact bootstrap through psql, on a disposable pgvector
server with an admin fixture account. Environments without role administration
must use that disposable container (or a dedicated DBA-provisioned test cluster),
not bypass the consumer-login privilege checks.
