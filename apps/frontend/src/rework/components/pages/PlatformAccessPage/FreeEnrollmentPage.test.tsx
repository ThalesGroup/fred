// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act, StrictMode } from "react";
import { createRoot, Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({
  error: undefined as unknown,
  loading: false,
  support: "https://support.example.org",
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
  useFrontendProperties: () => ({ gcuVersion: "v1", contactSupportLink: state.support, siteDisplayName: "Acme" }),
}));
vi.mock("../../../../security/KeycloakService", () => ({ KeyCloakService: { CallLogout: vi.fn() } }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useFreeEnrollmentPreviewQuery: () => ({
    data: state.error || state.loading ? undefined : { team_name: "Demo", cgu_required: state.required },
    error: state.error,
    isError: Boolean(state.error),
    isLoading: state.loading,
    isSuccess: !state.error && !state.loading,
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
  state.error = undefined;
  state.loading = false;
  state.support = "https://support.example.org";
  state.required = true;
  state.markdown = "Terms of use";
  vi.clearAllMocks();
  state.accept.mockReturnValue({ unwrap: async () => undefined });
  state.enroll.mockReturnValue({ unwrap: async () => ({ admitted: false }) });
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
const invalidLink = { status: 404, data: { detail: "free_enrollment_link_invalid" } };
const button = (key: string) => [...host.querySelectorAll("button")].find((node) => node.textContent?.endsWith(key));
it("uses the common terms page before offering explicit team enrollment", async () => {
  act(() => root.render(<FreeEnrollmentPage />));
  expect(host.textContent).toContain("rework.gcu.title");
  expect(host.textContent).not.toContain("rework.platformAccess.join.title");
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
  expect(host.textContent).toContain("rework.platformAccess.join.title");
  expect(host.textContent).not.toContain("rework.platformAccess.signOut");
  await act(async () => button("rework.platformAccess.join.action")!.click());
  expect(state.enroll).toHaveBeenCalledWith({ token: "opaque-token" });
  expect(state.accept).toHaveBeenCalledTimes(1);
});
it("skips the legal page when current terms are already accepted", async () => {
  state.required = false;
  act(() => root.render(<FreeEnrollmentPage />));
  expect(host.textContent).not.toContain("rework.gcu.title");
  await act(async () => button("rework.platformAccess.join.action")!.click());
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
  expect(button("rework.platformAccess.join.action")).toBeUndefined();
  expect(state.refetch).not.toHaveBeenCalled();
  expect(state.enroll).not.toHaveBeenCalled();
});
it("cannot accept terms before their document loads", () => {
  state.markdown = "";
  act(() => root.render(<FreeEnrollmentPage />));
  act(() => reachBottom());
  expect(button("rework.gcu.validate")!.disabled).toBe(true);
});
it("reports an invalid link without a retry", () => {
  state.error = invalidLink;
  act(() => root.render(<FreeEnrollmentPage />));
  expect(host.querySelector("h1")?.textContent).toBe("rework.platformAccess.join.invalidTitle");
  expect(host.textContent).toContain("rework.platformAccess.join.invalidMessage");
  expect(host.querySelector('a[href="https://support.example.org"]')).not.toBeNull();
  expect(host.querySelectorAll("button")).toHaveLength(0);
  expect(host.textContent).not.toContain("Demo");
  expect(state.record).not.toHaveBeenCalled();
});
it("drops the footer of an invalid link when no support link is configured", () => {
  state.error = invalidLink;
  state.support = "";
  act(() => root.render(<FreeEnrollmentPage />));
  expect(host.querySelector("footer")).toBeNull();
});
it.each([
  ["a network failure", { status: "FETCH_ERROR", error: "Failed to fetch" }],
  ["a server error", { status: 503, data: { detail: "platform_access_unavailable" } }],
  ["another 404", { status: 404, data: { detail: "Not Found" } }],
])("keeps a retry for %s instead of calling the link invalid", (_name, error) => {
  state.error = error;
  act(() => root.render(<FreeEnrollmentPage />));
  expect(host.querySelector("h1")?.textContent).toBe("rework.platformAccess.join.uncheckedTitle");
  expect(host.querySelector('[role="alert"]')?.textContent).toBe("rework.platformAccess.join.uncheckedMessage");
  expect(host.textContent).not.toContain("rework.platformAccess.join.invalid");
  expect(host.textContent).not.toContain("rework.platformAccess.signOut");
  act(() => button("rework.platformAccess.retry")!.click());
  expect(state.refetch).toHaveBeenCalledTimes(1);
});
it("keeps a retry when joining fails", async () => {
  state.required = false;
  state.enroll.mockReturnValue({
    unwrap: async () => {
      throw { status: 500, data: { detail: "boom" } };
    },
  });
  act(() => root.render(<FreeEnrollmentPage />));
  await act(async () => button("rework.platformAccess.join.action")!.click());
  expect(host.querySelector("h1")?.textContent).toBe("rework.platformAccess.join.failedTitle");
  expect(host.querySelector('[role="alert"]')?.textContent).toBe("rework.platformAccess.failed");
  expect(button("rework.platformAccess.retry")).toBeDefined();
});
it("reports a link revoked while the page was open as no longer valid", async () => {
  state.required = false;
  state.enroll.mockReturnValue({
    unwrap: async () => {
      throw invalidLink;
    },
  });
  act(() => root.render(<FreeEnrollmentPage />));
  await act(async () => button("rework.platformAccess.join.action")!.click());
  expect(host.querySelector("h1")?.textContent).toBe("rework.platformAccess.join.invalidTitle");
  expect(button("rework.platformAccess.retry")).toBeUndefined();
});
it("shows the invitation with the team and a single join action", () => {
  state.required = false;
  act(() => root.render(<FreeEnrollmentPage />));
  const headings = host.querySelectorAll("h1");
  expect(headings).toHaveLength(1);
  expect(headings[0].textContent).toBe("rework.platformAccess.join.title");
  expect(host.querySelector("section")?.getAttribute("aria-labelledby")).toBe(headings[0].id);
  expect(host.querySelector("h2")?.textContent).toBe("Demo");
  expect(host.textContent).toContain("Acme");
  expect(host.querySelectorAll("button")).toHaveLength(1);
  expect(host.querySelector('a[href="https://support.example.org"]')).not.toBeNull();
});
it("announces that the invitation is being checked", () => {
  state.loading = true;
  act(() => root.render(<FreeEnrollmentPage />));
  expect(host.querySelector("h1")?.textContent).toBe("rework.platformAccess.join.checking");
  expect(host.querySelector('[role="status"]')?.textContent).toBe("rework.platformAccess.loading");
  expect(host.querySelectorAll("button")).toHaveLength(0);
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
