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

// Manual folder creation mirrors the backend's TagCreate guards (#2355) so
// the user learns BEFORE clicking Create: no new folder inside a parent
// already at MAX_FOLDER_DEPTH (found live: the modal relied on the backend
// 422 alone, which a stale backend doesn't send), and no "/" in a name (a
// slashed name would smuggle several levels past the depth cap in one call).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  createTag: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("@shared/utils/Portal", () => ({ Portal: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({}) }));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useCreateTagKnowledgeFlowV1TagsPostMutation: () => [probe.createTag, { isLoading: false }],
}));

import CreateFolderModal from "./CreateFolderModal";
import { MAX_FOLDER_DEPTH } from "@shared/organisms/DocumentUploadDrawer/droppedPaths";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  probe.createTag.mockClear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function render(ui: React.ReactElement) {
  act(() => {
    root.render(ui);
  });
}

function typeName(value: string) {
  const input = container.querySelector("input");
  if (!input) throw new Error("name input not rendered");
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
  act(() => {
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function createButton(): HTMLButtonElement {
  const btn = [...container.querySelectorAll("button")].find((b) =>
    b.textContent?.includes("rework.resources.folderModal.create"),
  );
  if (!btn) throw new Error("create button not rendered");
  return btn;
}

const parentAtDepth = (depth: number) => Array.from({ length: depth }, (_, i) => `d${i}`).join("/");

describe("CreateFolderModal guards", () => {
  it("blocks creation inside a parent already at MAX_FOLDER_DEPTH, with an inline explanation", () => {
    render(
      <CreateFolderModal open onClose={() => {}} onCreated={() => {}} parentPath={parentAtDepth(MAX_FOLDER_DEPTH)} />,
    );

    expect(container.textContent).toContain("rework.resources.folderModal.tooDeep");
    typeName("valid-name");
    expect(createButton().hasAttribute("disabled")).toBe(true);
    expect(probe.createTag).not.toHaveBeenCalled();
  });

  it("allows creation one level above the cap", () => {
    render(
      <CreateFolderModal
        open
        onClose={() => {}}
        onCreated={() => {}}
        parentPath={parentAtDepth(MAX_FOLDER_DEPTH - 1)}
      />,
    );

    expect(container.textContent).not.toContain("rework.resources.folderModal.tooDeep");
    typeName("valid-name");
    expect(createButton().hasAttribute("disabled")).toBe(false);
  });

  it("rejects a slashed name inline — it would smuggle extra levels past the cap", () => {
    render(<CreateFolderModal open onClose={() => {}} onCreated={() => {}} parentPath="CIR" />);

    typeName("a/b/c");
    expect(container.textContent).toContain("rework.resources.folderModal.nameNoSlash");
    expect(createButton().hasAttribute("disabled")).toBe(true);
  });

  it("does not apply the tag depth cap to the fs mkdir variant (custom onSubmit)", () => {
    render(
      <CreateFolderModal
        open
        onClose={() => {}}
        onCreated={() => {}}
        onSubmit={async () => {}}
        parentPath={parentAtDepth(MAX_FOLDER_DEPTH + 3)}
      />,
    );

    expect(container.textContent).not.toContain("rework.resources.folderModal.tooDeep");
    typeName("valid-name");
    expect(createButton().hasAttribute("disabled")).toBe(false);
  });
});
