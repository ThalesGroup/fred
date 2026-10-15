## Why

Any workload holding `service_agent` can publish a Knowledge Base definition, and every
workload holds it (fred-agents, the evaluation worker, any agent pod). The first one to
publish under a free prefix owns it for good: trust on first use, with no rebinding path.
Nothing reaches a team without a platform admin enabling it, so the exposure is a
polluted catalog and a prefix squatted out of its owner's reach, but the gate does not
follow least privilege or deny by default.

Tracking: https://github.com/ThalesGroup/fred/issues/3104

## What Changes

- The Control Plane configuration gains `knowledge_bases.publishers`: the clients allowed
  to publish Knowledge Base definitions, each with the prefix it owns. Empty by default:
  nobody publishes.
- `PUT /knowledge-bases/definitions/{name}` refuses a client that is not listed, or a
  declaration outside the client's listed prefix, with a message naming the setting.
  Prefix ownership is assigned by the operator rather than claimed by the first caller.
- The rest of publication is unchanged: the image still publishes its own declaration,
  a user session is still refused, a platform admin still enables each definition per team.
- Fred's k3d values and local configurations list the samples' client
  (`kb-fred.samples`, prefix `fred.samples`), and `local-dev` where security is off.
- **BREAKING** at upgrade for a deployment that runs Knowledge Bases: its clients must be
  listed first, or their next publication is refused.
- Out of this change: what a published pod may write (one client per definition,
  `KNOWLEDGE-BASE.md` §4), and definitions already stored for a client that will not be
  listed (the migration note asks operators to review the catalog).

## Capabilities

### New Capabilities

- `knowledge-base-publication`: who may declare a Knowledge Base to Fred, under which
  prefix, and how a refusal reads.

### Modified Capabilities

None.

## Impact

- Control Plane: `config/models.py` (`KnowledgeBasesConfig`), `knowledge_bases/service.py`
  (`publish_definition`), tests; the generated configuration schema and the fred chart's
  values schema.
- Configuration: `apps/control-plane-backend/config/configuration*.yaml`,
  `deploy/k3d/values.yaml`; the fred chart's `values.yaml` documents the setting.
- Docs: `docs/swift/design/KNOWLEDGE-BASE.md` (§3, §4), the publication row of
  `docs/swift/platform/authz-endpoint-matrix.yaml`, a migration note with `operations` impact.
- Knowledge Base pods: no code change; an unlisted client now fails at `publish`.
