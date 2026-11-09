// @vitest-environment jsdom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillsPage from "./SkillsPage";

const h = vi.hoisted(() => ({ read: true, write: false, install: vi.fn(), refetch: vi.fn() }));
vi.mock("react-router-dom", () => ({
  useParams: () => ({ teamId: "space-1" }),
  useSearchParams: () => [new URLSearchParams()],
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@core/hooks/useSpaceAccess", () => ({
  useSpaceAccess: (_: string, permission: string) => ({
    settled: true,
    allowed: permission === "write" ? h.write : h.read,
  }),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: vi.fn() }),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({ currentData: [{ id: "space-1", name: "Organization", kind: "organization" }] }),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useListSkillsQuery: () => ({ currentData: [], refetch: h.refetch }),
  useDefaultSkillsQuery: () => ({ currentData: [{ name: "graph", description: "Diagrams" }] }),
  useGetSkillQuery: () => ({}),
  useInstallSkillMutation: () => [(args: unknown) => ({ unwrap: () => h.install(args) }), {}],
  useDeleteSkillMutation: () => [vi.fn(), {}],
  usePutSkillMutation: () => [vi.fn(), {}],
}));
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  h.read = true;
  h.write = false;
  h.install.mockReset();
  h.refetch.mockReset();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("space-owned skill catalog", () => {
  it("shows the owning space to readers without offering writes", () => {
    act(() => root.render(<SkillsPage />));
    expect(container.textContent).toContain("Organization");
    expect(container.textContent).toContain("rework.spaceSkills.empty");
    expect(container.textContent).not.toContain("rework.spaceSkills.installExplanation");
  });
  it("installs explicitly into the selected space and refreshes its catalog", async () => {
    h.write = true;
    h.install.mockResolvedValue(undefined);
    act(() => root.render(<SkillsPage />));
    const button = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.spaceSkills.install",
    );
    expect(button).toBeDefined();
    await act(async () => button!.click());
    expect(h.install).toHaveBeenCalledWith({ spaceId: "space-1", name: "graph" });
    expect(h.refetch).toHaveBeenCalledOnce();
  });
  it("does not present content to a caller without reading rights", () => {
    h.read = false;
    act(() => root.render(<SkillsPage />));
    expect(container.textContent).toContain("rework.spaceMembers.forbidden");
    expect(container.textContent).not.toContain("Diagrams");
  });
});
