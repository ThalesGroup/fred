// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { skipToken } from "@reduxjs/toolkit/query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import {
  useGetTraceIncidentOfferQuery,
  useShareTraceIncidentMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./ManagedChatPage.module.scss";

export function TraceIncidentShare({
  teamId,
  sessionId,
  errorRef,
}: {
  teamId: string;
  sessionId: string;
  errorRef: string;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: "chatbot.traceConsent" });
  const args = { teamId, sessionId, errorRef };
  const [open, setOpen] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const query = useGetTraceIncidentOfferQuery(open ? args : skipToken, { refetchOnMountOrArgChange: true });
  const [share, sharing] = useShareTraceIncidentMutation();
  const offer = query.currentData;
  const ready = offer && !query.isFetching && !query.isError;

  async function confirm() {
    if (!offer || !ready || offer.reported || sharing.isLoading) return;
    setSaveError(false);
    try {
      await share({
        ...args,
        traceConsentRequest: {
          exchange_id: offer.cutoff.exchange_id,
          last_rank: offer.cutoff.last_rank,
          expected_version: offer.consent_version,
        },
      }).unwrap();
      setOpen(false);
    } catch {
      setSaveError(true);
      void query.refetch();
    }
  }

  return (
    <div className={styles.incidentShare}>
      <span>{t("incident.failure")}</span>
      <Button
        color="secondary"
        size="small"
        variant="outlined"
        onClick={() => {
          setSaveError(false);
          setOpen(true);
        }}
      >
        {t("share")}
      </Button>
      {open && (
        <ConfirmationDialog
          open
          title={t("incident.title")}
          message={
            ready
              ? t(offer.capture_available ? "incident.captured" : "incident.historyOnly", {
                  number: offer.cutoff.turn_number,
                })
              : t(query.isError ? "incident.unavailable" : "loading")
          }
          details={
            <>
              <p>
                {t("incident.reference")} <code>{errorRef}</code>
              </p>
              {ready && offer.consent_cutoff && (
                <p>{t("sharedThrough", { number: offer.consent_cutoff.turn_number })}</p>
              )}
              {ready && offer.reported && <p>{t("incident.reported")}</p>}
              {saveError && <p role="alert">{t("incident.saveError")}</p>}
              {query.isError && (
                <Button color="secondary" size="small" variant="text" onClick={() => void query.refetch()}>
                  {t("refresh")}
                </Button>
              )}
            </>
          }
          confirmLabel={t("share")}
          cancelLabel={t("cancel")}
          confirmDisabled={!ready || offer?.reported || sharing.isLoading}
          dismissible={!sharing.isLoading}
          onConfirm={() => void confirm()}
          onCancel={() => {
            if (!sharing.isLoading) setOpen(false);
          }}
        />
      )}
    </div>
  );
}
