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

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { RichInputField } from "./RichInputField";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values ? `${key}:${values.used ?? ""}:${values.limit ?? ""}` : key,
    i18n: { language: "en" },
  }),
}));

function sendButtonOpeningTag(html: string): string {
  return html.match(/<button[^>]*aria-label="chatbot\.sendMessage"[^>]*>/)?.[0] ?? "";
}

function textareaOpeningTag(html: string): string {
  return html.match(/<textarea[^>]*>/)?.[0] ?? "";
}

function render(props: { sendDisabled?: boolean; characterCount?: number; characterLimit?: number }): string {
  return renderToStaticMarkup(
    <RichInputField value="hello" onChange={() => undefined} onSend={() => undefined} showSendButton {...props} />,
  );
}

describe("RichInputField send gating", () => {
  it("renders an enabled send button by default", () => {
    const tag = sendButtonOpeningTag(render({}));
    expect(tag).not.toBe("");
    expect(tag).not.toContain("disabled");
  });

  it("disables the send button while sendDisabled is set (e.g. attachments still uploading)", () => {
    const tag = sendButtonOpeningTag(render({ sendDisabled: true }));
    expect(tag).not.toBe("");
    expect(tag).toContain("disabled");
  });

  it("shows no counter at the exact limit and sets no native maxLength", () => {
    const html = render({ characterCount: 5, characterLimit: 5 });
    const textarea = textareaOpeningTag(html);

    expect(html).not.toContain("chatbot.characterCounter");
    expect(html).not.toContain("chatbot.errors.chatInputTooLong");
    expect(html).not.toContain("maxLength=");
    expect(textarea).not.toBe("");
    expect(textarea).not.toContain("aria-invalid");
  });

  it("marks an over-limit draft invalid, reveals the counter, and keeps the full textarea value", () => {
    const html = render({ characterCount: 6, characterLimit: 5, sendDisabled: true });
    const textarea = textareaOpeningTag(html);

    expect(textarea).toContain('aria-invalid="true"');
    expect(html).toContain("chatbot.errors.chatInputTooLong::5");
    expect(html).toContain("chatbot.characterCounter:6:5");
    expect(html).toContain(">hello</textarea>");
    expect(sendButtonOpeningTag(html)).toContain("disabled");
  });

  it("describes the textarea with the notice whenever the runtime publishes a limit", () => {
    // The notice stays mounted below the limit, so the description never
    // points at a removed node when the draft crosses back and forth.
    const describedBy = (html: string) => /aria-describedby="([^"]*)"/.exec(textareaOpeningTag(html))?.[1];

    expect(describedBy(render({ characterCount: 5, characterLimit: 5 }))).toBeDefined();
    expect(describedBy(render({ characterCount: 6, characterLimit: 5 }))).toBe(
      describedBy(render({ characterCount: 5, characterLimit: 5 })),
    );
    expect(describedBy(render({ characterCount: 6 }))).toBeUndefined();
  });
});
