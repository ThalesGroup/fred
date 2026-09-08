# Copyright Thales 2026
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

"""`SessionWorkspaceCapability` — a scratch filesystem shared across one session.

A parent agent and the sub-agents it spawns run under the SAME `session_id`, so a
directory keyed on it is the cheapest shared surface between them: children write
`part-N.md`, the parent merges the parts with `concat_files` instead of re-writing
them through a small model.

The `ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep` tools come from
deepagents' `FilesystemMiddleware`; only the merge tool is written here.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.context import ToolInvocationResult
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)

SESSION_WORKSPACE_CAPABILITY_ID = "session_workspace"

_TOOL_REF = "session_workspace"

# Local disk, not the pod's object store: this is scratch space for one session,
# and the POC runs a single fred-agents replica.
_SESSIONS_ROOT = Path("~/.fred/fred-agents/sessions")


def session_workspace_root(session_id: str) -> Path:
    """The on-disk root every tool in this session resolves paths against."""

    root = _SESSIONS_ROOT.expanduser() / session_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_in_workspace(root: Path, path: str) -> Path | None:
    """Resolve one model-supplied path under `root`, or None if it escapes it.

    The model sees the session root as `/` (deepagents `virtual_mode`), so a
    leading slash is stripped rather than treated as a real absolute path.
    """

    candidate = (root / path.lstrip("/")).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        return None
    return candidate


def _heading_for(path: str) -> str:
    """A markdown heading derived from a file name, for a merged part."""

    stem = Path(path).stem.replace("_", " ").replace("-", " ").strip()
    return f"## {stem}" if stem else "##"


class _SessionWorkspaceMiddleware(AgentMiddleware):
    """Carries `concat_files`, bound to one session's workspace root."""

    def __init__(self, root: Path) -> None:
        super().__init__()

        @tool("concat_files", response_format="content_and_artifact")
        async def concat_files(
            paths: list[str],
            output_path: str,
            heading_per_file: bool = True,
        ) -> tuple[str, ToolInvocationResult]:
            """Merge several workspace files into one file, mechanically and losslessly.

            Use this to assemble the outputs your sub-agents wrote (for example
            part-1.md, part-2.md, ...) into a single document. Do NOT read the parts and
            re-type them yourself: that loses content and wastes a whole turn — call
            this tool instead, then open the merged file.

            Paths are relative to the session workspace root. The files are concatenated
            in the order you list them, separated by a blank line, and each one is
            prefixed with a markdown heading built from its file name unless
            heading_per_file is false.
            """

            if not paths:
                return (
                    "concat_files needs at least one input path.",
                    ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True),
                )

            resolved: list[tuple[str, Path]] = []
            escaping: list[str] = []
            for path in paths:
                target = resolve_in_workspace(root, path)
                if target is None:
                    escaping.append(path)
                else:
                    resolved.append((path, target))
            out_target = resolve_in_workspace(root, output_path)
            if out_target is None:
                escaping.append(output_path)
            # `out_target is None` is already in `escaping`; repeating it here
            # narrows the type for the write below.
            if escaping or out_target is None:
                return (
                    "Refused: these paths point outside the session workspace: "
                    + ", ".join(escaping),
                    ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True),
                )

            missing = [path for path, target in resolved if not target.is_file()]
            if missing:
                # Nothing is written: a partial merge would read as a complete
                # document to the caller.
                return (
                    "Cannot merge: these files do not exist in the session "
                    "workspace: " + ", ".join(missing),
                    ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True),
                )

            chunks: list[str] = []
            for path, target in resolved:
                body = target.read_text(encoding="utf-8").strip()
                chunks.append(
                    f"{_heading_for(path)}\n\n{body}" if heading_per_file else body
                )
            merged = "\n\n".join(chunks)

            out_target.parent.mkdir(parents=True, exist_ok=True)
            out_target.write_text(merged, encoding="utf-8")
            logger.info(
                "[SESSION_WORKSPACE] merged %d file(s) into %s (%d chars)",
                len(resolved),
                output_path,
                len(merged),
            )
            summary = (
                f"Merged {len(resolved)} file(s), {len(merged)} characters, "
                f"into {output_path}."
            )
            return summary, ToolInvocationResult(tool_ref=_TOOL_REF)

        tools: Sequence[BaseTool] = [concat_files]
        self.tools = tools


class SessionWorkspaceCapability(AgentCapability[EmptyModel, EmptyModel, EmptyModel]):
    """A scratch filesystem shared by an agent and the sub-agents of its session.

    No config, no table, no router, no chat part: the whole capability is the
    deepagents filesystem tools anchored on the session directory plus one merge
    tool.
    """

    manifest = CapabilityManifest(
        id=SESSION_WORKSPACE_CAPABILITY_ID,
        version="0.1.0",
        name="capability.session_workspace.name",
        description="capability.session_workspace.description",
        icon="folder_shared",
        kind="tool",
        # Overrides `middleware()` without `tools()` (the filesystem tools ride
        # on deepagents' own middleware), so it has no Graph-visible half.
        execution_models=("react",),
    )
    ConfigModel = EmptyModel

    def middleware(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> list[AgentMiddleware[Any, Any, Any]]:
        session_id = ctx.identity.session_id
        if not session_id:
            # Nothing to scope a workspace to — contribute nothing rather than
            # handing every session one shared directory.
            logger.info("[SESSION_WORKSPACE] no session id on this turn; no tools")
            return []
        root = session_workspace_root(session_id)
        backend = FilesystemBackend(root_dir=root, virtual_mode=True)
        return [
            FilesystemMiddleware(backend=backend),
            _SessionWorkspaceMiddleware(root),
        ]
