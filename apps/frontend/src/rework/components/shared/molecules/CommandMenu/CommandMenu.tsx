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

import { memo, useId, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import styles from "./CommandMenu.module.css";

/** One invocable entry. Today always a library prompt carrying a command. */
export interface CommandMenuEntry {
  promptId: string;
  command: string;
  name: string;
  description?: string | null;
  emoji?: string | null;
}

interface CommandMenuProps {
  /** Id the composer points at with `aria-controls`. */
  id: string;
  entries: CommandMenuEntry[];
  /** Index of the focused entry — the composer keeps the caret, this the focus. */
  activeIndex: number;
  /** Builds the id the composer's active-descendant names. */
  optionId: (index: number) => string;
  /** Pointer activation, which behaves as `Tab`: completes, never sends. */
  onActivate: (index: number) => void;
  /** Hovering an entry focuses it, so pointer and keyboard share one highlight. */
  onFocusEntry: (index: number) => void;
}

// Sectioned from day one with a single section: adding a second kind of
// invocable object is then a new entry rather than a visual change.
export const CommandMenu = memo(function CommandMenu({
  id,
  entries,
  activeIndex,
  optionId,
  onActivate,
  onFocusEntry,
}: CommandMenuProps) {
  const { t } = useTranslation();
  const headingId = useId();

  // Activating on mousedown, with the default suppressed: a click that first
  // blurred the textarea would take the caret out of the composer.
  const activate = (index: number) => (event: MouseEvent) => {
    event.preventDefault();
    onActivate(index);
  };

  return (
    <div id={id} className={styles.menu} role="listbox" aria-label={t("chatbot.commandMenu.ariaLabel")}>
      <div className={styles.group} role="group" aria-labelledby={headingId}>
        <div id={headingId} className={styles.groupTitle}>
          {t("chatbot.commandMenu.promptsSection")}
        </div>
        {entries.map((entry, index) => (
          <div
            key={entry.promptId}
            id={optionId(index)}
            className={styles.row}
            role="option"
            aria-selected={index === activeIndex}
            data-active={index === activeIndex}
            onMouseMove={() => onFocusEntry(index)}
            onMouseDown={activate(index)}
          >
            <span className={styles.rowIcon} aria-hidden>
              {entry.emoji?.trim() || "/"}
            </span>
            <span className={styles.rowText}>
              <span className={styles.rowLabel}>/{entry.command}</span>
              <span className={styles.rowSublabel}>{entry.description?.trim() || entry.name}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
});
