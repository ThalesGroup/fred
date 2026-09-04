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
import FilterChips from "@shared/molecules/FilterChips/FilterChips.tsx";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { filterPrompts, NO_CATEGORY_FILTER_ID } from "@shared/utils/promptFilter.ts";
import {
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery,
  useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery,
  type ContextPromptSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PromptSelectionChatPanel.module.css";

/** Chips shown before the "+N" toggle — same budget as the team prompts page. */
const FILTER_VISIBLE = 4;

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
  const { data: teamPrompts = [], isLoading: isLoadingTeam } =
    useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery({ teamId }, { skip: !open || !teamId });
  // `/prompts/context` returns one space per call and never leaks personal
  // prompts into a team's answer, so the personal side needs its own call.
  const { data: personalPrompts = [], isLoading: isLoadingPersonal } =
    useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery(
      { teamId: personalTeamId ?? "" },
      { skip: !open || !personalTeamId || isPersonalChat },
    );
  const { data: categories = [] } = useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery(
    { teamId: spaceTeamId ?? "" },
    { skip: !open || !spaceTeamId },
  );

  const onTeamSide = isPersonalChat || space === "team";
  const prompts = onTeamSide ? teamPrompts : personalPrompts;
  // Bootstrap may not have resolved the personal id yet; that is still loading,
  // not an empty space.
  const isLoading = onTeamSide ? isLoadingTeam : isLoadingPersonal || !personalTeamId;

  // Counts come from the whole space, not the searched subset, so a chip's
  // number does not shift as the user types.
  const categoryCounts = useMemo(() => {
    const byId = new Map<string, number>();
    let noCategory = 0;
    for (const prompt of prompts) {
      if (prompt.category_id) byId.set(prompt.category_id, (byId.get(prompt.category_id) ?? 0) + 1);
      else noCategory += 1;
    }
    return { byId, noCategory };
  }, [prompts]);

  const visiblePrompts = useMemo(
    () => filterPrompts(prompts, { search, categoryId: category }),
    [prompts, search, category],
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
    <InlineDrawer
      open={open}
      onClose={onClose}
      title={t("chatbot.promptSelectionPanel.title")}
      layout="push"
      floating
      resizable={{ persistKey: "prompt-selection-panel" }}
    >
      <div className={styles.body}>
        {!isPersonalChat && (
          <ButtonGroup
            size="small"
            color="primary"
            variant="radio"
            fullWidth
            aria-label={t("chatbot.promptSelectionPanel.spaceLabel")}
            items={SPACES.map((value) => ({ label: t(`chatbot.promptSelectionPanel.space.${value}`) }))}
            selectedIndex={SPACES.indexOf(space)}
            onSelectedIndexChange={(index) => setSpace(SPACES[index])}
          />
        )}

        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder={t("chatbot.promptSelectionPanel.searchPlaceholder")}
          clearAriaLabel={t("chatbot.promptSelectionPanel.clearSearch")}
          size="small"
        />

        {categories.length > 0 && (
          <FilterChips
            options={[
              {
                id: NO_CATEGORY_FILTER_ID,
                label: t("rework.promptCategories.noCategory"),
                count: categoryCounts.noCategory,
              },
              ...categories.map((cat) => ({
                id: cat.id,
                label: cat.name,
                count: categoryCounts.byId.get(cat.id) ?? 0,
              })),
            ]}
            value={category}
            onChange={setCategory}
            allLabel={t("chatbot.promptSelectionPanel.allCategories")}
            maxVisible={FILTER_VISIBLE}
            showMoreLabel={(count) => `+${count}`}
            showLessLabel="−"
          />
        )}

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
      </div>
    </InlineDrawer>
  );
}
