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

import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, type LinkProps, useLocation } from "react-router-dom";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { useCopyConfirmation } from "@core/hooks/useCopyConfirmation";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import type {
  ConversationTraceTurn,
  TraceFailureCategory,
  TraceOutcome,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ConversationTraces.module.css";

export const TRACE_LIST_PATH = "/admin/conversation-traces";
export const TRACE_TRANSLATION_PREFIX = "rework.admin.conversationTraces";

export function canReadTraceArtifact(
  turn: ConversationTraceTurn,
  cutoffRank: number | undefined,
  observedRank: number | null | undefined,
): boolean {
  return (
    turn.access === "local" ||
    (turn.access === "shared" && cutoffRank != null && observedRank != null && observedRank <= cutoffRank)
  );
}

export function traceBytes(data: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(atob(data), (character) => character.charCodeAt(0));
}

export function downloadTraceBytes(data: string, name: string) {
  const url = URL.createObjectURL(new Blob([traceBytes(data)], { type: "application/octet-stream" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export type TraceInspectorOrigin = {
  listSearch: string;
  listSteps: number;
};

export function traceInspectorOrigin(state: (Partial<TraceInspectorOrigin> & { fromTraceList?: boolean }) | null) {
  if (typeof state?.listSearch === "string" && state.listSteps && state.listSteps > 0) {
    return { listSearch: state.listSearch, listSteps: state.listSteps };
  }
  return state?.fromTraceList === true ? { listSearch: "", listSteps: 1 } : null;
}

export function nextTraceInspectorState(origin: TraceInspectorOrigin | null) {
  return origin && { ...origin, listSteps: origin.listSteps + 1 };
}

export function TraceInspectorLink({
  search,
  ...props
}: Omit<LinkProps, "to" | "state" | "replace"> & { search: string }) {
  const location = useLocation();
  const current = `?${search}`;
  const replace = current === location.search;
  const origin = traceInspectorOrigin(location.state);
  return (
    <Link
      {...props}
      to={{ search: current }}
      replace={replace}
      state={replace ? origin : nextTraceInspectorState(origin)}
      preventScrollReset
    />
  );
}

export function TracePageButtons({
  pager,
  nextCursor,
  disabled,
  label,
}: {
  pager: { cursor: string | undefined; previous: () => void; next: (cursor: string) => void };
  nextCursor: string | null;
  disabled: boolean;
  label?: string;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  if (!pager.cursor && !nextCursor) return null;
  return (
    <nav className={styles.pager} aria-label={label ?? t("pagination")}>
      <Button
        color="secondary"
        size="small"
        variant="outlined"
        onClick={pager.previous}
        disabled={disabled || !pager.cursor}
      >
        {t("previous")}
      </Button>
      <Button
        color="secondary"
        size="small"
        variant="outlined"
        onClick={() => nextCursor && pager.next(nextCursor)}
        disabled={disabled || !nextCursor}
      >
        {t("next")}
      </Button>
    </nav>
  );
}

export function TraceOutcomeBadge({ outcome }: { outcome: TraceOutcome | TraceFailureCategory }) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  return (
    <span className={styles.outcome} data-outcome={outcome}>
      {t(`outcome.${outcome}`)}
    </span>
  );
}

export function TraceIdentifier({ label, value }: { label: string; value: string }) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const { copied, confirmCopied } = useCopyConfirmation();
  const [copyFailed, setCopyFailed] = useState(false);
  return (
    <div className={styles.identifier}>
      <code>{value}</code>
      <IconButton
        size="2xs"
        variant="icon"
        title={copied ? t("copied") : t("copy", { label })}
        aria-label={copied ? t("copied") : t("copy", { label })}
        icon={{ category: "outlined", type: copied ? "check" : "content_copy" }}
        onClick={() => {
          void writeRichClipboard("", value).then((ok) => {
            setCopyFailed(!ok);
            if (ok) confirmCopied();
          });
        }}
      />
      {copyFailed && <span role="alert">{t("copyFailed")}</span>}
    </div>
  );
}

export function traceElapsedFormatter(language: string) {
  const seconds = new Intl.NumberFormat(language, { style: "unit", unit: "second", maximumFractionDigits: 3 });
  const milliseconds = new Intl.NumberFormat(language, {
    style: "unit",
    unit: "millisecond",
    maximumFractionDigits: 0,
  });
  return (ms: number) => (ms >= 1000 ? seconds.format(ms / 1000) : milliseconds.format(ms));
}

export function TraceFact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function TraceEvidenceTabs<T extends string>({
  label,
  tabs,
  selected,
  onSelect,
}: {
  label: string;
  tabs: { key: T; label: string }[];
  selected: T;
  onSelect: (tab: T) => void;
}) {
  return (
    <div className={styles.tabs} role="group" aria-label={label}>
      {tabs.map(({ key, label: text }) => (
        <Button
          key={key}
          type="button"
          size="small"
          color="primary"
          variant={selected === key ? "filled" : "text"}
          aria-pressed={selected === key}
          onClick={() => onSelect(key)}
        >
          {text}
        </Button>
      ))}
    </div>
  );
}

export function TraceMaskedEvidence({ message }: { message: string }) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  return (
    <div className={styles.masked}>
      <Icon category="outlined" type="lock" />
      <div>
        <h3>{t("maskedEvidence")}</h3>
        <p>{message}</p>
      </div>
    </div>
  );
}
