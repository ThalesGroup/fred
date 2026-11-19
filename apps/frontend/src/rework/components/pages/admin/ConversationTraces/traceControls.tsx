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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { useCopyConfirmation } from "@core/hooks/useCopyConfirmation";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import type { TraceOutcome } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ConversationTraces.module.css";

export const TRACE_LIST_PATH = "/admin/conversation-traces";
export const TRACE_TRANSLATION_PREFIX = "rework.admin.conversationTraces";

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

export function useTracePagination() {
  const [pages, setPages] = useState<string[]>([]);
  return {
    cursor: pages.length > 0 ? pages[pages.length - 1] : undefined,
    next: (cursor: string) => setPages((prior) => [...prior, cursor]),
    previous: () => setPages((prior) => prior.slice(0, -1)),
    reset: () => setPages([]),
  };
}

export function TracePageButtons({
  pager,
  nextCursor,
  disabled,
}: {
  pager: ReturnType<typeof useTracePagination>;
  nextCursor: string | null;
  disabled: boolean;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  if (!pager.cursor && !nextCursor) return null;
  return (
    <nav className={styles.pager} aria-label={t("pagination")}>
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

export function TraceOutcomeBadge({ outcome }: { outcome: TraceOutcome }) {
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
