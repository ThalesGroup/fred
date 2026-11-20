// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { TraceConsentWithdrawalDialog } from "@shared/molecules/DebugRawDrawer/TraceConsentWithdrawalDialog";
import {
  enhancedControlPlaneApi,
  useShareTraceIncidentMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./TraceIncidentShare.module.css";

export function TraceIncidentShare({
  teamId,
  sessionId,
  errorRef,
  turnPending,
}: {
  teamId: string;
  sessionId: string;
  errorRef: string;
  turnPending: boolean;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: "chatbot.traceConsent" });
  const titleId = useId();
  const cardRef = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(typeof IntersectionObserver === "undefined");
  const [withdrawing, setWithdrawing] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const args = { teamId, sessionId, errorRef };
  const incidentEndpoint = enhancedControlPlaneApi.endpoints.getTraceIncidentOffer;
  const query = incidentEndpoint.useQueryState(args);
  const { refetch } = incidentEndpoint.useQuerySubscription(args, {
    skip: turnPending || (!visible && !withdrawing),
    refetchOnMountOrArgChange: 30,
  });
  const [share, sharing] = useShareTraceIncidentMutation();
  const offer = query.currentData;
  const reported = offer?.reported === true && !query.isError;
  const busy = sharing.isLoading || query.isFetching;
  const ready = offer && !busy && !query.isError && !turnPending;

  useEffect(() => {
    const card = cardRef.current;
    if (!card || typeof IntersectionObserver === "undefined") return;
    // Keep history reads bounded to the incident cards the user scrolls to.
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(card);
    return () => observer.disconnect();
  }, []);

  async function shareIncident() {
    if (!offer || !ready || reported) return;
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
    } catch {
      setSaveError(true);
    }
  }

  return (
    <section className={styles.card} ref={cardRef} aria-labelledby={titleId}>
      <h2 id={titleId}>{t(reported ? "incident.thankYou" : "incident.failure")}</h2>
      {!reported && (
        <>
          <p>{t("incident.explanation")}</p>
          <p>{t("incident.description")}</p>
        </>
      )}
      <div role="status">
        {reported
          ? t("incident.shared")
          : sharing.isLoading
            ? t("incident.sharing")
            : !ready && !query.isError && t("loading")}
      </div>
      <p className={styles.reference}>
        {t("incident.reference")} <code>{errorRef}</code>
      </p>
      {!reported && saveError && <p role="alert">{t("incident.saveError")}</p>}
      {query.isError && <p role="alert">{t("incident.unavailable")}</p>}
      <div className={styles.actions}>
        {reported ? (
          <Button
            type="button"
            color="secondary"
            variant="outlined"
            size="small"
            onClick={() => {
              setSaveError(false);
              setWithdrawing(true);
            }}
          >
            {t("revoke")}
          </Button>
        ) : query.isError ? (
          <Button
            type="button"
            color="secondary"
            variant="text"
            size="small"
            aria-disabled={!visible || turnPending}
            onClick={() => {
              if (visible && !turnPending) void refetch();
            }}
          >
            {t("refresh")}
          </Button>
        ) : (
          <Button
            type="button"
            color="primary"
            variant="filled"
            size="medium"
            aria-disabled={!ready}
            disabled={turnPending || sharing.isLoading}
            onClick={() => void shareIncident()}
          >
            {t("share")}
          </Button>
        )}
      </div>
      {withdrawing && (
        <TraceConsentWithdrawalDialog teamId={teamId} sessionId={sessionId} onClose={() => setWithdrawing(false)} />
      )}
    </section>
  );
}
