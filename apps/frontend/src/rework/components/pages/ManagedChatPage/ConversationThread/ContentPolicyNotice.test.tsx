// @vitest-environment happy-dom
// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0.

import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { ContentPolicyNotice } from "./ContentPolicyNotice";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../../security/KeycloakService", () => ({
  KeyCloakService: { ensureFreshToken: async () => {}, GetToken: () => "fixture-token" },
}));

it("polls the authoritative rank and support reference and stops after enrichment", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("IntersectionObserver", undefined);
  const container = document.createElement("div");
  const root = createRoot(container);
  const supportErrorRef = "b".repeat(32);
  const initial = {
    code: "content_policy_blocked",
    kind: "prompt_blocked",
    categories: ["self_harm"],
    analysis_state: "pending",
  } as const;
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: true,
    json: async () => ({ ...initial, analysis_state: "complete", explanation: "self_harm" }),
  } as Response);
  try {
    act(() =>
      root.render(
        <ContentPolicyNotice
          notice={{ ...initial, categories: [...initial.categories] }}
          messagesUrl="/runtime/agents/sessions/local-session/messages"
          rank={7}
          supportErrorRef={supportErrorRef}
          timestamp={new Date().toISOString()}
        />,
      ),
    );
    expect(container.textContent).not.toContain("rework.contentPolicy.explanation");
    await act(async () => vi.advanceTimersByTimeAsync(1800));
    expect(fetchSpy).toHaveBeenCalledWith(
      new URL(`/runtime/agents/sessions/local-session/content-notices/7/${supportErrorRef}`, location.origin).href,
      expect.objectContaining({ headers: { Authorization: "Bearer fixture-token" } }),
    );
    expect(container.textContent).toContain("rework.contentPolicy.explanation");
    await act(async () => vi.advanceTimersByTimeAsync(30_000));
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  } finally {
    act(() => root.unmount());
    fetchSpy.mockRestore();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  }
});
