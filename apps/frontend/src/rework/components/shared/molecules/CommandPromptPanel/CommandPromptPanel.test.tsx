// @vitest-environment jsdom
// Copyright Thales 2026 - Licensed under the Apache License, Version 2.0.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import CommandPromptPanel from "./CommandPromptPanel";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
const show = (text: string, status?: "loading" | "error") =>
  act(() =>
    root.render(
      <CommandPromptPanel open onClose={() => {}} text={text} command="summary" promptName="Summary" status={status} />,
    ),
  );

it("shows the prompt's text", () => {
  show("Summarise the document.");
  expect(container.textContent).toContain("Summarise the document.");
  expect(container.textContent).not.toContain("chatbot.commandTurn.previewEmpty");
});

it.each(["", "  \n "])("says the prompt is empty instead of showing a blank panel for %j", (text) => {
  show(text);
  expect(container.querySelector('[role="status"]')?.textContent).toBe("chatbot.commandTurn.previewEmpty");
});

it("keeps the loading and error lines while there is no text yet", () => {
  show("", "loading");
  expect(container.querySelector('[role="status"]')?.textContent).toBe("chatbot.commandTurn.previewLoading");
  show("", "error");
  expect(container.querySelector('[role="status"]')?.textContent).toBe("chatbot.commandTurn.previewError");
});
