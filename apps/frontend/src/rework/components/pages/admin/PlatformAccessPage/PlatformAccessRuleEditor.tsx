// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Button from "@shared/atoms/Button/Button";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Switch from "@shared/atoms/Switch/Switch";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import Select from "@shared/molecules/Select/Select";
import type {
  HttpValidationError,
  PlatformAccessCondition,
  PlatformAccessPolicy,
  PlatformAccessPolicyPreview,
  PlatformAccessState,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  usePlatformAccessUsersQuery,
  usePreviewPlatformPolicyMutation,
  useSavePlatformPolicyMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { KeyCloakService } from "../../../../../security/KeycloakService";
import styles from "./PlatformAccessPage.module.css";
import PlatformAccessClaimPicker from "./PlatformAccessClaimPicker";
import PlatformAccessValuePrompt from "./PlatformAccessValuePrompt";

const emptyCondition = (): PlatformAccessCondition => ({
  claim: [""],
  operator: "contains",
  value: "",
  case_sensitive: false,
});
const copyPolicy = (policy: PlatformAccessPolicy | null): PlatformAccessPolicy =>
  policy
    ? { ...policy, conditions: policy.conditions.map((condition) => ({ ...condition, claim: [...condition.claim] })) }
    : { combination: "all", conditions: [] };
const operators: PlatformAccessCondition["operator"][] = ["contains", "not_contains", "equals", "not_equals", "regex"];
const combinations = ["all", "any"] as const;

export default function PlatformAccessRuleEditor({
  state,
  disabled,
  reload,
}: {
  state: PlatformAccessState;
  disabled: boolean;
  reload: () => Promise<PlatformAccessState | undefined>;
}) {
  const { t } = useTranslation();
  const fieldId = useId();
  const [preview] = usePreviewPlatformPolicyMutation();
  const [save] = useSavePlatformPolicyMutation();
  const generation = useRef(0);
  const conditionList = useRef<HTMLDivElement>(null);
  const revealLast = useRef(false);
  const [draft, setDraft] = useState(() => copyPolicy(state.policy));
  const [revision, setRevision] = useState(state.revision);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<string>();
  const [conflict, setConflict] = useState(false);
  const [conditionErrors, setConditionErrors] = useState<Record<number, string>>({});
  const [picking, setPicking] = useState<number | "add">();
  const [selection, setSelection] = useState<number>();
  const [result, setResult] = useState<PlatformAccessPolicyPreview>();
  const locked = disabled || busy;
  // The test answers "kept or lost" only; the admin user list names what else grants access.
  const username = KeyCloakService.GetUserName();
  const ownAccess = usePlatformAccessUsersQuery(
    { offset: 0, limit: 100, query: username ?? "" },
    { skip: !result?.admitted || !username },
  );
  const ruleUnchecked = result?.conditions.some((reason) => reason === "timeout" || reason === "unavailable") ?? false;
  const blocking = draft.mode === "block";
  const ruleAccepts = !!result && !ruleUnchecked && (blocking ? !result.matched : result.matched);
  const ownSources = ownAccess.currentData?.items.find((user) => user.user_id === KeyCloakService.GetUserId())?.sources;
  const accessSources = [
    ...new Set([
      ...(ruleAccepts ? [t("rework.platformAccess.rule.accessSource.rule")] : []),
      ...(ownSources ?? [])
        .filter((source) => source.kind !== "attribute")
        .map((source) =>
          source.kind === "team" || source.kind === "free"
            ? t(`rework.platformAccess.rule.accessSource.${source.kind}`, { team: source.team_name || source.team_id })
            : t(`rework.platformAccess.rule.accessSource.${source.kind === "admin" ? "admin" : "manual"}`),
        ),
    ]),
  ];
  const [saved, setSaved] = useState(false);
  const valid =
    draft.conditions.length > 0 &&
    draft.conditions.every(
      (condition) =>
        condition.claim.length > 0 &&
        condition.claim.length <= 16 &&
        condition.claim.every((key) => key.trim().length > 0 && key.length <= 256) &&
        condition.value.length > 0 &&
        condition.value.length <= (condition.operator === "regex" ? 2048 : 1024),
    );

  useEffect(() => {
    if (!dirty && picking === undefined && selection === undefined && state.revision >= revision) {
      if (state.revision !== revision) {
        generation.current += 1;
        setResult(undefined);
      }
      setDraft(copyPolicy(state.policy));
      setRevision(state.revision);
    }
  }, [state, dirty, revision, picking, selection]);

  // The add button sits above the list, so a new condition is brought into view at its end.
  useEffect(() => {
    if (!revealLast.current) return;
    revealLast.current = false;
    conditionList.current?.lastElementChild?.scrollIntoView?.({ block: "nearest" });
  }, [draft.conditions.length]);

  const edit = (policy: PlatformAccessPolicy) => {
    generation.current += 1;
    setDraft(policy);
    setDirty(true);
    setSaved(false);
    setResult(undefined);
    setFeedback(undefined);
    setConditionErrors({});
  };
  const updateCondition = (index: number, update: Partial<PlatformAccessCondition>) =>
    edit({
      ...draft,
      conditions: draft.conditions.map((condition, i) => (i === index ? { ...condition, ...update } : condition)),
    });
  const reportError = (error: unknown) => {
    const normalized = normalizeApiError(error);
    if (normalized.status === 422 && error && typeof error === "object" && "data" in error) {
      const validation = error.data as HttpValidationError;
      const fields: Record<number, string> = {};
      if (Array.isArray(validation?.detail)) {
        for (const entry of validation.detail) {
          const position = entry.loc.indexOf("conditions");
          const index = entry.loc[position + 1];
          if (position >= 0 && typeof index === "number" && draft.conditions[index]) {
            fields[index] = t(
              draft.conditions[index].operator === "regex"
                ? "rework.platformAccess.rule.invalidRegex"
                : "rework.platformAccess.rule.invalidCondition",
            );
          }
        }
      }
      setConditionErrors(fields);
    }
    const detail = normalized.detail;
    const key =
      detail === "platform_access_policy_conflict"
        ? "conflict"
        : detail === "platform_access_actor_lockout"
          ? "actorLockout"
          : "invalidOrFailed";
    setConflict(key === "conflict");
    setFeedback(t(`rework.platformAccess.rule.${key}`));
  };
  const test = async () => {
    setBusy(true);
    setFeedback(undefined);
    const testedGeneration = generation.current;
    try {
      const tested = await preview({ platformAccessPolicy: draft }).unwrap();
      if (generation.current === testedGeneration) setResult(tested);
    } catch (error) {
      if (generation.current === testedGeneration) reportError(error);
    } finally {
      setBusy(false);
    }
  };
  const persist = async () => {
    setBusy(true);
    setSaving(true);
    setSaved(false);
    setFeedback(undefined);
    try {
      const saved = await save({ setPlatformAccessPolicy: { policy: draft, expected_revision: revision } }).unwrap();
      setDraft(copyPolicy(saved.policy));
      setRevision(saved.revision);
      setDirty(false);
      setConflict(false);
      setConditionErrors({});
      setResult(undefined);
      setSaved(true);
      setFeedback(t("rework.platformAccess.rule.saved"));
    } catch (error) {
      reportError(error);
    } finally {
      setBusy(false);
      setSaving(false);
    }
  };
  const discardAndReload = async () => {
    setBusy(true);
    try {
      const fresh = await reload();
      if (!fresh) throw new Error("Unavailable policy");
      setDraft(copyPolicy(fresh.policy));
      setRevision(fresh.revision);
      setDirty(false);
      setConflict(false);
      setConditionErrors({});
      setResult(undefined);
      setFeedback(undefined);
    } catch (error) {
      reportError(error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={styles.ruleEditor}>
      <Select
        compact
        label={t("rework.platformAccess.rule.mode")}
        size="small"
        value={draft.mode ?? "allow"}
        disabled={locked}
        options={(["allow", "block"] as const).map((mode) => ({
          key: mode,
          value: mode,
          label: t(`rework.platformAccess.rule.modeLabel.${mode}`),
        }))}
        onChange={(mode) => edit({ ...draft, mode: mode === "block" ? "block" : "allow" })}
      />
      <div className={styles.conditionsHeader}>
        <h3>{t("rework.platformAccess.rule.conditions")}</h3>
        {draft.conditions.length > 1 && (
          <ButtonGroup
            size="small"
            color="secondary"
            variant="radio"
            aria-label={t("rework.platformAccess.rule.combination")}
            selectedIndex={combinations.indexOf(draft.combination ?? "all")}
            onSelectedIndexChange={(index) => edit({ ...draft, combination: combinations[index] })}
            items={combinations.map((combination) => ({
              label: t(`rework.platformAccess.rule.${combination}`),
              disabled: locked,
            }))}
          />
        )}
        <Button
          color="primary"
          variant="outlined"
          size="small"
          disabled={locked || draft.conditions.length >= 16}
          onClick={() => setPicking("add")}
        >
          {t("rework.platformAccess.rule.addCondition")}
        </Button>
      </div>
      {draft.conditions.length > 0 && (
        <div className={styles.conditions} ref={conditionList}>
          {/* Visual column headings only: each control carries its own accessible name. */}
          <div className={`${styles.conditionRow} ${styles.conditionLabels}`} aria-hidden="true">
            <span />
            <span>{t("rework.platformAccess.rule.accountField")}</span>
            <span>{t("rework.platformAccess.rule.operator")}</span>
            <span>{t("rework.platformAccess.rule.value")}</span>
            <span>{t("rework.platformAccess.rule.caseSensitive")}</span>
            <span />
          </div>
          {draft.conditions.map((condition, index) => {
            const selectedField = condition.claim.some(Boolean)
              ? condition.claim.length === 1
                ? condition.claim[0]
                : condition.claim.map((key) => JSON.stringify(key)).join(" > ")
              : t("rework.platformAccess.picker.choose");
            const maxLength = condition.operator === "regex" ? 2048 : 1024;
            const showCounter = condition.value.length >= maxLength * 0.9;
            const conditionLabel = t("rework.platformAccess.rule.condition", { number: index + 1 });
            const valueLabel = t(
              condition.operator === "regex" ? "rework.platformAccess.rule.regex" : "rework.platformAccess.rule.value",
            );
            return (
              <fieldset className={styles.condition} key={index} disabled={locked}>
                <legend className={styles.screenReaderOnly}>{conditionLabel}</legend>
                <div className={styles.conditionRow}>
                  <span className={styles.conditionNumber} aria-hidden="true">
                    {index + 1}
                  </span>
                  <div className={styles.conditionCell}>
                    <span aria-hidden="true">{t("rework.platformAccess.rule.accountField")}</span>
                    <button
                      type="button"
                      disabled={locked}
                      className={styles.fieldChoice}
                      aria-label={`${t("rework.platformAccess.rule.accountField")}: ${selectedField}`}
                      aria-haspopup="dialog"
                      onClick={() => setPicking(index)}
                    >
                      <code className={styles.fieldName} title={selectedField}>
                        {selectedField}
                      </code>
                      <Icon category="outlined" type="edit" />
                    </button>
                  </div>
                  <div className={styles.conditionCell}>
                    <span aria-hidden="true">{t("rework.platformAccess.rule.operator")}</span>
                    <Select
                      compact
                      size="xs"
                      ariaLabel={t("rework.platformAccess.rule.operator")}
                      disabled={locked}
                      value={condition.operator}
                      options={operators.map((operator) => ({
                        key: operator,
                        value: operator,
                        label: t(`rework.platformAccess.rule.operatorLabel.${operator}`),
                      }))}
                      onChange={(operator) => updateCondition(index, { operator })}
                    />
                  </div>
                  <div className={styles.conditionCell}>
                    <span aria-hidden="true">{valueLabel}</span>
                    <TextInput
                      size="xs"
                      compact={!conditionErrors[index] && !showCounter}
                      showCharacterCount={showCounter}
                      aria-label={valueLabel}
                      value={condition.value}
                      error={conditionErrors[index]}
                      maxLength={maxLength}
                      disabled={locked}
                      onChange={(event) => updateCondition(index, { value: event.target.value })}
                    />
                  </div>
                  <div className={`${styles.conditionCell} ${styles.conditionToggle}`}>
                    <label htmlFor={`${fieldId}-case-${index}`}>{t("rework.platformAccess.rule.caseSensitive")}</label>
                    <Switch
                      id={`${fieldId}-case-${index}`}
                      size="small"
                      checked={condition.case_sensitive ?? false}
                      disabled={locked}
                      aria-label={t("rework.platformAccess.rule.caseSensitiveCondition", { number: index + 1 })}
                      onChange={(event) => updateCondition(index, { case_sensitive: event.target.checked })}
                    />
                  </div>
                  <Tooltip text={t("rework.platformAccess.rule.removeConditionNumber", { number: index + 1 })}>
                    <IconButton
                      color="on-surface-retreat"
                      variant="icon"
                      size="small"
                      icon={{ category: "outlined", type: "delete" }}
                      disabled={locked}
                      aria-label={t("rework.platformAccess.rule.removeConditionNumber", { number: index + 1 })}
                      onClick={() => edit({ ...draft, conditions: draft.conditions.filter((_, i) => i !== index) })}
                    />
                  </Tooltip>
                </div>
                {condition.operator === "regex" && <p>{t("rework.platformAccess.rule.regexHint")}</p>}
                {result && <p>{t(`rework.platformAccess.rule.result.${result.conditions[index]}`)}</p>}
              </fieldset>
            );
          })}
        </div>
      )}
      {!draft.conditions.length && <p>{t("rework.platformAccess.rule.empty")}</p>}
      <div className={`${styles.row} ${styles.ruleActions}`}>
        <Button color="primary" variant="outlined" size="small" disabled={locked || !valid} onClick={() => void test()}>
          {t("rework.platformAccess.rule.test")}
        </Button>
        {(dirty || conflict) && (
          <Button
            color="primary"
            variant="outlined"
            size="small"
            disabled={locked}
            onClick={() => void discardAndReload()}
          >
            {t("rework.platformAccess.rule.reload")}
          </Button>
        )}
        <div className={styles.saveGroup}>
          <span className={styles.hint} role="status">
            {dirty ? t("rework.platformAccess.rule.unsaved") : saved ? t("rework.platformAccess.rule.saved") : ""}
          </span>
          <Button
            color="primary"
            variant="filled"
            size="small"
            disabled={locked || !valid || !dirty || conflict}
            onClick={() => void persist()}
          >
            {t(saving ? "rework.platformAccess.rule.saving" : "rework.platformAccess.rule.save")}
          </Button>
        </div>
      </div>
      {feedback && !saved && <p role="status">{feedback}</p>}
      {result && (
        <div className={styles.testResults} role="status">
          <p className={styles.banner} data-outcome={ruleAccepts ? "success" : "error"}>
            <Icon category="outlined" type={ruleAccepts ? "check_circle" : "error"} />
            <span>
              {t(
                ruleUnchecked
                  ? "rework.platformAccess.rule.ruleUnchecked"
                  : blocking
                    ? result.matched
                      ? "rework.platformAccess.rule.ruleBlocks"
                      : "rework.platformAccess.rule.ruleDoesNotBlock"
                    : result.matched
                      ? "rework.platformAccess.rule.ruleAccepts"
                      : "rework.platformAccess.rule.ruleRejects",
              )}
            </span>
          </p>
          <p className={styles.banner} data-outcome={result.admitted ? "success" : "error"}>
            <Icon category="outlined" type={result.admitted ? "check_circle" : "error"} />
            <span>
              {!result.admitted
                ? t("rework.platformAccess.rule.accessLost")
                : accessSources.length
                  ? t("rework.platformAccess.rule.accessKeptBy", { sources: accessSources.join(", ") })
                  : t("rework.platformAccess.rule.accessKept")}
            </span>
          </p>
        </div>
      )}
      {picking !== undefined && (
        <PlatformAccessClaimPicker
          onClose={() => setPicking(undefined)}
          onSelect={(claim) => {
            const index = picking === "add" ? draft.conditions.length : picking;
            if (picking === "add") {
              revealLast.current = true;
              edit({ ...draft, conditions: [...draft.conditions, { ...emptyCondition(), claim }] });
            } else updateCondition(picking, { claim });
            setSelection(index);
            setPicking(undefined);
          }}
        />
      )}
      {selection !== undefined && draft.conditions[selection] && (
        <PlatformAccessValuePrompt
          claim={draft.conditions[selection].claim}
          operator={draft.conditions[selection].operator}
          onSelect={(value) => {
            if (value !== undefined) updateCondition(selection, { value });
            setSelection(undefined);
          }}
        />
      )}
    </section>
  );
}
