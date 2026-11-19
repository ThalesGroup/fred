// @vitest-environment jsdom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillsPage, { skillDocument } from "./SkillsPage";

const h = vi.hoisted(() => ({ read: true, write: false, create: vi.fn(), refetch: vi.fn() }));
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
  useGetSkillQuery: () => ({}),
  useCreateSkillMutation: () => [(args: unknown) => ({ unwrap: () => h.create(args) }), {}],
  useDeleteSkillMutation: () => [vi.fn(), {}],
  usePutSkillMutation: () => [vi.fn(), {}],
}));
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  h.read = true;
  h.write = false;
  h.create.mockReset();
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
    expect(container.textContent).not.toContain("rework.spaceSkills.new");
  });
  it("creates a package in the selected space from plain fields and refreshes its catalog", async () => {
    h.write = true;
    h.create.mockResolvedValue(undefined);
    act(() => root.render(<SkillsPage />));
    const button = (label: string) =>
      Array.from(container.querySelectorAll("button")).find((b) => b.textContent === label)!;
    await act(async () => button("rework.spaceSkills.new").click());
    const type = (element: HTMLInputElement | HTMLTextAreaElement, value: string) => {
      const prototype = Object.getPrototypeOf(element) as object;
      Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(element, value);
      element.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const [name, description] = Array.from(container.querySelectorAll("input"));
    await act(async () => {
      type(name, "meeting-notes");
      type(description, "Notes: decisions and actions");
      type(container.querySelector("textarea")!, "# Notes\n\nList the decisions.");
    });
    await act(async () => button("rework.spaceSkills.create").click());
    expect(h.create).toHaveBeenCalledWith({
      spaceId: "space-1",
      createSkill: {
        name: "meeting-notes",
        files: {
          "SKILL.md": skillDocument("meeting-notes", "Notes: decisions and actions", "# Notes\n\nList the decisions."),
        },
      },
    });
    expect(h.refetch).toHaveBeenCalledOnce();
  });
  it("quotes the description so YAML punctuation stays text", () => {
    expect(skillDocument("example", ' Use: "quotes" ', "Body")).toBe(
      '---\nname: example\ndescription: "Use: \\"quotes\\""\n---\n\nBody\n',
    );
  });
  it("does not present content to a caller without reading rights", () => {
    h.read = false;
    act(() => root.render(<SkillsPage />));
    expect(container.textContent).toContain("rework.spaceMembers.forbidden");
  });
});
