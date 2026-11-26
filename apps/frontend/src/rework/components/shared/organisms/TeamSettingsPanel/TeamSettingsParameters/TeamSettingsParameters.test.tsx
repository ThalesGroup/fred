// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { MySpace } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  space: {
    id: "team",
    kind: "team",
    name: "Research",
    description: null,
    parent_id: "org",
    personal_owner: null,
    path: ["org", "team"],
    organization_id: "org",
    roles: ["owner"],
  } as MySpace,
  access: { offered: true, allowed: true, settled: true },
  fetching: false,
  error: false,
  save: vi.fn(),
  upload: vi.fn(() => ({ unwrap: async () => undefined })),
  removeAvatar: vi.fn(() => ({ unwrap: async () => undefined })),
  refetch: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@core/hooks/useSpaceAccess", () => ({ useSpaceAccess: () => h.access }));
vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useTeamMetadataQuery: () => ({
    currentData: { visibility: "hidden", joining_mode: "invite_only" },
    refetch: h.refetch,
  }),
  useGetTeamAvatarQuery: () => ({ currentData: "data:image/png;base64,photo" }),
  usePutTeamAvatarMutation: () => [h.upload, { isLoading: false }],
  useDeleteTeamAvatarMutation: () => [h.removeAvatar, { isLoading: false }],
  useMySpacesQuery: () => ({ currentData: [h.space], isFetching: h.fetching, isError: h.error, refetch: h.refetch }),
  useUpdateTeamParametersMutation: () => [h.save, { isLoading: false }],
}));
vi.mock("@shared/molecules/AvatarUploadCard/AvatarUploadCard", () => ({
  default: ({
    onUpload,
    onDelete,
    uploading,
    deleting,
  }: {
    onUpload: (file: File) => Promise<void>;
    onDelete: () => void;
    uploading: boolean;
    deleting: boolean;
  }) => (
    <>
      <button
        disabled={uploading}
        onClick={() => void onUpload(new File(["photo"], "avatar.png", { type: "image/png" }))}
      >
        upload-avatar
      </button>
      <button disabled={uploading || deleting} onClick={onDelete}>
        delete-avatar
      </button>
    </>
  ),
}));
vi.mock("@shared/molecules/Select/Select", () => ({
  default: ({
    label,
    value,
    options,
    onChange,
    disabled,
  }: {
    label: string;
    value: string;
    options: { value: string; label: string }[];
    onChange: (value: string) => void;
    disabled: boolean;
  }) => (
    <select aria-label={label} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock("./TeamConversationRetention", () => ({ default: () => null }));
import TeamSettingsParameters from "./TeamSettingsParameters";
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  h.space.id = "team";
  h.space.name = "Research";
  h.space.kind = "team";
  h.space.description = null;
  h.access = { offered: true, allowed: true, settled: true };
  h.fetching = false;
  h.error = false;
  vi.clearAllMocks();
  h.save.mockImplementation(({ teamParameters }) => ({
    unwrap: async () => {
      if (teamParameters.description !== undefined) h.space.description = teamParameters.description;
      if (teamParameters.name !== undefined) h.space.name = teamParameters.name;
    },
  }));
  h.refetch.mockReturnValue({ unwrap: async () => [h.space] });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
const render = async (id = "team") => {
  await act(async () => root.render(<TeamSettingsParameters key={id} spaceId={id} />));
};
const field = () => container.querySelector("textarea")!;
const button = () =>
  Array.from(container.querySelectorAll("button"))
    .reverse()
    .find((item) => item.textContent === "common.save")!;
const type = async (value: string) => {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(field(), value);
    field().dispatchEvent(new Event("input", { bubbles: true }));
  });
};

it("saves a trimmed description and refreshes the canonical spaces", async () => {
  await render();
  expect(field().value).toBe("");
  await type("  Research into safer AI systems.  ");
  await act(async () => button().click());
  expect(h.save).toHaveBeenCalledWith({
    id: "team",
    teamParameters: { description: "Research into safer AI systems." },
  });
  expect(h.refetch).toHaveBeenCalled();
  expect(container.textContent).toContain("rework.teamSettings.parameters.description.saved");
});
it("validates Unicode code points and refuses empty, short and oversized drafts", async () => {
  await render();
  for (const value of ["", " ".repeat(30), "short", "x".repeat(501)]) {
    await type(value);
    expect(button().disabled).toBe(true);
  }
  await type("😀".repeat(500));
  expect(button().disabled).toBe(false);
});
it("keeps an unsaved draft mounted through refresh and disables writes until permission is current", async () => {
  await render();
  await type("An unsaved research description.");
  const node = field();
  h.fetching = true;
  h.access.allowed = false;
  h.access.settled = false;
  h.space.description = "Another owner's saved description.";
  await render();
  expect(field()).toBe(node);
  expect(field().value).toBe("An unsaved research description.");
  expect(button().disabled).toBe(true);
  h.fetching = false;
  h.access.settled = true;
  h.access.offered = false;
  await render();
  expect(container.querySelector("textarea")).toBeNull();
  expect(h.save).not.toHaveBeenCalled();
});
it("keeps the draft after a failed save", async () => {
  h.save.mockReturnValue({
    unwrap: async () => {
      throw new Error("refused");
    },
  });
  await render();
  await type("An unsaved research description.");
  await act(async () => button().click());
  expect(field().value).toBe("An unsaved research description.");
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("saveError");
});
it.each(["organization", "personal"] as const)("refuses direct parameter access for %s", async (kind) => {
  h.space.kind = kind;
  await render();
  expect(container.querySelector("textarea")).toBeNull();
  expect(h.save).not.toHaveBeenCalled();
});
it("does not carry a draft to a different space", async () => {
  await render();
  await type("An unsaved research description.");
  h.space = { ...h.space, id: "next" };
  await render("next");
  expect(field().value).toBe("");
});

it("renames without discarding an unsaved description", async () => {
  await render();
  await type("An unsaved research description.");
  const input = container.querySelector("input")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "  New research  ");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () =>
    Array.from(container.querySelectorAll("button"))
      .find((item) => item.textContent === "rework.teamSettings.parameters.name.save")!
      .click(),
  );
  expect(h.save).toHaveBeenCalledWith({ id: "team", teamParameters: { name: "New research" } });
  expect(field().value).toBe("An unsaved research description.");
});

it("uploads and deletes the team photo through the shared avatar transport", async () => {
  await render();
  await act(async () =>
    Array.from(container.querySelectorAll("button"))
      .find((b) => b.textContent === "upload-avatar")!
      .click(),
  );
  expect(h.upload).toHaveBeenCalledWith({ id: "team", fileUpload: { file: expect.any(File) } });
  await act(async () =>
    Array.from(container.querySelectorAll("button"))
      .find((b) => b.textContent === "delete-avatar")!
      .click(),
  );
  expect(h.removeAvatar).toHaveBeenCalledWith({ id: "team" });
});

it("saves discovery settings atomically without altering name or description drafts", async () => {
  await render();
  await type("Keep this draft while changing visibility.");
  const visibility = container.querySelector<HTMLSelectElement>('[aria-label="rework.teamDiscovery.visibility"]')!;
  const joining = container.querySelector<HTMLSelectElement>('[aria-label="rework.teamDiscovery.joiningMode"]')!;
  await act(async () => {
    visibility.value = "visible";
    visibility.dispatchEvent(new Event("change", { bubbles: true }));
    joining.value = "open";
    joining.dispatchEvent(new Event("change", { bubbles: true }));
  });
  const saveSettings = Array.from(container.querySelectorAll("button")).find(
    (item) => item.textContent === "common.save",
  )!;
  await act(async () => saveSettings.click());
  expect(h.save).toHaveBeenCalledWith({ id: "team", teamParameters: { visibility: "visible", joining_mode: "open" } });
  expect(field().value).toBe("Keep this draft while changing visibility.");
});

it("edits a project's parameters with wording addressed to its parent team", async () => {
  h.space.kind = "project";
  await render();
  const visibility = container.querySelector<HTMLSelectElement>('[aria-label="rework.projectParameters.visibility"]')!;
  expect(Array.from(visibility.options).map((option) => option.textContent)).toEqual([
    "rework.projectParameters.hidden",
    "rework.projectParameters.visible",
  ]);
  const joining = container.querySelector<HTMLSelectElement>('[aria-label="rework.teamDiscovery.joiningMode"]')!;
  expect(Array.from(joining.options).map((option) => option.textContent)).toEqual([
    "rework.teamDiscovery.invite_only",
    "rework.projectParameters.open",
  ]);
  expect(container.textContent).toContain("rework.projectParameters.name.save");
  expect(container.textContent).not.toContain("rework.teamSettings.parameters.name.save");
  await type("  What this project delivers for the team.  ");
  await act(async () => button().click());
  expect(h.save).toHaveBeenCalledWith({
    id: "team",
    teamParameters: { description: "What this project delivers for the team." },
  });
});
