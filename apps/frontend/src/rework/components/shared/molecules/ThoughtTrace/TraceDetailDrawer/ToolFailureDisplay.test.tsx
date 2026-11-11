// @vitest-environment jsdom
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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage, ToolFailure, ToolFailureCode } from "../../../../../../slices/runtime/runtimeOpenApi";
import en from "../../../../../../locales/en/translation.json";
import fr from "../../../../../../locales/fr/translation.json";
import type { TraceEntry } from "../../../../../utils/traceUtils";
import { TraceDetailDrawer } from "./TraceDetailDrawer";
import { TraceEntryRow } from "../TraceEntryRow/TraceEntryRow";

const clipboard = vi.hoisted(() => vi.fn());
vi.mock("../../../../../utils/clipboardUtils", () => ({ writeRichClipboard: clipboard }));
vi.mock("../traceDrawerContext", () => ({ useTraceDrawer: () => ({ openTrace: () => undefined }) }));

// Real catalogues: every assertion reads the shipped sentence, English unless a test switches.
const locale = vi.hoisted(() => ({ catalogue: null as unknown }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const value = key
        .split(".")
        .reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], locale.catalogue);
      if (typeof value !== "string") return key;
      return value.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options?.[name] ?? ""));
    },
  }),
}));

const failures = en.rework.chatTrace.failure;

// `Record<ToolFailureCode, …>`: a code added to the contract without a message fails to compile.
const EXPECTED: Record<ToolFailureCode, string> = {
  invalid_arguments: failures.invalid_arguments,
  not_approved: "Call declined by the user.",
  authentication_required: failures.authentication_required,
  resource_unavailable: failures.resource_unavailable,
  scope_refused: failures.scope_refused,
  rate_limited: failures.rate_limited,
  misconfigured: failures.misconfigured,
  service_busy: failures.service_busy,
  timeout: failures.timeout,
  service_error: failures.service_error,
  unexpected: failures.unexpected,
};

function message(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    session_id: "session-1",
    exchange_id: "exchange-7f3a",
    rank: 0,
    timestamp: "2026-11-11T00:00:00.000Z",
    role: "tool",
    channel: "tool_result",
    parts: [],
    ...overrides,
  };
}

function entry(
  name: string,
  content: string,
  failure: ToolFailure | null,
  args: Record<string, unknown> = {},
): Extract<TraceEntry, { kind: "combo" }> {
  return {
    kind: "combo",
    call: message({
      role: "assistant",
      channel: "tool_call",
      parts: [{ type: "tool_call", call_id: "c1", name, args }],
    }),
    result: message({ parts: [{ type: "tool_result", call_id: "c1", content, failure, latency_ms: 5 }] }),
  };
}

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  locale.catalogue = en;
  clipboard.mockReset().mockResolvedValue(true);
});

afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});

async function openDrawer(value: TraceEntry) {
  await act(async () => root.render(<TraceDetailDrawer entry={value} onClose={() => undefined} />));
}

describe("tool failure message", () => {
  it.each(Object.entries(EXPECTED) as [ToolFailureCode, string][])(
    "shows the %s message from the code alone",
    async (code, expected) => {
      await openDrawer(entry("summarize_document", "model-facing text that is never shown", { code }));
      expect(host.textContent).toContain(expected);
      expect(host.textContent).not.toContain("model-facing text");
    },
  );

  it("has the same failure keys in French and English", () => {
    expect(Object.keys(fr.rework.chatTrace.failure).sort()).toEqual(Object.keys(failures).sort());
  });

  it("shows the HTTP status once, from the structured failure", async () => {
    await openDrawer(entry("summarize_document", "", { code: "rate_limited", status: 429 }));
    expect(host.textContent).toContain("HTTP status 429");
    expect(host.textContent?.match(/429/g)).toHaveLength(1);
  });

  it("presents a declined call as a decision, without a support reference", async () => {
    await openDrawer(entry("summarize_document", "Tool execution was not approved.", { code: "not_approved" }));
    expect(host.textContent).toContain("Call declined by the user.");
    expect(host.textContent).not.toContain("Reference:");
    expect(host.querySelector('[class*="errorBox"]')).toBeNull();
  });
});

describe("platform failure reported by Knowledge Flow", () => {
  // The 2026-11-11 scenario: a wrong KF_ARTIFACT_ACCESS_KEY.
  const refusedKey: ToolFailure = {
    code: "misconfigured",
    status: 502,
    origin: "object_storage",
    setting: "KF_ARTIFACT_ACCESS_KEY",
  };

  it.each([
    [
      "en",
      en,
      "The document storage refused the credentials of Knowledge Flow. This is a platform configuration problem, not a problem with your request: an administrator must correct the Knowledge Flow configuration.",
      "Setting to check: KF_ARTIFACT_ACCESS_KEY (Knowledge Flow)",
      "HTTP status 502",
    ],
    [
      "fr",
      fr,
      "Le stockage de documents a refusé les identifiants de Knowledge Flow. C'est un problème de configuration de la plateforme, pas de votre demande : un administrateur doit corriger la configuration de Knowledge Flow.",
      "Réglage à vérifier : KF_ARTIFACT_ACCESS_KEY (Knowledge Flow)",
      "Statut HTTP 502",
    ],
  ])("says the component, the nature and the setting in %s", async (_lang, catalogue, sentence, setting, status) => {
    locale.catalogue = catalogue;
    await openDrawer(entry("read_document", "model-facing text that is never shown", refusedKey));
    const text = host.textContent?.replace(/\s+/g, " ") ?? "";
    expect(text).toContain(sentence);
    expect(text).toContain(setting);
    expect(text).toContain(status);
    expect(text.indexOf(sentence)).toBeLessThan(text.indexOf(setting));
    expect(text.indexOf(setting)).toBeLessThan(text.indexOf(status));
    expect(text.indexOf(status)).toBeLessThan(text.indexOf("exchange-7f3a"));
    const settingCode = [...host.querySelectorAll("code")].find(
      (node) => node.textContent === "KF_ARTIFACT_ACCESS_KEY",
    );
    expect(settingCode?.className).toContain("failureSetting");
  });

  it("names an unreachable dependency without blaming the request", async () => {
    await openDrawer(entry("read_document", "", { code: "service_busy", status: 503, origin: "search_index" }));
    expect(host.textContent).toContain(
      "The search index is unreachable. This is a platform availability problem, not a problem with your request",
    );
    expect(host.textContent).not.toContain("Setting to check");
  });
});

describe("tool failure reference", () => {
  it("shows the exchange reference under the message and copies it", async () => {
    await openDrawer(entry("summarize_document", "", { code: "service_error", status: 500 }));
    expect(host.textContent).toContain("Reference:");
    expect(host.querySelector("code")?.textContent).toBe("exchange-7f3a");
    const copy = host.querySelector<HTMLButtonElement>('button[aria-label="Copy the reference"]')!;
    await act(async () => copy.click());
    expect(clipboard).toHaveBeenCalledWith("", "exchange-7f3a");
    expect(host.querySelector('button[aria-label="Reference copied"]')).not.toBeNull();
  });
});

describe("query_tabular_documents SQL view", () => {
  it("opens on invalid_arguments and the tool name", async () => {
    await openDrawer(
      entry(
        "query_tabular_documents",
        'Binder Error: Referenced column "amount_typo" not found in FROM clause!',
        { code: "invalid_arguments", status: 400 },
        { sql: "SELECT amount_typo FROM d_sales" },
      ),
    );
    expect(host.textContent?.replace(/\s+/g, " ")).toContain("SELECT amount_typo FROM d_sales");
    expect(host.textContent).toContain('Referenced column "amount_typo" not found in FROM clause!');
    expect(host.textContent).not.toContain(failures.invalid_arguments);
  });

  it("stays closed for another code, even with an SQL engine text", async () => {
    await openDrawer(
      entry(
        "query_tabular_documents",
        "Binder Error: private engine dump",
        { code: "service_error" },
        { sql: "SELECT 1" },
      ),
    );
    expect(host.textContent).toContain(failures.service_error);
    expect(host.textContent).not.toContain("private engine dump");
  });
});

describe("result text never classifies", () => {
  // The exact sentence the frontend used to recognise as an HTTP 401 failure.
  const formerPhrase =
    "AUTHENTICATION_REQUIRED: Authentication was refused (HTTP 401). Authentication must be restored before retrying.";

  it("shows no failure for a former frozen phrase without `failure`", async () => {
    const value = entry("describe_tabular_documents", formerPhrase, null);
    await openDrawer(value);
    expect(host.textContent).toContain("Success");
    expect(host.textContent).not.toContain(failures.authentication_required);
    expect(host.textContent).not.toContain("Reference:");

    await act(async () => root.render(<TraceEntryRow entry={value} />));
    expect(host.textContent).not.toContain(failures.authentication_required);
    expect(host.querySelector('[aria-label="error"]')).toBeNull();
  });
});
