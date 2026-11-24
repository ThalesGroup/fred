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

import { useConversationTraceAccess } from "@core/hooks/useConversationTraceAccess";
import { skipToken } from "@reduxjs/toolkit/query";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip";
import Icon from "@shared/atoms/Icon/Icon";
import { CodeBlock } from "@shared/molecules/CodeBlock/CodeBlock";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type {
  ConversationTraceTurn,
  TraceHttpAttempt,
  TraceHttpBody,
  TraceHttpEvidence,
  TraceModelCall,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  TRACE_TRANSLATION_PREFIX,
  TraceEvidenceTabs,
  TraceFact,
  TraceIdentifier,
  TraceMaskedEvidence,
  TracePageButtons,
  canReadTraceArtifact,
  downloadTraceBytes,
  traceElapsedFormatter,
  traceBytes,
} from "./traceControls";
import { ConversationTraceModel } from "./ConversationTraceModel";
import { ConversationTraceSse } from "./ConversationTraceSse";
import { formatTraceJson } from "./formatTraceJson";
import {
  formatTraceHttpReplay,
  prepareTraceHttpReplay,
  traceReplayFormats,
  type ReplayRequest,
} from "./traceHttpReplay";
import TraceJson from "./TraceJson";
import styles from "./ConversationTraces.module.css";

const prefix = `${TRACE_TRANSLATION_PREFIX}.http`;
const previewBytes = 4 * 1024 * 1024;

type HttpSide = "request" | "response";

async function previewText(data: string, encoding: string | undefined, pagedText: boolean): Promise<string> {
  const bytes = traceBytes(data);
  const decoder = new TextDecoder("utf-8", { fatal: !pagedText, ignoreBOM: true });
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

function BodyPayload({
  body,
  label,
  encoding,
  modelRequest,
  pagedText,
}: {
  body: TraceHttpBody;
  label: string;
  encoding?: string;
  modelRequest: boolean;
  pagedText: boolean;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const [text, setText] = useState<string | null>();
  useEffect(() => {
    let current = true;
    void previewText(body.data, encoding, pagedText).then(
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
  }, [body.data, encoding, pagedText]);

  const json = useMemo(() => (text ? formatTraceJson(text) : undefined), [text]);
  return text === undefined ? (
    <p role="status">{t("loading")}</p>
  ) : text === null ? (
    <p>{t("binaryBody")}</p>
  ) : text.length === 0 ? (
    <p>{t(body.complete ? "emptyBody" : "partialBody")}</p>
  ) : json ? (
    <TraceJson code={json} label={label} copyText={text} modelRequest={modelRequest} />
  ) : (
    <div className={styles.rawBody} tabIndex={0} aria-label={label}>
      <CodeBlock code={text} language="text" />
    </div>
  );
}

function HttpReplayCopyMenu({ request }: { request: ReplayRequest }) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const label = t(`${prefix}.replay.copyAs`);
  return (
    <IconButtonMenu
      button={{
        size: "2xs",
        variant: "text",
        color: "on-surface",
        children: (
          <>
            {label}
            <Icon category="outlined" type="arrow_drop_down" />
          </>
        ),
      }}
      options={traceReplayFormats.map((format) => ({
        key: format,
        value: format,
        label: t(`${prefix}.replay.${format}`),
      }))}
      onSelect={async (format) => {
        const copied = await writeRichClipboard("", formatTraceHttpReplay(request, format));
        if (copied) showSuccess({ summary: t("common.copied") });
        else showError({ summary: t(`${prefix}.replay.copyFailed`) });
      }}
    />
  );
}

function HttpPayload({
  label,
  side,
  remoteTool,
  headers,
  body,
  replayExchange,
  offset,
  onPage,
}: {
  label: string;
  side: HttpSide;
  remoteTool: boolean;
  headers: Record<string, string>;
  body?: TraceHttpBody | null;
  replayExchange?: TraceHttpEvidence;
  offset: number;
  onPage: (next?: number) => void;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const replay = useMemo(() => replayExchange && prepareTraceHttpReplay(replayExchange), [replayExchange]);
  const recordedOffset = body?.offset ?? offset;
  const page = !!(body && (recordedOffset > 0 || body.next_offset != null));
  const contentType = headers["content-type"] ?? "";
  const encoding = body?.decoded ? undefined : headers["content-encoding"]?.trim().toLowerCase();
  const compressedPage = page && encoding && encoding !== "identity";
  const fileName = (remoteTool ? "http-" : "provider-") + side + (page ? `-${recordedOffset}` : "") + ".bin";
  const base64 = body?.data ?? "";
  const size = (base64.length / 4) * 3 - (base64.endsWith("==") ? 2 : base64.endsWith("=") ? 1 : 0);

  return (
    <section className={styles.httpPayload} aria-label={label}>
      <header>
        <h4>{label}</h4>
        <div className={styles.httpPayloadActions}>
          {replay?.status === "ready" && <HttpReplayCopyMenu request={replay.request} />}
          {body && (
            <Button
              type="button"
              size="2xs"
              variant="text"
              color="on-surface"
              onClick={() => downloadTraceBytes(body.data, fileName)}
            >
              {t(page ? "downloadPage" : "downloadOriginal")}
            </Button>
          )}
        </div>
      </header>
      {replay?.status === "incomplete" && <p>{t("replay.incomplete")}</p>}
      {replay?.status === "unsupported" && <p>{t("replay.unsupported")}</p>}
      {!remoteTool && side === "request" && page && <p>{t("replay.paged")}</p>}
      {offset === 0 && Object.keys(headers).length > 0 && (
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
      {body?.decoded && <p>{t("decodedBody")}</p>}
      {page && size > 0 && body?.total_bytes != null && (
        <p>{t("bodyRange", { first: recordedOffset + 1, last: recordedOffset + size, total: body.total_bytes })}</p>
      )}
      <TracePageButtons
        label={t("bodyPages", { body: label })}
        pager={{
          cursor: offset > 0 ? String(offset) : undefined,
          previous: () => onPage(),
          next: (cursor) => onPage(Number(cursor)),
        }}
        nextCursor={body?.next_offset == null ? null : String(body.next_offset)}
        disabled={false}
      />
      {compressedPage ? (
        <p>{t("compressedPagePreview")}</p>
      ) : body ? (
        <BodyPayload
          key={offset}
          body={body}
          label={label}
          encoding={encoding}
          modelRequest={!remoteTool && side === "request"}
          pagedText={page && (contentType.startsWith("text/") || contentType.includes("json"))}
        />
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
  const [paging, setPaging] = useState<{ ref: string; request: number[]; response: number[] }>();
  const current = paging?.ref === attempt?.ref ? paging : undefined;
  const requestOffset = current?.request[current.request.length - 1] ?? 0;
  const responseOffset = current?.response[current.response.length - 1] ?? 0;
  const shared = attempt && canReadTraceArtifact(turn, cutoffRank, attempt.observed_through_rank);
  const { organizationId } = useConversationTraceAccess();
  const query = enhancedControlPlaneApi.useGetConversationTraceHttpEvidenceQuery(
    attempt && shared && attempt.completeness !== "unavailable"
      ? {
          organizationId,
          sessionId,
          exchangeId: turn.exchange_id,
          ref: attempt.ref,
          requestOffset,
          responseOffset,
        }
      : skipToken,
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  if (!attempt) return { status: "unavailable" } as const;
  if (!shared) return { status: "masked" } as const;
  if (query.isError || attempt.completeness === "unavailable") return { status: "unavailable" } as const;
  if (!query.currentData || query.isFetching) return { status: "loading" } as const;
  const ref = attempt.ref;
  function page(side: HttpSide, next?: number) {
    setPaging((previous) => {
      const offsets = previous?.ref === ref ? previous : { ref, request: [], response: [] };
      const trail = next == null ? offsets[side].slice(0, -1) : [...offsets[side], next];
      return { ...offsets, [side]: trail };
    });
  }
  return { status: "ready", exchange: query.currentData, requestOffset, responseOffset, page } as const;
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
  const { exchange, requestOffset, responseOffset, page } = evidence;
  const requestPaged =
    (exchange.request_body?.offset ?? requestOffset) > 0 || exchange.request_body?.next_offset != null;
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
        replayExchange={remoteTool || requestPaged ? undefined : exchange}
        offset={requestOffset}
        onPage={(next) => page("request", next)}
      />
      <HttpPayload
        label={t(remoteTool ? "toolResponse" : "response")}
        side="response"
        remoteTool={remoteTool}
        headers={exchange.response_headers}
        body={exchange.response_body}
        offset={responseOffset}
        onPage={(next) => page("response", next)}
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
        <ConversationTraceSse
          sessionId={sessionId}
          turn={turn}
          attemptRef={attempt?.ref ?? null}
          cutoffRank={cutoffRank}
        />
      ) : tab === "langchain" ? (
        <ConversationTraceModel sessionId={sessionId} turn={turn} model={model} cutoffRank={cutoffRank} />
      ) : (
        <HttpEvidence key={attempt?.ref} evidence={evidence} />
      )}
    </article>
  );
}
