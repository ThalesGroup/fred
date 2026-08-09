---
name: seed-synthetic-corpus
description: Seed (and safely reset) a large synthetic corpus of fake libraries/documents/vectors/content in a LOCAL Fred docker-compose stack, to load-test corpus repair/audit tooling (metadata/vector reconciliation, /corpus/revectorize, MetadataService.audit_stores, the "Audit du corpus" admin page). Use when asked to simulate a big platform locally, stress-test repair/audit tools against volume, or generate bulk fake libraries/documents under a team space.
user-invocable: true
argument-hint: [team display name] [library count, default 100] [document count, default 20000]
---

# Seed a synthetic corpus for local repair/audit testing

Drives `apps/knowledge-flow-backend/knowledge_flow_backend/scripts/seed_synthetic_corpus.py`:
writes fake libraries (tags), documents (Postgres metadata), vectors (OpenSearch), and small
fake content objects (Minio/S3) directly into the stores knowledge-flow-backend itself reads —
no ingestion pipeline, no LLM cost per document (only one real embedding call, to learn the
configured vector dimension). Comes with a tested `--purge` that removes exactly what it created.

**LOCAL docker-compose only.** Before touching anything, confirm with the developer that
`apps/knowledge-flow-backend/config/.env`'s `CONFIG_FILE` points at `configuration_prod.yaml`
(their local full-stack config: `localhost` Postgres/OpenSearch/OpenFGA/Keycloak/Minio) — never
run this against a shared/staging/prod `CONFIG_FILE`. Run all commands from
`apps/knowledge-flow-backend`, cwd matters (`.env` is loaded relative to it).

## The one gotcha that will burn you: `--team-id` is NOT the team's display name

Fred team names ("fredlab", "northbridge", ...) and their real `team_id` are different strings.
`--team-id` writes tag ownership (Postgres `tag.owner_id`) and a ReBAC tuple
(`team:<id>` OWNER `tag:<id>`) — if you pass the display name literally, you create tags owned by
a team object that doesn't exist in OpenFGA. Nobody can see them: `schema.fga`'s `tag.read`
resolves through `team_member from owner`, so zero members on a nonexistent team means zero
visibility, silently — no error anywhere, the seed step reports success.

Resolve the real id first:

```bash
docker exec -i app-postgres psql -U fred -d fred -c "SELECT id, name FROM teammetadata;"
```

Use the `id` column (a 32-char hex string) for `--team-id`, not `name`. If the developer only gave
you a display name (e.g. "fredlab"), look it up here — don't ask them for the id, they likely
don't have it memorized either.

To double check a seed actually landed somewhere visible (don't just trust "0 errors" in the
script's own log), get the developer's Keycloak `user:<uid>` (e.g. from `identity.uploaded_by` on
one of their real, non-seed documents) and check directly against OpenFGA:

```bash
STORE_ID=$(curl -s -H "Authorization: Bearer $OPENFGA_API_TOKEN" http://localhost:9080/stores | python3 -c "import sys,json;print(json.load(sys.stdin)['stores'][0]['id'])")
curl -s -H "Authorization: Bearer $OPENFGA_API_TOKEN" -H "Content-Type: application/json" \
  -X POST "http://localhost:9080/stores/$STORE_ID/check" \
  -d '{"tuple_key": {"user": "user:<uid>", "relation": "read", "object": "tag:<one seed tag id>"}}'
```
Expect `{"allowed": true}`. **Check a `document:<one seed document_uid>` too, not just the
tag** — the tag/folder resolving to `allowed: true` does NOT mean its documents do; they're a
separate ReBAC object (see the parent-tuple gotcha above). A folder that opens empty in the UI
means you checked the tag and stopped one level too early. `OPENFGA_API_TOKEN` is in
`apps/knowledge-flow-backend/config/.env`.

## Recommended flow — pilot before scale, every time

Don't jump straight to 100 libraries / 20000 documents. The sequence that actually caught real
bugs (a dropped-mapping-field purge marker, then the team-id mistake above) was:

1. **Baseline**: record current counts before touching anything —
   ```bash
   cd apps/knowledge-flow-backend
   .venv/bin/python - <<'EOF'
   import asyncio, logging
   logging.basicConfig(level=logging.CRITICAL)
   from knowledge_flow_backend.application_context import ApplicationContext
   from knowledge_flow_backend.common.config_loader import load_configuration

   async def main():
       ApplicationContext(load_configuration())
       app_context = ApplicationContext.get_instance()
       print("docs:", await app_context.get_metadata_store().count_all())
       print("tags:", len(await app_context.get_tag_store().list_all_tags()))
       vs = app_context.get_create_vector_store(app_context.get_embedder())
       print("vectors:", vs.client.count(index=vs.index_name).get("count"))
       print("content prefixes:", len(app_context.get_content_store().list_document_uids()))

   asyncio.run(main())
   EOF
   ```
2. **Pilot** at tiny scale (`--libraries 2 --documents 5`) with the real `--team-id`.
3. **Verify** counts increased by exactly the pilot size, and content is actually readable
   (`content_store.get_content(document_uid).read()`), not just present.
4. **Purge** (`--purge`) and re-run step 1's baseline query — must match the original numbers
   exactly (docs, tags, vectors, *and* content prefixes). If it doesn't, stop and figure out why
   before scaling up — don't seed 20000 documents on top of an unproven purge.
5. **Full scale** only after step 4 passes.

## Commands

```bash
cd apps/knowledge-flow-backend

# Seed (content objects included by default; add --skip-content to skip them: faster,
# but every document then shows up as `missing_content` in audit tooling)
.venv/bin/python -m knowledge_flow_backend.scripts.seed_synthetic_corpus \
  --team-id <real team_id from teammetadata> --libraries 100 --documents 20000

# Reset everything this script created (source_tag=seed-synthetic-corpus /
# seed-library-* tags/tuples/vectors/content) -- never touches anything else
.venv/bin/python -m knowledge_flow_backend.scripts.seed_synthetic_corpus --purge
```

Both commands commonly run past the 120s foreground timeout at full scale (~2-3 min for 20000
documents) — launch in the background and read the output file rather than waiting inline.

## What it actually writes (so you know what "reset" means)

- Postgres `tag` rows: `owner_id=<team_id>`, `name=seed-library-NNN`, type `document`.
- ReBAC tuple: `team:<team_id>` OWNER `tag:<tag_id>` (one per library) — makes the *folder* visible.
- Postgres `metadata` rows: `source.source_tag=seed-synthetic-corpus`, one fake vector chunk id
  `<document_uid>::seed-chunk-0`, round-robin across the libraries.
- ReBAC tuple: `tag:<tag_id>` PARENT `document:<document_uid>` (one per document) — makes each
  *document inside the folder* visible. `schema.fga`: `document.read = read from parent`. Miss
  this one and the folder itself is visible but opens onto "Ce dossier est vide" / an empty
  `get_document_metadata_in_tag` result — the tag being readable does not imply its documents are;
  they're a separate ReBAC object with their own relation. This bit the first real run of this
  script (folder visible, empty) before the tuple was added — don't skip it.
- OpenSearch: one random vector per document, dimension read from the *existing* index mapping
  (never assume a dimension — a mismatch fails loudly at `ensure_ready()`, which is correct).
- Minio/S3 (unless `--skip-content`): one small text object per document at
  `<document_uid>/input/<document_name>` — enough for `get_content()`/previews to actually work,
  not just for the content-store presence check to pass.

`--purge` reverses all four using the Postgres rows found via `source_tag` as the index (matches
what `MetadataService.audit_stores`-style tooling should also do) — read the script's `_purge`
docstring/comments if you need the exact matching logic, it documents its own known gaps (e.g. a
content object orphaned by a run that died mid-way between the content and metadata-delete steps
won't be found by a later purge, since content objects carry no marker of their own).
