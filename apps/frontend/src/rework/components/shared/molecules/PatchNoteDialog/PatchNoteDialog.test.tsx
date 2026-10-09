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

// What these pin: the dialog renders the note as markdown, opens at its top
// and reports the checkbox state however it is closed (Close, Escape or scrim).
// The gate (users) and the admin preview both rely on that contract.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import en from "../../../../../locales/en/translation.json";
import fr from "../../../../../locales/fr/translation.json";
import { PatchNoteDialog } from "./PatchNoteDialog";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
// Records the width and dividers asked of the Dialog: happy-dom drops a `min()` inline width.
const dialogWidth = vi.hoisted(() => ({ value: undefined as number | undefined }));
const dialogDividers = vi.hoisted(() => ({ value: undefined as boolean | undefined }));
vi.mock("../Dialog/Dialog", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../Dialog/Dialog")>();
  return {
    ...actual,
    Dialog: (props: React.ComponentProps<typeof actual.Dialog>) => {
      dialogWidth.value = props.maxWidth;
      dialogDividers.value = props.dividers;
      return <actual.Dialog {...props} />;
    },
  };
});

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function render(
  onClose: (dontShowAgain: boolean) => void,
  markdown = "# Release 3.4\n\n- **Faster** search",
  extra: Partial<React.ComponentProps<typeof PatchNoteDialog>> = {},
) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root!.render(<PatchNoteDialog open title="Version 3.4" markdown={markdown} onClose={onClose} {...extra} />),
  );
  return document.body;
}

const closeButton = () =>
  [...document.body.querySelectorAll("button")].find((b) =>
    b.textContent?.includes("rework.announcements.dialog.close"),
  )!;
const checkbox = () => document.body.querySelector<HTMLInputElement>('input[type="checkbox"]')!;

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  document.getElementById("modal-portal")?.remove();
});

describe("PatchNoteDialog", () => {
  it("renders the markdown body", () => {
    const body = render(() => {});

    expect(body.querySelector("h1")?.textContent).toBe("Release 3.4");
    expect(body.querySelector("li strong")?.textContent).toBe("Faster");
    expect(body.textContent).toContain("rework.announcements.patchNote.dialog.dontShowAgain");
  });

  it("shows the patch note title in the header", () => {
    const body = render(() => {}, "Body");
    const dialog = body.querySelector('[role="dialog"]')!;

    expect(document.getElementById(dialog.getAttribute("aria-labelledby")!)?.textContent).toBe("Version 3.4");
  });

  it("opens links in a new tab", () => {
    const body = render(() => {}, "See [the docs](https://example.com).");
    const link = body.querySelector<HTMLAnchorElement>('[role="dialog"] a')!;

    expect([link.target, link.rel]).toEqual(["_blank", "noopener noreferrer"]);
  });

  it("has no checkbox when the user reopened the note on purpose", () => {
    const onClose = vi.fn();
    render(onClose, undefined, { showDontShowAgain: false });

    expect(document.body.querySelector('input[type="checkbox"]')).toBeNull();
    act(() => closeButton().click());
    expect(onClose).toHaveBeenCalledExactlyOnceWith(false);
  });

  it("is at most 720px wide", () => {
    render(() => {});

    expect(dialogWidth.value).toBe(720);
  });

  it("rules off its header and action bar", () => {
    render(() => {});

    expect(dialogDividers.value).toBe(true);
  });

  it("puts the checkbox in the action bar, right before Close", () => {
    render(() => {});
    const actions = closeButton().parentElement!;
    const focusable = [...actions.querySelectorAll("input, button")];

    expect(actions.contains(checkbox())).toBe(true);
    expect(focusable).toEqual([checkbox(), closeButton()]);
  });

  it("opens focused on the dialog itself, so a link or code block far down does not scroll the note", () => {
    const filler = Array.from({ length: 60 }, (_, i) => `Paragraph ${i}.`).join("\n\n");
    const body = render(
      () => {},
      `# Release 3.4\n\n${filler}\n\n[Docs](https://example.com)\n\n\`\`\`bash\nmake run\n\`\`\`\n`,
    );
    const dialog = body.querySelector<HTMLElement>('[role="dialog"]')!;
    const content = body.querySelector("h1")!.closest<HTMLElement>('[role="dialog"] > div:nth-child(2)')!;

    expect(content.querySelector("a")).not.toBeNull();
    expect(document.activeElement).toBe(dialog);
    expect(content.contains(document.activeElement)).toBe(false);
    expect(content.scrollTop).toBe(0);
  });

  it("reports the checkbox state on close", () => {
    const onClose = vi.fn();
    render(onClose);

    act(() => closeButton().click());
    expect(onClose).toHaveBeenLastCalledWith(false);

    act(() => checkbox().click());
    act(() => closeButton().click());
    expect(onClose).toHaveBeenLastCalledWith(true);
  });

  it("escape with the box ticked records the dismissal", () => {
    const onClose = vi.fn();
    render(onClose);

    act(() => checkbox().click());
    act(() => void window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));

    expect(onClose).toHaveBeenCalledExactlyOnceWith(true);
  });

  it("escape with the box unticked records nothing", () => {
    const onClose = vi.fn();
    render(onClose);

    act(() => void window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));

    expect(onClose).toHaveBeenCalledExactlyOnceWith(false);
  });

  it("the label toggles the checkbox", () => {
    render(() => {});
    const label = document.body.querySelector<HTMLLabelElement>("label[for]")!;

    act(() => label.click());

    expect(checkbox().checked).toBe(true);
  });

  it("has its strings in French and English", () => {
    for (const locale of [fr, en]) {
      const { patchNote, dialog } = locale.rework.announcements;
      expect(patchNote.dialog.dontShowAgain.trim()).not.toBe("");
      expect(dialog.close.trim()).not.toBe("");
    }
  });
});
