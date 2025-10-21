# Hybrid Search (Default)

**Who is this for?**  
Data scientists, architects, and curious users who want reliable search over mixed content (docs, notes, specs, code
snippets) without tuning lots of knobs.

---

## What it does (in plain English)

Hybrid Search blends two ways of finding relevant passages:

- **Semantic match** (AI “understands” your wording, even if terms don’t match exactly).
- **Keyword match** (classic search that prefers exact words and phrases).

It combines both rankings so items that are strong in **either** style float to the top. You’ll usually get:

- Better **recall** on paraphrased questions (semantic),
- Better **precision** on acronyms, codes, names, and exact terms (keyword),
- A balanced list with **diverse sources** (we avoid flooding from a single document).

> If keyword search isn’t available in the current backend, Hybrid quietly behaves like **Semantic** search—no errors,
> just a simpler result list.

---

## When to pick **Hybrid** (recommended default)

Choose Hybrid if your query:

- Mixes **short terms** (e.g., IDs, acronyms, proper names) and **natural language** (“SLA targets for GEO traffic in
  EMEA”).
- Needs **exact tokens** or **people names** to be noticed (error codes, config keys, Amartya Sen, Nussbaum, etc.).
- May be phrased in a way that doesn’t match the document text exactly (paraphrasing).

It’s also a great first pick when you’re **not sure** which mode is best.

---

## When **Semantic** might be better

Pick **Semantic** if:

- You want **speed** and your questions are naturally phrased.
- You’re exploring concepts (“explain autoscaling trade-offs for batch workloads”).
- Your corpus is well-embedded and exact token matching adds little value.

---

## When **Keyword** (Lexical) might be better

Pick **Keyword** if:

- You need **exact phrase** matches or strict filtering (e.g., `"KafkaConsumer" AND "max.poll.interval.ms"`).
- You’re hunting for **identifiers**, **error messages**, or **verbatim snippets**.
- You’re familiar with the vocabulary and want literal matches only.

---

## What you’ll see in the UI

- A ranked list of **passages** (snippets) from different documents.
- Usually **one or a few** passages per document (to keep variety).
- A confidence indicator driven by semantic similarity (useful for quick triage).
- Consistent behavior across libraries/tags you’ve selected.

> Tip: If your first results look close but not quite right, try adding 1–2 **specific words** (e.g., an acronym, a
> name, or a setting). Hybrid will pick that up.

---

## Why Hybrid is often best-in-class

- **Robust to phrasing** (semantic).
- **Precise on tokens and names** (keyword).
- **Fair fusion** (balances both rather than over-favoring one).
- **Name-evidence gate**: prevents semantically-related but irrelevant docs from surfacing if your query clearly names
  people.
- **Graceful fallback** (works even if keyword search isn’t available).

---

## Performance notes

- Hybrid does a bit more work than Semantic-only, so it may be **slightly slower**.  
  For most users, the quality gain is worth it. If you need the fastest response, use **Semantic**.

---

## Quick decision guide

| Your situation                 | Best first choice         | Why                      |
|--------------------------------|---------------------------|--------------------------|
| Unsure / general question      | **Hybrid**                | Balanced, robust results |
| Needs exact codes/IDs or names | **Hybrid** or **Keyword** | Exact terms matter       |
| Conceptual, long questions     | **Semantic**              | Paraphrase-friendly      |
| Strict phrase search           | **Keyword**               | Literal matching         |

---

## FAQs

**Q: Will Hybrid flood me with many snippets from the same file?**  
**A:** No—results are kept diverse, so you see the best from multiple documents.

**Q: I typed a short query and got “smart” but not exact answers.**  
**A:** Add one or two precise tokens (e.g., a name, acronym, or error code). Hybrid will boost exact matches.

**Q: Does Hybrid work everywhere?**  
**A:** Yes. If keyword search isn’t available in your current backend, it seamlessly falls back to semantic results.

---

## Summary

- **Default to Hybrid** for balanced, dependable search.
- Switch to **Semantic** for speed and open-ended questions.
- Switch to **Keyword** for strict, exact matches.

Hybrid makes it easy to start broad, stay precise on critical tokens or names, and avoid semantic drift into irrelevant
but related documents.
