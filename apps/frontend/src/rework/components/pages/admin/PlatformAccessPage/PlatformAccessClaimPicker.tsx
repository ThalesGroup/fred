// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import type {
  PlatformAccessClaim,
  PlatformAccessCondition,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { usePlatformAccessOwnClaimsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformAccessClaimPicker.module.css";

const TOKEN_METADATA = new Set([
  "iss",
  "sub",
  "aud",
  "typ",
  "azp",
  "sid",
  "acr",
  "amr",
  "jti",
  "nonce",
  "scope",
  "exp",
  "iat",
  "nbf",
  "auth_time",
  "at_hash",
  "c_hash",
  "s_hash",
  "cnf",
  "act",
  "may_act",
  "client_id",
  "session_state",
  "allowed-origins",
]);
const isRootAttribute = (path: string[]) => path.length === 1 && !TOKEN_METADATA.has(path[0]);

export default function PlatformAccessClaimPicker({
  condition,
  observed,
  catalogFailed,
  onSelect,
  onClose,
}: {
  condition: PlatformAccessCondition;
  observed: PlatformAccessClaim[];
  catalogFailed: boolean;
  onSelect: (update: Partial<PlatformAccessCondition>) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const own = usePlatformAccessOwnClaimsQuery(undefined, { refetchOnMountOrArgChange: true });
  const [source, setSource] = useState<"own" | "observed">("own");
  const [advanced, setAdvanced] = useState(false);
  const [search, setSearch] = useState("");
  const [path, setPath] = useState<string[]>();
  const [copied, setCopied] = useState<string>();
  const facts = !own.isFetching && !own.isError ? own.data : undefined;
  const selectable = new Set((facts?.selectable_paths ?? []).map((part) => JSON.stringify(part)));
  const select = (next: string[]) => {
    setPath(next);
    setCopied(undefined);
  };
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
  const observedFields = observed.filter(
    (claim) => (advanced || (isRootAttribute(claim.path) && claim.types.includes("string"))) && matches(claim.path),
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
          onClick={() => select(next)}
        >
          {JSON.stringify(key)}
        </button>
        <span>: </span>
        <span className={styles.claimValue}>{JSON.stringify(value)}</span>
        {!supported && <span className={styles.explanation}>{t("rework.platformAccess.picker.unsupported")}</span>}
      </div>
    );
  };
  let current: unknown = facts?.claims;
  for (const key of path ?? [])
    current =
      current && typeof current === "object" && Object.prototype.hasOwnProperty.call(current, key)
        ? (current as Record<string, unknown>)[key]
        : undefined;
  const examples =
    source === "own" && path && selectable.has(JSON.stringify(path))
      ? typeof current === "string"
        ? [current]
        : Array.isArray(current)
          ? current.filter((value): value is string => typeof value === "string")
          : []
      : [];
  const copy = (value: string) =>
    setCopied(condition.operator === "regex" ? value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") : value);
  return (
    <Dialog
      open
      title={t("rework.platformAccess.picker.title")}
      maxWidth={900}
      confirmLabel={t("rework.platformAccess.picker.useField")}
      cancelLabel={t("common.cancel")}
      confirmDisabled={!path || (source === "own" && !selectable.has(JSON.stringify(path)))}
      onCancel={onClose}
      onConfirm={() => {
        if (path) onSelect({ claim: path, ...(copied === undefined ? {} : { value: copied }) });
      }}
    >
      <div className={styles.content}>
        <div className={styles.sources}>
          {(["own", "observed"] as const).map((tab) => (
            <Button
              key={tab}
              color="primary"
              variant={source === tab ? "filled" : "outlined"}
              size="medium"
              aria-pressed={source === tab}
              onClick={() => {
                setSource(tab);
                setPath(undefined);
                setCopied(undefined);
              }}
            >
              {t(`rework.platformAccess.picker.${tab}`)}
            </Button>
          ))}
        </div>
        <p>{t(`rework.platformAccess.picker.${source}${advanced ? "Advanced" : ""}Hint`)}</p>
        <div>
          <Button
            color="primary"
            variant="outlined"
            size="small"
            aria-expanded={advanced}
            onClick={() => {
              setAdvanced(!advanced);
              setPath(undefined);
              setCopied(undefined);
            }}
          >
            {t(`rework.platformAccess.picker.${advanced ? "simpleFields" : "advancedFields"}`)}
          </Button>
        </div>
        <TextInput
          label={t("rework.platformAccess.picker.search")}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        {source === "own" ? (
          <>
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
                <div className={styles.json}>
                  {advanced && "{"}
                  <div className={styles.children}>{ownFields.map(([key, value]) => tree(value, [key], key))}</div>
                  {advanced && "}"}
                </div>
                {!ownFields.length && <p>{t(`rework.platformAccess.picker.${advanced ? "empty" : "simpleEmpty"}`)}</p>}
              </>
            )}
          </>
        ) : (
          <>
            {catalogFailed && <p role="alert">{t("rework.platformAccess.rule.claimsFailed")}</p>}
            <div className={styles.catalog}>
              {observedFields.map((claim) => (
                <button
                  type="button"
                  className={styles.key}
                  key={JSON.stringify(claim.path)}
                  aria-pressed={JSON.stringify(path) === JSON.stringify(claim.path)}
                  onClick={() => select(claim.path)}
                >
                  {claim.path.map((key) => JSON.stringify(key)).join(" > ")}{" "}
                  <span className={styles.explanation}>
                    {claim.types.map((type) => t(`rework.platformAccess.rule.type.${type}`)).join(", ")}
                  </span>
                </button>
              ))}
            </div>
            {!observedFields.length && <p>{t(`rework.platformAccess.picker.${advanced ? "empty" : "simpleEmpty"}`)}</p>}
          </>
        )}
        {path && (
          <div className={styles.selection}>
            <p>
              {t("rework.platformAccess.picker.selected")}:{" "}
              <strong>{path.map((key) => JSON.stringify(key)).join(" > ")}</strong>
            </p>
            {!!examples.length && (
              <>
                <p>{t("rework.platformAccess.picker.copyHint")}</p>
                <div className={styles.sources}>
                  {examples.map((value, index) => (
                    <Button key={index} color="primary" variant="outlined" size="small" onClick={() => copy(value)}>
                      <span className={styles.claimValue}>{JSON.stringify(value)}</span>
                    </Button>
                  ))}
                </div>
              </>
            )}
            {copied !== undefined && (
              <p role="status">
                {t("rework.platformAccess.picker.copied")}: <span className={styles.claimValue}>{copied}</span>
              </p>
            )}
          </div>
        )}
      </div>
    </Dialog>
  );
}
