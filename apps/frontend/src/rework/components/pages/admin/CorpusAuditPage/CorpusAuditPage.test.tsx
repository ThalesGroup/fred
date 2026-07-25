// @vitest-environment happy-dom
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

// The fix action mutates many documents at once (resets a stale processing
// stage — never deletes anything, see CorpusAuditPage.tsx), so the
// confirm → mutation wiring needs real DOM interaction, not just static
// markup — rendered with react-dom/client + act, same convention as
// TeamCard.test.tsx (this repo's vitest default environment is "node", with
// no DOM, so interactive component tests opt into `happy-dom` per file and
// dispatch real click events rather than using react-dom/server).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { StoreAuditFinding, StoreAuditReport } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  audit: { data: undefined, isLoading: false, isFetching: false, isError: false, refetch: vi.fn() } as {
    data?: StoreAuditReport;
    isLoading: boolean;
    isFetching: boolean;
    isError: boolean;
    refetch: () => void;
  },
  fixAnomalies: vi.fn(() => ({ unwrap: () => Promise.resolve({ before: undefined, after: undefined }) })),
  isFixing: false,
}));

// `t` echoes its key, appending the interpolated `count` when one is passed —
// enough to assert which key (and which count) each state renders.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { count?: number }) => (opts?.count === undefined ? key : `${key}:${opts.count}`),
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useAuditDocumentsKnowledgeFlowV1DocumentsAuditGetQuery: () => h.audit,
  useFixDocumentsKnowledgeFlowV1DocumentsAuditFixPostMutation: () => [h.fixAnomalies, { isLoading: h.isFixing }],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarn: vi.fn(), showInfo: vi.fn() }),
}));

import CorpusAuditPage from "./CorpusAuditPage";

let container: HTMLDivElement;
let root: Root;

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<CorpusAuditPage />);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  h.audit = { data: undefined, isLoading: false, isFetching: false, isError: false, refetch: vi.fn() };
  h.fixAnomalies.mockClear();
  h.isFixing = false;
});

function finding(over: Partial<StoreAuditFinding> & Pick<StoreAuditFinding, "document_uid">): StoreAuditFinding {
  return {
    present_in_metadata: true,
    present_in_vector_store: true,
    present_in_content_store: true,
    ...over,
  };
}

function report(over: Partial<StoreAuditReport> = {}): StoreAuditReport {
  return {
    has_anomalies: false,
    total_seen: 0,
    metadata_count: 0,
    vector_count: 0,
    content_count: 0,
    anomalies: [],
    ...over,
  };
}

describe("CorpusAuditPage loading and error states", () => {
  it("shows the loading state while the audit is fetching", () => {
    h.audit = { data: undefined, isLoading: true, isFetching: true, isError: false, refetch: vi.fn() };
    render();
    expect(container.textContent).toContain("rework.admin.corpusAudit.loading");
  });

  it("shows the error state when the audit fails to load", () => {
    h.audit = { data: undefined, isLoading: false, isFetching: false, isError: true, refetch: vi.fn() };
    render();
    expect(container.textContent).toContain("rework.admin.corpusAudit.loadError");
  });
});

describe("CorpusAuditPage anomaly table", () => {
  it("renders the KPI counts and one row per anomaly", () => {
    h.audit = {
      data: report({
        has_anomalies: true,
        metadata_count: 10,
        vector_count: 9,
        content_count: 10,
        anomalies: [
          finding({
            document_uid: "doc-1",
            document_name: "Report.pdf",
            present_in_vector_store: false,
            issues: ["missing_vectors"],
          }),
        ],
      }),
      isLoading: false,
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    };
    render();

    expect(container.textContent).toContain("Report.pdf");
    expect(container.textContent).toContain("doc-1");
    expect(container.textContent).toContain("missing_vectors");
    expect(container.textContent).toContain("rework.admin.corpusAudit.anomaliesFound:1");
    // KPI stat cards render the raw counts via toLocaleString().
    expect(container.textContent).toContain("10");
    expect(container.textContent).toContain("9");
  });

  it("disables the Fix action when the audit reports no anomalies", () => {
    h.audit = {
      data: report({ has_anomalies: false }),
      isLoading: false,
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    };
    render();

    const fixButton = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("rework.admin.corpusAudit.fix"),
    );
    expect(fixButton?.disabled).toBe(true);
  });
});

describe("CorpusAuditPage empty state", () => {
  it("shows the empty state when has_anomalies is false and the list is empty", () => {
    h.audit = { data: report(), isLoading: false, isFetching: false, isError: false, refetch: vi.fn() };
    render();

    expect(container.textContent).toContain("rework.admin.corpusAudit.noAnomalies");
    expect(container.textContent).toContain("rework.admin.corpusAudit.empty");
  });
});

describe("CorpusAuditPage fix-confirmation flow", () => {
  function withAnomaly() {
    h.audit = {
      data: report({
        has_anomalies: true,
        anomalies: [finding({ document_uid: "doc-1", present_in_vector_store: false, issues: ["missing_vectors"] })],
      }),
      isLoading: false,
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    };
  }

  // ConfirmationDialog renders through `Portal` (`createPortal` into a
  // `#modal-portal` div appended directly to `document.body`), so it lives
  // outside `container` — search and assert against the whole document for
  // anything dialog-related, not just `container`.
  function clickButton(label: string) {
    const button = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.includes(label));
    expect(button).toBeTruthy();
    act(() => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
  }

  it("opens a confirmation dialog on Fix, and does not call the mutation before it is confirmed", () => {
    withAnomaly();
    render();

    clickButton("rework.admin.corpusAudit.fix");

    expect(document.body.textContent).toContain("rework.admin.corpusAudit.fixConfirm.title");
    expect(h.fixAnomalies).not.toHaveBeenCalled();
  });

  it("calls the fix mutation once the dialog is confirmed", async () => {
    withAnomaly();
    render();

    clickButton("rework.admin.corpusAudit.fix");
    clickButton("rework.admin.corpusAudit.fixConfirm.confirm");

    // Flush the mutation's promise microtask queue.
    await act(async () => {
      await Promise.resolve();
    });

    expect(h.fixAnomalies).toHaveBeenCalledTimes(1);
    expect(document.body.textContent).not.toContain("rework.admin.corpusAudit.fixConfirm.title");
  });

  it("cancelling the dialog does not call the mutation", () => {
    withAnomaly();
    render();

    clickButton("rework.admin.corpusAudit.fix");
    clickButton("rework.admin.corpusAudit.fixConfirm.cancel");

    expect(h.fixAnomalies).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain("rework.admin.corpusAudit.fixConfirm.title");
  });
});
