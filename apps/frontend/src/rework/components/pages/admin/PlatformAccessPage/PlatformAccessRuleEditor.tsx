// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Button from "@shared/atoms/Button/Button";
import Switch from "@shared/atoms/Switch/Switch";
import TextInput from "@shared/atoms/TextInput/TextInput";
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
    <section className={styles.section}>
      <h2>{t("rework.platformAccess.rule.title")}</h2>
      <p>{t("rework.platformAccess.rule.hint")}</p>
      <p>{t("rework.platformAccess.rule.discoveryHint")}</p>
      <p>{t("rework.platformAccess.rule.delegatedHint")}</p>
      {claims.isError && <p role="alert">{t("rework.platformAccess.rule.claimsFailed")}</p>}
      <Select
        size="medium"
        label={t("rework.platformAccess.rule.combination")}
        disabled={locked}
        value={draft.combination ?? "all"}
        options={["all", "any"].map((value) => ({
          key: value,
          value: value as "all" | "any",
          label: t(`rework.platformAccess.rule.${value}`),
        }))}
        onChange={(combination) => edit({ ...draft, combination })}
      />
      {draft.conditions.map((condition, index) => (
        <fieldset className={styles.condition} key={index} disabled={locked}>
          <legend>{t("rework.platformAccess.rule.condition", { number: index + 1 })}</legend>
          <Select
            size="medium"
            label={t("rework.platformAccess.rule.observedClaim")}
            disabled={locked}
            value={JSON.stringify(condition.claim)}
            placeholder={t("rework.platformAccess.rule.selectClaim")}
            options={(claims.data ?? []).map((claim) => ({
              key: JSON.stringify(claim.path),
              value: JSON.stringify(claim.path),
              label: JSON.stringify(claim.path),
              description: claim.types.map((type) => t(`rework.platformAccess.rule.type.${type}`)).join(", "),
            }))}
            onChange={(value) => updateCondition(index, { claim: JSON.parse(value) as string[] })}
          />
          <div className={styles.path}>
            {condition.claim.map((key, segment) => (
              <TextInput
                key={segment}
                label={t("rework.platformAccess.rule.pathKey", { number: segment + 1 })}
                value={key}
                maxLength={256}
                disabled={locked}
                onChange={(event) =>
                  updateCondition(index, {
                    claim: condition.claim.map((part, i) => (i === segment ? event.target.value : part)),
                  })
                }
              />
            ))}
            <Button
              color="primary"
              variant="outlined"
              size="small"
              disabled={locked || condition.claim.length >= 16}
              onClick={() => updateCondition(index, { claim: [...condition.claim, ""] })}
            >
              {t("rework.platformAccess.rule.addKey")}
            </Button>
            <Button
              color="primary"
              variant="outlined"
              size="small"
              disabled={locked || condition.claim.length <= 1}
              onClick={() => updateCondition(index, { claim: condition.claim.slice(0, -1) })}
            >
              {t("rework.platformAccess.rule.removeKey")}
            </Button>
          </div>
          <Select
            size="medium"
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
            label={t(
              condition.operator === "regex" ? "rework.platformAccess.rule.regex" : "rework.platformAccess.rule.value",
            )}
            value={condition.value}
            error={conditionErrors[index]}
            maxLength={condition.operator === "regex" ? 2048 : 1024}
            disabled={locked}
            onChange={(event) => updateCondition(index, { value: event.target.value })}
          />
          {condition.operator === "regex" && <p>{t("rework.platformAccess.rule.regexHint")}</p>}
          <label className={styles.row}>
            <Switch
              checked={condition.case_sensitive ?? false}
              disabled={locked}
              aria-label={t("rework.platformAccess.rule.caseSensitiveCondition", { number: index + 1 })}
              onChange={(event) => updateCondition(index, { case_sensitive: event.target.checked })}
            />
            {t("rework.platformAccess.rule.caseSensitive")}
          </label>
          <Button
            color="primary"
            variant="outlined"
            size="small"
            disabled={locked || draft.conditions.length <= 1}
            onClick={() => edit({ ...draft, conditions: draft.conditions.filter((_, i) => i !== index) })}
          >
            {t("rework.platformAccess.rule.removeCondition")}
          </Button>
          {result && <p>{t(`rework.platformAccess.rule.result.${result.conditions[index]}`)}</p>}
        </fieldset>
      ))}
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
      {feedback && <p role="status">{feedback}</p>}
      {result && (
        <div role="status">
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
