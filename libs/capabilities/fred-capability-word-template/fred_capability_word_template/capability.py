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


"""`WordTemplateCapability`: the Word template engine as a Fred capability.

The model's tools (read, edit, undo, base choice), the ReAct middleware that
adds the engine's prompt and checks each model step, and the template library
configuration. A session's document is its base plus the replayed operation
log. Spec: openspec/specs/word-template/spec.md.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fred_sdk.contracts.capability import (
    AgentCapability,
    AssetSlot,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    HitlGateRequest,
    HitlSpec,
    SaveContext,
    SidePanelSpec,
    UploadedFile,
)
from fred_sdk.contracts.models import FieldSpec, UIHints
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool
from pydantic import ValidationError

from fred_capability_word_template.config import (
    TEMPLATE_LIBRARY_SLOT,
    WordTemplateConfig,
    resolve_library,
)
from fred_capability_word_template.documents import (
    Documents,
)
from fred_capability_word_template.middleware import (
    PREFLIGHT,
    WordTemplateMiddleware,
)
from fred_capability_word_template.operations import (
    normalized,
    parse_operation,
)
from fred_capability_word_template.router import build_router
from fred_capability_word_template.store import (
    WORD_TEMPLATE_CAPABILITY_ID,
    WordTemplateAnalysis,
    WordTemplateAttachment,
    WordTemplateBatch,
    WordTemplateImage,
    WordTemplateSession,
    WordTemplateSnapshot,
)
from fred_capability_word_template.tools import (
    build_tools,
)

logger = logging.getLogger(__name__)


class WordTemplateCapability(
    AgentCapability[WordTemplateConfig, WordTemplateConfig, EmptyModel]
):
    """Fill and write any Word template from chat. The use case - tone,
    sources, what to ask - lives in each agent's own system prompt, never
    here."""

    manifest = CapabilityManifest(
        id=WORD_TEMPLATE_CAPABILITY_ID,
        version="0.1.0",
        name="capability.word_template.name",
        description="capability.word_template.description",
        icon="description",
        config_fields=[
            # Owned by the frontend plugin's custom widget (upload + names).
            FieldSpec(
                key="template_library",
                type="array",
                title="capability.word_template.fields.template_library.title",
                description=(
                    "capability.word_template.fields.template_library.description"
                ),
                required=False,
                ui=UIHints(widget="word_template_library"),
            ),
        ],
        assets=[
            # One file per NEW library entry, same order. min_count=0: an
            # ordinary edit with no re-upload must pass the slot gate.
            AssetSlot(
                key=TEMPLATE_LIBRARY_SLOT,
                accepted_types=[".docx"],
                min_count=0,
                max_count=None,
            ),
        ],
        side_panels=[SidePanelSpec(widget="word_template_pane")],
        router=build_router(),
        # The guards and prompt fragments are ReAct middleware: a Graph agent
        # would get the tools unguarded.
        execution_models=("react",),
        tables=[
            WordTemplateSession,
            WordTemplateBatch,
            WordTemplateAnalysis,
            WordTemplateSnapshot,
            WordTemplateAttachment,
            WordTemplateImage,
        ],
    )
    ConfigModel = WordTemplateConfig

    @classmethod
    def migrations_location(cls) -> str:
        return str(Path(__file__).resolve().parent / "word_template_migrations")

    async def validate_config(
        self,
        config: WordTemplateConfig,
        uploads: Mapping[str, list[UploadedFile]],
        ctx: SaveContext,
    ) -> WordTemplateConfig:
        """Store new library files and precompute their parts. The template
        analysis is NOT run here: the save path carries no chat model
        (``_build_capability_save_services`` gives assets/workspace/folders
        only), so it runs on first use. An empty library
        is valid: the agent then works on a Word file attached in the chat."""
        files = list(uploads.get(TEMPLATE_LIBRARY_SLOT, ()))
        if config.template_library is None and not files:
            return config
        library = await resolve_library(config.template_library or [], files, ctx)
        return config.model_copy(update={"template_library": library or None})

    def hitl_specs(self) -> Sequence[HitlSpec]:
        """The acts the collaborator approves through the platform gate: a
        batch that changes the document's structure (removes content, or
        declares changes_template: adds a chapter, changes fixed wording),
        switching the document's base to an attached file, removing the
        template's unused parts, and undoing an earlier turn's edit on the
        collaborator's request. All read the call itself (and whether it was
        found refused when planned); the prompt rules stay as the second
        layer."""
        return [
            HitlSpec(
                tool="edit_document",
                require=False,
                when=_batch_changes_structure,
                question=_STRUCTURE_QUESTION,
            ),
            HitlSpec(tool="use_attached_document", require=True),
            HitlSpec(
                tool="remove_unused_template_parts",
                require=True,
                question=_CLEANUP_QUESTION,
            ),
            HitlSpec(
                tool="undo_last_edit",
                require=False,
                when=_undo_asked_by_collaborator,
                question=_UNDO_QUESTION,
            ),
        ]

    def tools(
        self, ctx: CapabilityContext[WordTemplateConfig, EmptyModel]
    ) -> Sequence[BaseTool]:
        return build_tools(Documents(ctx))

    def middleware(
        self, ctx: CapabilityContext[WordTemplateConfig, EmptyModel]
    ) -> list[AgentMiddleware]:
        return [WordTemplateMiddleware(ctx)]


# The gate's question is fixed text (the platform renders it as is): it
# points to the agent's message, which says what exactly will change.
_STRUCTURE_QUESTION = (
    "L'agent veut modifier la structure de votre document : supprimer ou "
    "déplacer du contenu, ajouter un chapitre ou un sous-chapitre, ou changer "
    "un texte fixe du "
    "modèle. Son message "
    "ci-dessus indique exactement ce qui va changer. Acceptez seulement si "
    "c'est ce que vous avez demandé."
)


_CLEANUP_QUESTION = (
    "L'agent veut retirer de votre document les parties du modèle qui n'ont "
    "pas été utilisées. Son message ci-dessus indique lesquelles. Acceptez "
    "seulement si vous ne comptez plus les rédiger ; vous pourrez annuler."
)
_UNDO_QUESTION = (
    "L'agent veut annuler sa dernière modification de votre document, faite "
    "lors d'un échange précédent. Acceptez seulement si c'est ce que vous avez "
    "demandé."
)


def _undo_asked_by_collaborator(request: HitlGateRequest) -> bool:
    """An undo of an earlier turn's edit (declared as asked for) is approved
    by the collaborator; the middleware refuses it undeclared."""
    args = request.tool_call.get("args") or {}
    return isinstance(args, Mapping) and args.get("collaborator_asked") is True


def _parses(op: Any) -> bool:
    try:
        parse_operation(op)
    except (ValidationError, TypeError, ValueError):
        return False
    return True


def _batch_changes_structure(request: HitlGateRequest) -> bool:
    """Gate an `edit_document` batch that removes content or declares a
    change to the template (`changes_template`: fixed wording, a chapter),
    read from the call's arguments. Not gated: a malformed batch, or one found refused when the
    model planned it; the tool refuses them without changing anything, and
    the collaborator would accept them for nothing."""
    identity = getattr(request.context, "identity", None)
    planned = (
        getattr(identity, "session_id", None),
        str(request.tool_call.get("id") or ""),
    )
    if PREFLIGHT.get(planned) is not None:
        return False
    args = request.tool_call.get("args") or {}
    if not isinstance(args, Mapping):
        return False
    operations = args.get("operations")
    if not isinstance(operations, list):
        return False
    operations = [normalized(op) for op in operations]
    # An operation the engine will refuse: no approval for a batch that
    # cannot run (the collaborator would accept it for nothing).
    if not all(_parses(op) for op in operations):
        return False
    # A chapter is added only with changes_template (refused otherwise).
    return args.get("changes_template") is True or any(
        isinstance(op, Mapping)
        and str(op.get("op", "")).strip().lower() in ("remove", "move")
        for op in operations
    )
