// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act, StrictMode } from "react";
import { createRoot, Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({
  invalid: false,
  required: true,
  markdown: "Terms of use",
  refetch: vi.fn(),
  record: vi.fn((_args: unknown) => ({ unwrap: async () => undefined })),
  accept: vi.fn(() => ({ unwrap: async () => undefined })),
  enroll: vi.fn(() => ({ unwrap: async () => ({ admitted: false }) })),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn(), useParams: () => ({ token: "opaque-token" }) }));
vi.mock("@shared/molecules/MarkdownRenderer/MarkdownRenderer", () => ({
  MarkdownRenderer: ({ text }: { text: string }) => <p>{text}</p>,
}));
vi.mock("@hooks/useLegalMarkdown", () => ({ useLegalMarkdown: () => state.markdown }));
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ gcuVersion: "v1", contactSupportLink: "https://support.example.org" }),
}));
vi.mock("../../../../security/KeycloakService", () => ({ KeyCloakService: { CallLogout: vi.fn() } }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useFreeEnrollmentPreviewQuery: () => ({
    data: state.invalid ? undefined : { team_name: "Demo", cgu_required: state.required },
    isError: state.invalid,
    isSuccess: !state.invalid,
    refetch: state.refetch,
  }),
  useAcceptFreeCguMutation: () => [state.accept, {}],
  useEnrollFreeTeamMutation: () => [state.enroll, {}],
  useRecordFreeOpeningMutation: () => [state.record, {}],
}));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetUserDetailsControlPlaneV1UserGetQuery: () => {
    throw new Error("Protected user query before enrollment");
  },
  useValidateGcuControlPlaneV1GcuPostMutation: () => {
    throw new Error("Ordinary legal endpoint before admission");
  },
}));
import FreeEnrollmentPage from "./FreeEnrollmentPage";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
let reachBottom: () => void;
beforeEach(() => {
  state.invalid = false;
  state.required = true;
  state.markdown = "Terms of use";
  vi.clearAllMocks();
  state.accept.mockReturnValue({ unwrap: async () => undefined });
  state.refetch.mockReturnValue({
    unwrap: async () => {
      state.required = false;
    },
  });
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(private callback: (entries: unknown[]) => void) {}
      observe(target: Element) {
        reachBottom = () => this.callback([{ isIntersecting: true, target }]);
      }
      unobserve() {}
      disconnect() {}
    },
  );
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
const button = (key: string) => [...host.querySelectorAll("button")].find((node) => node.textContent?.endsWith(key));
it("uses the common terms page before offering explicit team enrollment", async () => {
  act(() => root.render(<FreeEnrollmentPage />));
  expect(host.textContent).toContain("rework.gcu.title");
  expect(host.textContent).not.toContain("rework.platformAccess.joinTeam");
  expect(host.querySelector('input[type="checkbox"]')).toBeNull();
  expect(button("rework.gcu.validate")!.disabled).toBe(true);
  act(() => reachBottom());
  expect(button("rework.gcu.validate")!.disabled).toBe(false);
  await act(async () => button("rework.gcu.validate")!.click());
  expect(state.accept).toHaveBeenCalledWith({ token: "opaque-token", acceptFreeEnrollmentCgu: { version: "v1" } });
  expect(state.refetch).toHaveBeenCalledTimes(1);
  expect(state.enroll).not.toHaveBeenCalled();
  act(() => root.render(<FreeEnrollmentPage />));
  expect(host.textContent).not.toContain("rework.gcu.title");
  expect(host.textContent).toContain("rework.platformAccess.joinTeam");
  expect(host.textContent).not.toContain("rework.platformAccess.signOut");
  await act(async () => button("rework.platformAccess.join")!.click());
  expect(state.enroll).toHaveBeenCalledWith({ token: "opaque-token" });
  expect(state.accept).toHaveBeenCalledTimes(1);
});
it("skips the legal page when current terms are already accepted", async () => {
  state.required = false;
  act(() => root.render(<FreeEnrollmentPage />));
  expect(host.textContent).not.toContain("rework.gcu.title");
  await act(async () => button("rework.platformAccess.join")!.click());
  expect(state.accept).not.toHaveBeenCalled();
  expect(state.enroll).toHaveBeenCalledTimes(1);
});
it("does not enroll when invitation legal acceptance fails", async () => {
  state.accept.mockReturnValue({
    unwrap: async () => {
      throw new Error("Expired invitation");
    },
  });
  act(() => root.render(<FreeEnrollmentPage />));
  act(() => reachBottom());
  await act(async () => button("rework.gcu.validate")!.click());
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("rework.platformAccess.failed");
  expect(button("rework.platformAccess.join")).toBeUndefined();
  expect(state.refetch).not.toHaveBeenCalled();
  expect(state.enroll).not.toHaveBeenCalled();
});
it("cannot accept terms before their document loads", () => {
  state.markdown = "";
  act(() => root.render(<FreeEnrollmentPage />));
  act(() => reachBottom());
  expect(button("rework.gcu.validate")!.disabled).toBe(true);
});
it("invalid links expose no enrollment action", () => {
  state.invalid = true;
  act(() => root.render(<FreeEnrollmentPage />));
  expect(host.textContent).toContain("rework.platformAccess.invalidLink");
  expect(host.textContent).not.toContain("rework.platformAccess.joinTeam");
  expect(host.textContent).not.toContain("rework.platformAccess.signOut");
});

it("records one authenticated arrival independently of legal acceptance and enrollment", async () => {
  await act(async () => root.render(<FreeEnrollmentPage />));
  expect(state.record).toHaveBeenCalledTimes(1);
  expect(state.record.mock.calls[0][0]).toMatchObject({
    token: "opaque-token",
  });
  expect(state.accept).not.toHaveBeenCalled();
  expect(state.enroll).not.toHaveBeenCalled();
  await act(async () => root.render(<FreeEnrollmentPage />));
  expect(state.record).toHaveBeenCalledTimes(1);
});

it("records once under duplicate StrictMode effects", async () => {
  await act(async () =>
    root.render(
      <StrictMode>
        <FreeEnrollmentPage />
      </StrictMode>,
    ),
  );
  expect(state.record).toHaveBeenCalledTimes(1);
});
