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

// What these pin: the inline preview follows what is typed, the save waits for
// a title and a body in the same languages and sends a patch_note payload,
// unsaved changes are never dropped silently, and "preview as users see it"
// opens the users' dialog with the unsaved text.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr" } }),
}));
// CodeMirror is PromptEditor's own concern; a textarea stands in for it here.
vi.mock("@shared/molecules/PromptEditor/PromptEditor", () => ({
  PromptEditor: ({ value, onChange, error }: { value: string; onChange: (next: string) => void; error?: string }) => (
    <div>
      <textarea data-testid="prompt-editor" value={value} onChange={(e) => onChange(e.target.value)} />
      {error && <span data-testid="editor-error">{error}</span>}
    </div>
  ),
}));

import PatchNoteEditorDialog from "./PatchNoteEditorDialog";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function render(props: Partial<React.ComponentProps<typeof PatchNoteEditorDialog>> = {}) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root!.render(
      <PatchNoteEditorDialog
        open
        announcement={null}
        saving={false}
        onSave={props.onSave ?? (() => {})}
        onCancel={props.onCancel ?? (() => {})}
        {...props}
      />,
    ),
  );
}

const editor = () => document.body.querySelector<HTMLTextAreaElement>('[data-testid="prompt-editor"]')!;
const inlinePreview = () => document.body.querySelector('[data-testid="patch-note-inline-preview"]')!;
const button = (label: string) =>
  [...document.body.querySelectorAll("button")].find((b) => b.textContent?.includes(label))!;

function existing(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: "p1",
    kind: "patch_note",
    severity: "info",
    title: { fr: "Version 3.3" },
    description_short: {},
    description_long: { fr: "# Version 3.3" },
    enabled: true,
    dismissible: true,
    content_version: 2,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
    ...overrides,
  };
}

const titleField = () => document.body.querySelector<HTMLInputElement>("input")!;

function typeTitle(value: string) {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(titleField(), value);
  act(() => void titleField().dispatchEvent(new Event("input", { bubbles: true })));
}

function type(value: string) {
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(editor(), value);
  act(() => void editor().dispatchEvent(new Event("input", { bubbles: true })));
}

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  document.getElementById("modal-portal")?.remove();
  vi.clearAllMocks();
});

describe("PatchNoteEditorDialog", () => {
  it("inline preview follows the typed markdown", () => {
    render();
    expect(inlinePreview().textContent).toContain("rework.announcements.patchNote.editor.previewEmpty");

    type("## Version 3.4\n\n- **Faster** search");

    expect(inlinePreview().querySelector("h2")?.textContent).toBe("Version 3.4");
    expect(inlinePreview().querySelector("li strong")?.textContent).toBe("Faster");
  });

  it("inline preview renders like the user dialog, links included", () => {
    render();

    type("See [the docs](https://example.com)");

    expect(inlinePreview().querySelector("a")?.target).toBe("_blank");
  });

  it("opens on the first language that has content", () => {
    render({ announcement: existing({ title: { en: "Release" }, description_long: { en: "# Release" } }) });

    expect(titleField().value).toBe("Release");
  });

  it("refuses a title without a body in the same language", () => {
    render();
    typeTitle("Version 3.4");
    type("# Version 3.4");
    act(() => button("rework.announcements.locale.en").click());
    typeTitle("Release 3.4");

    expect(button("rework.save").disabled).toBe(true);
    act(() => button("rework.announcements.locale.fr").click());
    expect(document.body.textContent).toContain("rework.announcements.patchNote.editor.incomplete");
  });

  it("save is disabled until one locale has a title and a body", () => {
    render();
    expect(button("rework.save").disabled).toBe(true);

    type("   ");
    expect(button("rework.save").disabled).toBe(true);

    type("# Release");
    expect(button("rework.save").disabled).toBe(true);

    typeTitle("   ");
    expect(button("rework.save").disabled).toBe(true);

    typeTitle("Version 3.4");
    expect(button("rework.save").disabled).toBe(false);
  });

  it("title is a plain single-line field bounded like a banner title", () => {
    render();

    expect(titleField().type).toBe("text");
    expect(titleField().maxLength).toBe(200);
    expect(document.body.textContent).toContain("rework.announcements.patchNote.editor.title");
  });

  it("asks for a title once the field is left empty", () => {
    render();
    expect(document.body.textContent).not.toContain("rework.announcements.patchNote.editor.titleRequired");

    act(() => void titleField().dispatchEvent(new FocusEvent("focusout", { bubbles: true })));

    expect(document.body.textContent).toContain("rework.announcements.patchNote.editor.titleRequired");
  });

  it("asks for a body once the field is left empty", () => {
    render();
    expect(document.body.querySelector('[data-testid="editor-error"]')).toBeNull();

    act(() => void editor().dispatchEvent(new FocusEvent("focusout", { bubbles: true })));

    expect(document.body.querySelector('[data-testid="editor-error"]')?.textContent).toBe(
      "rework.announcements.patchNote.editor.bodyRequired",
    );
  });

  it("saves a patch_note payload", () => {
    const onSave = vi.fn();
    render({ onSave, announcement: existing() });

    // The French body is kept while the English one is written.
    act(() => button("rework.announcements.locale.en").click());
    expect(titleField().value).toBe("");
    typeTitle("Release 3.4");
    type("# Release 3.4");
    act(() => button("rework.save").click());

    expect(onSave).toHaveBeenCalledWith(
      {
        kind: "patch_note",
        title: { fr: "Version 3.3", en: "Release 3.4" },
        description_long: { fr: "# Version 3.3", en: "# Release 3.4" },
        severity: "info",
        description_short: {},
        dismissible: true,
        enabled: true,
      },
      false,
    );
  });

  it.each([
    ["Escape", () => act(() => void window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })))],
    ["Cancel", () => act(() => button("rework.cancel").click())],
  ])("%s with unsaved changes asks before discarding them", (_, close) => {
    const onCancel = vi.fn();
    render({ onCancel, announcement: existing() });
    typeTitle("Changed");

    close();
    expect(onCancel).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain("rework.announcements.patchNote.discard.title");

    act(() => button("rework.announcements.patchNote.discard.cancel").click());
    expect(titleField().value).toBe("Changed");

    close();
    act(() => button("rework.announcements.patchNote.discard.confirm").click());
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("closes at once when nothing changed", () => {
    const onCancel = vi.fn();
    render({ onCancel, announcement: existing() });

    act(() => void window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));

    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("offers save and activate on an inactive note only", () => {
    const onSave = vi.fn();
    render({ onSave, announcement: existing({ enabled: false }) });

    act(() => button("rework.announcements.patchNote.editor.saveAndActivate").click());
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ kind: "patch_note" }), true);

    act(() => root!.unmount());
    render({ announcement: existing({ enabled: true }) });
    expect(button("rework.announcements.patchNote.editor.saveAndActivate")).toBeUndefined();
  });

  it("names the active patch note save and activate would switch off", () => {
    const onSave = vi.fn();
    render({ onSave, announcement: existing({ enabled: false }), replacesTitle: "Version 3.2" });

    act(() => button("rework.announcements.patchNote.editor.saveAndActivate").click());
    expect(onSave).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain("rework.announcements.patchNote.activate.message");

    act(() => button("rework.announcements.patchNote.activate.confirm").click());
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ kind: "patch_note" }), true);
  });

  it("editor preview shows the unsaved title and body in the user dialog", () => {
    render();
    typeTitle("Unsaved title");
    type("# Unsaved release\n\nBody text");

    act(() => button("rework.announcements.patchNote.editor.previewAsUsers").click());

    const dialogs = document.body.querySelectorAll('[role="dialog"]');
    // The editor steps aside: only the users' dialog is open.
    expect(dialogs).toHaveLength(1);
    expect(dialogs[0].textContent).toContain("Unsaved title");
    expect(dialogs[0].querySelector("h1")?.textContent).toBe("Unsaved release");

    act(() => button("rework.announcements.dialog.close").click());

    // Back to the editor, with the text still there.
    expect(editor().value).toBe("# Unsaved release\n\nBody text");
  });
});
