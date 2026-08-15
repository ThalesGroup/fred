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

import { act, type ComponentProps } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { HitlPrompt } from "./HitlPrompt";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values ? `${key}:${values.used ?? ""}:${values.limit ?? ""}` : key,
    i18n: { language: "en" },
  }),
}));

function buttonTag(html: string, label: string): string {
  const tag = html.match(new RegExp(`<button[^>]*>[^<]*<div[^>]*>${label}</div></button>`))?.[0] ?? "";
  // A regex that stops matching (any Button markup change) would otherwise make
  // every `not.toContain("disabled")` below pass while checking nothing.
  expect(tag).not.toBe("");
  return tag;
}

const event = {
  session_id: "session-1",
  exchange_id: "exchange-1",
  payload: { free_text: true, choices: [{ id: "proceed", label: "Proceed" }] },
};

describe("HitlPrompt chat-input limit", () => {
  it("counts the exact free-text value and blocks only its send action", () => {
    const html = renderToStaticMarkup(
      <HitlPrompt
        event={event}
        onAnswer={() => undefined}
        maxChatInputChars={5}
        freeTextValue=" 🙂🙂🙂🙂🙂"
        onFreeTextChange={() => undefined}
      />,
    );

    expect(html).toContain("chatbot.characterCounter:6:5");
    expect(html).toContain("chatbot.errors.chatInputTooLong::5");
    expect(html).toContain('aria-live="polite"');
    expect(html).not.toContain("maxLength=");
    expect(buttonTag(html, "Proceed")).not.toContain("disabled");
    expect(buttonTag(html, "chatbot\\.sendHitlAnswer")).toContain('disabled=""');
  });

  it("hides the counter while the free text is within the limit", () => {
    const html = renderToStaticMarkup(
      <HitlPrompt
        event={event}
        onAnswer={() => undefined}
        maxChatInputChars={5}
        freeTextValue="🙂🙂🙂🙂🙂"
        onFreeTextChange={() => undefined}
      />,
    );

    expect(html).not.toContain("chatbot.characterCounter");
    expect(html).not.toContain("chatbot.errors.chatInputTooLong");
    expect(buttonTag(html, "chatbot\\.sendHitlAnswer")).not.toContain("disabled");
  });

  it("omits limit UI for an older runtime while preserving free text", () => {
    const html = renderToStaticMarkup(
      <HitlPrompt
        event={event}
        onAnswer={() => undefined}
        freeTextValue="🙂🙂🙂🙂🙂🙂"
        onFreeTextChange={() => undefined}
      />,
    );

    expect(html).not.toContain("chatbot.characterCounter");
    expect(html).toContain("🙂🙂🙂🙂🙂🙂");
  });

  it("localizes both values in the character counter", () => {
    const html = renderToStaticMarkup(
      <HitlPrompt
        event={event}
        onAnswer={() => undefined}
        maxChatInputChars={5_000}
        freeTextValue={"x".repeat(5_001)}
        onFreeTextChange={() => undefined}
      />,
    );

    expect(html).toContain("chatbot.characterCounter:5,001:5,000");
  });

  it("submits only the fixed choice id and never an unrelated free-text draft", () => {
    const onAnswer = vi.fn();
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    try {
      act(() => {
        root.render(
          <HitlPrompt
            event={event}
            onAnswer={onAnswer}
            freeTextValue="unrelated free-text draft"
            onFreeTextChange={() => undefined}
          />,
        );
      });
      const choiceButton = Array.from(container.querySelectorAll("button")).find(
        (button) => button.textContent === "Proceed",
      );
      expect(choiceButton).toBeDefined();

      act(() => {
        choiceButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      });

      expect(onAnswer.mock.calls).toEqual([["proceed"]]);
    } finally {
      act(() => root.unmount());
      container.remove();
    }
  });

  it("requires controlled free-text props together at compile time", () => {
    const baseProps = { event, onAnswer: () => undefined };
    const uncontrolled: ComponentProps<typeof HitlPrompt> = baseProps;
    const controlled: ComponentProps<typeof HitlPrompt> = {
      ...baseProps,
      freeTextValue: "draft",
      onFreeTextChange: () => undefined,
    };

    // @ts-expect-error freeTextValue requires onFreeTextChange.
    const missingChangeHandler: ComponentProps<typeof HitlPrompt> = { ...baseProps, freeTextValue: "draft" };
    // @ts-expect-error onFreeTextChange requires freeTextValue.
    const missingControlledValue: ComponentProps<typeof HitlPrompt> = {
      ...baseProps,
      onFreeTextChange: () => undefined,
    };

    expect([uncontrolled, controlled, missingChangeHandler, missingControlledValue]).toHaveLength(4);
  });
});
