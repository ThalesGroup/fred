// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import ChatSidePanel from "@shared/molecules/ChatSidePanel/ChatSidePanel";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { filterPrompts } from "@shared/utils/promptFilter";
import { usePromptCatalogQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { PromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PromptSelectionChatPanel.module.css";

type Space = "team" | "personal";
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
  const [search, setSearch] = useState("");
  const [insertingId, setInsertingId] = useState<string | null>(null);
  const canPickSpace = !isPersonalChat && Boolean(personalTeamId);
  const spaceId = isPersonalChat || !canPickSpace || space === "team" ? teamId : personalTeamId!;
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
  }, [scope]);
  const catalog = usePromptCatalogQuery({ spaceId }, { skip: !open || !spaceId, refetchOnMountOrArgChange: true });
  const prompts = catalog.currentData?.items ?? [];
  const visible = filterPrompts(prompts, { search, categoryId: null });
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
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder={t("chatbot.promptSelectionPanel.searchPlaceholder")}
          clearAriaLabel={t("chatbot.promptSelectionPanel.clearSearch")}
          size="xs"
        />
        <p className={styles.state}>{t("rework.weaverPrompts.filtersDeferred")}</p>
      </div>
      {catalog.isError ? (
        <div className={styles.state} role="alert">
          {t("rework.weaverPrompts.catalogError")}
          <Button color="primary" variant="text" size="small" onClick={() => void catalog.refetch()}>
            {t("rework.weaverPrompts.retry")}
          </Button>
        </div>
      ) : !catalog.currentData ? (
        <div className={styles.state}>
          <Spinner size={20} />
        </div>
      ) : visible.length === 0 ? (
        <p className={styles.state}>
          {t(prompts.length === 0 ? "chatbot.promptSelectionPanel.empty" : "chatbot.promptSelectionPanel.emptyFilters")}
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
                <span className={styles.description} title={`/${prompt.logical_name}`}>
                  /{prompt.logical_name}
                </span>
                {prompt.description && <span className={styles.description}>{prompt.description}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </ChatSidePanel>
  );
}
