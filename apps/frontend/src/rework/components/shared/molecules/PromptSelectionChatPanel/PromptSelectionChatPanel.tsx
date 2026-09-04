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

// Prompt-library side panel for the chat composer. Replaces the anchored
// sub-menu that listed every prompt flat, with no search and no way to reach
// the caller's personal prompts from a team chat.

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import ChatSidePanel from "@shared/molecules/ChatSidePanel/ChatSidePanel.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { filterPrompts, NO_CATEGORY_FILTER_ID } from "@shared/utils/promptFilter.ts";
import {
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery,
  useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery,
  type ContextPromptSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PromptSelectionChatPanel.module.css";

/**
 * "Every category" as a select value. A sentinel rather than `null`: the menu
 * derives each option's DOM id from its value, and `null` would stringify.
 * Mapped back to `null` — no filter — before it reaches the predicate.
 */
const ALL_CATEGORIES = "__all__";

type Space = "team" | "personal";
const SPACES: Space[] = ["team", "personal"];

export interface PromptSelectionChatPanelProps {
  open: boolean;
  onClose: () => void;
  /** The chat's own team. In a personal chat this *is* the personal space. */
  teamId: string;
  /** The caller's personal space, from bootstrap. Undefined until it resolves. */
  personalTeamId?: string;
  /** Hides the space picker: a personal chat has no team side to offer. */
  isPersonalChat: boolean;
  /**
   * Inserts the prompt into the composer. Resolves true once the text is in —
   * the panel stays open on false so a failed fetch does not lose the user's
   * place in the list.
   */
  onInsert: (prompt: ContextPromptSummary) => Promise<boolean>;
}

export default function PromptSelectionChatPanel({
  open,
  onClose,
  teamId,
  personalTeamId,
  isPersonalChat,
  onInsert,
}: PromptSelectionChatPanelProps) {
  const { t } = useTranslation();
  const [space, setSpace] = useState<Space>(isPersonalChat ? "personal" : "team");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [insertingId, setInsertingId] = useState<string | null>(null);

  // Reopening starts clean: a search left over from last time would otherwise
  // show an empty list the user has no reason to expect.
  useEffect(() => {
    if (!open) return;
    setSpace(isPersonalChat ? "personal" : "team");
    setSearch("");
    setCategory(null);
  }, [open, isPersonalChat]);

  // Prompt categories are team-owned, so each space has its own set — the
  // active filter cannot survive a space change.
  useEffect(() => {
    setCategory(null);
  }, [space]);

  // The space the list and the chips read from. A personal chat only ever has
  // one, and it is the chat's own team id.
  const spaceTeamId = isPersonalChat || space === "team" ? teamId : personalTeamId;

  // Every query is skipped while closed: the panel is mounted for every chat,
  // but most sessions never open it.
  const {
    data: teamPrompts = [],
    isFetching: isFetchingTeam,
    isUninitialized: isTeamUninitialized,
  } = useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery({ teamId }, { skip: !open || !teamId });
  // `/prompts/context` returns one space per call and never leaks personal
  // prompts into a team's answer, so the personal side needs its own call.
  const {
    data: personalPrompts = [],
    isFetching: isFetchingPersonal,
    isUninitialized: isPersonalUninitialized,
  } = useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery(
    { teamId: personalTeamId ?? "" },
    { skip: !open || !personalTeamId || isPersonalChat },
  );
  const { data: categories = [] } = useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery(
    { teamId: spaceTeamId ?? "" },
    { skip: !open || !spaceTeamId },
  );

  // Switching spaces needs a personal id. Without one (bootstrap not resolved)
  // the panel stays on the team side rather than offering a tab whose query is
  // skipped and whose spinner could never clear.
  const canPickSpace = !isPersonalChat && Boolean(personalTeamId);
  const onTeamSide = !canPickSpace || space === "team";
  const prompts = onTeamSide ? teamPrompts : personalPrompts;
  // `isFetching` alone is false on the render where `skip` flips, while the
  // query is still uninitialized — the list would flash "no prompts" before the
  // spinner. Both flags together cover the whole gap.
  const isLoading = onTeamSide ? isFetchingTeam || isTeamUninitialized : isFetchingPersonal || isPersonalUninitialized;

  const knownCategoryIds = useMemo(() => new Set(categories.map((cat) => cat.id)), [categories]);

  // Counts come from the whole space, not the searched subset, so a chip's
  // number does not shift as the user types. A prompt whose category was
  // deleted counts as uncategorised, matching how the filter treats it.
  const categoryCounts = useMemo(() => {
    const byId = new Map<string, number>();
    let noCategory = 0;
    for (const prompt of prompts) {
      const id = prompt.category_id;
      if (id && knownCategoryIds.has(id)) byId.set(id, (byId.get(id) ?? 0) + 1);
      else noCategory += 1;
    }
    return { byId, noCategory };
  }, [prompts, knownCategoryIds]);

  // Counts ride in the label: a menu row has no second column for them, and the
  // number is what makes an empty category obvious before clicking it.
  const categoryOptions: OptionModel<string>[] = useMemo(
    () => [
      { value: ALL_CATEGORIES, key: ALL_CATEGORIES, label: t("chatbot.promptSelectionPanel.allCategories") },
      {
        value: NO_CATEGORY_FILTER_ID,
        key: NO_CATEGORY_FILTER_ID,
        label: `${t("rework.promptCategories.noCategory")} (${categoryCounts.noCategory})`,
      },
      ...categories.map((cat) => ({
        value: cat.id,
        key: cat.id,
        label: `${cat.name} (${categoryCounts.byId.get(cat.id) ?? 0})`,
      })),
    ],
    [categories, categoryCounts, t],
  );

  const visiblePrompts = useMemo(
    () => filterPrompts(prompts, { search, categoryId: category, knownCategoryIds }),
    [prompts, search, category, knownCategoryIds],
  );

  const handlePick = async (prompt: ContextPromptSummary) => {
    if (insertingId) return;
    setInsertingId(prompt.id);
    try {
      if (await onInsert(prompt)) onClose();
    } finally {
      setInsertingId(null);
    }
  };

  return (
    <ChatSidePanel
      open={open}
      onClose={onClose}
      title={t("chatbot.promptSelectionPanel.title")}
      persistKey="prompt-selection-panel"
      fill
    >
      {canPickSpace && (
        <ButtonGroup
          size="small"
          color="secondary"
          variant="radio"
          fullWidth
          aria-label={t("chatbot.promptSelectionPanel.spaceLabel")}
          items={SPACES.map((value) => ({ label: t(`chatbot.promptSelectionPanel.space.${value}`) }))}
          selectedIndex={SPACES.indexOf(space)}
          onSelectedIndexChange={(index) => setSpace(SPACES[index])}
        />
      )}

      {/* Search and category are one group — both narrow the same list — so they
          sit tighter than the panel body's own spacing between blocks. */}
      <div className={styles.filters}>
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder={t("chatbot.promptSelectionPanel.searchPlaceholder")}
          clearAriaLabel={t("chatbot.promptSelectionPanel.clearSearch")}
          size="small"
        />

        {categories.length > 0 && (
          <Select<string>
            size="small"
            compact
            options={categoryOptions}
            value={category ?? ALL_CATEGORIES}
            onChange={(value) => setCategory(value === ALL_CATEGORIES ? null : value)}
            ariaLabel={t("chatbot.promptSelectionPanel.categoryLabel")}
          />
        )}
      </div>

      {isLoading ? (
        <div className={styles.state}>
          <Spinner size={20} />
        </div>
      ) : visiblePrompts.length === 0 ? (
        <p className={styles.state}>
          {/* A category chip can empty the list on its own, with the search
                box untouched — "no match for this search" would be a lie. */}
          {prompts.length === 0
            ? t("chatbot.promptSelectionPanel.empty")
            : t("chatbot.promptSelectionPanel.emptyFilters")}
        </p>
      ) : (
        <ul className={styles.list}>
          {visiblePrompts.map((prompt) => (
            <li key={prompt.id}>
              <button
                type="button"
                className={styles.row}
                disabled={insertingId !== null}
                aria-busy={insertingId === prompt.id}
                onClick={() => void handlePick(prompt)}
              >
                <span className={styles.name}>{prompt.name}</span>
                {prompt.description && <span className={styles.description}>{prompt.description}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </ChatSidePanel>
  );
}
