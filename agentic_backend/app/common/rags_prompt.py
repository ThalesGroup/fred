# app/core/rag/rag_prompt.py
from datetime import datetime

def rag_preamble(now: str | None = None) -> str:
    now = now or datetime.now().strftime("%Y-%m-%d")
    return (
        "You are an assistant that answers questions strictly based on the retrieved document chunks. "
        "Always cite your claims using bracketed numeric markers like [1], [2], etc., matching the provided sources list. "
        "Be concise, factual, and avoid speculation. If evidence is weak or missing, say so.\n"
        f"Current date: {now}.\n"
    )

def build_rag_prompt(preamble: str, question: str, sources_block: str) -> str:
    return (
        f"{preamble}\n"
        "Use ONLY the sources below. When you state a fact, append a citation like [1] or [1][2]. "
        "If the sources disagree, say so briefly.\n\n"
        f"Question:\n{question}\n\n"
        f"Sources:\n{sources_block}\n"
    )
