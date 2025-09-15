# Strict Search (Precision-First)

**Who is this for?**  
Data scientists, architects, and users who want *only* high-confidence answers, even if that means returning fewer (or zero) results.

---

## What it does (in plain language)

Strict Search is designed to **avoid false positives**. It combines:
- **Semantic match** (AI understanding of your question)
- **Keyword match** (classic exact-term relevance)
- **Optional exact phrase check** (literal string match)

A result is shown **only if** it passes semantic and keyword checks (and phrase when enabled). If evidence is weak, Strict returns **nothing** rather than guess.

> **Important:** Strict Search requires a backend with **keyword/phrase** capabilities (e.g., OpenSearch). If that isn’t available, the Strict option may be disabled in the UI.

---

## When to pick **Strict**

Choose Strict when:
- You need **high precision** and can’t afford noise (e.g., compliance, audits, change control).
- You’re searching for **identifiers, config keys, error codes**, or formal terms where literal match matters.
- You want results that your team can **quickly verify** (semantic + keyword agreement).

**Examples**
- “`max.poll.interval.ms` production default”  
- “CVE disclosure procedure for third-party libraries”  
- “GDPR Article 35 Data Protection Impact Assessment”  

---

## When **Hybrid** or **Semantic** may be better

- **Hybrid** (default): you want a balanced list—good for mixed queries that include both natural language and specific tokens.
- **Semantic** (fastest): you’re exploring concepts or phrasing questions naturally; speed and coverage matter more than literal matching.

---

## What you’ll see in the UI

- A **short list** of highly reliable snippets, often one per document.  
- Sometimes **no results** (by design) if nothing meets the strict criteria.  
- Confidence indicator reflects semantic agreement; items also had to satisfy keyword (and optional phrase) checks.

> Tip: If Strict returns nothing, add an **exact token** (e.g., a field name, code, or phrase). If you’re still seeing nothing, switch to **Hybrid** for a broader pass.

---

## Why this mode exists

- To minimize **false positives** in sensitive workflows (tickets, audits, SRE runbooks, policy lookups).
- To provide results that are **easy to defend**—they match both what you meant and what’s written.

---

## Performance notes

- Strict typically costs slightly more latency than Semantic-only (it runs multiple checks), but you’ll get **fewer, cleaner** results.
- If the backend lacks keyword/phrase support, Strict is not available (choose Hybrid or Semantic instead).

---

## Quick decision guide

| Your situation | Best first choice | Why |
|---|---|---|
| Compliance / audits / policies | **Strict** | High precision, low noise |
| Hunting exact tokens (IDs, keys) | **Strict** or **Hybrid** | Literal matching required |
| General Q&A / exploration | **Hybrid** | Balanced, robust |
| Speed & concept exploration | **Semantic** | Fastest, paraphrase-friendly |

---

## FAQs

**Q: Why did I get no results?**  
**A:** Nothing met the strict evidence gates. Add an exact term or switch to **Hybrid** for broader coverage.

**Q: Is Strict always better?**  
**A:** No—Strict trades **recall** for **precision**. Use it when wrong answers are costly; otherwise start with **Hybrid**.

**Q: Can Strict return duplicates from the same file?**  
**A:** It prefers **diversity**. You’ll usually see at most one top snippet per document.

---

## Summary

- Pick **Strict** when correctness beats coverage.  
- Expect **fewer, higher-confidence** results—and sometimes none.  
- If you need a broader net, switch to **Hybrid** (default) or **Semantic** for speed.
