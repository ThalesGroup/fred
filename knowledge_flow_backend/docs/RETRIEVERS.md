# Fred Retrieval Modes — Quick Guide

**Who is this for?**  
Data scientists, solution architects, product owners, and curious users choosing how search should behave in Fred.

---

## Summary (how to choose)

- **Hybrid (default)** — *AI + keywords*  
  Balanced results that work well for most queries. Great when your question mixes natural language with **specific tokens** (IDs, error codes, config keys).  
  ➜ If the backend has no keyword index, Hybrid gracefully falls back to Semantic behavior.

- **Semantic** — *AI only (fast)*  
  Best for **concept exploration** and paraphrased questions. Lowest latency and simplest setup.  
  Not ideal when you must match **exact tokens** or phrases.

- **Strict** — *precision-first*  
  Shows results **only** when both AI similarity and keyword evidence (and optionally an exact phrase) agree.  
  Great for **compliance**, **policy lookups**, and **change control**. May return **no results** by design. Requires keyword/phrase support.

---

## At a glance

| Mode       | Best for                                | Trade-off                  | Needs keyword index? |
|------------|-----------------------------------------|----------------------------|----------------------|
| **Hybrid** | Everyday use, mixed queries             | Slightly slower than AI-only | Optional (uses it when available) |
| **Semantic** | Conceptual / exploratory questions     | May miss exact tokens      | No                   |
| **Strict** | Compliance, exact tokens, low tolerance for noise | Fewer results, sometimes none | **Yes**               |

---

## Learn more

- Details & examples: **[Hybrid Retriever](./HYBRID_RETRIEVER.md)**
- Details & examples: **[Semantic (ANN-Only) Retriever](./SEMANTIC_RETRIEVER.md)**
- Details & examples: **[Strict Retriever](./STRICT_RETRIEVER.md)**

> Tip: Start with **Hybrid**. If you need speed, try **Semantic**. If wrong answers are costly, pick **Strict**.
