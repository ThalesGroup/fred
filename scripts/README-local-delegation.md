# Local delegation with deployment-factory

Start with the [native development prerequisites](../README.md#option-2-native-mode-ie-install-everything-locally)
and prepare the app `.env` files, including model-provider credentials. Use matching
Fred and deployment-factory branches containing this setup. No secrets or generated
service-account identities belong in Git.

After `make docker-up` in deployment-factory, prepare Fred once per fresh Keycloak realm:

```bash
# From the Fred repository, with dependencies and config/.env already prepared:
make delegation
```

All three applications must select `CONFIG_FILE=./config/configuration_prod.yaml`
in their existing `config/.env`. The helper uses the agentic workload credentials
already configured there, not Keycloak admin credentials. Before writing anything
it verifies that the workload token carries the `delegation_caller` role of the
`fred-delegation` client, the `fred-delegation` audience and a realm issuer; the
deployment-factory post-install step grants that role to `agentic`. Neither tokens
nor secrets are saved.

The generated `apps/*/config/.delegation.local.json` files are ignored by Git.
`make run` and `make run-worker` explicitly pass them to the shared loader through
`FRED_LOCAL_DELEGATION_FILE`; production entrypoints do not discover these files.
The files only switch on one direction of each application's own
`security.delegation` block: `act_for_people` for Fred Agents, which calls the
others for a person, and `accept_delegated_calls` for Control Plane and Knowledge
Flow, which believe those calls. Every other delegation setting is read from the
selected YAML. A file whose issuer is not a realm address of the selected
configuration, or whose token lacked the delegation audience, is rejected.

Start Control Plane first (`make run` in `apps/control-plane-backend`), then the
remaining APIs, workers and frontend using their usual make commands. The Knowledge
Flow worker respects `CONFIG_FILE`, and its local metrics port defaults to 9112 to
avoid the API's port 9111. Control Plane's `run-worker` selects its dedicated
`configuration_worker.yaml`.

For an empty deployment, bootstrap your platform admin using Control Plane's
`make bootstrap-local` instructions. Before importing the demo bundle, run
`local-testing/demo/seed-keycloak-users.sh` in deployment-factory to create the demo
identities. Import the bundle via **Admin > Migration**, then enable the required
capabilities via **Admin > Capabilities**.

Rerun the helper after recreating the realm/service account or changing a
delegation audience, role or claim path in the YAML; ordinary Fred restarts reuse
the generated settings. `make delegation ARGS=--dry-run` checks without writing;
`make delegation ARGS=--reset` removes
the generated files without editing tracked YAML. Reset returns to the YAML's own
delegation settings, it does not force delegation off. Deployments turn on
`act_for_people` for the agents runtime and `accept_delegated_calls` for the
receivers in their own configuration, and grant the role in their own realm.

The local prod profiles use `security.profile: c3` and the same canonical issuer
`http://localhost:8080/realms/app` for browser and workload tokens. These profiles
are for applications running on the host above Docker infrastructure. A deployed
pod must use its deployment's canonical realm URL, not its own localhost. Changing
the issuer requires regenerating local delegation and restarting the applications.

The Docker Keycloak post-install step explicitly includes `app` in user token
audiences, matching `security.user.client_id`. After updating an existing realm,
sign in again to replace previously issued tokens; `azp=app` alone is insufficient.

## Start the six components

Run each command in a separate terminal from the Fred repository root, after
preparing the existing per-app `.env` files and installing the usual dependencies:

```bash
make -C apps/control-plane-backend run
make -C apps/control-plane-backend run-worker
make -C apps/knowledge-flow-backend run
make -C apps/knowledge-flow-backend run-worker
make -C apps/fred-agents run
make -C apps/frontend run
```

Open http://localhost:5173. API ports are 8222 (Control Plane), 8111 (Knowledge
Flow) and 8000 (Fred Agents). Workers must report Temporal polling readiness.
The evaluator and sample/MCP servers are optional separate services.

## Verify and troubleshoot

After bootstrap and demo provisioning, `make validation-report` runs the live
authorization suite and writes `validation/report.md`. It creates disposable
resources: use a local test stack. This does not test token renewal over time.
A short chat should emit `delegated_run_admitted` in Fred Agents and
`delegation.grant.accepted` in the receivers. Never print bearer tokens to debug.

| Symptom | Check / correction |
| --- | --- |
| Issuer mismatch | Use the same canonical realm URL for user and M2M authentication; rerun `make delegation`, restart Fred. |
| C3 rejects a fresh user token | Verify `aud` contains `app`; `azp` is not an audience. Update deployment-factory and rerun its Docker Keycloak post-install script, then sign in again. |
| Workload rejected | Run `make delegation ARGS=--dry-run`; fix the reported client secret, caller role, issuer or audience where it is owned. |
| Recreated Keycloak | Rerun the deployment-factory post-install step if the role is missing, then `make delegation`, and restart Fred. |
| Direct OpenAI-compatible endpoint unavailable | This local C3 profile disables `openai_compat`; use the managed chat UI. |
| Evaluation proxy refuses port 8336 | The optional evaluator is not running; this does not prove delegation failed. |

For an existing Docker realm, the audience repair and the delegation caller role are
applied without restarting Docker or recreating data:

```bash
# From fred-deployment-factory; requires its local Keycloak admin credentials:
KEYCLOAK_FORCE_RELOGIN=false bash docker/keycloak/keycloak-post-install.sh
```

This is infrastructure provisioning, separate from Fred's `make delegation`,
which requires only workload credentials. Existing browser tokens remain
unchanged until refreshed or replaced by signing in again.

The shared assistant skill lives in `.claude/skills/fred/SKILL.md` (also exposed
through `.agents/skills`). If a personal `$fred` installation shadows it, update
that copy from this file; do not maintain a different startup procedure.

## Accelerate browser-token renewal tests

From the matching deployment-factory checkout, with local Docker already running:

```bash
make keycloak-token-status
make keycloak-token-short   # app: 60 seconds; agentic M2M: 120 seconds
# Sign out/in, send a message, wait 90 seconds without reload, send another.
make keycloak-token-normal  # app and agentic M2M: standard 300 seconds
```

These commands administer only the local Docker `app` and `agentic` clients.
They do not change other clients, refresh tokens, session timeouts or delegation grants.
Only newly issued tokens receive the new lifetime. The setting persists across
Fred restarts: explicitly restore normal mode when finished. Normal mode sets
300 seconds; it does not restore an arbitrary earlier custom value.

For a long-agent test, perform an authenticated tool call after the initial user
token expires. A successful short chat alone does not prove renewal, and this
setting accelerates agentic workload-token renewal too. Existing cached M2M tokens
keep their original expiry: restart Fred Agents or wait for that expiry before
testing. Run the agent for more than two minutes with a protected call afterwards.
Observe fresh browser token issuance
in the browser network panel without copying token contents into logs or reports.

For backend authentication dashboards and troubleshooting, use the
[operator guide](../docs/swift/platform/OBSERVABILITY-AND-AUDIT.md#using-the-dashboard).
It covers local Grafana startup, scrape targets and distinguishing initial token
acquisition from renewal. Browser console events are not central Grafana metrics.
