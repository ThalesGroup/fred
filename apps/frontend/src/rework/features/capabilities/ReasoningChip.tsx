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

// The composer's model and reasoning control: a text button at the right edge
// of the composer naming the current model and reasoning mode, whose menu lists
// the selectable models and the two reasoning modes (never an effort level).
// `COMPOSER_CHIP_WIDGETS` keeps its widget ids out of the "tune" popover.

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import type { ChatControlDescriptor, EffectiveChatModel } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState } from "./types";
import { currentModelRow, offersReasoning } from "./modelChoice";
import styles from "./ReasoningChip.module.css";

export const COMPOSER_CHIP_WIDGETS = new Set(["reasoning_toggle"]);

/** The model name the button shows: whatever ops authored as
 *  `model_display_name` in `models_catalog.yaml`, else the derived guess
 *  below. Ops win because only they know whether a hyphen is a version
 *  separator ("claude-sonnet-4-6") or a variant one ("gpt-4.1-mini").
 *  Exported for tests. */
export function modelLabel(displayName: unknown, modelName: unknown, modelId: unknown): string | null {
  if (typeof displayName === "string" && displayName.trim()) return displayName.trim();
  // The real model name before the capability id, because `model_capability_id`
  // normalizes characters outside the id charset to `-`: derived from the id,
  // "mistral:latest" would read "Mistral Latest" (#2387).
  if (typeof modelName === "string" && modelName.trim()) return prettifyModelName(modelName.trim());
  return modelLabelFromCapabilityId(modelId);
}

/** Fallback label derived from a `model__{provider}__{name}` capability id —
 *  "model__openai__gpt-4.1-mini" → "GPT 4.1 Mini". Used only when the catalog
 *  names no `model_display_name`; it is a guess, and ops override it per
 *  model rather than grow another special case here. Exported for tests. */
export function modelLabelFromCapabilityId(modelId: unknown): string | null {
  if (typeof modelId !== "string") return null;
  const parts = modelId.split("__");
  if (parts.length < 3 || parts[0] !== "model") return null;
  return prettifyModelName(parts.slice(2).join("__"));
}

/** Turn a raw model name into a display label — "gpt-4.1-mini" → "GPT 4.1 Mini".
 *  Shared by the `name` and capability-id paths above so both prettify
 *  identically. Exported for tests. */
export function prettifyModelName(rawName: string): string | null {
  // Split on hyphens ONLY: dots are version numbers (gpt-4.1, gemini-2.5-pro)
  // and must survive. Anthropic-style 8-digit date stamps (…-20251001) are
  // release plumbing, not identity — dropped. "latest" is kept: it is part of
  // how ops pinned the model and says something true about it.
  const words = rawName.split("-").filter((word) => word.length > 0 && !/^\d{8}$/.test(word));
  if (words.length === 0) return null;
  const acronyms: Record<string, string> = { gpt: "GPT", chatgpt: "ChatGPT", deepseek: "DeepSeek" };
  return words
    .map((word) => {
      const lower = word.toLowerCase();
      if (acronyms[lower]) return acronyms[lower];
      // Size tokens read better uppercased: 8b → 8B, 70b → 70B, 8x7b → 8x7B.
      if (/^\d+(?:x\d+)?b$/.test(lower)) return lower.toUpperCase().replace("X", "x");
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");
}

interface ReasoningChipProps {
  /** `ExecutionPreparation.chat_controls` — same list ComposerControlSlot reads. */
  chatControls: readonly ChatControlDescriptor[];
  /** Shared composer state (same object passed to ComposerControlSlot). */
  composer: ChatTurnControlComposerState;
  /** Mirrors the add/tune menu buttons: no picking while a response streams. */
  disabled?: boolean;
  /** The agent's resolved model and the models a member may pick. */
  effectiveModel?: EffectiveChatModel;
  /** The conversation's model choice; null runs the recommended model. */
  chatProfileId?: string | null;
  onChatProfileChange?: (profileId: string) => void;
}

/**
 * One compact composer control: the current model, a menu listing the
 * selectable models and, when the current model can reason, the reasoning row.
 * Read-only text when nothing can be picked.
 */
export function ReasoningChip({
  chatControls,
  composer,
  disabled = false,
  effectiveModel,
  chatProfileId = null,
  onChatProfileChange,
}: ReasoningChipProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Same compact close contract as ContextualPicker: click outside closes,
  // Escape closes and restores focus to the trigger.
  useEffect(() => {
    if (!open) return;
    const handleMouseDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const locked = effectiveModel?.choice_locked === true;
  const rows = locked ? [] : (effectiveModel?.selectable_models ?? []);
  const current = currentModelRow(effectiveModel, chatProfileId);
  // A model the routed turn would strip reasoning from gets no reasoning row.
  const showReasoning = offersReasoning(chatControls, effectiveModel, chatProfileId);

  const on = composer.reasoning;
  const title = t("chatbot.composerSettings.reasoningRowLabel");
  // Two modes, never a level: the effort is the pod's ops-authored setting.
  const onLabel = t("chatbot.composerSettings.reasoningOn");
  const offLabel = t("chatbot.composerSettings.reasoningOff");
  // The "(Raisonnement)" wording lives in the menu only.
  const onMenuLabel = t("chatbot.composerSettings.reasoningOnMenu");
  const displayLabel = current
    ? modelLabel(current.display_name, current.name, current.capability_id)
    : modelLabel(effectiveModel?.display_name, effectiveModel?.name, effectiveModel?.capability_id);
  const stateLabel = on ? onLabel : offLabel;
  // The recommended model the team cannot use fails the turn: say so up front.
  const unavailable = !current && effectiveModel?.enabled_for_team === false;
  const unavailableLabel = t("chatbot.composerSettings.modelNotEnabledForTeam");
  const canPickModel = rows.length > 1 && !!onChatProfileChange;

  if (!showReasoning && !displayLabel) return null;

  // Nothing to pick: a plain statement of which model answers, not a disabled button.
  if (!showReasoning && !canPickModel) {
    return (
      <div className={styles.wrap}>
        <span
          className={styles.static}
          title={unavailable ? unavailableLabel : undefined}
          aria-label={unavailable ? `${displayLabel} — ${unavailableLabel}` : (displayLabel ?? undefined)}
        >
          <span className={styles.model} data-unavailable={unavailable || undefined}>
            {displayLabel}
          </span>
          {unavailable && (
            <span className={styles.warning} aria-hidden="true">
              <Icon category="outlined" type="error_outline" />
            </span>
          )}
        </span>
      </div>
    );
  }

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };
  const pick = (next: boolean) => {
    composer.onReasoningChange(next);
    close();
  };
  const pickModel = (profileId: string) => {
    onChatProfileChange?.(profileId);
    close();
  };
  const ariaLabel = showReasoning
    ? `${displayLabel ? `${displayLabel}, ` : ""}${title}: ${stateLabel}`
    : (displayLabel ?? title);

  // Model rows: the selectable models, or (older backend) the resolved model
  // as one read-only row. A locked choice lists none.
  const modelRows = rows.length
    ? rows.map((row) => {
        const selected = row.profile_id === current?.profile_id;
        return (
          <MenuPopoverItem
            key={row.profile_id}
            role="option"
            label={modelLabel(row.display_name, row.name, row.capability_id) ?? row.profile_id}
            selected={selected}
            accentSelected
            trailingIcon={selected ? "check_circle" : undefined}
            onClick={canPickModel ? () => pickModel(row.profile_id) : undefined}
          />
        );
      })
    : !locked && displayLabel
      ? [
          <MenuPopoverItem
            key="model"
            role="option"
            label={displayLabel}
            selected
            accentSelected
            trailingIcon="check_circle"
          />,
        ]
      : [];

  // The menu is named after the sections it shows.
  const menuLabel =
    modelRows.length && showReasoning
      ? t("chatbot.composerSettings.modelAndReasoningMenu")
      : modelRows.length
        ? t("chatbot.composerSettings.reasoningModelsSection")
        : title;

  return (
    <div ref={containerRef} className={styles.wrap}>
      <button
        ref={triggerRef}
        type="button"
        className={styles.trigger}
        data-open={open}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={unavailable ? `${ariaLabel} — ${unavailableLabel}` : ariaLabel}
        title={unavailable ? unavailableLabel : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        {displayLabel ? (
          <>
            <span className={styles.model} data-unavailable={unavailable || undefined}>
              {displayLabel}
            </span>
            {unavailable && (
              <span className={styles.warning} aria-hidden="true">
                <Icon category="outlined" type="error_outline" />
              </span>
            )}
            {showReasoning && <span className={styles.state}>{stateLabel}</span>}
          </>
        ) : (
          <span className={styles.value}>{on ? onLabel : title}</span>
        )}
        <span className={styles.chevron}>
          <Icon category="outlined" type="keyboard_arrow_down" />
        </span>
      </button>

      {open && (
        <div className={styles.menu}>
          <MenuPopover
            dense
            quietUnselected
            aria-label={menuLabel}
            groups={[
              ...(modelRows.length
                ? [
                    [
                      <div key="models-title" className={styles.sectionTitle}>
                        {t("chatbot.composerSettings.reasoningModelsSection")}
                      </div>,
                      ...modelRows,
                    ],
                  ]
                : []),
              ...(showReasoning
                ? [
                    [
                      <div key="effort-title" className={styles.sectionTitle}>
                        {t("chatbot.composerSettings.reasoningEffortSection")}
                      </div>,
                      <MenuPopoverItem
                        key="off"
                        role="option"
                        label={offLabel}
                        selected={!on}
                        accentSelected
                        trailingIcon={!on ? "check_circle" : undefined}
                        onClick={() => pick(false)}
                      />,
                      <MenuPopoverItem
                        key="on"
                        role="option"
                        label={onMenuLabel}
                        selected={on}
                        accentSelected
                        trailingIcon={on ? "check_circle" : undefined}
                        onClick={() => pick(true)}
                      />,
                    ],
                  ]
                : modelRows.length
                  ? [
                      // The section stays, so the menu reads the same for every model.
                      [
                        <div key="effort-title" className={styles.sectionTitle}>
                          {t("chatbot.composerSettings.reasoningEffortSection")}
                        </div>,
                        <div key="effort-none" className={styles.sectionEmpty}>
                          {t("chatbot.composerSettings.reasoningEffortNone")}
                        </div>,
                      ],
                    ]
                  : []),
            ]}
          />
        </div>
      )}
    </div>
  );
}
