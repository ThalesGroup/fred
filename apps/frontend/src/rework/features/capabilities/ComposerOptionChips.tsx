// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Promotes a small set of closed-choice chat-turn controls to always-visible
// `ContextualPicker` chips in the composer's bottomRow (RichInputField's
// `topSlot`), instead of only living inside the "tune" popover
// (`ComposerControlSlot`, part="tools") — mirrors Gemini's "Deep Search"
// chip. `COMPOSER_CHIP_WIDGETS` is the single source of truth for which
// widget ids were promoted: `ComposerControlSlot` excludes them from its
// "tools" render and `ManagedChatPage`'s `hasToolControls` guard excludes
// them too, so the tune button never opens onto an empty popover when an
// agent only exposes chip-only controls.
//
// This placement is expected to keep moving between the tune menu and a
// standalone chip as positioning is iterated on — to move a widget back into
// the tune menu, remove it from COMPOSER_CHIP_WIDGETS and delete its chip
// block below; its `EnumSelectRow`-based row (`stockKit/`) was never
// deleted, so it reappears in the tune popover with no other change needed.
// search_policy moved back to the tune menu on 2026-08-06 (was a chip
// 2026-08-05–2026-08-06); rag_scope stays a chip.

import { useTranslation } from "react-i18next";
import { ContextualPicker } from "@shared/molecules/ContextualPicker/ContextualPicker";
import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState, RagScopeName } from "./types";
import styles from "./ComposerOptionChips.module.css";

export const COMPOSER_CHIP_WIDGETS = new Set(["rag_scope"]);

interface ComposerOptionChipsProps {
  /** `ExecutionPreparation.chat_controls` — same list ComposerControlSlot reads. */
  chatControls: readonly ChatControlDescriptor[];
  /** Shared composer state (same object passed to ComposerControlSlot). */
  composer: ChatTurnControlComposerState;
}

export function ComposerOptionChips({ chatControls, composer }: ComposerOptionChipsProps) {
  const { t } = useTranslation();
  const hasRagScope = chatControls.some((control) => control.widget === "rag_scope");

  if (!hasRagScope) return null;

  return (
    <div className={styles.row}>
      <ContextualPicker<RagScopeName>
        icon={{ category: "outlined", type: "book_2" }}
        title={t("chatbot.composerSettings.scopeTitle")}
        value={composer.ragScope}
        onChange={composer.onRagScopeChange}
        options={[
          { value: "corpus_only", label: t("chatbot.composerSettings.scopeCorpus") },
          { value: "hybrid", label: t("chatbot.composerSettings.scopeCorpusAndWeb") },
          { value: "general_only", label: t("chatbot.composerSettings.scopeGeneral") },
        ]}
      />
    </div>
  );
}
