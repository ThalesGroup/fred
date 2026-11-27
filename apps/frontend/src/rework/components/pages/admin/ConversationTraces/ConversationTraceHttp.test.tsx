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
import { ConversationTraceModelCall, TraceHttpAttemptEvidence } from "./ConversationTraceHttp";
import { ConversationTraceModel } from "./ConversationTraceModel";

const { httpEvidenceQuery, maskedEvidenceQuery, modelEvidenceQuery, writeRichClipboard } = vi.hoisted(() => ({
  httpEvidenceQuery: vi.fn(),
  maskedEvidenceQuery: vi.fn(),
  modelEvidenceQuery: vi.fn(),
  writeRichClipboard: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("@rework/utils/clipboardUtils", () => ({ writeRichClipboard }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  enhancedControlPlaneApi: {
    useGetConversationTraceHttpEvidenceQuery: httpEvidenceQuery,
    useGetConversationTraceMaskedEvidenceQuery: maskedEvidenceQuery,
    useGetConversationTraceModelEvidenceQuery: modelEvidenceQuery,
  },
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it("copies the selected provider request in masked and shared views even when the response is partial", async () => {
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
  const formats = [
    ["python", "API_KEY = None"],
    ["curl", "--data-binary @-"],
    ["powershell", "curl.exe"],
  ];
  async function copyReplay(format: string, expected: string) {
    act(() => copyButton()!.click());
    expect(copyOptions()).toHaveLength(3);
    const option = copyOptions().find((item) => item.textContent?.endsWith("replay." + format))!;
    await act(async () => option.click());
    expect(copyOptions()).toHaveLength(0);
    expect(writeRichClipboard).toHaveBeenLastCalledWith("", expect.stringContaining(expected));
    return writeRichClipboard.mock.lastCall?.[1];
  }
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
  const maskedRequest = {
    messages: [{ role: "user", content: "<redacted>" }],
  };
  maskedEvidenceQuery.mockReturnValue({
    currentData: {
      documents: {
        request: {
          data: maskedRequest,
          annotations: [{ parent: ["messages", 0], position: 1, key: "new_field", value_type: "object" }],
        },
        response: { data: { error: "separate response evidence" } },
      },
    },
  });
  writeRichClipboard.mockResolvedValue(true);
  try {
    await render(1);
    expect(httpEvidenceQuery).toHaveBeenLastCalledWith(skipToken, expect.anything());
    expect(copyButton()?.textContent).toContain("replay.copyAs");
    expect(host.textContent).toContain("replay.maskedSetup");
    expect(maskedEvidenceQuery).toHaveBeenLastCalledWith(
      { sessionId: "session", exchangeId: "exchange", ref: attempt.ref, kind: "http" },
      expect.anything(),
    );
    expect(host.textContent).toContain("masking.field");
    const toggle = host.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    expect(toggle.checked).toBe(true);
    const copy = host.querySelector<HTMLButtonElement>('button[aria-label="common.copyCode"]')!;
    await act(async () => copy.click());
    expect(JSON.parse(writeRichClipboard.mock.lastCall?.[1])).toEqual(maskedRequest);
    for (const [format, expected] of formats) {
      const snippet = await copyReplay(format, expected);
      expect(snippet).toContain("<redacted>");
      expect(snippet).not.toContain("new_field");
      expect(snippet).not.toContain("separate response evidence");
      expect(snippet).not.toContain(exchange.target);
      expect(snippet).not.toContain("fixture");
      expect(snippet).not.toContain("never-copy-this");
    }
    await act(async () => toggle.click());
    expect(host.textContent).not.toContain("masking.field");

    await act(async () =>
      root.render(<TraceHttpAttemptEvidence sessionId="session" turn={turn} attempt={attempt} cutoffRank={1} />),
    );
    expect(copyButton()).toBeNull();

    await render(2);
    expect(httpEvidenceQuery).toHaveBeenLastCalledWith(
      { sessionId: "session", exchangeId: "exchange", ref: attempt.ref },
      expect.anything(),
    );
    expect(copyButton()?.textContent).toContain("replay.copyAs");
    expect(copyOptions()).toHaveLength(0);
    for (const [format, expected] of formats) {
      const snippet = await copyReplay(format, expected);
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

it("colors masked LangChain input messages and initially folds their tool definitions", async () => {
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  const model = {
    ref: "2".repeat(32),
    call_id: "call",
    model: "fixture",
    observed_through_rank: 2,
    completeness: "complete",
  } as const;
  modelEvidenceQuery.mockReturnValue({});
  maskedEvidenceQuery.mockReturnValue({
    currentData: {
      documents: {
        model: {
          data: {
            input: {
              tools: [{ name: "<redacted>" }],
              messages: [{ role: "user" }, { role: "assistant" }],
            },
          },
          annotations: [{ parent: ["input", "messages", 0], position: 1, key: "args", value_type: "object" }],
        },
      },
    },
  });
  try {
    await act(async () =>
      root.render(
        <ConversationTraceModel
          sessionId="session"
          turn={{
            exchange_id: "exchange",
            turn_number: 1,
            started_at: "2026-11-19T12:00:00Z",
            duration_ms: 1,
            outcome: "failed",
            availability: "captured",
            call_ids: [model.call_id],
            trace_id: null,
            span_id: null,
            access: "masked",
          }}
          model={model}
        />,
      ),
    );
    expect(modelEvidenceQuery).toHaveBeenLastCalledWith(skipToken, expect.anything());
    expect(host.querySelector(".cm-foldPlaceholder")).toBeTruthy();
    expect(host.querySelector(".cm-content")?.textContent).not.toContain("<redacted>");
    expect([...host.querySelectorAll(".trace-message-even")].map((line) => line.textContent).join(" ")).toContain(
      '"user"',
    );
    expect([...host.querySelectorAll(".trace-message-odd")].map((line) => line.textContent).join(" ")).toContain(
      '"assistant"',
    );
    expect(host.querySelector(".cm-content")?.textContent).toContain("masking.field");
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});
