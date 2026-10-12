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
import Icon from "@shared/atoms/Icon/Icon";
import styles from "./CommandMenu.module.css";

/** A library prompt command or a platform skill suggestion. */
export type CommandMenuEntry = {
  /** Where the entry comes from, which is also the section it is listed under. */
  source: CommandMenuSource;
  promptId: string;
  command: string;
  name: string;
  description?: string | null;
  emoji?: string | null;
} & ({ kind: "skill" } | { kind: "prompt"; promptTeamId: string });

type CommandMenuSource = "team" | "personal" | "platform";

// Display order of the sections. `entries` arrives in this same order, so each
// section is a contiguous slice and the flat index stays the visual order.
const SECTION_ORDER: readonly CommandMenuSource[] = ["team", "personal", "platform"];

interface CommandMenuProps {
  /** Id the composer points at with `aria-controls`. */
  id: string;
  entries: CommandMenuEntry[];
  /** Index of the focused entry — the composer keeps the caret, this the focus. */
  activeIndex: number;
  /** False when the team holds no command at all, which is worth saying plainly
   *  — a different miss from a query that matches none of the ones it has. */
  teamHasCommands: boolean;
  /** Name of the conversation's team, shown in its section heading. */
  teamName?: string;
  /** Builds the id the composer's active-descendant names. */
  optionId: (index: number) => string;
  /** Pointer activation, which behaves as `Tab`: completes, never sends. */
  onActivate: (index: number) => void;
  /** Hovering an entry focuses it, so pointer and keyboard share one highlight. */
  onFocusEntry: (index: number) => void;
}

export const CommandMenu = memo(function CommandMenu({
  id,
  entries,
  activeIndex,
  teamHasCommands,
  teamName,
  optionId,
  onActivate,
  onFocusEntry,
}: CommandMenuProps) {
  const { t } = useTranslation();
  const headingIdPrefix = useId();
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

  const headings: Record<CommandMenuSource, string> = {
    team: teamName
      ? t("chatbot.commandMenu.sections.team", { name: teamName })
      : t("chatbot.commandMenu.sections.teamFallback"),
    personal: t("chatbot.commandMenu.sections.personal"),
    platform: t("chatbot.commandMenu.sections.platform"),
  };
  // Rows keep their index in `entries`: option ids and the focus are global.
  const indexed = entries.map((entry, index) => ({ entry, index }));
  const sections = SECTION_ORDER.map((source) => ({
    source,
    rows: indexed.filter(({ entry }) => entry.source === source),
  })).filter((section) => section.rows.length > 0);

  return (
    <div id={id} ref={listRef} className={styles.menu} role="listbox" aria-label={t("chatbot.commandMenu.ariaLabel")}>
      {sections.map(({ source, rows }) => (
        <div
          key={source}
          className={styles.group}
          role="group"
          aria-labelledby={`${headingIdPrefix}-${source}`}
          data-source={source}
        >
          <div id={`${headingIdPrefix}-${source}`} className={styles.groupTitle} title={headings[source]}>
            {headings[source]}
          </div>
          {rows.map(({ entry, index }) => (
            <div
              key={`${entry.kind === "prompt" ? entry.promptTeamId : "platform"}:${entry.promptId}`}
              id={optionId(index)}
              className={styles.row}
              role="option"
              aria-selected={index === activeIndex}
              data-active={index === activeIndex}
              title={entry.description?.trim() || entry.name}
              onMouseMove={() => onFocusEntry(index)}
              onMouseDown={activate(index)}
            >
              <span className={`${styles.rowIcon} ${entry.kind === "prompt" ? styles.promptIcon : ""}`} aria-hidden>
                {entry.kind === "skill" ? (
                  <Icon category="outlined" type="customPlatformSkill" />
                ) : (
                  <Icon category="outlined" type="edit_note" />
                )}
              </span>
              <span className={styles.rowText}>
                <span className={styles.rowLabel}>{entry.kind === "skill" ? entry.name : `/${entry.command}`}</span>
                <em className={styles.rowDescription}>{entry.description?.trim() || entry.name}</em>
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
});
