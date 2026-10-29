# Call Knowledge Flow without the Fred SDK

These examples describe the mounted contract from source and OpenAPI. They have
not been executed against a running Fred deployment. They are integration
templates, not evidence of a validated Weaver journey. See the generated
[API reference](API_REFERENCE.md) for every request and response schema.

## Admission and the per-request context

An integration must already be an authorized delegated workload. Its bearer
token must satisfy KF's existing issuer, audience, caller-role and service-account
policy. Send the admitted `person`, `run` and `agent` as three query parameters
for both GET and POST. A person's token or an arbitrary service token does not
become authorized merely by including these parameters. Token provisioning and
turn admission are unchanged.

The runtime executing the agent builds the document context from its configuration
and the admitted turn, outside model-supplied tool arguments. Intersect configured
and turn selection clauses; never let model arguments replace or widen them.
Transmit one compact JSON object in `x-fred-document-context`, with no base64,
URL encoding or second JSON serialization. Send `Content-Type: application/json`
for a JSON body; it does not replace the context header.

```json
{"space_id":"00000000-0000-0000-0000-000000000001","document_scope":{"selections":[]}}
```

The identifiers here are placeholders, not provisioned resources. `space_id` and
scope identifiers use UUID syntax. The grant identifiers `person`, `run`, `agent`
follow their own existing identifier contract; do not infer they must be UUIDs.

| Scope value, inside an explicitly supplied context | Meaning |
| --- | --- |
| `{}` or `{"selections":[]}` | No additional selection filter within the admitted space; permissions, publication and lifecycle still apply |
| `{"selections":[{}]}` | Selects no documents; never falls back to the corpus |
| `{"selections":[{"folder_ids":["00000000-0000-0000-0000-000000000002"]}]}` | Direct contents of that folder, without recursive expansion |
| Multiple selections | Intersection of clauses; within each clause, folders and explicit documents form a union |

Searching an entire authorized corpus does not transmit every document UUID.
The first example has constant size regardless of corpus size. `dataset_uids`
and path/query document identifiers are business selections within this context.
They cannot grant access; KF checks the complete requested tabular subset.

Neither the body nor query can supply document authority. Extra fields in the
strict POST bodies are rejected; an extra query field is not a fallback and is
not guaranteed to be rejected by FastAPI. Use the declared query parameters only.

## curl: document search

Set `KF_BASE_URL` to the trusted deployment URL including its configured prefix,
for example `https://fred.example/knowledge-flow/v2`. Supply
`WORKLOAD_ACCESS_TOKEN`, `PERSON_ID`, `RUN_ID`, `AGENT_ID` and
`FRED_DOCUMENT_CONTEXT` from the admitted runtime. The context variable contains
the JSON object shown above, populated from that admission.

```sh
GRANT_QUERY=$(python3 - <<'PY'
import os
from urllib.parse import urlencode
print(urlencode({
    "person": os.environ["PERSON_ID"],
    "run": os.environ["RUN_ID"],
    "agent": os.environ["AGENT_ID"],
}))
PY
)

curl --fail-with-body --request POST \
  "${KF_BASE_URL%/}/documents/search?${GRANT_QUERY}" \
  --header "Authorization: Bearer $WORKLOAD_ACCESS_TOKEN" \
  --header "x-fred-document-context: $FRED_DOCUMENT_CONTEXT" \
  --header 'Content-Type: application/json' \
  --data '{"question":"Which deadlines apply?","top_k":10,"search_policy":"hybrid"}'
```

The body contains business arguments only. For the same admitted request context,
the following other document calls use the same headers and grant query:

| Method and path, relative to `KF_BASE_URL` | Additional query or body |
| --- | --- |
| GET `/documents/{document_uid}/chunks` | Query `limit=200` (1 to 1000) |
| GET `/documents/{document_uid}/markdown` | No body; response JSON has `content` |
| POST `/documents/{document_uid}/summarize` | `{"instruction":"Summarize deadlines","max_chars":2000}` |
| POST `/documents/{document_uid}/extract` | `{"instruction":"List deadlines and their context"}` |

URL-encode path identifiers as single segments. Retain the grant query when
adding business query parameters; do not put `space_id` or `document_scope` there.

## Python standard library: tabular discovery and query

This example requires no Fred package. It lists authorized documents, describes
one chosen document and uses an exact returned table alias for a bounded query.
In production, the application chooses the document using its business needs.
`document_uids` is a repeated query parameter, not a comma-separated string.

```python
import json
import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def call_kf(base, token, grant, context, path, *, query=(), body=None):
    # Fresh headers and parameters for this request. Context comes from admission.
    params = list(grant.items()) + list(query)
    headers = {
        "Authorization": "Bearer " + token,
        "x-fred-document-context": json.dumps(context, separators=(",", ":")),
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = Request(base.rstrip("/") + path + "?" + urlencode(params),
                      headers=headers, data=data)
    try:
        # Example client timeout, not a server-side execution guarantee.
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    except HTTPError as error:
        # Preserve HTTP status and distinguish string detail from 422 arrays.
        payload = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"KF HTTP {error.code}: {payload}") from error


def main():
    base = os.environ["KF_BASE_URL"]
    token = os.environ["WORKLOAD_ACCESS_TOKEN"]
    grant = {"person": os.environ["PERSON_ID"], "run": os.environ["RUN_ID"],
             "agent": os.environ["AGENT_ID"]}
    context = json.loads(os.environ["FRED_DOCUMENT_CONTEXT"])
    args = (base, token, grant, context)
    documents = call_kf(*args, "/tabular/documents")
    if not documents:
        print("No visible tabular documents in this selection.")
        return
    selected = [documents[0]["document_uid"]]
    descriptions = call_kf(*args, "/tabular/documents/schemas",
                           query=[("document_uids", uid) for uid in selected])
    if not descriptions or not descriptions[0]["tables"]:
        print("No queryable table returned for the selected document.")
        return
    alias = descriptions[0]["tables"][0]["query_alias"]
    relation = '"' + alias.replace('"', '""') + '"'
    result = call_kf(*args, "/tabular/query", body={
        "sql": f"SELECT * FROM {relation}",
        "dataset_uids": selected,
        "max_rows": 10,
    })
    print(json.dumps(result["rows"], ensure_ascii=False))


if __name__ == "__main__":
    main()
```

For value lookup, use POST `/tabular/search` with, for example,
`{"keyword":"Paris","dataset_uids":["00000000-0000-0000-0000-000000000003"],"max_rows_per_table":5,"max_matching_tables":30}`.
Replace the illustrative document ID with one returned by listing. Inspect
`tables_truncated` and each match's `rows_truncated` before interpreting results.

## Limits and partial results

Schema limits appear in the reference; additional service behavior matters:

| Operation or transport | Limit and interpretation |
| --- | --- |
| Context header | No Fred-specific cap/truncation. 1000 explicit document UUIDs in one compact selection take 39,120 ASCII bytes. h11 defaults to a 16 KiB incomplete-header-event limit; fragmented large headers may fail before KF. Uvicorn auto selects httptools when installed, otherwise h11. Proxy and deployed-server bounds remain to be verified; no universal accepted size is claimed |
| Search | `top_k` defaults to 10, maximum 100. Fewer hits or `[]` is valid; no pagination or exhaustive-coverage guarantee |
| Chunks | At most `limit` ordered chunks; no continuation or truncation flag. `[]` may mean no visible chunks or unsupported direct fetching, not proof of document absence |
| Markdown | Full published markdown, no API size cap or pagination. Budget client memory accordingly |
| Summary | `max_chars` is a target (200 to 20000), not a hard output bound; corrective rewriting can fail or still exceed it |
| Extraction | Input above 2,000,000 characters is reduced to head and tail. `truncated` reports this cap only; individual model window failures can yield partial results without setting it. A 200 is not proof of exhaustive extraction |
| Tabular list | No pagination or fixed response-count cap; scope the request when needed |
| Tabular schemas | 1 to 1000 document IDs in repeated query parameters; total described tables also bounded by configured `max_selected_datasets`. One workbook may contain several tables |
| Tabular query | `max_rows` defaults to configured `default_max_rows`, clamped to configured `max_rows`; no completeness flag or continuation. SQL must read at least one authorized alias. Omitted/null `dataset_uids` uses the authorized scope; `[]` selects nothing and returns 400 |
| Tabular search | Stripped keyword must have at least two characters and normalize to nonempty. At most 5 rows per table and 30 matching tables, with lower caller limits allowed. Dataset scan ceiling may truncate coverage; `[]` dataset selection returns 400 |

Tabular execution budgets live in `storage.tabular_store.query`. Source defaults
are 200 result rows, a 1000-row maximum, 50 selected tables, 2 concurrent jobs
and 4 queued jobs per process, 30 seconds, 1 DuckDB thread and 256 MB DuckDB
memory. These are configurable defaults, not universal deployment guarantees;
the DuckDB memory setting is not a bound on total process memory. Input/query
length and response size have no additional undocumented SDK limit. HTTP server
and proxy limits can also apply to the repeated-ID query string and request body.
No compression, context reference, storage service or implicit authority fallback
is introduced to bypass a transport limit.

## Rejections and caller handling

The following context outcomes assume valid existing delegated authentication;
authentication or admission failures can reject the request earlier. Submit an
otherwise valid business request when checking the specific error precedence.

| Example | Expected contract response, not an observed live result |
| --- | --- |
| Header omitted | 403 `{"detail":"document_context_required"}` |
| Header value `not-json`, `null`, `"{...}"`, missing `space_id`, bad UUID or extra context field | 400 `{"detail":"invalid_document_context"}` |
| Valid header, POST body additionally contains `space_id` or `document_scope` | 422 with validation-error array in `detail` |
| Tabular request names a document outside scope | 403; request is not partially authorized |
| Space pending deletion | 409 `{"detail":"space_pending_deletion"}` |
| Published markdown missing or not visible | 404 `{"detail":"document_not_found"}` |

Do not retry 400/422 without correcting the request, or widen a 403 context to
make a call pass. HTTP 404 is not an existence oracle. Existing authorization
errors may include `X-Fred-Denial-Cause`; not every 403/503 has this header.
503 can mean account-status checks unavailable, index unavailable or tabular
capacity exhausted. Apply bounded backoff for capacity, and diagnose the actual
cause rather than treating every 503 identically. For tabular 504, narrow the
selection/query before retrying. Infrastructure errors can be non-JSON or fail
before KF; do not assume every proxy response uses KF's error envelope.

## MCP transport

Use the existing MCP client protocol at `<KF_BASE_URL>/mcp/tabular`, carrying the
same bearer, grant query and JSON context header on the outer HTTP requests.
The projected tools are `list_tabular_documents`, `describe_tabular_documents`,
`query_tabular_documents` and `search_tabular_values`. Their arguments contain
only the business parameters described above. KF verifies the outer delegation,
removes any inner supplied authority header and forwards the outer context to
the REST dependency. Do not place authority in `tools/call` arguments or invent
an extra JSON-RPC envelope for it. MCP errors have the protocol's envelope;
the HTTP examples above describe the REST handlers, not a promised MCP wire shape.
