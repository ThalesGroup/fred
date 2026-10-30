# Publishing a changed authorization model

Startup and Python consumers require the exact published model. They never replace
an incompatible model automatically. `sync_schema_on_init` initializes an empty
installation; it does not upgrade an existing publication.

For a reviewed model change that can retain the existing tuples:

1. Stop every Control Plane and Python consumer, including old rollout replicas
   and operator imports. Back up the Fred database, the published model and all
   tuples in its active store. Inspect the SQL migration history.
2. Compare the published model with this release's `model.json`. Verify that the
   tuples remain meaningful under the new rules. This command does not transform
   or delete tuples and is not a general data migration tool.
3. With the target release's binary and the installation's configuration and
   credentials, read `model_id` from `authorization_store` and run:

   ```sh
   control-plane publish-authorization-model --expected-model <published-model-id>
   ```

4. Restart all consumers using the target release. Check their actual image IDs
   and readiness; an old ready replica does not validate the new release.

The command requires an initialized SQL schema and an existing publication. Under
the existing publication lock it checks the configured store and expected model
ID, writes the embedded model to the same active store, reads it back through the
normal strict validator, then commits the new model ID in PostgreSQL. An already
matching model is unchanged. The store, tuples, SQL resources and bootstrap marker
are preserved. The lock does not stop running consumers, which retain their model
ID until restarted; stopping them is an operator prerequisite.

An OpenFGA write and a SQL commit are not one distributed transaction. A failure
can leave an unreferenced model in OpenFGA. Inspect `authorization_store` after a
failure; its model ID remains the authority, not OpenFGA's latest model. Do not
resume an old binary against a new binding or reset SQL to repair a model mismatch.

The current model uses `platform_admin` and `organization_admin` for technical
administration, and `owner` for business governance. Earlier Weaver models used
`platform_owner`, `organization_owner` and `admin` respectively. These identifiers
and the provisioning role declarations are intentionally incompatible; a fresh
installation uses the current demo bundle. Publishing a model alone does not
rename existing tuples. The current branch targets a fresh local installation;
no role-tuple migration is provided.

Personal-space eligibility is now derived from a business owner role on an active
organization, team or project. There is no separate `personal_space_creator` grant.
Control Plane resolves those scopes from paginated OpenFGA roles and active SQL
placement, checks eligibility, and requires the personal space's own read/write
permission. Technical-only admins do not qualify.
