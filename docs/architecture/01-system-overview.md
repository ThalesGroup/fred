# 1. System overview

Fred combines platform governance, organization/team/project spaces and document
processing. The Rust control-plane owns admission, authorization and document state;
Knowledge Flow executes document processing. The existing frontend exposes the
implemented journeys without redefining their business behavior.

## Current local deployment

The profile in `deploy/k3d/helmfile.yaml.gotmpl` deploys three applications:

| Deployment | Responsibility |
| --- | --- |
| `control-plane-backend` | `control-plane serve`: HTTP API, storage cleanup, processing dispatcher and lifecycle tasks in one supervised process |
| `knowledge-flow-worker` | Document processing through Temporal; no Knowledge Flow HTTP API |
| `frontend` | Shared Fred UI, authenticated calls through `/control-plane/v1` |

The profile disables the separate control-plane worker, Knowledge Flow API and
agent runtime. PostgreSQL, OpenFGA, Keycloak, Temporal, SeaweedFS and OpenSearch
belong to the infrastructure release. Application deployment does not recreate them.

## Data ownership

PostgreSQL owns document placement, processing receipts and publication state.
OpenFGA owns authorization relations. Object storage owns original and derived
bytes; the configured vector index holds processing outputs. The index name is a
deployment setting, independent of the component name. It is not an authorization
boundary by itself.

See [document storage](05-documents.md), [runtime](A1-manager-runtime.md) and
[operations](08-operations.md) for the implemented contracts.
