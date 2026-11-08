# Verification

## Automated (2026-11-08, on the simplified chat-image-pixels-every-turn branch, stacked on chat-image-descriptions)

| Suite | Passed | Risky paths covered |
| --- | --- | --- |
| fred-runtime `test_react_vision_attachments.py` | 41 | 5 newest images, by mime or file extension as in the frontend, on the first human message of every call, fetched once, not checkpointed; description omitted, SVG facts kept; unusable previews (404 at debug, 503, HTML, corrupt, mistyped, over 4 MiB) skipped with a uid log; inventory 404/500 and a 5 s timeout fall back; pre-filter on the attachments context, no read without a team and conversation; run stops from inventory and preview stop the run before any model call; history reserve, turn without pixels when only text fits, too large still refused; provider 400 retried once without pixels, 401/403/429/5xx, no-image 400 and run stops raised unchanged, no provider body in logs |
| fred-runtime frame, trim, prompting, read scope, rate limit, token totals, credential paths | 8, 12, 65, 9, 17, 23, 36 | unchanged suites re-run |
| Knowledge Flow `test_attachment_preview.py` | 11 | PNG and photo JPEG stored and served (`no-store`); other user, other session, malformed uid 404; `session_id` required; fast delete removes it, a malformed uid or missing preview is a no-op; over 4 MiB not stored; busy 503 then recovery with the slot given back; uid checked before any read, object before ownership, no chunks refused |
| Knowledge Flow `test_fast_lite_image_processor.py` | 23 | preview kept without a describer: photo JPEG, flat chart, transparent and SVG PNG, huge image none, no spurious log; the describer still gets a PNG when the preview is a JPEG |
| Knowledge Flow svg summary, fast ingest registry, fast delete authz, authz matrix | 20, 2, 14, 1 | re-run |
| Frontend `useChatAttachments.test.ts`, `.batch.test.tsx` | 8, 4 | no second argument; a ready image listed before the list refetch |

ruff check, `--select I`, format check and basedpyright on touched Python files: clean. `tsc --noEmit`, prettier: clean. Knowledge Flow client regenerated, second run identical. Each guard was disabled in turn: every one fails a test.

## Live checks

- Sessions 272e5ab8 and cf8ac281 (owner, 2026-11-07): pixels on every turn, previews 200 in 27-40 ms, no tool call; session erasure removed both previews from MinIO.
- Prompt cache, mistral-medium-latest, 3,300-token prompt, turns 2-4: 92-94% cached with images on the first human message, 64-66% on the last; nothing cached under about 1,000 tokens.

## Performance and consumption

No blocking call or cross-request state: the middleware is per request, reads use the shared async clients, previews are fetched concurrently outside `llm.call_latency_ms`, Knowledge Flow store calls run in its own bounded pool. Image tokens count in consumption from the provider's own usage (`model_metadata.py` `usage_metadata`, summed per turn into `agent.turn_completed`); the history reserve is an estimate used only to size the trim.

## Considered, not applied

- An image share of the history budget: 5 images cost at most about 22,000 of 200,000 characters, and a turn that does not fit already drops its pixels.
- Fast delete tolerant of a down content store: erasure should fail visibly.
- A fallback-rate metric: additive follow-up.
- Shorter MinIO timeouts for previews: the client is shared; the read pool and 503 bound the cost.

## Not proven

Load at 200 users (5 photo previews per call, 0.1-0.7 MB each); prompt caching on providers other than Mistral; Deep and Graph agents (out of scope).
