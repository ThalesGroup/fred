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

"""`PptxGeneratorCapability` — compose a PowerPoint deck from scratch.

Unlike `ppt_filler` (which only fills an uploaded template's placeholders), the
tool schema is static, so this is a `tools()`-only capability that runs on both
ReAct and Graph agents. The brand template is optional. Rationale: README.md
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import time
from collections.abc import Mapping, Sequence
from typing import Annotated, cast

from fred_core import convert_office_bytes_to_pdf
from fred_sdk.contracts.capability import (
    AgentCapability,
    AssetKey,
    AssetSlot,
    CapabilityContext,
    CapabilityManifest,
    ChatControlSpec,
    EmptyModel,
    SaveContext,
    SidePanelSpec,
    UploadedFile,
)
from fred_sdk.contracts.context import (
    LinkKind,
    LinkPart,
    PublishedArtifact,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
    UiPart,
)
from fred_sdk.contracts.models import FieldSpec, UIHints
from langchain_core.tools import BaseTool, StructuredTool
from pptx import Presentation
from pydantic import BaseModel

from fred_capability_pptx_generator.concurrency import (
    acquire_heavy_job_slot,
    release_heavy_job_slot,
)
from fred_capability_pptx_generator.deck_builder import MAX_SLIDES
from fred_capability_pptx_generator.deck_builder import build as build_deck
from fred_capability_pptx_generator.models import GeneratePptxArgs, SlideSpec, ThemeSpec
from fred_capability_pptx_generator.parts import PptxGeneratedPart
from fred_capability_pptx_generator.template_inventory import describe_template_slides

logger = logging.getLogger(__name__)

PPTX_GENERATOR_CAPABILITY_ID = "pptx_generator"

# Fixed per-instance storage key: one template per agent, re-uploading swaps it.
BRAND_TEMPLATE_SLOT = "brand_template"
BRAND_TEMPLATE_KEY = "pptx_generator_brand_template.pptx"

_TOOL_REF = "pptx_generator"
_PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
_PDF_CONTENT_TYPE = "application/pdf"
_PPTX_SUFFIX = ".pptx"
_PDF_SUFFIX = ".pdf"
_DEFAULT_OUTPUT_FILE_NAME = "generated_presentation.pptx"

# Explicit cap on the uploaded brand template (mirrors ppt_filler's
# MAX_TEMPLATE_UPLOAD_BYTES): unbounded reads are an uncapped memory/CPU sink.
MAX_TEMPLATE_UPLOAD_BYTES = 50 * 1024 * 1024

# Bounded concurrency for the image-bytes prefetch: a deck with many image
# slides must not fire an unbounded burst of document fetches.
_IMAGE_PREFETCH_CONCURRENCY = 4

_BUSY_MESSAGE = (
    "The server is busy generating other PowerPoint decks right now. Please "
    "try again in a moment."
)


def _tool_error(message: str) -> tuple[str, ToolInvocationResult]:
    """The `generate_pptx` tool's uniform error-return shape. `blocks` repeats
    the message: the runtime surfaces a failed call from the artifact, and an
    empty one degrades to a generic "step failed" text for the user."""

    return message, ToolInvocationResult(
        tool_ref=_TOOL_REF,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


def _warnings_note(warnings: Sequence[str]) -> str:
    """Tell the agent which fields or shapes the build dropped, so it can
    mention them."""

    if not warnings:
        return ""
    return " Some elements could not be placed and were left out: " + " ".join(warnings)


class PptxGeneratorConfig(BaseModel):
    """Stored config of the pptx_generator capability. Holds only the template
    storage key, never the template bytes."""

    template_key: Annotated[str | None, AssetKey(BRAND_TEMPLATE_SLOT)] = None
    # Computed once at save time: `tools(ctx)` is synchronous, so the
    # template must not be fetched/parsed on every turn.
    template_slide_catalog: str | None = None


def _sanitize_output_file_name(raw: str) -> str:
    """Turn the deck 'title' into a safe `*.pptx` file name (same rules as
    `ppt_filler`'s `_sanitize_output_file_name`)."""

    name = raw.replace("\\", "/").split("/")[-1].strip().strip('"').strip("'").strip()
    name = "".join(c for c in name if c.isprintable() and c not in '<>:"\\|?*')
    if name.lower().endswith(_PPTX_SUFFIX):
        name = name[: -len(_PPTX_SUFFIX)].rstrip()
    if not name:
        return _DEFAULT_OUTPUT_FILE_NAME
    return f"{name}{_PPTX_SUFFIX}"


def _pdf_key_for(pptx_key: str) -> str:
    base = pptx_key
    if base.lower().endswith(_PPTX_SUFFIX):
        base = base[: -len(_PPTX_SUFFIX)]
    return f"{base}{_PDF_SUFFIX}"


def _preview_version(pdf_bytes: bytes) -> str:
    """Per-generation freshness token derived from the PDF content (same
    recipe as `ppt_filler`'s `PptPreviewPart.version`)."""

    return hashlib.sha256(pdf_bytes).hexdigest()[:16]


_TOOL_DESCRIPTION = (
    "Compose a complete PowerPoint deck from scratch and return it as a "
    "downloadable, previewable file — use this whenever the user asks — in "
    "any wording or language — to build, generate, create, or put together a "
    "PowerPoint, presentation, deck, or slides; never paste slide content as "
    "chat text instead. Provide a short deck 'title' (also used as the base "
    f"of the output file name) and 'slides', a list of 1-{MAX_SLIDES} slide "
    "specs. Each slide has a 'kind': 'title' (title + subtitle), "
    "'section_header' (a section divider: title + subtitle), 'bullets' "
    "(title + nested bullet points), 'image' (title + a picture from the "
    "document library), 'table' (title + a headers/rows table), 'chart' "
    "(title + a chart), 'two_content' (title + bullets on the left, and "
    "an image/table/chart on the right — set whichever one you want shown), "
    "or 'columns' (title + 2-4 side-by-side 'columns', each with an "
    "optional 'heading', 'bullets' and 'icon_ref'; 'subtitle' is the intro "
    "paragraph above them, 'group_label' a short tag over the column "
    "group, and 'image_ref' the main picture, when the "
    "template slide has those zones — columns fill the template's column "
    "zones left to right). "
    "Only set the fields relevant to the slide's kind; leave the rest unset. "
    "Optional 'speaker_notes' text is accepted on any slide.\n"
    "IMAGES: 'image_ref' (and a column's 'icon_ref') must be the "
    "document_uid of an existing document in "
    "the document library — find it with a document search or document tree "
    "tool first; never invent one. If no document tools are available in "
    "this conversation, tell the user instead of guessing.\n"
    "CHARTS: set 'chart.chart_type' to one of bar, column, line, pie, "
    "doughnut, area, radar, scatter, bubble, heatmap, waterfall, funnel, or "
    "gantt, plus 'categories' and 'series' (each series has a 'name' and "
    "'values'; scatter/bubble also use 'x_values', bubble also uses "
    "'sizes') — or 'gantt_tasks' (name/start/duration) for a gantt chart. "
    "Whether the chart becomes a native, PowerPoint-editable object or an "
    "embedded image is decided automatically from chart_type; you never "
    "need to worry about which. Set a series' 'color' (hex '#RRGGBB') to "
    "color it — honored for bar/column/line/area/radar series, ignored for "
    "other chart types.\n"
    "STYLING: optional top-level 'theme' sets deck-wide defaults — "
    "'heading_font'/'body_font' (font names), 'primary_color' (hex, used as "
    "the default text color), and 'background' (deck-wide, see BACKGROUNDS "
    "below). Any slide can override the theme with its own "
    "'title_style'/'body_style' (font, size_pt, color, bold, italic, align) "
    "or 'background'. Bullet text supports inline '**bold**' and '*italic*' "
    "spans.\n"
    "PRESETS (recommended): set 'theme.preset' to one of 8 curated names "
    "instead of hand-picking 'primary_color'/'background' hex values — an "
    "LLM inventing colors from scratch tends to produce mismatched, "
    "low-contrast decks, whereas a preset gives every title/section slide a "
    "contrast-checked 'strong' look and every other slide a matching pale "
    "'soft' background automatically. Prefer a preset over manual colors "
    "unless the user asks for a specific brand palette. Options: "
    "'corporate_navy' (deep navy + blue accent, buttoned-up), "
    "'startup_electric' (indigo with soft purple circles, energetic SaaS), "
    "'sustainability_green' (forest green, eco/ESG), 'healthcare_calm' "
    "(calm medical blue/cyan), 'creative_bold' (near-black with orange "
    "diagonal bands, agency/creative), 'editorial_warm' (warm brown/rust, "
    "magazine-style serif), 'minimal_mono' (near-black with a subtle grey "
    "dot grid, minimalist), 'sunset_gradient' (red-orange gradient, warm and "
    "vivid). A slide's own 'background'/'title_style'/'body_style' still "
    "overrides the preset when set.\n"
    "BACKGROUNDS: a 'background' (on 'theme' for the whole deck, or on a "
    "slide to override it) is 'solid' (+ 'color'), 'gradient' (+ exactly 2 "
    "'gradient_colors'), 'image' (+ 'image_ref', same document-library "
    "resolution as slide images — use only for a genuine full-bleed "
    "photo/texture, not as a substitute for the 'image' slide kind), or "
    "'pattern' (+ 'pattern': 'soft_circles' (a few large soft blurred "
    "circles, modern/energetic), 'diagonal_bands' (angled subtle stripes, "
    "SaaS-deck look), or 'dot_grid' (a faint dot texture, minimalist) — plus "
    "'color' as its base fill and optionally 'accent_color', which falls "
    "back to 'theme.primary_color' if unset). A curated preset already picks "
    "a good pattern for its 'strong' slides — only set 'pattern' by hand for "
    "a look beyond what a preset offers.\n"
    "SHAPES: a slide's optional 'shapes' list draws decorative or diagram "
    "elements on top of its normal content — rectangle, rounded_rectangle, "
    "oval, triangle, diamond, arrow_right/left/up/down, line, star, "
    "pentagon, hexagon, chevron, cloud. Each shape's 'left'/'top'/'width'/"
    "'height' are FRACTIONS of the slide size (0.0 to 1.0), never inches — "
    "e.g. a shape centered in the middle third of the slide is left=0.33, "
    "top=0.33, width=0.34, height=0.34. A shape can carry its own 'text' + "
    "'text_style' to act as a labeled diagram node (e.g. a process-flow box "
    "or a highlight annotation over a chart).\n"
    "After the tool runs, the generated deck is surfaced to the user "
    "automatically (a preview beside the chat when available, otherwise a "
    "download button) — do NOT write, invent, or repeat any download link or "
    "URL in your reply, and do not tell the user to click a link you wrote. "
    "Just briefly confirm the deck is ready."
)


def _tool_description(template_slide_catalog: str | None) -> str:
    """`_TOOL_DESCRIPTION` plus, when a brand template with slides is
    configured, the catalog of valid `template_slide_index` values."""

    if not template_slide_catalog:
        return _TOOL_DESCRIPTION
    return _TOOL_DESCRIPTION + (
        "\nTEMPLATE SLIDES: the configured brand template also has "
        "pre-designed slides you can reuse as a starting point — set a "
        "slide spec's 'template_slide_index' (0-based) to duplicate that "
        "exact slide (its background, decorative shapes, and placeholder "
        "layout) and fill it with this slide's own 'kind'-appropriate "
        "content, instead of building from a generic layout. Only use an "
        "index listed below; when unset, the slide is built from a generic "
        "layout as before. A slide's 'text zone' lines list, top to bottom, "
        "the look of each paragraph level in that zone: a bullet's 'level' "
        "picks one of those looks, so not every line has to be a bullet — "
        "put headings/sub-titles on a 'no bullet, bold' level and list items "
        "on a 'bullet' level. On a 'bullets' slide (or a 'two_content' one "
        "filling a template picture frame), 'bullets' fill the largest text zone and 'subtitle' the topmost other one (e.g. a lead "
        "'chapeau' paragraph) — set it whenever the template slide has one, "
        "or that zone is dropped. A 'subtitle' may hold several lines "
        "(separated by '\\n'): each line takes that zone's next listed level, "
        "e.g. a bold lead line then a plain paragraph. Available slides:\n"
        + template_slide_catalog
    )


def _open_template_and_catalog(pptx_bytes: bytes) -> str | None:
    """Open and catalog the template in a single `asyncio.to_thread` offload."""

    return describe_template_slides(Presentation(io.BytesIO(pptx_bytes)))


class PptxGeneratorCapability(
    AgentCapability[PptxGeneratorConfig, PptxGeneratorConfig, EmptyModel]
):
    """Compose a PowerPoint deck from scratch via the `generate_pptx` tool."""

    manifest = CapabilityManifest(
        id=PPTX_GENERATOR_CAPABILITY_ID,
        version="0.2.0",
        name="capability.pptx_generator.name",
        description="capability.pptx_generator.description",
        icon="co_present",
        config_fields=[
            # Without a `config_fields` entry the generic form renders nothing,
            # so this widget is what surfaces the brand-template upload control.
            FieldSpec(
                key="template_key",
                type="string",
                title="PowerPoint brand template",
                description=(
                    "Optional .pptx uploaded to source masters/theme/palette "
                    "for generated decks."
                ),
                ui=UIHints(widget="pptx_generator_template"),
            ),
        ],
        assets=[
            AssetSlot(
                key=BRAND_TEMPLATE_SLOT,
                accepted_types=[".pptx"],
                # Optional: ordinary edits must pass the platform slot gate,
                # and zero-config generation is the point of this capability.
                min_count=0,
                max_count=1,
            )
        ],
        chat_parts=[PptxGeneratedPart],
        side_panels=[SidePanelSpec(widget="pptx_preview_pane")],
        # No execution_models override: tools()-only, so the default
        # ("react", "graph") is correct.
    )
    ConfigModel = PptxGeneratorConfig

    def chat_controls(self, config: PptxGeneratorConfig) -> list[ChatControlSpec]:
        """Composer file-attach control, so an attached source doc
        (`RuntimeContext.attachments_markdown`) can seed slide content."""
        return [ChatControlSpec(widget="attach_files")]

    async def validate_config(
        self,
        config: PptxGeneratorConfig,
        uploads: Mapping[str, list[UploadedFile]],
        ctx: SaveContext,
    ) -> PptxGeneratorConfig:
        template_uploads = list(uploads.get(BRAND_TEMPLATE_SLOT, ()))

        # No upload: never configured, or an edit with the template unchanged.
        if not template_uploads:
            return config

        pptx_bytes = template_uploads[0].content
        if len(pptx_bytes) > MAX_TEMPLATE_UPLOAD_BYTES:
            raise ValueError(
                "The uploaded brand template exceeds the "
                f"{MAX_TEMPLATE_UPLOAD_BYTES // (1024 * 1024)} MB limit."
            )

        # Bounded per pod: opening/parsing is CPU-heavy python-pptx work
        # (offloaded to a thread); fail fast rather than queue.
        if not acquire_heavy_job_slot():
            raise RuntimeError(_BUSY_MESSAGE)
        try:
            try:
                # Off the event loop: a pathological slide/shape count must
                # not block it.
                slide_catalog = await asyncio.to_thread(
                    _open_template_and_catalog, pptx_bytes
                )
            except Exception as exc:
                raise ValueError(
                    f"The uploaded file could not be read as a .pptx: {exc}"
                ) from exc
        finally:
            release_heavy_job_slot()

        assets = ctx.services.agent_assets
        if assets is None:
            raise RuntimeError(
                "pptx_generator: RuntimeServices.agent_assets is not "
                "available on this save path; the brand template cannot be "
                "stored."
            )
        await assets.store(
            BRAND_TEMPLATE_KEY,
            pptx_bytes,
            content_type=_PPTX_CONTENT_TYPE,
            filename=BRAND_TEMPLATE_KEY,
        )
        return config.model_copy(
            update={
                "template_key": BRAND_TEMPLATE_KEY,
                "template_slide_catalog": slide_catalog,
            }
        )

    def tools(
        self, ctx: CapabilityContext[PptxGeneratorConfig, EmptyModel]
    ) -> Sequence[BaseTool]:
        """Build the `generate_pptx` tool, the capability's only runtime
        contribution (wrapped by the default `middleware()` for ReAct, bound
        via `invoke_runtime_tool` for Graph)."""

        config = ctx.config
        services = ctx.services
        identity = ctx.identity

        async def _generate_pptx(
            title: str, slides: list[SlideSpec], theme: ThemeSpec | None = None
        ) -> tuple[str, ToolInvocationResult]:
            if not slides:
                return _tool_error(
                    "No slides were provided — the deck was NOT generated. "
                    "Call this tool again with at least one slide."
                )
            if len(slides) > MAX_SLIDES:
                return _tool_error(
                    f"Too many slides ({len(slides)}) — the limit is "
                    f"{MAX_SLIDES} per call. Split the deck across more than "
                    "one call or trim the content."
                )

            session_id = identity.session_id
            started = time.monotonic()

            workspace = services.workspace_fs
            if workspace is None:
                raise RuntimeError(
                    "pptx_generator: RuntimeServices.workspace_fs is not "
                    "available on this execution path."
                )

            # Reserved before any fetch so an overloaded pod rejects fast
            # instead of fetching assets it would discard. Held through step 3.
            if not acquire_heavy_job_slot():
                return _tool_error(_BUSY_MESSAGE)
            try:
                # 1+2. Fetch the template and all image refs concurrently. A ref
                # that fails is left out of the map; `deck_builder` reports it
                # as an "unknown image_ref" the agent can self-correct.
                image_refs = {
                    spec.image_ref
                    for spec in slides
                    if spec.image_ref
                    and spec.kind in ("image", "two_content", "columns")
                }
                image_refs |= {
                    column.icon_ref
                    for spec in slides
                    if spec.kind == "columns"
                    for column in spec.columns or []
                    if column.icon_ref
                }
                image_refs |= {
                    spec.background.image_ref
                    for spec in slides
                    if spec.background
                    and spec.background.kind == "image"
                    and spec.background.image_ref
                }
                if (
                    theme
                    and theme.background
                    and theme.background.kind == "image"
                    and theme.background.image_ref
                ):
                    image_refs.add(theme.background.image_ref)

                # A missing port is a configuration error, not an agent
                # mistake: raise up front.
                assets = services.agent_assets if config.template_key else None
                if config.template_key and assets is None:
                    raise RuntimeError(
                        "pptx_generator: RuntimeServices.agent_assets is not "
                        "available on this execution path, but a brand "
                        "template is configured."
                    )
                document_content_port = (
                    services.document_content if image_refs else None
                )
                if image_refs and document_content_port is None:
                    raise RuntimeError(
                        "pptx_generator: RuntimeServices.document_content is "
                        "not available on this execution path, but a slide "
                        "references an image."
                    )

                async def _fetch_template() -> bytes | None:
                    if not config.template_key:
                        return None
                    assert assets is not None  # checked above
                    return await assets.fetch(config.template_key)

                async def _fetch_images() -> dict[str, bytes]:
                    if not image_refs:
                        return {}
                    assert document_content_port is not None  # checked above
                    port = document_content_port
                    semaphore = asyncio.Semaphore(_IMAGE_PREFETCH_CONCURRENCY)

                    async def _fetch_one(ref: str) -> tuple[str, bytes | None]:
                        async with semaphore:
                            try:
                                raw = await port.fetch_raw(ref)
                                return ref, raw.content
                            except Exception:
                                logger.warning(
                                    "[PPTXGEN][TOOL] image_ref '%s' fetch failed "
                                    "(reported to the model as unresolved)",
                                    ref,
                                    exc_info=True,
                                )
                                return ref, None

                    fetched = await asyncio.gather(
                        *(_fetch_one(ref) for ref in image_refs)
                    )
                    return {
                        ref: content for ref, content in fetched if content is not None
                    }

                try:
                    template_bytes, image_bytes_by_ref = await asyncio.gather(
                        _fetch_template(), _fetch_images()
                    )
                except Exception as exc:
                    elapsed = time.monotonic() - started
                    message = (
                        "Could not fetch the configured brand template "
                        f"after {elapsed:.0f}s [{type(exc).__name__}: {exc}]."
                    )
                    logger.exception(
                        "[PPTX_GENERATOR][TOOL] template fetch FAILED -> %s",
                        message,
                    )
                    return _tool_error(message)

                # 3. Build the deck entirely off the event loop: one worker call
                # owns the Presentation object end to end (python-pptx /
                # matplotlib are synchronous, CPU-bound).
                build_warnings: list[str] = []
                try:
                    deck_bytes = await asyncio.to_thread(
                        build_deck,
                        title,
                        slides,
                        template_bytes=template_bytes,
                        image_bytes_by_ref=image_bytes_by_ref,
                        theme=theme,
                        warnings=build_warnings,
                    )
                except ValueError as exc:
                    # A structural mistake the agent can correct (unknown
                    # image_ref, oversized table, malformed chart) — never a
                    # raised exception reaching the default ToolNode handler.
                    return _tool_error(str(exc))
                except Exception as exc:
                    elapsed = time.monotonic() - started
                    message = (
                        f"Could not build the presentation after "
                        f"{elapsed:.0f}s [{type(exc).__name__}: {exc}]."
                    )
                    logger.exception(
                        "[PPTX_GENERATOR][TOOL] build FAILED -> %s", message
                    )
                    return _tool_error(message)
            finally:
                release_heavy_job_slot()

            # 4. Write the .pptx (session-scoped path so conversations never
            # clobber each other) and, concurrently, the best-effort PDF preview.
            output_file_name = _sanitize_output_file_name(title)
            output_path = (
                f"outputs/{session_id}/{output_file_name}"
                if session_id
                else f"outputs/{output_file_name}"
            )

            async def _build_pdf_preview() -> tuple[bytes | None, str | None]:
                """Convert `deck_bytes` to PDF and upload it. Never raises: any
                failure degrades to the plain download chip."""

                pdf_bytes = await convert_office_bytes_to_pdf(
                    deck_bytes, suffix=".pptx"
                )
                if pdf_bytes is None:
                    return None, None
                try:
                    pdf_artifact = await workspace.write(
                        _pdf_key_for(output_path),
                        pdf_bytes,
                        content_type=_PDF_CONTENT_TYPE,
                        title=_pdf_key_for(output_file_name),
                    )
                    return pdf_bytes, pdf_artifact.href
                except Exception as exc:  # noqa: BLE001 - degrade to download, never fail the whole call
                    logger.warning(
                        "[PPTX_GENERATOR][TOOL] preview upload failed (deck "
                        "still returned): %s",
                        exc,
                    )
                    return None, None

            pptx_result, pdf_preview_result = await asyncio.gather(
                workspace.write(
                    output_path,
                    deck_bytes,
                    content_type=_PPTX_CONTENT_TYPE,
                    title=output_file_name,
                ),
                _build_pdf_preview(),
                return_exceptions=True,
            )
            if isinstance(pptx_result, BaseException):
                elapsed = time.monotonic() - started
                message = (
                    "Built the presentation but could not upload it after "
                    f"{elapsed:.0f}s [{type(pptx_result).__name__}: {pptx_result}]."
                )
                logger.exception(
                    "[PPTX_GENERATOR][TOOL] upload FAILED -> %s",
                    message,
                    exc_info=pptx_result,
                )
                return _tool_error(message)
            pptx_artifact: PublishedArtifact = pptx_result
            # `_build_pdf_preview` never raises; `return_exceptions=True`
            # only guards the pptx upload.
            pdf_bytes, pdf_download_url = cast(
                "tuple[bytes | None, str | None]", pdf_preview_result
            )

            logger.info(
                "[PPTX_GENERATOR][TOOL] deck uploaded session=%s key=%s slides=%d",
                session_id,
                pptx_artifact.key,
                len(slides),
            )

            if pdf_download_url and pdf_bytes is not None:
                preview = PptxGeneratedPart(
                    preview_id=pptx_artifact.key,
                    title=output_file_name,
                    pdf_download_url=pdf_download_url,
                    version=_preview_version(pdf_bytes),
                    pptx_download_url=pptx_artifact.href,
                    file_name=pptx_artifact.file_name,
                )
                artifact = ToolInvocationResult(
                    tool_ref=_TOOL_REF,
                    ui_parts=(cast(UiPart, preview),),
                )
                message = (
                    f"The presentation '{output_file_name}' has been "
                    "generated. A preview opens beside the chat and a "
                    "download button is shown automatically; do not write a "
                    "download link yourself."
                ) + _warnings_note(build_warnings)
                return message, artifact

            # Preview unavailable -> fall back to the download chip and say so.
            link = LinkPart(
                href=pptx_artifact.href,
                title=f"Download {pptx_artifact.file_name}",
                kind=LinkKind.download,
                mime=_PPTX_CONTENT_TYPE,
                document_uid=pptx_artifact.document_uid,
                file_name=pptx_artifact.file_name,
            )
            artifact = ToolInvocationResult(
                tool_ref=_TOOL_REF,
                ui_parts=(cast(UiPart, link),),
            )
            message = (
                f"The presentation '{output_file_name}' has been generated "
                "(the preview could not be generated, so only the download "
                "is available). A download button is shown to the user "
                "automatically; do not write a download link yourself."
            ) + _warnings_note(build_warnings)
            return message, artifact

        generate_pptx = StructuredTool.from_function(
            coroutine=_generate_pptx,
            name="generate_pptx",
            description=_tool_description(config.template_slide_catalog),
            args_schema=GeneratePptxArgs,
            response_format="content_and_artifact",
        )
        return [generate_pptx]
