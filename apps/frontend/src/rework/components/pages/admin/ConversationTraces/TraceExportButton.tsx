// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { handlePlatformAccessResponse } from "../../../../../common/platformAccess";
import { KeyCloakService } from "../../../../../security/KeycloakService";
import type {
  ExportConversationTracesApiResponse,
  ExportConversationTracesRequest,
  TraceExportMode,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { downloadFile, filenameFromDisposition } from "../../../../../utils/downloadUtils";
import styles from "./ConversationTraces.module.css";
import { TRACE_TRANSLATION_PREFIX } from "./traceControls";

const modes = ["masked_content", "shared_content"] as const satisfies readonly TraceExportMode[];
type ExportMode = (typeof modes)[number];

function errorMessage(status: number) {
  switch (status) {
    case 404:
    case 409:
      return "exportChanged";
    case 413:
      return "exportTooLarge";
    case 429:
      return "exportBusy";
    default:
      return "exportError";
  }
}

export function TraceExportButton({
  sessionIds,
  hasSharedContent,
  single,
  disabled,
}: {
  sessionIds: string[];
  hasSharedContent: boolean;
  single?: boolean;
  disabled?: boolean;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const optionHelpId = useId();
  const [targets, setTargets] = useState<{ sessionIds: string[]; canExportFull: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ReturnType<typeof errorMessage>>();

  async function startExport(mode: ExportMode) {
    if (busy || !targets || (mode === "shared_content" && !targets.canExportFull)) return;
    setBusy(true);
    setError(undefined);
    try {
      const request: ExportConversationTracesRequest = { session_ids: targets.sessionIds, mode };
      // Binary downloads use a Blob outside the RTK Query cache.
      const response = await fetch("/control-plane/v1/admin/conversation-traces/export", {
        method: "POST",
        headers: {
          Authorization: "Bearer " + (KeyCloakService.GetToken() ?? ""),
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
      });
      await handlePlatformAccessResponse(response);
      if (!response.ok) {
        setError(errorMessage(response.status));
        return;
      }
      const blob: ExportConversationTracesApiResponse = await response.blob();
      const filename =
        filenameFromDisposition(response.headers.get("Content-Disposition")) ?? "conversation-traces.zip";
      downloadFile(blob, filename);
      setTargets(null);
    } catch {
      setError("exportError");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        type="button"
        color="on-surface"
        size="small"
        variant="outlined"
        icon={single ? undefined : { category: "outlined", type: "download" }}
        disabled={disabled || !sessionIds.length}
        onClick={() => {
          setError(undefined);
          setTargets({ sessionIds, canExportFull: sessionIds.length > 1 || hasSharedContent });
        }}
      >
        {t("exportShort")}
      </Button>
      <Dialog
        open={targets !== null}
        title={t("exportTitle")}
        initialFocus="dialog"
        hideConfirm
        hideCancel={busy}
        confirmLabel=""
        onConfirm={() => {}}
        cancelLabel={t("cancel")}
        dismissible={!busy}
        onCancel={() => {
          if (!busy) setTargets(null);
        }}
      >
        <p>{t("exportHelp", { count: targets?.sessionIds.length ?? 0 })}</p>
        <div className={styles.exportOptions}>
          {modes.map((mode) => {
            const blocked = mode === "shared_content" && !targets?.canExportFull;
            const helpId = optionHelpId + "-" + mode;
            return (
              <div className={styles.exportOption} key={mode}>
                <Button
                  type="button"
                  size="small"
                  variant="outlined"
                  color="on-surface"
                  disabled={busy || blocked}
                  aria-describedby={helpId}
                  onClick={() => void startExport(mode)}
                >
                  {t(`exportMode.${mode}.label`)}
                </Button>
                <p id={helpId} className={styles.help}>
                  {t(blocked ? "exportFullUnavailable" : `exportMode.${mode}.help`)}
                </p>
              </div>
            );
          })}
        </div>
        {error && (
          <p className={styles.error} role="alert">
            {t(error)}
          </p>
        )}
        {busy && <p role="status">{t("exportPreparing")}</p>}
      </Dialog>
    </>
  );
}
