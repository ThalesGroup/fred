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
// The chat-context-prompts row is NOT a capability control (PROMPT-05 is
// orthogonal to AGENT-CAPABILITY-RFC) — it stays hard-mounted here, always
// visible, exactly as it was in the former `SearchConfig`, so attaching a
// chat-context prompt keeps working through the new slot.

import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ChatControlDescriptor, ContextPromptSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { ContextPromptPicker } from "@shared/molecules/ContextPromptPicker/ContextPromptPicker";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import { usePickerMenuMaxHeight } from "@shared/molecules/MenuPopover/usePickerMenuMaxHeight";
import { resolveChatTurnControls, type ResolvedChatTurnControl } from "./chatTurnControlRegistry";
import type { ChatTurnControlComposerState } from "./types";
import styles from "./ComposerControlSlot.module.css";

const PROMPTS_MENU_MAX_HEIGHT_PX = 480;
const CONTEXT_PROMPTS_KEY = "__context_prompts__";

interface ComposerControlSlotProps {
  /** `ExecutionPreparation.chat_controls`, already ordered (RFC §3.3/§3.7). */
  chatControls: readonly ChatControlDescriptor[];
  /** Shared composer state every resolved control reads/writes. */
  composer: ChatTurnControlComposerState;
  /** Closes the whole composer actions popover (the slot's parent owns it). */
  onRequestClose?: () => void;
  /** Chat-context prompts (PROMPT-05) — always-on, not capability-driven. */
  contextPrompts: ContextPromptSummary[];
  contextPromptIds: string[];
  onContextPromptIdsChange: (ids: string[]) => void;
}

const controlKey = (entry: ResolvedChatTurnControl): string => `${entry.capabilityId}:${entry.widget}`;

export function ComposerControlSlot({
  chatControls,
  composer,
  onRequestClose,
  contextPrompts,
  contextPromptIds,
  onContextPromptIdsChange,
}: ComposerControlSlotProps) {
  const { t } = useTranslation();
  const rootRef = useRef<HTMLDivElement>(null);
  const promptsWrapRef = useRef<HTMLDivElement>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);

  const resolved = useMemo(() => resolveChatTurnControls(chatControls), [chatControls]);
  // The former SearchConfig rendered the attach action alone in its own group,
  // separated by a divider from the picker/policy/scope group. Preserve that
  // layout by widget id (data-driven presence, not capability branching).
  const attachControls = resolved.filter((entry) => entry.widget === "attach_files");
  const otherControls = resolved.filter((entry) => entry.widget !== "attach_files");

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

  const promptsOpen = openKey === CONTEXT_PROMPTS_KEY;
  const promptsMenuStyle: CSSProperties = usePickerMenuMaxHeight(
    promptsOpen,
    promptsWrapRef,
    PROMPTS_MENU_MAX_HEIGHT_PX,
  );
  const promptsLabel =
    contextPromptIds.length > 0
      ? t("chatbot.contextPrompts.activeCount", { count: contextPromptIds.length })
      : t("chatbot.contextPrompts.none");

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

  return (
    <MenuPopover
      ref={rootRef}
      className={styles.controlSlotBox}
      groups={[
        attachControls.map(renderControl),
        [
          <div key="prompts" ref={promptsWrapRef} className={styles.rowWrap}>
            <MenuPopoverItem
              icon={{ category: "outlined", type: "auto_awesome" }}
              label={t("chatbot.contextPrompts.rowLabel")}
              value={promptsLabel}
              trailingIcon="chevron_right"
              aria-haspopup="dialog"
              aria-expanded={promptsOpen}
              onClick={() => setOpenKey((current) => (current === CONTEXT_PROMPTS_KEY ? null : CONTEXT_PROMPTS_KEY))}
            />

            {promptsOpen && (
              <div
                className={styles.pickerMenu}
                role="dialog"
                aria-label={t("chatbot.contextPrompts.title")}
                style={promptsMenuStyle}
              >
                <div className={styles.pickerMenuBody}>
                  <ContextPromptPicker
                    prompts={contextPrompts}
                    selectedIds={contextPromptIds}
                    onChange={onContextPromptIdsChange}
                  />
                </div>
              </div>
            )}
          </div>,
        ],
        otherControls.map(renderControl),
      ]}
    />
  );
}
