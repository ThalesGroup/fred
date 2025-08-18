# app/core/rag/rag_prompt.py
from datetime import datetime

def base_rag_preamble(now: str | None = None) -> str:
    now = now or datetime.now().strftime("%Y-%m-%d")
    return (
        "You are an assistant that answers questions strictly from the retrieved document chunks. "
        "Always cite claims using bracketed numeric markers like [1], [2], matching the provided sources. "
        "Be concise, factual, and note when evidence is weak or missing.\n"
        f"Current date: {now}.\n"
    )

def build_question_prompt(base_preamble: str, question: str, sources_block: str) -> str:
    return (
        f"{base_preamble}\n"
        "Use ONLY the sources below. When you state a fact, append a citation like [1] or [1][2]. "
        "If the sources disagree, say so briefly.\n\n"
        f"Question:\n{question}\n\n"
        f"Sources:\n{sources_block}\n"
    )
