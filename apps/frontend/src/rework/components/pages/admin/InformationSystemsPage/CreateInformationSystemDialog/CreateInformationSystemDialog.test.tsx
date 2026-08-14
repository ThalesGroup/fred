// @vitest-environment happy-dom
// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Regression coverage for the business rule discovered the hard way (#2307):
// `rags_agents/assessment/graph_steps.py`'s `identify_technical_documents_step`
// re-resolves an SI by exact string match against its backing library's name,
// so the SI's `information_system` field must always equal the chosen tag's
// `name` — never an independently typed value. This file asserts the create
// payload always carries the tag's own name, and that a library which already
// backs an SI (or isn't top-level) never appears as a pickable option.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { InformationSystemSummary } from "../../../../../../slices/rags/ragsOpenApi";
import type { TagWithPermissions } from "../../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  tags: { data: undefined, isFetching: false } as { data?: TagWithPermissions[]; isFetching: boolean },
  createInformationSystem: vi.fn(() => ({ unwrap: () => Promise.resolve(undefined) })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key}:${JSON.stringify(opts)}` : key),
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => h.tags,
}));

vi.mock("../../../../../../slices/rags/ragsOpenApi", () => ({
  useCreateInformationSystemRagsServicesV1InformationSystemPostMutation: () => [
    h.createInformationSystem,
    { isLoading: false },
  ],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));

import CreateInformationSystemDialog from "./CreateInformationSystemDialog";

let container: HTMLDivElement;
let root: Root;

function render(props: Partial<React.ComponentProps<typeof CreateInformationSystemDialog>> = {}) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <CreateInformationSystemDialog open existingSystems={[]} onClose={vi.fn()} onCreated={vi.fn()} {...props} />,
    );
  });
}

function tag(over: Partial<TagWithPermissions> & Pick<TagWithPermissions, "id" | "name">): TagWithPermissions {
  return {
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    owner_id: "user-1",
    type: "document",
    item_ids: [],
    ...over,
  } as TagWithPermissions;
}

function existingSystem(name: string): InformationSystemSummary {
  return {
    information_system_uid: `si-${name}`,
    information_system: name,
    library_tag_id: `tag-${name}`,
  } as InformationSystemSummary;
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  h.tags = { data: undefined, isFetching: false };
  h.createInformationSystem.mockClear();
});

// The Dialog molecule itself renders through `Portal` (into a `#modal-portal`
// div appended to `document.body`, same convention as CorpusAuditPage.test.tsx),
// and Select's own option list is a SEPARATE portal straight onto
// `document.body` too — so every lookup here goes through `document`, not the
// local `container`, and the dropdown must be opened before its options exist
// in the DOM at all.
function openSelect() {
  const trigger = document.querySelector("button[aria-haspopup='listbox']");
  expect(trigger).toBeTruthy();
  act(() => {
    trigger?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function openSelectAndPick(optionLabel: string) {
  openSelect();
  const option = Array.from(document.querySelectorAll("[role='option']")).find((el) =>
    el.textContent?.includes(optionLabel),
  );
  expect(option).toBeTruthy();
  act(() => {
    option?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

describe("CreateInformationSystemDialog library picker", () => {
  it("excludes libraries that already back an information system", () => {
    h.tags = {
      data: [tag({ id: "tag-crm", name: "crm-legacy" }), tag({ id: "tag-hr", name: "hr-portal" })],
      isFetching: false,
    };
    render({ existingSystems: [existingSystem("crm-legacy")] });
    openSelect();

    expect(document.body.textContent).not.toContain("crm-legacy");
    expect(document.body.textContent).toContain("hr-portal");
  });

  it("excludes non-top-level libraries (tags with a path)", () => {
    h.tags = {
      data: [tag({ id: "tag-a", name: "top-level" }), tag({ id: "tag-b", name: "nested", path: "Sales/HR" })],
      isFetching: false,
    };
    render();
    openSelect();

    expect(document.body.textContent).toContain("top-level");
    expect(document.body.textContent).not.toContain("nested");
  });
});

describe("CreateInformationSystemDialog submit payload", () => {
  it("creates the SI with information_system locked to the selected tag's own name", async () => {
    h.tags = { data: [tag({ id: "tag-crm", name: "crm-legacy" })], isFetching: false };
    render();

    openSelectAndPick("crm-legacy");

    const confirmButton = Array.from(document.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.informationSystems.create.submit",
    );
    expect(confirmButton?.hasAttribute("disabled")).toBe(false);
    act(() => {
      confirmButton?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(h.createInformationSystem).toHaveBeenCalledWith({
      informationSystemWithoutUid: { information_system: "crm-legacy", library_tag_id: "tag-crm" },
    });
  });

  it("keeps the confirm button disabled until a library is chosen", () => {
    h.tags = { data: [tag({ id: "tag-crm", name: "crm-legacy" })], isFetching: false };
    render();

    const confirmButton = Array.from(document.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.informationSystems.create.submit",
    );
    expect(confirmButton?.hasAttribute("disabled")).toBe(true);
    expect(h.createInformationSystem).not.toHaveBeenCalled();
  });
});
