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

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { resolveAgentIcon } from "@shared/utils/agentIcon.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import PromptViewDialog, { type PromptViewDetail } from "../../PromptsPage/PromptViewDialog/PromptViewDialog.tsx";
import { useLazyGetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetQuery } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  filterHomeSearch,
  flattenResults,
  type PromptHit,
  type SearchHit,
  totalResultCount,
} from "./homeSearchIndex.ts";
import { useHomeSearchIndex } from "./useHomeSearchIndex.ts";
import styles from "./HomeSearch.module.scss";

type PromptDialogState =
  | { mode: "team"; teamId: string; promptId: string }
  | { mode: "marketplace"; detail: PromptViewDetail; chipLabel?: string | null };

/**
 * Home "Spotlight" — one search field over agents, teams and prompts. There is
 * no global search endpoint, so `useHomeSearchIndex` aggregates per team (lazily,
 * on first focus) and the pure `filterHomeSearch` ranks/caps the matches. The
 * field mimics the chat composer's look. Selecting a result: agent → new
 * conversation, team → its agents page, prompt → the read-only view dialog
 * (rendered here so a prompt opens without leaving Home).
 */
export default function HomeSearch() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { agentIconName } = useFrontendProperties();

  const [query, setQuery] = useState("");
  // Latches on first focus so the (lazy, per-team) aggregation only ever starts
  // once the user actually engages the search.
  const [active, setActive] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [promptDialog, setPromptDialog] = useState<PromptDialogState | null>(null);

  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const sources = useHomeSearchIndex(active);
  const results = useMemo(() => filterHomeSearch(sources, query), [sources, query]);
  const flat = useMemo(() => flattenResults(results), [results]);
  const count = totalResultCount(results);
  const showMenu = menuOpen && query.trim() !== "";

  const [fetchPromptDetail] = useLazyGetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetQuery();

  // Keep the highlighted row in range as results change; top hit pre-selected so
  // Enter fires it (focus stays in the input — only the visual highlight moves).
  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  // Close on click outside.
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  const dismiss = () => {
    setMenuOpen(false);
    setQuery("");
  };

  const openPrompt = async (hit: PromptHit) => {
    if (hit.source === "team" && hit.teamId) {
      setPromptDialog({ mode: "team", teamId: hit.teamId, promptId: hit.id });
    } else {
      // Marketplace prompt: the view dialog's marketplace variant wants the full
      // text preloaded (the caller may not be a member of the author team).
      try {
        const detail = await fetchPromptDetail({ promptId: hit.id }).unwrap();
        setPromptDialog({
          mode: "marketplace",
          detail: { id: detail.id, name: detail.name, description: detail.description, text: detail.text },
          chipLabel: hit.teamName ?? null,
        });
      } catch {
        return; // fetch failed — leave the search as-is rather than opening an empty dialog
      }
    }
  };

  const activate = (hit: SearchHit) => {
    if (hit.kind === "agent") {
      dismiss();
      navigate(`/team/${hit.teamId}/managed-chat/${hit.id}`);
    } else if (hit.kind === "team") {
      dismiss();
      navigate(`/team/${hit.id}/agents`);
    } else {
      setMenuOpen(false);
      void openPrompt(hit);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!showMenu) setMenuOpen(true);
      else if (flat.length) setActiveIndex((i) => (i + 1) % flat.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (flat.length) setActiveIndex((i) => (i - 1 + flat.length) % flat.length);
    } else if (event.key === "Enter") {
      const hit = flat[activeIndex];
      if (hit) {
        event.preventDefault();
        activate(hit);
      }
    } else if (event.key === "Escape") {
      if (showMenu) setMenuOpen(false);
      else dismiss();
    }
  };

  const iconFor = (hit: SearchHit) => {
    if (hit.kind === "agent") return resolveAgentIcon(hit.instance, agentIconName);
    if (hit.kind === "team") return "groups";
    return "description";
  };

  const sublabelFor = (hit: SearchHit): string | undefined => {
    if (hit.kind === "agent") return hit.teamName;
    if (hit.kind === "prompt") return hit.teamName ?? undefined;
    return undefined;
  };

  // Flat index of a hit within the rendered order — drives the active-row style.
  let renderIndex = -1;
  const renderRow = (hit: SearchHit) => {
    renderIndex += 1;
    const index = renderIndex;
    const isActive = index === activeIndex;
    const sublabel = sublabelFor(hit);
    return (
      <button
        key={`${hit.kind}:${hit.id}`}
        type="button"
        role="option"
        aria-selected={isActive}
        data-active={isActive}
        className={styles.row}
        // Keep focus in the input so typing continues uninterrupted.
        onMouseDown={(event) => event.preventDefault()}
        onMouseEnter={() => setActiveIndex(index)}
        onClick={() => activate(hit)}
      >
        <span className={styles.rowIcon}>
          <Icon category="outlined" type={iconFor(hit)} />
        </span>
        <span className={styles.rowText}>
          <span className={styles.rowLabel}>{hit.name}</span>
          {sublabel && <span className={styles.rowSublabel}>{sublabel}</span>}
        </span>
      </button>
    );
  };

  const group = (titleKey: string, hits: SearchHit[]) =>
    hits.length > 0 && (
      <div className={styles.group} role="group" aria-label={t(titleKey)}>
        <div className={styles.groupTitle}>{t(titleKey)}</div>
        {hits.map(renderRow)}
      </div>
    );

  return (
    <div ref={wrapRef} className={styles.wrap}>
      <div className={styles.field}>
        <span className={styles.searchIcon}>
          <Icon category="outlined" type="search" />
        </span>
        <input
          ref={inputRef}
          className={styles.input}
          type="text"
          role="combobox"
          aria-expanded={showMenu}
          aria-controls="home-search-listbox"
          autoComplete="off"
          placeholder={t("rework.home.search.placeholder")}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setMenuOpen(event.target.value.trim() !== "");
          }}
          onFocus={() => {
            setActive(true);
            if (query.trim() !== "") setMenuOpen(true);
          }}
          onKeyDown={handleKeyDown}
        />
      </div>

      {showMenu && (
        <div id="home-search-listbox" role="listbox" className={styles.menu}>
          {count === 0 ? (
            <div className={styles.empty}>{t("rework.home.search.empty")}</div>
          ) : (
            <>
              {group("rework.home.search.groups.agents", results.agents)}
              {group("rework.home.search.groups.teams", results.teams)}
              {group("rework.home.search.groups.prompts", results.prompts)}
            </>
          )}
        </div>
      )}

      <PromptViewDialog
        open={!!promptDialog}
        onClose={() => setPromptDialog(null)}
        teamId={promptDialog?.mode === "team" ? promptDialog.teamId : undefined}
        promptId={promptDialog?.mode === "team" ? promptDialog.promptId : null}
        preloadedDetail={promptDialog?.mode === "marketplace" ? promptDialog.detail : null}
        chipLabel={promptDialog?.mode === "marketplace" ? promptDialog.chipLabel : null}
      />
    </div>
  );
}
