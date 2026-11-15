// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({
  token: "opaque-token",
  error: undefined as unknown,
  loading: false,
  redeeming: false,
  refetch: vi.fn(),
  preview: vi.fn(),
  redeem: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({ useParams: () => ({ token: state.token }) }));
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ siteDisplayName: "Acme" }),
}));
vi.mock("../../../../common/platformAccess", () => ({ platformPath: (path: string) => `/fred/${path}` }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePreviewTeamJoinLinkQuery: (...args: unknown[]) => {
    state.preview(...args);
    return {
      currentData: state.error || state.loading ? undefined : { team_id: "team", team_name: "Research" },
      error: state.error,
      isFetching: state.loading,
      refetch: state.refetch,
    };
  },
  useRedeemTeamJoinLinkMutation: () => [state.redeem, { isLoading: state.redeeming }],
}));
import FreeEnrollmentPage from "./FreeEnrollmentPage";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
const button = (key: string) => [...host.querySelectorAll("button")].find((node) => node.textContent === key);
const render = async () => {
  await act(async () => root.render(<FreeEnrollmentPage />));
};
beforeEach(() => {
  state.token = "opaque-token";
  state.error = undefined;
  state.loading = false;
  state.redeeming = false;
  vi.clearAllMocks();
  state.redeem.mockReturnValue({ unwrap: async () => ({ team_id: "team", team_name: "Research" }) });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
it("previews an admitted user's invitation without enrolling automatically", async () => {
  await render();
  expect(state.preview).toHaveBeenCalledWith({ token: "opaque-token" }, { refetchOnMountOrArgChange: true });
  expect(host.textContent).toContain("Research");
  expect(host.textContent).toContain("rework.teamSettings.members.inviteLink.hint");
  expect(state.redeem).not.toHaveBeenCalled();
});
it("joins only on explicit action, then opens the canonical team landing under the basename", async () => {
  const replace = vi.fn();
  vi.stubGlobal("location", { ...window.location, replace });
  await render();
  await act(async () => button("rework.platformAccess.join.action")!.click());
  expect(state.redeem).toHaveBeenCalledWith({ token: "opaque-token" });
  expect(replace).toHaveBeenCalledWith("/fred/team/team");
});
it.each([404, 422, 403, 503])("does not offer membership when preview returns %s", async (status) => {
  state.error = { status };
  await render();
  expect(host.querySelector('[role="alert"]')).not.toBeNull();
  expect(button("rework.platformAccess.join.action")).toBeUndefined();
  expect(state.redeem).not.toHaveBeenCalled();
  await act(async () => button("rework.spaceMembers.refresh")!.click());
  expect(state.refetch).toHaveBeenCalled();
});
it("reports revocation between preview and redemption without navigating", async () => {
  const replace = vi.fn();
  vi.stubGlobal("location", { ...window.location, replace });
  state.redeem.mockReturnValue({
    unwrap: async () => {
      throw { status: 404 };
    },
  });
  await render();
  await act(async () => button("rework.platformAccess.join.action")!.click());
  expect(host.textContent).toContain("rework.platformAccess.join.invalidMessage");
  expect(replace).not.toHaveBeenCalled();
  state.token = "another-token";
  await render();
  expect(host.textContent).not.toContain("rework.platformAccess.join.invalidMessage");
});
it("waits for preview and disables a pending redemption", async () => {
  state.loading = true;
  await render();
  expect(host.querySelector('[role="status"]')).not.toBeNull();
  expect(button("rework.platformAccess.join.action")).toBeUndefined();
  state.loading = false;
  state.redeeming = true;
  await render();
  expect(button("rework.platformAccess.join.action")!.disabled).toBe(true);
});
