"""In-process LangChain tool for Knowledge Flow vector search."""

from .langchain_tools import build_kf_vector_search_tools

__all__ = ["build_kf_vector_search_tools"]
