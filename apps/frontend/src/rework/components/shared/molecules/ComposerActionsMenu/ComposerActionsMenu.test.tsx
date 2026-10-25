// @vitest-environment happy-dom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { ComposerActionsMenu } from "./ComposerActionsMenu";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | undefined;
let host: HTMLDivElement | undefined;

afterEach(() => {
  act(() => root?.unmount());
  host?.remove();
});

it("moves keyboard focus into a portaled action menu and restores it on Escape", () => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  act(() => {
    root?.render(
      <ComposerActionsMenu portal openAriaLabel="Actions">
        <button type="button">Edit</button>
        <button type="button">Remove</button>
      </ComposerActionsMenu>,
    );
  });
  const trigger = host.querySelector("button")!;
  trigger.focus();
  act(() => trigger.click());
  expect(document.activeElement?.textContent).toBe("Edit");

  act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(document.activeElement).toBe(trigger);
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});

it("restores focus when a portaled action closes the menu", () => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  act(() => {
    root?.render(
      <ComposerActionsMenu portal openAriaLabel="Actions">
        {({ closeMenu }) => (
          <button type="button" onClick={closeMenu}>
            Edit
          </button>
        )}
      </ComposerActionsMenu>,
    );
  });
  const trigger = host.querySelector("button")!;
  act(() => trigger.click());
  const edit = document.querySelector<HTMLButtonElement>('[role="dialog"] button')!;
  expect(document.activeElement).toBe(edit);

  act(() => edit.click());
  expect(document.activeElement).toBe(trigger);
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});
