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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import SelectableCard from "@shared/molecules/SelectableCard/SelectableCard.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import {
  usePlatformHomeQuery,
  useSetPlatformHomeMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  PlatformHomeSettings,
  SetPlatformHomeRequest,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./HomeSettingsSection.module.scss";

type HomeLayout = NonNullable<PlatformHomeSettings["layout"]>;
// Display order of the modes; later modes are added here.
const LAYOUTS: HomeLayout[] = ["classic", "advanced"];
const LAYOUT_ICONS = { classic: "web", advanced: "auto_awesome" } as const;
// Same bounds as SetPlatformHomeRequest on the server.
const MAX_FEATURED = 10;
const MAX_BADGE = 20;
const MAX_HIGHLIGHTS = 4;
const MAX_HIGHLIGHT_LENGTH = 80;

interface DraftAgent {
  agent_instance_id: string;
  display_name: string;
  team_name?: string | null;
  available: boolean;
  badge: string;
  /** One highlight per line, as typed. */
  highlights: string;
}

function toDrafts(settings: PlatformHomeSettings): DraftAgent[] {
  return (settings.featured ?? []).map((agent) => ({
    agent_instance_id: agent.agent_instance_id,
    display_name: agent.display_name,
    team_name: agent.team_name,
    available: agent.available,
    badge: agent.badge ?? "",
    highlights: (agent.highlights ?? []).join("\n"),
  }));
}

function highlightLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function toRequest(layout: HomeLayout, drafts: DraftAgent[]): SetPlatformHomeRequest {
  return {
    layout,
    featured: drafts.map((draft) => ({
      agent_instance_id: draft.agent_instance_id,
      badge: draft.badge.trim() || null,
      highlights: highlightLines(draft.highlights),
    })),
  };
}

function highlightsError(text: string): "count" | "length" | undefined {
  const lines = highlightLines(text);
  if (lines.length > MAX_HIGHLIGHTS) return "count";
  if (lines.some((line) => line.length > MAX_HIGHLIGHT_LENGTH)) return "length";
  return undefined;
}

/**
 * Home page mode and the agents of its "featured" carousel, in display order.
 * Edits stay local until saved, since badges and highlights are typed text.
 */
export default function HomeSettingsSection() {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { data, isLoading, isError } = usePlatformHomeQuery();
  const [save, { isLoading: isSaving }] = useSetPlatformHomeMutation();

  const [layout, setLayout] = useState<HomeLayout>("classic");
  const [drafts, setDrafts] = useState<DraftAgent[]>([]);
  const [toAdd, setToAdd] = useState<string | undefined>();
  const [serverError, setServerError] = useState<string | undefined>();

  const reset = (settings: PlatformHomeSettings) => {
    setLayout(settings.layout ?? "classic");
    setDrafts(toDrafts(settings));
    setServerError(undefined);
  };
  useEffect(() => {
    if (data) reset(data);
  }, [data]);

  const request = toRequest(layout, drafts);
  const dirty = useMemo(
    () => !data || JSON.stringify(request) !== JSON.stringify(toRequest(data.layout ?? "classic", toDrafts(data))),
    [data, request],
  );
  const invalid = drafts.some((draft) => highlightsError(draft.highlights) !== undefined);
  const chosen = new Set(drafts.map((draft) => draft.agent_instance_id));
  const candidates = (data?.candidates ?? []).filter((agent) => !chosen.has(agent.agent_instance_id));
  const locked = isLoading || isError || isSaving;

  const update = (index: number, patch: Partial<DraftAgent>) =>
    setDrafts((current) => current.map((draft, i) => (i === index ? { ...draft, ...patch } : draft)));
  const move = (index: number, offset: -1 | 1) =>
    setDrafts((current) => {
      const next = [...current];
      [next[index], next[index + offset]] = [next[index + offset], next[index]];
      return next;
    });
  const add = () => {
    const agent = candidates.find((candidate) => candidate.agent_instance_id === toAdd);
    if (!agent) return;
    setDrafts((current) => [
      ...current,
      {
        agent_instance_id: agent.agent_instance_id,
        display_name: agent.display_name,
        team_name: agent.team_name,
        available: true,
        badge: "",
        highlights: "",
      },
    ]);
    setToAdd(undefined);
  };

  const persist = async () => {
    setServerError(undefined);
    try {
      await save({ setPlatformHomeRequest: request }).unwrap();
      showSuccess({ summary: t("rework.uiSettings.home.saved") });
    } catch (error: unknown) {
      setServerError(normalizeApiError(error).detail);
      showError({ summary: t("rework.uiSettings.home.saveFailed") });
    }
  };

  return (
    <section className={styles.section} aria-labelledby="home-settings-title">
      <header className={styles.header}>
        <h2 id="home-settings-title" className={styles.title}>
          {t("rework.uiSettings.home.title")}
        </h2>
        <p className={styles.hint}>{t("rework.uiSettings.home.subtitle")}</p>
      </header>
      {isError && (
        <p className={styles.error} role="alert">
          {t("rework.uiSettings.home.loadFailed")}
        </p>
      )}

      <div className={styles.field}>
        <span className={styles.label}>{t("rework.uiSettings.home.layoutLabel")}</span>
        <div className={styles.layouts} role="group" aria-label={t("rework.uiSettings.home.layoutLabel")}>
          {LAYOUTS.map((id) => (
            <SelectableCard
              key={id}
              icon={LAYOUT_ICONS[id]}
              selected={layout === id}
              disabled={locked}
              title={t(`rework.uiSettings.home.layouts.${id}`)}
              description={t(`rework.uiSettings.home.layoutHints.${id}`)}
              onSelect={() => setLayout(id)}
            />
          ))}
        </div>
      </div>

      <div className={styles.field}>
        <div className={styles.labelRow}>
          <span className={styles.label}>{t("rework.uiSettings.home.featuredLabel")}</span>
          <span className={styles.counter}>
            {drafts.length} / {MAX_FEATURED}
          </span>
        </div>
        <p className={styles.hint}>{t("rework.uiSettings.home.featuredHint", { max: MAX_FEATURED })}</p>
        {drafts.length === 0 && (
          <div className={styles.empty}>
            <Icon category="outlined" type="star" />
            <span>{t("rework.uiSettings.home.empty")}</span>
          </div>
        )}
        <ol className={styles.list}>
          {drafts.map((draft, index) => {
            const error = highlightsError(draft.highlights);
            return (
              <li key={draft.agent_instance_id} className={styles.item} data-available={draft.available}>
                <div className={styles.itemHead}>
                  <span className={styles.position}>{index + 1}</span>
                  <span className={styles.agentIcon} aria-hidden="true">
                    <Icon category="outlined" type="smart_toy" />
                  </span>
                  <span className={styles.identity}>
                    <span className={styles.name}>{draft.display_name}</span>
                    {draft.team_name && <span className={styles.team}>{draft.team_name}</span>}
                  </span>
                  {!draft.available && (
                    <span className={styles.unavailable} title={t("rework.uiSettings.home.unavailableHint")}>
                      <Icon category="outlined" type="visibility_off" />
                      {t("rework.uiSettings.home.unavailable")}
                    </span>
                  )}
                  <span className={styles.actions}>
                    <IconButton
                      variant="icon"
                      size="small"
                      icon={{ category: "outlined", type: "arrow_upward" }}
                      disabled={locked || index === 0}
                      onClick={() => move(index, -1)}
                      aria-label={t("rework.uiSettings.home.moveUp", { name: draft.display_name })}
                    />
                    <IconButton
                      variant="icon"
                      size="small"
                      icon={{ category: "outlined", type: "arrow_downward" }}
                      disabled={locked || index === drafts.length - 1}
                      onClick={() => move(index, 1)}
                      aria-label={t("rework.uiSettings.home.moveDown", { name: draft.display_name })}
                    />
                    <IconButton
                      variant="icon"
                      size="small"
                      icon={{ category: "outlined", type: "close" }}
                      disabled={locked}
                      onClick={() => setDrafts((current) => current.filter((_, i) => i !== index))}
                      aria-label={t("rework.uiSettings.home.remove", { name: draft.display_name })}
                    />
                  </span>
                </div>
                <div className={styles.extras}>
                  <TextInput
                    size="small"
                    label={t("rework.uiSettings.home.badgeLabel")}
                    explanation={t("rework.uiSettings.home.badgeHint")}
                    maxLength={MAX_BADGE}
                    value={draft.badge}
                    disabled={locked}
                    onChange={(event) => update(index, { badge: event.target.value })}
                  />
                  <TextArea
                    label={t("rework.uiSettings.home.highlightsLabel")}
                    explanation={t("rework.uiSettings.home.highlightsHint", {
                      max: MAX_HIGHLIGHTS,
                      length: MAX_HIGHLIGHT_LENGTH,
                    })}
                    rows={MAX_HIGHLIGHTS}
                    value={draft.highlights}
                    disabled={locked}
                    error={
                      error &&
                      t(`rework.uiSettings.home.highlightsError.${error}`, {
                        max: MAX_HIGHLIGHTS,
                        length: MAX_HIGHLIGHT_LENGTH,
                      })
                    }
                    onChange={(event) => update(index, { highlights: event.target.value })}
                  />
                </div>
              </li>
            );
          })}
        </ol>

        <div className={styles.addRow}>
          <div className={styles.addSelect}>
            <Select
              size="small"
              compact
              ariaLabel={t("rework.uiSettings.home.addLabel")}
              placeholder={t("rework.uiSettings.home.addPlaceholder")}
              emptyMessage={t("rework.uiSettings.home.noCandidate")}
              disabled={locked || drafts.length >= MAX_FEATURED}
              value={toAdd}
              onChange={setToAdd}
              search={{
                placeholder: t("rework.uiSettings.home.searchPlaceholder"),
                noMatchMessage: t("rework.uiSettings.home.noMatch"),
              }}
              options={candidates.map((agent) => ({
                key: agent.agent_instance_id,
                value: agent.agent_instance_id,
                label: agent.display_name,
                description: agent.team_name ?? undefined,
              }))}
            />
          </div>
          <Button
            color="primary"
            variant="tonal"
            size="small"
            icon={{ category: "outlined", type: "add" }}
            disabled={locked || !toAdd || drafts.length >= MAX_FEATURED}
            onClick={add}
          >
            {t("rework.uiSettings.home.add")}
          </Button>
        </div>
      </div>

      {serverError && (
        <p className={styles.error} role="alert">
          {serverError}
        </p>
      )}

      <div className={styles.footer}>
        {data && dirty && <span className={styles.unsaved}>{t("rework.uiSettings.home.unsaved")}</span>}
        <Button
          color="secondary"
          variant="outlined"
          size="small"
          disabled={locked || !dirty}
          onClick={() => data && reset(data)}
        >
          {t("rework.uiSettings.home.cancel")}
        </Button>
        <Button
          color="primary"
          variant="filled"
          size="small"
          disabled={locked || !dirty || invalid}
          onClick={() => void persist()}
        >
          {t("rework.uiSettings.home.save")}
        </Button>
      </div>
    </section>
  );
}
