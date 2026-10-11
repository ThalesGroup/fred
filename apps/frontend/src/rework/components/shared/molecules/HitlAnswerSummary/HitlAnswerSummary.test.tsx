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

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { HitlAnswerSummary } from "./HitlAnswerSummary";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => (values ? `${key}:${values.count}:${values.tools}` : key),
  }),
}));

const base = { question: "Which format?", answer: "PDF", comment: null, skipped: false, choiceId: "pdf", choices: [] };

function render(summary: typeof base & Record<string, unknown>, inTrace = false) {
  const container = document.createElement("div");
  container.innerHTML = renderToStaticMarkup(<HitlAnswerSummary summary={summary} inTrace={inTrace} />);
  return container.firstElementChild as HTMLElement;
}

describe("HitlAnswerSummary", () => {
  it("shows a conversation answer as the person's reply, with the question recalled", () => {
    const card = render({ ...base, comment: "Short version please" });
    expect(card.textContent).toContain("reply");
    expect(card.textContent).toContain("Which format?");
    expect(card.textContent).toContain("PDF");
    expect(card.textContent).toContain("Short version please");
  });

  it("keeps the same reply bubble in the trace, aligned with the steps", () => {
    const card = render(base, true);
    expect(card.className).toContain("inTrace");
    expect(card.textContent).toContain("reply");
    expect(card.textContent).toContain("PDF");
  });

  it("shows a skipped answer as the localized skipped label, without its comment", () => {
    const card = render({ ...base, skipped: true, comment: "ignored" });
    expect(card.textContent).toContain("rework.hitlPrompt.skipped");
    expect(card.textContent).not.toContain("ignored");
  });

  it("recalls the tools and translates the decision of a tool approval", () => {
    const card = render({
      ...base,
      toolNames: ["Sending email", "Updating ticket"],
      answerKey: "rework.hitlPrompt.accepted",
    });
    expect(card.textContent).toContain("rework.hitlPrompt.toolRecall:2:Sending email, Updating ticket");
    expect(card.textContent).toContain("rework.hitlPrompt.accepted");
    expect(card.textContent).not.toContain("Which format?");
  });
});
