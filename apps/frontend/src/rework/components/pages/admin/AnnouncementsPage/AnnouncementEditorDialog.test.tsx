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

// @vitest-environment happy-dom

// What these pin: the form holds one text map per field and edits one language
// at a time, so the thing most worth proving is that switching language shows
// the other language rather than overwriting the one just typed. Then the two
// guards the backend also enforces — a title and a short description in at
// least one locale — caught here so an admin sees them before submitting, and
// the severity strip exposing its choice so the active segment can carry the
// banner's own colours.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import AnnouncementEditorDialog from "./AnnouncementEditorDialog";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr" } }),
}));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function render(props: Partial<React.ComponentProps<typeof AnnouncementEditorDialog>> = {}) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root!.render(
      <AnnouncementEditorDialog
        open
        announcement={null}
        saving={false}
        onSave={props.onSave ?? (() => {})}
        onCancel={props.onCancel ?? (() => {})}
        {...props}
      />,
    ),
  );
  return document.body;
}

/** React overrides the DOM value setter, so a plain assignment fires nothing. */
function type(field: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const proto = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(field, value);
  act(() => void field.dispatchEvent(new Event("input", { bubbles: true })));
}

// Not `input[0]`: the closable switch is a checkbox and comes first in the DOM.
const titleField = () => document.body.querySelector('input:not([type="checkbox"])') as HTMLInputElement;
const shortField = () => document.body.querySelectorAll("textarea")[0] as HTMLTextAreaElement;
const longField = () => document.body.querySelectorAll("textarea")[1] as HTMLTextAreaElement;
const button = (label: string) =>
  [...document.body.querySelectorAll("button")].find((b) => b.textContent?.includes(label));

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  vi.clearAllMocks();
});

describe("AnnouncementEditorDialog", () => {
  it("keeps one text per language instead of overwriting the previous one", () => {
    // The form edits a map, not a string. Switching to English must reveal an
    // empty English field and leave the French text intact underneath — the
    // whole reason there is a language switch rather than six stacked fields.
    const onSave = vi.fn();
    render({ onSave });
    type(titleField(), "Maintenance");
    type(shortField(), "Coupure dimanche.");

    act(() => button("rework.announcements.locale.en")!.click());
    expect(titleField().value).toBe("");
    type(titleField(), "Maintenance window");

    act(() => button("rework.save")!.click());

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0]).toMatchObject({
      title: { fr: "Maintenance", en: "Maintenance window" },
      description_short: { fr: "Coupure dimanche." },
    });
  });

  it("drops a locale left blank rather than sending an empty string", () => {
    const onSave = vi.fn();
    render({ onSave });
    type(titleField(), "Titre");
    type(shortField(), "Court");
    act(() => button("rework.announcements.locale.en")!.click());
    type(titleField(), "   ");

    act(() => button("rework.save")!.click());

    expect(onSave.mock.calls[0][0].title).toEqual({ fr: "Titre" });
    expect(onSave.mock.calls[0][0].description_long).toEqual({});
  });

  it("opens a new announcement without shouting two errors at the admin", () => {
    // A blank form is not a wrong form. The errors also displace the field
    // hints while showing, so an untouched form would open with no guidance.
    render();

    expect(document.body.textContent).not.toContain("rework.announcements.editor.titleRequired");
    expect(document.body.textContent).not.toContain("rework.announcements.editor.shortRequired");
    expect(document.body.textContent).toContain("rework.announcements.editor.descriptionShortHint");
  });

  it("reports a required field once the admin has left it empty", () => {
    render();

    act(() => void titleField().dispatchEvent(new FocusEvent("focusout", { bubbles: true })));

    expect(document.body.textContent).toContain("rework.announcements.editor.titleRequired");
  });

  it("stops the admin at the length the server would refuse", () => {
    render();

    expect(titleField().maxLength).toBe(200);
    expect(shortField().maxLength).toBe(500);
    expect(longField().maxLength).toBe(20_000);
  });

  it("refuses to save until a title and a short description exist somewhere", () => {
    render();
    const save = button("rework.save") as HTMLButtonElement;

    expect(save.disabled).toBe(true);
    type(titleField(), "Titre");
    expect((button("rework.save") as HTMLButtonElement).disabled).toBe(true);
    type(shortField(), "Court");
    expect((button("rework.save") as HTMLButtonElement).disabled).toBe(false);
  });

  it("never publishes from the editor — enabling is the list's job", () => {
    // Composing must not put a half-reviewed banner in front of every user.
    const onSave = vi.fn();
    render({ onSave });
    type(titleField(), "Titre");
    type(shortField(), "Court");

    act(() => button("rework.save")!.click());

    expect(onSave.mock.calls[0][0].enabled).toBe(false);
  });

  it("exposes the chosen severity so the active segment can take its colours", () => {
    render();

    expect(document.body.querySelector('[data-severity="info"]')).not.toBeNull();

    act(() => button("rework.announcements.severity.warning")!.click());

    expect(document.body.querySelector('[data-severity="warning"]')).not.toBeNull();
  });

  it("edits a long description without requiring one", () => {
    const onSave = vi.fn();
    render({ onSave });
    type(titleField(), "Titre");
    type(shortField(), "Court");
    type(longField(), "Le détail complet.");

    act(() => button("rework.save")!.click());

    expect(onSave.mock.calls[0][0].description_long).toEqual({ fr: "Le détail complet." });
  });
});
