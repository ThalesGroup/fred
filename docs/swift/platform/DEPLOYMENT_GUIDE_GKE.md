# Deploying Fred on GKE with native Google Cloud Storage (Workload Identity)

Audience: operators deploying Fred (knowledge-flow + control-plane) on GKE
Autopilot using **native Google Cloud Storage (GCS)** for object storage, with
credentials provided by **Workload Identity / Application Default Credentials
(ADC)** — no service-account JSON key committed or mounted.

Task: `FILES-06` (parent `FILES-04`) · Backlog: `docs/swift/backlog/BACKLOG.md`
· Registry: `docs/swift/data/id-legend.yaml`.

> MinIO/S3 and local-disk backends remain fully supported. GCS is additive and
> selected purely by the `type:` config discriminator.

---

## 1. What GCS replaces

Fred has two independent pluggable object-storage abstractions; GCS plugs into
both via configuration:

| Abstraction          | Config key        | GCS value     | Buckets used                                        |
| -------------------- | ----------------- | ------------- | --------------------------------------------------- |
| Content store        | `content_storage` | `type: gcs`   | `<prefix>-documents`, `<prefix>-objects`, `<prefix>-files` |
| Virtual filesystem   | `filesystem`      | `type: gcs`   | `<bucket_name>` (optional key `prefix`)             |

The content store mirrors MinIO's bucket-splitting convention: the configured
`bucket_name` is suffixed with `-documents` (ingestion document trees),
`-objects` (generic assets, tabular Parquet) and `-files` (namespaced file
store: templates, prompts, model artifacts).

---

## 2. Authentication model (hard constraint)

- **MUST** work with Workload Identity on GKE and ADC locally.
- **MUST NOT** require a committed/mounted SA JSON key on the standard path.
- `GOOGLE_APPLICATION_CREDENTIALS` stays an optional dev-only escape hatch.

The clients are created with `google.cloud.storage.Client()`, which discovers
credentials via ADC: Workload Identity on GKE, or
`gcloud auth application-default login` locally.

---

## 3. One-time GCP setup

Replace placeholders (`<PROJECT_ID>`, `<REGION>`, bucket names, SA names).

### 3.1 Create buckets (uniform bucket-level access)

```bash
PROJECT_ID=<PROJECT_ID>
REGION=<REGION>            # e.g. europe-west4
CONTENT=fredlab-content    # content-store prefix
FS=fredlab-fs              # virtual filesystem bucket

for b in "${CONTENT}-documents" "${CONTENT}-objects" "${CONTENT}-files" "${FS}"; do
  gcloud storage buckets create "gs://${b}" \
    --project="${PROJECT_ID}" --location="${REGION}" \
    --uniform-bucket-level-access
done
```

### 3.2 Google service account (GSA) + IAM on the buckets

```bash
GSA=fred-storage
gcloud iam service-accounts create "${GSA}" --project="${PROJECT_ID}"

GSA_EMAIL="${GSA}@${PROJECT_ID}.iam.gserviceaccount.com"
for b in "${CONTENT}-documents" "${CONTENT}-objects" "${CONTENT}-files" "${FS}"; do
  gcloud storage buckets add-iam-policy-binding "gs://${b}" \
    --member="serviceAccount:${GSA_EMAIL}" \
    --role="roles/storage.objectAdmin"
done
```

`roles/storage.objectAdmin` grants read/write/delete on objects. Bucket creation
is **not** required at runtime — the app references buckets lazily, so a
least-privilege object-only SA is sufficient.

**Tabular signed URLs** additionally require the GSA to sign V4 URLs via IAM
`signBlob` (keyless, no SA JSON key). Grant the signing service account
`iam.serviceAccounts.signBlob` on itself — here the GSA self-signs:

```bash
gcloud iam service-accounts add-iam-policy-binding "${GSA_EMAIL}" \
  --member="serviceAccount:${GSA_EMAIL}" \
  --role="roles/iam.serviceAccountTokenCreator"
```

Set this account as `content_storage.signing_service_account_email` (§4). It must
hold `storage.objects.get` on the `-objects` bucket (covered by the
`objectAdmin` binding above). A distinct signing SA also works, provided the GSA
holds `signBlob` on it and it can read the objects bucket.

### 3.3 Bind the Kubernetes SA to the GSA (Workload Identity)

Assume the chart deploys the workload with KSA `knowledge-flow-backend` in
namespace `<NS>`:

```bash
NS=<NS>
gcloud iam service-accounts add-iam-policy-binding "${GSA_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${NS}/knowledge-flow-backend]"
```

The KSA is annotated by the chart (see §4):
`iam.gke.io/gcp-service-account: <GSA_EMAIL>`.

---

## 4. Helm configuration

Use the overlay `deploy/charts/fred/values-gcp.yaml` as the reference for the
values to set. **Read its deep-merge caveat**: the `gcs` schema forbids extra
keys, so the storage blocks must *replace* the base `local`/`minio` blocks (edit
the `x-kf-content-storage`, `x-kf-filesystem`, `x-kf-storage` anchors in your
effective `values.yaml` rather than layering only `type: gcs` on top of them).

Minimum changes for `applications.knowledge-flow-backend`:

```yaml
serviceAccount:
  annotations:
    iam.gke.io/gcp-service-account: "fred-storage@<PROJECT_ID>.iam.gserviceaccount.com"

configuration:
  content_storage:
    type: gcs
    bucket_name: "fredlab-content"   # → -documents / -objects / -files
    project_id: ""                    # inferred from ADC when empty
    # Required: signs V4 signed URLs for tabular reads via IAM signBlob (§3.2).
    signing_service_account_email: "fred-storage@<PROJECT_ID>.iam.gserviceaccount.com"
  filesystem:
    type: gcs
    bucket_name: "fredlab-fs"
    prefix: ""
    project_id: ""
```

No `MINIO_SECRET_KEY` is needed. Keep DB/auth secrets in the rendered secret.

App-level YAML equivalent (non-Helm) lives in
`apps/knowledge-flow-backend/config/configuration_postgres.yaml`.

---

## 5. Signed URLs decision

Fred uses **application-level HMAC download tokens** for sharing
(`features/filesystem/download_token.py`), which are backend-agnostic and work
over GCS with pure Workload Identity. Accordingly:

- The content store's `get_presigned_url` (browser-facing) raises
  `NotImplementedError` on GCS (same as the local backend) — direct
  browser-to-bucket signed URLs are **off** by default.
- The content store's `get_presigned_url_internal` (backend-internal) **is
  supported**: it mints short-lived V4 signed URLs via IAM `signBlob` using
  `content_storage.signing_service_account_email`, with no SA JSON key. This is
  what DuckDB uses for tabular Parquet reads. The GSA needs
  `iam.serviceAccounts.signBlob` on the signing SA (§3.2). See
  [`GCS-TABULAR-SIGNED-URL-RFC.md`](../rfc/GCS-TABULAR-SIGNED-URL-RFC.md).

Practical consequences on the pure WI path:

- ✅ VFS share, ingestion read/write, document download (proxied), team data — work.
- ✅ Tabular SQL preview (`storage.tabular_store.query.access_mode: presigned_url`)
  works once `signing_service_account_email` is set and the `signBlob` binding is
  in place. The app **fails fast at startup** if a GCS content store is
  configured without a signing SA email.
- ✅ Team banner images degrade gracefully (the control plane catches the
  `NotImplementedError` and omits the banner URL).

---

## 6. Validation

```bash
# ADC sanity (local)
gcloud auth application-default login
python -c "from google.cloud import storage; print([b.name for b in storage.Client().list_buckets()])"

# On GKE: confirm the workload SA can write via Workload Identity
kubectl exec deploy/knowledge-flow-backend -- \
  python -c "from google.cloud import storage; storage.Client().bucket('fredlab-fs').blob('healthz').upload_from_string('ok')"
```

Then exercise the API:

- VFS round-trip: write → list → read → delete a file under `/teams/...`.
- Ingestion smoke test: upload a document and confirm objects appear under
  `gs://fredlab-content-documents/<document_uid>/`.

---

## 7. Migrations

None. Object storage is not relational; there is no Alembic impact. PostgreSQL /
Cloud SQL provisioning is owned by `fred-deployment-factory`.

---

## 8. Troubleshooting

| Symptom                                              | Likely cause / fix                                                                 |
| --------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `DefaultCredentialsError` at startup                | KSA not bound to GSA, or missing KSA annotation. Re-check §3.3 / §4.                |
| `403 ... does not have storage.objects.* access`    | GSA missing `roles/storage.objectAdmin` on the bucket (§3.2).                       |
| `404 ... bucket does not exist`                     | Bucket not created or wrong `bucket_name` (remember the `-documents/-objects/-files` suffixes). |
| Helm `values failed schema validation` on `gcs`     | Stale `root_path`/`endpoint` left from the base block — replace the block, don't deep-merge (§4). |
| Startup fails: `content_storage.type=gcs requires 'signing_service_account_email'` | Set it on the GCS content store and bind `signBlob` (§3.2, §4).                |
| `403 ... signBlob ... permission denied` on tabular query | GSA lacks `iam.serviceAccounts.signBlob` on the signing SA (§3.2).                |
| Tabular SQL preview fails with an unsupported-operation error | Content store is not GCS/MinIO/local with a readable path — check `content_storage.type` and §5. |
