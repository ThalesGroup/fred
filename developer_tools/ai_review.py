#!/usr/bin/env python

import fnmatch
import os
import argparse
import subprocess  # nosec B404
import logging
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.logging import RichHandler
import openai

# Initialize logging and console
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False, show_path=False)],
)
logger = logging.getLogger("ai-deploy-review")
console = Console()

# Constants
SCRIPT_NAME = "developer_tools/ai_review.py"
SUPPORTED_MODES = ["committed", "uncommitted", "all", "working"]
DOTENV_PATH = Path("config/.env")
GUIDELINES_PATH = Path("../docs/PYTHON_CODING_GUIDELINES.md")
CONTRIBUTING_PATH = Path("../docs/CONTRIBUTING.md")


def load_environment():
    logger.debug("Loading environment variables from .env")
    load_dotenv(dotenv_path=DOTENV_PATH)
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("Missing OPENAI_API_KEY. Please set it in config/.env")
        exit(1)

    for key in ["OLLAMA_BASE_URL", "AZURE_OPENAI_API_KEY", "AZURE_API_KEY"]:
        if os.getenv(key):
            logger.warning(f"Environment variable {key} is set, but only OpenAI is supported.")

    return openai.OpenAI()


def load_guidelines() -> str:
    logger.debug("Loading guidelines and contributing rules")
    return f"{GUIDELINES_PATH.read_text()}\n{CONTRIBUTING_PATH.read_text()}"


def get_git_diff(mode: str, patterns: List[str]) -> Tuple[str, List[str]]:
    logger.info(f"Getting git diff in {mode} mode for patterns: {patterns}")
    if mode == "committed":
        cmd = ["git", "diff", "origin/main...HEAD", "--name-only"]
    elif mode == "uncommitted":
        cmd = ["git", "diff", "--cached", "--name-only"]
    elif mode == "working":
        cmd = ["git", "ls-files", "--modified", "--others", "--exclude-standard"]
    else:
        cmd = ["git", "status", "--porcelain"]

    project_root = Path(__file__).resolve().parent.parent  # go up to project root
    logger.debug(f"Running command in root: {project_root}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root)  # nosec B603
    lines = result.stdout.strip().splitlines()
    logger.debug(f"Raw output from git command:\n{result.stdout}")

    collected, files = [], []

    logger.debug(f"Found {len(lines)} changed entries")

    for line in lines:
        logger.debug(f"Raw line: {line}")
        if mode == "all":
            parts = line.strip().split(maxsplit=1)
            path = parts[1] if len(parts) > 1 else ""
        else:
            path = line.strip()

        if not path:
            logger.debug("Skipping empty path")
            continue

        full_path = (project_root / path).resolve()
        logger.debug(f"Resolved path: {full_path}")
        if not full_path.is_file():
                logger.debug(f"Skipping non-file path: {full_path}")
                continue

        if SCRIPT_NAME in str(full_path):
            logger.debug(f"Skipping script file itself: {full_path}")
            continue

        matched = any(fnmatch.fnmatch(full_path.name, pat) for pat in patterns)
        logger.debug(f"Does file match any pattern? {matched}")
        if matched:
            logger.info(f"Processing file: {full_path}")
            try:
                content = full_path.read_text(encoding="utf-8")
                files.append(str(full_path))
                collected.append(f"# ==== FILE: {path} ====\n{content}\n")
            except Exception as e:
                logger.warning(f"Could not read {path}: {e}")

    logger.info(f"Collected {len(files)} file(s) for review")
    return "\n".join(collected), files


def review_with_gpt(client, guidelines: str, payload: str, review_type: str):
    logger.info(f"Starting GPT review in {review_type} mode")

    if review_type == "code":
        prompt = f"""
You are a senior software reviewer for a professional Python backend.

Here is the internal coding guide:
{guidelines}

Please review the following code changes and give feedback:
- Violations of structure (services, controllers, utils)
- Bad exception handling
- Missing tests, missing docstrings
- Violations of naming, layering, or Pydantic usage

Code:
```python
{payload}
```
"""
        title = "🧠 AI Code Review"
    else:
        prompt = f"""
You are a senior AI reviewer for a DevOps and Python platform.
Your job is to check if backend configuration models and deployment files (Helm, Docker) are aligned.

{guidelines}

Code and configuration to review:
```python
{payload}
```

Please:
- Detect renamed or missing config fields between Python and deployment files
- Identify unreferenced or unused fields in Helm/Docker
- Suggest improvements to avoid deployment failures
"""
        title = "🤖 AI Deployment Review"

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    console.print(Panel.fit(response.choices[0].message.content.strip(), title=title))


def main():
    parser = argparse.ArgumentParser(description="AI-based consistency checker for Python config vs Helm/K8s/Docker")
    parser.add_argument("--mode", choices=SUPPORTED_MODES, default="committed")
    parser.add_argument("--review-type", choices=["code", "deploy"], default="deploy")
    args = parser.parse_args()

    logger.info(f"Running AI review: mode={args.mode}, type={args.review_type}")

    client = load_environment()
    guidelines = load_guidelines()

    patterns = ["*.py"] if args.review_type == "code" else ["*.py", "*.yaml", "*.yml", "Dockerfile*", "*.sh"]
    payload, files = get_git_diff(args.mode, patterns)

    if not payload.strip():
        logger.info("No relevant changes detected for review.")
        console.print("[bold green]✅ No relevant changes to review.[/bold green]")
        return

    if files:
        logger.info("Reviewing the following files:")
        for f in files:
            logger.info(f" - {f}")

    review_with_gpt(client, guidelines, payload, args.review_type)


if __name__ == "__main__":
    main()
