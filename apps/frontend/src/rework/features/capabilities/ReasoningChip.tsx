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

// The per-question reasoning EFFORT picker (REASON-01 level 4 + 4b), rendered
// as an always-visible ContextualPicker chip anchored at the right edge of the
// composer's bottomRow (RichInputField's `rightExtraSlot`, just before the
// mic/send group). Claude's composer is the visual reference: the chip shows
// the MODEL IDENTITY plus the selected mode ("Mistral Small · Élevé"), and the
// menu's header says what the trade-off is (higher effort = slower). "off"
// maps to `reasoning: false` on the wire; a level maps to `reasoning: true` +
// `reasoning_effort` (the runtime replaces the ops-authored effort on
// profiles that carry one, and stays inert everywhere else).
//
// Multi-model readiness (deliberately NOT displayed yet): the model identity
// arrives as a plain `modelProfileId` prop, so when model selection ships as
// a Fred feature the chip's menu grows a model section fed by real catalog
// display names and this file's `modelLabelFromProfileId` heuristic dies —
// nothing else in the composer needs to move.
//
// `COMPOSER_CHIP_WIDGETS` is the single source of truth for which widget ids
// are promoted out of the "tune" popover: `ComposerControlSlot` excludes them
// from its "tools" render and `ManagedChatPage`'s `hasToolControls` guard
// excludes them too, so the tune button never opens onto an empty popover
// when an agent only exposes promoted controls. History: search_policy was a
// chip 2026-08-05–2026-08-06; rag_scope was a chip 2026-08-07–2026-08-12;
// both are back in the tune menu, replaced by this effort picker (its
// tune-menu row predecessor, stockKit/ReasoningControl, was deleted with it).

import { useTranslation } from "react-i18next";
import { ContextualPicker } from "@shared/molecules/ContextualPicker/ContextualPicker";
import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState, ReasoningEffortName } from "./types";

export const COMPOSER_CHIP_WIDGETS = new Set(["reasoning_toggle"]);

/**
 * Human-ish label for a routing profile id — "chat.mistral.small" → "Mistral
 * Small". TEMPORARY heuristic: profile ids are ops-authored routing keys, not
 * display names; the multi-model feature will serve real catalog names and
 * replace this. Null in → null out (no team default profile: routing falls to
 * the pod's YAML rules, whose identity the frontend cannot know).
 */
export function modelLabelFromProfileId(profileId: string | null | undefined): string | null {
  if (!profileId) return null;
  const segments = profileId.split(".").filter(Boolean);
  // Leading capability/tier qualifiers ("chat", "default") are routing
  // vocabulary, not identity — drop them, keep provider/model words.
  while (segments.length > 1 && ["chat", "default", "language", "vision", "embedding"].includes(segments[0])) {
    segments.shift();
  }
  if (segments.length === 0) return null;
  return segments.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}

interface ReasoningChipProps {
  /** `ExecutionPreparation.chat_controls` — same list ComposerControlSlot reads. */
  chatControls: readonly ChatControlDescriptor[];
  /** Shared composer state (same object passed to ComposerControlSlot). */
  composer: ChatTurnControlComposerState;
  /** Team default chat profile id (`ExecutionPreparation.chat_default_profile_id`)
   *  — the session's model identity, shown on the chip. Null hides the model
   *  segment (identity unknown frontend-side). */
  modelProfileId?: string | null;
  /** Mirrors the add/tune menu buttons: no picking while a response streams. */
  disabled?: boolean;
}

export function ReasoningChip({ chatControls, composer, modelProfileId = null, disabled = false }: ReasoningChipProps) {
  const { t } = useTranslation();
  // Only agents whose author enabled reasoning (and with a platform-enabled
  // reasoning model) emit the platform reasoning_toggle control — no control,
  // no chip, same gate the tune-menu row used.
  const offersReasoning = chatControls.some((control) => control.widget === "reasoning_toggle");
  if (!offersReasoning) return null;

  const effortLabels: Record<ReasoningEffortName, string> = {
    off: t("chatbot.composerSettings.reasoningOff"),
    low: t("chatbot.composerSettings.reasoningLow"),
    medium: t("chatbot.composerSettings.reasoningMedium"),
    high: t("chatbot.composerSettings.reasoningHigh"),
  };
  const modelLabel = modelLabelFromProfileId(modelProfileId);
  const effortLabel = effortLabels[composer.reasoningEffort];

  return (
    <ContextualPicker<ReasoningEffortName>
      icon={{ category: "outlined", type: "auto_awesome" }}
      title={t("chatbot.composerSettings.reasoningRowLabel")}
      value={composer.reasoningEffort}
      valueLabel={modelLabel ? `${modelLabel} · ${effortLabel}` : effortLabel}
      description={t("chatbot.composerSettings.reasoningEffortHint")}
      onChange={composer.onReasoningEffortChange}
      disabled={disabled}
      accent={composer.reasoningEffort !== "off"}
      // "off" always; the levels are the session's narrowed set (params.efforts
      // — what the enabled models' providers actually accept). The pod-side
      // clamp guards whatever slips through anyway.
      options={[
        { value: "off", label: effortLabels.off },
        ...composer.reasoningEffortOptions.map((level) => ({ value: level, label: effortLabels[level] })),
      ]}
    />
  );
}
