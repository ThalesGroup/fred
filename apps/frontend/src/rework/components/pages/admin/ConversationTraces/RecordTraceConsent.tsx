// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextArea from "@shared/atoms/TextArea/TextArea";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import type {
  ConversationTraceDetail,
  TraceHistoryBoundary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useRecordTraceConsentMutation } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { TRACE_TRANSLATION_PREFIX } from "./traceControls";
import styles from "./ConversationTraces.module.css";

export function RecordTraceConsent({
  conversation,
  selectedExchange,
  onConflict,
}: {
  conversation: ConversationTraceDetail;
  selectedExchange?: string;
  onConflict: () => void;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const [exchange, setExchange] = useState<string>();
  const [decision, setDecision] = useState<{ choices: TraceHistoryBoundary[]; version: string | null }>();
  const [note, setNote] = useState("");
  const [error, setError] = useState(false);
  const [recorded, setRecorded] = useState(false);
  const [record, saving] = useRecordTraceConsentMutation();
  const currentCutoff = conversation.consent_cutoff;
  const available = conversation.turns.flatMap(({ retained_cutoff }) =>
    retained_cutoff &&
    (!currentCutoff ||
      retained_cutoff.first_rank > currentCutoff.first_rank ||
      (retained_cutoff.exchange_id === currentCutoff.exchange_id &&
        retained_cutoff.last_rank >= currentCutoff.last_rank))
      ? [retained_cutoff]
      : [],
  );
  const selected = decision?.choices.find(({ exchange_id }) => exchange_id === exchange);

  async function confirm() {
    if (!decision || !selected || error || saving.isLoading || !note.trim()) return;
    setError(false);
    try {
      await record({
        sessionId: conversation.session_id,
        manualTraceConsentRequest: {
          exchange_id: selected.exchange_id,
          last_rank: selected.last_rank,
          expected_version: decision.version,
          source_note: note.trim(),
        },
      }).unwrap();
      setDecision(undefined);
      setNote("");
      setRecorded(true);
    } catch {
      setError(true);
      onConflict();
    }
  }

  return (
    <div>
      <Button
        color="secondary"
        size="small"
        variant="outlined"
        disabled={available.length === 0}
        onClick={() => {
          setRecorded(false);
          setError(false);
          setNote("");
          setDecision({ choices: available, version: conversation.consent_version ?? null });
          setExchange(
            available.find(({ exchange_id }) => exchange_id === selectedExchange)?.exchange_id ??
              available[0]?.exchange_id,
          );
        }}
      >
        {t("manual.action")}
      </Button>
      {recorded && <p role="status">{t("manual.recorded")}</p>}
      {decision && (
        <ConfirmationDialog
          open
          title={t("manual.action")}
          message={t("manual.description")}
          details={
            <div className={styles.recordConsentFields}>
              <label>
                {t("manual.cutoff")}
                <select
                  value={selected?.exchange_id ?? ""}
                  disabled={saving.isLoading}
                  onChange={(event) => setExchange(event.target.value)}
                >
                  {!selected && (
                    <option value="" disabled>
                      {t("manual.chooseCutoff")}
                    </option>
                  )}
                  {decision.choices.map(({ exchange_id, turn_number }) => (
                    <option value={exchange_id} key={exchange_id}>
                      {t("turnNumber", { number: turn_number })}
                    </option>
                  ))}
                </select>
              </label>
              <TextArea
                label={t("manual.source")}
                description={t("manual.sourceHelp")}
                required
                maxLength={2000}
                value={note}
                disabled={saving.isLoading}
                onChange={(event) => setNote(event.target.value)}
              />
              {error && (
                <p className={styles.error} role="alert">
                  {t("manual.error")}
                </p>
              )}
            </div>
          }
          confirmLabel={t("manual.action")}
          cancelLabel={t("manual.cancel")}
          confirmDisabled={!selected || !note.trim() || error || saving.isLoading}
          dismissible={!saving.isLoading}
          onConfirm={() => void confirm()}
          onCancel={() => {
            if (saving.isLoading) return;
            setDecision(undefined);
            setNote("");
          }}
        />
      )}
    </div>
  );
}
