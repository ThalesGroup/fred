# 10. Risks and open points

| Point | Why it matters | Next |
| --- | --- | --- |
| The UI does not talk to fred-manager yet | Nothing user-visible uses the new model | Decide how the UI relies on it, topic by topic |
| No OpenAPI from the code | The UI's client is generated from OpenAPI in fred | Generate it from the handlers (utoipa) before the first UI route |
| Self-grant of a content role by a space admin | Undermines D7 in practice | Decide the rule |
| Admission gates not ported | GCU, account status, platform access, whitelist and delegation are not enforced | Port each when its topic arrives |
| Source upload, worker, search | Ingestion stops at submission | Ingestion step: adapt the worker to `IngestDocument`, order deletion against a running ingestion, test submission against Temporal |
| Not in root `make test` / CI | Rust checks run only locally | Rust and protoc in the CI images |
| Not in fred's chart and schema | Schema workaround in `deploy/k3d/chart` | Add fred-manager to chart values and schema |
| Space deletion | Not built | Decide with the provisioning model |

Next planned step: import a provisioning bundle (`users.json` with an organization),
first from the command line, with fred-manager's own Keycloak service account.
