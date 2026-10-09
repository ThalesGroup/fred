// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { usePlatformAccessOwnClaimsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformAccessClaimPicker.module.css";
import pageStyles from "./PlatformAccessPage.module.css";

import { isRootAttribute } from "./platformAccessClaims";

export default function PlatformAccessClaimPicker({
  onSelect,
  onClose,
}: {
  onSelect: (claim: string[]) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const own = usePlatformAccessOwnClaimsQuery(undefined, { refetchOnMountOrArgChange: true });
  const [advanced, setAdvanced] = useState(false);
  const [search, setSearch] = useState("");
  const [path, setPath] = useState<string[]>();
  const selectedField = path?.length === 1 ? path[0] : path?.map((key) => JSON.stringify(key)).join(" > ");
  const facts = !own.isFetching && !own.isError ? own.data : undefined;
  const selectable = new Set((facts?.selectable_paths ?? []).map((part) => JSON.stringify(part)));
  const matches = (next: string[]) => next.join(" > ").toLocaleLowerCase().includes(search.toLocaleLowerCase());
  const hasMatch = (value: unknown, next: string[]): boolean =>
    matches(next) ||
    (!!value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.entries(value).some(([key, child]) => hasMatch(child, [...next, key])));
  const ownFields = Object.entries(facts?.claims ?? {}).filter(
    ([key, value]) =>
      (advanced || (typeof value === "string" && isRootAttribute([key]) && selectable.has(JSON.stringify([key])))) &&
      hasMatch(value, [key]),
  );
  const tree = (value: unknown, next: string[], key: string) => {
    if (!hasMatch(value, next)) return null;
    const identity = JSON.stringify(next);
    if (value && typeof value === "object" && !Array.isArray(value))
      return (
        <details key={identity} open={search ? true : undefined} className={styles.branch}>
          <summary role="button" tabIndex={0}>
            {JSON.stringify(key)}: {"{...}"}
          </summary>
          <div className={styles.children}>
            {Object.entries(value).map(([childKey, child]) => tree(child, [...next, childKey], childKey))}
          </div>
        </details>
      );
    const supported = selectable.has(identity);
    return (
      <div className={styles.leaf} key={identity}>
        <button
          type="button"
          className={styles.key}
          disabled={!supported}
          aria-pressed={JSON.stringify(path) === identity}
          title={
            supported
              ? next.map((part) => JSON.stringify(part)).join(" > ")
              : t("rework.platformAccess.picker.unsupported")
          }
          onClick={() => setPath(next)}
        >
          {JSON.stringify(key)}
        </button>
        <span>: </span>
        <span className={styles.claimValue}>{JSON.stringify(value)}</span>
        {!supported && <span className={styles.explanation}>{t("rework.platformAccess.picker.unsupported")}</span>}
      </div>
    );
  };
  return (
    <Dialog
      open
      title={t("rework.platformAccess.picker.title")}
      maxWidth={900}
      scrollMode="children"
      confirmLabel={t("rework.platformAccess.picker.useField")}
      cancelLabel={t("common.cancel")}
      confirmDisabled={!path || !selectable.has(JSON.stringify(path))}
      onCancel={onClose}
      onConfirm={() => {
        if (path) onSelect(path);
      }}
    >
      <div className={styles.content}>
        <div>
          <Button
            color="primary"
            variant="outlined"
            size="small"
            aria-expanded={advanced}
            onClick={() => {
              setAdvanced(!advanced);
              setPath(undefined);
            }}
          >
            {t(`rework.platformAccess.picker.${advanced ? "simpleFields" : "advancedFields"}`)}
          </Button>
        </div>
        <TextInput
          size="small"
          compact
          label={t("rework.platformAccess.picker.search")}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        {own.isFetching && <p role="status">{t("rework.platformAccess.loading")}</p>}
        {own.isError && (
          <div role="alert">
            <p>{t("rework.platformAccess.picker.failed")}</p>
            <Button color="primary" variant="outlined" size="small" onClick={() => void own.refetch()}>
              {t("rework.platformAccess.retry")}
            </Button>
          </div>
        )}
        {facts && (
          <>
            {facts.truncated && <p role="status">{t("rework.platformAccess.picker.truncated")}</p>}
            <div className={styles.json} role="region" aria-label={t("rework.platformAccess.picker.own")} tabIndex={0}>
              {advanced && "{"}
              <div className={styles.children}>{ownFields.map(([key, value]) => tree(value, [key], key))}</div>
              {advanced && "}"}
            </div>
            {!ownFields.length && <p>{t(`rework.platformAccess.picker.${advanced ? "empty" : "simpleEmpty"}`)}</p>}
          </>
        )}
        <div className={styles.selection}>
          <span>{t("rework.platformAccess.picker.selected")}</span>
          <code className={pageStyles.fieldName} title={selectedField} aria-live="polite" data-empty={!path}>
            {selectedField ?? t("rework.platformAccess.picker.noSelection")}
          </code>
        </div>
      </div>
    </Dialog>
  );
}
