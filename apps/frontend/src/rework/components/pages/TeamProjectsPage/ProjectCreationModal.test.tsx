// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { PendingMember } from "../TeamSettingsPage/SpaceMemberPicker";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  create: vi.fn(),
  upload: vi.fn(),
  showError: vi.fn(),
  retention: { configured_seconds: 7200 as number | null, organization_ceiling_seconds: 86400 as number | null },
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: h.showError }) }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useCreateSpaceMutation: () => [h.create, { isLoading: false }],
  usePutTeamAvatarMutation: () => [h.upload, { isLoading: false }],
}));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useTeamConversationRetentionQuery: () => ({ currentData: h.retention }),
}));
// The picker has its own tests; here it only hands back a selection.
vi.mock("../TeamSettingsPage/SpaceMemberPicker", () => ({
  default: ({
    spaceId,
    source,
    pending,
    onPendingChange,
  }: {
    spaceId: string;
    source: string;
    pending: PendingMember[];
    onPendingChange: (pending: PendingMember[]) => void;
  }) => (
    <div data-picker={`${source}:${spaceId}`}>
      <button onClick={() => onPendingChange([...pending, { user: { id: "carol" }, roles: ["editor"] }])}>
        add-editor
      </button>
      <button onClick={() => onPendingChange([...pending, { user: { id: "bob" }, roles: ["owner", "member"] }])}>
        add-owner
      </button>
    </div>
  ),
}));
vi.mock("@shared/molecules/AvatarUploadCard/AvatarUploadCard", () => ({
  default: ({ onUpload, imageUrl }: { onUpload: (file: File) => Promise<void>; imageUrl?: string }) => (
    <button data-avatar={imageUrl ?? ""} onClick={() => void onUpload(new File(["x"], "a.png", { type: "image/png" }))}>
      pick-avatar
    </button>
  ),
}));
import ProjectCreationModal from "./ProjectCreationModal";

const onClose = vi.fn();
let host: HTMLDivElement;
let root: Root;
const portal = () => document.getElementById("modal-portal")!;
const buttons = () => [...portal().querySelectorAll<HTMLButtonElement>("button")];
const button = (label: string) => buttons().find((node) => node.textContent?.trim().endsWith(label))!;
const sectionItem = (key: string) => button(`rework.projectCreation.sections.${key}`);
const click = async (node: HTMLElement) => act(async () => node.click());
const type = async (field: HTMLInputElement | HTMLTextAreaElement, value: string) =>
  act(async () => {
    const proto = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(field, value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
const fillParameters = async () => {
  await type(portal().querySelector("input")!, "  Tender  ");
  await type(portal().querySelector("textarea")!, "A tender answered by a small group");
};

beforeEach(async () => {
  vi.clearAllMocks();
  h.retention = { configured_seconds: 7200, organization_ceiling_seconds: 86400 };
  h.create.mockReturnValue({ unwrap: () => Promise.resolve({ id: "project-1" }) });
  h.upload.mockReturnValue({ unwrap: () => Promise.resolve() });
  globalThis.URL.createObjectURL = vi.fn(() => "blob:preview");
  globalThis.URL.revokeObjectURL = vi.fn();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () => root.render(<ProjectCreationModal teamId="team-1" teamName="Bid" onClose={onClose} />));
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  document.getElementById("modal-portal")?.remove();
});

it("lists its sections on the side and shows the selected one's form", async () => {
  expect(portal().textContent).toContain("rework.projectCreation.title");
  expect(portal().querySelector("nav")?.getAttribute("aria-label")).toBe("rework.projectCreation.sectionsAria");
  expect(sectionItem("parameters").getAttribute("data-selected")).toBe("true");
  expect(portal().querySelector("textarea")).not.toBeNull();
  expect(portal().querySelector("[data-picker]")).toBeNull();
  await click(sectionItem("members"));
  expect(sectionItem("members").getAttribute("data-selected")).toBe("true");
  expect(portal().querySelector("[data-picker]")?.getAttribute("data-picker")).toBe("roster:team-1");
  expect(portal().querySelector("textarea")).toBeNull();
});

it("refuses to create without parameters and an owner, marking the invalid sections", async () => {
  await click(button("rework.create"));
  expect(h.create).not.toHaveBeenCalled();
  expect(portal().textContent).toContain("rework.projectCreation.validation");
  expect(sectionItem("parameters").querySelector('[aria-hidden="true"]:last-child')).not.toBeNull();
  expect(sectionItem("parameters").getAttribute("data-selected")).toBe("true");

  await fillParameters();
  await click(sectionItem("members"));
  await click(button("add-editor"));
  await click(button("rework.create"));
  expect(h.create).not.toHaveBeenCalled();
  expect(sectionItem("members").getAttribute("data-selected")).toBe("true");
  expect(portal().textContent).toContain("rework.projectCreation.ownerRequired");
});

it("creates the project with its parameters and members, uploads the avatar, then closes", async () => {
  await fillParameters();
  await click(button("pick-avatar"));
  expect(button("pick-avatar").getAttribute("data-avatar")).toBe("blob:preview");
  await click(sectionItem("members"));
  await click(button("add-owner"));
  await click(button("add-editor"));
  await click(button("rework.create"));
  expect(h.create).toHaveBeenCalledWith({
    createSpace: {
      kind: "project",
      parent_id: "team-1",
      name: "Tender",
      description: "A tender answered by a small group",
      visibility: "hidden",
      joining_mode: "invite_only",
      conversation_retention_seconds: undefined,
      members: [
        { user: "bob", roles: ["owner", "member"] },
        { user: "carol", roles: ["editor"] },
      ],
    },
  });
  expect(h.upload).toHaveBeenCalledWith({ id: "project-1", fileUpload: { file: expect.any(File) } });
  expect(onClose).toHaveBeenCalledOnce();
});

it("keeps the surface open on a sibling name conflict and shows it on the parameters", async () => {
  h.create.mockReturnValue({
    unwrap: () => Promise.reject({ status: 409, data: { detail: "a space with this name already exists here" } }),
  });
  await fillParameters();
  await click(sectionItem("members"));
  await click(button("add-owner"));
  await click(button("rework.create"));
  expect(onClose).not.toHaveBeenCalled();
  expect(sectionItem("parameters").getAttribute("data-selected")).toBe("true");
  expect(portal().textContent).toContain("rework.projectParameters.name.alreadyTaken");
});
