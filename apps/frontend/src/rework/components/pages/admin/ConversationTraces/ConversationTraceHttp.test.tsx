// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom

import { skipToken } from "@reduxjs/toolkit/query";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import type {
  ConversationTraceTurn,
  TraceHttpAttempt,
  TraceHttpEvidence,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { ConversationTraceModelCall } from "./ConversationTraceHttp";

const { httpEvidenceQuery, writeRichClipboard } = vi.hoisted(() => ({
  httpEvidenceQuery: vi.fn(),
  writeRichClipboard: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("@rework/utils/clipboardUtils", () => ({ writeRichClipboard }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  enhancedControlPlaneApi: { useGetConversationTraceHttpEvidenceQuery: httpEvidenceQuery },
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it("copies only the selected shared provider request and keeps replay available for a partial response", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const attempt: TraceHttpAttempt = {
    ref: "1".repeat(32),
    call_id: "call",
    attempt: 1,
    status: 400,
    duration_ms: 1,
    request_bytes: 16,
    response_bytes: 0,
    completeness: "partial",
    observed_through_rank: 2,
  };
  const turn: ConversationTraceTurn = {
    exchange_id: "exchange",
    turn_number: 1,
    started_at: "2026-11-19T12:00:00Z",
    duration_ms: 1,
    outcome: "failed",
    availability: "captured",
    call_ids: [attempt.call_id],
    trace_id: null,
    span_id: null,
    access: "shared",
  };
  const exchange: TraceHttpEvidence = {
    target: "https://provider.example/v1/chat/completions",
    method: "POST",
    bearer_replay: true,
    request_headers: { "content-type": "application/json", authorization: "never-copy-this" },
    request_body: { data: btoa('{"model":"fixture"}'), complete: true },
    response_headers: {},
  };
  const copyButton = (format: string) =>
    Array.from(host.querySelectorAll("button")).find((button) => button.textContent === "replay." + format);
  const render = (cutoffRank: number) =>
    act(async () =>
      root.render(
        <ConversationTraceModelCall
          sessionId="session"
          turn={turn}
          attempt={attempt}
          cutoffRank={cutoffRank}
          view="http"
          onView={vi.fn()}
        />,
      ),
    );

  httpEvidenceQuery.mockReturnValue({ currentData: exchange });
  writeRichClipboard.mockResolvedValue(true);
  try {
    await render(1);
    expect(httpEvidenceQuery).toHaveBeenLastCalledWith(skipToken, expect.anything());
    expect(copyButton("python")).toBeUndefined();

    await render(2);
    expect(httpEvidenceQuery).toHaveBeenLastCalledWith(
      { sessionId: "session", exchangeId: "exchange", ref: attempt.ref },
      expect.anything(),
    );
    for (const [format, expected] of [
      ["python", "API_KEY = None"],
      ["curl", "--data-binary @-"],
      ["powershell", "curl.exe"],
    ]) {
      const button = copyButton(format)!;
      await act(async () => button.click());
      expect(writeRichClipboard).toHaveBeenLastCalledWith("", expect.stringContaining(expected));
      const snippet = writeRichClipboard.mock.lastCall?.[1];
      expect(snippet).toContain(exchange.target);
      expect(snippet).toContain("fixture");
      expect(snippet).not.toContain("never-copy-this");
    }
    expect(host.textContent).toContain("replay.copied");

    httpEvidenceQuery.mockReturnValue({ currentData: { ...exchange, bearer_replay: false } });
    await render(2);
    expect(copyButton("powershell")).toBeUndefined();
    expect(host.textContent).toContain("replay.unsupported");

    httpEvidenceQuery.mockReturnValue({
      currentData: { ...exchange, request_body: { ...exchange.request_body, complete: false } },
    });
    await render(2);
    expect(copyButton("powershell")).toBeUndefined();
    expect(host.textContent).toContain("replay.incomplete");
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
