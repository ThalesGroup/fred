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

// The per-question reasoning control (REASON-01 level 4): an always-visible
// chip anchored at the right edge of the composer's bottomRow (RichInputField's
// `rightExtraSlot`, just before the mic/send group). Claude's composer is the
// UI reference, faithfully: the chip shows the MODEL IDENTITY plus the
// reasoning state ("Mistral Small · Activé"), and its menu holds ONE switch
// row — label + trailing toggle, flipped in place, popover stays open so the
// user can keep composing — under a muted header stating the trade-off
// (more thorough, slower). The switch row reuses the exact affordance of the
// retired tune-menu row (`MenuPopoverItem trailingToggle`, role
// menuitemcheckbox): one on/off setting, the same switch here, on the agent
// form, and on the admin models page — never a checkbox, never an options
// list.
//
// Deliberately ON/OFF only — a per-question EFFORT picker was built and
// withdrawn the same day (2026-08-12): providers disagree on the accepted
// values (Mistral small 400s on low/medium; RUNTIME-EXECUTION-CONTRACT §8.48).
// The effort a reasoning turn runs with is the ops-authored `reasoning_effort`
// in the routed profile's settings, full stop.
//
// Multi-model readiness (deliberately NOT displayed yet): the model identity
// arrives as a plain `modelProfileId` prop, so when model selection ships as
// a Fred feature this menu grows a model section fed by real catalog display
// names and `modelLabelFromProfileId` dies — nothing else moves.
//
// `COMPOSER_CHIP_WIDGETS` is the single source of truth for which widget ids
// are promoted out of the "tune" popover: `ComposerControlSlot` excludes them
// from its "tools" render and `ManagedChatPage`'s `hasToolControls` guard
// excludes them too, so the tune button never opens onto an empty popover
// when an agent only exposes promoted controls.

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState } from "./types";
import styles from "./ReasoningChip.module.css";

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
  /** Mirrors the add/tune menu buttons: no toggling while a response streams. */
  disabled?: boolean;
}

export function ReasoningChip({ chatControls, composer, modelProfileId = null, disabled = false }: ReasoningChipProps) {
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
  // no chip, same gate the tune-menu row used.
  const offersReasoning = chatControls.some((control) => control.widget === "reasoning_toggle");
  if (!offersReasoning) return null;

  const on = composer.reasoning;
  const title = t("chatbot.composerSettings.reasoningRowLabel");
  const stateLabel = t(on ? "chatbot.composerSettings.reasoningOn" : "chatbot.composerSettings.reasoningOff");
  const modelLabel = modelLabelFromProfileId(modelProfileId);

  return (
    <div ref={containerRef} className={styles.wrap}>
      <Tooltip text={title}>
        <button
          ref={triggerRef}
          type="button"
          className={styles.chip}
          data-open={open}
          data-accent={on || undefined}
          disabled={disabled}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label={`${title}: ${stateLabel}`}
          onClick={() => setOpen((current) => !current)}
        >
          <span className={styles.icon}>
            <Icon category="outlined" type="auto_awesome" />
          </span>
          <span className={styles.value}>{modelLabel ? `${modelLabel} · ${stateLabel}` : stateLabel}</span>
        </button>
      </Tooltip>

      {open && (
        <div className={styles.menu}>
          <MenuPopover
            aria-label={title}
            header={<div className={styles.description}>{t("chatbot.composerSettings.reasoningHint")}</div>}
            groups={[
              [
                <MenuPopoverItem
                  key="reasoning"
                  icon={{ category: "outlined", type: "auto_awesome" }}
                  label={title}
                  // A switch, like the agent-form and admin-side reasoning
                  // controls it continues — the row IS the control, it opens
                  // no submenu, and the popover stays open: flip it and keep
                  // composing (Claude's "Thinking" toggle behaves the same).
                  trailingToggle
                  selected={on}
                  onClick={() => composer.onReasoningChange(!on)}
                />,
              ],
            ]}
          />
        </div>
      )}
    </div>
  );
}
