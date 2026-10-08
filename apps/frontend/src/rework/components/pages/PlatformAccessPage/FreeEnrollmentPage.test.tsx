// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act, StrictMode } from "react";
import { createRoot, Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({
  invalid: false,
  record: vi.fn((_args: unknown) => ({ unwrap: async () => undefined })),
  accept: vi.fn(() => ({ unwrap: async () => undefined })),
  enroll: vi.fn(() => ({ unwrap: async () => ({ admitted: false }) })),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn(), useParams: () => ({ token: "opaque-token" }) }));
vi.mock("@shared/molecules/MarkdownRenderer/MarkdownRenderer", () => ({
  MarkdownRenderer: ({ text }: { text: string }) => <p>{text}</p>,
}));
vi.mock("@hooks/useLegalMarkdown", () => ({ useLegalMarkdown: () => "Terms of use" }));
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ gcuVersion: "v1", contactSupportLink: "https://support.example.org" }),
}));
vi.mock("../../../../security/KeycloakService", () => ({ KeyCloakService: { CallLogout: vi.fn() } }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useFreeEnrollmentPreviewQuery: () => ({
    data: state.invalid ? undefined : { team_name: "Demo", cgu_required: true },
    isError: state.invalid,
    isSuccess: !state.invalid,
    refetch: vi.fn(),
  }),
  useAcceptFreeCguMutation: () => [state.accept, {}],
  useEnrollFreeTeamMutation: () => [state.enroll, {}],
  useRecordFreeOpeningMutation: () => [state.record, {}],
}));
import FreeEnrollmentPage from "./FreeEnrollmentPage";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  state.invalid = false;
  vi.clearAllMocks();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
it("requires legal acceptance before caller-only enrollment", async () => {
  act(() => root.render(<FreeEnrollmentPage />));
  const join = [...host.querySelectorAll("button")].find((node) => node.textContent === "rework.platformAccess.join")!;
  expect(join.disabled).toBe(true);
  await act(async () => host.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
  await act(async () => join.click());
  expect(state.accept).toHaveBeenCalledWith({ token: "opaque-token", acceptFreeEnrollmentCgu: { version: "v1" } });
  expect(state.enroll).toHaveBeenCalledWith({ token: "opaque-token" });
});
it("invalid links expose no enrollment action", () => {
  state.invalid = true;
  act(() => root.render(<FreeEnrollmentPage />));
  expect(host.textContent).toContain("rework.platformAccess.invalidLink");
  expect(host.textContent).not.toContain("rework.platformAccess.joinTeam");
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
