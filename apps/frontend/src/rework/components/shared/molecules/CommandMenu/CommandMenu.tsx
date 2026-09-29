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

import { memo, useEffect, useId, useRef, type MouseEvent } from "react";
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
  /** False when the team holds no command at all, which is worth saying plainly
   *  — a different miss from a query that matches none of the ones it has. */
  teamHasCommands: boolean;
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
  teamHasCommands,
  optionId,
  onActivate,
  onFocusEntry,
}: CommandMenuProps) {
  const { t } = useTranslation();
  const headingId = useId();
  const listRef = useRef<HTMLDivElement>(null);

  // The list scrolls past 40vh, and the focus is conveyed by id rather than by
  // moving the caret — so nothing brings the focused row into view on its own.
  // Instant rather than smooth (unlike `Menu`): a held arrow key would queue
  // animations behind the focus it is already past.
  useEffect(() => {
    const focused = listRef.current?.querySelector(`[data-active="true"]`);
    focused?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, entries]);

  // Activating on mousedown, with the default suppressed: a click that first
  // blurred the textarea would take the caret out of the composer.
  const activate = (index: number) => (event: MouseEvent) => {
    event.preventDefault();
    onActivate(index);
  };

  // Nothing to offer: a status line rather than a listbox with no options, the
  // same swap `Menu` makes. The panel still shows — the placeholder has just
  // invited the user to type `/`, so vanishing would read as a broken hint.
  if (entries.length === 0) {
    return (
      <div id={id} className={styles.menu} role="status">
        <p className={styles.empty}>
          {teamHasCommands ? t("chatbot.commandMenu.noMatch") : t("chatbot.commandMenu.noneInTeam")}
        </p>
      </div>
    );
  }

  return (
    <div id={id} ref={listRef} className={styles.menu} role="listbox" aria-label={t("chatbot.commandMenu.ariaLabel")}>
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
