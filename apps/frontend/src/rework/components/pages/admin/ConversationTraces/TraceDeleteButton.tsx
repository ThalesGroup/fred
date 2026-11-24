// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useConversationTraceAccess } from "@core/hooks/useConversationTraceAccess";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import {
  useDeleteConversationTracesMutation,
  useFlushConversationTraceCapturesMutation,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ConversationTraces.module.css";
import { TRACE_TRANSLATION_PREFIX } from "./traceControls";

type DeleteProps = {
  onDeleted: () => void;
  disabled?: boolean;
} & ({ mode: "flush" } | { mode: "selected"; sessionIds: string[]; single?: boolean });

export function TraceDeleteButton(props: DeleteProps) {
  const { organizationId, canManage } = useConversationTraceAccess();
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const [target, setTarget] = useState<string[] | null>(null);
  const [error, setError] = useState(false);
  const [remove, removing] = useDeleteConversationTracesMutation();
  const [flush, flushing] = useFlushConversationTraceCapturesMutation();
  const busy = removing.isLoading || flushing.isLoading;
  const isFlush = props.mode === "flush";
  const ids = props.mode === "selected" ? props.sessionIds : [];
  const label = t(isFlush ? "flushCaptures" : props.single ? "deleteDiagnostics" : "deleteSelected");

  function close() {
    if (!busy) setTarget(null);
  }

  async function confirm() {
    if (target === null || busy) return;
    setError(false);
    try {
      if (isFlush) {
        await flush({ organizationId }).unwrap();
      } else {
        await remove({ organizationId, deleteConversationTracesRequest: { session_ids: target } }).unwrap();
      }
    } catch {
      setError(true);
      return;
    }
    setTarget(null);
    props.onDeleted();
  }

  if (!canManage) return null;

  return (
    <>
      <Button
        type="button"
        color="error"
        size="small"
        variant="outlined"
        icon={{ category: "outlined", type: "delete" }}
        disabled={props.disabled || (!isFlush && ids.length === 0)}
        onClick={() => {
          setError(false);
          setTarget(ids);
        }}
      >
        {isFlush || props.single ? label : t("deleteShort")}
      </Button>
      <ConfirmationDialog
        open={target !== null}
        title={t(isFlush ? "flushTitle" : "deleteTitle")}
        message={
          isFlush
            ? t("flushHelp")
            : t(target?.length === 1 ? "deleteOneHelp" : "deleteSelectedHelp", {
                id: target?.[0],
                count: target?.length ?? 0,
              })
        }
        details={
          error ? (
            <p role="alert" className={styles.error}>
              {t(isFlush ? "flushError" : "deleteError")}
            </p>
          ) : undefined
        }
        confirmLabel={label}
        cancelLabel={t("cancel")}
        criticalAction
        confirmDisabled={busy}
        dismissible={!busy}
        onConfirm={() => void confirm()}
        onCancel={close}
      />
    </>
  );
}
