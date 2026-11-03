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

import type { ThreadMessage } from "@rework/types/thread";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type { CommandMenuEmptyReason, CommandMenuEntry } from "@shared/molecules/CommandMenu/CommandMenu";
import {
  commandQueryOf,
  type CommandChoice,
  type CommandKeyEvent,
  type CommandTriggerBinding,
  type DraftEdit,
} from "@shared/molecules/RichInputField/RichInputField";
import {
  type PromptCommandSummary,
  useGetAgentInstanceSkillsQuery,
  useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery,
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  assemblePromptTurn,
  findCommandWords,
  findSkillInvocations,
  isCommandTokenAt,
  MAX_TURN_PROMPTS,
  usablePromptList,
} from "@rework/utils/skillInvocation";
import type { SkillInvocation, TurnCommand } from "../../../../slices/runtime/runtimeOpenApi";

/**
 * The composer's command trigger: the menu `/` opens, and the resolution of a
 * command on submit.
 *
 * The menu only ever inserts a command: `Tab`, `Enter` and a click all complete
 * the row and send nothing. Resolution happens on submit, with the menu closed.
 */

/** A composer line that starts with a command, split from its trailing text. */
export function parseCommandLine(value: string): { command: string; appended: string } | null {
  const match = /^\/(\S+)(?:\s+([\s\S]*))?$/.exec(value.trim());
  return match ? { command: match[1], appended: (match[2] ?? "").trim() } : null;
}

// The rest of the name under the caret, in any case like the menu's filter.
function completionRange(input: string, range: { start: number; end: number }) {
  return { ...range, end: range.end + (/^[a-z0-9_-]+/i.exec(input.slice(range.end))?.[0].length ?? 0) };
}

/** Entries whose name contains the query; names starting with it come first. */
function matchByName<T extends { command: string }>(entries: readonly T[], query: string): T[] {
  const needle = query.toLowerCase();
  const hits = entries.filter((entry) => entry.command.toLowerCase().includes(needle));
  const starts = (entry: T) => entry.command.toLowerCase().startsWith(needle);
  return [...hits.filter(starts), ...hits.filter((entry) => !starts(entry))];
}

/** The span one edit replaced, guessed from the two texts. Only for a change
 *  the editor did not report (recall, voice, a programmatic insert): where the
 *  removed text repeats, the guess can name the wrong occurrence. */
function editBetween(old: string, value: string): DraftEdit[] {
  let from = 0;
  while (from < old.length && from < value.length && old[from] === value[from]) from++;
  let tail = 0;
  while (
    tail < old.length - from &&
    tail < value.length - from &&
    old[old.length - tail - 1] === value[value.length - tail - 1]
  )
    tail++;
  return [{ from, to: old.length - tail, insert: value.length - tail - from }];
}

/** A range after the edits: unmoved before them, shifted after them, and
 *  gone (`null`) when an edit reaches into it. */
function mapRange<T extends { from: number; to: number }>(range: T, edits: readonly DraftEdit[]): T | null {
  let shift = 0;
  for (const edit of edits) {
    if (edit.to <= range.from) shift += edit.insert - (edit.to - edit.from);
    else if (edit.from < range.to) return null;
  }
  return shift ? { ...range, from: range.from + shift, to: range.to + shift } : range;
}

/** A deleted or forbidden prompt will not come back by retrying. */
function isGone(error: unknown): boolean {
  const status = (error as { status?: unknown } | null)?.status;
  return status === 403 || status === 404;
}

function promptEntries(prompts: PromptCommandSummary[], teamId: string, source: "personal" | "team") {
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

/** The prompt commands of a conversation: the team's, then the personal ones. */
function promptCommands(
  team: PromptCommandSummary[] | undefined,
  personal: PromptCommandSummary[] | undefined,
  teamId: string,
  personalTeamId: string | undefined,
) {
  return [
    ...promptEntries(team ?? [], teamId, personalTeamId === teamId ? "personal" : "team"),
    ...(personalTeamId && personalTeamId !== teamId ? promptEntries(personal ?? [], personalTeamId, "personal") : []),
  ];
}

/** What a submit resolves the names of a draft against. */
interface Catalogs {
  commands: ReturnType<typeof promptCommands>;
  skillNames: readonly string[];
  /** The team's catalog has answered, so a personal fallback is safe. */
  teamReady: boolean;
  /** Every prompt catalog has answered: a missing prompt is known gone. */
  promptsReady: boolean;
}

/** The answer a catalog gives once asked again; nothing when it fails. */
function answerOf<T>(source: { missing: boolean; refetch: () => PromiseLike<{ data?: T }> }): Promise<T | undefined> {
  if (!source.missing) return Promise.resolve(undefined);
  return Promise.resolve(source.refetch()).then(
    (result) => result.data,
    () => undefined,
  );
}

export interface ComposerCommandsMenu {
  id: string;
  entries: CommandMenuEntry[];
  activeIndex: number;
  /** Why `entries` is empty: catalogs still loading, one that could not be
   *  read, no command anywhere, or a query that matches none of them. */
  empty: CommandMenuEmptyReason;
  optionId: (index: number) => string;
  onActivate: (index: number) => void;
  onFocusEntry: (index: number) => void;
}

export function useComposerCommands(params: {
  teamId: string;
  agentInstanceId?: string;
  /** The caller's personal space, whose prompt commands join the team's. */
  personalTeamId?: string;
  onRunSkill?: (run: { text: string; skills: SkillInvocation[] }) => void;
  onSkillError?: (reason: "usage" | "unavailable") => void;
  input: string;
  setInput: (value: string) => void;
  /** Sends the assembled prompt text with the descriptor on the turn's context. */
  onRunCommand: (run: { text: string; command: TurnCommand; skills?: SkillInvocation[] }) => void;
  /** Ordinary submit — no command, or a token no prompt holds. */
  onSend: () => void;
  /** The message is held back because of `command`: `stale` when its prompt is
   *  gone, renamed or from another agent or team; `unreadable` when the read
   *  failed for now; `tooMany` when it is the first one past the limit. */
  onResolveError: (reason: "stale" | "unreadable" | "tooMany", command: string) => void;
}): {
  trigger: CommandTriggerBinding;
  menu: ComposerCommandsMenu | null;
  submit: () => void;
  dismiss: (line: string, message?: ThreadMessage) => void;
  selectedSkills: { name: string; from: number; to: number }[];
  /** Every prompt command shown as a token, in the order of the line. */
  selectedPrompts: (Omit<Extract<CommandMenuEntry, { kind: "prompt" }>, "source"> & {
    source: "personal" | "team";
    from: number;
    to: number;
  })[];
  selectedSkillArgumentHint: string | null;
  skillDescriptions: ReadonlyMap<string, string>;
  composerValue: string;
  onComposerChange: (value: string) => void;
} {
  const { teamId, agentInstanceId, personalTeamId } = params;
  const scopeKey = JSON.stringify([teamId, agentInstanceId, personalTeamId]);
  const scopeRef = useRef({ key: scopeKey, version: 0 });
  if (scopeRef.current.key !== scopeKey) scopeRef.current = { key: scopeKey, version: scopeRef.current.version + 1 };
  type Choice = CommandChoice;
  const [choices, setChoices] = useState<Choice[]>([]);
  const choicesRef = useRef(choices);
  choicesRef.current = choices;
  const draftReplaceRef = useRef(false);
  // The exact spans of the change the editor is reporting, and the last change
  // applied: both replace a guess from the two texts wherever they are known.
  const pendingEditsRef = useRef<readonly DraftEdit[] | null>(null);
  const lastEditRef = useRef<{ old: string; value: string; edits: readonly DraftEdit[] } | null>(null);
  const restoredChoicesRef = useRef<readonly Choice[] | null>(null);
  const skillsQueried = Boolean(teamId && agentInstanceId);
  const {
    currentData: catalog,
    isFetching: skillsFetching,
    isError: skillsFailed,
    refetch: refetchSkills,
  } = useGetAgentInstanceSkillsQuery(
    { teamId, agentInstanceId: agentInstanceId ?? "" },
    { skip: !skillsQueried, refetchOnMountOrArgChange: true },
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
  const {
    currentData: prompts,
    isFetching: teamCommandsFetching,
    isError: teamCommandsFailed,
    refetch: refetchTeamCommands,
  } = useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery({ teamId }, { skip: !teamId });
  const teamCommandsReadyRef = useRef(false);
  teamCommandsReadyRef.current = prompts !== undefined;
  const personalQueried = Boolean(personalTeamId) && personalTeamId !== teamId;
  const {
    currentData: personalPrompts,
    isFetching: personalCommandsFetching,
    isError: personalCommandsFailed,
    refetch: refetchPersonalCommands,
  } = useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery(
    { teamId: personalTeamId ?? "" },
    { skip: !personalQueried },
  );
  // A prompt missing from a catalog that has not answered is not known gone.
  const promptCatalogsReadyRef = useRef(false);
  promptCatalogsReadyRef.current = prompts !== undefined && (!personalQueried || personalPrompts !== undefined);
  const catalogsLoading =
    (teamCommandsFetching && prompts === undefined) ||
    (personalCommandsFetching && personalPrompts === undefined) ||
    (skillsFetching && catalog === undefined);
  // A catalog is `missing` until it has answered once: still loading, or failed.
  const catalogSources = {
    team: {
      data: prompts,
      missing: Boolean(teamId) && prompts === undefined,
      failed: teamCommandsFailed,
      refetch: refetchTeamCommands,
    },
    personal: {
      data: personalPrompts,
      missing: personalQueried && personalPrompts === undefined,
      failed: personalCommandsFailed,
      refetch: refetchPersonalCommands,
    },
    skills: {
      data: catalog,
      missing: skillsQueried && catalog === undefined,
      failed: skillsFailed,
      refetch: refetchSkills,
    },
  };
  const catalogSourcesRef = useRef(catalogSources);
  catalogSourcesRef.current = catalogSources;
  const catalogsFailed =
    !catalogsLoading && Object.values(catalogSources).some((source) => source.missing && source.failed);
  const [fetchPrompt] = useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery();

  const commands = useMemo(
    () => promptCommands(prompts, personalPrompts, teamId, personalTeamId),
    [prompts, personalPrompts, teamId, personalTeamId],
  );
  const commandsRef = useRef(commands);
  commandsRef.current = commands;
  const matchedChoices = choices.filter((choice) => isCommandTokenAt(params.input, choice.from, choice.name));
  const promptChoices = matchedChoices.flatMap((choice) => (choice.kind === "prompt" ? [{ ...choice, choice }] : []));
  const allSkillRanges = findSkillInvocations(params.input, skillNames);
  // A name picked as a prompt is never also a skill, wherever it sits.
  const selectedSkills = allSkillRanges.filter(
    (token) =>
      !promptChoices.some((choice) => choice.from === token.from) &&
      (token.to < params.input.length ||
        matchedChoices.some((choice) => choice.kind === "skill" && choice.from === token.from)),
  );
  // A typed prompt has no choice behind it, so once shown it is remembered:
  // deleting the text after it must not turn the token back into raw text.
  const shownPromptsRef = useRef<{ input: string; tokens: { from: number; to: number; name: string }[] }>({
    input: params.input,
    tokens: [],
  });
  const remembered = shownPromptsRef.current;
  const lastEdit = lastEditRef.current;
  const shownEdits =
    lastEdit?.old === remembered.input && lastEdit.value === params.input
      ? lastEdit.edits
      : editBetween(remembered.input, params.input);
  const shownBefore = remembered.tokens.flatMap((token) => mapRange(token, shownEdits) ?? []);
  const selectedPrompts = [
    ...promptChoices,
    ...findSkillInvocations(
      params.input,
      commands.map((entry) => entry.command),
    )
      .filter(
        (token) =>
          !promptChoices.some((choice) => choice.from === token.from) &&
          !selectedSkills.some((skill) => skill.from === token.from),
      )
      .map((token) => ({ ...token, choice: undefined })),
  ]
    .sort((a, b) => a.from - b.from)
    .flatMap((range) => {
      const { choice } = range;
      // A choice made for another agent or team is not shown as a token.
      if (choice && choice.scope !== scopeRef.current.version) return [];
      const entry = commands.find(
        (candidate) =>
          candidate.command === range.name &&
          (!choice ||
            (candidate.promptId === choice.promptId &&
              (!choice.promptTeamId || candidate.promptTeamId === choice.promptTeamId))),
      );
      const shown =
        entry &&
        (range.to < params.input.length ||
          choice ||
          shownBefore.some((token) => token.from === range.from && token.name === range.name)) &&
        (entry.promptTeamId === teamId || choice || prompts !== undefined);
      return shown ? [{ ...entry, from: range.from, to: range.to }] : [];
    });
  // Committed after the render, so a render React discards remembers nothing.
  useEffect(() => {
    shownPromptsRef.current = {
      input: params.input,
      tokens: selectedPrompts.map((prompt) => ({ from: prompt.from, to: prompt.to, name: prompt.command })),
    };
  });
  const selectedSummary = skills.find((skill) => skill.name === selectedSkills[0]?.name);

  const mapChoices = useCallback((value: string, known?: readonly DraftEdit[] | null) => {
    const old = paramsRef.current.input;
    const edits = known ?? editBetween(old, value);
    lastEditRef.current = { old, value, edits };
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
    // A choice whose token an edit reached into, or glued a character to, is
    // dropped for good: the text left behind is ordinary typed text.
    const mappedChoices = previous.flatMap((choice) => {
      const mapped = mapRange(choice, edits);
      return mapped && isCommandTokenAt(value, mapped.from, mapped.name) ? [mapped] : [];
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
      const edits = pendingEditsRef.current;
      pendingEditsRef.current = null;
      const mapped = mapChoices(value, edits);
      setChoices(restored ? [...restored] : mapped);
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
        kind: "skill",
        source: "platform",
      })),
    [skills],
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

  // Filtered source by source, so the flat list stays grouped like the menu's
  // sections and the arrow keys walk it in display order.
  const entries = useMemo<CommandMenuEntry[]>(
    () =>
      query === null
        ? []
        : query === "skill" || query.startsWith("skill ")
          ? matchByName(skillEntries, query.startsWith("skill ") ? query.slice(6) : "")
          : [
              ...(["team", "personal"] as const).flatMap((source) =>
                matchByName(
                  commands.filter((entry) => entry.source === source),
                  query,
                ),
              ),
              ...matchByName(skillEntries, query),
            ],
    [commands, skillEntries, query],
  );
  const safeIndex = entries.length === 0 ? 0 : Math.min(activeIndex, entries.length - 1);
  // Two distinct states. The panel is shown whenever the trigger is live — with
  // nothing to offer it says so rather than vanishing under a placeholder that
  // just invited the user to type `/`. It only *claims keys* when it has
  // entries, so `/nosuchcommand` + Enter still reaches the ordinary send.
  const panelOpen =
    focused &&
    query !== null &&
    // The query lags the input by one commit; equality would unmount the menu per keystroke.
    commandQueryOf(params.input, commandRange?.end, [...skillNames, ...commands.map((entry) => entry.command)]) !==
      null &&
    query !== dismissedQuery &&
    !selectedSkills.some((token) => token.from === commandRange?.start) &&
    !selectedPrompts.some((prompt) => prompt.from === commandRange?.start);
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
    // Re-filtering puts the focus back on the first row shown, so it is never
    // left on something that is no longer on screen.
    setActiveIndex(0);
    // Any other query clears the dismissal, or deleting then retyping the last
    // character after an Esc (or a recall) would find the menu still shut.
    setDismissedQuery((dismissed) => (dismissed === next ? dismissed : null));
  }, []);

  // Recall preserves selected identities and leaves the menu closed until editing.
  const dismiss = useCallback((line: string, message?: ThreadMessage) => {
    const command = message?.command;
    const listed = message ? usablePromptList(command, message.text) : null;
    // One restored prompt per listed entry; an older turn has its single one.
    const sent = listed
      ? listed.map((entry) => ({
          name: entry.command,
          from: entry.draft_offset,
          to: entry.draft_offset + entry.command.length + 1,
          promptId: entry.prompt_id,
        }))
      : command
        ? findSkillInvocations(line, [command.command])
            .filter((token) => command.draft_command_offset == null || token.from === command.draft_command_offset)
            .slice(0, 1)
            .map((token) => ({ ...token, promptId: command.prompt_id }))
        : [];
    const restored: Choice[] = findSkillInvocations(
      line,
      message?.skillNames ?? (message?.skillName ? [message.skillName] : []),
    )
      .filter((token) => !sent.some((prompt) => prompt.from === token.from))
      .map((token) => ({
        ...token,
        kind: "skill",
        scope: scopeRef.current.version,
      }));
    for (const { promptId, ...range } of sent) {
      if (!promptId || !isCommandTokenAt(line, range.from, range.name)) continue;
      const entry = commandsRef.current.find((entry) => entry.promptId === promptId && entry.command === range.name);
      restored.push({
        ...range,
        kind: "prompt",
        promptId,
        promptTeamId: entry?.promptTeamId ?? "",
        scope: scopeRef.current.version,
      });
    }
    choicesRef.current = restored;
    setChoices(restored);
    setQuery(null);
    setCommandRange(undefined);
    setDismissedQuery(
      commandQueryOf(line, line.length, [
        ...skillsRef.current.map((skill) => skill.name),
        ...commandsRef.current.map((entry) => entry.command),
      ]),
    );
  }, []);

  // Prefetch warms the connection and the preview for the focused row; the
  // set makes moving the focus back over an entry a no-op. Submit reads again.
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
      const preserved = mapChoices(value, [
        { from: range.start, to: range.end, insert: token.length + separator.length },
      ]).filter((choice) => choice.from !== range.start);
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

  type PromptEntry = Extract<CommandMenuEntry, { kind: "prompt" }>;
  const run = useCallback(
    async (
      draft: string,
      targets: { entry: PromptEntry; from: number; to: number }[],
      selections: SkillInvocation[],
    ) => {
      const scopeAtSubmit = scopeRef.current.version;
      // One read per distinct prompt, all started together, and never from the
      // cache: what is sent is the prompt as its library holds it now.
      const reads = new Map<string, Promise<string>>();
      for (const { entry } of targets) {
        const key = `${entry.promptTeamId}:${entry.promptId}`;
        if (reads.has(key)) continue;
        reads.set(
          key,
          fetchPrompt({ teamId: entry.promptTeamId, promptId: entry.promptId }, false)
            .unwrap()
            .then((detail) => {
              const text = detail.text?.trim();
              if (!text) throw new Error("empty prompt");
              return text;
            }),
        );
      }
      const results = await Promise.allSettled(
        targets.map(({ entry }) => reads.get(`${entry.promptTeamId}:${entry.promptId}`)!),
      );
      if (scopeRef.current.version !== scopeAtSubmit) return;
      // All or nothing: the first command of the line that failed is reported.
      const failed = results.findIndex((result) => result.status === "rejected");
      if (failed >= 0) {
        const { reason } = results[failed] as PromiseRejectedResult;
        paramsRef.current.onResolveError(isGone(reason) ? "stale" : "unreadable", targets[failed].entry.command);
        return;
      }
      paramsRef.current.onRunCommand({
        ...assemblePromptTurn(
          draft,
          targets.map(({ entry, from, to }, index) => ({
            command: entry.command,
            promptId: entry.promptId,
            promptName: entry.name,
            from,
            to,
            text: (results[index] as PromiseFulfilledResult<string>).value,
          })),
        ),
        ...(selections.length ? { skills: selections } : {}),
      });
    },
    [fetchPrompt],
  );

  const resolve = useCallback(
    (draft: string, choices: readonly Choice[], catalogs: Catalogs) => {
      let input = draft;
      let choiceOffset = 0;
      const parsed = parseCommandLine(input);
      if (parsed?.command === "skill") {
        const match = /^(\S+)(?:\s+([\s\S]*))?$/.exec(parsed.appended);
        if (!match) {
          paramsRef.current.onSkillError?.("usage");
          return;
        }
        if (!catalogs.skillNames.includes(match[1])) {
          paramsRef.current.onSkillError?.("unavailable");
          return;
        }
        const originalLength = input.trimEnd().length;
        input = `/${match[1]}${match[2] ? " " + match[2] : ""}`;
        choiceOffset = input.length - originalLength;
      }
      // Legacy prefix normalization must preserve the chosen prompt's owner.
      const active = choices
        .map((choice) => ({ ...choice, from: choice.from + choiceOffset, to: choice.to + choiceOffset }))
        .filter((choice) => isCommandTokenAt(input, choice.from, choice.name))
        .sort((a, b) => a.from - b.from);
      const explicitPrompts = active.flatMap((choice) =>
        choice.kind === "prompt" ? [{ ...choice, explicit: choice }] : [],
      );
      if (active.some((choice) => choice.scope !== scopeRef.current.version)) {
        const outdated =
          explicitPrompts.find((choice) => choice.scope !== scopeRef.current.version) ?? explicitPrompts[0];
        if (outdated) paramsRef.current.onResolveError("stale", outdated.name);
        else paramsRef.current.onSkillError?.("unavailable");
        return;
      }
      if (active.some((choice) => choice.kind === "skill" && !catalogs.skillNames.includes(choice.name))) {
        paramsRef.current.onSkillError?.("unavailable");
        return;
      }
      const skillRanges = findSkillInvocations(input, catalogs.skillNames);
      // A typed name that is also a skill is a skill, unless it ends the line
      // undelimited and was not picked as one: then the prompt gets it.
      const typedPrompts = findSkillInvocations(
        input,
        catalogs.commands.map((entry) => entry.command),
      ).filter(
        (token) =>
          !explicitPrompts.some((choice) => choice.from === token.from) &&
          !skillRanges.some(
            (skill) =>
              skill.from === token.from &&
              (skill.to < input.length ||
                active.some((choice) => choice.kind === "skill" && choice.from === skill.from)),
          ),
      );
      const ranges = [...explicitPrompts, ...typedPrompts.map((token) => ({ ...token, explicit: undefined }))].sort(
        (a, b) => a.from - b.from,
      );
      if (ranges.length > MAX_TURN_PROMPTS) {
        paramsRef.current.onResolveError("tooMany", ranges[MAX_TURN_PROMPTS].name);
        return;
      }
      const targets: { entry: PromptEntry; from: number; to: number }[] = [];
      for (const range of ranges) {
        const { explicit } = range;
        const entry = catalogs.commands.find(
          (candidate) =>
            candidate.command === range.name &&
            (!explicit ||
              (candidate.promptId === explicit.promptId &&
                (!explicit.promptTeamId || candidate.promptTeamId === explicit.promptTeamId))),
        );
        if (!entry) {
          paramsRef.current.onResolveError(catalogs.promptsReady ? "stale" : "unreadable", range.name);
          return;
        }
        // A typed name falls back to the personal library only once the team's
        // catalog has answered that it has no such command.
        if (!explicit && entry.promptTeamId !== paramsRef.current.teamId && !catalogs.teamReady) {
          paramsRef.current.onResolveError("unreadable", range.name);
          return;
        }
        targets.push({ entry, from: range.from, to: range.to });
      }
      if (targets.length) {
        const selections = [
          ...new Set(
            skillRanges
              .filter((token) => !ranges.some((range) => range.from === token.from))
              .map((token) => token.name),
          ),
        ].map((name) => ({ name }));
        void run(input, targets, selections);
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
    },
    [run],
  );

  // Sending never races the catalogs. A draft holding a `/name` nobody picked
  // waits for every catalog with no answer yet; one that failed is asked once
  // more, and the message is held back only if it still does not answer.
  const waitingRef = useRef(false);
  const submit = useCallback(() => {
    const draft = paramsRef.current.input;
    const choices = choicesRef.current;
    const sources = catalogSourcesRef.current;
    const typed = findCommandWords(draft).find(
      (word) =>
        !choices.some((choice) => choice.from === word.from && isCommandTokenAt(draft, choice.from, choice.name)),
    );
    if (!typed || !(sources.team.missing || sources.personal.missing || sources.skills.missing)) {
      resolve(draft, choices, {
        commands: commandsRef.current,
        skillNames: skillsRef.current.map((skill) => skill.name),
        teamReady: teamCommandsReadyRef.current,
        promptsReady: promptCatalogsReadyRef.current,
      });
      return;
    }
    if (waitingRef.current) return;
    waitingRef.current = true;
    const scopeAtSubmit = scopeRef.current.version;
    const { teamId, personalTeamId } = paramsRef.current;
    void Promise.all([answerOf(sources.team), answerOf(sources.personal), answerOf(sources.skills)]).then(
      ([team, personal, skillCatalog]) => {
        waitingRef.current = false;
        if (scopeRef.current.version !== scopeAtSubmit) return;
        const answered = {
          team: sources.team.missing ? team : sources.team.data,
          personal: sources.personal.missing ? personal : sources.personal.data,
          skills: sources.skills.missing ? skillCatalog : sources.skills.data,
        };
        if (
          (sources.team.missing && !answered.team) ||
          (sources.personal.missing && !answered.personal) ||
          (sources.skills.missing && !answered.skills)
        ) {
          paramsRef.current.onResolveError("unreadable", typed.name);
          return;
        }
        resolve(draft, choices, {
          commands: promptCommands(answered.team, answered.personal, teamId, personalTeamId),
          skillNames: answered.skills?.supported ? (answered.skills.skills ?? []).map((skill) => skill.name) : [],
          teamReady: true,
          promptsReady: true,
        });
      },
    );
  }, [resolve]);

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
          // The focus stops at either end of the list instead of wrapping.
          setActiveIndex((index) => Math.min(index + 1, count - 1));
          return true;
        case "ArrowUp":
          event.preventDefault();
          setActiveIndex((index) => Math.max(Math.min(index, count - 1) - 1, 0));
          return true;
        case "Tab":
        case "Enter":
          if (event.key === "Enter" && (event.shiftKey || event.nativeEvent.isComposing)) return false;
          event.preventDefault();
          // Enter picks the row like Tab and sends nothing: the next Enter,
          // with the menu closed, goes through the ordinary submit.
          complete(focusedEntry);
          return true;
        default:
          return false;
      }
    },
    [complete],
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

  const onDraftEdit = useCallback((edits: readonly DraftEdit[]) => {
    pendingEditsRef.current = edits;
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
    onDraftEdit,
    onQueryChange,
    onKeyDown,
    onFocusChange,
    listboxId,
    open: panelOpen,
    activeDescendantId: panelOpen && hasEntries ? optionId(safeIndex) : null,
  };

  // A catalog that failed is asked again each time a command is started, not
  // on each keystroke of its name.
  const commandStarted = focused && query !== null;
  useEffect(() => {
    if (!commandStarted) return;
    for (const source of Object.values(catalogSourcesRef.current))
      if (source.missing && source.failed) void source.refetch();
  }, [commandStarted]);

  const empty = catalogsLoading
    ? "loading"
    : catalogsFailed
      ? "error"
      : commands.length > 0 || skillEntries.length > 0
        ? "noMatch"
        : "none";
  const menu = useMemo<ComposerCommandsMenu | null>(
    () =>
      panelOpen ? { id: listboxId, entries, activeIndex: safeIndex, empty, optionId, onActivate, onFocusEntry } : null,
    [panelOpen, listboxId, entries, safeIndex, empty, optionId, onActivate, onFocusEntry],
  );

  return {
    trigger,
    menu,
    submit,
    dismiss,
    selectedSkills,
    selectedPrompts,
    selectedSkillArgumentHint: selectedSkills.length === 1 ? selectedSummary?.argument_hint?.trim() || null : null,
    skillDescriptions,
    composerValue: params.input,
    onComposerChange,
  };
}
