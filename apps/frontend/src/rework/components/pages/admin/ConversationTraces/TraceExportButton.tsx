// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
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

const modes = ["metadata_only", "shared_content"] as const satisfies readonly TraceExportMode[];

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
  single,
  disabled,
}: {
  sessionIds: string[];
  single?: boolean;
  disabled?: boolean;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const optionsName = useId();
  const [targets, setTargets] = useState<string[] | null>(null);
  const [mode, setMode] = useState<TraceExportMode>("metadata_only");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ReturnType<typeof errorMessage>>();

  async function confirm() {
    if (busy || !targets?.length) return;
    setBusy(true);
    setError(undefined);
    try {
      const request: ExportConversationTracesRequest = { session_ids: targets, mode };
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
          setMode("metadata_only");
          setError(undefined);
          setTargets(sessionIds);
        }}
      >
        {t("exportShort")}
      </Button>
      <ConfirmationDialog
        open={targets !== null}
        title={t("exportTitle")}
        message={t("exportHelp", { count: targets?.length ?? 0 })}
        details={
          <>
            <fieldset className={styles.exportOptions} disabled={busy}>
              <legend>{t("exportContents")}</legend>
              {modes.map((option) => (
                <label key={option}>
                  <input type="radio" name={optionsName} checked={mode === option} onChange={() => setMode(option)} />
                  <span>
                    <strong>{t(`exportMode.${option}.label`)}</strong>
                    <span>{t(`exportMode.${option}.help`)}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            {error && (
              <p className={styles.error} role="alert">
                {t(error)}
              </p>
            )}
            {busy && <p role="status">{t("exportPreparing")}</p>}
          </>
        }
        confirmLabel={t("exportDownload")}
        cancelLabel={t("cancel")}
        confirmDisabled={busy}
        dismissible={!busy}
        onConfirm={() => void confirm()}
        onCancel={() => {
          if (!busy) setTargets(null);
        }}
      />
    </>
  );
}
