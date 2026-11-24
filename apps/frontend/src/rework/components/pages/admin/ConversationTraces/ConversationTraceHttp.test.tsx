// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom

import { skipToken } from "@reduxjs/toolkit/query";
import { ToastProvider } from "@shared/molecules/Toast/ToastProvider";
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
  const copyButton = () => host.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"]');
  const copyOptions = () => Array.from(document.querySelectorAll<HTMLElement>('[role="listbox"] [role="option"]'));
  const render = (cutoffRank: number) =>
    act(async () =>
      root.render(
        <ToastProvider>
          <ConversationTraceModelCall
            sessionId="session"
            turn={turn}
            attempt={attempt}
            cutoffRank={cutoffRank}
            view="http"
            onView={vi.fn()}
          />
        </ToastProvider>,
      ),
    );

  httpEvidenceQuery.mockReturnValue({ currentData: exchange });
  writeRichClipboard.mockResolvedValue(true);
  try {
    await render(1);
    expect(httpEvidenceQuery).toHaveBeenLastCalledWith(skipToken, expect.anything());
    expect(copyButton()).toBeNull();

    await render(2);
    expect(httpEvidenceQuery).toHaveBeenLastCalledWith(
      { sessionId: "session", exchangeId: "exchange", ref: attempt.ref },
      expect.anything(),
    );
    expect(copyButton()?.textContent).toContain("replay.copyAs");
    expect(copyOptions()).toHaveLength(0);
    for (const [format, expected] of [
      ["python", "API_KEY = None"],
      ["curl", "--data-binary @-"],
      ["powershell", "curl.exe"],
    ]) {
      act(() => copyButton()!.click());
      expect(copyOptions()).toHaveLength(3);
      const option = copyOptions().find((item) => item.textContent?.endsWith("replay." + format))!;
      await act(async () => option.click());
      expect(copyOptions()).toHaveLength(0);
      expect(writeRichClipboard).toHaveBeenLastCalledWith("", expect.stringContaining(expected));
      const snippet = writeRichClipboard.mock.lastCall?.[1];
      expect(snippet).toContain(exchange.target);
      expect(snippet).toContain("fixture");
      expect(snippet).not.toContain("never-copy-this");
    }
    expect(host.querySelector('[role="alert"][data-severity="success"]')?.textContent).toContain("common.copied");

    writeRichClipboard.mockResolvedValueOnce(false);
    act(() => {
      copyButton()!.focus();
      copyButton()!.click();
    });
    const listbox = document.querySelector('[role="listbox"]')!;
    expect(listbox.getAttribute("aria-labelledby")).toBe(copyButton()!.id);
    for (const key of ["End", "Enter"]) {
      await act(async () => listbox.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true })));
    }
    expect(host.querySelector('[role="alert"][data-severity="error"]')?.textContent).toContain("replay.copyFailed");
    expect(document.activeElement).toBe(copyButton());

    httpEvidenceQuery.mockReturnValue({ currentData: { ...exchange, bearer_replay: false } });
    await render(2);
    expect(copyButton()).toBeNull();
    expect(host.textContent).toContain("replay.unsupported");

    httpEvidenceQuery.mockReturnValue({
      currentData: { ...exchange, request_body: { ...exchange.request_body, complete: false } },
    });
    await render(2);
    expect(copyButton()).toBeNull();
    expect(host.textContent).toContain("replay.incomplete");

    let decodedResponse = true;
    httpEvidenceQuery.mockImplementation((args) => ({
      currentData: {
        ...exchange,
        request_body: { ...exchange.request_body, offset: 0, next_offset: 15, total_bytes: 30 },
        response_headers: {
          "content-type": decodedResponse ? "text/event-stream" : "application/json",
          "content-encoding": "gzip",
        },
        response_body: {
          data: btoa(args?.responseOffset ? "late provider frame" : "early provider frame"),
          complete: false,
          decoded: decodedResponse,
          offset: args?.responseOffset ? 64 : 0,
          next_offset: args?.responseOffset ? null : 64,
          total_bytes: 83,
        },
      },
    }));
    const responseButton = (text: string) =>
      [...host.querySelectorAll<HTMLButtonElement>('section[aria-label="response"] button')].find(
        (button) => button.textContent === text,
      );
    await render(2);
    expect(copyButton()).toBeNull();
    expect(host.textContent).toContain("replay.paged");
    expect(host.textContent).toContain("early provider frame");
    expect(host.textContent).toContain("decodedBody");
    await act(async () => responseButton("next")!.click());
    expect(httpEvidenceQuery).toHaveBeenLastCalledWith(
      { sessionId: "session", exchangeId: "exchange", ref: attempt.ref, responseOffset: 64 },
      expect.anything(),
    );
    expect(host.textContent).toContain("late provider frame");
    expect(host.textContent).not.toContain("early provider frame");
    await act(async () => responseButton("previous")!.click());
    expect(host.textContent).toContain("early provider frame");

    decodedResponse = false;
    await render(2);
    expect(host.textContent).toContain("compressedPagePreview");
    expect(host.textContent).not.toContain("early provider frame");
    expect(responseButton("downloadPage")?.disabled).toBe(false);
    await act(async () => responseButton("next")!.click());
    expect(host.textContent).toContain("compressedPagePreview");
    expect(responseButton("downloadPage")?.disabled).toBe(false);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
