# Fred log integration and detection scenarios for a SIEM

This guide is for teams collecting logs from a Fred installation on virtual machines with Podman Compose. Container output reaches journald, a syslog relay, a collection agent, and then the SIEM. This document identifies the sources, fields, and initial security detection scenarios. The SIEM team owns the queries, correlation windows, alert routing, and tuning.

Fred emits **events**, not SIEM alerts or executable rules. Translate each scenario below into the selected SIEM's query language.

```text
Microsoft Entra ID ---------------------> SIEM
Podman VM -> journald -> syslog -> agent -> SIEM -> rules -> alerts
HTTP ingress / WAF ---------------------> SIEM
```

## 1. Sources and ownership

| Source | Useful events | Collection route | Source owner |
| --- | --- | --- | --- |
| `fred.security.audit` | Permission changes, platform access, delegation, runtime admission, tool invocations | Fred container JSON on stdout, then journald and the syslog relay to the agent | Fred operator emits; SIEM operator collects |
| Fred application logs | HTTP responses, authorization denials, errors, diagnostics | Container output, journald, syslog relay; set `app.log_format: json` on each relevant backend and worker | Fred operator |
| HTTP ingress / proxy | Method, route, status, volume, and, where supported, source IP and WAF decisions | Ingress logs to the agent, through syslog if that is the selected route | Ingress operator |
| Microsoft Entra ID | Interactive and non-interactive user sign-ins, service principal sign-ins, directory changes | Entra diagnostic settings to a destination selected by the SIEM operator, such as Event Hubs | Entra administrator and SIEM operator |
| VM and Podman | Stops, restarts, collector errors, missing flows | Host logs and collector monitoring | VM operator |

Fred writes audit events to stdout as JSON with `logger=fred.security.audit`. They are excluded from Fred's application log store. **Do not rely on Fred's OpenSearch application log index to retrieve audit events.** Durable delivery, retention, and tamper protection belong in the collection infrastructure. See [Observability and Audit](OBSERVABILITY-AND-AUDIT.md#5-stream-3--security--audit-trail).

Fred's direct Entra configuration is documented in [Identity providers](IDENTITY-PROVIDERS.md#microsoft-entra-id-recipe). Entra is the authentication source; Fred application roles and permissions remain in OpenFGA. An Entra sign-in does not prove a Fred role grant, and a Fred audit event does not prove a successful Entra sign-in.

Compared with Keycloak, the SIEM collects no Keycloak source. Human and confidential client sign-ins come from Entra. Entra directory audit records tenant configuration changes; Fred audit records Fred permission changes. A verified identity mapping is needed to join the two. Fred's audit format and VM collection route do not change.

### Entra feeds to request

Export at least interactive user sign-ins, non-interactive user sign-ins, service principal sign-ins, and directory audit logs. Add managed identity sign-ins if used. Check available categories, permissions, licensing, and export destination with the tenant administrator. Microsoft documents the [exportable categories](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/concept-diagnostic-settings-logs-options) and [access routes](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/howto-access-activity-logs), including diagnostic settings to Event Hubs and Microsoft Graph.

Filter Entra events by the application IDs of the Fred UI, API, and confidential clients. A service principal sign-in represents an application authentication, not a human sign-in. Tune its thresholds separately.

## 2. VM collection contract

1. Verify `container -> Podman -> journald -> syslog relay -> agent -> SIEM`. Check the container log driver with `podman info --format '{{ .Host.LogDriver }}'` and `podman inspect`. Podman does not list `syslog` as a native container log driver. This deployment uses `journald`, followed by a VM syslog relay. Validate both steps against the deployed version and configuration. The global `podman --syslog` option logs Podman messages; it does not forward container stdout and stderr. See the [container log driver documentation](https://docs.podman.io/en/latest/markdown/podman-run.1.html) and [`podman --syslog`](https://docs.podman.io/en/latest/markdown/podman.1.html).
2. Forward stdout and stderr from all backends, workers, agent runtimes, the frontend, and the proxy. Extract Fred JSON from the syslog message while retaining the syslog envelope and original audit JSON. Add host, container, service, environment, and receive time as separate fields. Check maximum message size, splitting, and encoding for long JSON events.
3. Route decoded JSON by its structured `logger` field, not the text of `msg` or the syslog prefix. Give `fred.security.audit` a destination and access policy appropriate for security evidence. Keep higher-volume application logs separate. Avoid duplicate ingestion through multiple routes.
4. Provide a bounded local queue and retry after relay or SIEM interruption, a disk-space limit, and an alert on collector failure or silence. Check restarts, Podman journal rotation, and the selected syslog transport. Measure loss and emission-to-ingestion delay.
5. Use authenticated, encrypted transport when logs leave the VM. Set retention and access controls under the local security policy. Keep tokens, authorization headers, signed URLs, HTTP bodies, user messages, and document content out of events.

The frontend's JSON access logs do not include the raw path or client IP. Native diagnostics on stderr can contain free text and need separate privacy handling. Use ingress logs for scans, WAF decisions, and network source information. See [Observability and Audit](OBSERVABILITY-AND-AUDIT.md#63-frontend-pod-logs).

## 3. Minimum normalization

| Meaning | Fred audit | Fred application log | Entra / HTTP ingress |
| --- | --- | --- | --- |
| Event time | `ts` (Unix seconds) | `timestamp` or producer event time | Source event time |
| Origin | `service`, `logger` | `service`, `logger`, `role` when present | Tenant, application, host, or proxy |
| Action | `extra.audit_event` | `message`, `route`, `http_method`, or `denial_cause`, depending on the event | Source operation type |
| Result | `extra.outcome`, `extra.reason` when present | `outcome`, `http_status`, `denial_cause` when present | Sign-in or decision status |
| Actor and target | `extra.actor_uid`, `extra.user_id`, `extra.subject`, `extra.resource`, `extra.team_id`, or `extra.link_id`, depending on the event | `user_id` and permitted references when present | User, application, or service principal ID |
| Correlation | Explicitly emitted `extra.*` fields | `request_id`, `correlation_id` when present | Entra or proxy identifiers |

With the current Entra recipe, Fred uses the access token's `oid` claim as the user identifier. A non-UUID identifier is converted to UUIDv5 using its issuer and value. Validate the Entra `oid` to Fred `user_id` mapping with a test account in the same tenant, and include tenant and target application in the join key. Entra and Fred correlation IDs are generated independently: **do not treat them as a shared request ID**. If identity is missing, retain the event without inventing an actor.

## 4. Initial detection catalog

The windows and thresholds below are starting points to tune against local traffic. Retain individual administrative events even when they do not raise an alert.

| ID | Priority | Proposed rule | Sources | Availability and limits |
| --- | --- | --- | --- | --- |
| D01 | High | Any `platform_admin` grant on `organization:fred`; other administrative relations according to the local role matrix | `authz.relation.granted` | Available now. `actor_uid` can be absent; identify the target with `subject`. |
| D02 | High | A privileged grant followed within 30 minutes by a policy change or administrative action by the target | Relation audit + `platform.access.*` | Join on Fred user ID when both events carry it. |
| D03 | High | `platform.access.filtering.updated` with `filtering_enabled=false`, or any policy change or platform access exception | `platform.access.filtering.updated`, `platform.access.policy.updated`, `platform.access.user.granted`, `platform.access.users.granted`, `platform.access.team.updated` | Available now. Policy audit gives the revision, not its content; investigate the authorized state separately. |
| D04 | High | A secret or certificate added, an application permission or consent changed, or an access policy changed for a Fred application | Entra directory audit | Exact operation names and fields depend on the Entra export; filter by registered application IDs. |
| D05 | High | Several failed Entra sign-ins, then success for the same account, then a D01-D04 action | Entra sign-ins + Fred and Entra audit | Requires Entra export and a validated `oid`/tenant join. Do not count silent token renewal as a new interactive login. |
| D06 | Medium | One origin tries several accounts, or one account fails from several origins, in a short window | Entra sign-ins | Requires Entra IP and status. Tune thresholds and account for shared proxy/VPN IPs. |
| D07 | Medium | Failed or newly sourced sign-ins for a Fred confidential client | Entra service principal sign-ins | Correlate by application, status, and IP. Entra may aggregate events; inspect timestamps and counts first. |
| D08 | Medium | Repeated attempts to access another user's session or other denied resources | `session_owner_mismatch`, diagnostics with `denial_cause=permission_refused` | Session denial is explicit. With delegation enabled, its audit loses identifiers; generic denials may also lack usable identity. |
| D09 | Medium | Multiple rejected delegated grants, especially `caller_not_trusted` or `caller_not_allowed` | `delegation.grant.rejected` | Count by service and reason. This audit does not identify a user or IP by itself. |
| D10 | Medium | A Free link reveal followed by enrollments, or regeneration of a team join link followed by unusual joins | `platform.access.link.revealed`, `platform.access.free.enrolled`, `team.join_link.regenerated`, `team.join_link.joined` | Join Free events on `link_id`. A team link regeneration carries only `team_id`; correlate at that level. |
| D11 | Medium | A spike of 401/403/404/5xx for one route or origin, near WAF blocks or application errors | HTTP ingress + Fred logs | Ingress supplies IP and path; Fred supplies bounded route and result. A burst alone does not prove intrusion. |
| D12 | Investigate | Rare tool invocation, large volume increase, or repeated failures for an account or team | `agent.tool.invocation.started` and `.completed` | Identity and tool name may be absent with delegation settings. No document content or exfiltration destination is logged. |

Do not claim reliable detection of document exfiltration, revocation of every OpenFGA relation, or attribution of a delegated attempt to an IP. These cases need a source inventory and potentially new bounded events. Today `authz.relation.revoked` is emitted for platform-role revocation, while the central relation-write path audits grants. Runtime and delegation events can contain only event, result, and reason when delegation is enabled. See [Observability and Audit](OBSERVABILITY-AND-AUDIT.md#5-stream-3--security--audit-trail).

For D01, translate the specification into a native SIEM query: select `logger=fred.security.audit`, `extra.audit_event=authz.relation.granted`, `extra.resource=organization:fred`, and `extra.relation=platform_admin`. Alert on each match with `subject`, `actor_uid`, `service`, and `ts`. Import format, query syntax, and notification policy depend on the SIEM. Other catalog entries use the same process, with time-window aggregation where specified.

## 5. Real development log chains

These lines were captured on 4 November 2026 from a running local Fred Control Plane and Keycloak development stack. They are copied from the producer logs, with no synthesized fields or syslog envelope. This development Control Plane uses text application logging; the VM deployment should use JSON application logging as described above. Keycloak appears here only to make the example reproducible locally. In the target deployment, use Entra sign-in events for D05-D07.

<details>
<summary>Failed sign-ins: attempts for alice and admin in the Keycloak development realm</summary>

```text
2026-11-04 08:28:15,168 WARN  [org.keycloak.events] (executor-thread-5) type="LOGIN_ERROR", realmId="b0557f70-80bf-407f-9947-cb7c538105c2", realmName="app", clientId="app", userId="null", ipAddress="172.18.0.1", error="user_not_found", auth_method="openid-connect", grant_type="password", client_auth_method="client-secret", username="alice"
2026-11-04 08:28:15,210 WARN  [org.keycloak.events] (executor-thread-5) type="LOGIN_ERROR", realmId="b0557f70-80bf-407f-9947-cb7c538105c2", realmName="app", clientId="app", userId="null", ipAddress="172.18.0.1", error="user_not_found", auth_method="openid-connect", grant_type="password", client_auth_method="client-secret", username="admin"
2026-11-04 08:28:40,476 WARN  [org.keycloak.events] (executor-thread-5) type="LOGIN_ERROR", realmId="b0557f70-80bf-407f-9947-cb7c538105c2", realmName="app", clientId="app", userId="null", ipAddress="172.18.0.1", error="user_not_found", auth_method="openid-connect", grant_type="password", client_auth_method="client-secret", username="alice"
2026-11-04 08:28:40,514 WARN  [org.keycloak.events] (executor-thread-5) type="LOGIN_ERROR", realmId="b0557f70-80bf-407f-9947-cb7c538105c2", realmName="app", clientId="app", userId="null", ipAddress="172.18.0.1", error="user_not_found", auth_method="openid-connect", grant_type="password", client_auth_method="client-secret", username="admin"
```

The attempted usernames, client, realm, source IP, and rejection reason are visible. Because `userId="null"` and the reason is `user_not_found`, these events cannot establish that either account exists. The two usernames share the same source IP and recur within 25 seconds, making them useful inputs for D06 after local threshold tuning.

</details>

<details>
<summary>Denied administrative API request: Fred authentication warning and HTTP completion</summary>

```text
2026-11-04T08:33:47+00:00 WARNING control-plane/fred_core.security.oidc No Bearer token provided on secured endpoint correlation_id=1b188ae9-63b9-4383-8630-312ac4e9b5be request_id=d541e93e-67d1-4728-93cd-0d27388774c7
2026-11-04T08:33:47+00:00 WARNING control-plane/http GET /admin/platform/access/users → 401 | 82ms http_method=GET duration_ms=81.80919800361153 outcome=responded route=/admin/platform/access/users http_status=401 correlation_id=1b188ae9-63b9-4383-8630-312ac4e9b5be request_id=d541e93e-67d1-4728-93cd-0d27388774c7
```

The matching `correlation_id` and `request_id` show that the warning and 401 response belong to one request. No user identity is available because the request had no bearer token. The Fred route is bounded; obtain the client IP from the ingress log when implementing D11.

</details>

## 6. Validation and acceptance

In a representative test environment, perform permitted and denied actions with test accounts: a successful and failed Entra sign-in, a confidential client sign-in, a role grant and revocation, an access-policy change, another user's session access attempt, a rejected delegated grant, and a test tool invocation.

For each action, verify in the SIEM that the raw event is searchable; the syslog envelope and JSON survive; source and timestamp are correct; normalized fields have the expected types; content and credentials are absent; the event is not duplicated; delivery is timely; and the rule triggers or intentionally stays silent. Interrupt the relay or destination and restart a container to test recovery, queue limits, and collection alerts. Measure alert volume on normal traffic before enabling operational notifications.

Before go-live, the SIEM operator confirms the actual relay and syslog format, transport to the agent, Entra tenant access and exported categories, Fred application IDs, retention, audit access separation, thresholds and windows, maintenance windows, alert recipients, and investigation procedure. The Fred operator supplies versions, service names, and test scenarios. The security team owns SIEM rules and ongoing tuning.
