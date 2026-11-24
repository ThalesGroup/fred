// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  items: [] as { capability_id: string; preparation_id: string; state: string }[],
  refetch: vi.fn(),
  retry: vi.fn(),
  checkReadiness: vi.fn(),
  translate: vi.fn((key: string) => key),
}));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: h.translate }) }));
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "Assistant" }),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAgentReadinessCheckMutation: () => [h.checkReadiness],
}));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamAgentPreparationsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPreparationsGetQuery: () => ({
    data: { items: h.items },
    refetch: h.refetch,
  }),
  usePostTeamAgentPreparationRetryControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPreparationsCapabilityIdRetryPostMutation:
    () => [h.retry, { isLoading: false }],
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
  h.items = [];
  h.refetch.mockReset();
  h.retry.mockReset().mockReturnValue({ unwrap: () => Promise.resolve() });
  h.checkReadiness.mockReset();
  h.translate.mockClear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("WordTemplatePreparationStatus", () => {
  it("shows staged and running preparation with the configured agent name", () => {
    render(true);
    expect(container.textContent).toContain("capability.word_template.preparation.staged");
    h.items = [{ capability_id: "word_template", preparation_id: "prep", state: "running" }];
    render();
    expect(container.textContent).toContain("capability.word_template.preparation.running");
    expect(h.translate).toHaveBeenCalledWith("capability.word_template.preparation.running", {
      agentsNicknameSingular: "Assistant",
    });
    expect(container.querySelector("button")).toBeNull();
  });

  it("offers retry after failure and refreshes readiness on a terminal result", async () => {
    h.items = [{ capability_id: "word_template", preparation_id: "prep", state: "failed" }];
    render();
    expect(container.getAttribute("role")).toBeNull();
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
    const button = container.querySelector("button");
    expect(button).not.toBeNull();
    await act(async () => button?.click());
    expect(h.retry).toHaveBeenCalledWith({ teamId: "team", agentInstanceId: "agent", capabilityId: "word_template" });
    expect(h.refetch).toHaveBeenCalledTimes(1);
    expect(h.checkReadiness).toHaveBeenCalledWith({ teamId: "team", agentInstanceId: "agent" });
    h.items = [{ capability_id: "word_template", preparation_id: "next", state: "succeeded" }];
    render();
    expect(container.textContent).toContain("capability.word_template.preparation.succeeded");
    expect(h.checkReadiness).toHaveBeenCalledTimes(2);
  });
});
