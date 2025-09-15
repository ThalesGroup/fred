# Semantic Search (Semantic)

**Who is this for?**  
Data scientists, architects, and users who want **fast**, **concept-oriented** results using AI embeddings only—no keyword or phrase matching.

---

## What it does (in plain language)

Semantic relies purely on **semantic similarity**: it embeds your question and the document chunks into the same vector space and returns the closest chunks. This means it can match **paraphrases** and **related concepts** even when wording doesn’t line up exactly.

- ✅ Great at **conceptual questions** and **natural language** prompts  
- ✅ Works the same across backends (no keyword index required)  
- ⚠️ Not designed for **exact tokens** (IDs, error strings, config keys)

---

## When to pick **Semantic**

Choose Semantic if you:
- Want **lowest latency** and minimal infrastructure.
- Are **exploring** a topic or asking open-ended questions.
- Run in a **dev/demo** environment without a keyword/phrase index.
- Have a corpus where exact matching isn’t critical, and **paraphrase recall** matters more.

**Examples**
- “Explain autoscaling trade-offs for batch processing.”  
- “What are the security considerations for multi-tenant APIs?”  
- “How does our agent framework orchestrate long-running tasks?”

---

## When **Hybrid** or **Strict** may be better

- **Hybrid** (default): Balanced results. Best when your query mixes **natural language** and **specific tokens** (like `SLA`, `CVE-2024-xxxx`, `max.poll.interval.ms`).  
- **Strict**: Precision-first. Best when **false positives are costly** (audits, policy lookups). Requires keyword/phrase support.

---

## What you’ll see in the UI

- A list of passages ranked by **semantic closeness** (often with a similarity indicator).
- Results may include **relevant paraphrases** you didn’t type verbatim.
- If your query is short or very specific (e.g., an error code), results may be **too broad**—that’s expected with semantic-only.

> Tip: If you need exact terms, switch to **Hybrid** or add a couple of precise tokens to your query.

---

## Why choose Semantic

- **Speed & simplicity**: no keyword index; fewer moving parts.  
- **Portability**: consistent behavior across storage backends.  
- **Great for ideation**: surfaces related concepts you might not think to type.

---

## Performance notes

- Usually the **fastest** option, especially on small/medium corpora.  
- Quality depends on your **embedding model** and **chunking**. Better titles and structured context improve results.

---

## Quick decision guide

| Your situation | Best first choice | Why |
|---|---|---|
| Concept exploration / brainstorming | **Semantic** | Fast, paraphrase-friendly |
| Mixed query (words + IDs/keys) | **Hybrid** | Balances semantic + exact terms |
| Compliance / exact policy text | **Strict** | High precision, low noise |

---

## FAQs

**Q: I searched an error code and got fuzzy results.**  
**A:** Semantic doesn’t boost exact tokens. Add the token plus a couple of words, or switch to **Hybrid/Strict**.

**Q: Does Semantic need special indexing?**  
**A:** No—just embeddings. That’s why it’s great for dev/demo environments.

**Q: Why is it the fastest?**  
**A:** It performs a single semantic search—no keyword or phrase pass.

---

## Summary

Pick **Semantic** when you want **speed** and **concept coverage** with minimal setup.  
Switch to **Hybrid** for mixed/token-heavy queries or **Strict** when correctness beats coverage.
