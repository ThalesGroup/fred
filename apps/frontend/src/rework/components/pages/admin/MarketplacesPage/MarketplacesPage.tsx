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

// Admin "Marketplaces": default publishing switch and quota, with per-team
// overrides (same Default mechanism as Features). A switch-off removes published
// agents, so it is confirmed whenever it would remove any or cannot be previewed.

import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useLazyMarketplaceDefaultImpactQuery,
  useLazyTeamMarketplaceSettingsImpactQuery,
  useMarketplaceSettingsQuery,
  useSetMarketplaceDefaultMutation,
  useSetTeamMarketplaceSettingsMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  MarketplaceSettingsImpact,
  SetTeamMarketplaceSettingsRequest,
  TeamMarketplaceSettings,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { normalizeApiError } from "../../../../core/errors/normalizeApiError";
import styles from "./MarketplacesPage.module.css";
import {
  DEFAULT_CHOICES,
  PUBLISHING_CHOICES,
  choiceColor,
  overrideForChoice,
  parseQuota,
  publishingChoice,
  turnsTeamOff,
  type PublishingChoice,
} from "./marketplaceSettings";

interface PendingSwitchOff {
  message: string;
  impact: MarketplaceSettingsImpact | null;
  apply: () => void;
}

interface QuotaFieldProps {
  value: number;
  ariaLabel: string;
  disabled: boolean;
  autoFocus?: boolean;
  /** Resolves to whether the save succeeded. */
  onCommit: (quota: number) => Promise<boolean>;
}

/** Saved on blur or Enter; an empty or invalid value is refused, never sent. */
function QuotaField({ value, ariaLabel, disabled, autoFocus, onCommit }: QuotaFieldProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(String(value));
  const [invalid, setInvalid] = useState(false);
  // Enter then blur would send the same value twice: hold it until the saved
  // value comes back, or release it if the save failed.
  const sent = useRef<number | null>(null);
  useEffect(() => {
    setDraft(String(value));
    setInvalid(false);
    sent.current = null;
  }, [value]);

  const commit = () => {
    const quota = parseQuota(draft);
    setInvalid(quota === null);
    if (quota === null || quota === value || quota === sent.current) return;
    sent.current = quota;
    void onCommit(quota).then((saved) => {
      if (!saved && sent.current === quota) sent.current = null;
    });
  };

  return (
    <div className={styles.quotaField}>
      <TextInput
        type="number"
        min={1}
        step={1}
        size="xs"
        compact={!invalid}
        value={draft}
        disabled={disabled}
        autoFocus={autoFocus}
        aria-label={ariaLabel}
        aria-invalid={invalid}
        error={invalid ? t("rework.admin.marketplaces.quotaInvalid") : undefined}
        showCharacterCount={false}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit();
        }}
      />
    </div>
  );
}

export default function MarketplacesPage() {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { data, isLoading, isError } = useMarketplaceSettingsQuery();
  const [setDefault, { isLoading: isSavingDefault }] = useSetMarketplaceDefaultMutation();
  const [setTeamSettings, { isLoading: isSavingTeam }] = useSetTeamMarketplaceSettingsMutation();
  const [previewDefault] = useLazyMarketplaceDefaultImpactQuery();
  const [previewTeam] = useLazyTeamMarketplaceSettingsImpactQuery();
  const [pendingSwitchOff, setPendingSwitchOff] = useState<PendingSwitchOff | null>(null);
  // Teams whose quota the admin is about to customize: nothing is saved until a value is entered.
  const [customizing, setCustomizing] = useState<ReadonlySet<string>>(new Set());
  const busy = isSavingDefault || isSavingTeam;

  const defaults = data?.default;
  const teams = data?.teams ?? [];

  const save = async (write: () => Promise<unknown>) => {
    try {
      await write();
      showSuccess({ summary: t("rework.admin.marketplaces.savedToast") });
      return true;
    } catch (error) {
      showError({ summary: t("rework.admin.marketplaces.saveError"), detail: normalizeApiError(error).detail });
      return false;
    }
  };

  const saveDefault = (agentsPublishingEnabled: boolean, agentsPublishQuota: number) =>
    save(() =>
      setDefault({
        setAgentsMarketplaceDefaultRequest: {
          agents_publishing_enabled: agentsPublishingEnabled,
          agents_publish_quota: agentsPublishQuota,
        },
      }).unwrap(),
    );

  const saveTeam = (team: TeamMarketplaceSettings, request: SetTeamMarketplaceSettingsRequest) =>
    save(() => setTeamSettings({ teamId: team.team_id, setTeamMarketplaceSettingsRequest: request }).unwrap());

  // Preview what a switch-off removes: apply directly when it removes nothing,
  // otherwise ask first — also when the preview fails, without the counts.
  const confirmSwitchOff = async (
    message: string,
    preview: () => Promise<MarketplaceSettingsImpact>,
    apply: () => void,
  ) => {
    try {
      const impact = await preview();
      if (!impact.removed_published_agents) {
        apply();
        return;
      }
      setPendingSwitchOff({ message, impact, apply });
    } catch (error) {
      showError({ summary: t("rework.admin.marketplaces.impactError"), detail: normalizeApiError(error).detail });
      setPendingSwitchOff({ message, impact: null, apply });
    }
  };

  const selectDefault = (next: boolean) => {
    if (!defaults || next === defaults.agents_publishing_enabled) return;
    const apply = () => void saveDefault(next, defaults.agents_publish_quota);
    if (next) {
      apply();
      return;
    }
    void confirmSwitchOff(
      t("rework.admin.marketplaces.offConfirm.defaultMessage"),
      () => previewDefault({ agentsPublishingEnabled: false }).unwrap(),
      apply,
    );
  };

  const selectChoice = (team: TeamMarketplaceSettings, choice: PublishingChoice) => {
    if (!defaults || choice === publishingChoice(team)) return;
    const override = overrideForChoice(choice);
    const apply = () =>
      void saveTeam(team, {
        agents_publishing_enabled: override,
        agents_publish_quota: team.agents_publish_quota_override ?? null,
      });
    if (!turnsTeamOff(team, choice, defaults.agents_publishing_enabled)) {
      apply();
      return;
    }
    void confirmSwitchOff(
      t("rework.admin.marketplaces.offConfirm.teamMessage", { team: team.team_name }),
      () => previewTeam({ teamId: team.team_id, agentsPublishingEnabled: override ?? undefined }).unwrap(),
      apply,
    );
  };

  const setTeamQuota = (team: TeamMarketplaceSettings, quota: number | null) =>
    saveTeam(team, {
      agents_publishing_enabled: team.agents_publishing_enabled_override ?? null,
      agents_publish_quota: quota,
    });

  const setTeamCustomizing = (teamId: string, on: boolean) =>
    setCustomizing((current) => {
      const next = new Set(current);
      if (on) next.add(teamId);
      else next.delete(teamId);
      return next;
    });

  // Back to Default sends a null override, so the team follows later default changes.
  const resetTeamQuota = (team: TeamMarketplaceSettings) => {
    setTeamCustomizing(team.team_id, false);
    if (team.agents_publish_quota_override != null) void setTeamQuota(team, null);
  };

  const quotaCell = (team: TeamMarketplaceSettings) => {
    if (!defaults) return null;
    const overridden = team.agents_publish_quota_override != null;
    const customized = overridden || customizing.has(team.team_id);
    return (
      <div className={styles.quotaCell}>
        {customized ? (
          <QuotaField
            value={team.agents_publish_quota}
            ariaLabel={t("rework.admin.marketplaces.quotaAria", { team: team.team_name })}
            disabled={busy}
            autoFocus={!overridden}
            onCommit={(quota) => setTeamQuota(team, quota)}
          />
        ) : (
          <span className={styles.quotaDefault}>{t("rework.admin.marketplaces.choice.default")}</span>
        )}
        {customized ? (
          <Tooltip text={t("rework.admin.marketplaces.resetQuota", { count: defaults.agents_publish_quota })}>
            <IconButton
              variant="icon"
              size="small"
              color="on-surface-retreat"
              icon={{ category: "outlined", type: "history" }}
              disabled={busy}
              aria-label={t("rework.admin.marketplaces.resetQuotaAria", { team: team.team_name })}
              onClick={() => resetTeamQuota(team)}
            />
          </Tooltip>
        ) : (
          <Tooltip text={t("rework.admin.marketplaces.customizeQuota")}>
            <IconButton
              variant="icon"
              size="small"
              color="on-surface-retreat"
              icon={{ category: "outlined", type: "edit" }}
              disabled={busy}
              aria-label={t("rework.admin.marketplaces.customizeQuotaAria", { team: team.team_name })}
              onClick={() => setTeamCustomizing(team.team_id, true)}
            />
          </Tooltip>
        )}
      </div>
    );
  };

  const columns: DataTableColumn<TeamMarketplaceSettings>[] = [
    {
      label: t("rework.admin.marketplaces.col.team"),
      size: "1.6fr",
      cellRenderer: (team) => team.team_name,
    },
    {
      label: t("rework.admin.marketplaces.col.publishing"),
      size: "17rem",
      cellRenderer: (team) => (
        <ButtonGroup
          size="2xs"
          color="secondary"
          variant="radio"
          aria-label={t("rework.admin.marketplaces.rowControlAria", { team: team.team_name })}
          selectedIndex={PUBLISHING_CHOICES.indexOf(publishingChoice(team))}
          onSelectedIndexChange={(index) => selectChoice(team, PUBLISHING_CHOICES[index])}
          items={PUBLISHING_CHOICES.map((choice) => ({
            label: t(`rework.admin.marketplaces.choice.${choice}`),
            selectedColor: choiceColor(choice),
            disabled: busy,
          }))}
        />
      ),
    },
    {
      label: t("rework.admin.marketplaces.col.quota"),
      size: "14rem",
      cellRenderer: quotaCell,
    },
    {
      label: t("rework.admin.marketplaces.col.published"),
      size: "7rem",
      cellRenderer: (team) => team.published_count,
    },
  ];

  const impact = pendingSwitchOff?.impact;

  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.admin.marketplaces.title")} subtitle={t("rework.admin.marketplaces.subtitle")} />

      {isLoading && <p className={styles.status}>{t("rework.admin.marketplaces.loading")}</p>}
      {isError && <p className={styles.statusError}>{t("rework.admin.marketplaces.loadError")}</p>}

      {defaults && (
        <section className={styles.section} aria-labelledby="marketplaces-agents">
          <h2 id="marketplaces-agents" className={styles.sectionTitle}>
            {t("rework.admin.marketplaces.agentsSection")}
          </h2>
          <div className={styles.defaultRow}>
            <div className={styles.defaultText}>
              <span className={styles.defaultTitle}>{t("rework.admin.marketplaces.defaultTitle")}</span>
              <span className={styles.defaultHint}>{t("rework.admin.marketplaces.defaultHint")}</span>
            </div>
            <ButtonGroup
              size="small"
              color="secondary"
              variant="radio"
              aria-label={t("rework.admin.marketplaces.defaultTitle")}
              selectedIndex={DEFAULT_CHOICES.indexOf(defaults.agents_publishing_enabled ? "enabled" : "disabled")}
              onSelectedIndexChange={(index) => selectDefault(DEFAULT_CHOICES[index] === "enabled")}
              items={DEFAULT_CHOICES.map((choice) => ({
                label: t(`rework.admin.marketplaces.defaultChoice.${choice}`),
                selectedColor: choiceColor(choice),
                disabled: busy,
              }))}
            />
            <div className={styles.defaultControl}>
              <span>{t("rework.admin.marketplaces.quota")}</span>
              <QuotaField
                value={defaults.agents_publish_quota}
                ariaLabel={t("rework.admin.marketplaces.defaultQuotaAria")}
                disabled={busy}
                onCommit={(quota) => saveDefault(defaults.agents_publishing_enabled, quota)}
              />
            </div>
          </div>

          {teams.length === 0 ? (
            <PageEmptyState icon="storefront" message={t("rework.admin.marketplaces.noTeams")} />
          ) : (
            <DataTable columns={columns} data={teams} rowKey={(team) => team.team_id} size="small" />
          )}
        </section>
      )}

      <ConfirmationDialog
        open={pendingSwitchOff !== null}
        title={t("rework.admin.marketplaces.offConfirm.title")}
        message={pendingSwitchOff?.message}
        details={
          impact && (
            <p className={styles.impact}>
              {t("rework.admin.marketplaces.offConfirm.agents", { count: impact.removed_published_agents ?? 0 })}
            </p>
          )
        }
        confirmLabel={t("rework.admin.marketplaces.offConfirm.confirm")}
        cancelLabel={t("rework.admin.marketplaces.offConfirm.cancel")}
        criticalAction
        onConfirm={() => {
          pendingSwitchOff?.apply();
          setPendingSwitchOff(null);
        }}
        onCancel={() => setPendingSwitchOff(null)}
      />
    </div>
  );
}
