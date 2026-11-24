// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom

import { configureStore } from "@reduxjs/toolkit";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import { expect, it, vi } from "vitest";
import { enhancedControlPlaneApi as api } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { TraceIncidentShare } from "./TraceIncidentShare";

const mock = vi.hoisted(() => {
  const cutoff = { exchange_id: "failed", first_rank: 4, last_rank: 7 };
  const state = { reported: false, version: null as string | null };
  const request = vi.fn(async ({ method }: { url: string; method?: string; body?: unknown }) => {
    switch (method) {
      case "PUT":
        state.reported = true;
        state.version = "shared-version";
        return { data: { consent: { cutoff, grant_id: state.version } } };
      case "DELETE":
        state.reported = false;
        state.version = "revoked-version";
        return { data: undefined };
      default:
        return { data: { cutoff, reported: state.reported, consent_version: state.version } };
    }
  });
  return { request };
});

vi.mock("../../../../common/dynamicBaseQuery", () => ({ createDynamicBaseQuery: () => mock.request }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it("shares the verified failed-turn cutoff directly and refreshes after confirmed withdrawal", async () => {
  const store = configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (getDefault) => getDefault().concat(api.middleware),
  });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const render = (turnPending: boolean) =>
    act(async () => {
      root.render(
        <Provider store={store}>
          <TraceIncidentShare spaceId="team" sessionId="session" errorRef="error-ref" turnPending={turnPending} />
        </Provider>,
      );
    });
  const findButton = (label: string, container: ParentNode = host) =>
    [...container.querySelectorAll("button")].find((button) => button.textContent === label)!;
  const click = (label: string, container?: ParentNode) => act(async () => findButton(label, container).click());

  try {
    vi.stubGlobal("IntersectionObserver", undefined);
    await render(true);
    expect(findButton("share").disabled).toBe(true);
    expect(mock.request).not.toHaveBeenCalled();

    await render(false);
    expect(host.textContent).toContain("incident.description");
    expect(findButton("share").getAttribute("aria-disabled")).toBe("false");

    await click("share");
    expect(document.querySelector('[role="alertdialog"]')).toBeNull();
    expect(mock.request.mock.calls.find(([request]) => request.method === "PUT")?.[0]).toEqual({
      url: "/control-plane/v1/spaces/team/sessions/session/trace-incident/error-ref",
      method: "PUT",
      body: { exchange_id: "failed", last_rank: 7, expected_version: null },
    });
    expect(host.querySelector("h2")?.textContent).toBe("incident.thankYou");
    expect(host.querySelector('[role="status"]')?.textContent).toBe("incident.shared");

    await click("revoke");
    let dialog = document.querySelector('[role="alertdialog"]')!;
    expect(dialog.textContent).toContain("revokeDescription");
    await click("cancel", dialog);
    expect(mock.request.mock.calls.some(([request]) => request.method === "DELETE")).toBe(false);

    await click("revoke");
    dialog = document.querySelector('[role="alertdialog"]')!;
    await click("revoke", dialog);
    expect(host.querySelector("h2")?.textContent).toBe("incident.failure");
    expect(findButton("share").getAttribute("aria-disabled")).toBe("false");

    await click("share");
    const shareBodies = mock.request.mock.calls
      .filter(([request]) => request.method === "PUT")
      .map(([request]) => request.body);
    expect(shareBodies).toEqual([
      { exchange_id: "failed", last_rank: 7, expected_version: null },
      { exchange_id: "failed", last_rank: 7, expected_version: "revoked-version" },
    ]);
  } finally {
    await act(async () => root.unmount());
    store.dispatch(api.util.resetApiState());
    vi.unstubAllGlobals();
    host.remove();
  }
});
