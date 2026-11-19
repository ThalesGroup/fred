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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import type { TraceHistoryBoundary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useGetTraceConsentQuery,
  useRevokeTraceConsentMutation,
  useSetTraceConsentMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./DebugRawDrawer.module.css";

interface TraceConsentControlsProps {
  teamId: string;
  sessionId: string;
  turnPending: boolean;
}

type ConsentDecision =
  | { kind: "share"; cutoff: TraceHistoryBoundary; version: string | null; extending: boolean }
  | { kind: "revoke" };

export function TraceConsentControls({ teamId, sessionId, turnPending }: TraceConsentControlsProps) {
  const { t } = useTranslation(undefined, { keyPrefix: "chatbot.traceConsent" });
  const args = { teamId, sessionId };
  const state = useGetTraceConsentQuery(args, { refetchOnMountOrArgChange: true });
  const [setConsent, setting] = useSetTraceConsentMutation();
  const [revokeConsent, revoking] = useRevokeTraceConsentMutation();
  const [decision, setDecision] = useState<ConsentDecision>();
  const [error, setError] = useState(false);
  const wasPending = useRef(turnPending);
  const refreshConsent = state.refetch;
  useEffect(() => {
    if (wasPending.current && !turnPending) void refreshConsent();
    wasPending.current = turnPending;
  }, [refreshConsent, turnPending]);
  const busy = setting.isLoading || revoking.isLoading;
  const grant = state.currentData?.consent;
  const cutoff = state.currentData?.available_cutoff;
  const canShare =
    cutoff != null &&
    (grant == null ||
      cutoff.first_rank > grant.cutoff.first_rank ||
      (cutoff.exchange_id === grant.cutoff.exchange_id &&
        cutoff.first_rank === grant.cutoff.first_rank &&
        cutoff.last_rank > grant.cutoff.last_rank));

  async function confirm() {
    if (!decision || busy) return;
    setError(false);
    try {
      if (decision.kind === "revoke") {
        await revokeConsent(args).unwrap();
      } else {
        await setConsent({
          ...args,
          traceConsentRequest: {
            exchange_id: decision.cutoff.exchange_id,
            last_rank: decision.cutoff.last_rank,
            expected_version: decision.version,
          },
        }).unwrap();
      }
      setDecision(undefined);
    } catch {
      setError(true);
      void state.refetch();
    }
  }

  return (
    <section className={styles.sharing} aria-label={t("section")}>
      <h2>{t("section")}</h2>
      {state.isLoading ? (
        <p role="status">{t("loading")}</p>
      ) : state.isError ? (
        <p role="alert">{t("loadError")}</p>
      ) : (
        <>
          <p>{t(grant ? "shared" : "notShared")}</p>
          {state.currentData?.history_unavailable && <p>{t("historyUnavailable")}</p>}
          {!grant && !cutoff && !state.currentData?.history_unavailable && <p>{t("noSavedTurns")}</p>}
          <div className={styles.sharingActions}>
            {canShare && (
              <Button
                color="secondary"
                variant="outlined"
                size="small"
                onClick={() => {
                  setError(false);
                  setDecision({
                    kind: "share",
                    cutoff,
                    version: state.currentData?.consent_version ?? null,
                    extending: grant != null,
                  });
                }}
              >
                {t(grant ? "extend" : "share")}
              </Button>
            )}
            {grant && (
              <Button
                color="secondary"
                variant="text"
                size="small"
                onClick={() => {
                  setError(false);
                  setDecision({ kind: "revoke" });
                }}
              >
                {t("revoke")}
              </Button>
            )}
            {state.currentData?.history_unavailable && (
              <Button color="secondary" size="small" variant="text" onClick={() => void state.refetch()}>
                {t("refresh")}
              </Button>
            )}
          </div>
        </>
      )}
      {decision && (
        <ConfirmationDialog
          open
          title={t(decision.kind === "revoke" ? "revokeTitle" : decision.extending ? "extend" : "shareTitle")}
          message={t(decision.kind === "revoke" ? "revokeDescription" : "shareDescription")}
          details={error && <p role="alert">{t("saveError")}</p>}
          confirmLabel={t(decision.kind === "revoke" ? "revoke" : decision.extending ? "extend" : "share")}
          cancelLabel={t("cancel")}
          confirmDisabled={busy || error}
          dismissible={!busy}
          onConfirm={() => void confirm()}
          onCancel={() => {
            if (!busy) setDecision(undefined);
          }}
        />
      )}
    </section>
  );
}
