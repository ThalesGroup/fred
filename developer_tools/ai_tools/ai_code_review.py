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

import argparse
import glob
import logging
import os
import subprocess  # nosec B404
from pathlib import Path

import openai
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

# Configure logging
logging.basicConfig(
    level="INFO",
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[RichHandler(rich_tracebacks=False, show_time=False, show_path=False)],
)
logger = logging.getLogger("ai-review")
console = Console()

# Load environment variables
load_dotenv(dotenv_path=Path("config/.env"))

# Warn if incompatible providers are configured
unsupported_keys = ["OLLAMA_BASE_URL", "AZURE_OPENAI_API_KEY", "AZURE_API_KEY"]
offenders = [key for key in unsupported_keys if os.getenv(key)]

if offenders:
    logger.warning("This script only supports OpenAI. Detected other configured providers:")
    for key in offenders:
        logger.warning(f"- {key} is set")

if not os.getenv("OPENAI_API_KEY"):
    logger.error("Missing OPENAI_API_KEY. Please set it in config/.env")
    exit(1)

client = openai.OpenAI()

# Load guidelines

PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[1]))
GUIDELINES = Path(PROJECT_ROOT / "docs/PYTHON_CODING_GUIDELINES.md").read_text()
CONTRIBUTING = Path(PROJECT_ROOT / "docs/CONTRIBUTING.md").read_text()

SCRIPT_NAME = "developer_tools/ai_review_pull_request.py"


def get_diff_committed():
    """Diff between origin/main and HEAD (committed changes), excluding this script"""
    files = glob.glob("*.py")
    if not files:
        return ""

    cmd = ["/usr/bin/git", "diff", "origin/main...HEAD", "--"] + files
    result = subprocess.run(cmd, capture_output=True, text=True)  # nosec B603
    return "\n".join(line for line in result.stdout.strip().splitlines() if SCRIPT_NAME not in line)


def get_diff_uncommitted():
    """Diff of staged files, excluding this script"""
    files = glob.glob("*.py")
    if not files:
        return ""

    cmd = ["/usr/bin/git", "diff", "--cached", "--"] + files
    result = subprocess.run(cmd, capture_output=True, text=True)  # nosec B603
    return "\n".join(line for line in result.stdout.strip().splitlines() if SCRIPT_NAME not in line)


def get_all_python_files_content():
    """Concatenate full content of all modified/untracked Python files, excluding this script"""
    result = subprocess.run(["/usr/bin/git", "status", "--porcelain"], capture_output=True, text=True)  # nosec B603
    lines = result.stdout.strip().splitlines()

    file_contents = []
    reviewed_files = []

    for line in lines:
        path = line[3:].strip()
        if path.endswith(".py") and os.path.isfile(path) and SCRIPT_NAME not in path:
            try:
                content = Path(path).read_text(encoding="utf-8")
                reviewed_files.append(path)
                file_contents.append(f"# ==== START FILE: {path} ====\n{content}\n# ==== END FILE ====\n")
            except Exception as e:
                logger.warning(f"Could not read {path}: {e}")

    return "\n".join(file_contents), reviewed_files


def review_code(payload: str):
    """Call OpenAI to review code"""
    prompt = f"""
You are a senior software reviewer for a professional Python backend.

Here is the internal coding guide:
{GUIDELINES}

And additional contribution rules:
{CONTRIBUTING}

Please review the following code changes and give feedback:
- Violations of structure (services, controllers, utils)
- Bad exception handling
- Missing tests, missing docstrings
- Violations of naming, layering, Pydantic usage

Code:
```python
{payload}
```
"""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    console.print(Panel.fit(response.choices[0].message.content.strip(), title="🧠 AI Review", subtitle="Code quality and compliance"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["committed", "uncommitted", "all"], default="committed")
    args = parser.parse_args()

    if args.mode == "committed":
        diff = get_diff_committed()
        reviewed_files = []  # Not tracked
    elif args.mode == "uncommitted":
        diff = get_diff_uncommitted()
        reviewed_files = []  # Not tracked
    elif args.mode == "all":
        diff, reviewed_files = get_all_python_files_content()
        if reviewed_files:
            logger.info("Reviewing the following files:")
            for f in reviewed_files:
                logger.info(f" - {f}")
    else:
        diff = ""
        reviewed_files = []

    if not diff.strip():
        console.print("[bold green]✅ No Python changes to review.[/bold green]")
        return

    review_code(diff)


if __name__ == "__main__":
    main()
