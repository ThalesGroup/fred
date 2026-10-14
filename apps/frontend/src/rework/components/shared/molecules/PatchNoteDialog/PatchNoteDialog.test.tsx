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

// What these pin: the dialog renders a note as markdown and opens at its top,
// on the first of the notes it is given; with several it lets the user step
// through them from the left of the action bar, and with one it shows no
// navigation. The gate, the profile menu and the admin preview rely on that.

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

const NOTES = [
  { id: "p4", title: "Version 3.4", markdown: "# Release 3.4\n\n- **Faster** search" },
  { id: "p3", title: "Version 3.3", markdown: "# Release 3.3" },
  { id: "p2", title: "Version 3.2", markdown: "# Release 3.2" },
];

function render(onClose: () => void = () => {}, notes = NOTES.slice(0, 1)) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<PatchNoteDialog open notes={notes} onClose={onClose} />));
  return document.body;
}

const note = (markdown: string) => [{ id: "p1", title: "Version 3.4", markdown }];
const closeButton = () =>
  [...document.body.querySelectorAll("button")].find((b) =>
    b.textContent?.includes("rework.announcements.dialog.close"),
  )!;
const arrow = (direction: "newer" | "older") =>
  document.body.querySelector<HTMLButtonElement>(`[aria-label="rework.announcements.patchNote.dialog.${direction}"]`)!;
const position = () => document.body.querySelector("nav > span[aria-live]")?.textContent;
const titleText = () => {
  const dialog = document.body.querySelector('[role="dialog"]')!;
  return document.getElementById(dialog.getAttribute("aria-labelledby")!)?.textContent;
};
const scroller = () => document.body.querySelector<HTMLElement>('[role="dialog"] > div:nth-child(2)')!;

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  document.getElementById("modal-portal")?.remove();
});

describe("PatchNoteDialog", () => {
  it("renders the markdown body, with no don't-show-again control", () => {
    const body = render();

    expect(body.querySelector("h1")?.textContent).toBe("Release 3.4");
    expect(body.querySelector("li strong")?.textContent).toBe("Faster");
    expect(body.querySelector('input[type="checkbox"]')).toBeNull();
  });

  it("shows the patch note title in the header", () => {
    render(() => {}, note("Body"));

    expect(titleText()).toBe("Version 3.4");
  });

  it("opens links in a new tab", () => {
    const body = render(() => {}, note("See [the docs](https://example.com)."));
    const link = body.querySelector<HTMLAnchorElement>('[role="dialog"] a')!;

    expect([link.target, link.rel]).toEqual(["_blank", "noopener noreferrer"]);
  });

  it("is at most 720px wide", () => {
    render();

    expect(dialogWidth.value).toBe(720);
  });

  it("rules off its header and action bar", () => {
    render();

    expect(dialogDividers.value).toBe(true);
  });

  it("opens focused on the dialog itself, so a link or code block far down does not scroll the note", () => {
    const filler = Array.from({ length: 60 }, (_, i) => `Paragraph ${i}.`).join("\n\n");
    const body = render(
      () => {},
      note(`# Release 3.4\n\n${filler}\n\n[Docs](https://example.com)\n\n\`\`\`bash\nmake run\n\`\`\`\n`),
    );
    const dialog = body.querySelector<HTMLElement>('[role="dialog"]')!;

    expect(scroller().querySelector("a")).not.toBeNull();
    expect(document.activeElement).toBe(dialog);
    expect(scroller().contains(document.activeElement)).toBe(false);
    expect(scroller().scrollTop).toBe(0);
  });

  it("closes the same way from Close and from Escape", () => {
    const onClose = vi.fn();
    render(onClose);

    act(() => closeButton().click());
    act(() => void window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));

    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("shows no navigation for a single note", () => {
    render();

    expect(document.body.querySelector("nav")).toBeNull();
    expect(closeButton()).toBeDefined();
  });

  it("opens on the first note, with the navigation at the left of the action bar", () => {
    render(() => {}, NOTES);
    const actions = closeButton().parentElement!;

    expect(titleText()).toBe("Version 3.4");
    expect(position()).toBe("1 / 3");
    // Newer, position, older, then Close: the navigation faces the button.
    expect([...actions.querySelectorAll("button")]).toEqual([arrow("newer"), arrow("older"), closeButton()]);
    expect(arrow("newer").disabled).toBe(true);
    expect(arrow("older").disabled).toBe(false);
  });

  it("moves to the older note and back, replacing title and body", () => {
    render(() => {}, NOTES);

    act(() => arrow("older").click());
    expect([titleText(), position(), document.body.querySelector("h1")?.textContent]).toEqual([
      "Version 3.3",
      "2 / 3",
      "Release 3.3",
    ]);
    expect(arrow("newer").disabled).toBe(false);

    act(() => arrow("newer").click());
    expect([titleText(), position()]).toEqual(["Version 3.4", "1 / 3"]);
  });

  it("disables the button that cannot move further and hands the focus to the other one", () => {
    render(() => {}, NOTES);

    act(() => arrow("older").click());
    arrow("older").focus();
    act(() => arrow("older").click());

    expect(position()).toBe("3 / 3");
    expect(arrow("older").disabled).toBe(true);
    expect(document.activeElement).toBe(arrow("newer"));
  });

  it("shows a note from its top after moving", () => {
    render(() => {}, NOTES);
    scroller().scrollTop = 240;

    act(() => arrow("older").click());

    expect(scroller().scrollTop).toBe(0);
  });

  it("opens on the first note again after it was closed further down", () => {
    const show = (open: boolean) =>
      act(() => root!.render(<PatchNoteDialog open={open} notes={NOTES} onClose={() => {}} />));
    render(() => {}, NOTES);
    act(() => arrow("older").click());

    act(() => closeButton().click());
    show(false);
    show(true);

    expect(position()).toBe("1 / 3");
  });

  it("has its strings in French and English", () => {
    for (const locale of [fr, en]) {
      const { patchNote, dialog } = locale.rework.announcements;
      for (const text of [dialog.close, ...Object.values(patchNote.dialog)]) expect(text.trim()).not.toBe("");
    }
  });
});
