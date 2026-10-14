# 6. Cross-cutting concepts

## Authentication

The `CurrentUser` extractor authenticates every route but the health probe.

| Aspect | Rule |
| --- | --- |
| Token | `Authorization: Bearer`, RS256 only, key chosen by `kid` among the realm's signing keys |
| Endpoints | Keycloak: `<realm>/protocol/openid-connect/certs`; OIDC: discovery, issuer must match the configured one |
| Identity | `sub` is the user id and the OpenFGA subject; roles from `resource_access.<client_id>.roles` or `roles_claim`; client from `azp` or `client_id`; service account recognised by `preferred_username = service-account-<client>` |
| OIDC subjects | A non-UUID `sub` becomes `uuid5(NAMESPACE_URL, "<issuer>#<sub>")`; an empty `sub` is refused |
| Strict mode | `profile: c3`, or `FRED_STRICT_ISSUER` / `FRED_STRICT_AUDIENCE`: exact issuer (user and m2m realms), audience `audience` or `client_id` |
| Times | `exp` and an integer `iat` required, `iat` not in the future, `exp - iat` at most `FRED_JWT_MAX_LIFETIME_SECONDS` (3600), leeway `FRED_JWT_CLOCK_SKEW` (0) |
| Key cache | Keys kept 300 s; an unknown `kid` refetches at most once per 30 s, failures included, one fetch at a time, cached keys readable meanwhile; tokens are verified on every request |
| Disabled | `security.user.enabled: false`: every caller is the mock `admin`, client `local-dev`; `profile: c3` refuses to start that way |

401 answers carry a `WWW-Authenticate` header:

| Detail | `WWW-Authenticate` |
| --- | --- |
| `No authentication token provided` | `Bearer` |
| `Invalid token signature` | `Bearer error='invalid_token'` |
| `Token has expired` | `Bearer error='invalid_token', error_description='token expired'` |
| `Invalid token` | `Bearer error='invalid_token'` |
| `Token has invalid iat/exp claims` | `Bearer error='invalid_token', error_description='exp before iat'` |
| `Token lifetime exceeds the maximum permitted duration` | `Bearer error='invalid_token', error_description='token lifetime too long'` |
| `Invalid token claims` | `Bearer error='invalid_token'` |

## Logging

Structured stdout, in the format shared by Fred's services.

| `app.log_format` | Output |
| --- | --- |
| `json` | One object per line: `severity`, `message`, `timestamp` `{seconds, nanos}`, `logger`, `service` (`fred-manager`), `service_role` (`api`), `category`, `logging.googleapis.com/sourceLocation` (`file`, `line`, `function` = module path), `process`, `thread` |
| `text` | `<rfc3339> <SEVERITY> fred-manager/<logger> <message> key=value ...`, no wrapping, colors only on a terminal without `NO_COLOR` |

- Event fields and request context are top-level and never replace core fields.
  Fields named `token`, `access_token`, `refresh_token`, `id_token`, `authorization`,
  `cookie`, `password`, `secret`, `email`, `user`, `prompt`, `completion`, `content`,
  `body`, `arguments`, `result`, `url` or `signed_url` are dropped (I11).
- Dependencies log from WARNING only, as `Dependency diagnostic`, without their text or
  fields (I11).
- Each request gets `X-Request-ID` and `X-Correlation-ID`; its lines carry
  `request_id`, `correlation_id` and, once authenticated, `user_id`. It ends with one
  event on logger `http`: `METHOD route → status | Nms`, fields `http_method`, `route`
  (template), `http_status`, `duration_ms`, `outcome`; INFO below 400, WARNING for
  other 4xx, ERROR for 5xx; omitted for a successful `/healthz`; `cancelled` when the
  client goes away (I13).
- A fatal error after startup is one ERROR event, `fred-manager stopped`.

## Errors

Every error body is `{"detail": "<message>"}`, as FastAPI.

| Status | When |
| --- | --- |
| 400 | Unknown role name, placement rule broken (I1) |
| 401 | Missing or invalid bearer (details above) |
| 403 | Permission denied (`forbidden`), wrong bootstrap secret |
| 404 | Unknown id |
| 409 | Unique or foreign-key violation, invariant refusal, bootstrap completed, ingestion already running |
| 422 | Invalid JSON body (optional ones included), short bootstrap token, half a cursor |
| 503 | Bootstrap with authentication disabled |
| 500 | Anything else, logged, answered `internal error` |

## Configuration

`CONFIG_FILE` (default `./config/configuration.yaml`) holds the settings, in sections
`app`, `security`, `storage`, `scheduler`; `ENV_FILE` (default `./config/.env`) holds
secrets only and never overrides the process environment.

| Secret | Read from |
| --- | --- |
| `FRED_POSTGRES_PASSWORD` | process or `.env` |
| `OPENFGA_API_TOKEN` | the variable `security.rebac.token_env_var` names |
| `FRED_BOOTSTRAP_TOKEN` | the variable `app.bootstrap_token_env_var` names |

Local reference configuration:

<!-- generated: include apps/fred-manager/config/configuration.yaml yaml -->
```yaml
# fred-manager on the host, against the local stack of fred-deployment-factory.
# Secrets come from config/.env.

app:
  name: Fred Manager
  base_url: /fred-manager/v1
  address: 0.0.0.0
  port: 8400
  log_level: info
  log_format: text
  # One-time root platform-admin bootstrap secret, from config/.env.
  bootstrap_token_env_var: FRED_BOOTSTRAP_TOKEN

security:
  profile: c3
  m2m:
    realm_url: http://localhost:8080/realms/app
  user:
    enabled: true
    realm_url: http://localhost:8080/realms/app
    client_id: app
  authorized_origins:
    - http://localhost:5173
  rebac:
    type: openfga
    api_url: "http://localhost:9080"
    store_name: fred-manager

storage:
  postgres:
    host: localhost
    port: 5432
    database: fred
    username: fred

scheduler:
  temporal:
    host: localhost:7233
    namespace: default
    task_queue: fred-ingestion
```
<!-- end generated -->
