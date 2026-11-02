// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { usePromptFavoriteToggle } from "@core/hooks/usePromptFavoriteToggle";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import ChatSidePanel from "@shared/molecules/ChatSidePanel/ChatSidePanel";
import Select from "@shared/molecules/Select/Select";
import FavoritesFilterChip from "@shared/molecules/FavoritesFilterChip/FavoritesFilterChip";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { filterPrompts, countPromptsByCategory, NO_CATEGORY_FILTER_ID } from "@shared/utils/promptFilter";
import {
  usePromptCatalogQuery,
  useListPromptCategoriesQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { PromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PromptSelectionChatPanel.module.css";

type Space = "team" | "personal";
const ALL_CATEGORIES = "__all_categories__";
const SPACES: Space[] = ["team", "personal"];

export interface PromptSelectionChatPanelProps {
  open: boolean;
  onClose: () => void;
  teamId: string;
  /** Authorized personal space in the conversation's organization. */
  personalTeamId?: string;
  isPersonalChat: boolean;
  /** Only closes after the complete text has been inserted into the draft. */
  onInsert: (prompt: PromptSummary) => Promise<boolean>;
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
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [insertingId, setInsertingId] = useState<string | null>(null);
  const canPickSpace = !isPersonalChat && Boolean(personalTeamId);
  const spaceId = isPersonalChat || !canPickSpace || space === "team" ? teamId : personalTeamId!;
  const toggleFavorite = usePromptFavoriteToggle(spaceId);
  const scope = JSON.stringify([open, spaceId]);
  const currentScope = useRef({ key: scope });
  if (currentScope.current.key !== scope) currentScope.current = { key: scope };
  const scopeIdentity = currentScope.current;
  useEffect(() => {
    setSpace(isPersonalChat ? "personal" : "team");
    setSearch("");
  }, [open, teamId, personalTeamId, isPersonalChat]);
  useEffect(() => {
    setSearch("");
    setInsertingId(null);
    setCategoryId(null);
    setFavoritesOnly(false);
  }, [scope]);
  const catalog = usePromptCatalogQuery({ spaceId }, { skip: !open || !spaceId, refetchOnMountOrArgChange: true });
  const categoryCatalog = useListPromptCategoriesQuery(
    { spaceId },
    { skip: !open || !spaceId, refetchOnMountOrArgChange: true },
  );
  const categories = categoryCatalog.currentData?.items ?? [];
  useEffect(() => {
    if (
      categoryCatalog.currentData &&
      !categoryCatalog.isFetching &&
      categoryId &&
      categoryId !== NO_CATEGORY_FILTER_ID &&
      !categoryCatalog.currentData.items.some((category) => category.id === categoryId)
    )
      setCategoryId(null);
  }, [categoryCatalog.currentData, categoryCatalog.isFetching, categoryId]);
  const prompts = catalog.currentData?.items ?? [];
  const counts = useMemo(() => countPromptsByCategory(prompts), [prompts]);
  const visible = filterPrompts(prompts, { search, categoryId, favoritesOnly });
  const handlePick = async (prompt: PromptSummary) => {
    if (insertingId) return;
    setInsertingId(prompt.prompt_id);
    try {
      if ((await onInsert(prompt)) && currentScope.current === scopeIdentity) onClose();
    } finally {
      if (currentScope.current === scopeIdentity) setInsertingId(null);
    }
  };
  return (
    <ChatSidePanel
      open={open}
      onClose={onClose}
      title={t("chatbot.promptSelectionPanel.title")}
      persistKey="prompt-selection-panel"
      width="340px"
      fill
    >
      {canPickSpace && (
        <ButtonGroup
          size="2xs"
          color="secondary"
          variant="radio"
          fullWidth
          aria-label={t("chatbot.promptSelectionPanel.spaceLabel")}
          items={SPACES.map((value) => ({ label: t(`chatbot.promptSelectionPanel.space.${value}`) }))}
          selectedIndex={SPACES.indexOf(space)}
          onSelectedIndexChange={(index) => setSpace(SPACES[index])}
        />
      )}
      <div className={styles.filters}>
        <div className={styles.searchRow}>
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder={t("chatbot.promptSelectionPanel.searchPlaceholder")}
            clearAriaLabel={t("chatbot.promptSelectionPanel.clearSearch")}
            size="xs"
          />
          <FavoritesFilterChip
            size="xs"
            label={t("rework.teams.prompts.favorite.filter")}
            active={favoritesOnly}
            onToggle={() => setFavoritesOnly((value) => !value)}
          />
        </div>
        {categories.length > 0 && (
          <Select
            size="xs"
            compact
            ariaLabel={t("chatbot.promptSelectionPanel.categoryLabel")}
            disabled={
              !categoryCatalog.currentData || categoryCatalog.isError || !catalog.currentData || catalog.isError
            }
            value={categoryId ?? ALL_CATEGORIES}
            onChange={(value) => setCategoryId(value === ALL_CATEGORIES ? null : value)}
            options={[
              { key: ALL_CATEGORIES, value: ALL_CATEGORIES, label: t("chatbot.promptSelectionPanel.allCategories") },
              {
                key: NO_CATEGORY_FILTER_ID,
                value: NO_CATEGORY_FILTER_ID,
                label: `${t("rework.promptCategories.noCategory")} (${counts.get(null) ?? 0})`,
              },
              ...categories.map((category) => ({
                key: category.id,
                value: category.id,
                label: `${category.name} (${counts.get(category.id) ?? 0})`,
              })),
            ]}
          />
        )}
      </div>
      {catalog.isError || categoryCatalog.isError ? (
        <div className={styles.state} role="alert">
          {t(categoryCatalog.isError ? "rework.promptCategories.loadError" : "rework.weaverPrompts.catalogError")}
          <Button
            color="primary"
            variant="text"
            size="small"
            onClick={() => {
              void catalog.refetch();
              void categoryCatalog.refetch();
            }}
          >
            {t("rework.weaverPrompts.retry")}
          </Button>
        </div>
      ) : !catalog.currentData || !categoryCatalog.currentData ? (
        <div className={styles.state}>
          <Spinner size={20} />
        </div>
      ) : visible.length === 0 ? (
        <p className={styles.state}>
          {t(
            prompts.length === 0
              ? "chatbot.promptSelectionPanel.empty"
              : favoritesOnly && !search && !categoryId
                ? "rework.teams.prompts.favorite.empty"
                : "chatbot.promptSelectionPanel.emptyFilters",
          )}
        </p>
      ) : (
        <ul className={styles.list}>
          {visible.map((prompt) => (
            <li key={prompt.prompt_id} className={styles.item}>
              <button
                type="button"
                className={styles.row}
                disabled={insertingId !== null}
                aria-busy={insertingId === prompt.prompt_id}
                onClick={() => void handlePick(prompt)}
              >
                <span className={styles.name} title={prompt.display_name}>
                  {prompt.display_name}
                </span>
                {prompt.description && <span className={styles.description}>{prompt.description}</span>}
              </button>
              {/* A sibling of the row: a button cannot hold a button. */}
              <span className={styles.favorite}>
                <Tooltip
                  text={t(
                    prompt.is_favorite ? "rework.teams.prompts.favorite.remove" : "rework.teams.prompts.favorite.add",
                  )}
                >
                  <IconButton
                    variant="icon"
                    size="small"
                    color={prompt.is_favorite ? "warning" : "on-surface-retreat"}
                    icon={{ category: "outlined", type: "star", filled: prompt.is_favorite }}
                    aria-label={t("rework.teams.prompts.favorite.filter")}
                    aria-pressed={prompt.is_favorite}
                    onClick={() => void toggleFavorite(prompt)}
                  />
                </Tooltip>
              </span>
            </li>
          ))}
        </ul>
      )}
    </ChatSidePanel>
  );
}
