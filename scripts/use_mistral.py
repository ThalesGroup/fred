from __future__ import annotations

import argparse
from pathlib import Path


MISTRAL_CHAT_MODEL = "mistral-medium-latest"
MISTRAL_EMBEDDING_MODEL = "mistral-embed"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
MISTRAL_VECTOR_INDEX = "vector-index-mistral"
MISTRAL_PROFILE_IDS = {"default.chat.mistral", "default.language.mistral"}


def _indent_of(line: str) -> int:
    """Why: YAML block edits need stable indentation to avoid reformatting unrelated text.
    How: Count leading spaces on the original line and reuse that indentation in replacements.
    Example: `_indent_of("    key: value\\n") == 4`.
    """

    return len(line) - len(line.lstrip(" "))


def _find_block(lines: list[str], path: tuple[str, ...]) -> tuple[int, int]:
    """Why: We only want to edit known YAML sections without rewriting the full document.
    How: Walk the requested header path and return the start/end line indexes of the final block.
    Example: `_find_block(lines, ("storage:", "vector_store:"))`.
    """

    search_start = 0
    search_end = len(lines)
    parent_indent = -1
    block_start = -1

    for depth, header in enumerate(path):
        found = -1
        for index in range(search_start, search_end):
            stripped = lines[index].strip()
            if stripped != header:
                continue
            indent = _indent_of(lines[index])
            if depth > 0 and indent <= parent_indent:
                continue
            found = index
            parent_indent = indent
            break
        if found < 0:
            raise ValueError(f"Unable to find YAML block: {' > '.join(path)}")
        block_start = found
        next_start = found + 1
        next_end = search_end
        for index in range(next_start, search_end):
            stripped = lines[index].strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _indent_of(lines[index]) <= parent_indent:
                next_end = index
                break
        search_start = next_start
        search_end = next_end

    return block_start, search_end


def _replace_block(content: str, path: tuple[str, ...], replacement: str) -> str:
    """Why: Some targeted model sections are simpler to replace as blocks than field-by-field.
    How: Locate the YAML block by path, then splice in the replacement text with original neighbors untouched.
    Example: `_replace_block(text, ("chat_model:",), "chat_model:\\n  provider: openai\\n")`.
    """

    lines = content.splitlines(keepends=True)
    start, end = _find_block(lines, path)
    suffix_start = end
    trailing_separators: list[str] = []
    while suffix_start > start + 1 and (
        not lines[suffix_start - 1].strip()
        or lines[suffix_start - 1].lstrip().startswith("#")
    ):
        trailing_separators.insert(0, lines[suffix_start - 1])
        suffix_start -= 1
    return "".join(
        lines[:start]
        + replacement.splitlines(keepends=True)
        + trailing_separators
        + lines[end:]
    )


def _replace_line(content: str, path: tuple[str, ...], key: str, new_value: str) -> str:
    """Why: Scalar YAML fields like `index:` should change without disturbing surrounding formatting.
    How: Replace only the matching line inside the selected block and keep its original indentation.
    Example: `_replace_line(text, ("vector_store:",), "index:", "vector-index-mistral")`.
    """

    lines = content.splitlines(keepends=True)
    start, end = _find_block(lines, path)
    for index in range(start + 1, end):
        stripped = lines[index].strip()
        if stripped.startswith(f"{key} "):
            indent = " " * _indent_of(lines[index])
            lines[index] = f"{indent}{key} {new_value}\n"
            return "".join(lines)
    raise ValueError(f"Unable to find key {key!r} in block {' > '.join(path)}")


def _update_profiles(content: str, path: tuple[str, ...], profile_items: str) -> str:
    """Why: The Mistral default profiles must be inserted without reserializing the full YAML list.
    How: Remove existing Mistral profile items from the selected `profiles:` block, then prepend canonical items.
    Example: `_update_profiles(text, ("profiles:",), "- profile_id: default.chat.mistral\\n")`.
    """

    lines = content.splitlines(keepends=True)
    start, end = _find_block(lines, path)
    item_indent = _indent_of(lines[start]) + 2
    kept_lines = lines[: start + 1]
    cursor = start + 1

    while cursor < end:
        line = lines[cursor]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            kept_lines.append(line)
            cursor += 1
            continue

        if _indent_of(line) == item_indent and line.lstrip().startswith("- profile_id:"):
            item_start = cursor
            item_end = cursor + 1
            while item_end < end:
                next_line = lines[item_end]
                next_stripped = next_line.strip()
                if (
                    next_stripped
                    and not next_stripped.startswith("#")
                    and _indent_of(next_line) == item_indent
                    and next_line.lstrip().startswith("- ")
                ):
                    break
                item_end += 1

            profile_id = line.split(":", maxsplit=1)[1].strip()
            if profile_id not in MISTRAL_PROFILE_IDS:
                kept_lines.extend(lines[item_start:item_end])
            cursor = item_end
            continue

        kept_lines.append(line)
        cursor += 1

    kept_lines.extend(lines[end:])
    insertion = profile_items.splitlines(keepends=True)
    return "".join(kept_lines[: start + 1] + insertion + kept_lines[start + 1 :])


def _write_if_changed(path: Path, content: str) -> None:
    """Why: The target should touch files only when a real YAML field changes.
    How: Compare the original text with the updated text before writing to disk.
    Example: `_write_if_changed(repo_root / "file.yaml", new_content)`.
    """

    current = path.read_text()
    if current != content:
        path.write_text(content)


def _configure_models_catalog(path: Path) -> None:
    """Why: Agentic model catalogs need new defaults plus the two canonical Mistral profiles.
    How: Update the defaults block, remove old Mistral items, and reinsert the canonical ones at the top.
    Example: `_configure_models_catalog(repo_root / "agentic-backend/config/models_catalog.yaml")`.
    """

    content = path.read_text()
    content = _replace_block(
        content,
        ("default_profile_by_capability:",),
        "default_profile_by_capability:\n"
        "  chat: default.chat.mistral\n"
        "  language: default.language.mistral\n",
    )
    content = _update_profiles(
        content,
        ("profiles:",),
        "  - profile_id: default.chat.mistral\n"
        "    capability: chat\n"
        "    model:\n"
        "      provider: openai\n"
        f"      name: {MISTRAL_CHAT_MODEL}\n"
        "      settings:\n"
        f"        base_url: {MISTRAL_BASE_URL}\n"
        "  - profile_id: default.language.mistral\n"
        "    capability: language\n"
        "    model:\n"
        "      provider: openai\n"
        f"      name: {MISTRAL_CHAT_MODEL}\n"
        "      settings:\n"
        f"        base_url: {MISTRAL_BASE_URL}\n",
    )
    _write_if_changed(path, content)


def _configure_knowledge_flow(path: Path) -> None:
    """Why: Knowledge Flow prod/worker YAMLs need Mistral models without losing local comments or spacing elsewhere.
    How: Replace only the three model blocks and the vector index line.
    Example: `_configure_knowledge_flow(repo_root / "knowledge-flow-backend/config/configuration_prod.yaml")`.
    """

    content = path.read_text()
    content = _replace_block(
        content,
        ("chat_model:",),
        "chat_model:\n"
        "  provider: openai\n"
        f"  name: {MISTRAL_CHAT_MODEL} # any chat-capable model (gpt-4o, gpt-4o-mini, gpt-4.1, etc.)\n"
        "  settings:\n"
        f"    base_url: {MISTRAL_BASE_URL}\n",
    )
    content = _replace_block(
        content,
        ("embedding_model:",),
        "embedding_model:\n"
        "  provider: openai\n"
        f"  name: {MISTRAL_EMBEDDING_MODEL} # or text-embedding-3-small\n"
        "  settings:\n"
        f"    base_url: {MISTRAL_BASE_URL}\n"
        "    check_embedding_ctx_length: false\n",
    )
    content = _replace_block(
        content,
        ("vision_model:",),
        "vision_model:\n"
        "  provider: openai\n"
        f"  name: {MISTRAL_CHAT_MODEL} # or gpt-4o if you want higher fidelity\n"
        "  settings:\n"
        f"    base_url: {MISTRAL_BASE_URL}\n",
    )
    content = _replace_line(content, ("storage:", "vector_store:"), "index:", MISTRAL_VECTOR_INDEX)
    _write_if_changed(path, content)


def _configure_values_local(path: Path) -> None:
    """Why: The local Helm values file must switch to Mistral while preserving anchors and merge syntax outside edited blocks.
    How: Update only the targeted anchor blocks, vector index, and embedded agentic models catalog section.
    Example: `_configure_values_local(repo_root / "deploy/local/k3d/values-local.yaml")`.
    """

    content = path.read_text()
    content = _replace_block(
        content,
        ("x-kf-embedding-model: &kf-embedding-model",),
        "x-kf-embedding-model: &kf-embedding-model\n"
        "  provider: openai\n"
        f"  name: {MISTRAL_EMBEDDING_MODEL}\n"
        "  settings:\n"
        f"    base_url: {MISTRAL_BASE_URL}\n"
        "    check_embedding_ctx_length: false\n",
    )
    content = _replace_block(
        content,
        ("x-kf-chat-model: &kf-chat-model",),
        "x-kf-chat-model: &kf-chat-model\n"
        "  provider: openai\n"
        f"  name: {MISTRAL_CHAT_MODEL}\n"
        "  settings:\n"
        f"    base_url: {MISTRAL_BASE_URL}\n",
    )
    content = _replace_block(
        content,
        ("x-kf-vision-model: &kf-vision-model",),
        "x-kf-vision-model: &kf-vision-model\n"
        "  provider: openai\n"
        f"  name: {MISTRAL_CHAT_MODEL}\n"
        "  settings:\n"
        f"    base_url: {MISTRAL_BASE_URL}\n",
    )
    content = _replace_line(content, ("x-kf-storage: &kf-storage", "vector_store:"), "index:", MISTRAL_VECTOR_INDEX)
    content = _replace_block(
        content,
        ("applications:", "agentic-backend:", "models_catalog:", "default_profile_by_capability:"),
        "      default_profile_by_capability:\n"
        "        chat: default.chat.mistral\n"
        "        language: default.language.mistral\n",
    )
    content = _update_profiles(
        content,
        ("applications:", "agentic-backend:", "models_catalog:", "profiles:"),
        "        - profile_id: default.chat.mistral\n"
        "          capability: chat\n"
        "          model:\n"
        "            provider: openai\n"
        f"            name: {MISTRAL_CHAT_MODEL}\n"
        "            settings:\n"
        f"              base_url: {MISTRAL_BASE_URL}\n"
        "        - profile_id: default.language.mistral\n"
        "          capability: language\n"
        "          model:\n"
        "            provider: openai\n"
        f"            name: {MISTRAL_CHAT_MODEL}\n"
        "            settings:\n"
        f"              base_url: {MISTRAL_BASE_URL}\n",
    )
    _write_if_changed(path, content)


def main() -> None:
    """Why: `make use-mistral` needs one stable entrypoint for all targeted YAML edits.
    How: Resolve the repo root, apply the three targeted configuration updates, and print each touched file.
    Example: `python3 scripts/use_mistral.py --root /path/to/fred`.
    """

    parser = argparse.ArgumentParser(description="Switch Fred YAML configs to Mistral without reformatting them.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Fred repository root. Defaults to the parent of this script.",
    )
    args = parser.parse_args()

    repo_root = args.root.resolve()
    targets = [
        repo_root / "agentic-backend/config/models_catalog.yaml",
        repo_root / "knowledge-flow-backend/config/configuration_prod.yaml",
        repo_root / "knowledge-flow-backend/config/configuration_worker.yaml",
        repo_root / "deploy/local/k3d/values-local.yaml",
    ]

    print("--- agentic-backend: models_catalog.yaml ---")
    _configure_models_catalog(targets[0])
    print("--- knowledge-flow-backend: configuration_prod.yaml ---")
    _configure_knowledge_flow(targets[1])
    print("--- knowledge-flow-backend: configuration_worker.yaml ---")
    _configure_knowledge_flow(targets[2])
    print("--- deploy/local/k3d: values-local.yaml ---")
    _configure_values_local(targets[3])


if __name__ == "__main__":
    main()
