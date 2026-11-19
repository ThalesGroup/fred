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
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import type {
  ConversationTraceTurn,
  TraceCheckpointStatus,
  TraceHttpAttempt,
  TraceHttpBody,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  TRACE_TRANSLATION_PREFIX,
  TraceIdentifier,
  canReadTraceArtifact,
  downloadTraceBytes,
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
    <pre className={styles.httpText} tabIndex={0} aria-label={label}>
      {text}
    </pre>
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
        <details>
          <summary>{t("headers")}</summary>
          <dl>
            {Object.entries(headers).map(([name, value]) => (
              <div className={styles.httpHeader} key={name}>
                <dt>{name}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </details>
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

function AttemptEvidence({
  sessionId,
  exchangeId,
  attempt,
}: {
  sessionId: string;
  exchangeId: string;
  attempt: TraceHttpAttempt;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const [expanded, setExpanded] = useState(false);
  const evidence = enhancedControlPlaneApi.useGetConversationTraceHttpEvidenceQuery(
    expanded ? { sessionId, exchangeId, ref: attempt.ref } : skipToken,
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  const exchange = evidence.isError ? undefined : evidence.currentData;
  return (
    <>
      <Button
        type="button"
        size="2xs"
        variant="text"
        color="on-surface"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        {t(expanded ? "hide" : "view")}
      </Button>
      {expanded &&
        (evidence.isError ? (
          <p role="alert">{t("unavailable")}</p>
        ) : exchange ? (
          <div className={styles.httpContent}>
            <code className={styles.httpTarget}>
              {exchange.method} {exchange.target}
            </code>
            <HttpPayload
              label={t(attempt.tool_ref != null ? "toolRequest" : "request")}
              side="request"
              remoteTool={attempt.tool_ref != null}
              headers={exchange.request_headers}
              body={exchange.request_body}
            />
            <HttpPayload
              label={t(attempt.tool_ref != null ? "toolResponse" : "response")}
              side="response"
              remoteTool={attempt.tool_ref != null}
              headers={exchange.response_headers}
              body={exchange.response_body}
            />
          </div>
        ) : (
          <p role="status">{t("loading")}</p>
        ))}
    </>
  );
}

export function TraceHttpAttemptSummary({
  active,
  provider = false,
  checkpointStatus,
}: {
  active: TraceHttpAttempt;
  provider?: boolean;
  checkpointStatus?: TraceCheckpointStatus;
}) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: prefix });
  const milliseconds = new Intl.NumberFormat(i18n.language, { style: "unit", unit: "millisecond" });
  return (
    <dl>
      {provider && (
        <>
          <dt>{t("model")}</dt>
          <dd>{active.model ?? t("unavailable")}</dd>
        </>
      )}
      <dt>{t("httpStatus")}</dt>
      <dd>{active.status ?? t("noStatus")}</dd>
      <dt>{t("duration")}</dt>
      <dd>{milliseconds.format(active.duration_ms)}</dd>
      <dt>{t("failureStage")}</dt>
      <dd>{active.failure_stage ? t(`stage.${active.failure_stage}`) : t("noFailure")}</dd>
      {provider && (
        <>
          <dt>{t("release")}</dt>
          <dd>{active.release ?? t("unavailable")}</dd>
          <dt>{t("checkpointStatus")}</dt>
          <dd>{t(`checkpoint.${checkpointStatus ?? "unknown"}`)}</dd>
        </>
      )}
      <dt>{t("completeness")}</dt>
      <dd>{t(`completenessValue.${active.completeness}`)}</dd>
      <dt>{t("callId")}</dt>
      <dd>
        <TraceIdentifier label={t("callId")} value={active.call_id} />
      </dd>
      {active.upstream_id && (
        <>
          <dt>{t("upstreamId")}</dt>
          <dd>
            <TraceIdentifier label={t("upstreamId")} value={active.upstream_id} />
          </dd>
        </>
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
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  if (!canReadTraceArtifact(turn, cutoffRank, attempt.observed_through_rank)) return <p>{t("masked")}</p>;
  if (attempt.completeness === "unavailable") return <p>{t("unavailable")}</p>;
  return <AttemptEvidence key={attempt.ref} sessionId={sessionId} exchangeId={turn.exchange_id} attempt={attempt} />;
}

export function ConversationTraceHttp({
  sessionId,
  turn,
  cutoffRank,
  initialCallId,
}: {
  sessionId: string;
  turn: ConversationTraceTurn;
  cutoffRank?: number;
  initialCallId?: string;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const [selected, setSelected] = useState(initialCallId);
  const [view, setView] = useState(initialCallId ? 1 : 0);
  const metadata = enhancedControlPlaneApi.useListConversationTraceHttpAttemptsQuery(
    turn.availability === "history_only" ? skipToken : { sessionId, exchangeId: turn.exchange_id },
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  const modelMetadata = enhancedControlPlaneApi.useListConversationTraceModelCallsQuery(
    turn.availability === "history_only" ? skipToken : { sessionId, exchangeId: turn.exchange_id },
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  const attempts = metadata.currentData ?? [];
  const models = modelMetadata.currentData ?? [];
  const selectedModel = models.find((model) => model.ref === selected || model.call_id === selected);
  const active =
    attempts.find((attempt) => attempt.ref === selected || attempt.call_id === selectedModel?.call_id) ??
    (selectedModel ? undefined : attempts[0]);
  const activeModel =
    selectedModel ?? models.find((model) => model.call_id === active?.call_id) ?? (active ? undefined : models[0]);
  if (turn.availability === "history_only") return null;
  if (!active && !activeModel) {
    return metadata.isLoading || modelMetadata.isLoading ? null : (
      <ConversationTraceSse sessionId={sessionId} turn={turn} cutoffRank={cutoffRank} />
    );
  }
  const groups = new Map<string, TraceHttpAttempt[]>();
  for (const attempt of attempts) {
    const group = groups.get(attempt.call_id) ?? [];
    group.push(attempt);
    groups.set(attempt.call_id, group);
  }
  return (
    <section className={styles.history} aria-label={t("evidenceTitle")}>
      <h3>{t("evidenceTitle")}</h3>
      <div className={styles.httpAttempts}>
        {Array.from(groups, ([callId, group]) => (
          <div className={styles.httpAttemptGroup} key={callId}>
            <div>{group[0]?.model ?? t("modelCall")}</div>
            <div className={styles.httpAttemptButtons}>
              {group.map((item) => (
                <Button
                  key={item.ref}
                  type="button"
                  size="2xs"
                  variant={item.ref === active?.ref ? "filled" : "outlined"}
                  color={item.ref === active?.ref ? "primary" : "on-surface"}
                  aria-pressed={item.ref === active?.ref}
                  onClick={() => setSelected(item.ref)}
                >
                  {t("attempt", { number: item.attempt })}
                  {" · "}
                  {item.status ?? t("noStatus")}
                </Button>
              ))}
            </div>
          </div>
        ))}
        {models
          .filter((model) => !groups.has(model.call_id))
          .map((model) => (
            <Button
              key={model.ref}
              type="button"
              size="2xs"
              variant={model.ref === activeModel?.ref ? "filled" : "outlined"}
              color={model.ref === activeModel?.ref ? "primary" : "on-surface"}
              aria-pressed={model.ref === activeModel?.ref}
              onClick={() => {
                setSelected(model.ref);
                setView(1);
              }}
            >
              {model.model ?? t("modelCall")}
            </Button>
          ))}
      </div>
      {active && <TraceHttpAttemptSummary active={active} provider checkpointStatus={turn.checkpoint_status} />}
      <ButtonGroup
        items={[{ label: t("exchangeTab") }, { label: t("langchainTab") }, { label: t("sseTab") }]}
        size="2xs"
        color="primary"
        variant="tabs"
        aria-label={t("evidenceTabs")}
        selectedIndex={view}
        onSelectedIndexChange={setView}
      />
      {view === 2 ? (
        <ConversationTraceSse sessionId={sessionId} turn={turn} attemptRef={active?.ref} cutoffRank={cutoffRank} />
      ) : view === 1 ? (
        <ConversationTraceModel sessionId={sessionId} turn={turn} model={activeModel} cutoffRank={cutoffRank} />
      ) : !active ? (
        <p>{t("unavailable")}</p>
      ) : (
        <TraceHttpAttemptEvidence sessionId={sessionId} turn={turn} attempt={active} cutoffRank={cutoffRank} />
      )}
    </section>
  );
}
