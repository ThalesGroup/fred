// SPDX-License-Identifier: Apache-2.0
import { type ComponentProps, type ReactNode, type Ref, useId } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Switch from "@shared/atoms/Switch/Switch";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import Select from "@shared/molecules/Select/Select";
import type { PlatformAccessCondition } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ClaimConditionList.module.css";

export const CLAIM_OPERATORS: PlatformAccessCondition["operator"][] = [
  "contains",
  "not_contains",
  "equals",
  "not_equals",
  "regex",
];

/** A claim path as shown everywhere: the key alone, or each key quoted and joined. */
export function claimLabel(claim: string[]): string {
  return claim.length === 1 ? claim[0] : claim.map((key) => JSON.stringify(key)).join(" > ");
}

/** The highlighted claim path used by the field button and the claim dialogs. */
export function ClaimFieldName(props: ComponentProps<"code">) {
  return <code {...props} className={styles.fieldName} />;
}

interface ClaimConditionListProps {
  conditions: PlatformAccessCondition[];
  disabled?: boolean;
  /** A validation message per condition index. */
  errors?: Record<number, string>;
  onChange: (index: number, update: Partial<PlatformAccessCondition>) => void;
  onRemove: (index: number) => void;
  /** Opens the caller's field picker for this condition. */
  onPickField: (index: number) => void;
  /** Extra lines inside a condition block, such as its test result. */
  renderNote?: (index: number) => ReactNode;
  listRef?: Ref<HTMLDivElement>;
}

/** Condition rows on account claims (field, operator, value, case), shared by the access rule and the analytics user filter. */
export default function ClaimConditionList({
  conditions,
  disabled = false,
  errors = {},
  onChange,
  onRemove,
  onPickField,
  renderNote,
  listRef,
}: ClaimConditionListProps) {
  const { t } = useTranslation();
  const fieldId = useId();
  if (conditions.length === 0) return null;

  return (
    <div className={styles.conditions} ref={listRef}>
      {/* Visual column headings only: each control carries its own accessible name. */}
      <div className={`${styles.conditionRow} ${styles.conditionLabels}`} aria-hidden="true">
        <span />
        <span>{t("rework.platformAccess.rule.accountField")}</span>
        <span>{t("rework.platformAccess.rule.operator")}</span>
        <span>{t("rework.platformAccess.rule.value")}</span>
        <span>{t("rework.platformAccess.rule.caseSensitive")}</span>
        <span />
      </div>
      {conditions.map((condition, index) => {
        const selectedField = condition.claim.some(Boolean)
          ? claimLabel(condition.claim)
          : t("rework.platformAccess.picker.choose");
        const maxLength = condition.operator === "regex" ? 2048 : 1024;
        const showCounter = condition.value.length >= maxLength * 0.9;
        const conditionLabel = t("rework.platformAccess.rule.condition", { number: index + 1 });
        const valueLabel = t(
          condition.operator === "regex" ? "rework.platformAccess.rule.regex" : "rework.platformAccess.rule.value",
        );
        return (
          <fieldset className={styles.condition} key={index} disabled={disabled}>
            <legend className={styles.screenReaderOnly}>{conditionLabel}</legend>
            <div className={styles.conditionRow}>
              <span className={styles.conditionNumber} aria-hidden="true">
                {index + 1}
              </span>
              <div className={styles.conditionCell}>
                <span aria-hidden="true">{t("rework.platformAccess.rule.accountField")}</span>
                <button
                  type="button"
                  disabled={disabled}
                  className={styles.fieldChoice}
                  aria-label={`${t("rework.platformAccess.rule.accountField")}: ${selectedField}`}
                  aria-haspopup="dialog"
                  onClick={() => onPickField(index)}
                >
                  <ClaimFieldName title={selectedField}>{selectedField}</ClaimFieldName>
                  <Icon category="outlined" type="edit" />
                </button>
              </div>
              <div className={styles.conditionCell}>
                <span aria-hidden="true">{t("rework.platformAccess.rule.operator")}</span>
                <Select
                  compact
                  size="xs"
                  ariaLabel={t("rework.platformAccess.rule.operator")}
                  disabled={disabled}
                  value={condition.operator}
                  options={CLAIM_OPERATORS.map((operator) => ({
                    key: operator,
                    value: operator,
                    label: t(`rework.platformAccess.rule.operatorLabel.${operator}`),
                  }))}
                  onChange={(operator) => onChange(index, { operator })}
                />
              </div>
              <div className={styles.conditionCell}>
                <span aria-hidden="true">{valueLabel}</span>
                <TextInput
                  size="xs"
                  compact={!errors[index] && !showCounter}
                  showCharacterCount={showCounter}
                  aria-label={valueLabel}
                  value={condition.value}
                  error={errors[index]}
                  maxLength={maxLength}
                  disabled={disabled}
                  onChange={(event) => onChange(index, { value: event.target.value })}
                />
              </div>
              <div className={`${styles.conditionCell} ${styles.conditionToggle}`}>
                <label htmlFor={`${fieldId}-case-${index}`}>{t("rework.platformAccess.rule.caseSensitive")}</label>
                <Switch
                  id={`${fieldId}-case-${index}`}
                  size="small"
                  checked={condition.case_sensitive ?? false}
                  disabled={disabled}
                  aria-label={t("rework.platformAccess.rule.caseSensitiveCondition", { number: index + 1 })}
                  onChange={(event) => onChange(index, { case_sensitive: event.target.checked })}
                />
              </div>
              <Tooltip text={t("rework.platformAccess.rule.removeConditionNumber", { number: index + 1 })}>
                <IconButton
                  color="on-surface-retreat"
                  variant="icon"
                  size="small"
                  icon={{ category: "outlined", type: "delete" }}
                  disabled={disabled}
                  aria-label={t("rework.platformAccess.rule.removeConditionNumber", { number: index + 1 })}
                  onClick={() => onRemove(index)}
                />
              </Tooltip>
            </div>
            {condition.operator === "regex" && <p>{t("rework.platformAccess.rule.regexHint")}</p>}
            {renderNote?.(index)}
          </fieldset>
        );
      })}
    </div>
  );
}
