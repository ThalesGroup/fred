// @vitest-environment jsdom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SkillSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import SkillsPage, { skillDocument } from "./SkillsPage";

const h = vi.hoisted(() => ({
  read: true,
  write: false,
  create: vi.fn(),
  refetch: vi.fn(),
  skills: [] as SkillSummary[],
  failed: false,
  detail: vi.fn(),
  put: vi.fn(),
}));
vi.mock("react-router-dom", () => ({
  useParams: () => ({ teamId: "space-1" }),
  useSearchParams: () => [new URLSearchParams()],
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, args?: { space?: string }) => (args?.space ? `${key}: ${args.space}` : key),
  }),
}));
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
  useSkillScopeQuery: () => ({ currentData: { skills: h.skills }, isError: h.failed, refetch: h.refetch }),
  useGetSkillQuery: (args: unknown) => {
    h.detail(args);
    return {
      currentData: {
        files: { "SKILL.md": "# Instructions", "references/help.md": "Reference" },
        expected_revision: "r1",
        discoverable: false,
      },
      refetch: h.refetch,
    };
  },
  useCreateSkillMutation: () => [(args: unknown) => ({ unwrap: () => h.create(args) }), {}],
  useDeleteSkillMutation: () => [vi.fn(), {}],
  usePutSkillMutation: () => [(args: unknown) => ({ unwrap: () => h.put(args) }), {}],
}));
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  h.skills = [];
  h.failed = false;
  h.detail.mockClear();
  h.put.mockReset();
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
      Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.endsWith(label))!;
    await act(async () => button("rework.spaceSkills.new").click());
    const type = (element: HTMLInputElement | HTMLTextAreaElement, value: string) => {
      const prototype = Object.getPrototypeOf(element) as object;
      Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(element, value);
      element.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const dialog = document.querySelector('[role="dialog"]')!;
    const [name, description] = Array.from(dialog.querySelectorAll("input"));
    await act(async () => {
      type(name, "meeting-notes");
      type(description, "Notes: decisions and actions");
      type(dialog.querySelector("textarea")!, "# Notes\n\nList the decisions.");
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

function skill(spaceId: string): SkillSummary {
  return {
    skill_id: `skill-${spaceId}`,
    space_id: spaceId,
    space_name: spaceId === "space-1" ? "Team" : "Acme",
    name: "meeting-notes",
    description: "Decisions and actions",
    builtin: false,
    user_invocable: true,
    disable_model_invocation: false,
  };
}

it("opens inherited packages from their owner, read-only even for local writers", async () => {
  h.skills = [skill("org")];
  h.write = true;
  act(() => root.render(<SkillsPage />));
  const card = container.querySelector('[role="button"]')!;
  expect(card.textContent).toContain("rework.inheritedResource: Acme");
  await act(async () => card.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  const dialog = document.querySelector('[role="dialog"]')!;
  expect(dialog.textContent).toContain("rework.inheritedResource: Acme");
  expect(dialog.textContent).toContain("Instructions");
  expect(dialog.textContent).toContain("references/help.md");
  expect(dialog.textContent).not.toContain("rework.spaceSkills.edit");
  expect(dialog.textContent).not.toContain("rework.spaceSkills.remove");
  expect(dialog.textContent).not.toContain("rework.localMarketplace.propose");
  expect(h.detail).toHaveBeenLastCalledWith({ spaceId: "org", skillId: "skill-org" });
});

it("keeps editing available for local skills", async () => {
  h.skills = [skill("space-1")];
  h.write = true;
  act(() => root.render(<SkillsPage />));
  await act(async () =>
    container.querySelector('[role="button"]')!.dispatchEvent(new MouseEvent("click", { bubbles: true })),
  );
  const dialog = document.querySelector('[role="dialog"]')!;
  expect(dialog.textContent).toContain("rework.spaceSkills.edit");
  expect(dialog.textContent).toContain("rework.spaceSkills.remove");
  expect(dialog.textContent).not.toContain("rework.inheritedResource");
});

it("hides a cached inherited catalog when access is refused", () => {
  h.skills = [skill("org")];
  h.failed = true;
  act(() => root.render(<SkillsPage />));
  expect(container.textContent).not.toContain("meeting-notes");
  expect(container.textContent).toContain("rework.manager.unavailable");
});

it("saves skill discoverability together with the edited package", async () => {
  h.skills = [skill("space-1")];
  h.write = true;
  act(() => root.render(<SkillsPage />));
  await act(async () => container.querySelector<HTMLElement>('[role="button"]')!.click());
  const button = (key: string) =>
    [...document.querySelectorAll("button")].find((item) => item.textContent?.endsWith(key))!;
  await act(async () => button("rework.spaceSkills.edit").click());
  const checkbox = document.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
  expect(checkbox.checked).toBe(false);
  await act(async () => checkbox.click());
  await act(async () => button("rework.spaceSkills.save").click());
  expect(h.put).toHaveBeenCalledWith({
    spaceId: "space-1",
    skillId: "skill-space-1",
    putSkill: {
      files: { "SKILL.md": "# Instructions", "references/help.md": "Reference" },
      expected_revision: "r1",
      discoverable: true,
    },
  });
});
