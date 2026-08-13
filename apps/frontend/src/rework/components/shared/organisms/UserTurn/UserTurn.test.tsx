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

// #2359: the user turn's copy affordance is the SAME one as the assistant
// turn's (#2336) — `ActionBar`, content_copy → check, 2s revert. These tests
// pin the parts that made the two diverge in the first place: the icon flip,
// the timing, and the silent-failure contract inherited from the deleted
// useCopyToClipboard hook.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UserTurn } from "./UserTurn";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const writeText = vi.fn<(text: string) => Promise<void>>();

let container: HTMLDivElement;
let root: Root;

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(ui);
  });
}

/** The action's icon glyph, read the way ActionBar renders it. */
function iconOf(button: HTMLButtonElement): string {
  return button.querySelector(".material-symbols-outlined")?.textContent ?? "";
}

function buttons(): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll("button"));
}

/** Copy is always the last action in the bar; edit, when present, precedes it. */
function copyButton(): HTMLButtonElement {
  const all = buttons();
  const button = all[all.length - 1];
  if (!button) throw new Error("no copy button rendered");
  return button;
}

async function click(button: HTMLButtonElement) {
  await act(async () => {
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  writeText.mockReset();
  writeText.mockResolvedValue(undefined);
  Object.defineProperty(globalThis.navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  vi.useRealTimers();
});

describe("UserTurn copy affordance (#2359)", () => {
  it("renders only the copy action when no onEdit is supplied", () => {
    render(<UserTurn text="hello" />);
    expect(buttons()).toHaveLength(1);
    expect(iconOf(copyButton())).toBe("content_copy");
    expect(copyButton().getAttribute("aria-label")).toBe("chatbot.copyMessage.tooltip");
  });

  it("renders the edit action ahead of copy when onEdit is supplied", () => {
    const onEdit = vi.fn();
    render(<UserTurn text="hello" onEdit={onEdit} />);

    const [edit] = buttons();
    expect(buttons()).toHaveLength(2);
    expect(iconOf(edit)).toBe("edit");

    edit.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onEdit).toHaveBeenCalledWith("hello");
  });

  it("copies the message text and flips the button to a check for 2s", async () => {
    render(<UserTurn text="the question" />);

    await click(copyButton());
    expect(writeText).toHaveBeenCalledWith("the question");
    expect(iconOf(copyButton())).toBe("check");
    expect(copyButton().getAttribute("aria-label")).toBe("chatbot.copyMessage.copied");

    // Still confirming just before the 2s mark — same timing as AssistantTurn.
    act(() => {
      vi.advanceTimersByTime(1999);
    });
    expect(iconOf(copyButton())).toBe("check");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(iconOf(copyButton())).toBe("content_copy");
  });

  it("stays silent when the clipboard write fails — the icon not flipping IS the feedback", async () => {
    writeText.mockRejectedValue(new Error("not allowed"));
    render(<UserTurn text="hello" />);

    await click(copyButton());
    expect(iconOf(copyButton())).toBe("content_copy");
  });
});
