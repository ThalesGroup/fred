# RFC TABULAR-SANDBOX — Security boundary for agent-authored SQL over tabular datasets

**Status:** draft pending sign-off (2026-08-26)
**Scope:** where the security boundary sits when executing agent/LLM-authored SQL
(DuckDB) over ingested Parquet artifacts — replacing the SQL parser
(`validate_read_query`) as the *sole* boundary. Related: #2364 (GCS signBlob
outage, fixed by PR #2444), #2318 (browser-facing signed URLs, out of scope).
**Decides:** which of two viable enforcement models each content-store family
uses, and what infrastructure each requires.

---

## 1. Problem

The tabular feature (`knowledge-flow-backend/features/tabular/`) executes
arbitrary read-only SQL written by an agent against Parquet artifacts the
*user* is authorized to read (ReBAC). Requirements:

- R1 — the agent must never read a dataset the user cannot see;
- R2 — the agent must never read anything else reachable from the pod
  (local files such as `.env`, other buckets, internal HTTP endpoints,
  the cloud metadata server / service-account tokens);
- R3 — the enforcement mechanism should not be a hand-written SQL analyzer:
  a parser gap must not become a data breach;
- R4 — (goal, not yet met) large Parquet files should be readable without
  materializing the whole object (HTTP range reads: footer + needed row
  groups/columns only).

Today R1/R2 rest on `validate_read_query` — a DuckDB-AST walk that allowlists
relation names and rejects table functions. It works, but it is exactly the
kind of boundary R3 rules out: one gap exposes everything the pod's
credentials and filesystem can reach, including SSRF to the metadata server
(on AWS-style IMDSv1, a plain `read_csv('http://169.254.169.254/...')`
reaches credential material; on GCP the token endpoint additionally requires
a `Metadata-Flavor` header, but DuckDB `CREATE SECRET (TYPE http,
EXTRA_HTTP_HEADERS …)` exists, so the header is not a safety net).

## 2. Solutions considered (consolidated history)

Options 1–8 were explored during the original design; the verdicts below are
updated with the 2026-08-26 empirical results of §3.

| # | Design | Verdict |
|---|--------|---------|
| 1 | DuckDB `:memory:` + pre-registered views + SQL parsing guard (first token, then AST walk) | **Rejected as sole boundary** (R3): security depends on the parser. This is what ships today; the parser stays as a UX/perf layer only (§6). |
| 2 | DuckDB + `httpfs` reading `s3://` with the backend's normal store credentials | **Broken:** the credential grants the whole bucket; any parser gap (`read_csv_auto('s3://…/other-team/…')`) reads foreign data. |
| 3 | DuckDB + server-side download of exactly the authorized files into a per-job directory + `enable_external_access=false` | **Viable → Solution A (§4).** Security by physical absence. Confirmed workable on DuckDB 1.5.4 with `allowed_directories` + `lock_configuration`. Cost: full-file downloads (fails R4 for big Parquet). |
| 4 | Postgres RLS, one `csv_data` table, `SET app.current_team_id` | **Broken:** agent controls the SQL stream → `SET`/`RESET` clears the context. RLS is only safe when a typed API compiles the SQL (PostgREST-style). |
| 5 | Postgres schema-per-team + `SET ROLE team_N_agent` | **Broken:** runner is a member of every team role → `SET ROLE team_other` escalates. |
| 6 | Postgres per-team LOGIN role, no memberships, `GRANT SELECT` on own schema only | **Secure but rejected:** roles are cluster-global (`pg_authid`); dynamic per-team provisioning + view maintenance doesn't scale. |
| 7 | SQLite, one DB file per team | **Rejected:** no engine-level access control; `ATTACH DATABASE` cannot be disabled → arbitrary file reach. |
| 7b | SQLite + OS isolation (setuid per team) | **Rejected:** process-wide/irreversible, breaks async FastAPI; K8s containers run one UID. |
| 7c | SQLite/DuckDB in an ephemeral pod per query | **Rejected as-is:** real isolation but heavy, cold-start slow. Resurfaces in softened form as the persistent minimal executor of Solution B (§5). |
| 8 | Object-store STS (MinIO `AssumeRole` + inline policy; GCS Credential Access Boundaries) + DuckDB `httpfs`, "layered with `enable_external_access=false`" | **Viable but corrected → Solution B (§5).** The credential-as-boundary half is right. The layering half is impossible: §3 shows `enable_external_access=false` blocks `httpfs` itself (`s3://` included). With external access ON, arbitrary-host HTTP (SSRF) stays open and **no DuckDB setting can close it** — the missing layer is a network egress allowlist, not a DuckDB flag. |
| 9 | Presigned URL per object + `httpfs` (what shipped pre-#2364) | A capability-URL variant of 8: per-object short-TTL scoping without STS. Fine on MinIO/S3; **died on GCS** where minting V4 URLs needs `iam.serviceAccounts.signBlob` (not granted on tp-s3ns). Also leaks bearer URLs into DuckDB error text (redaction machinery required), and leaves the same SSRF/local-read exposure as 8 since `httpfs` is on. |
| 10 | GCS server-side ADC download to per-job temp dir (PR #2444, current branch) | The GCS-shaped instance of 3, **without the DuckDB sandbox flags yet** — parser still the boundary. Gap analysis in §7. |

## 3. Empirical results — DuckDB 1.5.4 (prod version), 2026-08-26

Method: local tests, including two local HTTP servers ("allowed" and
"attacker") that log every connection, so "config-blocked" is distinguishable
from "network failed".

| Knob | Measured behavior |
|------|-------------------|
| `enable_external_access=false` | Blocks local files outside the allowlist, `http(s)://` **and `s3://`** — checked *before* any network/credential use. Therefore **mutually exclusive with `httpfs` reads**: options 3 and 8 cannot be layered. |
| `allowed_directories` / `allowed_paths` | **Local-filesystem allowlist only.** With `allowed_paths=['http://allowed-host/']` set and locked, a request to a *different* host still connected (attacker server logged the hit). Does **not** gate URL hosts → useless against SSRF. Also directory-granular: *any* file inside an allowed dir is readable (`read_text` on a planted secret succeeded), so the job dir must contain only authorized artifacts. |
| `disabled_filesystems` | All-or-nothing per filesystem (`'LocalFileSystem'`, `'HTTPFileSystem'`). Cannot pin `httpfs` to one host. |
| `lock_configuration=true` | Effective: subsequent `SET` of any security option fails. Must be set *after* the allowlist/flags, and any needed extension (`httpfs`) must be loaded *before* external access is disabled. |
| `ATTACH` | Still permitted *inside* an allowed directory under `enable_external_access=false`. Harmless for reads (blocked outside the dir) but note it can write a `.db` file into the job dir; the single-`SELECT` statement check (§6) blocks it anyway. |
| Host pinning for `httpfs` | **No in-DuckDB mechanism exists.** Egress control must come from the network layer. |

## 4. Solution A — local materialization + directory sandbox ("physical absence")

For each job: ReBAC resolves the authorized datasets → the backend downloads
exactly those artifacts into a per-job temp dir (digest-named files, disk
budget) → DuckDB opens with:

```sql
SET allowed_directories = ['<job temp dir>'];
SET enable_external_access = false;
SET lock_configuration = true;
-- httpfs never loaded; temp_directory already '' (spilling disabled)
```

Properties (all measured, §3): agent SQL cannot leave the job dir, cannot
reach http/s3, cannot re-`SET`. The security boundary is *which files the
trusted code put in the directory* — no parser, no credential in DuckDB's
hands, no network. Works identically for GCS (ADC download), S3/MinIO/
SeaweedFS (`get_local_copy`-style download), and the local filesystem store
(copy into the job dir — pointing `allowed_directories` at the store's
`object_root` would expose *every* document and is forbidden).

Limits: full-file download (fails R4 for large Parquet); per-job disk budget
(`max_local_artifact_bytes`) is the ceiling. The re-download cost is
addressed by the artifact cache below.

### 4.1 Pod-local artifact cache (pnpm-style, hardlinks)

Downloads persist in a shared pod-local cache; each job dir receives
**hardlinks** to the cached artifacts it is authorized to mount. Verified on
1.5.4 (2026-08-26):

- the shared cache holds *every* team's artifacts, so it must never be the
  `allowed_directories` target (same reasoning as G3's `object_root`) — the
  per-job dir of links *is* the sandbox boundary;
- **hardlinks work** under the sandbox (the link is the file; direct cache
  paths stay blocked). **Symlinks do not**: DuckDB canonicalizes the path and
  checks the *target*, refusing a symlink out of the job dir — which both
  rules out the symlink variant and confirms there is no symlink-escape hole;
- write-protection: cache files `chmod 444`, job dir `chmod 500` after
  linking — both `COPY … TO` into the dir and overwrite of an artifact fail
  at the OS (retires §6 reason 3 without metering);
- **eviction is safe by construction**: evicting an entry unlinks only the
  cache's name; a running job's hardlink keeps the inode alive until its job
  dir is deleted. No coordination between eviction and queries;
- invalidation: **one mechanism — the store's own version marker.** Object
  stores version every object (GCS *generation*, S3/MinIO *ETag*); the cache
  key is `(object_key, generation/etag)`. Per mount, one `HEAD` returns the
  current marker without content (~ms, parallelizable across a query's
  datasets → ~one store round trip per query — noise next to the full
  download the no-cache design pays today). This covers every change path:
  re-ingestion *and* objects overwritten directly in the bucket behind
  Fred's back (admin `gsutil`/`mc` write, bucket restore). Not by hashing
  the remote (that is a full download), and not by ingestion metadata
  (`generated_at`) — a metadata-based key would be a second mechanism with
  a blind spot for out-of-band writes, for no gain. On a miss, record the
  generation/etag returned *by the download response itself* (not the
  HEAD's), closing the HEAD-then-download race. Accepted trade-off: a cache
  hit requires the store to answer the HEAD, so a store outage fails even
  cached queries — misses need the store anyway, and serving possibly-stale
  data during an outage is not a property this feature wants;
- mechanics: cache and job dirs on the **same filesystem** (one emptyDir —
  hardlinks do not cross devices); download to a temp name + atomic rename
  for concurrent jobs; two budgets — pod-level cache size (physical, LRU by
  atime) and the per-job *logical* budget (sum of linked artifact sizes,
  enforced cache hit or miss);
- **local mode (`FileSystemContentStore`): no cache layer.** Artifacts are
  already local, so there is nothing to avoid re-downloading — and therefore
  nothing to invalidate. Each job **copies** (not hardlinks) its authorized
  artifacts into the job dir: a hardlink would share the inode with the
  store's own file, and here the local file *is* the store of record — a
  write through the link would corrupt it, whereas the GCS/S3 cache file is
  a disposable copy. Copy keeps the store physically unreachable from the
  sandbox; local mode is dev/test, so the copy cost is irrelevant
  (`cp --reflink=auto` where the filesystem supports CoW). Both modes end on
  the same contract: job dir contains only authorized artifacts, sandboxed
  per §4.

## 5. Solution B — STS-scoped credentials + `httpfs` + network egress allowlist

For each job: ReBAC resolves the authorized datasets → the backend mints a
short-TTL credential scoped to exactly those object keys (MinIO
`AssumeRole` + inline policy; GCS Credential Access Boundary via
`sts.googleapis.com` — one rule per bucket, multiple `startsWith` prefixes
OR-ed in one CEL condition, ≤10 rules/token) → DuckDB reads `s3://`/`https://`
directly with range requests. A foreign object key gets 403 **from the object
store's IAM layer**, entirely outside the SQL stream. Meets R4.

The mandatory second half: because `httpfs` requires external access ON,
DuckDB can `GET` *any* host (§3) — SSRF is open unless the **network layer**
closes it. That means a K8s egress `NetworkPolicy` allowing only the object
store endpoint (+ DNS), denying everything else including `169.254.169.254`.

### 5.1 Why the egress allowlist cannot be applied to knowledge-flow itself

`NetworkPolicy` is pod-granular; DuckDB runs in-process, so KF's policy is
DuckDB's policy. KF legitimately needs egress to Postgres/OpenSearch,
Keycloak, OpenFGA, the object store, LLM/embedding APIs, and — fatally — on
GCS with Workload Identity the pod **must** reach the metadata server to
obtain its own tokens. An allowlist tight enough to stop SSRF breaks KF; one
loose enough for KF lets DuckDB reach every internal service KF can (worst on
unauthenticated/link-local endpoints). Sidecar containers share the pod's
network namespace, so they don't help either.

**Consequence: Solution B requires a separate minimal executor service** — a
small deployment (`tabular-executor`) that:

- accepts `(SQL, scoped credential, object locations, limits)` from KF and
  returns rows — KF keeps ReBAC, dataset resolution, and STS minting;
- runs under a **no-privilege service account**, no secrets/env of its own
  (credentials arrive per-request, already downscoped);
- carries the tight egress `NetworkPolicy`: object-store endpoint + DNS only,
  explicit deny for the metadata endpoint;
- is the softened form of option 7c: pod-boundary isolation, but persistent
  (no cold start per query). Also shrinks the blast radius of any residual
  gap: the executor pod has nothing else to read.

## 6. What remains of the SQL parser

Under either solution, **every semantic restriction on the SQL is dropped** —
no `SELECT`-only rule, no single-statement rule. Each of the three reasons the
restriction used to serve is engineered away (all verified on 1.5.4,
2026-08-26):

1. *Row cap:* today the cap is a SQL wrapper (`SELECT * FROM (<sql>) AS
   fred_result LIMIT n`), which is both injectable (a statement that closes
   the parenthesis runs outside the cap) and the reason the input had to be
   one SELECT expression. Replaced by a **Python-side streaming fetch**:
   DuckDB's client streams results (`fetchmany(11)` on a 2·10⁹-row query
   returns in ~1 ms), so the executor fetches `max_rows + 1` rows and stops —
   no wrapper, no injection surface, no restriction.
2. *Result shape:* multi-statement scripts are split with DuckDB's own
   `duckdb.extract_statements` (typed statements, not a hand-rolled parser),
   executed sequentially, and the response returns **one result set per
   `SELECT`** (contract change: `rows` becomes a list of result sets; MCP
   schema + client update). Staging workflows — `CREATE TEMP TABLE … AS …;
   SELECT …` — verified working under the full A sandbox; temp tables are
   in-memory, bounded by `memory_limit` with spilling disabled.
3. *Writes under A:* nothing persists across queries anyway — the job dir is
   created per job and deleted with it. Within one job, `chmod 500` on the
   dir after materializing closes `COPY … TO`/`ATTACH` writes (verified:
   write fails with a permission error, reads unaffected).

Also verified: `lock_configuration` blocks the `PRAGMA` and `RESET` spellings
of `SET`, so a script cannot lift its own limits; under B, set
`autoinstall_known_extensions=false` / `autoload_known_extensions=false`
before locking so `INSTALL` cannot fetch extensions (the egress policy blocks
it anyway).

What remains of `validate_read_query` is mechanical, not a boundary:
statement splitting (`extract_statements`) and the AST relation walk kept
*as UX and performance* — clean 400s the LLM can self-correct from, and
`referenced_relations` narrowing which datasets are downloaded (A) or
included in the STS scope (B); mounting everything per query is the
round-trip/download explosion the narrowing was added to fix. A gap in it
under A reads only the job dir; under B, only what the scoped credential and
the egress policy allow.

## 7. Gap: current branch (PR #2444) vs Solution A

The branch already implements the expensive parts of A for GCS: per-job temp
dir wrapping the whole connection lifetime, ADC streaming download, disk
budget with declared-size precheck, digest filenames, lazy per-table mounting
in search, error redaction, spilling disabled. What's missing:

| Gap | Size |
|-----|------|
| G1 — sandbox flags: when a job's location strategy is "local files", open the connection with `allowed_directories=[job dir]`, `enable_external_access=false`, `lock_configuration=true` (ordering per §3). Strategy is known before `open_duckdb_connection` (store class → `_dataset_location_scope`), so this is a parameter to connection open + tests. | small (few lines + tests) |
| G2 — non-GCS remote stores (MinIO/SeaweedFS) still use presigned URL + `httpfs` → external access ON → unsandboxed, parser still the boundary there. Decide: extend the download model (A everywhere, uniform, loses range reads) or hold for Solution B on S3-compatible stores. | decision + medium |
| G3 — `FileSystemContentStore` hands DuckDB direct paths into `object_root` (all documents). For A, copy authorized artifacts into the job dir (copy, not hardlink — §4.1 local-mode note; no cache layer needed). | small |
| G4 — artifact cache per §4.1: shared pod-local cache + per-job hardlink dirs, metadata-keyed invalidation, LRU eviction, chmod write-protection. Optimization (kills per-request re-downloads for queries *and* previews), not security. | medium |
| G5 — unrestricted-SQL execution model (§6): replace the `LIMIT` wrapper with a streaming `fetchmany(max_rows+1)` cap, split scripts with `extract_statements` and return one result set per `SELECT` (response/MCP contract change), chmod the job dir read-only after materializing. Separable from G1 and lower priority: it *adds* agent capability, while G1 removes the parser dependency. | medium (contract change) |

With G1 alone, the GCS path (the one in production trouble) stops depending
on the parser. G2/G3 decide how uniform the model is.

## 8. Open questions

1. Does S3NS (sovereign GCP universe, `s3nsapis.fr`) expose the STS
   endpoint / Credential Access Boundaries at all? (Same class of gap as the
   `signBlob` denial that caused #2364 — verify before committing to B on
   that environment; fmuller to check.)
2. CEL/expression size limits on a Credential Access Boundary rule vs
   `max_selected_datasets` (how many object prefixes fit one token).
3. Live confirmation that `storage.objects.get` works on the tp-s3ns
   `-objects` bucket (open verification from #2364; SeaweedFS is the
   documented fallback).
4. B's executor service: worth the operational cost now, or adopt A
   uniformly (G2) and revisit B when large-Parquet demand (R4) is real?

## 9. Recommendation

- **Now:** land PR #2444, then close G1 (sandbox flags on the local-file
  strategy) as a small follow-up — GCS tabular reads stop relying on the
  parser with a few lines.
- **Next:** decide G2/G3 (uniform Solution A) — simplest coherent model,
  no new infrastructure, acceptable while artifacts stay ≤ the disk budget.
- **When R4 matters (big Parquet):** implement Solution B behind the
  `tabular-executor` service, gated on open questions 1–2.
