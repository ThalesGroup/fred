## Decisions

- **Deterministic, every turn.** Owner decision: never rely on the model deciding to look. *Rejected:* attach-turn browser pixels (`chat-image-vision-turn`, dropped), a look-again tool.
- **Versus OpenCode.** Same core: pixels stored and resent every turn. OpenCode keeps the original file (25 MiB cap), drops old images with a "read it again" note, errors on non-vision models and reads SVG as text. Here: a bounded preview, the 5 newest images, the description as fallback, SVG rendered plus exact facts.
- **Pixels only for an image sent as pixels.** Replay on one chart question (mistral-medium-latest): image only correct and stable; description plus image unstable; description only invented. Earlier 30-question eval: description 14 correct, pixels 19, both 17. SVG markup facts are exact, so they stay.
- **On the first human message.** The request prefix stays stable across calls and turns while the set is unchanged, so provider prompt caching applies (3,300-token prompt: 92-94% cached from turn 2, against 64-66% on the last message).
- **Preview in the Knowledge Flow content store**, outside the per-document tree, deleted by the fast delete. Read: the caller owns a chunk of the document in the named session; otherwise 404, never 403 (a delegated caller reads 403 as lost authority). Control-plane is ruled out: CONTROL-PLANE-PRODUCT-CONTRACT.md §3.9 forbids binary content there.
- **JPEG for photos, PNG for drawings.** Resent on every call, so bytes matter: an opaque preview is kept as JPEG q85 only below 70% of its PNG size (photos 7-18%, a flat bar chart 139% so it stays PNG). Transparent images and SVG renderings stay PNG. JPEG saves bytes, not tokens. The describer still gets a PNG.
- **History budget.** The size trim runs before the images are added, so it reserves their cost (`w*h/750` tokens at 1.35 chars/token, from the header). A turn that fits only without them goes without pixels instead of `ChatTurnTooLargeError`. 5 images cost at most about 22,000 of the 200,000 characters, so no separate image share is needed.
- **Failures.** One unusable preview skips that image only. A run stop stops the run. The fetch is bounded to 5 s. A provider 4xx other than 401/403/429 is retried once without pixels; throttling and server errors stay with the retry middleware. Knowledge Flow runs at most 8 preview reads in its own pool and answers 503 past a 0.5 s wait, which the runtime skips.
- **When to fetch.** Skipped when the attachments context lists no image; asked when that field is absent (API callers, queued messages).

## Open question for reviewers

Storing previews partly reopens the decision that fast-ingest chat attachments keep no raw copy (FILES-04 note in `ingestion_controller.py`). The preview is bounded, not the file, and goes with the attachment: acceptable, or should it live elsewhere?

## Risks

- Up to 5 images on every vision call: token cost and latency. Bounded size, JPEG for photos, prompt cache; image tokens count in consumption; migration note `minor`.
- Previews of attachments never recorded in control-plane are not erased with the session: same gap as their vectors.
