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

import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { HitlPrompt } from "./HitlPrompt";

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
  it("counts the exact free-text value and blocks answers carrying it", () => {
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
    expect(buttonTag(html, "Proceed")).toContain('disabled=""');
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
      <HitlPrompt event={event} onAnswer={() => undefined} freeTextValue="🙂🙂🙂🙂🙂🙂" />,
    );

    expect(html).not.toContain("chatbot.characterCounter");
    expect(html).toContain("🙂🙂🙂🙂🙂🙂");
  });
});

describe("HitlPrompt agent questions", () => {
  it("shows skip only for an agent question", () => {
    const question = { ...event, payload: { ...event.payload, stage: "agent_question" } };
    const questionHtml = renderToStaticMarkup(<HitlPrompt event={question} onAnswer={() => undefined} />);
    expect(questionHtml).toContain("chatbot.skipHitlQuestion");
    expect(questionHtml).toContain('aria-label="chatbot.skipHitlQuestionAria"');
    const approvalHtml = renderToStaticMarkup(<HitlPrompt event={event} onAnswer={() => undefined} />);
    expect(approvalHtml).not.toContain("chatbot.skipHitlQuestion");
    expect(approvalHtml).not.toContain("chatbot.skipHitlQuestionAria");
  });
});

describe("HitlPrompt tool approval", () => {
  it("uses the same choice presentation and approves the current call when remembering", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const onAnswer = vi.fn();
    const approval = {
      ...event,
      payload: {
        free_text: false,
        stage: "tool_approval",
        choices: [
          { id: "proceed", label: "Accept" },
          { id: "cancel", label: "Reject" },
        ],
        pending_calls: [{ tool_call_id: "call-1", tool_name: "write_file", args_preview: "{}" }],
      },
    };
    act(() => root.render(<HitlPrompt event={approval} onAnswer={onAnswer} />));
    const buttons = Array.from(container.querySelectorAll("button"));
    expect(buttons.map((button) => button.textContent)).toEqual(["Accept", "Reject", "chatbot.approveForConversation"]);
    expect(container.textContent).not.toContain("chatbot.skipHitlQuestion");
    act(() => buttons[2].click());
    expect(onAnswer).toHaveBeenLastCalledWith("proceed", undefined, false, true);
    act(() => root.unmount());
    container.remove();
  });
});

describe("HitlPrompt answer actions", () => {
  it("sends a choice with its comment, supports Ctrl+Enter, and skips explicitly", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const onAnswer = vi.fn();
    const question = { ...event, payload: { ...event.payload, stage: "agent_question" } };
    act(() => root.render(<HitlPrompt event={question} onAnswer={onAnswer} freeTextValue=" note " />));
    const buttons = Array.from(container.querySelectorAll("button"));
    const choice = buttons.find((button) => button.textContent?.includes("Proceed"));
    const skip = buttons.find((button) => button.textContent?.includes("chatbot.skipHitlQuestion"));
    const close = buttons.find((button) => button.getAttribute("aria-label") === "chatbot.skipHitlQuestionAria");
    expect(choice).toBeDefined();
    expect(skip).toBeDefined();
    expect(close).toBeDefined();
    expect(buttons.at(-1)).toBe(skip);
    act(() => choice?.click());
    expect(onAnswer).toHaveBeenLastCalledWith("proceed", " note ");
    act(() =>
      container
        .querySelector("textarea")
        ?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true })),
    );
    expect(onAnswer).toHaveBeenLastCalledWith(undefined, " note ");
    act(() => skip?.click());
    expect(onAnswer).toHaveBeenLastCalledWith(undefined, undefined, true);
    act(() => close?.click());
    expect(onAnswer).toHaveBeenLastCalledWith(undefined, undefined, true);
    act(() => root.unmount());
    container.remove();
  });
});
