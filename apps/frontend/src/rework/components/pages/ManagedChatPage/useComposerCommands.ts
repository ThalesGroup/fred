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

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type { CommandMenuEntry } from "@shared/molecules/CommandMenu/CommandMenu";
import {
  type CommandChoice,
  type CommandKeyEvent,
  type CommandTriggerBinding,
} from "@shared/molecules/RichInputField/RichInputField";
import {
  type PromptCommandSummary,
  useGetAgentInstanceSkillsQuery,
  useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery,
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { findSkillInvocations } from "@rework/utils/skillInvocation";
import type { SkillInvocation, TurnCommand } from "../../../../slices/runtime/runtimeOpenApi";

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

function completionRange(input: string, range: { start: number; end: number }) {
  return { ...range, end: range.end + (/^[a-z0-9_-]+/.exec(input.slice(range.end))?.[0].length ?? 0) };
}

function promptEntries(prompts: PromptCommandSummary[], teamId: string, source?: "personal" | "team") {
  return prompts
    .filter((prompt) => prompt.command !== "skill")
    .map((prompt) => ({
      kind: "prompt" as const,
      promptId: prompt.prompt_id,
      promptTeamId: teamId,
      source,
      command: prompt.command,
      name: prompt.name,
      description: prompt.description,
      emoji: prompt.emoji,
    }));
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
  agentInstanceId?: string;
  /** Enables personal prompt commands only for a resolved ReAct template. */
  includePersonalCommands?: boolean;
  personalTeamId?: string;
  onRunSkill?: (run: { text: string; skills: SkillInvocation[] }) => void;
  onSkillError?: (reason: "usage" | "unavailable") => void;
  input: string;
  setInput: (value: string) => void;
  /** Sends the assembled prompt text with the descriptor on the turn's context. */
  onRunCommand: (run: { text: string; command: TurnCommand; skills?: SkillInvocation[] }) => void;
  /** Ordinary submit — no command, or a token no prompt holds. */
  onSend: () => void;
  /** The prompt behind a command could not be read. */
  onResolveError: () => void;
}): {
  trigger: CommandTriggerBinding;
  menu: ComposerCommandsMenu | null;
  submit: () => void;
  selectedSkills: { name: string; from: number; to: number }[];
  selectedPrompt:
    | (Omit<Extract<CommandMenuEntry, { kind: "prompt" }>, "source"> & {
        source?: "personal" | "team";
        from: number;
        to: number;
      })
    | null;
  selectedSkillArgumentHint: string | null;
  skillDescriptions: ReadonlyMap<string, string>;
  composerValue: string;
  onComposerChange: (value: string) => void;
} {
  const { teamId, agentInstanceId, includePersonalCommands = false, personalTeamId } = params;
  const scopeKey = JSON.stringify([teamId, agentInstanceId, includePersonalCommands, personalTeamId]);
  const scopeRef = useRef({ key: scopeKey, version: 0 });
  if (scopeRef.current.key !== scopeKey) scopeRef.current = { key: scopeKey, version: scopeRef.current.version + 1 };
  type Choice = CommandChoice;
  const [choices, setChoices] = useState<Choice[]>([]);
  const choicesRef = useRef(choices);
  choicesRef.current = choices;
  const draftReplaceRef = useRef(false);
  const restoredChoicesRef = useRef<readonly Choice[] | null>(null);
  const { currentData: catalog } = useGetAgentInstanceSkillsQuery(
    { teamId, agentInstanceId: agentInstanceId ?? "" },
    { skip: !teamId || !agentInstanceId, refetchOnMountOrArgChange: true },
  );
  const skills = catalog?.supported ? (catalog.skills ?? []) : [];
  const skillsRef = useRef(skills);
  skillsRef.current = skills;
  const skillNames = useMemo(() => skills.map((skill) => skill.name), [skills]);
  const skillDescriptions = useMemo(
    () => new Map((catalog?.supported ? (catalog.skills ?? []) : []).map((skill) => [skill.name, skill.description])),
    [catalog],
  );
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
  const { currentData: prompts } = useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery(
    { teamId },
    { skip: !teamId },
  );
  const teamCommandsReadyRef = useRef(false);
  teamCommandsReadyRef.current = prompts !== undefined;
  const { currentData: personalPrompts } = useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery(
    { teamId: personalTeamId ?? "" },
    { skip: !includePersonalCommands || !personalTeamId || personalTeamId === teamId },
  );
  const [fetchPrompt] = useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery();

  const commands = useMemo(
    () => [
      ...promptEntries(
        prompts ?? [],
        teamId,
        includePersonalCommands ? (personalTeamId === teamId ? "personal" : "team") : undefined,
      ),
      ...(includePersonalCommands && personalTeamId && personalTeamId !== teamId
        ? promptEntries(personalPrompts ?? [], personalTeamId, "personal")
        : []),
    ],
    [prompts, personalPrompts, teamId, personalTeamId, includePersonalCommands],
  );
  const commandsRef = useRef(commands);
  commandsRef.current = commands;
  const matchedChoices = choices.filter((choice) => params.input.slice(choice.from, choice.to) === `/${choice.name}`);
  const promptChoice = matchedChoices.find((choice) => choice.kind === "prompt");
  const currentPromptChoice = promptChoice?.scope === scopeRef.current.version ? promptChoice : undefined;
  const allSkillRanges = findSkillInvocations(params.input, skillNames);
  const selectedSkills = allSkillRanges.filter(
    (token) =>
      token.from !== promptChoice?.from &&
      (token.to < params.input.length ||
        matchedChoices.some((choice) => choice.kind === "skill" && choice.from === token.from)),
  );
  const promptRange =
    promptChoice ??
    findSkillInvocations(
      params.input,
      commands.map((entry) => entry.command),
    ).find((token) => !selectedSkills.some((skill) => skill.from === token.from));
  const promptEntry =
    (!promptChoice || currentPromptChoice) && promptRange
      ? commands.find(
          (entry) =>
            entry.command === promptRange.name &&
            (!currentPromptChoice ||
              currentPromptChoice.kind !== "prompt" ||
              (entry.promptId === currentPromptChoice.promptId &&
                entry.promptTeamId === currentPromptChoice.promptTeamId)),
        )
      : undefined;
  const selectedPrompt =
    promptEntry &&
    promptRange &&
    (promptRange.to < params.input.length || currentPromptChoice) &&
    (promptEntry.promptTeamId === teamId || currentPromptChoice || prompts !== undefined)
      ? { ...promptEntry, from: promptRange.from, to: promptRange.to }
      : null;
  const selectedSummary = skills.find((skill) => skill.name === selectedSkills[0]?.name);

  const mapChoices = useCallback((value: string) => {
    const old = paramsRef.current.input;
    let from = 0;
    while (from < old.length && from < value.length && old[from] === value[from]) from++;
    let tail = 0;
    while (
      tail < old.length - from &&
      tail < value.length - from &&
      old[old.length - tail - 1] === value[value.length - tail - 1]
    )
      tail++;
    const end = old.length - tail;
    const delta = value.length - old.length;
    const replacing = draftReplaceRef.current;
    draftReplaceRef.current = false;
    const previous = replacing ? [] : [...choicesRef.current];
    for (const token of findSkillInvocations(
      old,
      skillsRef.current.map((skill) => skill.name),
      true,
    ))
      if (!replacing && !previous.some((choice) => choice.from === token.from))
        previous.push({ ...token, kind: "skill", scope: scopeRef.current.version });
    const mappedChoices = previous.flatMap((choice) => {
      const mapped =
        choice.to <= from
          ? choice
          : choice.from >= end
            ? { ...choice, from: choice.from + delta, to: choice.to + delta }
            : null;
      return mapped && value.slice(mapped.from, mapped.to) === `/${mapped.name}` ? [mapped] : [];
    });
    for (const token of findSkillInvocations(
      value,
      skillsRef.current.map((skill) => skill.name),
      true,
    ))
      if (!mappedChoices.some((choice) => choice.from === token.from))
        mappedChoices.push({ ...token, kind: "skill", scope: scopeRef.current.version });
    return mappedChoices;
  }, []);
  const onComposerChange = useCallback(
    (value: string) => {
      const restored = restoredChoicesRef.current;
      restoredChoicesRef.current = null;
      setChoices(restored ? [...restored] : mapChoices(value));
      paramsRef.current.setInput(value);
    },
    [mapChoices],
  );
  const skillEntries = useMemo<CommandMenuEntry[]>(
    () =>
      skills.map((skill) => ({
        promptId: "platform:skill:" + skill.name,
        command: skill.name,
        name: skill.name,
        description: skill.description,
        argumentHint: skill.argument_hint,
        kind: "skill",
        source: includePersonalCommands ? "platform" : undefined,
      })),
    [skills, includePersonalCommands],
  );

  // `null` while the composer holds no command query. `dismissedQuery` is the
  // query `Esc` closed the menu on: typing further reopens it, which keeps Esc
  // from being a mode the user cannot leave without clearing the line.
  const [query, setQuery] = useState<string | null>(null);
  const [commandRange, setCommandRange] = useState<{ start: number; end: number }>();
  const commandRangeRef = useRef(commandRange);
  commandRangeRef.current = commandRange;
  const [selectionRequest, setSelectionRequest] = useState<{ id: number; caret: number }>();
  const [dismissedQuery, setDismissedQuery] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  // The menu belongs to the focused composer. Without this it kept floating
  // over the thread after a click elsewhere, with no way back to it but typing.
  const [focused, setFocused] = useState(false);

  const entries = useMemo(
    () =>
      query === null
        ? []
        : query === "skill" || query.startsWith("skill ")
          ? skillEntries.filter((entry) => entry.name.startsWith(query.startsWith("skill ") ? query.slice(6) : ""))
          : [
              ...commands.filter(
                (entry) =>
                  entry.command.startsWith(query) && (!promptChoice || commandRange?.start === promptChoice.from),
              ),
              ...skillEntries.filter((entry) => entry.name.startsWith(query)),
            ],
    [commands, skillEntries, query, commandRange, promptChoice],
  );
  const safeIndex = entries.length === 0 ? 0 : Math.min(activeIndex, entries.length - 1);
  // Two distinct states. The panel is shown whenever the trigger is live — with
  // nothing to offer it says so rather than vanishing under a placeholder that
  // just invited the user to type `/`. It only *claims keys* when it has
  // entries, so `/nosuchcommand` + Enter still reaches the ordinary send.
  const panelOpen =
    focused &&
    query !== null &&
    query !== dismissedQuery &&
    !selectedSkills.some((token) => token.from === commandRange?.start) &&
    !(promptEntry && promptRange && promptRange.to < params.input.length && promptRange.from === commandRange?.start);
  const hasEntries = entries.length > 0;

  const entriesRef = useRef(entries);
  entriesRef.current = entries;
  const safeIndexRef = useRef(safeIndex);
  safeIndexRef.current = safeIndex;
  const panelOpenRef = useRef(panelOpen);
  panelOpenRef.current = panelOpen;
  const queryRef = useRef(query);
  queryRef.current = query;

  const onQueryChange = useCallback((next: string | null, range?: { start: number; end: number }) => {
    setQuery(next);
    setCommandRange(next === null ? undefined : range);
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
  const focusedEntry = panelOpen && hasEntries ? entries[safeIndex] : undefined;
  const focusedPromptId = focusedEntry?.kind === "prompt" ? focusedEntry.promptId : null;
  const focusedPromptTeamId = focusedEntry?.kind === "prompt" ? focusedEntry.promptTeamId : null;
  useEffect(() => {
    if (!focusedPromptId || !focusedPromptTeamId) return;
    const key = `${focusedPromptTeamId}:${focusedPromptId}`;
    if (prefetchedRef.current.has(key)) return;
    prefetchedRef.current.add(key);
    void fetchPrompt({ teamId: focusedPromptTeamId, promptId: focusedPromptId }, true);
  }, [focusedPromptId, focusedPromptTeamId, fetchPrompt]);

  const complete = useCallback(
    (entry: CommandMenuEntry) => {
      const activeRange = commandRangeRef.current;
      if (!activeRange) return;
      const input = paramsRef.current.input;
      const range = completionRange(input, activeRange);
      const name = entry.kind === "skill" ? entry.name : entry.command;
      const token = `/${name}`;
      const trailing = input.slice(range.end);
      const separator = /^\s/.test(trailing) ? "" : " ";
      const value = input.slice(0, range.start) + token + separator + trailing;
      const preserved = mapChoices(value).filter((choice) => choice.from !== range.start);
      const choice: Choice = {
        name,
        from: range.start,
        to: range.start + token.length,
        scope: scopeRef.current.version,
        ...(entry.kind === "prompt"
          ? { kind: "prompt", promptId: entry.promptId, promptTeamId: entry.promptTeamId }
          : { kind: "skill" }),
      };
      setChoices([...preserved, choice]);
      paramsRef.current.setInput(value);
      setSelectionRequest((previous) => ({
        id: (previous?.id ?? 0) + 1,
        caret: range.start + token.length + (separator.length || (/^\s/.test(trailing) ? 1 : 0)),
      }));
    },
    [mapChoices],
  );

  const run = useCallback(
    async (entry: CommandMenuEntry, draft: string, range: { from: number; to: number }) => {
      if (entry.kind === "skill") {
        complete(entry);
        return;
      }
      const scopeAtSubmit = scopeRef.current.version;
      const active = choicesRef.current.filter(
        (choice) => paramsRef.current.input.slice(choice.from, choice.to) === `/${choice.name}`,
      );
      if (active.some((choice) => choice.scope !== scopeAtSubmit)) {
        paramsRef.current.onResolveError();
        return;
      }
      if (
        active.some(
          (choice) => choice.kind === "skill" && !skillsRef.current.some((skill) => skill.name === choice.name),
        )
      ) {
        paramsRef.current.onSkillError?.("unavailable");
        return;
      }
      const selections = [
        ...new Set(
          findSkillInvocations(
            draft,
            skillsRef.current.map((skill) => skill.name),
          )
            .filter((token) => token.from !== range.from)
            .map((token) => token.name),
        ),
      ].map((name) => ({ name }));
      try {
        const detail = await fetchPrompt({ teamId: entry.promptTeamId, promptId: entry.promptId }, true).unwrap();
        if (scopeRef.current.version !== scopeAtSubmit) return;
        const text = detail.text?.trim();
        if (!text) throw new Error("empty prompt");
        const before = draft.slice(0, range.from).trim();
        const after = draft.slice(range.to).trim();
        const appended = [before, after].filter(Boolean).join("\n\n");
        paramsRef.current.onRunCommand({
          text: [before, text, after].filter(Boolean).join("\n\n"),
          command: {
            command: entry.command,
            ...(appended ? { appended_text: appended } : {}),
            prompt_id: entry.promptId,
            prompt_name: entry.name,
            draft_text: draft,
            draft_command_offset: range.from,
          },
          ...(selections.length ? { skills: selections } : {}),
        });
      } catch {
        if (scopeRef.current.version === scopeAtSubmit) paramsRef.current.onResolveError();
      }
    },
    [fetchPrompt, complete],
  );

  const submit = useCallback(() => {
    let input = paramsRef.current.input;
    let choiceOffset = 0;
    const parsed = parseCommandLine(input);
    if (parsed?.command === "skill") {
      const match = /^(\S+)(?:\s+([\s\S]*))?$/.exec(parsed.appended);
      if (!match) {
        paramsRef.current.onSkillError?.("usage");
        return;
      }
      if (!skillsRef.current.some((skill) => skill.name === match[1])) {
        paramsRef.current.onSkillError?.("unavailable");
        return;
      }
      const originalLength = input.trimEnd().length;
      input = `/${match[1]}${match[2] ? " " + match[2] : ""}`;
      choiceOffset = input.length - originalLength;
    }
    // Legacy prefix normalization must preserve the chosen prompt's owner.
    const active = choicesRef.current
      .map((choice) => ({ ...choice, from: choice.from + choiceOffset, to: choice.to + choiceOffset }))
      .filter((choice) => input.slice(choice.from, choice.to) === `/${choice.name}`);
    const explicitPrompt = active.find((choice) => choice.kind === "prompt");
    if (active.some((choice) => choice.scope !== scopeRef.current.version)) {
      if (explicitPrompt) paramsRef.current.onResolveError();
      else paramsRef.current.onSkillError?.("unavailable");
      return;
    }
    if (
      active.some((choice) => choice.kind === "skill" && !skillsRef.current.some((skill) => skill.name === choice.name))
    ) {
      paramsRef.current.onSkillError?.("unavailable");
      return;
    }
    const skillRanges = findSkillInvocations(
      input,
      skillsRef.current.map((skill) => skill.name),
    );
    const promptRanges = findSkillInvocations(
      input,
      commandsRef.current.map((entry) => entry.command),
    );
    const range =
      explicitPrompt ??
      promptRanges.find(
        (token) =>
          !skillRanges.some(
            (skill) =>
              skill.from === token.from &&
              (skill.to < input.length ||
                active.some((choice) => choice.kind === "skill" && choice.from === skill.from)),
          ),
      );
    const entry = range
      ? commandsRef.current.find(
          (candidate) =>
            candidate.command === range.name &&
            (!explicitPrompt ||
              explicitPrompt.kind !== "prompt" ||
              (candidate.promptId === explicitPrompt.promptId &&
                candidate.promptTeamId === explicitPrompt.promptTeamId)),
        )
      : undefined;
    if (explicitPrompt && !entry) {
      paramsRef.current.onResolveError();
      return;
    }
    if (entry && range) {
      if (!explicitPrompt && entry.promptTeamId !== paramsRef.current.teamId && !teamCommandsReadyRef.current) {
        paramsRef.current.onResolveError();
        return;
      }
      void run(entry, input, range);
      return;
    }
    if (skillRanges.length) {
      if (!paramsRef.current.onRunSkill) {
        paramsRef.current.onSkillError?.("unavailable");
        return;
      }
      paramsRef.current.onRunSkill({
        text: input,
        skills: [...new Set(skillRanges.map((token) => token.name))].map((name) => ({ name })),
      });
      return;
    }
    paramsRef.current.onSend();
  }, [run]);

  const onKeyDown = useCallback(
    (event: CommandKeyEvent): boolean => {
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
          // Preserve the highlighted row's identity, including homonyms.
          // Skill completion never sends; the next Enter submits the draft.
          if (focusedEntry.kind === "skill") complete(focusedEntry);
          else {
            const range = commandRangeRef.current;
            if (range) {
              const input = paramsRef.current.input;
              const replacement = completionRange(input, range);
              const draft =
                input.slice(0, replacement.start) + `/${focusedEntry.command}` + input.slice(replacement.end);
              void run(focusedEntry, draft, { from: range.start, to: range.start + focusedEntry.command.length + 1 });
            }
          }
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
  const onDraftReplace = useCallback(() => {
    draftReplaceRef.current = true;
    choicesRef.current = [];
    setChoices([]);
  }, []);

  const onChoicesRestore = useCallback((restored: readonly Choice[]) => {
    restoredChoicesRef.current = restored;
    draftReplaceRef.current = false;
  }, []);

  const trigger: CommandTriggerBinding = {
    choices,
    onChoicesRestore,
    inlineCommandNames: [...skillNames, ...commands.map((entry) => entry.command)],
    selectionRequest,
    onDraftReplace,
    onQueryChange,
    onKeyDown,
    onFocusChange,
    listboxId,
    open: panelOpen,
    activeDescendantId: panelOpen && hasEntries ? optionId(safeIndex) : null,
  };

  const teamHasCommands = commands.length > 0 || skillEntries.length > 0;
  const menu = useMemo<ComposerCommandsMenu | null>(
    () =>
      panelOpen
        ? { id: listboxId, entries, activeIndex: safeIndex, teamHasCommands, optionId, onActivate, onFocusEntry }
        : null,
    [panelOpen, listboxId, entries, safeIndex, teamHasCommands, optionId, onActivate, onFocusEntry],
  );

  return {
    trigger,
    menu,
    submit,
    selectedSkills,
    selectedPrompt,
    selectedSkillArgumentHint: selectedSkills.length === 1 ? selectedSummary?.argument_hint?.trim() || null : null,
    skillDescriptions,
    composerValue: params.input,
    onComposerChange,
  };
}
