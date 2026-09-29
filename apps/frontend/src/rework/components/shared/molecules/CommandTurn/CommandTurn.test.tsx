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

// A command turn shows the command, never the prompt it ran, and opening the
// prompt must not be a click-only path.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts?.command ? `${key}:${opts.command}` : key),
    i18n: { language: "en" },
  }),
}));

import { UserMessage } from "../UserMessage/UserMessage";

const PROMPT_TEXT = "Résume le document et rédige une synthèse de : 33 lignes";

describe("UserMessage with a command descriptor", () => {
  let container: HTMLDivElement;
  let root: Root;

  const render = (node: React.ReactNode) => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(node);
    });
  };

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("shows the command and the appended text, never the prompt", () => {
    render(
      <UserMessage
        text={PROMPT_TEXT}
        command={{ command: "summary", appended_text: "33 lignes" }}
        onOpenCommand={() => {}}
      />,
    );

    // One string, separated by a real space rather than by a flex gap: the two
    // parts are one sentence and have to reflow as one when the bubble narrows.
    expect(container.textContent).toContain("/summary 33 lignes");
    expect(container.textContent).not.toContain("Résume le document");
  });

  it("renders a plain text turn when there is no descriptor", () => {
    render(<UserMessage text={PROMPT_TEXT} />);

    expect(container.textContent).toContain("Résume le document");
    expect(container.querySelector("button")).toBeNull();
  });

  it("is reachable and activatable by keyboard, with a name saying what it opens", () => {
    const onOpenCommand = vi.fn();
    render(<UserMessage text={PROMPT_TEXT} command={{ command: "summary" }} onOpenCommand={onOpenCommand} />);

    const control = container.querySelector("button")!;
    expect(control.getAttribute("aria-label")).toBe("chatbot.commandTurn.open:summary");
    // A real button: Enter and Space activate it without any key handler of
    // our own, which is exactly why it is not a decorated span.
    act(() => {
      control.focus();
      control.click();
    });
    expect(document.activeElement).toBe(control);
    expect(onOpenCommand).toHaveBeenCalledTimes(1);
  });

  it("is inert when nothing can open the prompt", () => {
    render(<UserMessage text={PROMPT_TEXT} command={{ command: "summary" }} />);

    expect(container.querySelector("button")!.disabled).toBe(true);
  });
});
