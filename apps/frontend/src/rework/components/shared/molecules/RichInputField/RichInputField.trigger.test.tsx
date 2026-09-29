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

// The command trigger seam alone: what RichInputField reports, and that a host
// which does not opt in keeps the field it always had.

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RichInputField, type CommandTriggerBinding } from "./RichInputField";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

let container: HTMLDivElement;
let root: Root;

function Host(props: { trigger?: CommandTriggerBinding; onSend: () => void; hint?: string; sendDisabled?: boolean }) {
  const [value, setValue] = useState("");
  return (
    <RichInputField
      value={value}
      onChange={setValue}
      onSend={props.onSend}
      placeholder={props.hint}
      accessibleDescription={props.hint}
      commandTrigger={props.trigger}
      sendDisabled={props.sendDisabled}
    />
  );
}

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(ui);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function textarea(): HTMLTextAreaElement {
  return container.querySelector("textarea") as HTMLTextAreaElement;
}

// The native setter, then a real input event: React's own value tracker would
// otherwise swallow a change made straight on the element.
function type(text: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set?.call(textarea(), text);
    textarea().dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function pressEnter() {
  act(() => {
    textarea().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
  });
}

function binding(overrides: Partial<CommandTriggerBinding> = {}): CommandTriggerBinding {
  return {
    onQueryChange: vi.fn(),
    onKeyDown: vi.fn(() => false),
    onFocusChange: vi.fn(),
    listboxId: "menu",
    open: false,
    activeDescendantId: null,
    ...overrides,
  };
}

describe("RichInputField command trigger", () => {
  it("reports the query when a slash opens an empty composer", () => {
    const trigger = binding();
    render(<Host trigger={trigger} onSend={vi.fn()} />);

    expect(trigger.onQueryChange).not.toHaveBeenCalled();
    type("/");
    expect(trigger.onQueryChange).toHaveBeenCalledWith("");
  });

  it("reports nothing for a slash inside text", () => {
    const trigger = binding();
    render(<Host trigger={trigger} onSend={vi.fn()} />);

    type("cat /tmp");
    expect(trigger.onQueryChange).not.toHaveBeenCalled();
  });

  it("updates the query as the user types after the slash", () => {
    const trigger = binding();
    render(<Host trigger={trigger} onSend={vi.fn()} />);

    type("/");
    type("/su");
    expect(trigger.onQueryChange).toHaveBeenNthCalledWith(1, "");
    expect(trigger.onQueryChange).toHaveBeenNthCalledWith(2, "su");
  });

  it("closes when the slash is deleted away", () => {
    const trigger = binding();
    render(<Host trigger={trigger} onSend={vi.fn()} />);

    type("/su");
    type("");
    expect(trigger.onQueryChange).toHaveBeenLastCalledWith(null);
  });

  it("stops sending on a key the trigger claims", () => {
    const onSend = vi.fn();
    render(<Host trigger={binding({ onKeyDown: () => true })} onSend={onSend} />);

    type("/summary");
    pressEnter();
    expect(onSend).not.toHaveBeenCalled();
  });

  // Running a command IS sending, so it obeys the same gate as the send button:
  // an attachment still uploading or an over-limit draft must not let Enter
  // through the menu into a send the field itself refuses.
  it("withholds Enter from the menu while sending is blocked, but not the other keys", () => {
    const onKeyDown = vi.fn(() => true);
    const onSend = vi.fn();
    render(<Host trigger={binding({ open: true, onKeyDown })} onSend={onSend} sendDisabled />);

    type("/summary");
    pressEnter();
    expect(onKeyDown).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();

    act(() => {
      textarea().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
    });
    expect(onKeyDown).toHaveBeenCalledOnce();
  });

  it("reports focus leaving and returning, so the menu can follow it", () => {
    const trigger = binding();
    render(<Host trigger={trigger} onSend={vi.fn()} />);

    // The field focuses itself once enabled, so the first report is already in.
    expect(trigger.onFocusChange).toHaveBeenLastCalledWith(true);
    act(() => textarea().blur());
    expect(trigger.onFocusChange).toHaveBeenLastCalledWith(false);
    act(() => textarea().focus());
    expect(trigger.onFocusChange).toHaveBeenLastCalledWith(true);
  });

  it("wires the composer as a combobox only while the menu is open", () => {
    render(<Host trigger={binding({ open: true, activeDescendantId: "opt-1" })} onSend={vi.fn()} />);

    expect(textarea().getAttribute("role")).toBe("combobox");
    expect(textarea().getAttribute("aria-expanded")).toBe("true");
    expect(textarea().getAttribute("aria-controls")).toBe("menu");
    expect(textarea().getAttribute("aria-activedescendant")).toBe("opt-1");
  });

  it("leaves a leading slash as ordinary text when the host does not opt in", () => {
    const onSend = vi.fn();
    render(<Host onSend={onSend} />);

    type("/summary");
    expect(textarea().getAttribute("role")).toBeNull();
    expect(textarea().getAttribute("aria-expanded")).toBeNull();
    pressEnter();
    expect(onSend).toHaveBeenCalledOnce();
  });
});

describe("RichInputField hint", () => {
  // Visibility is the platform's own placeholder rule — empty, focused or not —
  // so what this asserts is that the attribute is set unconditionally rather
  // than only on focus, and that the same sentence is durably announced.
  it("carries the hint as a placeholder and on the accessible description", () => {
    render(<Host onSend={vi.fn()} hint="chatbot.composerPlaceholder" />);

    expect(textarea().getAttribute("placeholder")).toBe("chatbot.composerPlaceholder");
    act(() => textarea().focus());
    expect(textarea().getAttribute("placeholder")).toBe("chatbot.composerPlaceholder");

    const describedBy = textarea().getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    const description = container.querySelector(`#${CSS.escape(describedBy as string)}`);
    expect(description?.textContent).toBe("chatbot.composerPlaceholder");
  });

  it("sets no placeholder and no description when the host passes none", () => {
    render(<Host onSend={vi.fn()} />);

    expect(textarea().getAttribute("placeholder")).toBeNull();
    expect(textarea().getAttribute("aria-describedby")).toBeNull();
  });
});
