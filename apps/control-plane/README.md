# control-plane

Fred's service for spaces, folders, documents and their authorization. Its design,
invariants and decisions are in the architecture dossier:
[docs/architecture](../../docs/architecture/README.md). This file says how to work on it. Use the [source map](src/README.md) to locate a feature.

## Develop

Same targets as the other apps (`make help` lists them). Building needs `protoc`;
`PROTOC` defaults to `~/bin/tools/protoc/bin/protoc`.

Rust packages share the repository-root Cargo workspace and `Cargo.lock`.
Authentication and platform-role reads come from the internal
[`fred-rust-sdk`](../../libs/fred-rust-sdk/README.md); Control Plane retains schema
and role-mutation ownership. Docker builds use the repository root as context.

```
cp config/.env.template config/.env   # once: the four secrets
make run                              # http://localhost:8222/control-plane/v1
make test                             # offline unit tests
make test-integration                 # throwaway Postgres and Keycloak containers
make test-lifecycle-temporal          # disposable SQL/Temporal worker recovery
make code-quality                     # model parity + clippy + rustfmt
make -C ../../docs/architecture check # the dossier still matches the code
```

## Organization supervision

Control Plane serves organization totals and team detail, gated by organization
attachment. The [supervision contract](../../docs/architecture/A8-organizations.md#organization-supervision)
defines counters, privacy boundaries, pagination and the UI. The generated
[REST inventory](../../docs/architecture/A12-control-plane-api.md#organizations-routes)
lists its operations; supervision does not require a separate service.

## Embedded Rust agent

The same process serves `POST /control-plane/v1/agents/execute/stream` (under the
configured base URL). It uses the existing authentication and consent checks and
streams Fred runtime events. Managed instances use the common inference admission
and Rig; direct `agent_id: "fred.github.ralph"` remains a fixed demonstration. See the
[agent library](../../libs/fred-rust-agent/README.md) for the contract and current integration limits.
The host stores Rig's opaque log in `embedded_agent_conversation`, keyed by the
existing private session. Successful turns restore and append that log; the title
call stays memoryless. `GET /agents/sessions/{session_id}/messages` projects it
into the shared chat history contract under the same configured base URL.
No additional server or deployment is required. Apply migrations 0009 and 0010
before startup; the latter indexes sessions awaiting retirement receipts.

## Knowledge Base admission (reception pending)

The HTTP/SDK admission boundary accepts managed mirrors in dedicated space folders;
the Knowledge Base administration UI is not yet connected to it. Apply the complete
migration chain to a fresh installation. Document storage, processing and Temporal
must be configured. A source worker needs an explicit workload binding, not an
HTTP agent endpoint:

```yaml
platform:
  knowledge_bases:
    workers:
      webdav-knowledge-base:
        issuer: https://identity.example/realms/app
        client_id: kb-fred.webdav
        audience: app
    credentials:
      - runtime_id: webdav-knowledge-base
        space_id: 00000000-0000-0000-0000-000000000001
        credential_binding: webdav-research
```

Use the actual issuer, audience, runtime and destination space. Credential bindings
contain no secret: the connector's `knowledge_base.secret_bindings` maps each approved
reference to an environment variable. Set its `knowledge_base.protocol: weaver` and
Control Plane URL; the connector uses the ordinary SDK `publish` and `run` commands.
Publishing creates an offer; enable that offer through existing organization and
space policy before a space Owner creates an instance or starts a run.

The generated [REST inventory](../../docs/architecture/A12-control-plane-api.md)
lists definition, instance and run operations. Source configuration and destination
are immutable; pause/interval changes govern subsequent runs. Pausing keeps stored
content, and already admitted document processing can finish. This boundary does
not enable manual replacement or reprocessing in Resources. See the
[storage contract](../../docs/architecture/A9-documents.md#managed-mirror-admission)
for publication, withdrawal and cleanup ownership.

## Metrics

`app.metrics_port` opens an unauthenticated Prometheus `GET /metrics` listener,
outside `base_url`; absent, there is none. The chart sets 9222 as the container's
`metrics` port, which neither the Service nor the ingress routes. The series reuse
the Python KPI names: see the [Fred bench dashboard](../../deploy/grafana/README.md#fred-bench).

## From scratch (fred-deployment-factory)

**Host run**: see the [first start](../../deploy/k3d/README.md#first-start).
`config/configuration_prod.yaml` points to the Docker Compose services. Against
another fresh database, run `make initialize-schema` here with `DATABASE_URL`
pointing to its `fred_cp` login.

API startup only verifies the installed schema fingerprint. The explicit
initialization command creates the schema atomically, or does nothing when the
same schema is already installed. It refuses an incompatible database.

**In the cluster, after `make k3d-up`**, from fred-deployment-factory:

```
make k3d-app FRED=weaver APP=fred DIR=../fred            # build, import, sync
make k3d-app-validate FRED=weaver APP=fred DIR=../fred   # lint and render only
kubectl --context k3d-fred -n fred-weaver logs deploy/control-plane-backend
```

Use `ENV=secondary` for this checkout's local profile. It deploys
`control-plane-backend`, `knowledge-flow-worker` and `frontend`; HTTP and background
tasks run together as `control-plane serve`. See [the profile](../../deploy/k3d/README.md).
Open Fred and check the connected SSO identity. Enter the installation bootstrap secret
to activate platform administration for that account, then accept the CGU before
using protected operations. Status reads do not create a local profile or consent.
See [independent platform initialization](../../docs/architecture/A6-security.md#independent-platform-initialization). The local service uses `FRED_BOOTSTRAP_TOKEN` from `config/.env`.
The k3d Fred values read the cluster secret `fred-secrets` key
`CONTROL_PLANE_BOOTSTRAP_TOKEN`; use the value supplied by your deployment.

The root is platform admin and has no organization membership. Open
**Provisioning**, import the ZIP built below, then sign out and sign in as an
imported user. That person accepts their own CGU and sees their declared spaces.
There is no automatic personal space or default-team enrollment.

`app.gcu_version: v1` enables this step in the reference and k3d configurations.
Changing the version requires everyone, including root, to accept again. Publish
the corresponding frontend `gcu.<language>.md`/`gcu.md` assets with the version;
`null` disables the gate. Existing Python consent and bootstrap records are not
manager consent or bootstrap records.

## Commands

| Command | Purpose |
| --- | --- |
| `control-plane serve` | HTTP API and its background tasks (default) |
| `control-plane discover-agents` | Describes the embedded agent and public templates from enabled configured runtimes; JSON output, no SQL or enrollment |
| `control-plane initialize-schema` | Creates the complete schema from `DATABASE_URL`; repeatable on the same schema, refuses incompatible history |
| `control-plane generate-openapi` | Prints the HTTP contract, without configuration or services |
| `control-plane generate-config-schema` | Prints the configuration JSON Schema |
| `control-plane processing-schema` | Prints the wire contracts shared with the Knowledge Flow worker |
| `control-plane register-local-user <weaver-user-id> <username>` | Explicitly registers a known identity in the local directory, without roles or consent |
| `control-plane import-provisioning <bundle.zip> --token-file <path>` | Authenticated additive import ([below](#import-a-provisioning-bundle)) |

### Admit a user with the local directory

With `security.user_directory: local` (required for generic OIDC), a deployment
operator explicitly registers the identity before an administrator assigns its
first role. Use the canonical Weaver UUID returned by the person's authenticated
`GET /me/onboarding` and the exact username verified with the identity provider.
For non-UUID OIDC subjects, this Weaver ID is different from the provider's raw
subject; do not substitute the username or compute another mapping.

```sh
control-plane register-local-user <weaver-user-id> <username>
```

The command uses the usual `CONFIG_FILE` and deployment database credentials, like
`initialize-models`; it requires enabled authentication and the local directory.
It reuses `user_identity`, creates no provider account, role, personal space or
CGU acceptance, and refuses to replace an existing subject's different username.
Replaying the same registration preserves the profile. The administrator then
uses the existing organization governance or role-grant API/UI. Only after this
grant can the person accept CGU and enter Weaver. Merely signing in with a Swift
SSO identity never performs this registration.

## Discover agent definitions

`control-plane discover-agents` loads the usual `ENV_FILE` and `CONFIG_FILE`,
includes the embedded `control-plane` catalog without a network request or source
configuration, then calls each enabled `platform.runtime_catalog_sources` entry:

```yaml
platform:
  runtime_catalog_sources:
    - runtime_id: fred-agents
      base_url: http://localhost:8000/fred/agents/v2
      enabled: true
```

From `apps/control-plane`, run `cargo run --locked -- discover-agents` after
starting fred-agents. The runtime's public `GET /agents/templates` endpoint needs
no bearer. Output is a JSON array of `{runtime_id, templates}`; template payloads
retain tuning, capability metadata and additional runtime fields. Internal
(non-public) templates are excluded. Disabled sources are not contacted; an
omitted platform configuration yields only `control-plane`, with one `fred.github.ralph`
template of the same name, version `0.1.0`. Its direct demonstration path replies
`Hello world!` without an LLM or data access. The managed path described below
requires an admitted instance and local inference provisioning. Its `kind` is `static`: the Rust discovery field
is a free string, and no ReAct or Graph engine runs this fixed response.
`control-plane` is reserved: configuring an external source with that identifier
is rejected, even when disabled.

The existing Administration Console -> Features -> Agents tab reads this same
catalog through `GET /control-plane/v1/organizations/{organization_id}/agents`.
Admission, a direct role in that organization, active lifecycle and `can_manage` on an
organization are required; neither organization attachment alone nor platform
roles bypass this check. The page reads projected template identities and their organization defaults.
Its existing switch writes `PUT /organizations/{organization_id}/agents/{agent_id}/default-on`.
The default starts off and is stored in `agent_template_policy`. No enrollment or
instance state is inferred. The write reuses platform/organization locks after discovery; no
runtime call holds a SQL transaction. Templates declaring tool dependencies cannot
be enabled by this initial integration. The supplied local configuration disables the
external fred-agents source; with no enabled external source the embedded catalog
requires no fred-agents process. An explicitly enabled source still fails the
whole discovery if unavailable.

This operator command uses a 10-second timeout per source and exits with an error
if any source fails, without printing a partial catalog. It does not start the API,
connect to SQL, persist definitions or enroll instances. `serve` does not
poll runtimes. This command does not enroll or execute agents.

## Space skills

`0017_space_skills.sql` stores each package in its owning space. The shared
`authorization::readable_path` determines conversation scope: current space and
parents with a direct reading role, with the existing personal-space boundary.
Management reads the exact owning space. `spaces::authorized_mutation` applies
Write permission and the organization mutation lock, as for prompts. Creator
identity is provenance, not authority. Space deletion cascades to its packages.

The binary ships no skill. Distributed packages are data, in language packs under
`skill-packs/<language>/<name>/`: `en` holds the seven Swift packages
(`analyze-data`, `compare-options`, `graph`, `grill-me`, `grounded-research`,
`meeting-minutes`, `summarize-document`), whose instructions, references, MIT
attribution and license were preserved from Swift
`d7e7f99e75e3e7cc2d97b53cf652c85955d621ae`; `fr` translates all seven with
the same names and invocation controls. A deployment
installs one pack per organization; there is no runtime translation.

A [provisioning bundle](#import-a-provisioning-bundle) places packages in declared
spaces, creating each one absent by name and never replacing a present one, edited or
not. A provisioned package is ordinary space content marked `builtin`; an edit makes
it the space's own. Writers otherwise create packages in the space's Skills page,
where the Control Plane validates the same contract. Nothing is activated without
an import or a writer's action.

`/spaces/{id}/skills` lists owned packages and accepts POST creation.
GET/PUT/DELETE on `/{skill_id}` manages an existing package by its immutable UUID
and owning space. PUT includes the expected content revision and replaces all files
atomically. `/scope` and `/scope/{skill_id}` expose the shared readable scope.

A skill's logical name is a label, not its execution identity. Homonyms in
readable spaces remain separate catalog entries, with their UUID and owning space.
The composer displays the space, retains the selected identity through edits and
recall, and requires an explicit choice for an ambiguous typed name. Admission
validates the identity/space pair. Deletion or revocation cannot silently select
another package with the same name. Runtime snapshots and native Deep pins are
keyed by UUID; authored SKILL.md content is unchanged.

Private execution admission includes the authorized files and their catalog
revision. Public preparation contains only metadata. The pod reads that admitted
copy, so instructions and references cannot come from different revisions.
A running turn keeps its admitted copy. Skills no longer participate in pod
capability inventory or tool-offer policies; tool authorization remains separate.

The packages pass [Agent Skills](https://agentskills.io/specification) reference
validator `skills-ref` 0.1.0 at revision
`83021e2be457a9b6679148719c1f6074f0ad975e` (`skills-ref validate skill-packs/<language>/<name>`).
Fred supports ASCII skill names, UTF-8 `.md`, `.txt`, `.json`, `.yaml`, `.yml` and
`.csv` resources, at most 64 skills, 128 files/package, 64 KiB/file and 4 MiB per
space/admitted snapshot. Binary assets and script execution are unsupported.
Standard packages need no Fred-specific adaptation; `allowed-tools` never grants
permissions or registers tools. Fred-specific invocation controls are string
values in `metadata`: `fred-argument-hint`, `fred-user-invocable` (default `"true"`),
`fred-disable-model-invocation` (default `"false"`). Old top-level controls are
rejected. The reference validator is a development check, not a runtime dependency.

Tests cover fresh SQL initialization, direct-space rights, parent scope, atomic
replacement, previews and immutable admission. These are automated checks, not
k3d/platform functional reception.

## Platform model inventory and organization administration

`platform.model_sources` defaults to `[]` in the schema. The host development
configuration and checkout-owned k3d overlay opt into the Mistral and OpenAI test
sources; see [the local model setup](../../deploy/k3d/README.md#models-for-local-testing).
`serve` applies these non-secret approvals to SQL after checking the schema, then
runs the bounded organization initialization below. Organization APIs expose only
assigned sources and persist explicit choices. There is no background model polling. The internal `configure_sources`,
`refresh` and `inventory` operations remain available to trusted Rust callers;
`refresh(pool, source)` requires the exact persisted platform configuration and
carries no user authorization. Administrative routes instead own the claim and
publication transactions and reuse that same M1 discovery adapter.

Example of a **disabled, fictitious** source (no credential value is provided):

```yaml
platform:
  model_sources:
    - source_id: example-gateway
      revision: 1
      enabled: false
      inventory:
        kind: discovered
        url: https://catalog.example.invalid/v1/models
        authentication:
          mode: bearer
          secret_env_var: EXAMPLE_MODEL_DISCOVERY_TOKEN
          provider_scopes: [provider-list-scope]
          authority: discovery_only
        qualification: mixed_capabilities_v1
        complete_inventory_guaranteed: true
      inference:
        credential_binding: example-gateway-inference
        api_root: https://inference.example.invalid/v1
        wire: openai_chat
        route: standard
        dialect: openai_compatible
        auth:
          kind: api_key
      visibility_scope: example-account-namespace-all-models
      # Platform attestation: model lists do not say which offers embed.
      # Such an offer is never chat; it can be an organization's corpus model.
      embedding_models: [example-embedding]
    # A source without a usable model list: the platform declares its models.
    - source_id: example-declared-gateway
      revision: 1
      enabled: false
      inventory:
        kind: declared
        models:
          - id: example-model
            display_name: Example model   # optional
            reasoning: false              # optional; absent means unknown
            context_window_tokens: 128000 # optional, like the next two
            max_input_tokens: 120000
            max_output_tokens: 4096
      inference:
        credential_binding: example-declared-gateway-inference
        api_root: https://gateway.example.invalid/v1
        wire: openai_chat
        route: standard
        dialect: openai_compatible
        auth:
          kind: api_key
      visibility_scope: example-gateway-deployments
```

### Configure organization models

`platform.organization_models` declares exact existing organization names (the same
PostgreSQL lookup as provisioning), explicit source IDs and exact offer keys. It
never creates an organization. This fictitious example assumes the two separately
approved, enabled sources can publish the named chat models:

```yaml
platform:
  organization_models:
    - organization: Example Research
      sources: [research-account, shared-gateway]
      permitted:
        - {source_id: research-account, upstream_model_id: chat-v1}
        - {source_id: shared-gateway, upstream_model_id: backup-v2}
      default: {source_id: research-account, upstream_model_id: chat-v1}
      fallback: {source_id: shared-gateway, upstream_model_id: backup-v2}
      reasoning_enabled:
        - {source_id: research-account, upstream_model_id: chat-v1}
      embedding: null   # optional: an attested embedding offer, also permitted
      vision: null      # optional: a permitted chat offer describing document images
    - organization: Example Support
      sources: [support-account]
      permitted: []
      default: null
      fallback: null
      reasoning_enabled: []
```

Different provider accounts require different `source_id` values even at the same
URL. Sharing a source with two organizations requires two explicit assignments.
At most 64 organizations, 64 sources per organization and 4096 permitted offers
are accepted. Reasoning requires a permitted, source-reported reasoning-capable
offer. A missing or unavailable model fails initialization; no substitute is picked.
Each choice must fit its use: chat offers for default, fallback and title, an attested
embedding offer for `embedding`, and a chat offer not reported without image input
for `vision`. Documents are not processed before an organization has an embedding
model, and its first indexing locks it: later writes keep that choice
(`embedding_model_locked`), and a trigger refuses to change, release or delete it.

Deployment order:

1. Provision existing Kubernetes Secrets/environment references and runtime-local
   inference bindings; initialize the schema through the deployment Job.
2. Start Control Plane with platform source approvals and organization declarations.
   The initial pass defers missing organizations, with a diagnostic.
3. Provision organizations through the existing organization API, Provisioning UI
   or `import-provisioning` CLI. After its commit, the caller runs a separate model
   initialization pass; the Swift bundle format does not contain model settings.
   The k3d overlay explicitly declares Acme and Globex, so the demo import requires
   no additional model manipulation in the UI.

For existing organizations, `serve` applies pending declarations on startup. For
recovery or deployment automation after external organization provisioning, run
`control-plane initialize-models` with the same `CONFIG_FILE` and environment as
Control Plane (for k3d: `kubectl exec deployment/control-plane-backend --
control-plane initialize-models`, with the deployment context/namespace). This trusted operator command uses deployment database credentials, not a
browser token, starts no service and requires every declared organization to exist.
Each pass has a 120-second deadline; discovery retains its five-second per-source
limit and runs outside transactions.

**Add sources on every pass; seed policy only once.** Startup and provisioning add
`sources` to each named organization under its existing lock, including organizations
already initialized. Replays preserve permissions, policy revisions, document models,
defaults and completion receipts, and perform no discovery for an administered policy.
The Owner refreshes newly assigned sources and permits their models in the Models UI.
Empty or deleted policies are not recreated. Removing a source from YAML does not
revoke an existing assignment; disable the source or withdraw model permissions to
stop its use. Source revision changes and credential rotation remain handled by
`configure_sources`. Keep identical declarations across replicas.

Every model permission references an explicit organization source assignment from
creation. The foreign key is validated in the initial schema. Already administered
policies (including empty or deleted policies) remain protected from YAML reseeding;
there is no migration of historical model decisions.

Failures identify the declaration index and a fixed diagnostic such as
`unknown_model_offer`, `model_offer_not_selectable` or `model_discovery_failed`.
Correct the exact ID, source configuration or discovery dependency and replay
`initialize-models`. No failed organization receives partial permissions or a
completion receipt; earlier successful organizations and the organization provisioning
itself remain committed. Discovery failure retains the last inventory. No provider
body, token or configuration value is included in initialization diagnostics.
Do not delete receipts to retry. To add a source, update the existing organization
declaration and restart Control Plane; no UUID lookup or manual assignment is needed.

### Assign a source after initialization

For deployment-managed organizations, use `platform.organization_models.sources`
as described above. The existing operator command remains available for an explicit
assignment outside those declarations:

```sh
control-plane assign-model-source <organization-uuid> <source-id>
```

It requires an active organization and a configured source, uses deployment credentials,
and adds visibility without discovery, policy changes or a new initialization receipt.
A disabled source stays disabled. Repeating the command is safe.

### Source approval and discovery

Every source has exactly one `inventory`. `kind: discovered` reads the models from an
HTTP list endpoint. `kind: declared` is the platform's own list, for a source without a
usable list endpoint, such as a gateway. A declared list replaces discovery for its
source; it never supplements it. Both publish through the same refresh, and selection,
policy and admission do not know which one produced an offer.

The platform must review both destinations, the provider account/namespace,
visibility, actual credential scopes and egress/TLS policy together. Discovery
secrets use the existing `ENV_FILE`/process environment; inference credentials
remain pod-owned references and are never looked up by Rust. `mode: public` is an
explicit alternative, not a default. A credential that also permits inference
requires `authority: discovery_and_inference` **and**
`accept_inference_authority: true`; issuing a distinct key is not proof of scope.
HTTPS is required unless `allow_insecure_http: true` explicitly approves internal
HTTP. URLs with credentials, query parameters or fragments are refused. No URL is
derived from another and no Fred or pod token is implicitly reused.

Increase `revision` for every change, including rotation behind the same secret
reference. Apply the same configuration across replicas: older revisions and
different content at the same revision are rejected. A changed inventory kind, discovery
URL, inference root, wire or route, or visibility scope requires a new source ID. The platform
must declare account/namespace changes through `visibility_scope`; discovery cannot
verify them from a bearer token. Disable a source at a higher revision before
removing its configuration. Disabled SQL rows and offers remain for diagnostics.
Configuration changes invalidate in-flight refreshes and retain the last success;
the observation becomes `not_observed` at the new revision.

The single adapter requires HTTP 200 and `{ "data": [{ "id": "exact-id" }] }`.
IDs are unique, nonblank, without outer whitespace/control characters, at most
256 UTF-8 bytes, and are never normalized. Requests take at most five seconds,
read at most one MiB and never follow redirects. The only supported envelope keys
besides `data` are `object: "list"`, `complete: true`, and
`has_more`/`partial`/`truncated: false`. Unknown envelope fields, pagination links,
ranges, truncation and unsupported pagination markers cannot replace a snapshot.
Non-identity content encodings are refused. A 200 response alone does not prove
completeness: `complete_inventory_guaranteed: false` always yields `incomplete`.
Silent provider truncation remains undetectable; platform approval must establish
the full-list guarantee for that exact visibility scope.

`chat_source` establishes chat from the platform guarantee, so its source cannot
attest `embedding_models`: a mixed list is declared or uses
`mixed_capabilities_v1`, which reads boolean `capabilities.completion_chat` and
`capabilities.reasoning` from the discovery response.
Missing/invalid mixed-source metadata stays unknown, and `false` still retains
the inventory member. Metadata records chat provenance, optional `name` or
`display_name`, positive integer `context_length`/`max_model_len`/
`max_context_length`, `max_input_tokens` and `max_output_tokens`. Invalid optional
fields become unknown. Labels are bounded to 256 bytes, limits to positive i64;
these remain source-reported facts. Reasoning is `true`, `false`, or unknown; a
discovered source takes nothing from a declared list. No tools, reasoning, modalities or limits are
inferred from IDs; unsupported feature metadata remains unknown.

A declared inventory lists 1 to 256 `models`. `id` follows the discovery rule above and is
never normalized; `display_name` is at most 256 bytes; limits are strictly positive. This
is a platform statement, so an invalid value refuses the configuration instead of becoming
unknown. Chat is established by `source_guarantee`; `reasoning`, the label and the limits
are exactly what is declared, and an absent one stays unknown. A refresh uses no network
or secret, and the steps do not change: `not_observed` until a refresh, then published
offers, then an explicit organization permission. A declaration grants nothing, and pods
never receive the list. Changing it requires a higher `revision`, which returns the
observation to `not_observed`; the next refresh withdraws the models no longer declared.
As for discovered limits, the lowest known limit becomes the admitted token ceiling: a
`context_window_tokens` declared without `max_output_tokens` is sent as that ceiling.

Successful publication is atomic per source, including the observation and empty
inventories. Withdrawals retain the composite key, first/last-seen dates and last
metadata; reappearance restores that same row. Failures update only the attempt
state (`unavailable`, `invalid` or `incomplete`) and sanitized error code. They
preserve the last success and offers. Discovery creates no permission.
SQL refresh tokens implement last-started-wins across processes: an older attempt
cannot publish success or failure after a newer claim or configuration change.
Cancellation preserves the previous snapshot; the next explicit refresh needs no
lease recovery. The HTTP phase retains no SQL connection or transaction. Reads use
one consistent SQL snapshot and expose no URLs or credential references.

The following paths use the usual `/control-plane/v1` prefix. Every operation
requires `AdmittedUser`, active organization placement and `Manage`, with no
platform-role exception. Reads recheck admission and Manage after their consistent
SQL snapshot. No response schema includes destinations, credential references or
source approval configuration.

| Method/path | Contract |
| --- | --- |
| `GET /organizations/{organization_id}/models` | One repeatable-read snapshot of explicitly assigned sources (including disabled ones), observations, retained offers and only this organization's policy. `advertised`, chat qualification/provenance, discovery state/revisions and permission are separate facts. |
| `POST /organizations/{organization_id}/model-sources/{source_id}/refresh` | No body or destination override. Only an assigned, enabled source in this replica's approved configuration can be refreshed, and it must exactly match SQL. 204 on publication; 403 unassigned; 404 unknown; 409 disabled, obsolete or superseded; 502 invalid/incomplete discovery; 503 unavailable discovery. Failures retain the last success. |
| `GET /organizations/{organization_id}/model-policy` | Explicit permitted composite keys, optional default/fallback, revision and creation/update attribution. Absent policy is revision 0, empty set, null choices and null attribution. |
| `PUT /organizations/{organization_id}/model-policy` | Full replacement with `expected_revision`, `permitted`, `default` and `fallback`; all four fields required. Null clears each optional choice. 200 returns the saved policy; 409 on revision conflict or a newly selected unavailable offer; 422 on malformed policy, duplicates, unknown offers or choices outside the permitted set. |

PUT accepts at most 4096 distinct exact offer keys. Revision increments on every
successful write, including a no-op; callers must reload after a conflict. Default
and fallback must belong to the submitted permitted set, so revoking a selected
offer also requires explicitly clearing or replacing that choice. No default,
fallback, name-based match or permission is inferred.

Every submitted permission requires a source assignment. Only additions to `permitted` and changed non-null default/fallback selections
need fresh eligibility: known offer, enabled source, `state=ok`,
`snapshot_source_revision=source_revision`, advertised presence and `chat=true`.
The affected source/offer rows are share-locked until commit. Retained choices are
not revalidated as new selections: outage, changed configuration, unknown/non-chat
metadata and confirmed withdrawal remain diagnosable without blocking permission
reductions or explicit clearing. Refresh never rewrites policy; reappearance never
restores a revoked permission. Permission alone establishes no execution readiness.

Refresh checks admission/Manage before claiming a SQL token, commits, then performs
HTTP without a SQL connection. After HTTP it reacquires the existing platform and
organization locks, rechecks admission/placement/lifecycle/Manage and source assignment inside the same SQL transaction
before calling the publication store on that same transaction. Revocation refuses
publication of both successes and failures. Configuration equality and latest-token
checks still fence M1 publication; an unauthorized or cancelled attempt leaves its
token harmlessly supersedable by a later explicit refresh.

Tables `organization_model_policy` and `organization_model_permission` hold the policy. Composite offer foreign keys retain diagnostic
references; deferred membership foreign keys ensure atomic default/fallback
consistency. A trigger restricts the policy owner to an organization. Policy and
permissions cascade only on physical organization purge, not retirement or a user's
departure. Model policies remain organization scoped.

Initialize the complete schema before deploying this binary; startup checks
its fingerprint. Instance settings and resolver data are described below.

### Instance recommendations and resolver data (M3)

The existing space-scoped POST/PATCH and GET/list routes now accept/project
`recommended_model: {source_id, upstream_model_id}` and `model_options` in the
existing instance tuning JSON. There is no profile entity or new migration.
The owning organization comes from the authorized space, including personal spaces.
Creation and changed non-null recommendations reuse M2's `require_selectable`:
known, permitted, advertised, chat-qualified, enabled source and successful
observation at its current revision. The existing platform/organization lock
serializes policy changes; source/offer share locks keep the checked facts stable
until the instance write commits. SQL parameters never carry browser authority.

| Input | POST | PATCH |
| --- | --- | --- |
| `recommended_model` omitted/null | No recommendation | Omitted preserves; null clears |
| `recommended_model` key | Validate and save | Validate a changed key; an unchanged saved reference remains retained |
| `model_options` omitted/null | No overrides (`{}`) | Omitted preserves; null resets to `{}` |
| `model_options` object | Save explicit overrides | Replace the complete options object; omitted/null members remove their override |

Only `temperature` (finite number), `max_tokens` (positive integer) and `top_p`
(finite number in [0, 1]) are accepted. Booleans, numeric strings, fractional token
counts and unknown keys are rejected. An empty object supplies no values. There
are no invented provider defaults or source/template-option merges: resolver
options are precisely the saved instance overrides, shared across candidate offers.
No options alter identity or permission. Transport, endpoints, provider, credentials,
retries, timeouts and reasoning are not instance options.
When saving a changed recommendation or an options object, known output/context
limits bound `max_tokens` for the recommendation, otherwise the organization default.
Missing metadata adds no inferred capability. Prompt-dependent input/context budgets
and actual provider support still require pod validation. The resolver separately diagnoses
option incompatibility for every candidate, including a possible fallback.

Metadata-only edits, unchanged recommendations and explicit clears do not require
successful discovery. Revocation, withdrawal or outage never rewrite a saved key.

The existing authenticated `/spaces/{space_id}/agent-instances/{agent_instance_id}/runtime`
route adds `models` and `agent.configuration_updated_at`. One read-only repeatable-read
snapshot contains instance configuration, policy, source/offer observations and
approved connections. Admission, canonical space/template authorization and enabled
instance checks are retained; admission/space/template rights are checked again
before returning. No SQL transaction survives a provider call (there is no provider
call here); the additional authorization checks occur outside the read transaction.

Reasoning activation is an organization ceiling stored on the existing permission
rows (`reasoning_enabled`, initially false). Complete policy replacement
includes `reasoning_enabled`, a subset of permitted composite keys. Newly enabled
reasoning requires a selectable offer with source-reported `reasoning: true`;
revoking permission removes its reasoning activation too. The same Manage gate,
revision check and source/offer locks apply. No model-name inference is used.

Control Plane evaluates the requested `reasoning: true` with the selected model's
organization permission and known capability. The admitted options contain
`reasoning_effort: high` only when all three allow it; otherwise it is omitted.
Python and Rust consume those options unchanged. Known output/context ceilings
bound `max_tokens`, even when the instance did not set an explicit override.
Python's existing Mistral reasoning replay and transport guards remain active.

`models.policy` includes revision, permitted and reasoning-enabled keys and explicit default/fallback;
`recommendation` and `options` describe saved settings. `offers` is the union of
permitted keys and retained references.
Each entry separates `permitted`, `candidate`, `selectable`, typed diagnostics,
known metadata and source/snapshot revisions and dates. A candidate requires known
presence/chat, current source revision, enabled source, permission and compatible
known option limits. It does not prove pod support, credentials, connectivity or
upstream authorization. After discovery failure a retained candidate may remain;
`selectable` is false until a successful refresh at the current revision. Withdrawn, non-chat,
disabled, revoked, unknown and obsolete-source references are not candidates.

`model_catalog::instance::decide` is the single inference decision used by public
preparation, trusted Python delegation and internal Rust admission. Selection is
explicit choice, then instance recommendation, then organization default. A present
unknown/forbidden choice is refused without substitution. Fallback requires
confirmed withdrawal and stays
within the same source and its approved provisioning/account. A discovery outage
alone, disabled source, revoked permission or missing credential never triggers it.

The `/runtime` query accepts `model_source_id` and `model_upstream_id` together,
and `reasoning`. These are requests, never authority. A trusted workload with the
existing authenticated person/run/agent delegation receives `inference`:
`selection` (effective key, selection origin, effective options and policy/source/
snapshot revisions) plus `connection` (provider, API root, local credential-binding
reference). Person calls receive facts without any connection or binding reference.
The in-process Rust host uses an explicit private resolver path after authenticating
the person, without manufacturing an HTTP delegation. Browser preparation returns
only the safe `selection` as `inference`, or the common decision's `model_error`.
No token value crosses these APIs or enters SQL.

The surrounding `RuntimeBinding` supplies subject, space/organization, instance,
configuration revision and conversation attribution. Python pins it to `RunScope`;
Rust retains it through the turn's tracing context. Neither runtime refreshes
permissions between LLM calls. New admissions observe changes; admitted turns can
finish, subject to local cancellation/deadlines and upstream credential rejection.

### Inference connection

`inference` separates three questions, without any vendor branch in the runtimes:

| Field | Values | Question |
| --- | --- | --- |
| `wire` | `openai_chat`, `openai_responses` | Which protocol |
| `route`, `api_version` | `standard`, `azure_deployment`; optional version | Which address |
| `dialect` | `openai`, `openai_compatible`, `mistral` | Which provider quirks |
| `auth.kind` | `none`, `api_key`, `entra` | Which authentication |

`auth.tenant_id`, `auth.client_id` and `auth.scope` are required with `entra` and
forbidden otherwise. `auth.gateway_key_header` optionally names a gateway key header
with any kind, except `Authorization`, `Host`, `Cookie`, `Content-*` and
`Transfer-Encoding`. `api_root` is canonical: nothing a parser would normalize, no
credentials, query, fragment, final `/`, percent-encoding, dot segment or IPv6 literal.
`entra` requires HTTPS; other kinds also accept HTTP under `allow_insecure_http`.

One connection reaches exactly one URL for a given model:

| Route and wire | URL |
| --- | --- |
| `standard`, `openai_chat` | `{api_root}/chat/completions` |
| `standard`, `openai_responses` | `{api_root}/responses` |
| `azure_deployment`, `openai_chat` (requires `api_version`) | `{api_root}/deployments/{model}/chat/completions` |

`?api-version={api_version}` is added when the version is present. A deployment route
limits the model identifier to `[A-Za-z0-9._-]+`, without `.` or `..`.

`dialect` never changes the URL. It decides what Chat Completions sends:

| `dialect` | For | Token ceiling | `stream_options` |
| --- | --- | --- | --- |
| `openai` | OpenAI and Azure OpenAI only | `max_completion_tokens` in Python, `max_tokens` in Ralph | Sent |
| `openai_compatible` | Other servers reading the ceiling only from `max_tokens` | `max_tokens` | Sent |
| `mistral` | Mistral, directly or behind a gateway | `max_tokens` | Not sent; Python replays reasoning |

`openai_responses` always sends `max_output_tokens`, whatever the dialect.

Python never ignores an admitted setting without saying so. LangChain removes the
temperature of some models, at construction or from the Responses payload; the factory
compares the payload the client would send and refuses the model with a fixed message,
before any request, instead of leaving the guard to report a lost authority.

Connection examples, all implemented and tested on a simulated transport only; none
was received on a real gateway, Ollama server or Entra tenant. Discovery knows neither
Entra nor a gateway key, so such a source publishes its offers through a declared
inventory:

```yaml
# Mistral
inference:
  credential_binding: mistral
  api_root: https://api.mistral.ai/v1
  wire: openai_chat
  route: standard
  dialect: mistral
  auth: {kind: api_key}
---
# Ollama (with allow_insecure_http on its source)
inference:
  credential_binding: ollama
  api_root: http://ollama:11434/v1
  wire: openai_chat
  route: standard
  dialect: openai_compatible
  auth: {kind: none}
---
# Azure API Management, chat completions by deployment
inference:
  credential_binding: apim-gpt4o
  api_root: https://gateway.example.invalid/genai-aoai-inference/v2
  wire: openai_chat
  route: azure_deployment
  api_version: "2024-06-01"
  dialect: openai
  auth:
    kind: entra
    tenant_id: example-tenant
    client_id: example-client
    scope: api://example-gateway/.default
    gateway_key_header: Example-Subscription-Key
---
# Azure API Management, Responses: same authentication, `api_root` ending in /v1
inference:
  credential_binding: apim-responses
  api_root: https://gateway.example.invalid/ai-models/v1
  wire: openai_responses
  route: standard
  api_version: preview
  dialect: openai
  auth:
    kind: entra
    tenant_id: example-tenant
    client_id: example-client
    scope: api://example-gateway/.default
    gateway_key_header: Example-Subscription-Key
---
# Gateway subscription key alone
inference:
  credential_binding: apim-key
  api_root: https://gateway.example.invalid/genai-aoai-inference/v2
  wire: openai_chat
  route: azure_deployment
  api_version: "2024-06-01"
  dialect: openai
  auth:
    kind: none
    gateway_key_header: Example-Subscription-Key
```

### Workload provisioning and rotation

Python uses top-level `inference_credentials` in `AgentPodConfig`; the embedded
Rust workload uses `platform.inference_credentials` in Control Plane configuration.
An entry carries only what protects the secrets, by variable name. It is required
even with `auth.kind: none`, to attest the destination; `credential_binding` is its
unique key.

```yaml
inference_credentials:
  - credential_binding: apim-gpt4o
    api_root: https://gateway.example.invalid/genai-aoai-inference/v2
    client_secret_env: EXAMPLE_ENTRA_CLIENT_SECRET
    gateway_key_env: EXAMPLE_GATEWAY_KEY
```

Before reading any variable, Python checks `credential_binding` and `api_root`, then
that the variables present exactly match `auth`: `api_key_env` with `api_key`,
`client_secret_env` with `entra`, `gateway_key_env` with `gateway_key_header`, and
nothing else. Embedded Ralph accepts `api_key_env` only, and only connections with
`openai_chat`, `standard`, `api_key`, no `api_version` and no `gateway_key_header`;
it refuses any other. It selects its Rig dialect from `dialect`, never from the host.
Missing, duplicate, incomplete or inconsistent provisioning fails closed, with no HTTP
inference request and no global-key/Swift fallback. A variable name is an explicit
mapping, not a default. Kubernetes Secrets/environment still provision the value;
no secret manager or API distribution was added.

An Entra client secret serves one `ClientSecretCredential` per binding, tenant and
client, on the public Azure authority, which is not configurable. Its tokens are
accepted only by the model that obtained them. A gateway key is added by the transport
guard after all its checks and stays off the model and the SDK client.

For rotation, prepare the new Secret, increase the Control Plane source revision,
refresh the source at that revision, and roll the consuming workloads. The binding
carries no revision: `selection.source_revision` remains for audit, and Control Plane
keeps blocking a source that has not been observed at its current revision. Deployment
ordering must prevent mismatched connections from admitting work; mismatches fail closed
while the rollout converges. Environment variables are process snapshots and are
not automatically reloaded. Drain admitted turns before retiring the old credential
if continuity matters; the provider may reject an already-admitted revoked key.
An account/namespace/payer change requires a new source identity, not a fallback.

Targeted tests use shared fixtures in `libs/fred-sdk/tests/fixtures/`
(`inference_admission.json`, `inference_connections.json`), real ChatOpenAI and Rig
adapters with simulated providers, and disposable SQL for host admission. These
checks do not establish k3d, provider or selector availability for Ralph.


## Automatic conversation titles

Newly registered conversations keep their initial title until one cosmetic title
attempt succeeds. Migration `0004_conversation_titles.sql` leaves every existing
session ineligible; it does not rewrite titles or histories. Registration replays
retain the original row and its eligibility. Run `control-plane init-schema` before
starting this version, using the normal schema-owner deployment procedure.

An organization **Owner** can optionally select a title model in its existing
Models settings. The choice is a pair `(source_id, upstream_model_id)` in the same
organization's permitted offers. It is persisted with the revisioned model policy,
whose complete replacement now requires `title` (use `null` for no dedicated
choice). Inventory `selectable` and write validation use the same calculation.
There is no platform-wide override, additional role or per-pod title setting.

With no dedicated choice, title inference uses the offer admitted for the answer,
with separate bounded settings: at most 128 output tokens (capped by known model
limits), no reasoning, no inherited answer temperature/top-p. With a dedicated
choice, an unusable offer leaves the initial title; it never falls back to another
organization's model or bypasses permission. Workload credentials for that source
must already be provisioned by the existing inference contract. Unchanged choices
can remain visible when unavailable, but newly selected offers must be selectable.

The read-only `GET .../agent-instances/{id}/runtime` never reserves a title.
Execution uses workload-delegated `POST` on the same path; the embedded Rust host
uses its private equivalent. After normal admission and association checks, an
atomic session update consumes `title_pending` and returns a unique attempt only
to one execution. A first resume or unavailable title model also consumes the
opportunity. Failures and retries do not schedule later attempts. No transaction
spans a provider call, and no extra queue or service is involved.

`POST /spaces/{space}/sessions/{session}/generated-title` is workload-only. Its
conditional write checks admitted subject, space, instance, session, attempt and
absence of deletion. Any manual non-null `PATCH` title clears the attempt, even
when its text equals the initial title; an activity-only patch does not. A late
result then receives 409 without changing the row. Deleted sessions are never
recreated. Successful persistence emits `session_title` with the original session
ID so the browser reloads canonical metadata instead of applying a stale string.

Python managed agent turns and embedded Rust Ralph implement the same envelope:
first 600 input characters, a prompt for 3–8 words in the input language, plain
text bounded to 80 characters, 10-second generation budget and at most 2 seconds
of grace before the final answer event. Closing/cancelling the stream cancels the
title work; failure or invalid output leaves the answer intact. The title is not
an assistant message. Existing inference observation and usage reporting count
consumption under its actual offer, including output rejected as an invalid title.
A provider's unreturned usage cannot be inferred after cancellation.

These contracts are covered by focused simulated-provider, SQL and UI
component tests. They do not certify a local k3d or integration-platform journey.
Deploy Control Plane, SDK/runtime and frontend coherently; see the
[operator note](../../deploy/release-notes/changes/weaver-conversation-titles.md).

## Conversation metadata and browser preparation (M5a)

These backend APIs and generated clients back managed chat. Focused tests do not
establish a k3d/integration-validated journey. Paths below are relative to the CP prefix.

| Method / path | Behavior |
| --- | --- |
| `POST /spaces/{space_id}/sessions` | Register `{session_id, agent_instance_id, title?}`; 201 new, 200 identical association replay. The frontend ID is retained. |
| `GET /spaces/{space_id}/sessions` | Only the authenticated owner's conversations, ordered by `updated_at DESC, session_id`. |
| `GET /spaces/{space_id}/sessions/{session_id}` | Private metadata, retained instance/template/runtime IDs, current or registration-snapshot agent name, deletion/disabled flags, nullable public `messages_url`. |
| `PATCH /spaces/{space_id}/sessions/{session_id}` | Only `title` and/or `updated_at`; omitted/null values are unchanged. Empty title clears; activity is monotonic and capped at server time. |
| `DELETE /spaces/{space_id}/sessions/{session_id}` | Retire the owned session immediately and create its retained deletion receipt. Effective erasure follows the lifecycle policy. |
| `POST /spaces/{space_id}/agent-instances/{agent_instance_id}/prepare-execution?session_id=...` | Admission, space Read, template Use, instance/source state and optional private association checks; public runtime/history routes and browser-safe model facts. |

Admission and current space Read apply to all operations. Session ownership is
always the authenticated subject; space membership, Write/Manage and platform roles
grant no access to another person's sessions. A foreign/unknown session is 404;
an owned incompatible association is 409 `session_association_mismatch`.
Unknown mutation fields are rejected with 422. Registration replay returns the
original row without overwriting title/activity, even when its instance is now
missing or disabled. New registration requires an executable saved association.
Title/activity edits and history metadata reads do not require template Use.

Table `session_metadata` is a private index, distinct from
shared instances; it contains no messages or checkpoints.
Its immutable identity columns deliberately have no cascading foreign keys:
the worker removes this index only when its runtime storage can be erased safely.
The embedded log and migrated Python content cascade from the same physical
session deletion. Runtime roles receive only schema USAGE and column REFERENCES
on this root, not access to Control Plane rows. Retained deletion receipts forbid
reusing a purged session UUID.
Missing/retired space authorization still prevents reading that index; retired
sessions are hidden from metadata and history reads during retention.
Agent names fall back to the registration snapshot after
instance deletion; registration is not a name-synchronization mechanism.

For each external `platform.runtime_catalog_sources` entry, `base_url` remains the
internal discovery endpoint. Optional `public_base_url` is an independently
approved same-origin ingress path, e.g. `/fred/agents/v2`. It must have canonical
nonempty path segments (ASCII letters/digits and `-_.~`, no `.`/`..`, trailing
slash, encoded characters, authority, query or fragment). No route is inferred.
Missing/disabled sources return `messages_url=null`; an instance's deletion or
disabling does not itself remove history routing. Reusing a runtime ID for another
history store is not a supported migration.
Embedded Ralph instead uses the Control Plane's configured mount for its history
URL, without an external runtime source. Unknown, foreign and retired sessions
return the same 404; an authorized conversation with no completed turn returns `[]`.

Team Owners can read/replace `/spaces/{id}/conversation-retention` without content
Read. `configured_seconds: null` inherits the team's existing lifecycle retention;
zero makes purge immediately eligible, positive integers choose a duration. The
response includes inherited, configured, organization ceiling and effective seconds.
The existing policy catalog accepts optional `conversation_retention_ceiling` in
purge defaults/rule actions, resolved against the organization; configuration owns
this ceiling, with no organization UI added. Absent a ceiling or team setting,
existing deadlines are unchanged. The effective team conversation delay is bounded
by that ceiling; writes above it are refused. Project/personal conversations,
documents and space deletions retain their existing policy. Settings and deletion
admission use the same organization guard: only newly accepted deletions snapshot
the current delay; existing receipts are never rescheduled. There is no inactivity
expiry or restoration. These component contracts do not certify browser acceptance.

The lifecycle worker removes attachments before conversation storage. Ralph's log
is removed with its session row; its foreign key prevents a late admitted turn
from recreating it after purge. The usage journal is retained. One audit helper
records session acceptance and completion with runtime and retention provenance.

Python cleanup now closes its existing conversation filesystem through the private
runtime source and the Control Plane's existing M2M token. A positive response
must certify both filesystem erasure and the validated SQL cascade schema; the
former history-only DELETE response is rejected. The runtime owns its history,
steering, checkpoint/blob/write/HITL tables and writable-document content. Their
foreign keys arbitrate concurrent commits and final erasure across replicas.
The worker neither reads these private tables nor enumerates them.

Object originals, derived artifacts, vectors, scratchpad/Deep files and generated
exports retain durable manifests until physical cleanup is confirmed. Pending
writes never expire merely because a lease ended. A lost result remains explicitly
blocked; a late successful acknowledgement permits the next sweep to continue.
`completed` is recorded atomically with root deletion and the SQL cascade. Existing
blocked receipts are selected again automatically, without SQL edits. The receipt
keeps immutable attribution for late consumption reports after session/space/agent
metadata deletion; usage itself is never cascaded. Delivery remains the existing
best-effort reporting path, not a new accounting outbox.

The workload exception for `manage_platform` is limited to the verified service
account of the configured CP M2M client and issuer, with no person/run/agent
assertion. It grants no permission to users, other workloads, or delegated users.
This is an identity-level `manage_platform` authorization decision, not a new
purge-specific permission: any consumer of that existing decision retains its own
authentication guards. It does not grant other platform permissions or bypass
Control Plane business-route authorization. The runtime checks that decision on
its purge route. Unavailable identity,
runtime or storage services do not authorize completion.

See the [Python erasure rollout note](../../deploy/release-notes/changes/weaver-python-conversation-erasure.md)
for mandatory migration ordering, storage constraints and validation limits.

Retiring an organization or team also hides its conversations through the space
access check. After retention, the worker selects one remaining space and creates
at most 100 child session receipts per visit, preserving the parent's original request, deadline, actor
and rule; already retired sessions keep their own receipt and deadline. These
child acceptance audit events are emitted when the worker creates the receipts.
The parent waits for every conversation to disappear before removing its spaces.
An incomplete child keeps the parent pending. Ordinary space documents and
pending uploads outside conversations retain the existing deletion restriction.
Conversation uploads and attachments use the existing document cleanup before
their session can be removed, including an upload already admitted at retirement.
The partial retirement index excludes sessions that already have receipts, so
blocked children do not accumulate in the queue being materialized. Each space
can require additional sweeps; the batch bound is not a completion-time guarantee.

Preparation uses the existing bounded, nonredirecting template discovery, outside
SQL. Unavailable discovery is 503, denied discovery is 403, absent template is 409.
Missing public routing is 409 `agent_public_route_unavailable`; disabled instance
is 409 `agent_instance_disabled`; unavailable runtime is 409
`agent_runtime_unavailable`. No-tool react/graph families expose the existing SSE
and UI-part transport and the advertised input limit; HITL is false and
a `reasoning_toggle` only when at least one candidate model has reasoning enabled.
The existing composer offers it only for the selected enabled model, initially off.
Active capabilities return 422, other execution families 409.
No unsupported control is replaced with a default or hidden tool selection.

`models` projects the common catalog facts: recommendation, default/fallback, options,
composite offers with permission/candidate/selectable and effective
reasoning-enabled facts, metadata and diagnostics. The DTO has no inference URL, connection or credential
binding. Its `inference` selection comes from the common decision, without certifying
provider connectivity. A preparation is `Cache-Control: no-store` product data, never a grant or a replacement for M4.
Session responses are also no-store.

The existing `/runtime?conversation=...` checks the registered owner/space/instance/
runtime/template association inside its single admission request. Python then
checks its immutable checkpoint provenance against those canonical identifiers;
old histories without provenance still fail. No additional resolution or authority
read is added to model calls, retries or descendants. Revocation remains next-turn.
The pod's direct history GET currently checks ownership only: its current Weaver
space/admission check is a prerequisite of the later chat cutover, independent of
executable-instance state. This increment does not claim that read gate is wired.

Authorization reads the PostgreSQL role tables and immutable space placement. Mutations
check permission under the same platform/organization locks and SQL transaction as
their writes. Discovery, inference and streaming stay outside SQL transactions.

`POST /authorize/scope` returns the requested `space_id` anchor and the exact readable
`space_ids` subset of its ancestor path. Managed runtime admission uses the same
permission primitives to return `authorized_space_ids` in its binding; the Agent Pod
relays that fixed corpus to Knowledge Flow for all document access within the turn.
Decision endpoints accept authenticated people or trusted person/run/agent delegation,
evaluate the person's admission and rights, and return `Cache-Control: no-store`.


## Conversation file catalogue

Conversation deliverables share the `document` catalogue with source documents.
`document` owns placement and the stable file identity; `document_content` owns
immutable object keys, hashes and sizes. `document_current` projects the current
primary content for existing readers. Content bytes remain immutable and only
sources can enter Knowledge Flow processing. A preview references its exact primary
content and disappears from current reads as soon as that primary is replaced.

Source processing freezes `content_id`, `expected_content_id` and the nullable
`expected_generation_id`; callbacks read those exact bytes and publication swaps
content and generation together. Migration `0036_document_processing_content.sql`
prepares replacement/reprocessing persistence and quota handling, but public
processing admission still refuses a previous success. See the
[storage/processing contract](../../docs/architecture/A9-documents.md#processing-behavior)
for that boundary; it does not change conversation deliverable replacement.

The conversation owner lists and downloads deliverables through
`/spaces/{space}/sessions/{session}/files`. Listing, download, `write-target` and multipart write
routes accept the existing trusted person/run/agent assertion and verify the live
conversation association without readmitting the turn. Browser reads retain owner
admission and consent checks. Content downloads include `X-Content-Id`, selected
with the immutable object key in one SQL row. A replacement based on read bytes
submits that returned identity as `expected_content_id`; it must not refresh the
snapshot at submission time. PowerPoint rendering can still capture
`current_content_id` through `write-target` before it starts.
A conflict requires reading the current target again; it never overwrites silently.
The idempotency key binds destination, content and expected revision. File links
identify the current saved file, not a historical message snapshot.
Browser links use origin-relative `/control-plane/v1` URLs, independently of the
pod's internal Control Plane address. The workspace port accepts a retained UUID
`request_key` for an identical replay and retries a transport failure once with
the same key and payload. Business conflicts and terminal failures are not retried.

Writes reuse the bounded original transfer, checksum verification and
`document_upload` journal. The organization advisory guard is shared for deliverables
and exclusive for governance. A short conversation lock coordinates its inventory;
file publication and budget deltas are transactional. Organization-total then local
budget rows arbitrate concurrent reservations across replicas. Bulk document updates
aggregate quota deltas per account, so retirement does not rewrite the same counter
for every file. Transfers never hold
a SQL transaction. `storage_budget` counts current primary bytes and positive pending
growth, including configuration PowerPoint files. Defaults are provisioned on first
write; the optional `organization_total_bytes` ceiling has no limit by default.
Previews are physical content inventory, separate from user quota. Superseded content
enters an indexed cleanup queue; uncertain PUTs remain fenced. Technical receipts
expire only after physical cleanup and the configured receipt retention period.

Source and output inventories each use `conversation_files` and `conversation_bytes`;
all transfers use the configured file ceiling, at most 100 MiB. The current API
returns at most 10,000 deliverables (`limit` and `offset` are bounded), with
downloads bounded by the shared content transfer slots. The common Python port
lists up to 100 entries per call and bounds streamed reads to the caller's limit,
at most 32 MiB. SQL counters and these bounds are not a production capacity test.
Deep's scratchpad and wiki domain revisions retain their existing owners; this port
does not implicitly ingest files, publish to a team, or implement wiki revision semantics.

## Background tasks

`control-plane serve` supervises HTTP, storage cleanup, the processing dispatcher
and configured lifecycle tasks in one process. Lifecycle is disabled by default.
See [activation and policy configuration](../../docs/architecture/A3-manager-operations.md#space-deletion-lifecycle).

## Changing it

A change described in the dossier updates its chapter in the same commit. A test that
proves an invariant carries `// Proves: I<n>` above it. Keep pushed SQLx migrations
immutable; add a numbered transaction, preserving constraints, indexes and reader
grants. Weaver currently supports fresh installations only (see
[AGENTS.md](../../AGENTS.md)): test fresh initialization, not upgrades. Never rewrite
live checksums (see [Existing local state](#existing-local-state)).

## Generate the frontend contract

```sh
make generate-openapi                       # writes ignored openapi.json
make -C ../frontend update-control-plane-api  # regenerates schema, RTK endpoints and types
```

Generation runs without configuration, credentials or services. The frontend's
`update-all-apis` includes control-plane. Commit the regenerated
`src/slices/controlPlane/controlPlaneOpenApi.ts` with changes to routes or DTOs;
never edit it by hand. The slice uses the shared bearer/refresh base query and
Redux store. Its enhancement encodes the generated import argument as multipart
FormData, retaining the generated URL, method and completed-report type.
Bootstrap and import never retry automatically on 401; expiry can follow committed effects.
Frontend consumers use `controlPlaneApiEnhancements`. Background tasks establish
their Temporal connections independently of HTTP serving.

## Platform and space roles

`GET /me` reports effective platform roles. Platform admins list direct grants
with `GET /users/platform-roles`, and grant/revoke with
`PUT`/`DELETE /users/{subject}/platform-roles/{role}`. Any platform admin names or
removes other owners; the last one cannot be revoked. `platform_observer`,
`feature_manager` and `prompt_editor` are also supported.

Admin is technical: `platform_admin` governs the platform and
`organization_admin` appoints its organization's business owners. Neither role
reads content. `owner` is the business governance role (French: **Responsable**).
Space roles `member`, `editor`, `analyst` and `owner` are business roles. They are
cumulative and apply only to the space where they are granted; no role reaches a
child space. Owner alone does not read content. A personal space inherits nothing.
Personal spaces have `kind: personal`, an organization attachment and an owner,
but no parent or child projects. `team` denotes collective teams only, including
in scope filters and lifecycle policy selectors; use `[team, personal]` explicitly
when both kinds are intended. Personal creation keeps its dedicated endpoint. Opening, listing and new Control
Plane access require a business role (`owner`, `member`, `editor` or `analyst`)
on an active organization, team or project. Technical admin alone is insufficient;
mixed admin/business roles qualify. The demo creates no personal spaces.
Organization owners create teams, team owners create projects. The last owner of a
non-personal space, and the last technical admin of an organization, cannot be revoked. Capability checks and their contracts are in the
[runtime chapter](../../docs/architecture/A1-manager-runtime.md#platform-administration-and-self-checks).

Organizations are created through the platform form (`POST /control-plane/v1/admin/organizations`)
or a provisioning ZIP. Without the frontend, use the authenticated HTTP endpoint or
`make import-provisioning BUNDLE=<zip> TOKEN_FILE=<bearer-file>` on an initialized
installation. Both paths require a platform admin; creation does not restore a lost
platform-admin role.

Platform grants and organization-admin grants require the manager's service client. The factory
provisions the `control-plane` client and its directory grants. The cluster uses
`KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET` from `fred-secrets`. To reuse that identity
on the host, set `security.m2m.client_id` to `control-plane`, set its
`secret_env_var` to `KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET`, and supply that secret
in the host `.env`.
The [deployment chapter](../../docs/architecture/A3-manager-operations.md) describes configuration.

## Import a provisioning bundle

Build the checked-in demo from the repository root or `apps/control-plane`,
without running services:

```sh
make bundle-demo
# Optional overrides (absolute paths work from either directory):
make bundle-demo DEMO_PROVISIONING_FIXTURE_DIR="/path/to/fixtures" DEMO_BUNDLE_FILE="/path/to/demo.zip"
```

The default output is `apps/control-plane/target/demo-provisioning-bundle.zip`
(path from the repository root). Both entry points delegate to the same packager.

The ZIP contains exactly `manifest.json`, `users.json`, `organizations.json`,
`teams.json` and `projects.json`, plus optional `skills.json` and `prompts.json`. The manifest
declares `format_version: 2`, `users_schema_version: 2`, `source_platform: "swift"`.
The data files are arrays. A `skills.json` entry is
`{"space": "<declared ref>", "name": "<skill>", "files": {"SKILL.md": "...", "references/x.md": "..."}}`:
its package must satisfy the [space skills](#space-skills) contract, once per space
and name. A Control Plane without this support rejects the file as `not_yet_supported`.
The packager builds it from an optional `skill_packs.json` in the fixture directory,
`[{"space": "<ref>", "pack": "<directory relative to the fixture>", "skills": ["<name>"]}]`;
the demo installs `en` in Acme and `fr` in Globex.

`prompts.json` entries use `{"space": "<ref>", "category": "<name>", "prompt": {...}}`.
The nested `prompt` follows `CreatePromptRequest` (logical name, display name,
description, text and optional tags); `category_id` must be omitted or null.
Categories are resolved by name in the destination space. The packager reads
`prompt_packs.json` with the same `space` and `pack` fields and a `prompts` list;
each name selects `<pack>/<name>.json`. The demo installs the four French Swift
starter prompts and their categories in both organizations from `prompt-packs/fr`.
The texts are copied unchanged from Swift `a773325202ee6ea55d9b19824884b68b0dfd66f3`,
`apps/control-plane-backend/control_plane_backend/product/prompt_starter_kit.py`.
They are bundle data, never seeded by the binary or ordinary space creation.

The demo's people, spaces and roles are listed once in
[Example people and spaces](../../docs/architecture/02-journeys.md#example-people-and-spaces);
the [fixture README](tests/fixtures/import_export/demo_provisioning/README.md) gives
its counts and test password. `make bundle-demo` is the only demo build target.
The [declaration contract](../../docs/architecture/A2-manager-contracts.md#provisioning-declarations)
defines explicit parent references and roles, including projects. Old JSON and
Python version-1 ZIPs return `not_yet_supported`; no conversion is performed.

After compatible initialization, root bootstrap and personal CGU acceptance, save a platform admin's
access token in a private file and run:

```sh
make import-provisioning BUNDLE=target/demo-provisioning-bundle.zip TOKEN_FILE=/path/to/operator-token
# Equivalent binary command:
control-plane import-provisioning /path/to/bundle.zip --token-file /path/to/operator-token
```

The CLI uses the normal configuration and the manager's Keycloak service client.
It needs neither the running HTTP server nor Temporal and never initializes or
migrates SQL. The HTTP equivalent is multipart
`POST /control-plane/v1/import-export/import`, with exactly one field named `file`
and the operator bearer. It checks platform administration before reading the upload.
A new organization declares at least one owner and one admin. Archive limits are 50 MiB compressed and
100 MiB expanded, with no filesystem extraction.

Existing identities keep their profile and password; new identities need a
nonempty password. Usernames must already be lowercase, without surrounding
whitespace or control characters. Noncanonical names and known new-user email
conflicts are rejected before any provisioning writes. All space roles are explicit: admin alone grants no content
access, and every child-role holder needs a direct parent content role. Replay
preserves committed space IDs and undeclared grants and repairs requested grants.
Declared skills are installed in the same transaction as the spaces; replay reports
present ones as kept (`skills_kept`) and never rewrites them. Prompts follow the
same rule, matched by space and immutable logical name (`prompts_created` and
`prompts_kept`). Existing prompts retain all fields, authorship and timestamps,
including category edits. Categories are created only for missing prompts, so
replay does not undo a rename or recreate a removed category for a kept prompt.
A deleted prompt is absent and is installed again by a subsequent import.
Success returns JSON counts only after completion. A failed run reports a safe
phase and acknowledgment counts; correct the cause and replay with a valid token.
There is no cross-system rollback, so failure does not prove absence of effects.

`make test-integration` imports the actual Make artifact over HTTP with disposable
Keycloak, PostgreSQL, verifies replay and identity preservation, and
imports a variant with a project.

### Nova coexistence bundle

For the separate Swift/Weaver exercise, run `make bundle-migration` from the
repository root or this directory. It generates
`apps/control-plane/target/nova-migration-bundle.zip` (path from the repository root)
without contacting any service. It contains only Nova, its Pilote team and three
accounts, with no project or platform grant. `nova.admin` is Nova's technical
administrator; `nova.responsable` owns Nova and Pilote and explicitly holds
`member` on Nova, as required for a team role. `nova.editeur` holds `member` on
Nova and `editor` on Pilote, allowing the document exercise while the responsible
person retains governance only on Pilote.

Follow the [Nova fixture and Chrome walkthrough](tests/fixtures/import_export/nova_migration/README.md)
for credentials, shared-SSO collision checks and the manual import steps. This
is fresh provisioning in Weaver, not a transfer of Swift data. The browser
journey remains an operator validation step.

## Import through the frontend

Fred's existing administration console exposes **Provisioning** at
`/admin/provisioning` to manager platform admins. Select the ZIP produced by `make bundle-demo` or `make bundle-migration`.
The page displays the completed server counts or an error with explicit replay
guidance. The existing Home and sidebar display own memberships, hierarchy and roles.
The account menu permits logout before and after admission. Platform admins are restricted to governance/account routes. Business users retain
the existing product UI; endpoints not yet reconstructed can fail.

From `apps/frontend`, automate this journey without touching development data:

```sh
make install-test-browser       # once: Chromium, after installing Node dependencies
make test-provisioning-browser
```

The test needs Docker, Node/npm and the Rust/protoc prerequisites above. It starts
throwaway PostgreSQL and Keycloak plus the real manager governance router
and Vite frontend, then removes its services. Starting with no root or consent,
it bootstraps through the UI, accepts CGU, imports the actual Make ZIP, replays it,
imports a project variant, then switches accounts in the same browser. It checks
consent isolation, empty root memberships, persisted hierarchy/roles, reports,
refusals, unsupported direct URLs and keyboard logout through the existing account
menu. Control Plane is real; unavailable Knowledge Flow and external runtime
requests receive explicit failures. Screenshots are
written under the frontend's ignored `target/` directory. The manager's
`make test-browser` invokes the same journey and integration suite when frontend
dependencies and Chromium are already installed.

From `apps/control-plane`, `make test-prompts-browser` reuses this fixture for prompt management in four spaces,
home search, the prompt self-test launcher, composer insertion and role isolation.
Prompt and authorization HTTP responses are real; no model generation is exercised.
It writes screenshots and `prompts-browser-progress.log` under the same ignored
frontend `target/` directory.

## Existing local state

The architecture dossier contains the [SQL table catalogue](../../docs/architecture/A2-manager-contracts.md#control-plane-sql-catalogue)
and [SQLx operations](../../docs/architecture/A3-manager-operations.md#sqlx-schema-initialization).

`migrations/0001_schema.sql` creates the baseline tables; `0002_cp_read.sql` creates
the consumer views and grants. `0003_cp_read_document_tree.sql` appends display
columns to three views without replacing their grants or changing stored data.
All pushed migration files are immutable. SQLx records their fingerprints in
`control_plane._sqlx_migrations`, serializes initialization and runs each migration
transactionally. `control-plane initialize-schema` creates a fresh schema or applies
pending migrations from a matching history. Repeating it preserves data. API startup
only verifies the complete fingerprint and does not apply migrations.

The k3d profile enables the pre-install/pre-upgrade `control-plane-backend-schema-init`
Job through the shared chart's `migration` settings. Weaver currently supports fresh
installations only: changed, missing or incomplete migration history is refused without
resetting data or rewriting checksums, and an incompatible local database is recreated.
Initialization has a five-second lock timeout: a busy database fails the hook safely
and can be retried after the blocker ends. Python runtimes retain their Alembic histories.

Role mutations, initial space grants and bootstrap commit atomically in PostgreSQL.
The service and binary are named `control-plane`; the image remains
`control-plane-backend` and the lifecycle queue/prefix is `control-plane-lifecycle`.

The frontend's `controlPlane` client targets this Rust API. `legacyControlPlane`
retains the previous API types and clients for screens not yet migrated; the
Python backend is no longer shipped.

### Email facts in document previews

The existing preview endpoint serves the published generation's `metadata.json`
with the same document read checks as its Markdown. The API schema describes the
subset used by the viewer; other metadata extensions retain their existing
contracts. Email facts are bounded and validated before final publication, outside
SQL locks, alongside the existing immutable-byte/hash and identity checks.
Publication never derives identity, uniqueness or access from an email address or
message reference. No SQL migration or catalog filter is introduced.

A conversation attachment requires `session_id` on the preview request. Control
Plane verifies the document's actual association, current space read access and
ownership of that live conversation. Without this context the drive route still
excludes attachments. The email preview in the existing conversation attachment
panel supplies it; this does not make an attachment a shared library document.
Metadata and text modes each read one published artifact, without combining fields
from different generations in one view. Missing metadata on older documents has
an explicit empty state. See the [operator note](../../deploy/release-notes/changes/weaver-email-metadata.md).

### Document search inclusion

`Document.retrievable` is the last confirmed inclusion state, separate from processing
success and caller permissions. Publication reads and verifies `metadata.json` before
persisting it in the same transaction that sets `document.published_generation`. The vector worker checks
the flag on written chunks. Existing listing and content permissions are unchanged.

`PUT /documents/{id}/retrievable` with `{"retrievable": false}` or `true` requires the
existing space write permission and a published vector generation. KF updates only
its published chunk IDs and reads them back before confirming SQL. The response is
200 only after confirmation. `retrievable_pending` drives the existing UI refresh;
503 means the outcome is not confirmed, not that the operation was rolled back.
A request matching the recorded state, whether set by publication or by a confirmed
command, returns it without delivery or mutation. While pending, the same actor can
repeat the same request; an opposite request is rejected. `null` is rejected. The
command and its phase live in the `document.retrieval_*` columns:

- `ready`: the worker must atomically claim `writing` before touching OpenSearch.
  Only one claim succeeds, including after an API restart or Temporal history expiry.
- `writing`: the mutation activity has one attempt. Its timeout, termination or
  partial failure never authorizes another writer. A lost claim response also stays
  protected, even if no write actually began.
- `applied`: a separate activity records successful writer completion. That callback
  retries independently, without an overall workflow deadline, so a temporary SQL/HTTP
  outage does not discard Temporal's evidence that the writer returned. Verification
  and confirmation then run in a separate activity (up to five attempts per run).
- `confirmed=true`: SQL contains the verified value; duplicate confirmations are
  idempotent. Every callback is fenced by the current operation ID.

Delivery uses `ALLOW_DUPLICATE_FAILED_ONLY`, with `FAIL` on a running ID and a fresh
start-request ID. A failed, timed-out, cancelled or terminated run may restart; it
reads the persisted phase and never repeats a claimed mutation. `AlreadyExists` is
described and accepted only for a running execution, not a closed failure. A completed
run is not restarted. These policies follow the
[Temporal workflow identity contract](https://docs.temporal.io/workflow-execution/workflowid-runid).

For diagnosis, use the authenticated internal GET
`/document-processing/retrievable/{id}?operation_id={operation_id}` and the matching
`manager-retrievable-{installation}-{operation_id}` Temporal history. If the phase is
`applied`, repeat the original PUT to retry verification/confirmation. If it is
`writing`, inspect whether the completion-recording activity is still retrying; it
can finish without reapplying the mutation. A closed run with `writing` or a partial
projection requires investigation of the activity and remote write. There is **no automatic repair or operator reset
endpoint** for that case. Keep pending, do not clear the command or submit the opposite
value; any repair must first establish that the old writer and remote operations
have stopped and be separately scoped. A read matching the target alone is not proof
that an uncertain writer has stopped.

OpenSearch verifies exactly the IDs derived from `manifest.vector_ordinals` with
sequential `_mget` batches of at most 500. Only `metadata.document_uid` and
`metadata.retrievable` are requested. Missing/duplicate/unexpected IDs, per-item errors,
wrong ownership and nonmatching boolean values reject confirmation. For N published
chunks and batch size B=500, each verification pass costs `ceil(N/B)` requests (zero
for N=0), with at most one in flight, instead of N full-chunk reads. A confirmation
retry before SQL succeeds can repeat this read cost; a confirmed replay performs no
vector reads. No latency or throughput measurement is claimed. Unsupported vector
backends explicitly reject both generation-scoped mutation and verification.

The manager index remains isolated from legacy search/chat.


## Wiki editorial storage

The Wiki uses migrations `0015_team_wiki.sql` and
`0041_wiki_files_and_arbitration.sql` and `src/wiki/`: one tree of pages and files
per space of any kind. Projects do not inherit their parent team's Wiki. Entries
are `page`, `rules` or `file`; a file is a leaf whose title keeps its extension.
Page text and its full history live in `wiki_revision`; a file keeps only its
current revision. The space `read`/`write` decisions and authorized `team_wiki`
pod offers control access; disabling the offer hides the Wiki without deleting it.

One arbitration serves pages and files. A proposal is a `proposed` revision:
a *draft* while bound to its conversation (`session_id`), *pending* once detached.
Acceptance publishes it (`published`); a refusal, a withdrawal or a declined draft
deletes the row, and nothing keeps or lists it. Only a person confirms or
arbitrates: `submit`, `accept` and `DELETE` refuse a delegated call (403). A
delegated turn only drafts, in its bound conversation; the `wiki_submit_proposal`
approval card then calls `submit` with the person's token. A member's submission
waits for an editor; an editor's is accepted in the same gesture, as is an
editor's manual proposal. A pending proposal is visible to its author and to the
editors, never expires, and stays arbitrable if its author loses access. A
proposal made on a changed revision, or for a name a sibling took meanwhile, is
`outdated` (computed) and cannot be accepted (409).

Every proposal from a conversation, a person's own included, is inserted as a
draft of that conversation and, for a person, detached in the same transaction:
the insert trigger checks the author's live conversation and snapshots its
agent instance and `agent_display_name`. That provenance survives the
conversation and the agent; no route exposes `session_id`. Deleting an entry
deletes its proposals and those creating an entry under it; marking a
conversation for deletion deletes its drafts (`session_drafts_retirement`).

`POST /wiki/proposals/file` (`Idempotency-Key`) copies the current content of an
output of the caller's own conversation, and its live PDF preview if any, through
the upload journal: a replay, checked against the immutable request fingerprint
stored at reservation (`0042_wiki_file_request_identity.sql`) and answered only
while the conversation lives, then a reservation in the space quota, a
verified copy outside SQL, then one transaction that stores the journal rows,
creates the `purpose='wiki'` document (id = revision id, no folder, no session)
and inserts the draft. The trigger requires those bytes to equal the current
content of an output of that conversation; a moved file answers 409
`content_changed`. The copy counts in the space quota from the draft on and is frozen
(`document_copy_frozen`); retiring a space fails its in-flight copies; removing
its revision clears its current content, which releases the quota and schedules
both objects in the content sweep, then the sweep deletes the empty document.
Wiki copies are never indexed or processed and stay out of every Drive reader.
`/wiki/revisions/{id}/{content|preview}` streams an accepted file to readers
and a proposal to those who see it, delegated reads included.

The same route accepts a human-selected conversation attachment (`document_id`),
a workspace file (`workspace_file: {path, sha256}`), or an editable document
(`writable_document: {document_id, sha256, format}`; Markdown by default, or Word).
Control Plane resolves the checked conversation's configured pod and calls only
its fixed authenticated source endpoint, with no redirects or arbitrary URLs.
A bounded anonymous spool checks the selected bytes before reservation; Word
exports check the saved Markdown digest at the capability before conversion.
The source owner retains editing/export responsibility. No intermediate
conversation deliverable is created. Migrations 0044/0045 retain immutable source
identities and require a verified completed receipt without a foreign key to
capability storage. Catalogue copies still match the checked conversation's bytes.

The Files drawer uses one destination for a selection and independent existing
file receipts, retaining successes and retrying failures. It sends `parent_slug`
for an existing page. Editors may instead supply `destination_title`: resolve or
create that named page under `parent_slug` (root if absent), then attach the file.
The page is created only in the successful publication transaction; cancellation
and failed transfers leave no empty page. All files in the selection reuse that
page. Non-editors may propose files to an existing page, without creating one.
Request fingerprints include the source, export format and destination intent;
existing single-file fingerprints remain unchanged. The browser retains request
metadata and keys, never content, to replay after a lost response or dialog reopen.
`GET /wiki/availability` includes `can_publish`, computed from the person's live
space rights, independently of an agent's writing mode.

The fingerprint covers the operation, space, conversation, source document,
expected content, requested title and parent, and replacement slug and base revision.
Titles use existing NFC/trim normalization; slugs stay exact; omitted and null
options both remain absent, without resolving defaults from current state.
Changed parameters return `409 idempotency_conflict`, even during copying or after
proposal deletion. An identical replay returns the original operation regardless
of later source edits; a deleted proposal returns 404 and is never recreated.

Space/organization cleanup marks Wiki copies with the space and purges the Wiki
in bounded batches, files first. The API preserves four tree levels, unique
sibling titles (`wiki_title_key`), revision comparisons, restoration as a new
revision, 50-entry history and proposal pages and base-revision conflicts. Text
limits remain 100,000 characters per page and 4,000 for rules.


## Local marketplace API

The organization catalogue holds frozen prompt, skill and reusable agent packages.
Only pending proposals and the current publication retain their content. Refusal,
cancellation, replacement and withdrawal erase the affected package and descriptive
metadata; they do not form a publication history. Minimal decision/request receipts
remain for idempotency: replaying a removed submission returns 409
`proposal_removed`, while its package detail returns 404. Refusing a replacement
preserves the current publication; replaying a decision never restores an older one.

Submission requires the source space's existing Write permission and organization
participation in the catalogue. A submitter with catalogue Write (organization
Editor) publishes immediately; other submissions remain pending for a catalogue
writer. Source writers can examine and cancel pending proposals; catalogue writers
can examine, decide and withdraw them. Approval checks the expected publication
version. Attribution grants nothing and revocation closes access. Source resource
deletion leaves a retained snapshot intact; source-space deletion detaches its
authorization relation while catalogue writers retain access. Technical roles do
not acquire content access through discovery.

`/me/marketplace-proposal-spaces` returns writable spaces with supported resource
kinds and their catalogue destinations, for submission and installation choices.
`/spaces/{catalogue}/marketplace/entries` and `/proposals` return authorized pages
of at most 100 rows using `next_cursor`; filters apply before pagination. Details
return the retained frozen package. Proposal `can_decide`/`can_cancel` and entry
`can_withdraw` are backend decisions. PUT decision, cancellation and withdrawal
use the corresponding item subpaths. POST submissions and entry installations
require a UUID `Idempotency-Key`; a different request with an accepted key returns
`idempotency_conflict`. The typed OpenAPI contract is the integration reference.

Installation uses ordinary resource validators and creation services. Its receipt
at `/spaces/{space}/marketplace-installations/{id}` retains provenance without
granting access or keeping resources alive. A replay after local deletion returns
`resource_exists=false`; it does not recreate the resource. Publication replacement,
withdrawal and source deletion do not modify installed resources. Copies and
imports are independent; names never identify publications and installation never
replaces a homonym.

Agent exports use the pod's template-field and capability owners. Each capability's
`validate_export` checks the stored configuration before scope-private settings are
reset: active DocumentAccess corpus selections and Tabular library bindings reject
the export rather than silently changing the agent. Ordinary agent copying retains
its existing reset behavior. Export does not implicitly include skills. Imports
carry no source identity; local template, capability and model policies are checked
again on commit. Pod calls occur outside SQL transactions; final submission checks
the source revision and resolved configuration again. Unsupported file owners or
configuration reject the whole operation.

Agent configuration is bounded to 2 MiB and 32 capabilities. The supported file
is one PowerPoint configuration original, at most 32 MiB. The organization owns
an immutable document copy, charged to its storage quota from submission, including
while approval is pending. Removing the proposal payload retires that copy,
releases its quota and schedules the existing physical cleanup. Public packages
contain file descriptors (document ID, name, MIME, size and digest); base64 bytes
are transient pod transport data, never durable package content. No marketplace
file-download route is added. Import reuses normal destination PowerPoint uploads,
quota checks and capability preparation, producing an independent original.
Document copies share the upload journal and lifecycle with Wiki. Skill limits
remain those of the normal package validator.

Source discovery is separate from publication. Existing prompt, skill and agent
edits expose `discoverable`, defaulting to false for new definitions, copies and
imports. Personal resources cannot opt in. `GET /organizations/{organization_id}/resources`
returns metadata for active organization participants and Organization Admins,
with optional `kind`, zero-based `page` (20 results) and `search` (180 characters).
Every search token must match name, description, source-space name or kind;
filtering and counting precede pagination in one read snapshot. Results contain
identity, name, description, source-space identity/name/kind and `can_read`, never
instructions, skill files, agent configuration or an importable package. Hidden
teams require a direct local role; project disclosure follows the parent team's
visibility or a direct project role, without exposing the hidden ancestor.
`can_read` reflects existing source content access (and agent template availability),
not a grant. Opening a source reuses its ordinary library and authorization.

These are implementation contracts. Test sources do not establish a passing run
or deployed reception; functional validation belongs to the developer.

## Hosted applications (reception pending)

Platform Admin registers application UI directories and optional API directories
through `/platform/applications`; registrations start disabled. These are trusted
HTTP(S) services: API requests carry the caller's bearer. Register the full upstream
UI directory (for example `http://fred-evaluator-ui:8080/apps/evaluation/`) and API
root (for example `http://application-api:8080/api/`). URLs must
end in `/` and contain no credentials, query or fragment. The stable logical name
is the SDK application ID; the UUID identifies the registry entry. A revision is
required for updates. Suspension preserves application data and governance.

Applications use the `$applications` source and existing organization capability
and team/project capability-policy screens. An organization Owner authorizes an
offer; local Owners can only restrict the inherited ceiling. Personal spaces are
excluded. The entry permission uses the existing space permission matrix (register
Evaluation with `run_evaluations`); each service still checks its own action rights.
Applications never become agent tools or pod templates.

`/spaces/{space_id}/applications` returns permitted applications and browser paths,
without internal destinations. The gateway forwards `/apps/` and `/app-services/`
to Control Plane. Static GET/HEAD requests carry no credentials; API requests retain
`teams/{space_uuid}/...` below the registered API directory and forward only the
validated user bearer. Redirects and unsafe path segments are rejected. Requests
are capped at 16 MiB/60 seconds; responses stream up to 64 MiB with a 180-second
upstream deadline. Suspension affects new admissions, not already admitted calls.

Targeted disposable reception: `make test-integration
CARGO_TEST_OPTS=applications::hosted_applications_registration_governance_and_proxy`.
Local SQL/HTTP checks do not establish deployed UI acceptance.

## Managed MCP connections (reception pending)

Each connection belongs to a space. The supported management journey is the
organization Owner's MCP panel in Features, beside models. Its space routes check
Manage permission for configuration, observation, publication and activation. Create → test
→ review the tool contracts → publish → enable. Testing only negotiates MCP and
paginates `tools/list`; it does not invoke a business tool. A successful test is
not a business authorization and cannot prove that every pod has its credential.

Impact is an aggregate `affected_instance_count` of saved selections within the
owning organization. It contains no agent or
space details; the existing business revoke-impact route retains its own rights.
Disabling with the exact stored configuration remains possible after provisioning
has been removed. Role, revision and metadata validation still apply. Activation
and any configuration change use normal destination/reference validation.

Organization owners use the existing capabilities page to authorize the central
offer. Team/project restrictions use the existing parent ceiling. Editors select
it in the existing agent form, in Simple or Advanced mode. Compatible Python
ReAct/Deep/Graph templates explicitly advertise `supports_managed_mcp`, independently
of `supports_capabilities`. Selectable templates offer the permitted catalog;
fixed templates retain their author-declared native capabilities and cannot add
external connections. Creation and
editing retain those defaults and reject additional managed selections. Import
and admission require the included set to match the template and still enforce
availability and organization/local policy. The embedded Rust agent does not
advertise this support.

Migration `0021_managed_mcp.sql` preserves native offer identities while renaming
`runtime_capability` to `capability_offer`, and governance keys to `source_id`.
`capability_source` records `pod` or `managed_mcp` provenance. The central `$mcp`
source has no runtime, ingress or template. Each connection has one linked offer
`managed-mcp:<UUID>`; this namespace is reserved in native inventories/catalogs.
The same offer and business permission serve every compatible pod. There is no
second permission store and no local YAML fallback for managed selections.

Migration `0023_mcp_space_ownership.sql` adds mandatory space ownership and per-space
logical-name uniqueness. It requires an empty MCP table; existing unowned
connections require a fresh installation, without backfill. Space purge cascades
through connections, offers and permissions. `$mcp` is technical provenance only.

Template choices read only advertised descriptors from `capability_offer`, once
per template-list request. Every connection mutation updates this projection in
its transaction. Admission loads detailed contracts only for selected connections
and rechecks their actual availability with policy in its SQL snapshot. Model
names remain stable collision-safe aliases; descriptions always include the exact
remote tool name, even if the remote description is absent. The published contract
and the name sent in MCP calls remain unchanged.

Provision a reference in Control Plane's `platform.mcp_credentials`:

```yaml
platform:
  mcp_credentials:
    - space_id: <owning-organization-space-uuid>
      credential_binding: external-search
      url: https://tools.example.org/mcp
      secret_env: EXTERNAL_SEARCH_KEY
```

Control Plane only proposes and accepts references assigned to the owning space.
Provision the same logical reference and exact URL in **each executing pod**,
under its top-level `mcp_credentials`. The environment variable name and value
may differ between workloads. Supply the value through the workload's existing
secret/environment mechanism, never through the browser, SQL connection record
or agent tuning. No reference is needed for unauthenticated MCP. Available
references in the administrator form report the Control Plane workload only.
A new reference requires normal workload configuration reload/restart; changing
a connection among already provisioned references is effective next admission.

Supported transport is Streamable HTTP using the maintained Rust `rmcp` SDK for
discovery and the existing FastMCP/LangChain runtime adapter for execution.
External authentication is none, bearer, or an `x-*` API-key header (`x-fred-*` is reserved).
Destinations reject embedded credentials, query strings and fragments; plaintext
HTTP needs explicit opt-in. Redirects are refused. No Fred JWT, delegation grant,
workspace, document or session context is inferred for these external tools.

Configuration edits use `expected_revision`. Discovery claims a unique token
and publishes only if both token and revision still match; it holds no SQL
transaction over network I/O. Publication also pins the reviewed `checked_at`.
Failed discovery preserves the last inventory but makes new execution unavailable.
A destination/authentication change requires another test and publication.
Metadata/activation edits carry the unchanged technical contract forward.
Disabling retains the offer, selections and affected-agent diagnosis; no delete
endpoint is exposed, and the offer's FK prevents deleting its connection.

Admission resolves current policy and technical bindings in its SQL snapshot.
Each admitted turn owns its immutable binding/revision and independent clients;
no process-wide registry or tool cache is updated. Runtime verifies the published
tool contracts before exposing them: remote additions remain hidden, removals or
contract changes fail closed until reviewed and republished. Tool names include
the connection UUID. External MCP marketplace selections have empty configuration.
Installation rechecks
the destination space and template, and admission resolves the current connection.
No connection credential or document grant is exported.

Bounds: 64 configured connections; 16 inventory pages, 256 tools and 1 MiB of
serialized inventory; discovery negotiation 15 s, listing 20 s, close 3 s;
runtime initialization 5 s, listing 20 s and individual calls 30 s. The Rust SDK
also bounds transport responses. There is no periodic health probe, personal OAuth flow,
per-tool business permission or per-organization technical identity in this lot.
Activation affects new admissions; an admitted turn keeps its context, but an
external server outage or credential revocation can still interrupt a call.

### Targeted checks to run separately

These commands have **not** been run for this change. The integration target
creates a disposable PostgreSQL container; do not point it at a development DB.
From the repository root:

```bash
~/.cargo/bin/cargo test -p control-plane --lib mcp_connections
~/.cargo/bin/cargo test -p control-plane --test openapi
make -C apps/control-plane test-integration CARGO_TEST_OPTS=managed_mcp
(cd libs/fred-runtime && .venv/bin/pytest tests/test_managed_mcp.py tests/test_mcp_v2_client.py tests/test_agent_app.py tests/test_delegated_admission.py)
(cd apps/frontend && npx --no-install vitest run src/rework/components/pages/admin/McpConnectionsPage/McpConnectionsPage.test.tsx src/rework/components/pages/admin/FeaturesPage/OrganizationCapabilities.test.tsx src/rework/components/pages/TeamSettingsPage/SpaceOffers.test.tsx src/rework/components/pages/TeamAgentsPage/AgentFormModal/AgentFormModal.capabilities.test.tsx src/rework/components/pages/TeamAgentsPage/AgentFormModal/SimpleCapabilitiesView/SimpleCapabilitiesView.test.tsx)
```

Frontend commands require the repository's Node version. Run the repository's
usual lint/type checks yourself after these behavioral tests; they were not run
as part of implementation. Existing native-capability integration tests were
adapted to the renamed SQL tables and remain relevant for regression testing.

### Manual reception: two pods and a team restriction

1. On a disposable environment, apply the migration through normal deployment.
   Register two Python pods using this runtime, with distinct runtime IDs and
   flexible templates. For authenticated peers, provision the same reference/URL
   in CP and both pods. The unauthenticated local fixture below needs none.
2. As organization Owner in Features > MCP, create one connection to a controlled MCP server,
   test it, inspect/publish its inventory and enable it. Verify no business tool
   was called during discovery, and no permission appeared automatically.
3. As organization owner, authorize its single central offer. Create one agent
   from each pod's template and select that offer in the existing form. Invoke a
   harmless fixture tool from both agents; observe the same connection/revision.
4. Restrict the team's central offers to an empty set. Both agents must be
   refused on their next admission. A previously admitted turn retains its
   binding. Remove the restriction; new admissions work without pod restart.
5. Check another organization has no inherited authorization. Check a native
   capability with the same display/logical name remains independently selected.
6. Add a remote tool: it remains hidden until test/review/publication. Remove or
   change a published schema: execution refuses it. Change destination with an
   in-flight discovery: its stale result must not overwrite the new revision.
7. Disable the connection and inspect the aggregate affected-agent count with a
   platform-only account: no agent/space names or IDs may be returned. Verify next-admission
   refusal on both pods, plus undeclared fixed-template dependencies, missing workload
   secret and redirect refusal. Inspect API responses/logs for secret absence.

This is a reception procedure to execute, not an end-to-end acceptance record.


### Same local HTTP peer: real Rust discovery through Python execution

The existing stdio wire fixture cannot serve the Control Plane's HTTP discovery.
The small [HTTP fixture](../../libs/fred-runtime/tests/fixtures/managed_mcp_http.py)
uses the runtime's installed FastMCP dependency, with no additional test framework.
This scenario has **not been executed**.

1. In the disposable environment above, start this peer yourself from the repo root:

   ```bash
   libs/fred-runtime/.venv/bin/python libs/fred-runtime/tests/fixtures/managed_mcp_http.py --port 8333
   ```

   The endpoint is `http://127.0.0.1:8333/mcp` when all workloads run on the host.
   For containers, use `--host 0.0.0.0` and choose **one exact URL reachable from
   both Control Plane and Python pods** on your local network. Use that URL for
   every step; do not substitute another mock endpoint in the runtime. Select no
   authentication and explicitly allow insecure HTTP for this local reception.
2. As platform admin, create the connection, then **test through the Control Plane**.
   Its Rust MCP client must negotiate and list `add(a, b)` and `multiply(a, b)`,
   both without descriptions. Check the observed schemas in the UI. The peer's
   terminal must contain no `MCP call:` lines yet. Publish that observation and
   enable the connection. Keep its connection ID and publication revision.
3. As organization owner, authorize the single central offer. As an editor,
   select it explicitly in an agent on each compatible Python pod. In each chat,
   ask: “Call the MCP tools add and multiply with a=2 and b=3; report both results.”
   Check actual tool events and the peer's `MCP call: add` / `MCP call: multiply`
   lines, with results 5 and 6. A model answer alone does not prove execution.
   Check that admission on both pods carries the same connection and revision;
   the model's descriptions contain the original names despite the opaque aliases.
4. Stop only this peer and restart it at the **same address and port** with:

   ```bash
   libs/fred-runtime/.venv/bin/python libs/fred-runtime/tests/fixtures/managed_mcp_http.py --port 8333 --changed-contract
   ```

   Retain `--host` if used before. `add` now has an extra `offset` argument. Before
   retesting/publishing, start a **new turn** on the existing agent: the Python
   runtime must refuse the changed published contract (`mcp_published_tool_changed`)
   before any business call. Previously admitted work is not a new-admission test.
5. Test again through Rust, inspect the new input schema, publish the reviewed
   observation, and start another new turn. Ask to call `add(2, 3, offset=10)`;
   verify the real peer invocation and result 15. No pod restart or registry
   update is needed. Recheck local restriction and technical disablement from
   the preceding procedure; both must block new admissions.
6. Separately, on an authenticated test connection, remove its provisioned
   reference and reload the CP configuration through the normal local procedure.
   With a fresh revision, disabling the stored configuration must succeed.
   Re-enabling or changing to an unprovisioned destination/reference must fail;
   stale revisions and non-platform actors must remain refused.

These are expected reception results, not an assertion that interoperability,
permissions, UI behavior or performance have been validated.

### Trusted Knowledge Flow Tabular

Tabular is a native capability, `mcp-knowledge-flow-mcp-tabular`, owned by
`fred-capability-mcp`. Its ordinary pod offer, organization permission and local
restrictions govern selection and admission. Configuration, marketplace copying
and chat controls use the native ID without substitution. General, Deep and fixed
templates retain their usual capability selection rules.

No organization connection, technical activation, availability probe or published
inventory is needed. The MCP administration API accepts only external authentication
modes (`none`, `bearer`, `api_key`). Migration `0024_native_tabular.sql` removes the
obsolete service index and enforces that boundary for fresh installations. It does
not convert existing data or grant permissions.

When Tabular is selected, Control Plane emits an internal MCP binding containing
only `kind: knowledge_flow_tabular` and the trusted `url`, derived from
`platform.knowledge_flow_url` plus `/mcp/tabular`. No network call occurs during
this resolution. The pod verifies the endpoint against `ai.knowledge_flow_url`
before obtaining credentials. The existing transport uses the turn's
`DelegatedCredentialProvider`, token renewal and `KnowledgeFlowAgentContext`.
Redirects are disabled, and model arguments cannot replace the delegated grant or
document scope. Missing configuration fails admission; service outages fail
execution without changing stored permissions or selections.

The runtime discovers the trusted internal service's tools for the turn, with the
same bounded transport as external MCP. Its contract is owned by the Fred deployment;
there is no manual external-inventory review. External connections still execute
only their published tools and never receive Fred credentials or document context.
Tabular prompt assembly, provenance guards and resource authorization remain in
their existing owners. Graph authors still supply their own business instructions.

### Real Knowledge Flow reception: two pods

Use a prepared development environment; this procedure does not authorize resetting
an existing database. The implementation targets fresh installations, not historical
connection or selection conversion. Automated tests and a real deployment receipt
are separate evidence.

1. With **no MCP connection**, enable the native Tabular capability for the organization
   and permit it in the test team. Open General and Deep agent forms: both offer
   the same native selection, with no technical setup step.
2. Save agents with Tabular and its document-selection controls. Reload them and
   verify selection and configuration. A fixed template declaring Tabular keeps it
   as an included capability.
3. Ingest a CSV and an XLSX in that team. Wait for processing to publish them;
   select each document in a conversation and request table listing, schema inspection
   and a sum whose result is known. Verify actual tool calls, not only model text.
4. Repeat under two users/pods. Check user delegation and canonical document context;
   attempts to read another team's document or another conversation's attachment fail.
5. Disable the capability for the team: new selections/admissions are refused and
   the form explains the restriction. Restore it and retry. A Knowledge Flow outage
   causes an execution failure, without hiding the capability or revoking its policy.
6. Check an external MCP still requires discovery/publication and receives no Fred
   identity, even if its display name or URL resembles Knowledge Flow.

Targeted checks:

```bash
make -C apps/control-plane test-integration CARGO_TEST_OPTS=managed_mcp
(cd libs/fred-sdk && .venv/bin/pytest tests/test_mcp_admission_contract.py)
(cd libs/fred-runtime && .venv/bin/pytest tests/test_managed_mcp.py tests/test_delegated_admission.py tests/test_mcp_document_scope.py tests/test_react_prompting.py)
(cd apps/frontend && npx --no-install vitest run src/rework/components/pages/admin/McpConnectionsPage src/rework/components/pages/TeamAgentsPage/AgentFormModal src/rework/features/pipeline/weaver/resourceSupport.test.ts)
```

### Personal profile photo (reception pending)

`GET`, `PUT` (one multipart `file`) and `DELETE` share
`/control-plane/v1/users/me/avatar`. They require an admitted human account and
apply only to its verified subject, including a platform admin with no spaces.
GET returns a PNG or 204 when absent; responses are private and not HTTP-cached.
The browser uses its authenticated client, never a bearer in an image URL.

`GET /spaces/{space_id}/users/{user_id}/avatar` reuses this transport for an
author's photo. Both caller and photo owner must have current Read permission in
that space, checked before and after storage I/O. Workloads cannot use this route.
The UI shares requests by space and subject and falls back to initials on absence
or refusal. Wiki summaries distinguish the revision's author and agent identity
from the last metadata editor; profile photos never stand in for an agent author.

Migration `0025_user_avatar.sql` records one active photo and at most one pending
upload per subject. S3 retains the normalized 192 x 192 PNG in the existing content
namespace; no organization document or quota is created. Inputs are JPEG, PNG or
WebP, at most 5 MiB and 4096 x 4096 pixels. Decoding is bounded and off the async
executor. Replacement/removal retire old objects; the existing cleanup worker
handles expiry, failed transfers and orphans. Content uploads and cleanup must be
enabled. No additional bucket, worker or public image route is needed.

Reception: apply the migration through the normal initialization command, restart
Control Plane, then import, replace, reload and remove a photo from Settings.
Check the personal navigation avatar and a platform-only account. The new unit and
OpenAPI fixtures and existing frontend tests have not been executed for this port.

### Team settings and members (implementation; reception pending)

The lot on `gap/team-settings` extends Weaver's existing space governance, using
Swift `cf698a739afae1b4cbcd92e82439e32bc1038198` only as a functional reference.
`PATCH /spaces/{id}` accepts name and/or description for a team under direct
Manage permission. Names reuse creation's NFC normalization, bounds and sibling
uniqueness; supplied fields commit together. Visibility and optional self-enrollment
are described below. The existing offers and usage navigation entries remain.

Roster reads now allow direct Read or Manage; candidate discovery and role changes
still require Manage. The optional `search` matches subject, username, name or email
among scoped people only. It scans at most 200 profiles per request (50 per batch,
eight concurrent directory lookups, each batch bounded to 15 seconds); a sparse or
empty result may have a continuation cursor. It never filters a truncated global
identity search. `DELETE /spaces/{id}/members/{user}` removes all direct roles in
one transaction, by a responsible person or the person leaving. Individual role
revocation uses the same checks. Last-owner and dependent-project refusals leave
all roles intact, including during concurrent departures. Resources remain owned
by the space.

Migration `0028_team_join_link.sql` stores one revocable token per team. The owner
creates or rotates it through `/spaces/{id}/join-link`; rotation invalidates the
previous token. Dimi confirmed **7 days** in the lot 1 chat. `/team-join-links/{token}`
previews or redeems it after ordinary authentication, admission and consent. The
recipient must already hold a direct content role in the parent organization,
matching Weaver's existing child-membership prerequisite. Redemption adds Member
only on that team, preserves other roles and grants nothing on projects or other
teams. Expiration/revocation block future joins without removing existing grants;
a former owner's link cannot continue granting access. SQL governance guards order
redemption, rotation, revocation and retirement. Application HTTP logs redact the
token. Account provisioning is not part of enrollment.

Migration `0029_team_avatar.sql` extends the existing avatar table (renamed from
`user_avatar` to `avatar`) with a team owner. `/spaces/{id}/avatar` uses the personal
photo's exact multipart parser, crop/normalization, content storage, transfer limits
and durable sweeper. Team discovery (described below) allows reading; Manage allows upload/removal.
Publication rechecks current authority after S3 I/O. Space purge retires both active
and pending photos while preserving their cleanup journal and pending-write deadline.
There is no second bucket, worker or quota account. The shared frontend crop card
and authenticated binary client feed settings and sidebar photos; personal photos
retain their existing endpoints. Published migrations 0001-0027 are unchanged.

Reception scenarios for Dimi, after the normal migration/deployment process:

1. As an owner without a content role, follow the description banner or Settings;
   rename the team, save its description, navigate back and reload. Try a duplicate
   sibling name, whitespace/Unicode normalization and invalid lengths. Keep one
   field's unsaved draft while saving the other. Check offers and usage entries.
2. Upload, replace, reload and remove a JPEG/PNG/WebP avatar; compare settings, team
   navigation and the Home team list. Try an invalid file and a file over 5 MiB.
   Verify personal photos still work and failed uploads leave the current photo intact.
3. Search current members and eligible candidates by name/email, including a result
   beyond the first page. Navigate sparse search pages; verify another organization
   never appears. Add and remove each explicit role and reload.
4. As a Member, read roles and leave; attempt to modify another member's roles.
   As an owner, remove a multi-role member. Try the last owner's departure and a
   person with project roles: refusal must leave every role unchanged. Hand over
   responsibility/remove project roles, then retry. Resources must remain.
5. Create, copy and open the link using another admitted person in the organization;
   verify consent precedes entry if necessary. Join explicitly and reload. Verify
   only the team's Member role was added, with no project or other-team access.
6. Rotate/revoke a link, retry its old URL, and retry a link past its displayed
   expiry. People already joined stay members. A person in another organization,
   a user without the parent's content role, and an issuer losing Manage must
   be refused. Keep a preview open while revoking, then try redemption.
7. In two browser sessions, compete to remove the two owners; at least one must
   remain. Revoke management while editing or uploading; confirm refusal on save.
   Exercise photo cleanup and team deletion through the existing lifecycle.

Focused checks (from the repository root) use disposable PostgreSQL and the real
HTTP/SQL contracts. They cover settings, membership, invitation links, discovery,
model restrictions and document activity; they do not establish deployed or browser
reception:

```sh
make -C apps/control-plane test-integration CARGO_TEST_OPTS=team_
make -C apps/control-plane test-integration CARGO_TEST_OPTS=membership_removal
make -C apps/control-plane test-integration CARGO_TEST_OPTS=model_catalog
make -C apps/control-plane test-integration CARGO_TEST_OPTS=session_deletion
make -C apps/frontend update-control-plane-api
make -C apps/control-plane code-quality
make -C apps/frontend code-quality
make -C docs/architecture generate-models
make -C docs/architecture check-models
```

### Team discovery and optional enrollment (implementation; reception pending)

The lot 2 increment extends `space` with `visibility` (`hidden`/`visible`) and
`joining_mode` (`invite_only`/`open`), through schema step
`0032_team_discovery.sql` in the existing SQLx initialization chain. This chain
constructs the final schema on an empty installation; it does not define support
for upgrading an existing Swift or Weaver. This increment includes no data
conversion, backfill, compatibility path or upgrade tests. Hidden and invite-only
are the defaults for newly created teams and projects. These are settings of the space's own
lifecycle, removed with it, not publication or role facts. Organizations and personal
spaces must retain the neutral defaults. Migration `0054_project_parameters.sql`
gives projects the team parameters (description, avatar, retention, discovery);
a project never enters the organization directory. Its audience is the content
holders of its parent team: `GET /spaces/{team_id}/projects` lists visible projects
and those where the caller holds a direct role, `discovery`, `avatar` and `join`
apply the same boundary, and a hidden project keeps its resources out of the
resource catalogue. There
is no new table, invitation mechanism, permission matrix or background projection.

`GET /organizations/{organization_id}/teams` returns 20 cards per zero-based `page`,
a filtered `total`, and optional `search` (at most 180 characters). Every search
word must occur literally in the name or description, ignoring case. SQL filters
before counting/paging and orders by name then ID; changes between pages can move
rows, so this is a current directory rather than a durable snapshot. The existing
organization and subject-role indexes bound the reads; no additional index is
justified for the current target of up to 100 teams per organization.

Organization eligibility reuses `authorization::load_facts`: active organization
participants and Organization Admins can read the directory. Within an active
organization, a card is available if the team is active and visible, or the
caller holds a direct role on it. `GET /spaces/{id}/discovery` and the existing
`GET /spaces/{id}/avatar` use that same boundary. The avatar reader checks it again
after object-store I/O and returns no public object URL. Cards expose only team
identity, description, discovery settings, the caller's own membership and join
affordance, plus a bounded roster summary: the count of distinct direct role
holders, the count of direct owners and the display names of at most three owners.
Counts and owner subjects come from the card query's correlated subqueries on the
`space_role_grant` primary key (no per-card round trip); the route resolves the
names of a whole page in one directory call after SQL is released, and an
unavailable directory leaves names empty. Cards expose no member list or content.
Reading cards grants no document, conversation, member-list, management or project
authority.

`PATCH /spaces/{id}` accepts either setting alongside name/description, with the
existing current Manage decision and exclusive organization guard. Hiding or
closing a team neither removes existing roles nor changes any agent publication.
A hidden team can retain an open preference, but neither the card nor a direct
`POST /spaces/{id}/join` allows enrollment while hidden. Existing invitation links
remain the route for new members of hidden teams, with their existing expiry,
revocation and parent-role prerequisite.

Self-enrollment requires the same direct content role on the parent organization
as invitation redemption and ordinary team role assignment. The POST acquires the
existing platform-then-organization governance locks and rechecks attachment,
lifecycle, visibility, mode and parent eligibility before writing. A newcomer
receives only the normal direct Member grant; a caller already holding any direct
team role is left unchanged, including an owner without content access. Repeated
or concurrent open/invited joins converge on the existing role uniqueness key.
Changing settings and revoking roles serialize with enrollment; no SQL transaction
is held across directory or object-store calls. Joins inherit the existing global
governance contention boundary, while directory reads share the organization guard.

The existing marketplace Teams route and TeamCard now use the generated Weaver
client. Search and pagination are server-side; working-organization changes reset
the page. Cache invalidation refreshes membership/navigation and access after join,
with focus/reconnect refresh and bounded polling for changes from another session.
Failed/refetching directory requests withhold old cards; failed avatar requests
withhold the old photo. The neutral team landing preserves owner-only access.
Parameters use shared Select/Button controls and both locales. Swift's global
enumeration and legacy team client are removed from these views; its card layout
(member count, owners, three-line description) returns from the summary above.

Discovery regressions are in `tests/support/team_discovery.rs`; API contracts are
in `tests/openapi.rs` and UI regressions accompany marketplace cards and parameters.
The generated REST inventory and SQL diagram describe the assembled contract,
without establishing deployed acceptance.

Reception scenarios after integration and the normal fresh-schema deployment:

1. In Acme, search by name and description and traverse more than 20 teams. Switch
   to Globex: no previous organization card, avatar or search page may remain.
   Verify personal/project spaces are absent, including via guessed metadata IDs;
   a visible project is disclosed only to content holders of its team.
2. As an organization member outside a visible team, read its name/description/photo;
   direct documents, conversations, roster, settings and project URLs remain denied.
   Repeat as a foreign user and a platform-only admin: metadata and avatars are denied.
3. As the Responsible person, switch visible/hidden and invitation/open. Check a
   hidden team remains in its members' directory/navigation; its non-members lose
   metadata and avatar access. Its published agent remains published and usable by
   the publication audience. Changing one setting preserves unsaved name/description.
4. Join a visible open team twice and from two tabs, concurrently with an invitation:
   exactly one direct Member grant, no additional role/project grant. An owner-only
   caller must not gain content access by POSTing join. A child-only organization
   participant can discover cards but cannot self-enroll without the parent role.
5. Keep a card open while another session hides/closes/deletes the team or revokes
   the parent role. A subsequent or queued join must refuse; refreshing drops stale
   cards. Restore eligibility and retry a lost-response join without duplicate grants.
6. Join a hidden team by its valid invitation link. Expire/revoke the link and close
   enrollment: existing members remain. Revoke management during a settings save;
   check refusal and that no partial name/description/settings change committed.

## Consumption analytics

Use `POST /control-plane/v1/analytics/query` for consumption reads. The canonical
[arc42 contract](../../docs/architecture/A12-control-plane-api.md#consumption-analytics)
defines scopes, authorization, measures, precision, estimates, source boundaries and
budgets, with the current frontend wiring and its validation limits.

Example request:

```json
{"queries":[{"name":"input","scope":{"kind":"self","organization_id":"00000000-0000-0000-0000-000000000001"},"time":{"since":"2026-01-01T00:00:00Z","until":"2026-01-03T00:00:00Z","timezone":"UTC"},"measures":["usage.input_tokens"],"group_by":[]}]}
```

For one recorded report containing 100 input tokens, the response is:

```json
{"calculation":"exact","collection_completeness":"unknown","results":{"input":{"since":"2026-01-01T00:00:00Z","until":"2026-01-03T00:00:00Z","timezone":"UTC","calendar":{"exclude_weekends":false,"exclude_holidays":false},"measures":[{"id":"usage.input_tokens","unit":"token","value_type":"integer","calculation":"exact"}],"rows":[{"dimensions":{"kind":"total"},"values":{"usage.input_tokens":"100"}}],"truncated":false}}}
```

Configure optional `storage.history` with `url`, one concrete `index`, and paired
`username`/`password_env_var` references if authentication is required. Grant read,
search and mapping inspection on that index only; credentials follow existing env
Secret conventions. The adapter pools one reqwest client, verifies TLS, disables
redirects, bounds connection time at 2s and each HTTP call at 5s, with 4s search and
10s batch deadlines. No runtime index creation or mapping mutation occurs.

`tests/support/usage.rs` exercises SQL isolation, estimates, cache, coverage and bounds;
`tests/analytics_history.rs` exercises the actual HTTP adapter and optionally a real
three-shard disposable OpenSearch via `CONTROL_PLANE_IT_OPENSEARCH`. Frontend tests
exercise rendering and real RTK cache/identity isolation. Production capacity and
functional browser reception remain separate.

### Team analytics (implementation; reception pending)

`TeamUsagePage` now uses only the common analytics POST for its collective cards.
Direct Owner/Analyst `ReadUsage`, organization participation, admission and current
consent gate consumption, retained creations, completed turns and skill loads.
The established team perimeter includes its projects, including retained deletion
receipts; a project stays local. The SQL predicate is shared by all these readers.
No user/session identity or conversation content is returned by aggregate reads.

`activity.active_users`, `activity.observed_conversations`, `activity.failed_turns`
and `activity.single_turn_conversations` extend completed-turn totals. Distinct
identities are exact over the bounded aggregation, not approximate cardinalities.
Missing/erased attribution omits affected values; missing outcome omits failed turns.
Empty valid history returns zero. Turns remain completion events, not unique messages;
conversation counts here mean observed conversations, not SQL creation counts.
`activity.retained_conversations` also supports collective scope, with the same
retained-catalogue definition as below. None of these counts grants content access.

Time grouping of turns supports UTC hour/day/week buckets, filled only after a valid
read. Attribution uses at most 10,000 composite groups across space, agent, user,
session and optional bucket. Exceeding this budget fails the batch rather than
silently dropping identities. Historical and SQL batches remain independent.
Consumption by agent/model now displays the existing estimates and their coverage;
comparison windows have equal elapsed duration. The collective Excel export rereads
the selected tab through the same authorized endpoint, preserves values as text,
and drops late results after context changes. It contains no personal dashboards.

The [lot 5 coverage matrix and acceptance scenarios](../../WEAVER_SWIFT_PORTAGE_A_REPRENDRE.md#lot-5---analytiques-déquipe-et-consommation-15-novembre-2026)
record the remaining Swift gaps and exact counting examples. Automated checks and
manual reception are distinct; the latter remains pending.
No migration, index mutation, backfill or deployed validation accompanies this code.

#### Additional team measures (implementation; acceptance pending)

The common POST and its existing authorization remain the only read/export path.
There is no new table, migration, historical journal, endpoint, backfill or upgrade
path. Installation assumes an empty Weaver database. SQL catalogue and receipt
reads share the existing read-only snapshot; historical observations are separate
reads. Targeted automated regressions have passed, including disposable SQL and
OpenSearch fixtures. The complete numerical/browser/Excel acceptance below remains pending.

All period measures use `[since,until)`, UTC completion/creation instants, and the
same server-side `time.calendar` object, echoed in each result. Its optional
`exclude_weekends` and `exclude_holidays` flags default to false. Dates are UTC,
not Europe/Paris; an offset-bearing input is converted to UTC before counting.
The holiday reference is the eleven national French holidays in
[article L3133-1](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000033020901/),
as listed by [Service Public](https://www.service-public.gouv.fr/entreprendre/vosdroits/F2405):
eight fixed dates plus Easter Monday, Ascension and Whit Monday. Local additions
(Alsace-Moselle, overseas territories), bridges and individual work schedules are
excluded from this calendar. Years 1970..9999 and maximum 366 elapsed days are
accepted. Partial UTC days touched by the half-open window count as one day.
Current stocks do not acquire a historical meaning from the selected period.

The preceding period has the same elapsed duration, ending at `since`; its own
excluded dates and denominators are computed from the same flags. Excluded facts
are removed before totals, rankings, ratios and estimates. Continuous time series
retain zero buckets on excluded days; the result and export announce the filter.
For recorded exchanges, the first consumption remains the first unfiltered fact:
a later included resume never turns an excluded first report into a new exchange.

The collective population is the authorized team and its projects, or the selected
project alone, including historical space references under the existing contract.
Current membership lists never supply analytic denominators. No person/conversation
identity is returned. The following definitions describe source observations, not
complete collection; `collection_completeness` remains unknown.

| Measures | Canonical fact and population | Calculation / absence | Deletion and retention |
| --- | --- | --- | --- |
| `inventory.enabled_agents` | Current `agent_instance.enabled`, instances owned by non-deleting scoped spaces | Current stock, independent of period/calendar. Not a guarantee that a pod/model is executable. Zero when the valid catalogue has none. | Agent removal or space retirement removes it. No past-stock comparison. |
| `inventory.retained_agents_created` | Retained instances by immutable `agent_instance.created_at`, enabled or disabled | Count created in the filtered period, not an immutable creation-event journal. | Removing an instance or retiring its space changes both period comparisons. |
| `inventory.agents_published` | **No agent publication field, relation, producer or operation exists in Weaver**; prompt publication is a different fact | Always absent: explicitly "not collected", never zero or inferred from `enabled`. | No historical reconstruction. Publication belongs to the agent catalogue owner, outside this increment. |
| `inventory.documents_added` | `document_upload` source receipts, `stored`, no `session_id`, by `completed_at` | Count retained successful drive imports in the filtered period. Failed/pending uploads, attachments, previews, output files and reprocessing do not count. | Document purge deletes its successful receipts; the count is therefore not a permanent import history. |
| `activity.retained_conversations_per_creator_median` | `session_metadata.created_at`, sessions/spaces not marked for deletion; only creators with at least one retained creation in the filtered window | Median retained creations per creator. Empty population: absent. This is **not** conversations per active user or all historical creations. | Deletion changes population, distribution and both comparisons. |
| `activity.creators_1`, `_2_3`, `_4_10`, `_11_30`, `_31_plus` | The same retained-creation population | Number of creators in each inclusive range; zeros on an empty valid catalogue. No identities exposed. | Same as retained creations. |
| `activity.retained_conversations_top_decile_share` | The same retained-creation population | Sum of creations of the top `ceil(creators/10)` creators / all retained creations. Empty denominator: absent. | Same as retained creations. |
| `activity.median_usage_days` | Observed `agent.turn_completed`, distinct `(user_id, UTC date)` in filtered period | Median active dates among users with at least one observed completion. Missing user attribution or empty population: absent. | History retention/erasure applies, independently of current membership or session deletion. |
| `activity.median_days_per_week` | Same users and dates; `D` = retained UTC dates touched by window | Median days / `max(1,D/5)` when weekends excluded, otherwise / `max(1,D/7)`. Holiday-only filtering still uses seven-day weeks. | Same history rule. |
| `activity.mean_daily_active`, `activity.daily_usage_share` | Same users/dates; `P` = distinct user/date pairs; `U` = observed users | `P/D` and `P/(D*U)` respectively. Zero users permits mean 0 if D>0; any zero denominator is absent. Missing user attribution: absent. | Same history rule. |
| `activity.median_turns_per_conversation`, `activity.single_turn_rate` | Observed completions grouped by conversation within the filtered window | Median completions; conversations with exactly one completion / observed conversations. Missing conversation attribution or empty population: absent. Not lifetime length. | Same history rule. |
| `activity.failure_rate` | All observed completions; `finish_reason=error` | Error completions / all completions, including paused/resumed executions. Any missing outcome or empty denominator: absent. | Same history rule. |
| `tools.attempts`, `.successes`, `.failures`, `.cancelled`, `.awaiting_human`, `.failure_rate` | One `agent.tool_latency_ms` observation per shared `ToolExecution` boundary, attributed from the admitted binding's space and instance | Attempts include local authorization failure; outcomes are `ok/error/cancelled/awaiting_human`. Failure rate = error/(ok+error). A pause and resume are two attempts; provider-internal retries are not separately observed. | History retention applies. Missing tool/agent attribution rejects the read; missing/unknown outcome preserves attempts but omits all outcome counters/rate for that group. |

Tool timers already exist in ReAct/Deep middleware and Graph execution. A trace
span, `tool_count`, skill-load event or the separate `agent.tool_failed_total`
counter is not added to these attempts. Same-named tools are grouped across
providers and agents, explicitly labelled as such; this does not claim capability
usage attribution. The shared timer now preserves the explicit `awaiting_human`
state when Graph interruption unwinds it; cancellation remains separate and an
ordinary exception remains an error. No new telemetry event is introduced.
Runtimes not emitting these canonical observations (including embedded Rust) are
outside historical counts; a valid empty source does not prove zero real activity.

Counts and medians remain exact decimal strings. Ratios/normalized frequencies
use integer long division truncated to six fractional digits and declare
`calculation=rounded`, `value_type=decimal`; no JavaScript floating conversion is
required. Missing values are absent, stocks have no previous value, and publication
is explicitly non-collected. Excel preserves the same definitions, units,
precision, filters, collection uncertainty and truncation flags as text cells.

Bounds remain 8 queries/batch, 12 measures/query, 366 days, 1,000 series points,
5,000 returned rows, 2 MiB response, 10 seconds overall and 5 seconds/SQL statement.
Creator statistics refuse more than 10,000 creators. Historical composite reads
refuse more than 10,000 groups rather than approximating medians/tails. Tool
rankings return at most 100 names; totals cover all bounded groups before ranking.
Daily frequency reads share existing turn reads except hourly series, which need
a separate resolution. The SQL first-consumption search remains unfiltered;
calendar exclusions apply to resulting facts. No production capacity is inferred
from compilation, and SQL plans have not been exercised.

Missing historical facts are not manufactured: permanent agent creation history
would require the agent create/delete owner to emit future observations through an
agreed existing observation mechanism; publication first needs a catalogue lifecycle
contract and its producer. Permanent document-import history would require the
upload completion owner to retain/emit that fact beyond receipt purge. These are
explicit gaps, not an invitation to add a second journal in this analytics lot.
Adoption, visits, retention cohorts and membership-based adoption rates remain deferred.

#### Additional numerical acceptance scenario (Dimi; not executed)

On an explicitly authorized disposable fixture, use `[2026-01-01T00:00:00Z,
2026-01-04T00:00:00Z)` and the preceding three days. Team T includes project P.
Retain the earlier lot's three-turn/token fixture: Alice/S1/G on Jan 1 and Jan 2,
Bob/S2/H on Jan 2 with error; S2 was created before the window. The title on Jan 1
has consumption but no completed turn. Total token reports are 135 on Jan 1 and
90 on Jan 2 (190 input, 35 output, 45 cache read, 10 cache created overall).
A single prior-period turn on Dec 30 consumes 25 tokens. Include conspicuous
out-of-team and out-of-organization facts which must never contribute.

Also retain S3 created by Alice and S4 by Bob on Jan 2, with no turns. Thus S1/S3/S4
are the three current creations, while observed conversations remain S1/S2 only.
Create enabled G on Jan 1 and H on Jan 2. Keep four successful source drive import
receipts (one Jan 1, two Jan 2, one Jan 3), plus an attachment and a failed upload.
Observe five tool timers: one `ok` Jan 1; `error`, `awaiting_human`, `cancelled` and
resumed `ok` Jan 2. The separate error counter must not add another attempt.
Observe one user skill load Jan 1 and two agent skill loads Jan 2.

| Expected team result | All days | Weekends and holidays excluded |
| --- | ---: | ---: |
| Counted UTC dates | 3 | 1 (Jan 2) |
| Completed turns / active users / observed conversations | 3 / 2 / 2 | 2 / 2 / 2 |
| Failed turns / single-turn conversations | 1 / 1 | 1 / 2 |
| Failure rate / single-turn share | 0.333333 / 0.5 | 0.5 / 1 |
| Median usage days / normalized days per week | 1.5 / 1.5 | 1 / 1 |
| Mean daily active / daily usage share | 1 / 0.5 | 2 / 1 |
| Median turns per observed conversation | 1.5 | 1 |
| Retained creations / median per creator | 3 / 1.5 | 2 / 1 |
| Creator buckets 1, 2-3, 4-10, 11-30, 31+ | 1,1,0,0,0 | 2,0,0,0,0 |
| Top creator decile share | 0.666666 | 0.5 |
| Enabled agent stock / retained agents created | 2 / 2 | 2 / 1 |
| Agent publications | Not collected | Not collected |
| Imports with retained receipt | 4 | 2 |
| Tool attempts / success / failure / cancelled / waiting | 5 / 2 / 1 / 1 / 1 | 4 / 1 / 1 / 1 / 1 |
| Tool failure rate | 0.333333 | 0.5 |
| Skill loads user / agent | 1 / 2 | 0 / 2 |
| Input / output / total tokens | 190 / 35 / 225 | 80 / 10 / 90 |
| Cache read / cache created (not added again) | 45 / 10 | 5 / 0 |
| Daily token series | 135,90,0 | 0,90,0 |
| Daily completed-turn series | 1,2,0 | 0,2,0 |
| Previous tokens / completed turns | 25 / 1 | 25 / 1 |

Recompute costs/CO2e/energy from the included reports and existing factor catalogue;
compare per-agent/model sums where rankings are not truncated. The fixture's
selected agent created dates and SQL receipts are input facts, not permission for
this assistant to edit a database. These figures are an oracle, not executed results.

Additional acceptance obligations:

- Direct Owner/Analyst, editor/member/admin-only refusal, project-only scope,
  former members included, outside-organization refusal; revoke access before
  refresh/export and check no cached file or retained aggregate is shown as authorized.
- Pause/resume, thrown error, typed error, cancellation, local authority refusal,
  internal provider retry, similarly named tools, and absence of canonical placement.
  Verify one timer per boundary in ReAct/Deep/Graph; no trace/skill double-counting.
- Four calendar combinations, holiday/weekend overlap (Nov 1 2026), Easter Monday
  Apr 6, Ascension May 14, Whit Monday May 25, Dec 26 and Good Friday not excluded
  as national holidays; offset-bearing boundaries, UTC midnight, DST, partial days,
  leap day, previous window with a different holiday count, all days excluded.
- Title/first consumption on an excluded day and included HITL resume: include
  resume tokens but do not count a new recorded exchange. Export must match the same
  filters on each selected tab and announce stocks independently of the period.
- Delete S1: retained creations/distribution change, historical turns follow their
  own retention. Purge an imported document: its successful receipt and count go
  away. Remove G: current stock/retained creation change, historical usage follows
  its retained observations. No inference about a missing publication.
- Empty valid source vs missing source/mapping, missing user/session/outcome,
  failed shards/timeouts, >10,000 groups/creators, >100 ranked tools/agents and
  absent denominators. Exact totals must not be silently reduced to a top-N tail.
- FR/EN, keyboard/labels, narrow viewport; change account/organization/team/calendar
  during an in-flight read/export, decline after revocation, open Excel/LibreOffice,
  exact strings >2^53, blank missing values and formula-like labels stored as text.

Regression coverage: `analytics/{calendar,statistics,history,opensearch,mod}.rs`,
`tests/analytics_history.rs`, `tests/support/usage.rs`,
`TeamUsagePage/{teamAnalytics.test.ts,TeamUsagePage.test.tsx,collectiveUsage.test.tsx,exportTeamAnalytics.test.ts}`,
and `fred-runtime/tests/test_tool_observability_middleware.py`. Targeted validation
passed 12 Rust unit tests, four historical HTTP tests, one real three-shard
OpenSearch test (skills and tool attempts), 30 SQL usage regressions across the
initial run and corrective reruns, 35 frontend tests, 68 core KPI tests and 75 runtime
observability tests. PostgreSQL/pgvector and OpenSearch were disposable dedicated
containers, removed afterwards; the local OpenSearch fixture disabled disk allocation
thresholds because the host disk exceeded 90% usage. Full component quality and
browser/Excel reception remain with integration and Dimi. These checks establish
neither deployed reception nor exhaustive Swift parity.

### Personal activity (implementation; reception pending)

The three home counters and two rankings use the same POST service, without an
additional endpoint or preset. Scope is always the authenticated person AND the
currently authorized working organization. The UI keeps 7/30/90-day periods and
requests the preceding equal-duration `[since-duration,since)` window explicitly.
The window ends at observation time when entering the view or changing period;
it is not rounded down, so recently created conversations are included.
The retained-catalogue definition below is an accepted difference from Swift;
completed turns preserve Swift's event-count meaning, not a unique-message count.

| Indicator / measure | Persistent fact and reference date | Aggregation | Deletion / withdrawal |
| --- | --- | --- | --- |
| New retained conversations / `activity.retained_conversations` | SQL `session_metadata.created_at`, non-deleting session and space | Count creations in the period, self only, total only | Marking for deletion removes it immediately; purge does not change it again. Previous-period counts also use today's retained catalogue. |
| Messages sent / `activity.completed_turns` | Observed `agent.turn_completed`, event completion timestamp | Count events, including errors and HITL pause/resume executions | Retained historical observations survive independent session/agent deletion subject to history retention/erasure; losing organization access denies the read. |
| Agents used / `activity.agents_used` | Same events, stable instance UUID | Exact distinct UUIDs across the complete bounded read, total only | Homonyms remain distinct, renamed/deleted agents retain their identity. |
| Activity in teams/spaces / completed turns, `space` grouping | Same events at canonical execution placement; SQL current direct memberships | Count per currently joined team, project or personal space; retain zero rows, rank then limit | Withdrawn/deleting spaces disappear from this ranking; totals still cover the person's organization history. Projects are separate direct-membership spaces, not silently rolled into parent-team rights. |
| Most-used agents / completed turns, `agent` grouping | Same events and last observed name | Aggregate by UUID across all execution spaces, rank then limit | Deleted instances retain their observed name; space sublabel is the latest observed execution space. |

Retries without a completion event do not add a turn; retries that produce another
completion event count again, like Swift. There is no exchange-level deduplication.
Title generation emits a different metric and is excluded. `usage.recorded_exchanges`
remains unchanged and must not supply these counters. Both rankings sort by descending
count, then ascending UUID. `limit` is 1..100; home requests 5 and discloses `truncated`.
A distinct total never comes from the limited list. Integer strings remain `BigInt`
through UI formatting, comparison and bar scaling.

Final REST bodies for `POST /control-plane/v1/analytics/query`, using 7-day windows
(the UI substitutes the working organization's UUID and selected period):

```json
{"queries":[
  {"name":"current","scope":{"kind":"self","organization_id":"00000000-0000-0000-0000-000000000001"},"time":{"since":"2026-11-06T00:00:00Z","until":"2026-11-13T00:00:00Z","timezone":"UTC"},"measures":["activity.retained_conversations"]},
  {"name":"previous","scope":{"kind":"self","organization_id":"00000000-0000-0000-0000-000000000001"},"time":{"since":"2026-10-30T00:00:00Z","until":"2026-11-06T00:00:00Z","timezone":"UTC"},"measures":["activity.retained_conversations"]}
]}
```

```json
{"queries":[
  {"name":"current","scope":{"kind":"self","organization_id":"00000000-0000-0000-0000-000000000001"},"time":{"since":"2026-11-06T00:00:00Z","until":"2026-11-13T00:00:00Z","timezone":"UTC"},"measures":["activity.completed_turns","activity.agents_used"]},
  {"name":"previous","scope":{"kind":"self","organization_id":"00000000-0000-0000-0000-000000000001"},"time":{"since":"2026-10-30T00:00:00Z","until":"2026-11-06T00:00:00Z","timezone":"UTC"},"measures":["activity.completed_turns","activity.agents_used"]},
  {"name":"teams","scope":{"kind":"self","organization_id":"00000000-0000-0000-0000-000000000001"},"time":{"since":"2026-11-06T00:00:00Z","until":"2026-11-13T00:00:00Z","timezone":"UTC"},"measures":["activity.completed_turns"],"group_by":["space"],"limit":5},
  {"name":"agents","scope":{"kind":"self","organization_id":"00000000-0000-0000-0000-000000000001"},"time":{"since":"2026-11-06T00:00:00Z","until":"2026-11-13T00:00:00Z","timezone":"UTC"},"measures":["activity.completed_turns"],"group_by":["agent"],"limit":5}
]}
```

Service paths:

- `analytics::query_analytics -> plan -> execute -> sessions::usage::read::retained_conversations`:
  existing authorization, read-only SQL snapshot and timeouts; the catalogue's
  space/owner index bounds the owner scan, with creation time as a residual filter.
- `analytics::query_analytics -> plan -> history::execute -> Reader::completed_turns`:
  authorize all scopes and resolve organization spaces/current memberships in SQL,
  release the transaction, then read history once per scope/period. `turn_result`
  supplies totals and both rankings from that complete set. The adapter reuses the
  pooled HTTP client, mapping validation, deadline, byte and shard checks. Its
  composite `(space,instance)` read rejects more than 10,000 groups, missing UUIDs
  or counts inconsistent with exact matching hits; it does not return an approximate top-N.

`agent_app::_emit_turn_completed` now carries the trusted `space_id` on stream,
execute and evaluate paths. `team_id` alone cannot attribute personal spaces or
projects correctly. Old observations without canonical placement cannot be recovered
by this change and are excluded: no cross-organization fallback or index mutation
is performed. History can also omit observations from producers that do not emit
this metric (including the embedded Rust agent). Collection remains explicitly
unknown; zero means no matching observed events, not proof of no activity. The UI
states this limitation for figures and comparisons. Missing source/mapping or partial
source responses yield unavailable, not a successful empty list.

`HomePage::ActivityTab` owns the two generated-client subscriptions. Arguments bind
session identity, organization and membership snapshot; `currentData` hides old
organization/account replies. Current Weaver memberships supply names/roles only;
server authorization and membership selection precede ranking. Shared cards, initials,
bars and FR/EN translations remain; absent comparison data never produces a stable
badge. The obsolete five handwritten legacy hook aliases are removed. The frozen
legacy generated client remains for unmigrated dashboards (its source snapshot is
not present here); it is not manually edited. Recent agents, cleanup, trends and
the existing consumption/impact subscriptions are unchanged.

Added regression sources cover canonical project/personal/HITL emission, SQL deletion
and adjacent windows, Acme/Globex and revocation, shared historical reads, exact counts,
homonyms, membership filtering before limits, late UI responses and unavailable/empty
states. Execution of tests and code-quality remains assigned to Dimi; these additions
are not a claim of passing tests or deployed reception.

### Developer diagnostic tracing

Select `observability.tracer: diagnostic` with
`observability.diagnostic.collector_endpoint` in the service YAML. The default
keeps diagnostic export off. The [SDK guide](../../libs/fred-rust-sdk/README.md)
describes the fixed request-based sampling and bounded technical export; the
[bench guide](../../developer_tools/benchmarks/README.md) describes collection.
This is an experimental developer facility; a sampled request context carries
no authority and does not certify bench as its sender.
