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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import Chip from "@shared/atoms/Chip/Chip";
import Icon from "@shared/atoms/Icon/Icon";
import ClaimConditionList, {
  ClaimFieldName,
  claimLabel,
} from "@shared/molecules/ClaimConditionList/ClaimConditionList";
import { useAnalyticsUserFilterQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { PlatformAccessCondition, UserFilterField } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { InfoHint } from "./AnalyticsSection";
import {
  type AnalyticsUserFilterValue,
  KPI_CACHE,
  USER_FILTER_MAX_CONDITIONS,
  USER_FILTER_MAX_LENGTH,
  userFilterParam,
} from "./analyticsQuery";
import scopeStyles from "./AnalyticsScopeSelector.module.scss";
import styles from "./AnalyticsUserFilter.module.scss";

const COMBINATIONS = ["all", "any"] as const;
// Counts follow the draft once typing pauses, not on every key.
const COUNT_DELAY_MS = 400;

const isComplete = (condition: PlatformAccessCondition) =>
  condition.claim.length > 0 && condition.claim.every((key) => key.trim()) && condition.value.length > 0;

/** "N users match · M without data", or nothing while the counts are unknown. */
function Coverage({ param }: { param?: string }) {
  const { t } = useTranslation();
  const summary = useAnalyticsUserFilterQuery({ userFilter: param }, { ...KPI_CACHE, skip: !param });
  if (!param) return null;
  if (summary.isError) return <span className={styles.error}>{t("rework.analytics.userFilter.invalid")}</span>;
  const data = summary.currentData;
  return (
    <span className={styles.coverage} role="status">
      {data?.matched == null
        ? t("rework.analytics.userFilter.counting")
        : `${t("rework.analytics.userFilter.matched", { count: data.matched })} · ${t(
            "rework.analytics.userFilter.noData",
            { count: data.no_data ?? 0 },
          )}`}
    </span>
  );
}

/** Header control restricting every figure to users whose stored access attributes match conditions. */
export default function AnalyticsUserFilter({
  value,
  onChange,
}: {
  value: AnalyticsUserFilterValue | null;
  onChange: (filter: AnalyticsUserFilterValue | null) => void;
}) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [draft, setDraft] = useState<AnalyticsUserFilterValue>({ combination: "all", conditions: [] });
  const [picking, setPicking] = useState<number | "add">();
  const [counted, setCounted] = useState<string>();
  const containerRef = useRef<HTMLDivElement>(null);
  const fields = useAnalyticsUserFilterQuery({}, { ...KPI_CACHE, skip: !isOpen });

  const param = userFilterParam(draft);
  const complete = draft.conditions.length > 0 && draft.conditions.every(isComplete);
  const tooLong = (param?.length ?? 0) > USER_FILTER_MAX_LENGTH;

  useEffect(() => {
    if (!isOpen) return;
    const onMouseDown = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setIsOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [isOpen]);

  useEffect(() => {
    const next = complete && !tooLong ? param : undefined;
    const timer = setTimeout(() => setCounted(next), COUNT_DELAY_MS);
    return () => clearTimeout(timer);
  }, [param, complete, tooLong]);

  const open = () => {
    setDraft(value ?? { combination: "all", conditions: [] });
    setPicking(undefined);
    setIsOpen(true);
  };
  const updateCondition = (index: number, update: Partial<PlatformAccessCondition>) =>
    setDraft((prev) => ({
      ...prev,
      conditions: prev.conditions.map((condition, i) => (i === index ? { ...condition, ...update } : condition)),
    }));
  const pick = (field: UserFilterField) => {
    if (picking === "add") {
      setDraft((prev) => ({
        ...prev,
        conditions: [...prev.conditions, { claim: field.claim, operator: "equals", value: "", case_sensitive: false }],
      }));
    } else if (picking !== undefined) updateCondition(picking, { claim: field.claim });
    setPicking(undefined);
  };
  const apply = () => {
    onChange(draft.conditions.length > 0 ? draft : null);
    setIsOpen(false);
  };
  const clear = () => {
    onChange(null);
    setIsOpen(false);
  };

  const available = fields.currentData?.fields ?? [];
  const label = value
    ? t("rework.analytics.userFilter.active", { count: value.conditions.length })
    : t("rework.analytics.userFilter.title");

  return (
    <div className={scopeStyles.container} ref={containerRef} data-open={isOpen}>
      <button
        type="button"
        className={scopeStyles.trigger}
        onClick={() => (isOpen ? setIsOpen(false) : open())}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        title={label}
      >
        <Icon category="outlined" type="tune" />
        <span className={scopeStyles.label}>{label}</span>
        <Icon category="outlined" type="arrow_drop_down" />
      </button>

      {isOpen && (
        <div
          className={`${scopeStyles.panel} ${styles.panel}`}
          role="dialog"
          aria-label={t("rework.analytics.userFilter.title")}
        >
          <p className={styles.intro}>{t("rework.analytics.userFilter.intro")}</p>
          {picking !== undefined ? (
            <div className={styles.fieldList} aria-label={t("rework.platformAccess.rule.accountField")} role="group">
              {available.map((field) => (
                <button
                  type="button"
                  key={JSON.stringify(field.claim)}
                  className={`${scopeStyles.row} ${styles.fieldOption}`}
                  onClick={() => pick(field)}
                >
                  <ClaimFieldName title={claimLabel(field.claim)}>{claimLabel(field.claim)}</ClaimFieldName>
                  <span className={scopeStyles.rowMeta}>
                    {t("rework.analytics.userFilter.fieldUsers", { count: field.users })}
                    {field.in_rule && ` · ${t("rework.analytics.userFilter.inRule")}`}
                  </span>
                </button>
              ))}
              {fields.currentData && available.length === 0 && (
                <p className={scopeStyles.empty}>{t("rework.analytics.userFilter.noFields")}</p>
              )}
              <div className={scopeStyles.footer}>
                <Button variant="text" color="primary" size="small" onClick={() => setPicking(undefined)}>
                  {t("rework.analytics.scope.cancel")}
                </Button>
              </div>
            </div>
          ) : (
            <>
              <div className={styles.conditionsHeader}>
                {draft.conditions.length > 1 && (
                  <ButtonGroup
                    size="small"
                    color="secondary"
                    variant="radio"
                    aria-label={t("rework.platformAccess.rule.combination")}
                    selectedIndex={COMBINATIONS.indexOf(draft.combination)}
                    onSelectedIndexChange={(index) =>
                      setDraft((prev) => ({ ...prev, combination: COMBINATIONS[index] }))
                    }
                    items={COMBINATIONS.map((combination) => ({
                      label: t(`rework.platformAccess.rule.${combination}`),
                    }))}
                  />
                )}
                <Button
                  color="primary"
                  variant="outlined"
                  size="small"
                  disabled={draft.conditions.length >= USER_FILTER_MAX_CONDITIONS}
                  onClick={() => setPicking("add")}
                >
                  {t("rework.platformAccess.rule.addCondition")}
                </Button>
              </div>
              <ClaimConditionList
                conditions={draft.conditions}
                onChange={updateCondition}
                onRemove={(index) =>
                  setDraft((prev) => ({ ...prev, conditions: prev.conditions.filter((_, i) => i !== index) }))
                }
                onPickField={setPicking}
              />
              {draft.conditions.length === 0 && (
                <p className={scopeStyles.empty}>{t("rework.analytics.userFilter.empty")}</p>
              )}
              {tooLong ? (
                <span className={styles.error}>{t("rework.analytics.userFilter.tooLong")}</span>
              ) : (
                <Coverage param={counted} />
              )}
              <div className={scopeStyles.footer}>
                {value && (
                  <Button variant="text" color="primary" size="small" onClick={clear}>
                    {t("rework.analytics.userFilter.clear")}
                  </Button>
                )}
                <Button variant="text" color="primary" size="small" onClick={() => setIsOpen(false)}>
                  {t("rework.analytics.scope.cancel")}
                </Button>
                <Button
                  variant="filled"
                  color="primary"
                  size="small"
                  onClick={apply}
                  disabled={tooLong || (draft.conditions.length > 0 && !complete)}
                >
                  {t("rework.analytics.scope.apply")}
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** Under the header once a filter applies: its conditions, its coverage, and what it does not narrow. */
export function AnalyticsUserFilterSummary({
  value,
  onClear,
}: {
  value: AnalyticsUserFilterValue | null;
  onClear: () => void;
}) {
  const { t } = useTranslation();
  if (!value) return null;
  const text = value.conditions
    .map((c) =>
      t("rework.analytics.userFilter.condition", {
        field: claimLabel(c.claim),
        operator: t(`rework.platformAccess.rule.operatorLabel.${c.operator}`).toLowerCase(),
        value: c.value,
      }),
    )
    .join(` ${t(`rework.analytics.userFilter.${value.combination === "all" ? "and" : "or"}`)} `);
  return (
    <div className={scopeStyles.summary}>
      <Chip
        label={text}
        leading={<Icon category="outlined" type="tune" />}
        onRemove={onClear}
        removeAriaLabel={t("rework.analytics.userFilter.clear")}
      />
      <Coverage param={userFilterParam(value)} />
      <InfoHint label={t("rework.analytics.userFilter.title")} def={t("rework.analytics.userFilter.notFiltered")} />
    </div>
  );
}
