from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Basic service settings
    app_name: str = "cir-hipporag-service"
    debug: bool = False
    security_enabled: bool = False

    # HippoRAG tuning (env overrides)
    max_words_per_chunk: int = Field(
        default=220, description="Soft cap for markdown chunk size"
    )
    llm_base_url: str = Field(default="http://localhost:5911/v1")
    llm_model: str = Field(default="gpt-oss:120b")
    embedding_model: str = Field(default="facebook/mcontriever-msmarco")
    rerank_prompt_path: str = Field(
        default="", description="Path to rerank prompt JSON (HippoRAG dspy file)"
    )
    retrieval_top_k: int = 100
    linking_top_k: int = 10
    max_qa_steps: int = 3
    qa_top_k: int = 5
    graph_type: str = "relation_aware_passage_entity"
    embedding_batch_size: int = 8
    max_new_tokens: int = 512
    openie_mode: str = "online"
    save_openie: bool = False
    openie_model: str = "openie_openai_gpt"
    temperature: float = 0.0
    directed_graph: bool = True
    chunk_overlap_tokens: int = 0
    chunk_func: str = "by_token"

    class Config:
        env_prefix = "HIPPORAG_"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
