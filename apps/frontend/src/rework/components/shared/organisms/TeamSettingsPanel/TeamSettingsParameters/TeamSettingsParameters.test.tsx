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
  refetch: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@core/hooks/useSpaceAccess", () => ({ useSpaceAccess: () => h.access }));
vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({ currentData: [h.space], isFetching: h.fetching, isError: h.error, refetch: h.refetch }),
  useUpdateTeamDescriptionMutation: () => [h.save, { isLoading: false }],
}));
import TeamSettingsParameters from "./TeamSettingsParameters";
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  h.space.id = "team";
  h.space.kind = "team";
  h.space.description = null;
  h.access = { offered: true, allowed: true, settled: true };
  h.fetching = false;
  h.error = false;
  vi.clearAllMocks();
  h.save.mockImplementation(({ teamDescription }) => ({
    unwrap: async () => {
      h.space.description = teamDescription.description;
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
const button = () => container.querySelector("button")!;
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
    teamDescription: { description: "Research into safer AI systems." },
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
it.each(["organization", "project", "personal"] as const)("refuses direct parameter access for %s", async (kind) => {
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
