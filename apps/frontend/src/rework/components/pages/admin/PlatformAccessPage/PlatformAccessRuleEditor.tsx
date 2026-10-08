// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Button from "@shared/atoms/Button/Button";
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
  usePlatformAccessClaimsQuery,
  usePreviewPlatformPolicyMutation,
  useSavePlatformPolicyMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformAccessPage.module.css";
import PlatformAccessClaimPicker from "./PlatformAccessClaimPicker";
import PlatformAccessValuePrompt from "./PlatformAccessValuePrompt";
import { isRootAttribute } from "./platformAccessClaims";

const emptyCondition = (): PlatformAccessCondition => ({
  claim: [""],
  operator: "contains",
  value: "",
  case_sensitive: false,
});
const copyPolicy = (policy: PlatformAccessPolicy | null): PlatformAccessPolicy =>
  policy
    ? { ...policy, conditions: policy.conditions.map((condition) => ({ ...condition, claim: [...condition.claim] })) }
    : { combination: "all", conditions: [emptyCondition()] };
const operators: PlatformAccessCondition["operator"][] = ["contains", "not_contains", "equals", "not_equals", "regex"];

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
  const claims = usePlatformAccessClaimsQuery();
  const [preview] = usePreviewPlatformPolicyMutation();
  const [save] = useSavePlatformPolicyMutation();
  const generation = useRef(0);
  const [draft, setDraft] = useState(() => copyPolicy(state.policy));
  const [revision, setRevision] = useState(state.revision);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string>();
  const [conflict, setConflict] = useState(false);
  const [conditionErrors, setConditionErrors] = useState<Record<number, string>>({});
  const [picking, setPicking] = useState<number>();
  const [selection, setSelection] = useState<{ index: number; claim: string[] }>();
  const [result, setResult] = useState<PlatformAccessPolicyPreview>();
  const locked = disabled || busy;
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
    if (!dirty && state.revision >= revision) {
      if (state.revision !== revision) {
        generation.current += 1;
        setResult(undefined);
      }
      setDraft(copyPolicy(state.policy));
      setRevision(state.revision);
    }
  }, [state, dirty, revision]);

  const edit = (policy: PlatformAccessPolicy) => {
    generation.current += 1;
    setDraft(policy);
    setDirty(true);
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
    setFeedback(undefined);
    try {
      const saved = await save({ setPlatformAccessPolicy: { policy: draft, expected_revision: revision } }).unwrap();
      setDraft(copyPolicy(saved.policy));
      setRevision(saved.revision);
      setDirty(false);
      setConflict(false);
      setConditionErrors({});
      setResult(undefined);
      setFeedback(t("rework.platformAccess.rule.saved"));
    } catch (error) {
      reportError(error);
    } finally {
      setBusy(false);
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
    <section className={`${styles.section} ${styles.ruleEditor}`}>
      <h2>{t("rework.platformAccess.rule.title")}</h2>
      <Select
        label={t("rework.platformAccess.rule.mode")}
        size="medium"
        value={draft.mode ?? "allow"}
        disabled={locked}
        options={(["allow", "block"] as const).map((mode) => ({
          key: mode,
          value: mode,
          label: t(`rework.platformAccess.rule.modeLabel.${mode}`),
        }))}
        onChange={(mode) => edit({ ...draft, mode: mode === "block" ? "block" : "allow" })}
      />
      <p>{t("rework.platformAccess.rule.hint")}</p>
      <p className={styles.hint}>{t("rework.platformAccess.rule.delegatedHint")}</p>
      {claims.isError && <p role="alert">{t("rework.platformAccess.rule.claimsFailed")}</p>}
      <div className={styles.row} role="group" aria-label={t("rework.platformAccess.rule.combination")}>
        <span>{t("rework.platformAccess.rule.combination")}</span>
        {(["all", "any"] as const).map((combination) => (
          <Button
            key={combination}
            color="primary"
            variant={(draft.combination ?? "all") === combination ? "filled" : "outlined"}
            size="small"
            disabled={locked}
            aria-pressed={(draft.combination ?? "all") === combination}
            onClick={() => edit({ ...draft, combination })}
          >
            {t(`rework.platformAccess.rule.${combination}`)}
          </Button>
        ))}
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
        return (
          <fieldset className={styles.condition} key={index} disabled={locked}>
            <legend className={styles.screenReaderOnly}>{conditionLabel}</legend>
            <div className={styles.conditionHeader}>
              <span aria-hidden="true">{conditionLabel}</span>
              {draft.conditions.length > 1 && (
                <Tooltip text={t("rework.platformAccess.rule.removeConditionNumber", { number: index + 1 })}>
                  <IconButton
                    variant="icon"
                    size="medium"
                    icon={{ category: "outlined", type: "delete" }}
                    disabled={locked}
                    aria-label={t("rework.platformAccess.rule.removeConditionNumber", { number: index + 1 })}
                    onClick={() => edit({ ...draft, conditions: draft.conditions.filter((_, i) => i !== index) })}
                  />
                </Tooltip>
              )}
            </div>
            <div className={styles.conditionGrid}>
              <Select
                size="small"
                compact
                label={t("rework.platformAccess.rule.accountField")}
                ariaLabel={`${t("rework.platformAccess.rule.accountField")}: ${selectedField}`}
                disabled={locked}
                value={JSON.stringify(condition.claim)}
                placeholder={t("rework.platformAccess.picker.choose")}
                options={[
                  ...(condition.claim.some(Boolean)
                    ? [{ key: "current", value: JSON.stringify(condition.claim), label: selectedField }]
                    : []),
                  ...(claims.data ?? [])
                    .filter(
                      (claim) =>
                        isRootAttribute(claim.path) &&
                        claim.types.includes("string") &&
                        JSON.stringify(claim.path) !== JSON.stringify(condition.claim),
                    )
                    .map((claim) => ({
                      key: JSON.stringify(claim.path),
                      value: JSON.stringify(claim.path),
                      label: claim.path[0],
                    })),
                  { key: "explore", value: "explore", label: t("rework.platformAccess.picker.choose") },
                ]}
                onChange={(value) => {
                  if (value === "explore") setPicking(index);
                  else {
                    const claim = JSON.parse(value) as string[];
                    updateCondition(index, { claim });
                    setSelection({ index, claim });
                  }
                }}
              />
              <Select
                size="small"
                label={t("rework.platformAccess.rule.operator")}
                disabled={locked}
                value={condition.operator}
                options={operators.map((operator) => ({
                  key: operator,
                  value: operator,
                  label: t(`rework.platformAccess.rule.operatorLabel.${operator}`),
                }))}
                onChange={(operator) => updateCondition(index, { operator })}
              />
              <TextInput
                size="small"
                compact={!conditionErrors[index] && !showCounter}
                showCharacterCount={showCounter}
                label={t(
                  condition.operator === "regex"
                    ? "rework.platformAccess.rule.regex"
                    : "rework.platformAccess.rule.value",
                )}
                value={condition.value}
                error={conditionErrors[index]}
                maxLength={maxLength}
                disabled={locked}
                onChange={(event) => updateCondition(index, { value: event.target.value })}
              />
            </div>
            {condition.operator === "regex" && <p>{t("rework.platformAccess.rule.regexHint")}</p>}
            <div className={styles.row}>
              <Switch
                size="small"
                checked={condition.case_sensitive ?? false}
                disabled={locked}
                aria-label={t("rework.platformAccess.rule.caseSensitiveCondition", { number: index + 1 })}
                onChange={(event) => updateCondition(index, { case_sensitive: event.target.checked })}
              />
              <span>{t("rework.platformAccess.rule.caseSensitive")}</span>
            </div>
            {result && <p>{t(`rework.platformAccess.rule.result.${result.conditions[index]}`)}</p>}
          </fieldset>
        );
      })}
      <div className={styles.row}>
        <Button
          color="primary"
          variant="outlined"
          size="medium"
          disabled={locked || draft.conditions.length >= 16}
          onClick={() => edit({ ...draft, conditions: [...draft.conditions, emptyCondition()] })}
        >
          {t("rework.platformAccess.rule.addCondition")}
        </Button>
      </div>
      <div className={`${styles.row} ${styles.ruleActions}`}>
        <Button
          color="primary"
          variant="outlined"
          size="medium"
          disabled={locked || !valid}
          onClick={() => void test()}
        >
          {t("rework.platformAccess.rule.test")}
        </Button>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          disabled={locked || !valid || !dirty || conflict}
          onClick={() => void persist()}
        >
          {t("rework.platformAccess.rule.save")}
        </Button>
        {(dirty || conflict) && (
          <Button
            color="primary"
            variant="outlined"
            size="medium"
            disabled={locked}
            onClick={() => void discardAndReload()}
          >
            {t("rework.platformAccess.rule.reload")}
          </Button>
        )}
      </div>
      {picking !== undefined && draft.conditions[picking] && (
        <PlatformAccessClaimPicker
          observed={claims.data ?? []}
          catalogFailed={claims.isError}
          onClose={() => setPicking(undefined)}
          onSelect={(update) => {
            if (update.claim) {
              updateCondition(picking, { claim: update.claim });
              setSelection({ index: picking, claim: update.claim });
            }
            setPicking(undefined);
          }}
        />
      )}
      {selection && draft.conditions[selection.index] && (
        <PlatformAccessValuePrompt
          claim={selection.claim}
          operator={draft.conditions[selection.index].operator}
          onSelect={(value) => {
            updateCondition(selection.index, { claim: selection.claim, ...(value === undefined ? {} : { value }) });
            setSelection(undefined);
          }}
        />
      )}
      {feedback && <p role="status">{feedback}</p>}
      {result && (
        <div className={styles.testResult} data-outcome={result.admitted ? "allowed" : "denied"} role="status">
          <h3>
            {t(result.admitted ? "rework.platformAccess.rule.testAllowed" : "rework.platformAccess.rule.testDenied")}
          </h3>
          <p>
            {t(
              result.matched ? "rework.platformAccess.rule.ruleMatches" : "rework.platformAccess.rule.ruleDoesNotMatch",
            )}
          </p>
          <p>{t(result.admitted ? "rework.platformAccess.rule.admitted" : "rework.platformAccess.rule.denied")}</p>
        </div>
      )}
    </section>
  );
}
