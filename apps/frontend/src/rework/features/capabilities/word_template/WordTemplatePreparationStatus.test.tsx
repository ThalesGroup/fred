// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  files: [] as { preparation_state: string; preparation_error?: string }[],
  ready: false,
  retry: vi.fn(),
  refetch: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useResolveWordTemplateLibraryQuery: () => ({
    data: { files: h.files, activation_ready: h.ready, source: "agent" },
    refetch: h.refetch,
  }),
  useUpdateAgentInstanceMutation: () => [h.retry, { isLoading: false }],
}));

import { WordTemplatePreparationStatus } from "./WordTemplatePreparationStatus";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

function render(staged = false) {
  act(() =>
    root.render(<WordTemplatePreparationStatus teamId="team" agentInstanceId="agent" staged={staged} hasLibrary />),
  );
}

beforeEach(() => {
  h.files = [];
  h.ready = false;
  h.retry.mockReset().mockReturnValue({ unwrap: async () => undefined });
  h.refetch.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("WordTemplatePreparationStatus", () => {
  it("shows staged originals and CP pending state", () => {
    render(true);
    expect(container.textContent).toContain("capability.word_template.preparation.staged");
    h.files = [{ preparation_state: "pending" }];
    render();
    expect(container.textContent).toContain("capability.word_template.preparation.pending");
  });
  it("retries the saved agent without sending form drafts and shows confirmed readiness", async () => {
    h.files = [{ preparation_state: "failed", preparation_error: "Preparation unavailable" }];
    render();
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
    expect(container.textContent).toContain("Preparation unavailable");
    await act(async () => container.querySelector("button")?.click());
    expect(h.retry).toHaveBeenCalledWith({ spaceId: "team", agentInstanceId: "agent", updateAgentInstanceRequest: {} });
    h.files = [{ preparation_state: "ready" }];
    h.ready = true;
    render();
    expect(container.textContent).toContain("capability.word_template.preparation.ready");
  });
});
