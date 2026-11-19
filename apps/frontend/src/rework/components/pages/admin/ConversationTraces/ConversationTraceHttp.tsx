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

import { skipToken } from "@reduxjs/toolkit/query";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip";
import { CodeBlock } from "@shared/molecules/CodeBlock/CodeBlock";
import type {
  ConversationTraceTurn,
  TraceHttpAttempt,
  TraceHttpBody,
  TraceModelCall,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  TRACE_TRANSLATION_PREFIX,
  TraceEvidenceTabs,
  TraceFact,
  TraceIdentifier,
  TraceMaskedEvidence,
  canReadTraceArtifact,
  downloadTraceBytes,
  traceElapsedFormatter,
  traceBytes,
} from "./traceControls";
import { ConversationTraceModel } from "./ConversationTraceModel";
import { ConversationTraceSse } from "./ConversationTraceSse";
import { formatTraceJson } from "./formatTraceJson";
import TraceJson from "./TraceJson";
import styles from "./ConversationTraces.module.css";

const prefix = `${TRACE_TRANSLATION_PREFIX}.http`;
const previewBytes = 4 * 1024 * 1024;

async function previewText(data: string, encoding: string | undefined): Promise<string> {
  const bytes = traceBytes(data);
  const decoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
  if (!encoding || encoding === "identity" || bytes.length === 0) {
    return decoder.decode(bytes);
  }
  if (encoding !== "gzip" && encoding !== "deflate") {
    throw new Error("Unsupported content encoding");
  }
  const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream(encoding)).getReader();
  let length = 0;
  let text = "";
  try {
    while (true) {
      const result = await reader.read();
      if (result.done) return text + decoder.decode();
      length += result.value.byteLength;
      if (length > previewBytes) throw new Error("Body preview exceeds the display limit");
      text += decoder.decode(result.value, { stream: true });
    }
  } finally {
    await reader.cancel();
  }
}

function BodyPayload({ body, label, encoding }: { body: TraceHttpBody; label: string; encoding?: string }) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const [text, setText] = useState<string | null>();
  useEffect(() => {
    let current = true;
    void previewText(body.data, encoding).then(
      (value) => {
        if (current) setText(value);
      },
      () => {
        if (current) setText(null);
      },
    );
    return () => {
      current = false;
    };
  }, [body.data, encoding]);

  const json = useMemo(() => (text ? formatTraceJson(text) : undefined), [text]);
  return text === undefined ? (
    <p role="status">{t("loading")}</p>
  ) : text === null ? (
    <p>{t("binaryBody")}</p>
  ) : text.length === 0 ? (
    <p>{t(body.complete ? "emptyBody" : "partialBody")}</p>
  ) : json ? (
    <TraceJson code={json} label={label} copyText={text} />
  ) : (
    <div className={styles.rawBody} tabIndex={0} aria-label={label}>
      <CodeBlock code={text} language="text" highlight={false} />
    </div>
  );
}

function HttpPayload({
  label,
  side,
  remoteTool,
  headers,
  body,
}: {
  label: string;
  side: "request" | "response";
  remoteTool: boolean;
  headers: Record<string, string>;
  body?: TraceHttpBody | null;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  return (
    <section className={styles.httpPayload} aria-label={label}>
      <header>
        <h4>{label}</h4>
        {body && (
          <Button
            type="button"
            size="2xs"
            variant="text"
            color="on-surface"
            onClick={() => downloadTraceBytes(body.data, (remoteTool ? "http-" : "provider-") + side + ".bin")}
          >
            {t("downloadOriginal")}
          </Button>
        )}
      </header>
      {Object.keys(headers).length > 0 && (
        <dl className={styles.httpHeaders} aria-label={t("headers")}>
          {Object.entries(headers).map(([name, value]) => (
            <div key={name}>
              <dt>{name}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {body?.complete === false && body.data.length > 0 && <p>{t("partialBody")}</p>}
      {body ? (
        <BodyPayload body={body} label={label} encoding={headers["content-encoding"]} />
      ) : (
        <p>{t("unavailable")}</p>
      )}
    </section>
  );
}

function useHttpEvidence(
  sessionId: string,
  turn: ConversationTraceTurn,
  attempt: TraceHttpAttempt | undefined,
  cutoffRank: number | undefined,
) {
  const shared = attempt && canReadTraceArtifact(turn, cutoffRank, attempt.observed_through_rank);
  const query = enhancedControlPlaneApi.useGetConversationTraceHttpEvidenceQuery(
    attempt && shared && attempt.completeness !== "unavailable"
      ? { sessionId, exchangeId: turn.exchange_id, ref: attempt.ref }
      : skipToken,
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  if (!attempt) return { status: "unavailable" } as const;
  if (!shared) return { status: "masked" } as const;
  if (query.isError || attempt.completeness === "unavailable") return { status: "unavailable" } as const;
  if (!query.currentData || query.isFetching) return { status: "loading" } as const;
  return { status: "ready", exchange: query.currentData } as const;
}

function HttpEvidence({
  evidence,
  remoteTool = false,
}: {
  evidence: ReturnType<typeof useHttpEvidence>;
  remoteTool?: boolean;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  if (evidence.status === "masked") return <TraceMaskedEvidence message={t("masked")} />;
  if (evidence.status === "loading") return <p role="status">{t("loading")}</p>;
  if (evidence.status !== "ready") return <p>{t("unavailable")}</p>;
  const { exchange } = evidence;
  return (
    <div className={styles.httpContent}>
      {remoteTool && (
        <code className={styles.httpTarget}>
          {exchange.method} {exchange.target}
        </code>
      )}
      <HttpPayload
        label={t(remoteTool ? "toolRequest" : "request")}
        side="request"
        remoteTool={remoteTool}
        headers={exchange.request_headers}
        body={exchange.request_body}
      />
      <HttpPayload
        label={t(remoteTool ? "toolResponse" : "response")}
        side="response"
        remoteTool={remoteTool}
        headers={exchange.response_headers}
        body={exchange.response_body}
      />
    </div>
  );
}

export function TraceHttpStatus({ status }: { status: number | null | undefined }) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  return (
    <Chip
      label={status == null ? t("noStatus") : t("statusBadge", { status })}
      tone={status != null && status >= 400 ? "error" : "default"}
    />
  );
}

export function TraceHttpAttemptSummary({
  attempt,
  turn,
  model,
  provider = false,
}: {
  attempt?: TraceHttpAttempt;
  turn: ConversationTraceTurn;
  model?: TraceModelCall;
  provider?: boolean;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const stage = attempt?.failure_stage;
  const callId = attempt?.call_id ?? model?.call_id;
  return (
    <dl className={styles.callSummary}>
      <TraceFact label={t("failureStage")}>
        {stage ? t(`stage.${stage}`) : attempt ? t("noFailure") : t("unavailable")}
      </TraceFact>
      <TraceFact label={t("execution")}>
        {attempt && (
          <div>
            {provider && attempt.release
              ? t("releaseAttempt", { release: attempt.release, attempt: attempt.attempt })
              : t("attempt", { number: attempt.attempt })}
          </div>
        )}
        {provider && <div>{attempt?.model ?? model?.model ?? t("unavailable")}</div>}
      </TraceFact>
      <TraceFact label={t(provider ? "captureState" : "completeness")}>
        {t(`completenessValue.${attempt?.completeness ?? model?.completeness ?? "unavailable"}`)}
        {provider && <div>{t(`checkpoint.${turn.checkpoint_status ?? "unknown"}`)}</div>}
      </TraceFact>
      {callId && (
        <TraceFact label={t("callId")}>
          <TraceIdentifier label={t("callId")} value={callId} />
        </TraceFact>
      )}
      {turn.trace_id && provider && (
        <TraceFact label={t("traceId")}>
          <TraceIdentifier label={t("traceId")} value={turn.trace_id} />
        </TraceFact>
      )}
      {attempt?.upstream_id && (
        <TraceFact label={t("upstreamId")}>
          <TraceIdentifier label={t("upstreamId")} value={attempt.upstream_id} />
        </TraceFact>
      )}
    </dl>
  );
}

export function TraceHttpAttemptEvidence({
  sessionId,
  turn,
  attempt,
  cutoffRank,
}: {
  sessionId: string;
  turn: ConversationTraceTurn;
  attempt: TraceHttpAttempt;
  cutoffRank?: number;
}) {
  const evidence = useHttpEvidence(sessionId, turn, attempt, cutoffRank);
  return <HttpEvidence evidence={evidence} remoteTool />;
}

export function ConversationTraceModelCall({
  sessionId,
  turn,
  attempt,
  model,
  cutoffRank,
  view,
  onView,
}: {
  sessionId: string;
  turn: ConversationTraceTurn;
  attempt?: TraceHttpAttempt;
  model?: TraceModelCall;
  cutoffRank?: number;
  view: string | null;
  onView: (tab: string) => void;
}) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: prefix });
  const tabs = [
    { key: "http", label: t("exchangeTab") },
    { key: "langchain", label: t("langchainTab") },
    { key: "sse", label: t("sseTab") },
  ];
  const preferred =
    turn.failure_category === "stream_interrupted" || turn.failure_category === "timeout_or_connection"
      ? "sse"
      : attempt
        ? "http"
        : "langchain";
  const tab = tabs.find(({ key }) => key === view)?.key ?? preferred;
  const evidence = useHttpEvidence(sessionId, turn, tab === "http" ? attempt : undefined, cutoffRank);
  return (
    <article className={styles.evidence} aria-label={t("evidenceTitle")}>
      <header className={styles.evidenceHeader}>
        <div>
          <h2>{attempt?.model ?? model?.model ?? t("modelCall")}</h2>
          {evidence.status === "ready" && (
            <p>
              <code className={styles.httpTarget}>
                {evidence.exchange.method} {evidence.exchange.target}
              </code>
            </p>
          )}
        </div>
        {attempt && (
          <div className={styles.chips}>
            <TraceHttpStatus status={attempt.status} />
            <Chip label={traceElapsedFormatter(i18n.language)(attempt.duration_ms)} />
          </div>
        )}
      </header>
      <TraceHttpAttemptSummary attempt={attempt} turn={turn} model={model} provider />
      <TraceEvidenceTabs label={t("evidenceTabs")} tabs={tabs} selected={tab} onSelect={onView} />
      {tab === "sse" ? (
        <ConversationTraceSse sessionId={sessionId} turn={turn} attemptRef={attempt?.ref} cutoffRank={cutoffRank} />
      ) : tab === "langchain" ? (
        <ConversationTraceModel sessionId={sessionId} turn={turn} model={model} cutoffRank={cutoffRank} />
      ) : (
        <HttpEvidence evidence={evidence} />
      )}
    </article>
  );
}
