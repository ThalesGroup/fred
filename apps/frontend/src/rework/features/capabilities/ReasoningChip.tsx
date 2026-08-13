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

// The per-question reasoning control (REASON-01 level 4), styled after the
// designer's Composer.html mockup (2026-08-12): a plain TEXT BUTTON with a
// chevron at the right edge of the composer's bottomRow (RichInputField's
// `rightExtraSlot`, before the mic). The button reads "Raisonnement" when off
// and the model's effort level when on ("Élevé"); its menu opens above,
// right-aligned, with the effort/latency explainer as a muted header and two
// check-circle rows: Désactivé, and the ON row labeled with the level.
//
// The level shown is the model's own ops-authored `settings.reasoning_effort`
// — the single source of truth (no separate supported-efforts declaration) —
// served on the control's `params.effort`. The wire stays the tri-state
// boolean: picking the level row means `reasoning: true` and the pod applies
// the live settings value; no per-question effort override exists
// (RUNTIME-EXECUTION-CONTRACT §8.48 records why: providers 400 on values
// they don't support). No effort in params = generic "Activé" label.
//
// `COMPOSER_CHIP_WIDGETS` is the single source of truth for which widget ids
// are promoted out of the "tune" popover: `ComposerControlSlot` excludes them
// from its "tools" render and `ManagedChatPage`'s `hasToolControls` guard
// excludes them too, so the tune button never opens onto an empty popover
// when an agent only exposes promoted controls.

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState } from "./types";
import styles from "./ReasoningChip.module.css";

export const COMPOSER_CHIP_WIDGETS = new Set(["reasoning_toggle"]);

/** The model name the button shows: whatever ops authored as
 *  `model_display_name` in `models_catalog.yaml`, else the derived guess
 *  below. Ops win because only they know whether a hyphen is a version
 *  separator ("claude-sonnet-4-6") or a variant one ("gpt-4.1-mini").
 *  Exported for tests. */
export function modelLabel(displayName: unknown, modelId: unknown): string | null {
  if (typeof displayName === "string" && displayName.trim()) return displayName.trim();
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
  // Split on hyphens ONLY: dots are version numbers (gpt-4.1, gemini-2.5-pro)
  // and must survive; the provider/name separator is the double underscore
  // consumed above. Anthropic-style 8-digit date stamps (…-20251001) are
  // release plumbing, not identity — dropped. "latest" is kept: it is part of
  // how ops pinned the model and says something true about it.
  const words = parts
    .slice(2)
    .join("__")
    .split("-")
    .filter((word) => word.length > 0 && !/^\d{8}$/.test(word));
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

/** i18n key for one ops-authored effort value; null for unknown/absent values
 *  (the caller then falls back to the generic On label). Exported for tests. */
export function effortLabelKey(effort: unknown): string | null {
  if (effort === "low") return "chatbot.composerSettings.reasoningLow";
  if (effort === "medium") return "chatbot.composerSettings.reasoningMedium";
  if (effort === "high") return "chatbot.composerSettings.reasoningHigh";
  return null;
}

interface ReasoningChipProps {
  /** `ExecutionPreparation.chat_controls` — same list ComposerControlSlot reads. */
  chatControls: readonly ChatControlDescriptor[];
  /** Shared composer state (same object passed to ComposerControlSlot). */
  composer: ChatTurnControlComposerState;
  /** Mirrors the add/tune menu buttons: no picking while a response streams. */
  disabled?: boolean;
}

export function ReasoningChip({ chatControls, composer, disabled = false }: ReasoningChipProps) {
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

  // Only agents whose author enabled reasoning (and with a platform-enabled
  // reasoning model) emit the platform reasoning_toggle control — no control,
  // no button, same gate the tune-menu row used.
  const control = chatControls.find((entry) => entry.widget === "reasoning_toggle");
  if (!control) return null;

  const on = composer.reasoning;
  const title = t("chatbot.composerSettings.reasoningRowLabel");
  const params = control.params as { effort?: unknown; model_id?: unknown; display_name?: unknown } | undefined;
  const levelKey = effortLabelKey(params?.effort);
  const onLabel = levelKey ? t(levelKey) : t("chatbot.composerSettings.reasoningOn");
  const offLabel = t("chatbot.composerSettings.reasoningOff");
  // Model identity first, Claude-style ("Mistral Small Élevé"): model in the
  // regular button text, reasoning state one step fainter
  // (--on-surface-muted) — the color contrast is the separator. Read-only
  // today, the model picker slot tomorrow. Without an unambiguous model the
  // button falls back to the mockup's bare labels.
  const displayLabel = modelLabel(params?.display_name, params?.model_id);
  const stateLabel = on ? onLabel : offLabel;

  const pick = (next: boolean) => {
    composer.onReasoningChange(next);
    setOpen(false);
    triggerRef.current?.focus();
  };

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
        aria-label={`${title}: ${on ? onLabel : offLabel}`}
        onClick={() => setOpen((current) => !current)}
      >
        {displayLabel ? (
          <>
            <span className={styles.model}>{displayLabel}</span>
            <span className={styles.state}>{stateLabel}</span>
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
            aria-label={title}
            header={<div className={styles.description}>{t("chatbot.composerSettings.reasoningHint")}</div>}
            groups={[
              [
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
                  label={onLabel}
                  selected={on}
                  accentSelected
                  trailingIcon={on ? "check_circle" : undefined}
                  onClick={() => pick(true)}
                />,
              ],
            ]}
          />
        </div>
      )}
    </div>
  );
}
