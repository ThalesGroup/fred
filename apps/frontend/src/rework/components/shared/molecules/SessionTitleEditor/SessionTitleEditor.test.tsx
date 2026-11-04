// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { SessionTitleEditor } from "./SessionTitleEditor";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
it("submits an explicit manual choice even when its text is unchanged", async () => {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const commit = vi.fn();
  await act(async () => root.render(<SessionTitleEditor title="Initial" onCommit={commit} />));
  act(() => container.querySelector<HTMLButtonElement>("button")!.click());
  const confirm = [...document.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "chatbot.sessionTitleEditor.save",
  )!;
  await act(async () => confirm.click());
  expect(commit).toHaveBeenCalledExactlyOnceWith("Initial");
  act(() => root.unmount());
  container.remove();
});
