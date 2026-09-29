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

import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { CommandMenuEntry } from "@shared/molecules/CommandMenu/CommandMenu";
import type { CommandTriggerBinding } from "@shared/molecules/RichInputField/RichInputField";
import {
  useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery,
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { TurnCommand } from "../../../../slices/runtime/runtimeOpenApi";

/**
 * The composer's command trigger: the menu `/` opens, and the resolution of a
 * command on submit.
 *
 * Resolution happens on submit rather than only from the menu, so completing
 * with `Tab` and then pressing `Enter` reaches exactly the same place as
 * `Enter` from the open menu. Full rationale:
 * `openspec/changes/add-prompt-command-trigger/design.md`.
 */

/** A composer line that starts with a command, split from its trailing text. */
export function parseCommandLine(value: string): { command: string; appended: string } | null {
  const match = /^\/(\S+)(?:\s+([\s\S]*))?$/.exec(value.trim());
  return match ? { command: match[1], appended: (match[2] ?? "").trim() } : null;
}

export interface ComposerCommandsMenu {
  id: string;
  entries: CommandMenuEntry[];
  activeIndex: number;
  /** False when the team holds no command at all — a different empty state
   *  from a query that happens to match none of them. */
  teamHasCommands: boolean;
  optionId: (index: number) => string;
  onActivate: (index: number) => void;
  onFocusEntry: (index: number) => void;
}

export function useComposerCommands(params: {
  teamId: string;
  input: string;
  setInput: (value: string) => void;
  /** Sends the assembled prompt text with the descriptor on the turn's context. */
  onRunCommand: (run: { text: string; command: TurnCommand }) => void;
  /** Ordinary submit — no command, or a token no prompt holds. */
  onSend: () => void;
  /** The prompt behind a command could not be read. */
  onResolveError: () => void;
}): { trigger: CommandTriggerBinding; menu: ComposerCommandsMenu | null; submit: () => void } {
  const { teamId } = params;
  const listboxId = useId();
  const optionIdPrefix = useId();

  // Read through refs so every callback below keeps one identity across a
  // keystroke render: the menu is memoized, and the composer's own trigger
  // reporting is keyed on the callback it was handed.
  const paramsRef = useRef(params);
  paramsRef.current = params;

  // Its own endpoint rather than a filter over the prompt listing: that listing
  // is capped, and a command past the cap would resolve to nothing — silently,
  // since an unmatched token is sent to the agent as ordinary text.
  const { data: prompts } = useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery(
    { teamId },
    { skip: !teamId },
  );
  const [fetchPrompt] = useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery();

  const commands = useMemo<CommandMenuEntry[]>(
    () =>
      (prompts ?? []).map((prompt) => ({
        promptId: prompt.prompt_id,
        command: prompt.command,
        name: prompt.name,
        description: prompt.description,
        emoji: prompt.emoji,
      })),
    [prompts],
  );
  const commandsRef = useRef(commands);
  commandsRef.current = commands;

  // `null` while the composer holds no command query. `dismissedQuery` is the
  // query `Esc` closed the menu on: typing further reopens it, which keeps Esc
  // from being a mode the user cannot leave without clearing the line.
  const [query, setQuery] = useState<string | null>(null);
  const [dismissedQuery, setDismissedQuery] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  // The menu belongs to the focused composer. Without this it kept floating
  // over the thread after a click elsewhere, with no way back to it but typing.
  const [focused, setFocused] = useState(false);

  const entries = useMemo(
    () => (query === null ? [] : commands.filter((entry) => entry.command.startsWith(query))),
    [commands, query],
  );
  const safeIndex = entries.length === 0 ? 0 : Math.min(activeIndex, entries.length - 1);
  // Two distinct states. The panel is shown whenever the trigger is live — with
  // nothing to offer it says so rather than vanishing under a placeholder that
  // just invited the user to type `/`. It only *claims keys* when it has
  // entries, so `/nosuchcommand` + Enter still reaches the ordinary send.
  const panelOpen = focused && query !== null && query !== dismissedQuery;
  const hasEntries = entries.length > 0;

  const entriesRef = useRef(entries);
  entriesRef.current = entries;
  const safeIndexRef = useRef(safeIndex);
  safeIndexRef.current = safeIndex;
  const panelOpenRef = useRef(panelOpen);
  panelOpenRef.current = panelOpen;
  const queryRef = useRef(query);
  queryRef.current = query;

  const onQueryChange = useCallback((next: string | null) => {
    setQuery(next);
    // Re-filtering re-focuses the best match, so the focus is never left on
    // something that is no longer on screen.
    setActiveIndex(0);
    // A closed trigger clears the dismissal, or retyping the same query after
    // an Esc would find the menu still shut.
    if (next === null) setDismissedQuery(null);
  }, []);

  // Prefetch keeps the detail fetch off the critical path when the command
  // runs; the set makes moving the focus back over an entry a no-op.
  const prefetchedRef = useRef(new Set<string>());
  const focusedPromptId = panelOpen && hasEntries ? (entries[safeIndex]?.promptId ?? null) : null;
  useEffect(() => {
    if (!focusedPromptId) return;
    const key = `${teamId}:${focusedPromptId}`;
    if (prefetchedRef.current.has(key)) return;
    prefetchedRef.current.add(key);
    void fetchPrompt({ teamId, promptId: focusedPromptId }, true);
  }, [focusedPromptId, fetchPrompt, teamId]);

  const complete = useCallback((entry: CommandMenuEntry) => {
    // The trailing space breaks the query, which closes the menu on its own.
    paramsRef.current.setInput(`/${entry.command} `);
  }, []);

  const run = useCallback(
    async (entry: CommandMenuEntry, appended: string) => {
      try {
        const detail = await fetchPrompt({ teamId, promptId: entry.promptId }, true).unwrap();
        const text = detail.text?.trim();
        if (!text) throw new Error("empty prompt");
        paramsRef.current.onRunCommand({
          text: appended ? `${text}\n\n${appended}` : text,
          command: {
            command: entry.command,
            ...(appended ? { appended_text: appended } : {}),
            prompt_id: entry.promptId,
            prompt_name: entry.name,
          },
        });
      } catch {
        paramsRef.current.onResolveError();
      }
    },
    [fetchPrompt, teamId],
  );

  const submit = useCallback(() => {
    const parsed = parseCommandLine(paramsRef.current.input);
    const entry = parsed ? commandsRef.current.find((candidate) => candidate.command === parsed.command) : null;
    // No command, or a token no prompt holds: the user may genuinely have
    // meant to write it, so it goes out as typed.
    if (!parsed || !entry) {
      paramsRef.current.onSend();
      return;
    }
    void run(entry, parsed.appended);
  }, [run]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>): boolean => {
      if (!panelOpenRef.current) return false;
      // Esc closes the panel whether or not it holds anything — an empty one
      // the user cannot dismiss would be worse than no panel at all.
      if (event.key === "Escape") {
        event.preventDefault();
        // Always available: while the menu is open `Tab` completes instead of
        // moving focus, so this is the only way back to ordinary tabbing.
        setDismissedQuery(queryRef.current);
        return true;
      }
      const count = entriesRef.current.length;
      if (count === 0) return false;
      const focusedEntry = entriesRef.current[safeIndexRef.current];
      switch (event.key) {
        case "ArrowDown":
          event.preventDefault();
          setActiveIndex((index) => (Math.min(index, count - 1) + 1) % count);
          return true;
        case "ArrowUp":
          event.preventDefault();
          setActiveIndex((index) => (Math.min(index, count - 1) + count - 1) % count);
          return true;
        case "Tab":
          event.preventDefault();
          complete(focusedEntry);
          return true;
        case "Enter":
          if (event.shiftKey || event.nativeEvent.isComposing) return false;
          event.preventDefault();
          // The focused entry, not the typed token: the menu is open on a
          // partial query, which would resolve to nothing on its own.
          void run(focusedEntry, "");
          return true;
        default:
          return false;
      }
    },
    [complete, run],
  );

  const onActivate = useCallback(
    (index: number) => {
      const entry = entriesRef.current[index];
      if (entry) complete(entry);
    },
    [complete],
  );

  const onFocusEntry = useCallback((index: number) => setActiveIndex(index), []);
  const optionId = useCallback((index: number) => `${optionIdPrefix}-${index}`, [optionIdPrefix]);

  const onFocusChange = useCallback((next: boolean) => setFocused(next), []);

  const trigger: CommandTriggerBinding = {
    onQueryChange,
    onKeyDown,
    onFocusChange,
    listboxId,
    open: panelOpen,
    activeDescendantId: panelOpen && hasEntries ? optionId(safeIndex) : null,
  };

  const teamHasCommands = commands.length > 0;
  const menu = useMemo<ComposerCommandsMenu | null>(
    () =>
      panelOpen
        ? { id: listboxId, entries, activeIndex: safeIndex, teamHasCommands, optionId, onActivate, onFocusEntry }
        : null,
    [panelOpen, listboxId, entries, safeIndex, teamHasCommands, optionId, onActivate, onFocusEntry],
  );

  return { trigger, menu, submit };
}
