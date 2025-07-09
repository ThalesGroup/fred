# app/features/code_search/service.py
from app.application_context import ApplicationContext
from app.features.code_search.code_loader import load_code_documents


class CodeSearchService:
    def __init__(self):
        context = ApplicationContext.get_instance()
        embedder = context.get_embedder()
        self.vector_store = context.get_vector_store(embedder)

    def similarity_search_with_score(self, query: str, k: int = 10):
        return self.vector_store.similarity_search_with_score(query, k=k)
    
    def scan_codebase(self, path: str):
        return load_code_documents(path)

    def index_documents(self, docs: list):
        self.vector_store.add_documents(docs)

