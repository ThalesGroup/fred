// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0.

import { useState } from "react";
import { skipToken } from "@reduxjs/toolkit/query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  ConversationTraceTurn,
  TraceModelCall,
  TraceModelSnapshot,
  TraceNormalization,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TraceSseFramePayload } from "./ConversationTraceSse";
import { TRACE_TRANSLATION_PREFIX, TraceMaskedEvidence, canReadTraceArtifact } from "./traceControls";
import TraceJson from "./TraceJson";
import styles from "./ConversationTraces.module.css";

const prefix = TRACE_TRANSLATION_PREFIX + ".model";

function Snapshot({
  label,
  snapshot,
  unavailable,
}: {
  label: string;
  snapshot?: TraceModelSnapshot | null;
  unavailable: string;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  return (
    <section className={styles.httpPayload} aria-label={label}>
      <h4>{label}</h4>
      {snapshot ? (
        <>
          {snapshot.partial && <p>{t("partialSnapshot")}</p>}
          <TraceJson
            label={label}
            code={JSON.stringify(
              { messages: snapshot.messages, ...(snapshot.tools?.length ? { tools: snapshot.tools } : {}) },
              null,
              2,
            )}
          />
        </>
      ) : (
        <p>{unavailable}</p>
      )}
    </section>
  );
}

function Normalization({
  sessionId,
  exchangeId,
  attempt,
  number,
}: {
  sessionId: string;
  exchangeId: string;
  attempt: TraceNormalization;
  number: number;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const [frameIndex, setFrameIndex] = useState<number>();
  return (
    <div className={styles.normalizationDetails}>
      <p>{t("normalizationAttempt", { number, status: t("normalization." + attempt.status) })}</p>
      {attempt.partial && <p>{t("partialNormalization")}</p>}
      {attempt.rewrites.length > 0 && (
        <details>
          <summary>{t("rewrites", { count: attempt.rewrites.length })}</summary>
          <TraceJson label={t("rewritesLabel")} code={JSON.stringify(attempt.rewrites, null, 2)} />
          <div className={styles.httpAttemptButtons}>
            {Array.from(
              new Set(
                attempt.rewrites.flatMap((rewrite) => (rewrite.frame_index == null ? [] : [rewrite.frame_index])),
              ),
            ).map((index) => (
              <Button
                key={index}
                type="button"
                size="2xs"
                variant="text"
                color="on-surface"
                aria-pressed={frameIndex === index}
                onClick={() => setFrameIndex(frameIndex === index ? undefined : index)}
              >
                {t("originalFragment", { number: index + 1 })}
              </Button>
            ))}
          </div>
          {frameIndex != null && (
            <TraceSseFramePayload
              key={frameIndex}
              sessionId={sessionId}
              exchangeId={exchangeId}
              refId={attempt.attempt_ref}
              index={frameIndex}
              shared
              stored
            />
          )}
        </details>
      )}
    </div>
  );
}

export function ConversationTraceModel({
  sessionId,
  turn,
  model,
  cutoffRank,
}: {
  sessionId: string;
  turn: ConversationTraceTurn;
  model?: TraceModelCall;
  cutoffRank?: number;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const canRead = model != null && canReadTraceArtifact(turn, cutoffRank, model.observed_through_rank);
  const query = enhancedControlPlaneApi.useGetConversationTraceModelEvidenceQuery(
    canRead && model.completeness !== "unavailable"
      ? { sessionId, exchangeId: turn.exchange_id, ref: model.ref }
      : skipToken,
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  if (!model || (canRead && model.completeness === "unavailable") || query.isError) return <p>{t("unavailable")}</p>;
  if (!canRead) return <TraceMaskedEvidence message={t("masked")} />;
  const evidence = query.currentData;
  if (!evidence || query.isFetching) return <p role="status">{t("loading")}</p>;
  return (
    <div className={styles.httpContent}>
      <section aria-label={t("normalizationTitle")} className={styles.httpPayload}>
        <h4>{t("normalizationTitle")}</h4>
        {evidence.normalization?.length ? (
          evidence.normalization.map((attempt, index) => (
            <Normalization
              key={attempt.attempt_ref}
              sessionId={sessionId}
              exchangeId={turn.exchange_id}
              attempt={attempt}
              number={index + 1}
            />
          ))
        ) : (
          <p>{t("normalization.unavailable")}</p>
        )}
        {!!evidence.origins?.length && (
          <ul>
            {evidence.origins.map((origin) => (
              <li key={origin.exchange_id + origin.call_id}>
                <Link
                  className={styles.back}
                  preventScrollReset
                  to={{
                    search: new URLSearchParams({
                      turn: origin.exchange_id,
                      rank: String(origin.history_rank),
                      call: origin.call_id,
                      view: "langchain",
                    }).toString(),
                  }}
                >
                  {origin.turn_number != null ? t("originTurn", { number: origin.turn_number }) : t("originCall")}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <Snapshot label={t("input")} snapshot={evidence.input} unavailable={t("inputUnavailable")} />
      <Snapshot
        label={t(evidence.output_state === "partial" ? "partialOutput" : "output")}
        snapshot={evidence.output}
        unavailable={t(evidence.output_state === "absent" ? "noOutput" : "outputUnavailable")}
      />
      {!!evidence.matched_results?.length && (
        <section className={styles.httpPayload} aria-label={t("matchedResults")}>
          <h4>{t("matchedResults")}</h4>
          <TraceJson code={JSON.stringify(evidence.matched_results, null, 2)} label={t("matchedResults")} />
        </section>
      )}
    </div>
  );
}
