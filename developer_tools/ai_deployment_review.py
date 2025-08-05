# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
import subprocess # nosec
import time
from io import StringIO
from pathlib import Path

from dotenv import load_dotenv
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from rich.console import Console
from rich.markdown import Markdown
from ruamel.yaml import YAML


# --------------------
# Logging Setup
# --------------------
def setup_logging(verbose: bool = False):
    log_level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Quiet noisy libraries
    if log_level > logging.DEBUG:
        for noisy in ["httpx", "httpcore", "openai"]:
            logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger("ai-rag-review")

# --------------------
# Settings
# --------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENT_GLOBS = [
    "deploy/charts/**/*.yaml",
    "deploy/charts/**/*.yml",
    "deploy/docker-compose/*.yml",
]

OPENAI_MODEL = "gpt-4"
yaml_parser = YAML()

# --------------------
# Chunking Utilities
# --------------------
def fallback_chunk_helm_template(content: str, file_path: str) -> list[Document]:
    blocks, current = [], []

    for line in content.splitlines():
        if line.strip() == "" or line.strip().startswith("#"):
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)

    if current:
        blocks.append("\n".join(current))

    return [
        Document(page_content=block, metadata={"file": file_path, "block": i})
        for i, block in enumerate(blocks) if block.strip()
    ]

def chunk_yaml_blocks(yaml_text: str, file_path: str) -> list[Document]:
    try:
        parsed = yaml_parser.load(yaml_text)
    except Exception as e:
        # debug logging it only is relevant for developper not users
        logger.debug(f"YAML parsing failed for {file_path}: {e}")
        return []

    if not isinstance(parsed, dict):
        return [Document(page_content=yaml_text, metadata={"file": file_path, "block": 0})]

    docs = []
    for i, (key, value) in enumerate(parsed.items()):
        stream = StringIO()
        yaml_parser.dump({key: value}, stream)
        chunk = stream.getvalue()
        docs.append(Document(page_content=chunk, metadata={"file": file_path, "block": i}))
        logger.debug(
            f"✅ Parsed block {i} from {file_path} [key={key}] ({len(chunk.splitlines())} lines)"
        )

    return docs

# --------------------
# Environment Loading
# --------------------
def load_environment(dotenv_path: str = "./config/.env"):
    if load_dotenv(dotenv_path):
        logger.debug(f"✅ Loaded environment variables from: {dotenv_path}")
    else:
        logger.warning(f"⚠️ No .env file found at: {dotenv_path}")

# --------------------
# Git Diff Helper
# --------------------
def get_git_diff(path: str) -> str:
    abs_path = Path(path).resolve()
    try:
        rel_path = abs_path.relative_to(PROJECT_ROOT)
    except ValueError:
        logger.error(f"❌ Path '{abs_path}' is outside the repo root: {PROJECT_ROOT}")
        return ""

    cmd = ["git", "diff", "--", str(rel_path)]
    logger.info(f"📁 Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT) # nosec
    if result.returncode != 0:
        logger.error(f"❌ Git diff failed: {result.stderr.strip()}")
        return ""
    return result.stdout

# --------------------
# Diff Parsing
# --------------------
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
                if key.isidentifier():
                    keys.append(key)
    return sorted(set(keys))

# --------------------
# Vector Index Builder
# --------------------
def build_vector_index() -> FAISS:
    docs, total_files = [], 0

    for pattern in DEPLOYMENT_GLOBS:
        matched = list(PROJECT_ROOT.glob(pattern))
        logger.debug(f"🔍 Pattern `{pattern}` matched {len(matched)} files")

        for file_path in matched:
            if not file_path.is_file():
                continue

            total_files += 1
            try:
                logger.debug(f"📄 Reading file: {file_path}")
                content = file_path.read_text(encoding="utf-8")
                file_docs = chunk_yaml_blocks(content, str(file_path))

                if not file_docs:
                    logger.debug(f"🌀 Falling back to Helm-style chunking: {file_path}")
                    file_docs = fallback_chunk_helm_template(content, str(file_path))

                docs.extend(file_docs)
                logger.debug(f"🧩 Extracted {len(file_docs)} blocks from {file_path}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to read {file_path}: {e}")

    logger.info(f"📦 Deployment files indexed: {total_files}")
    logger.info(f"🧱 YAML/Helm blocks before splitting: {len(docs)}")

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=256, chunk_overlap=0)
    chunks = splitter.split_documents(docs)

    logger.info(f"🧠 Chunks after token-aware splitting: {len(chunks)}")

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        logger.error("❌ OPENAI_API_KEY not found in environment.")
        raise RuntimeError("Missing OPENAI_API_KEY")

    embeddings = OpenAIEmbeddings(openai_api_key=openai_key)
    return FAISS.from_documents(chunks, embeddings)

# --------------------
# Deployment Context Retrieval
# --------------------
def retrieve_deployment_context(keys: list[str], store: FAISS, k: int = 10) -> list[str]:
    retrieved = []
    for key in keys:
        results = store.similarity_search(key, k=k)
        for r in results:
            file = r.metadata.get("file", "unknown")
            label = (
                f"block {r.metadata.get('block')}"
                if "block" in r.metadata
                else f"line {r.metadata.get('line', '?')}"
            )
            retrieved.append(f"# {file} ({label})\n{r.page_content}")
    return list(dict.fromkeys(retrieved))  # deduplicate

# --------------------
# Prompt Construction
# --------------------
def build_prompt(diff: str, context: list[str]) -> str:
    return f"""
You are a senior AI reviewer for a DevOps and Python platform.

Your task is to check whether the Python config model (typically a Pydantic BaseModel) is aligned
with the deployment files (YAML, Helm, Dockerfile, etc).
Please format the response using Markdown (use code blocks, headers, and bold text where 
appropriate) so it can be rendered nicely in a terminal."

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
""".strip()

# --------------------
# CLI Entry Point
# --------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, default=str(PROJECT_ROOT), help="Path to diff")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt without GPT call")
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging")
    args = parser.parse_args()

    global logger
    logger = setup_logging(verbose=args.verbose)

    load_environment()

    diff = get_git_diff(args.path)
    if not diff.strip():
        logger.info("✅ No changes detected in diff.")
        return

    keys = extract_changed_keys_from_diff(diff)
    logger.info(f"🔑 Extracted keys from diff: {keys}")

    start = time.time()
    store = build_vector_index()
    logger.info(f"⏱️ Vector index built in {time.time() - start:.2f}s")

    context_lines = retrieve_deployment_context(keys, store)
    prompt = build_prompt(diff, context_lines)

    if args.dry_run:
        print("\n\n====== START PROMPT (DRY RUN) ======\n")
        print(prompt)
        print("\n====== END PROMPT (DRY RUN) ======\n\n")
        return

    import openai
    openai.api_key = os.getenv("OPENAI_API_KEY")
    if not openai.api_key:
        logger.error("Missing OPENAI_API_KEY")
        return
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    console = Console()
    md = Markdown(response.choices[0].message.content)
    console.print(md)


if __name__ == "__main__":
    main()
