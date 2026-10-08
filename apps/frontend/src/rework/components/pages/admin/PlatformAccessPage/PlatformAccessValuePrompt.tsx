// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./PlatformAccessPage.module.css";
import Select from "@shared/molecules/Select/Select";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import type { PlatformAccessCondition } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { usePlatformAccessOwnClaimsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";

export default function PlatformAccessValuePrompt({
  claim,
  operator,
  onSelect,
}: {
  claim: string[];
  operator: PlatformAccessCondition["operator"];
  onSelect: (value?: string) => void;
}) {
  const { t } = useTranslation();
  const own = usePlatformAccessOwnClaimsQuery(undefined, { refetchOnMountOrArgChange: true });
  const [chosen, setChosen] = useState(0);
  let current: unknown = own.data?.claims;
  for (const key of claim)
    current =
      current && typeof current === "object" && Object.prototype.hasOwnProperty.call(current, key)
        ? (current as Record<string, unknown>)[key]
        : undefined;
  const supported = own.data?.selectable_paths.some((path) => JSON.stringify(path) === JSON.stringify(claim));
  const examples =
    !own.isFetching && !own.isError && supported
      ? typeof current === "string"
        ? [current]
        : Array.isArray(current)
          ? current.filter((value): value is string => typeof value === "string")
          : []
      : [];
  const literal = examples[chosen];
  const value =
    operator === "regex" && literal !== undefined ? literal.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") : literal;
  const limit = operator === "regex" ? 2048 : 1024;
  return (
    <Dialog
      open
      title={t("rework.platformAccess.picker.valueTitle")}
      maxWidth={600}
      confirmLabel={t("rework.platformAccess.picker.useValue")}
      cancelLabel={t("rework.platformAccess.picker.keepValue")}
      confirmDisabled={value === undefined || !value.length || value.length > limit}
      onCancel={() => onSelect()}
      onConfirm={() => {
        if (value !== undefined && value.length > 0 && value.length <= limit) onSelect(value);
      }}
    >
      <div className={styles.dialogBody}>
        <p className={styles.exampleValue}>{claim.map((key) => JSON.stringify(key)).join(" > ")}</p>
        <p>{t("rework.platformAccess.picker.valueHint")}</p>
        {own.isFetching && <p role="status">{t("rework.platformAccess.loading")}</p>}
        {own.isError && <p role="alert">{t("rework.platformAccess.picker.failed")}</p>}
        {!own.isFetching && !own.isError && !examples.length && <p>{t("rework.platformAccess.picker.noValue")}</p>}
        {examples.length > 1 ? (
          <Select
            size="small"
            label={t("rework.platformAccess.rule.value")}
            value={chosen}
            onChange={setChosen}
            options={examples.map((example, index) => ({ key: String(index), value: index, label: example }))}
          />
        ) : (
          examples.length === 1 && <p className={styles.exampleValue}>{examples[0]}</p>
        )}
        {value !== undefined && value.length > limit && (
          <p role="alert">{t("rework.platformAccess.picker.valueTooLong")}</p>
        )}
      </div>
    </Dialog>
  );
}
