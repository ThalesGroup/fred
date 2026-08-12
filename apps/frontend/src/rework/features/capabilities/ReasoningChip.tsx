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

// The per-question reasoning toggle (REASON-01 level 4), rendered as an
// always-visible pill chip anchored at the right edge of the composer's
// bottomRow (RichInputField's `rightExtraSlot`, just before the mic/send
// group) — Claude's composer, whose model/effort control anchors the right
// edge, is the visual reference. `COMPOSER_CHIP_WIDGETS` is the single source
// of truth for which widget ids are promoted out of the "tune" popover:
// `ComposerControlSlot` excludes them from its "tools" render and
// `ManagedChatPage`'s `hasToolControls` guard excludes them too, so the tune
// button never opens onto an empty popover when an agent only exposes
// promoted controls.
//
// This placement is expected to keep moving as positioning is iterated on —
// to move a widget back into the tune menu, remove it from
// COMPOSER_CHIP_WIDGETS and delete its chip; its row component (`stockKit/`)
// is never deleted, so it reappears in the tune popover with no other change
// needed. History: search_policy was a chip 2026-08-05–2026-08-06; rag_scope
// was a chip (ComposerOptionChips/ContextualPicker) 2026-08-07–2026-08-12;
// both are back in the tune menu, replaced by this reasoning chip.

import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState } from "./types";
import styles from "./ReasoningChip.module.css";

export const COMPOSER_CHIP_WIDGETS = new Set(["reasoning_toggle"]);

interface ReasoningChipProps {
  /** `ExecutionPreparation.chat_controls` — same list ComposerControlSlot reads. */
  chatControls: readonly ChatControlDescriptor[];
  /** Shared composer state (same object passed to ComposerControlSlot). */
  composer: ChatTurnControlComposerState;
  /** Mirrors the add/tune menu buttons: no toggling while a response streams. */
  disabled?: boolean;
}

export function ReasoningChip({ chatControls, composer, disabled = false }: ReasoningChipProps) {
  const { t } = useTranslation();
  // Only agents whose author enabled reasoning (and with a platform-enabled
  // reasoning model) emit the platform reasoning_toggle control — no control,
  // no chip, same gate the tune-menu row used.
  const offersReasoning = chatControls.some((control) => control.widget === "reasoning_toggle");
  if (!offersReasoning) return null;

  const on = composer.reasoning;
  return (
    <button
      type="button"
      className={styles.chip}
      data-on={on}
      aria-pressed={on}
      disabled={disabled}
      onClick={() => composer.onReasoningChange(!on)}
    >
      <span className={styles.icon}>
        <Icon category="outlined" type="auto_awesome" />
      </span>
      <span className={styles.label}>{t("chatbot.composerSettings.reasoningRowLabel")}</span>
    </button>
  );
}
