#!/usr/bin/env python

"""
AI Deployment Review with RAG-style Prompting

- Uses LangChain FAISS vector store in-memory
- Indexes all deployment files (YAML, Docker, Terraform, etc.)
- Parses Git diff to extract config field changes in Python
- Retrieves relevant deployment context chunks
- Builds a GPT-4 prompt and either prints it (--dry-run) or sends it
"""

import argparse
import logging
import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

import openai
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

# --- 0. Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ai-rag-review")

# --- 1. Settings ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENT_GLOBS = [
    "deploy/charts/**/*.yaml",
    "deploy/charts/**/*.yml",
    "deploy/charts/**/*.tpl",
    "deploy/Dockerfile*",
    "deploy/docker-compose/*.yml",
    "deploy/terraform/**/*.tf",
]

OPENAI_MODEL = "gpt-4"


# --- 2. Helper: run shell command ---
def get_git_diff() -> str:
    cmd = ["git", "diff", "origin/main...HEAD"]
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    return result.stdout


# --- 3. Extract relevant lines from Python diff ---
def extract_changed_keys_from_diff(diff_text: str) -> list[str]:
    keys = []
    for line in diff_text.splitlines():
        if line.startswith("+") or line.startswith("-"):
            if any(k in line for k in [":", "="]):
                line = line.strip("+- ")
                if ":" in line:
                    key = line.split(":")[0].strip()
                elif "=" in line:
                    key = line.split("=")[0].strip()
                else:
                    continue
                if key.isidentifier():
                    keys.append(key)
    return list(sorted(set(keys)))


# --- 4. Index deployment files in memory ---
def build_vector_index() -> FAISS:
    docs = []
    for pattern in DEPLOYMENT_GLOBS:
        for file_path in PROJECT_ROOT.glob(pattern):
            if file_path.is_file():
                try:
                    content = file_path.read_text(encoding="utf-8")
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        docs.append(
                            Document(
                                page_content=line, metadata={"file": str(file_path), "line": i}
                            )
                        )
                except Exception as e:
                    logger.warning(f"Failed to read {file_path}: {e}")

    logger.info(f"Indexing {len(docs)} lines from deployment files")

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=256, chunk_overlap=0
    )
    chunks = splitter.split_documents(docs)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        logger.error("OPENAI_API_KEY not found in environment.")
        raise RuntimeError("Missing OPENAI_API_KEY")

    embeddings = OpenAIEmbeddings(openai_api_key=openai_key)
    return FAISS.from_documents(chunks, embeddings)



# --- 5. Retrieve relevant deployment lines ---
def retrieve_deployment_context(keys: list[str], store: FAISS, k: int = 10) -> list[str]:
    retrieved = []
    for key in keys:
        results = store.similarity_search(key, k=k)
        for r in results:
            retrieved.append(
                f"# {r.metadata['file']} (line {r.metadata['line']})\n{r.page_content}"
            )
    return list(dict.fromkeys(retrieved))  # deduplicate


# --- 6. Build GPT prompt ---
def build_prompt(diff: str, context: list[str]) -> str:
    prompt = f"""
You are a senior AI reviewer for a DevOps and Python platform.

Your task is to check whether the Python config model (typically a Pydantic BaseModel) is aligned with the deployment files (YAML, Helm, Dockerfile, etc).

Please:
- Detect renamed or missing fields between Python and the deployment files
- Identify unreferenced or obsolete fields in Helm/Docker
- Suggest improvements to avoid deployment issues

Python diff:
```
{diff.strip()}
```

Relevant deployment context:
```
{os.linesep.join(context)}
```
"""
    return prompt.strip()


# --- 7. Run CLI ---
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the prompt without calling GPT"
    )
    args = parser.parse_args()

    diff = get_git_diff()
    if not diff.strip():
        logger.info("No changes detected.")
        return

    keys = extract_changed_keys_from_diff(diff)
    logger.info(f"Extracted keys from Python diff: {keys}")

    store = build_vector_index()
    context_lines = retrieve_deployment_context(keys, store)

    prompt = build_prompt(diff, context_lines)

    if args.dry_run:
        print("\n====== PROMPT (DRY RUN) ======\n")
        print(prompt)
        return

    openai.api_key = os.getenv("OPENAI_API_KEY")
    if not openai.api_key:
        logger.error("Missing OPENAI_API_KEY")
        return

    response = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    print("\n===== REVIEW =====\n")
    print(response.choices[0].message.content.strip())


if __name__ == "__main__":
    main()
