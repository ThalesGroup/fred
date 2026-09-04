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

// The composer control slot (RFC §9 item 2) — the ONE host that mounts a
// session's chat-turn controls in the composer's actions popover. It replaces
// the hardcoded `SearchConfig` mount (CAPAB-01 #1976): which rows appear is now
// driven entirely by `ExecutionPreparation.chat_controls`, resolved through the
// one chat-turn-control registry (mirrors `CapabilitySidePanelHost` for the
// side-panel slot).
//
// The prompt-library row is NOT a capability control (PROMPT-05 is orthogonal
// to AGENT-CAPABILITY-RFC) — it stays hard-mounted here, always visible. It
// only opens the page's prompt-selection side panel; the picking itself no
// longer happens in this popover.

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import { COMPOSER_CHIP_WIDGETS } from "./ReasoningChip";
import { resolveChatTurnControls, type ResolvedChatTurnControl } from "./chatTurnControlRegistry";
import type { ChatTurnControlComposerState } from "./types";
import styles from "./ComposerControlSlot.module.css";

interface ComposerControlSlotProps {
  /** `ExecutionPreparation.chat_controls`, already ordered (RFC §3.3/§3.7). */
  chatControls: readonly ChatControlDescriptor[];
  /** Shared composer state every resolved control reads/writes. */
  composer: ChatTurnControlComposerState;
  /** Closes the whole composer actions popover (the slot's parent owns it). */
  onRequestClose?: () => void;
  /**
   * Which slice of the composer controls to render, so the composer can split
   * them across two trigger buttons:
   *  - "primary" (default): the attach action + the always-on prompt-library row.
   *  - "tools": the search / scope / reasoning / document-scope controls.
   */
  part?: "primary" | "tools";
}

const controlKey = (entry: ResolvedChatTurnControl): string => `${entry.capabilityId}:${entry.widget}`;

export function ComposerControlSlot({
  chatControls,
  composer,
  onRequestClose,
  part = "primary",
}: ComposerControlSlotProps) {
  const { t } = useTranslation();
  const rootRef = useRef<HTMLDivElement>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);

  const resolved = useMemo(() => resolveChatTurnControls(chatControls), [chatControls]);
  // Split by widget id (data-driven presence, not capability branching): attach
  // goes in the "primary" menu alongside the prompts row, everything else in
  // the "tools" menu — see `part` below. COMPOSER_CHIP_WIDGETS
  // (reasoning_toggle) are promoted to always-visible composer chips instead
  // (ReasoningChip, right edge), so they're excluded here to avoid the same
  // setting appearing twice.
  const attachControls = resolved.filter((entry) => entry.widget === "attach_files");
  const otherControls = resolved.filter(
    (entry) => entry.widget !== "attach_files" && !COMPOSER_CHIP_WIDGETS.has(entry.widget),
  );

  useEffect(() => {
    if (!openKey) return;

    const handleMouseDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpenKey(null);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenKey(null);
    };

    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [openKey]);

  const renderControl = (entry: ResolvedChatTurnControl) => {
    const key = controlKey(entry);
    const { Component } = entry;
    return (
      <Component
        key={key}
        params={entry.params}
        composer={composer}
        open={openKey === key}
        onToggleOpen={() => setOpenKey((current) => (current === key ? null : key))}
        onRequestClose={onRequestClose}
      />
    );
  };

  // The always-on prompt-library row. Picking a prompt now happens in the
  // right-side panel the page owns, so this row only opens it and dismisses
  // the actions popover — the user lands back on the input either way.
  const promptsRow = !composer.onOpenPromptLibraryPanel ? null : (
    <MenuPopoverItem
      key="prompts"
      icon={{ category: "outlined", type: "edit_note" }}
      label={t("chatbot.promptSelectionPanel.menuRow")}
      aria-haspopup="dialog"
      onClick={() => {
        composer.onOpenPromptLibraryPanel?.();
        onRequestClose?.();
      }}
    />
  );

  // "primary" holds the attach action + prompt row; "tools" holds the search /
  // scope / reasoning / document-scope controls — the composer mounts each part
  // behind its own trigger button. Attach + prompts share a single group (no
  // divider between them) — unlike the former SearchConfig layout, this menu
  // reads as one flat list of actions rather than two visually split groups.
  const groups =
    part === "tools"
      ? [otherControls.map(renderControl)]
      : [[...attachControls.map(renderControl), promptsRow].filter(Boolean)];

  return (
    <MenuPopover
      ref={rootRef}
      className={part === "tools" ? styles.controlSlotBox : styles.primaryMenuBox}
      groups={groups}
    />
  );
}
