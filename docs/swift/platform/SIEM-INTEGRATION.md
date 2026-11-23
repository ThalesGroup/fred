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

The following events were observed on 5 November 2026 in a running local Fred stack. Two test accounts were created: `siem_admin_20261105` (`07f3fafe-39f5-4115-8baf-baa84e055607`) and `siem_analyst_20261105` (`8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1`). A dedicated development client `siem-workload-20261105` was also used. Fred lines are copied verbatim from process stdout. Keycloak failure lines are copied verbatim from container stdout; successful and administrative Keycloak event objects were retrieved through its Admin REST API and serialized as compact JSON without changing their fields. No syslog envelope or SIEM record is shown because neither was used in this local capture. Expand each scenario to inspect its source events.

Keycloak is a development analogue only. D04-D07 require Microsoft Entra ID directory audit, user sign-in, and service principal sign-in exports in the target deployment. These Keycloak events do not establish that Entra emits identical names or fields. The local Docker address `172.18.0.1` is a development origin, not an Internet client IP.

<details>
<summary>D01 - Platform administrator grant</summary>

`siem_admin_20261105` bootstrapped the isolated Fred test organization and received `platform_admin`. The target is in `subject`; `actor_uid` identifies the initiating account.

Fred Control Plane audit stdout

```json
{"ts": 1793858408.934622, "level": "INFO", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "control-plane", "msg": "[SECURITY] authz.relation.granted", "extra": {"audit_event": "authz.relation.granted", "actor_uid": "07f3fafe-39f5-4115-8baf-baa84e055607", "subject": "user:07f3fafe-39f5-4115-8baf-baa84e055607", "relation": "platform_admin", "resource": "organization:fred"}}
```

</details>

<details>
<summary>D02 - Privileged grant followed by a policy change</summary>

`siem_admin_20261105` granted `platform_access_manager` to `siem_analyst_20261105`. The analyst then changed the platform access policy. The grant target in `subject` matches the policy change `actor_uid`; the audit events themselves have no shared request ID.

Fred Control Plane audit stdout

```json
{"ts": 1793858502.129384, "level": "INFO", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "control-plane", "msg": "[SECURITY] authz.relation.granted", "extra": {"audit_event": "authz.relation.granted", "actor_uid": "07f3fafe-39f5-4115-8baf-baa84e055607", "subject": "user:8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", "relation": "platform_access_manager", "resource": "organization:fred"}}
{"ts": 1793858502.1750476, "level": "INFO", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "control-plane", "msg": "[SECURITY] platform.access.policy.updated", "extra": {"audit_event": "platform.access.policy.updated", "actor_uid": "8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", "revision": 1}}
```

</details>

<details>
<summary>D03 - Platform access filtering disabled</summary>

`siem_analyst_20261105` first enabled, then disabled platform access filtering. The second event is the high-priority detection input; `revision` does not contain the policy body.

Fred Control Plane audit stdout

```json
{"ts": 1793858517.6366093, "level": "INFO", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "control-plane", "msg": "[SECURITY] platform.access.filtering.updated", "extra": {"audit_event": "platform.access.filtering.updated", "actor_uid": "8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", "filtering_enabled": true, "revision": 1}}
{"ts": 1793858526.2727935, "level": "INFO", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "control-plane", "msg": "[SECURITY] platform.access.filtering.updated", "extra": {"audit_event": "platform.access.filtering.updated", "actor_uid": "8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", "filtering_enabled": false, "revision": 1}}
```

</details>

<details>
<summary>D04 - Development identity client created and secret rotated</summary>

The Keycloak development administrator created `siem-workload-20261105` and rotated its secret. The event refers to the internal client UUID; the client name was verified when the test client was created. In production, correlate the corresponding Entra directory audit events with Fred application and service principal IDs. Keycloak Admin REST events are not part of the Fred VM stdout forwarding route.

Keycloak Admin REST `admin-events` response objects

```json
{"id":"8e238b2d-f9d2-49fe-ab1b-d5782921a56a","time":1793858605221,"realmId":"b0557f70-80bf-407f-9947-cb7c538105c2","authDetails":{"realmId":"4978e402-a173-4b91-9d23-62d10e81a42a","clientId":"8f3155a2-3ed2-4438-9dc3-63dc6c1b3c08","userId":"40344204-c64d-452a-a48f-3bf776c4a5ce","ipAddress":"172.18.0.1"},"operationType":"CREATE","resourceType":"CLIENT","resourcePath":"clients/240a2019-0577-48dd-beeb-614d75c459fe"}
{"id":"efe3fb5a-c6f2-47eb-a0c6-2daf75864609","time":1793858605268,"realmId":"b0557f70-80bf-407f-9947-cb7c538105c2","authDetails":{"realmId":"4978e402-a173-4b91-9d23-62d10e81a42a","clientId":"8f3155a2-3ed2-4438-9dc3-63dc6c1b3c08","userId":"40344204-c64d-452a-a48f-3bf776c4a5ce","ipAddress":"172.18.0.1"},"operationType":"ACTION","resourceType":"CLIENT","resourcePath":"clients/240a2019-0577-48dd-beeb-614d75c459fe/client-secret"}
```

</details>

<details>
<summary>D05 - Failed sign-ins, success, then administrative action</summary>

`siem_analyst_20261105` submitted a wrong password twice, then signed in successfully and changed the access policy. The Keycloak `userId` matches the Fred `actor_uid`. The local password-grant flow is only a development test; production should distinguish interactive sign-ins from non-interactive token activity in Entra.

Keycloak container stdout - failed sign-ins

```text
2026-11-05 06:03:43,483 WARN  [org.keycloak.events] (executor-thread-1) type="LOGIN_ERROR", realmId="b0557f70-80bf-407f-9947-cb7c538105c2", realmName="app", clientId="app", userId="8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", ipAddress="172.18.0.1", error="invalid_user_credentials", auth_method="openid-connect", grant_type="password", client_auth_method="client-secret", username="siem_analyst_20261105"
2026-11-05 06:03:43,542 WARN  [org.keycloak.events] (executor-thread-1) type="LOGIN_ERROR", realmId="b0557f70-80bf-407f-9947-cb7c538105c2", realmName="app", clientId="app", userId="8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", ipAddress="172.18.0.1", error="invalid_user_credentials", auth_method="openid-connect", grant_type="password", client_auth_method="client-secret", username="siem_analyst_20261105"
```

Keycloak Admin REST `events` response object - successful sign-in

```json
{"id":"86e5e261-6c26-49d2-9e23-cd5978f8f2c6","time":1793858623571,"type":"LOGIN","realmId":"b0557f70-80bf-407f-9947-cb7c538105c2","clientId":"app","userId":"8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1","sessionId":"c6469772-c939-4627-a9f9-6210206cf94d","ipAddress":"172.18.0.1","details":{"auth_method":"openid-connect","token_id":"onrtro:0a481d41-5976-5fb6-b306-cbb541535524","grant_type":"password","refresh_token_type":"Refresh","scope":"profile email","refresh_token_id":"66210804-010d-46f1-bcb2-510fd6269980","client_auth_method":"client-secret","username":"siem_analyst_20261105"}}
```

Fred Control Plane audit stdout - subsequent action

```json
{"ts": 1793858623.6146283, "level": "INFO", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "control-plane", "msg": "[SECURITY] platform.access.policy.updated", "extra": {"audit_event": "platform.access.policy.updated", "actor_uid": "8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", "revision": 2}}
```

</details>

<details>
<summary>D06 - One development origin tries two accounts</summary>

The same development origin attempted both named accounts within 60 ms. These are three observations, not a suggested production threshold. Shared VPN and proxy addresses require threshold tuning.

Keycloak container stdout

```text
2026-11-05 06:03:43,483 WARN  [org.keycloak.events] (executor-thread-1) type="LOGIN_ERROR", realmId="b0557f70-80bf-407f-9947-cb7c538105c2", realmName="app", clientId="app", userId="8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", ipAddress="172.18.0.1", error="invalid_user_credentials", auth_method="openid-connect", grant_type="password", client_auth_method="client-secret", username="siem_analyst_20261105"
2026-11-05 06:03:43,518 WARN  [org.keycloak.events] (executor-thread-1) type="LOGIN_ERROR", realmId="b0557f70-80bf-407f-9947-cb7c538105c2", realmName="app", clientId="app", userId="07f3fafe-39f5-4115-8baf-baa84e055607", ipAddress="172.18.0.1", error="invalid_user_credentials", auth_method="openid-connect", grant_type="password", client_auth_method="client-secret", username="siem_admin_20261105"
2026-11-05 06:03:43,542 WARN  [org.keycloak.events] (executor-thread-1) type="LOGIN_ERROR", realmId="b0557f70-80bf-407f-9947-cb7c538105c2", realmName="app", clientId="app", userId="8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", ipAddress="172.18.0.1", error="invalid_user_credentials", auth_method="openid-connect", grant_type="password", client_auth_method="client-secret", username="siem_analyst_20261105"
```

</details>

<details>
<summary>D07 - Confidential client failure followed by success</summary>

A wrong secret for `siem-workload-20261105` produced `CLIENT_LOGIN_ERROR`; a correct secret produced `CLIENT_LOGIN`. In production, use Entra service principal sign-in records and validate whether the export aggregates attempts.

Keycloak container stdout - failed client sign-in

```text
2026-11-05 06:03:43,646 WARN  [org.keycloak.events] (executor-thread-1) type="CLIENT_LOGIN_ERROR", realmId="b0557f70-80bf-407f-9947-cb7c538105c2", realmName="app", clientId="siem-workload-20261105", userId="null", ipAddress="172.18.0.1", error="invalid_client_credentials", grant_type="client_credentials"
```

Keycloak Admin REST `events` response object - successful client sign-in

```json
{"id":"3b996d3e-4fef-4c60-9222-09a9b57daa07","time":1793858623660,"type":"CLIENT_LOGIN","realmId":"b0557f70-80bf-407f-9947-cb7c538105c2","clientId":"siem-workload-20261105","userId":"1a7360f5-0048-434e-b0bb-7f1360e3858f","ipAddress":"172.18.0.1","details":{"token_id":"trrtcc:942d7e7c-5f94-3d8f-7477-9442ccd8718c","grant_type":"client_credentials","scope":"profile email","client_auth_method":"client-secret","username":"service-account-siem-workload-20261105"}}
```

</details>

<details>
<summary>D08 - Attempt to use another user's session</summary>

`siem_admin_20261105` created the session. `siem_analyst_20261105` then attempted to execute against the same session and received 403. The audit indicates an ownership mismatch; the HTTP log carries the caller `user_id` but neither record names the session owner. Do not assume a shared request ID between the two lines.

Fred Agents audit and application stdout

```json
{"http_method": "POST", "duration_ms": 420.5819420021726, "outcome": "responded", "route": "/agents/execute/stream", "http_status": 200, "session_id": "siem-d08-owner-session-20261105", "exchange_id": "e7dfb11f-8973-4baf-96fd-6c8e96521a7f", "team_id": "fb8c7430f7624cc397740a26fe74d735", "agent_instance_id": "7831628f-0787-4437-a752-fc7d189a2e0a", "correlation_id": "3bd4d9bb-0089-496b-b833-8b938693204c", "request_id": "70710707-1492-444e-b11b-8ae054e1ab5e", "template_agent_id": "fred.github.test_assistant", "run_id": "93896b31-5add-4a35-be79-3b7419b0c449", "user_id": "07f3fafe-39f5-4115-8baf-baa84e055607", "severity": "INFO", "timestamp": {"seconds": 1793859178, "nanos": 302259922}, "message": "POST /agents/execute/stream → 200 | 421ms", "logger": "http", "service": "fred-agents", "category": "application", "logging.googleapis.com/sourceLocation": {"file": "http.py", "line": "136", "function": "__call__"}, "process": 1314249, "thread": "MainThread", "task_name": "Task-99", "service_role": "api"}
{"ts": 1793859192.023819, "level": "WARNING", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "fred-agents", "msg": "[SECURITY] session_owner_mismatch", "extra": {"audit_event": "session_owner_mismatch", "outcome": "rejected", "reason": "session_owner_mismatch"}}
{"http_method": "POST", "duration_ms": 22.925970995856915, "outcome": "responded", "route": "/agents/execute/stream", "http_status": 403, "correlation_id": "41e59eb4-e635-4882-87d4-ce5e0549daf0", "request_id": "56c19d77-03c1-4467-aec2-5420eeca6447", "user_id": "8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", "severity": "WARNING", "timestamp": {"seconds": 1793859192, "nanos": 25154113}, "message": "POST /agents/execute/stream → 403 | 23ms", "logger": "http", "service": "fred-agents", "category": "application", "logging.googleapis.com/sourceLocation": {"file": "http.py", "line": "136", "function": "__call__"}, "process": 1314249, "thread": "MainThread", "task_name": "Task-171", "service_role": "api"}
```

</details>

<details>
<summary>D09 - Rejected delegated grant</summary>

`siem_analyst_20261105` called the delegated frontend bootstrap route as an untrusted caller. The audit supplies `caller_not_trusted`; the HTTP completion supplies 403 and a request ID, but the audit has no actor or request ID.

Fred Control Plane audit and application stdout

```json
{"ts": 1793858726.6196928, "level": "WARNING", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "control-plane", "msg": "[SECURITY] delegation.grant.rejected", "extra": {"audit_event": "delegation.grant.rejected", "outcome": "rejected", "reason": "caller_not_trusted"}}
{"http_method": "GET", "duration_ms": 19.590803000028245, "outcome": "responded", "route": "/frontend/bootstrap", "http_status": 403, "correlation_id": "5e852d24-de30-4c26-83af-b0218773d30e", "request_id": "670d4f73-6117-4ca7-9eaf-db473d5a59df", "severity": "WARNING", "timestamp": {"seconds": 1793858726, "nanos": 620375633}, "message": "GET /frontend/bootstrap → 403 | 20ms", "logger": "http", "service": "control-plane", "category": "application", "logging.googleapis.com/sourceLocation": {"file": "http.py", "line": "136", "function": "__call__"}, "process": 1287358, "thread": "MainThread", "task_name": "Task-174", "service_role": "api"}
```

</details>

<details>
<summary>D10 - Free link revealed and used for enrollment</summary>

`siem_analyst_20261105` revealed the test team Free enrollment link and enrolled with it. The identical `link_id` and `team_id` join the two events. One enrollment is an observed chain, not an unusual-volume alert.

Fred Control Plane audit stdout

```json
{"ts": 1793858848.8121939, "level": "INFO", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "control-plane", "msg": "[SECURITY] platform.access.link.revealed", "extra": {"audit_event": "platform.access.link.revealed", "actor_uid": "8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", "team_id": "fb8c7430f7624cc397740a26fe74d735", "link_id": "dc87c837-1caf-4f8e-b748-0f6eec1c2919"}}
{"ts": 1793858848.8516037, "level": "INFO", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "control-plane", "msg": "[SECURITY] platform.access.free.enrolled", "extra": {"audit_event": "platform.access.free.enrolled", "actor_uid": "8ba40cdc-0d63-45a2-a3a2-4c5b113ddff1", "team_id": "fb8c7430f7624cc397740a26fe74d735", "link_id": "dc87c837-1caf-4f8e-b748-0f6eec1c2919"}}
```

</details>

<details>
<summary>D11 - Burst of unauthenticated administrative requests</summary>

Five requests without a bearer token hit the same administrative route within one second; Fred returned 401 each time. These are Fred application logs only. The local test bypassed the production ingress, so no WAF decision or external client IP was observed.

Fred Control Plane application stdout

```json
{"http_method": "GET", "duration_ms": 3.954758998588659, "outcome": "responded", "route": "/admin/platform/access/users", "http_status": 401, "correlation_id": "c9da2d5a-6064-4013-994a-21f0f3855e56", "request_id": "4e8d3131-603a-4d16-a1bc-91b4df26b757", "severity": "WARNING", "timestamp": {"seconds": 1793858858, "nanos": 279309272}, "message": "GET /admin/platform/access/users → 401 | 4ms", "logger": "http", "service": "control-plane", "category": "application", "logging.googleapis.com/sourceLocation": {"file": "http.py", "line": "136", "function": "__call__"}, "process": 1287358, "thread": "MainThread", "task_name": "Task-305", "service_role": "api"}
{"http_method": "GET", "duration_ms": 2.0708259980892763, "outcome": "responded", "route": "/admin/platform/access/users", "http_status": 401, "correlation_id": "1c21bb96-5352-49d0-9ddc-e8cf10d69ef7", "request_id": "428f3e11-6edd-489b-9e7a-d2b7a4a1fe5b", "severity": "WARNING", "timestamp": {"seconds": 1793858858, "nanos": 281939506}, "message": "GET /admin/platform/access/users → 401 | 2ms", "logger": "http", "service": "control-plane", "category": "application", "logging.googleapis.com/sourceLocation": {"file": "http.py", "line": "136", "function": "__call__"}, "process": 1287358, "thread": "MainThread", "task_name": "Task-307", "service_role": "api"}
{"http_method": "GET", "duration_ms": 3.825194995442871, "outcome": "responded", "route": "/admin/platform/access/users", "http_status": 401, "correlation_id": "97c7cc9b-3b03-4166-826a-8289ed10d7a6", "request_id": "3c6bc9fe-a443-44f7-b94d-a36ec9d982df", "severity": "WARNING", "timestamp": {"seconds": 1793858858, "nanos": 286276340}, "message": "GET /admin/platform/access/users → 401 | 4ms", "logger": "http", "service": "control-plane", "category": "application", "logging.googleapis.com/sourceLocation": {"file": "http.py", "line": "136", "function": "__call__"}, "process": 1287358, "thread": "MainThread", "task_name": "Task-309", "service_role": "api"}
{"http_method": "GET", "duration_ms": 1.7857999991974793, "outcome": "responded", "route": "/admin/platform/access/users", "http_status": 401, "correlation_id": "ed805d02-cf9c-421f-805b-5f083022d41d", "request_id": "e09f64aa-1a9d-4e77-b078-e82c7c585866", "severity": "WARNING", "timestamp": {"seconds": 1793858858, "nanos": 288530826}, "message": "GET /admin/platform/access/users → 401 | 2ms", "logger": "http", "service": "control-plane", "category": "application", "logging.googleapis.com/sourceLocation": {"file": "http.py", "line": "136", "function": "__call__"}, "process": 1287358, "thread": "MainThread", "task_name": "Task-311", "service_role": "api"}
{"http_method": "GET", "duration_ms": 4.705740000645164, "outcome": "responded", "route": "/admin/platform/access/users", "http_status": 401, "correlation_id": "e0a756e9-1bdd-4b62-87a6-710488f6c2bc", "request_id": "7e76e35f-676d-457f-840d-707b78c684d9", "severity": "WARNING", "timestamp": {"seconds": 1793858858, "nanos": 294335842}, "message": "GET /admin/platform/access/users → 401 | 5ms", "logger": "http", "service": "control-plane", "category": "application", "logging.googleapis.com/sourceLocation": {"file": "http.py", "line": "136", "function": "__call__"}, "process": 1287358, "thread": "MainThread", "task_name": "Task-313", "service_role": "api"}
```

</details>

<details>
<summary>D12 - Runtime tool invocation started and completed</summary>

`siem_admin_20261105` ran the development test assistant and answered its `ask_user` question. The audit records the start and successful completion; the application log names the tool and user. Under current delegation settings, the audit lines omit both identifiers, so the SIEM should not claim a reliable audit-to-application join from these lines alone.

Fred Agents audit and application stdout

```json
{"ts": 1793859428.204237, "level": "INFO", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "fred-agents", "msg": "[SECURITY] agent.tool.invocation.started", "extra": {"audit_event": "agent.tool.invocation.started", "outcome": "started", "reason": "tool_invocation"}}
{"ts": 1793859428.209212, "level": "INFO", "logger": "fred.security.audit", "file": "audit_log.py", "line": 63, "service": "fred-agents", "msg": "[SECURITY] agent.tool.invocation.completed", "extra": {"audit_event": "agent.tool.invocation.completed", "outcome": "succeeded", "reason": "tool_completed"}}
{"outcome": "succeeded", "duration_ms": 5.7370389986317605, "session_id": "siem-d12-tool-complete-20261105", "task_id": null, "document_uid": null, "tool_name": "ask_user", "exchange_id": "889dc56b-6e43-443d-a99f-d447e93e3689", "team_id": "fb8c7430f7624cc397740a26fe74d735", "agent_instance_id": "7831628f-0787-4437-a752-fc7d189a2e0a", "correlation_id": "6e572d89-3acc-41d8-a0fc-4fa6c18cdf49", "request_id": "1649c645-1020-44b9-9611-612668cc3f49", "template_agent_id": "fred.github.test_assistant", "run_id": "efa70342-b074-4c35-afac-8f23a0811a3f", "user_id": "07f3fafe-39f5-4115-8baf-baa84e055607", "severity": "INFO", "timestamp": {"seconds": 1793859428, "nanos": 209930658}, "message": "Tool invocation completed", "logger": "fred_runtime.runtime_support.tool_execution", "service": "fred-agents", "category": "application", "logging.googleapis.com/sourceLocation": {"file": "tool_execution.py", "line": "144", "function": "run"}, "process": 1314249, "thread": "MainThread", "task_name": "Task-427", "service_role": "api"}
```

</details>

## 6. Validation and acceptance

In a representative test environment, perform permitted and denied actions with test accounts: a successful and failed Entra sign-in, a confidential client sign-in, a role grant and revocation, an access-policy change, another user's session access attempt, a rejected delegated grant, and a test tool invocation.

For each action, verify in the SIEM that the raw event is searchable; the syslog envelope and JSON survive; source and timestamp are correct; normalized fields have the expected types; content and credentials are absent; the event is not duplicated; delivery is timely; and the rule triggers or intentionally stays silent. Interrupt the relay or destination and restart a container to test recovery, queue limits, and collection alerts. Measure alert volume on normal traffic before enabling operational notifications.

Before go-live, the SIEM operator confirms the actual relay and syslog format, transport to the agent, Entra tenant access and exported categories, Fred application IDs, retention, audit access separation, thresholds and windows, maintenance windows, alert recipients, and investigation procedure. The Fred operator supplies versions, service names, and test scenarios. The security team owns SIEM rules and ongoing tuning.
