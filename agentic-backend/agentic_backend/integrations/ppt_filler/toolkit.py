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

"""Inprocess toolkit factory for the ``ppt_filler`` provider (PPTFILL-05 / #1834).

The chat-time fill tool that makes a configured ``ppt_filler`` agent produce a filled,
downloadable deck.

Pipeline (all derived from the agent's persisted :class:`PptFillerParams`, never from
hardcoded slide indices):

1. **Dynamic per-slide ``args_schema``** — built AT TOOL-BUILD TIME from the persisted
   ``schema_slides``. It is nested by slide: a top-level object with one ``slide_<n>``
   property per schema slide (1-based ``SlideSchema.slide``), each of which is an object
   whose leaf properties are that slide's ``{{keys}}``. Each leaf carries its note
   description as the schema-level description so the model gets inline guidance.
2. **Fill** — fetch the template bytes from the agent-config blob store under the fixed
   ``PPT_FILLER_TEMPLATE_KEY``, open with python-pptx, and for each provided ``slide_<n>``
   group fill the n-th (1-based) slide via the SHARED traversal
   (:func:`replace_keys_on_slide`). Reusing the traversal guarantees the filler can never
   diverge from the parser, and that every occurrence of a key on a slide is filled
   consistently.
3. **Download** — render to bytes, upload to SESSION-SCOPED user storage, and return a
   :class:`LinkPart` (``kind=download``) so the UI renders a download button.

Scope limit (carried from the POC / RFC "Out of Scope"): only ``has_text_frame`` shapes
are filled — table cells and grouped shapes are intentionally not supported in v1. This
is enforced by the shared traversal, not re-implemented here.

NOTE on imports: ``build_ppt_filler_tools`` is imported directly from this submodule by
``core/tools/inprocess_toolkit_registry.py`` (NOT re-exported via the package
``__init__``) to avoid an import cycle through ``agent_spec``. Keep it that way.
"""

from __future__ import annotations

import io
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

from langchain_core.tools import BaseTool, StructuredTool
from pptx import Presentation
from pydantic import BaseModel, Field, create_model

from agentic_backend.common.kf_base_client import KnowledgeFlowAgentContext
from agentic_backend.common.kf_workspace_client import KfWorkspaceClient
from agentic_backend.core.agents.v2.contracts.context import ToolInvocationResult
from agentic_backend.core.chatbot.chat_schema import LinkKind, LinkPart
from agentic_backend.integrations.ppt_filler.ppt_filler_params import (
    PPT_FILLER_PROVIDER,
    PptFillerParams,
)
from agentic_backend.integrations.ppt_filler.parser import apply_kept_notes_to_slide
from agentic_backend.integrations.ppt_filler.traversal import replace_keys_on_slide

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agentic_backend.integrations.ppt_filler.parser import SlideSchema

logger = logging.getLogger(__name__)

_TOOL_NAME = "fill_ppt_template"
_TOOL_REF = "ppt_filler_fill"
_PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
_OUTPUT_FILE_NAME = "filled_presentation.pptx"
_PPTX_SUFFIX = ".pptx"

# Top-level (non-slide) arg the model fills with a human-friendly name for the output
# deck. Optional: when missing/blank we fall back to ``_OUTPUT_FILE_NAME``.
_OUTPUT_NAME_FIELD = "output_file_name"

# The top-level args field for each slide is ``slide_<n>`` where ``n`` is the 1-based
# ``SlideSchema.slide``. Building (here) and parsing (in the tool body) the prefix go
# through the same helper so they can never drift.
_SLIDE_FIELD_PREFIX = "slide_"


def _slide_field_name(slide_number: int) -> str:
    return f"{_SLIDE_FIELD_PREFIX}{slide_number}"


def _sanitize_output_file_name(raw: object) -> str:
    """Turn a model-provided output name into a safe ``*.pptx`` file name.

    The name is used both as a storage key segment and as the download file name, so it
    must not contain path separators or be empty. We keep only the final path component,
    strip control/quote characters, ensure a single ``.pptx`` suffix, and fall back to
    :data:`_OUTPUT_FILE_NAME` when nothing usable remains.
    """
    if not isinstance(raw, str):
        return _OUTPUT_FILE_NAME
    # Keep only the final path component to defeat traversal (e.g. "../../x", "a/b.pptx").
    name = raw.replace("\\", "/").split("/")[-1].strip().strip('"').strip("'").strip()
    # Drop characters that are awkward in file names / storage keys.
    name = "".join(c for c in name if c.isprintable() and c not in '<>:"\\|?*')
    # Normalize the extension: case-insensitive, exactly one trailing ".pptx".
    if name.lower().endswith(_PPTX_SUFFIX):
        name = name[: -len(_PPTX_SUFFIX)].rstrip()
    if not name:
        return _OUTPUT_FILE_NAME
    return f"{name}{_PPTX_SUFFIX}"


def _slide_number_from_field(field_name: str) -> Optional[int]:
    if not field_name.startswith(_SLIDE_FIELD_PREFIX):
        return None
    suffix = field_name[len(_SLIDE_FIELD_PREFIX) :]
    try:
        return int(suffix)
    except ValueError:
        return None


def _get_ppt_filler_params(agent: KnowledgeFlowAgentContext) -> PptFillerParams:
    """Extract this agent's own :class:`PptFillerParams` from its tuning refs.

    Mirrors ``_get_kf_vector_search_params`` in ``kf_document_client``: scan the agent's
    ``tuning.mcp_servers`` for the ref whose params carry ``provider == ppt_filler`` and
    return them; fall back to a default (empty schema) so callers never need a None check.
    """
    agent_settings = getattr(agent, "agent_settings", None)
    tuning = getattr(agent_settings, "tuning", None)
    if tuning is not None:
        for ref in tuning.mcp_servers:
            if (
                ref.params is not None
                and getattr(ref.params, "provider", None) == PPT_FILLER_PROVIDER
            ):
                return ref.params  # type: ignore[return-value]
    return PptFillerParams()


def _build_args_schema(schema_slides: "list[SlideSchema]") -> type[BaseModel]:
    """Build the dynamic, nested-by-slide ``args_schema`` from the persisted schema.

    For each slide we synthesize a per-slide model whose fields are that slide's keys,
    each carrying the key's note description as its schema-level ``description``. The
    top-level model then has one ``slide_<n>`` field per slide pointing at the per-slide
    model. Everything is derived from ``schema_slides`` — no hardcoded indices.
    """
    # ``create_model`` takes each field as a ``(type, FieldInfo)`` tuple; typing the dict
    # values as ``Any`` keeps the ``**`` spread assignable to its keyword parameters.
    top_fields: Dict[str, Any] = {}
    for slide_schema in schema_slides:
        leaf_fields: Dict[str, Any] = {}
        for key_field in slide_schema.keys:
            # Each leaf is a required string whose description is the note description, so
            # the model gets inline per-field guidance. Duplicate keys on one slide are
            # already de-duplicated by the parser, so last-wins here is harmless.
            leaf_fields[key_field.key] = (
                str,
                Field(..., description=key_field.description or ""),
            )
        slide_model = create_model(
            f"PptFillSlide{slide_schema.slide}",
            __base__=BaseModel,
            **leaf_fields,
        )
        top_fields[_slide_field_name(slide_schema.slide)] = (
            slide_model,
            Field(
                ...,
                description=(
                    f"Values for the {{key}} fields on slide {slide_schema.slide}."
                ),
            ),
        )
    # Optional, model-chosen name for the produced deck. Lets the agent give the file a
    # relevant name (e.g. derived from the content) instead of a generic default. The
    # ".pptx" extension is added automatically if omitted; leave empty for the default.
    top_fields[_OUTPUT_NAME_FIELD] = (
        Optional[str],
        Field(
            default=None,
            description=(
                "A short, relevant file name for the generated PowerPoint, based on "
                "its content (e.g. 'Proposition_ACME_2026'). The '.pptx' extension is "
                "added automatically. Optional — omit to use a generic default."
            ),
        ),
    )
    return create_model(
        "FillPptTemplateArgs",
        __base__=BaseModel,
        **top_fields,
    )


def _values_for_slide(slide_args: object) -> Dict[str, str]:
    """Coerce one ``slide_<n>`` group (a pydantic model) into a ``{key: value}`` map."""
    if isinstance(slide_args, BaseModel):
        raw = slide_args.model_dump()
    elif isinstance(slide_args, dict):
        raw = slide_args
    else:
        raw = dict(getattr(slide_args, "__dict__", {}) or {})
    return {key: "" if value is None else str(value) for key, value in raw.items()}


def build_ppt_filler_tools(agent: KnowledgeFlowAgentContext) -> list[BaseTool]:
    """Return the in-process LangChain tools for the PPT Filler toolkit.

    The single tool's dynamic ``args_schema`` is derived per-slide from the agent's
    persisted ``schema_slides``. With no schema (template never configured) there is
    nothing to fill, so no tool is exposed.
    """
    params = _get_ppt_filler_params(agent)
    schema_slides = params.schema_slides
    if not schema_slides:
        logger.debug(
            "ppt_filler toolkit requested but the agent has no persisted schema; "
            "returning no tools (template not configured)."
        )
        return []

    args_schema = _build_args_schema(schema_slides)
    template_key = params.template_key

    async def _fill(**kwargs: object) -> tuple[str, ToolInvocationResult]:
        # Validate/normalize the model-provided args against the dynamic schema so we get
        # the typed per-slide groups regardless of whether LangChain passed raw dicts.
        validated = args_schema(**kwargs)
        provided = validated.model_dump()

        # Resolve the per-run identifiers from the agent context (same accessors the
        # AgentFlow helpers use): agent_id for the agent-config template fetch, and
        # session_id to scope the user-storage output blob.
        runtime_context = getattr(agent, "runtime_context", None)
        agent_settings = getattr(agent, "agent_settings", None)
        agent_id = getattr(agent_settings, "id", None) or type(agent).__name__
        session_id = getattr(runtime_context, "session_id", None)
        access_token = getattr(runtime_context, "access_token", None)

        started = time.monotonic()
        client = KfWorkspaceClient(agent=agent)  # type: ignore[arg-type]

        # 1. Fetch the template from the agent-config blob store (fixed per-agent key).
        try:
            blob = await client.fetch_agent_config_blob(
                template_key,
                access_token,
                agent_id,
            )
        except Exception as exc:
            elapsed = time.monotonic() - started
            message = (
                f"Could not fetch the PPT template '{template_key}' from agent config "
                f"storage after {elapsed:.0f}s [{type(exc).__name__}: {exc}]."
            )
            logger.exception("[PPTFILL][TOOL] template fetch FAILED -> %s", message)
            return message, ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True)

        # 2. Open the template and fill, per-slide, via the SHARED traversal. Mapping
        #    slide_<n> -> the n-th (1-based) slide; only has_text_frame shapes are filled
        #    (the shared traversal enforces this; table cells / grouped shapes are out of
        #    scope in v1).
        try:
            presentation = Presentation(io.BytesIO(blob.bytes))
            slides = list(presentation.slides)
            for field_name, slide_args in provided.items():
                slide_number = _slide_number_from_field(field_name)
                if slide_number is None:
                    continue
                index = slide_number - 1
                if index < 0 or index >= len(slides):
                    # The persisted schema references a slide the template no longer has;
                    # skip rather than crash (template may have been edited).
                    logger.warning(
                        "[PPTFILL][TOOL] schema references slide %d but template has "
                        "only %d slides; skipping.",
                        slide_number,
                        len(slides),
                    )
                    continue
                values = _values_for_slide(slide_args)

                def value_for(key: str, _values: Dict[str, str] = values) -> str:
                    # Every occurrence of a key on this slide is filled with the same
                    # value; the shared traversal calls this once per placeholder.
                    return _values.get(key, "")

                replace_keys_on_slide(slides[index], value_for)

            # Strip template-authoring notes from EVERY slide so the ``{{key}}:``
            # descriptions never leak into the deliverable. Any content the author placed
            # after a ``---`` keep-separator is preserved as the slide's real notes.
            for slide in slides:
                apply_kept_notes_to_slide(slide)

            buffer = io.BytesIO()
            presentation.save(buffer)
            filled_bytes = buffer.getvalue()
        except Exception as exc:
            elapsed = time.monotonic() - started
            message = (
                f"Could not fill the PPT template after {elapsed:.0f}s "
                f"[{type(exc).__name__}: {exc}]."
            )
            logger.exception("[PPTFILL][TOOL] fill FAILED -> %s", message)
            return message, ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True)

        # 3. Upload to SESSION-SCOPED user storage and return a download LinkPart. The
        #    session prefix mirrors AgentFlow.upload_user_blob so outputs are cleaned up
        #    on session delete; KfWorkspaceClient.upload_user_blob does not prefix itself.
        #    The model-chosen name (sanitized) becomes both the storage key segment and
        #    the download file name; it falls back to a generic default when not given.
        output_file_name = _sanitize_output_file_name(provided.get(_OUTPUT_NAME_FIELD))
        upload_key = (
            f"{session_id}/{output_file_name}" if session_id else output_file_name
        )
        try:
            upload_result = await client.upload_user_blob(
                key=upload_key,
                file_content=filled_bytes,
                filename=output_file_name,
                content_type=_PPTX_CONTENT_TYPE,
            )
        except Exception as exc:
            elapsed = time.monotonic() - started
            message = (
                f"Filled the template but could not upload the result after "
                f"{elapsed:.0f}s [{type(exc).__name__}: {exc}]."
            )
            logger.exception("[PPTFILL][TOOL] upload FAILED -> %s", message)
            return message, ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True)

        link = LinkPart(
            href=upload_result.download_url,
            title=f"Download {upload_result.file_name}",
            kind=LinkKind.download,
            mime=_PPTX_CONTENT_TYPE,
            document_uid=upload_result.document_uid,
            file_name=upload_result.file_name,
        )
        logger.info(
            "[PPTFILL][TOOL] filled deck uploaded session=%s key=%s url=%s",
            session_id,
            upload_result.key,
            upload_result.download_url,
        )
        artifact = ToolInvocationResult(tool_ref=_TOOL_REF, ui_parts=(link,))
        return (
            f"The presentation '{output_file_name}' has been filled. A download button "
            "is shown to the user automatically; do not write a download link yourself.",
            artifact,
        )

    # NOTE: do NOT set response_format="content_and_artifact" here. The v2 ReAct
    # resolver invokes inprocess provider tools via `tool.ainvoke(<plain args dict>)`
    # (see react_tool_resolution._resolve_runtime_provider_tool). With
    # content_and_artifact, LangChain returns ONLY the content string on a plain-args
    # invoke and silently drops the artifact, so the download LinkPart never reaches
    # the UI. Returning a bare ``(content, ToolInvocationResult)`` tuple from the
    # coroutine instead lets the resolver normalize the artifact (it explicitly
    # handles the 2-tuple shape), which is how the ui_parts (the download link) and
    # is_error survive.
    fill_tool = StructuredTool.from_function(
        coroutine=_fill,
        name=_TOOL_NAME,
        description=(
            "Fill the agent's configured PowerPoint template with the provided values. "
            "Provide a value for every {{key}} field, grouped by slide: the input is an "
            "object with one 'slide_<n>' property per slide, each containing that "
            "slide's keys. Each field's description tells you what to put there. "
            "Optionally set 'output_file_name' to a short, relevant name for the deck "
            "(the '.pptx' extension is added automatically). "
            "After the tool runs, a download button for the filled PowerPoint is shown "
            "to the user automatically — do NOT write, invent, or repeat any download "
            "link or URL in your reply, and do not tell the user to click a link you "
            "wrote. Just briefly confirm the deck is ready."
        ),
        args_schema=args_schema,
    )
    return [fill_tool]
