// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ featureManager: true, legacyBootstrap: vi.fn() }));

vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({
  useManagerPlatformAdmin: () => ({
    isLoading: false,
    isFetching: false,
    currentData: { platform_roles: state.featureManager ? ["feature_manager"] : [] },
    isFeatureManager: state.featureManager,
  }),
}));
vi.mock("@hooks/useUserCapabilities.ts", () => ({
  useUserCapabilities: () => state.legacyBootstrap(),
}));
vi.mock("react-router-dom", () => ({
  Navigate: ({ to }: { to: string }) => <span>{to}</span>,
}));

import { Protected } from "./Protected";

it("admits a feature manager from current manager authority without the legacy bootstrap", () => {
  state.featureManager = true;
  state.legacyBootstrap.mockClear();
  const html = renderToStaticMarkup(
    <Protected requires="platformSkills">
      <div>Platform skills</div>
    </Protected>,
  );
  expect(html).toContain("Platform skills");
  expect(state.legacyBootstrap).not.toHaveBeenCalled();
});

it("rejects a user without the feature manager role", () => {
  state.featureManager = false;
  const html = renderToStaticMarkup(
    <Protected requires="platformSkills">
      <div>Platform skills</div>
    </Protected>,
  );
  expect(html).toContain("/unauthorized");
  expect(html).not.toContain("Platform skills");
});
