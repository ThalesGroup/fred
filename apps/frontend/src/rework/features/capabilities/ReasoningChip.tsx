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
// and "Activé" when on; its menu opens above, right-aligned, with the
// effort/latency explainer as a muted header and two check-circle rows:
// Désactivé and Activé.
//
// Deliberately NOT a level picker, and since #2387 not a level DISPLAY either.
// The effort a reasoning turn runs with is the model's ops-authored
// `settings.reasoning_effort`, applied live by the pod; surfacing it here
// implied a per-question choice that never existed, and it was snapshotted
// through two DB columns to reach the composer at all. A same-day effort
// picker was withdrawn for a related reason (RUNTIME-EXECUTION-CONTRACT §8.48:
// providers 400 on values they do not support). The wire stays the tri-state
// boolean.
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
import type { ChatControlDescriptor, EffectiveChatModel } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState } from "./types";
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
  /** The model the next turn will actually route to (#2387).
   *
   *  The chip used to take its model identity from the reasoning control's own
   *  `params` — i.e. the single model whose REASONING an admin had enabled
   *  platform-wide, which has nothing to do with routing. With a platform
   *  binding or any override in force it therefore named a model that was not
   *  answering. This prop is the resolved answer instead, and the two concerns
   *  are now independent: the model always shows, the reasoning menu still only
   *  appears when the `reasoning_toggle` control does. */
  effectiveModel?: EffectiveChatModel;
}

export function ReasoningChip({ chatControls, composer, disabled = false, effectiveModel }: ReasoningChipProps) {
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
  // no reasoning MENU, same gate the tune-menu row used. It no longer gates the
  // chip itself: the model label is independent of reasoning (#2387), so an
  // agent that offers no reasoning still gets to say which model answers.
  const platformControl = chatControls.find((entry) => entry.widget === "reasoning_toggle");
  // The control says "the platform enabled reasoning on SOME model and this
  // agent offers it" — it cannot say whether the model this turn routes to is
  // one of them, because computing that needs the pod catalog and the
  // prepare-execution path must stay free of catalog fetches.
  //
  // So the routed model has the last word. `RoutedChatModelFactory` STRIPS the
  // reasoning settings for a model whose reasoning is off, so offering the
  // toggle here would be offering something inert: the user flips it on and the
  // turn silently does not reason. Concretely, with reasoning enabled on Mistral
  // Small and a team override routing to Mistral Medium, the chip used to render
  // "Mistral Medium · Désactivé" with a working-looking toggle behind it.
  //
  // `undefined` (no resolution yet, or an older backend) leaves the control as
  // the platform served it — the pre-#2387 behaviour, not a silent hide.
  const control = effectiveModel?.reasoning_enabled === false ? undefined : platformControl;

  const on = composer.reasoning;
  const title = t("chatbot.composerSettings.reasoningRowLabel");
  // Plain on/off, never a level. The effort a reasoning turn runs with is the
  // pod's ops-authored `settings.reasoning_effort`, applied live — quoting it
  // back at the user implied a choice that never existed (#2387).
  const onLabel = t("chatbot.composerSettings.reasoningOn");
  const offLabel = t("chatbot.composerSettings.reasoningOff");
  // Model identity first, Claude-style ("Mistral Small Élevé"): model in the
  // regular button text, reasoning state one step fainter
  // (--on-surface-muted) — the color contrast is the separator.
  //
  // Sourced from the RESOLVED model, never from the reasoning control: the
  // capability id is the same `model__{provider}__{name}` shape `modelLabel`
  // already knew how to split, so the id-splitting fallback still covers a
  // model whose catalog names no `model_display_name`.
  const displayLabel = modelLabel(effectiveModel?.display_name, effectiveModel?.name, effectiveModel?.capability_id);
  const stateLabel = on ? onLabel : offLabel;
  // The turn will fail with ModelNotUsableError before the LLM call. Say so
  // here rather than letting the user discover an opaque error — the same
  // diagnosability rule REASON-01 §8 applies to the reasoning control itself.
  const unavailable = effectiveModel?.enabled_for_team === false;
  const unavailableLabel = t("chatbot.composerSettings.modelNotEnabledForTeam");

  // Nothing to show and nothing to pick: no reasoning control, and no model
  // resolved (a pod that declares no chat default and has no team policy, or an
  // unreachable pod). Rendering an empty chip would be worse than none.
  if (!control && !displayLabel) return null;

  // Model label with no reasoning menu behind it — a plain, non-interactive
  // statement of which model answers. Deliberately not a disabled button: there
  // is no action being withheld, so nothing should look clickable.
  if (!control) {
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
        aria-label={
          unavailable
            ? `${title}: ${on ? onLabel : offLabel} — ${unavailableLabel}`
            : `${title}: ${on ? onLabel : offLabel}`
        }
        title={unavailable ? unavailableLabel : undefined}
        onClick={() => setOpen((current) => !current)}
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
