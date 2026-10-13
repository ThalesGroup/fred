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
  const tag =
    html.match(new RegExp(`<button[^>]*>[^<]*<div[^>]*>(?:<span[^>]*>\\d</span>)?${label}</div></button>`))?.[0] ?? "";
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
  it("shows skip only for an agent question, with no close control", () => {
    const question = { ...event, payload: { ...event.payload, stage: "agent_question" } };
    const questionHtml = renderToStaticMarkup(<HitlPrompt event={question} onAnswer={() => undefined} />);
    expect(questionHtml).toContain("chatbot.skipHitlQuestion");
    expect(questionHtml).toContain('aria-keyshortcuts="Escape"');
    expect(questionHtml).toContain(">ESC</kbd>");
    expect(questionHtml).not.toContain(">close<");
    const approvalHtml = renderToStaticMarkup(<HitlPrompt event={event} onAnswer={() => undefined} />);
    expect(approvalHtml).not.toContain("chatbot.skipHitlQuestion");
  });
});

describe("HitlPrompt question tabs", () => {
  it("scrolls overflowing subjects with the wheel and releases page scrolling at the edge", () => {
    const first = { ...event, payload: { stage: "agent_question", title: "Duration", occurrence_id: "call-a" } };
    const second = { ...event, payload: { stage: "agent_question", title: "Transport", occurrence_id: "call-b" } };
    const container = document.createElement("div");
    const root = createRoot(container);
    act(() => root.render(<HitlPrompt event={first} siblingQuestions={[first, second]} onAnswer={() => undefined} />));
    const strip = container.querySelector('[role="tablist"]')?.parentElement as HTMLDivElement;
    Object.defineProperty(strip, "scrollWidth", { value: 600 });
    Object.defineProperty(strip, "clientWidth", { value: 200 });

    const wheel = new WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY: 100 });
    act(() => strip.dispatchEvent(wheel));
    expect(strip.scrollLeft).toBe(100);
    expect(wheel.defaultPrevented).toBe(true);

    strip.scrollLeft = 400;
    const edgeWheel = new WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY: 100 });
    act(() => strip.dispatchEvent(edgeWheel));
    expect(edgeWheel.defaultPrevented).toBe(false);

    const trackpad = new WheelEvent("wheel", { bubbles: true, cancelable: true, deltaX: -50 });
    act(() => strip.dispatchEvent(trackpad));
    expect(trackpad.defaultPrevented).toBe(false);
    act(() => root.unmount());
  });

  it("uses compact subjects and switches the selected question", () => {
    const first = {
      ...event,
      payload: { stage: "agent_question", title: "Trip duration", question: "How long?", occurrence_id: "call-a" },
    };
    const second = {
      ...event,
      payload: { stage: "agent_question", question: "What budget?", occurrence_id: "call-b" },
    };
    const onSelectQuestion = vi.fn();
    const container = document.createElement("div");
    const root = createRoot(container);
    act(() => {
      root.render(
        <HitlPrompt
          event={first}
          siblingQuestions={[first, second]}
          onSelectQuestion={onSelectQuestion}
          onAnswer={() => undefined}
        />,
      );
    });
    const tabs = container.querySelectorAll('[role="tab"]');
    expect(tabs).toHaveLength(2);
    expect(tabs[0].querySelector("[class*='label']")?.textContent).toBe("Trip duration");
    expect(tabs[0].getAttribute("title")).toBe("Trip duration");
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(tabs[1].querySelector("[class*='label']")?.textContent).toBe("chatbot.hitlQuestionTabFallback 2");
    act(() => (tabs[1] as HTMLButtonElement).click());
    expect(onSelectQuestion).toHaveBeenCalledWith(second);
    act(() => root.unmount());
  });
});

describe("HitlPrompt choice descriptions", () => {
  it("renders each description below its label inside one selectable button", () => {
    const question = {
      ...event,
      payload: {
        stage: "agent_question",
        free_text: false,
        choices: [
          { id: "baguette", label: "Baguette", description: "Pain blanc croustillant" },
          { id: "complet", label: "Pain complet", description: "Riche en fibres" },
        ],
      },
    };
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(<HitlPrompt event={question} onAnswer={() => undefined} />);
    const choiceButtons = Array.from(container.querySelectorAll("button")).filter((button) =>
      button.textContent?.includes("Pain"),
    );
    expect(choiceButtons).toHaveLength(2);
    expect(choiceButtons[0].textContent).toBe("1BaguettePain blanc croustillant");
    expect(choiceButtons[1].textContent).toBe("2Pain completRiche en fibres");
  });
});

describe("HitlPrompt Other answer row", () => {
  it("renders Other as an input field in a fifth row, keeping its label", () => {
    const question = {
      ...event,
      payload: {
        stage: "agent_question",
        free_text: true,
        choices: [
          { id: "one", label: "One" },
          { id: "two", label: "Two" },
          { id: "three", label: "Three" },
          { id: "four", label: "Four" },
        ],
      },
    };
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(<HitlPrompt event={question} onAnswer={() => undefined} />);
    const input = container.querySelector("input");
    expect(input?.getAttribute("placeholder")).toBe("chatbot.hitlOtherAnswerHint");
    expect(input?.parentElement?.tagName).toBe("LABEL");
    expect(input?.parentElement?.textContent).toContain("edit");
    expect(input?.previousElementSibling?.textContent).toBe("chatbot.hitlOtherAnswerPlaceholder");
    const rows = input?.parentElement?.parentElement;
    expect(rows?.children).toHaveLength(5);
    expect(
      Array.from(rows?.children ?? [])
        .slice(0, 4)
        .map((row) => row.textContent),
    ).toEqual(["1One", "2Two", "3Three", "4Four"]);
    expect(rows?.lastElementChild?.contains(input ?? null)).toBe(true);
    expect(container.querySelector("textarea")).toBeNull();
  });

  it("renders question emphasis as Markdown", () => {
    const question = {
      ...event,
      payload: {
        stage: "agent_question",
        free_text: true,
        choices: [
          { id: "train", label: "Train" },
          { id: "plane", label: "Plane" },
        ],
        question: "Dates validées : **20 au 27 décembre**.\n\nPassons aux **transports**.",
      },
    };
    const html = renderToStaticMarkup(<HitlPrompt event={question} onAnswer={() => undefined} />);
    expect(html).toContain("<strong>20 au 27 décembre</strong>");
    expect(html).toContain("<strong>transports</strong>");
    expect(html).not.toContain("**");
  });

  it("keeps the multiline field for a text-only question", () => {
    const question = {
      ...event,
      payload: { stage: "agent_question", free_text: true, choices: [] },
    };
    const html = renderToStaticMarkup(<HitlPrompt event={question} onAnswer={() => undefined} />);
    expect(html).toContain("<textarea");
    expect(html).not.toContain("chatbot.hitlOtherAnswerPlaceholder");
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
    expect(buttons.map((button) => button.textContent)).toEqual([
      "1Accept",
      "2Reject",
      "3chatbot.approveForConversation",
    ]);
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
    const send = buttons.find((button) => button.textContent?.includes("chatbot.sendHitlAnswer"));
    expect(choice).toBeDefined();
    expect(skip).toBeDefined();
    // Skip on the left, the main action last.
    expect(buttons[buttons.length - 1]).toBe(send);
    expect(buttons[buttons.length - 2]).toBe(skip);
    act(() => choice?.click());
    expect(onAnswer).toHaveBeenLastCalledWith("proceed", " note ");
    act(() =>
      container
        .querySelector("input")
        ?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, isComposing: true })),
    );
    expect(onAnswer).toHaveBeenCalledTimes(1);
    act(() =>
      container.querySelector("input")?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
    );
    expect(onAnswer).toHaveBeenLastCalledWith(undefined, " note ");
    act(() => skip?.click());
    expect(onAnswer).toHaveBeenLastCalledWith(undefined, undefined, true);
    act(() => root.unmount());
    container.remove();
  });
});

describe("HitlPrompt staged batch answers", () => {
  it("skips the whole group with Skip all", () => {
    const first = {
      ...event,
      payload: { ...event.payload, stage: "agent_question", occurrence_id: "call-a" },
    };
    const second = {
      ...event,
      payload: { ...event.payload, stage: "agent_question", occurrence_id: "call-b" },
    };
    const container = document.createElement("div");
    const root = createRoot(container);
    const onSkipAll = vi.fn();
    const onStageAnswer = vi.fn();
    act(() =>
      root.render(
        <HitlPrompt
          event={first}
          siblingQuestions={[first, second]}
          onStageAnswer={onStageAnswer}
          onSkipAll={onSkipAll}
          onAnswer={() => undefined}
        />,
      ),
    );
    const buttons = Array.from(container.querySelectorAll("[class*='actions'] button"));
    expect(buttons.map((button) => button.textContent)).toEqual([
      "chatbot.skipAllHitlQuestions",
      "chatbot.sendAllHitlAnswers",
    ]);
    act(() => (buttons[0] as HTMLButtonElement).click());
    expect(onSkipAll).toHaveBeenCalledOnce();
    expect(onStageAnswer).not.toHaveBeenCalled();
    act(() => root.unmount());
  });

  it("advances through choices while keeping every tab editable until Send all", () => {
    const first = {
      ...event,
      payload: { ...event.payload, stage: "agent_question", title: "Trip duration", occurrence_id: "call-a" },
    };
    const second = {
      ...event,
      payload: { ...event.payload, stage: "agent_question", title: "Travel budget", occurrence_id: "call-b" },
    };
    const container = document.createElement("div");
    const root = createRoot(container);
    const onStageAnswer = vi.fn();
    const onSendAll = vi.fn();
    const onAnswer = vi.fn();
    act(() =>
      root.render(
        <HitlPrompt
          event={first}
          siblingQuestions={[first, second]}
          onStageAnswer={onStageAnswer}
          onSendAll={onSendAll}
          onAnswer={onAnswer}
          canSendAll={false}
        />,
      ),
    );
    const choice = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "1Proceed");
    act(() => choice?.click());
    expect(onStageAnswer).toHaveBeenCalledWith("proceed", undefined, false);
    expect(onAnswer).not.toHaveBeenCalled();
    const sendAll = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "chatbot.sendAllHitlAnswers",
    );
    expect(sendAll?.hasAttribute("disabled")).toBe(true);
    act(() =>
      root.render(
        <HitlPrompt
          event={first}
          siblingQuestions={[first, second]}
          onStageAnswer={onStageAnswer}
          onSendAll={onSendAll}
          onAnswer={onAnswer}
          canSendAll
          stagedAnswer={{ answer: "proceed", skipped: false }}
        />,
      ),
    );
    expect(choice?.getAttribute("aria-pressed")).toBe("true");
    act(() =>
      root.render(
        <HitlPrompt
          event={first}
          siblingQuestions={[first, second]}
          onStageAnswer={onStageAnswer}
          onSendAll={onSendAll}
          onAnswer={onAnswer}
          canSendAll
          stagedAnswer={{ answer: "proceed", skipped: false }}
          freeTextValue="Other answer"
        />,
      ),
    );
    expect(choice?.getAttribute("aria-pressed")).toBe("false");
    act(() => sendAll?.click());
    expect(onSendAll).toHaveBeenCalledOnce();
    act(() => root.unmount());
  });
});

describe("HitlPrompt grouped questions", () => {
  const first = { ...event, payload: { ...event.payload, stage: "agent_question", occurrence_id: "call-a" } };
  const second = { ...event, payload: { ...event.payload, stage: "agent_question", occurrence_id: "call-b" } };
  const third = { ...event, payload: { ...event.payload, stage: "agent_question", occurrence_id: "call-c" } };

  function renderGroup(current: typeof first, states: ("waiting" | "answered" | "skipped")[]) {
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(
      <HitlPrompt
        event={current}
        siblingQuestions={[first, second, third]}
        questionStates={states}
        onStageAnswer={() => undefined}
        onAnswer={() => undefined}
      />,
    );
    return container;
  }

  it("gives every tab a state icon with an accessible name", () => {
    const container = renderGroup(first, ["waiting", "answered", "skipped"]);
    const icons = Array.from(container.querySelectorAll('[role="tab"] [role="img"]'));
    expect(icons.map((icon) => icon.textContent)).toEqual([
      "radio_button_unchecked",
      "check_circle",
      "do_not_disturb_on",
    ]);
    expect(icons.map((icon) => icon.getAttribute("aria-label"))).toEqual([
      "chatbot.hitlQuestionState.waiting",
      "chatbot.hitlQuestionState.answered",
      "chatbot.hitlQuestionState.skipped",
    ]);
    const tabs = Array.from(container.querySelectorAll('[role="tab"]'));
    expect(tabs.map((tab) => tab.getAttribute("data-hitl-state"))).toEqual(["waiting", "answered", "skipped"]);
  });

  it("offers Skip as the last choice and Confirm for typed text, with no Next action", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const onStageAnswer = vi.fn();
    const render = (current: Parameters<typeof HitlPrompt>[0]["event"], freeTextValue = "") =>
      act(() =>
        root.render(
          <HitlPrompt
            event={current}
            siblingQuestions={[first, second, third]}
            onStageAnswer={onStageAnswer}
            onAnswer={() => undefined}
            freeTextValue={freeTextValue}
          />,
        ),
      );
    render(first);
    const rows = Array.from(container.querySelector("[class*='choices']")?.children ?? []);
    const skip = rows[rows.length - 1] as HTMLButtonElement;
    expect(skip.textContent).toBe("ESCchatbot.skipHitlQuestion");
    expect(skip.getAttribute("aria-keyshortcuts")).toBe("Escape");
    expect(container.textContent).not.toContain("chatbot.validateHitlAnswer");
    act(() => skip.click());
    expect(onStageAnswer).toHaveBeenLastCalledWith(undefined, undefined, true);

    render(first, "Lyon");
    // Picking a choice replaces a typed Other answer: the field is cleared and only the choice is staged.
    const onFreeTextChange = vi.fn();
    act(() =>
      root.render(
        <HitlPrompt
          event={first}
          siblingQuestions={[first, second, third]}
          onStageAnswer={onStageAnswer}
          onAnswer={() => undefined}
          freeTextValue="Lyon"
          onFreeTextChange={onFreeTextChange}
        />,
      ),
    );
    act(() => (container.querySelector('[aria-keyshortcuts="1"]') as HTMLButtonElement).click());
    expect(onFreeTextChange).toHaveBeenLastCalledWith("");
    expect(onStageAnswer).toHaveBeenLastCalledWith("proceed", undefined, false);
    render(first, "Lyon");
    const confirm = container.querySelector(
      'label button[aria-label="chatbot.validateHitlAnswer"]',
    ) as HTMLButtonElement;
    act(() => confirm.click());
    expect(onStageAnswer).toHaveBeenLastCalledWith(undefined, "Lyon", false);

    const openQuestion = { ...event, payload: { stage: "agent_question", free_text: true, occurrence_id: "call-d" } };
    render(openQuestion, "A long answer");
    const labels = Array.from(container.querySelectorAll("button")).map((button) => button.textContent);
    expect(container.querySelector('button[aria-label="chatbot.validateHitlAnswer"]')).not.toBeNull();
    expect(labels).toContain("ESCchatbot.skipHitlQuestion");
    expect(labels).not.toContain("chatbot.nextHitlQuestion");

    // A validated text shows a success check instead of the button, until it is edited.
    const validated = (text: string) =>
      act(() =>
        root.render(
          <HitlPrompt
            event={openQuestion}
            siblingQuestions={[openQuestion, second]}
            onStageAnswer={onStageAnswer}
            onAnswer={() => undefined}
            stagedAnswer={{ answer: undefined, freeText: "A long answer", skipped: false }}
            freeTextValue={text}
          />,
        ),
      );
    // A selected choice ends with the same success check.
    act(() =>
      root.render(
        <HitlPrompt
          event={first}
          siblingQuestions={[first, second, third]}
          onStageAnswer={onStageAnswer}
          onAnswer={() => undefined}
          stagedAnswer={{ answer: "proceed", freeText: undefined, skipped: false }}
        />,
      ),
    );
    const picked = container.querySelector('[aria-keyshortcuts="1"]');
    expect(picked?.getAttribute("aria-pressed")).toBe("true");
    expect(picked?.textContent).toContain("check_circle");
    validated("A long answer");
    expect(container.querySelector('[role="img"][aria-label="chatbot.hitlAnswerValidated"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="chatbot.validateHitlAnswer"]')).toBeNull();
    validated("A longer answer");
    expect(container.querySelector('[aria-label="chatbot.hitlAnswerValidated"]')).toBeNull();
    expect(container.querySelector('button[aria-label="chatbot.validateHitlAnswer"]')).not.toBeNull();
    act(() => root.unmount());
    container.remove();
  });
});

describe("HitlPrompt tool approval labels", () => {
  it("colours only the accept and refuse labels", () => {
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
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(<HitlPrompt event={approval} onAnswer={() => undefined} />);
    const [accept, reject, remember] = Array.from(container.querySelectorAll("button"));
    expect(accept.className).toContain("acceptChoice");
    expect(reject.className).toContain("refuseChoice");
    expect(remember.className).not.toMatch(/acceptChoice|refuseChoice/);

    const question = { ...event, payload: { ...event.payload, stage: "agent_question" } };
    container.innerHTML = renderToStaticMarkup(<HitlPrompt event={question} onAnswer={() => undefined} />);
    expect(container.innerHTML).not.toMatch(/acceptChoice|refuseChoice/);
  });
});

describe("HitlPrompt keyboard", () => {
  const press = (key: string, target: EventTarget = document) =>
    act(() => {
      target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    });
  const choices = [
    { id: "a", label: "Alpha" },
    { id: "b", label: "Beta" },
  ];

  it("picks a choice with its number and skips with Escape", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const onAnswer = vi.fn();
    const question = { ...event, payload: { stage: "agent_question", free_text: true, choices } };
    act(() => root.render(<HitlPrompt event={question} onAnswer={onAnswer} />));
    expect(container.querySelectorAll("[class*='choiceBadge']")).toHaveLength(2);
    const heldComposer = document.createElement("textarea");
    document.body.appendChild(heldComposer);
    heldComposer.focus();
    heldComposer.disabled = true;
    press("2", heldComposer);
    expect(onAnswer).toHaveBeenLastCalledWith("b", undefined);
    heldComposer.remove();
    // Focus left on a button outside the card (a trace row that opened the drawer) still counts.
    const traceRow = document.createElement("button");
    document.body.appendChild(traceRow);
    traceRow.focus();
    press("1", traceRow);
    expect(onAnswer).toHaveBeenLastCalledWith("a", undefined);
    traceRow.remove();
    press("9");
    expect(onAnswer).toHaveBeenCalledTimes(2);
    const drawer = document.createElement("aside");
    drawer.dataset.open = "true";
    document.body.appendChild(drawer);
    press("Escape");
    expect(onAnswer).toHaveBeenCalledTimes(2);
    drawer.remove();
    press("Escape");
    expect(onAnswer).toHaveBeenLastCalledWith(undefined, undefined, true);
    act(() => root.unmount());
    container.remove();
  });

  it("ignores keys typed in a field and while busy or read-only", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const onAnswer = vi.fn();
    const question = { ...event, payload: { stage: "agent_question", free_text: true, choices } };
    act(() => root.render(<HitlPrompt event={question} onAnswer={onAnswer} />));
    const input = container.querySelector("input");
    input?.focus();
    press("1", input!);
    press("Escape", input!);
    input?.blur();
    const drawer = document.createElement("aside");
    drawer.dataset.open = "true";
    const drawerButton = document.createElement("button");
    drawer.appendChild(drawerButton);
    document.body.appendChild(drawer);
    drawerButton.focus();
    press("1", drawerButton);
    drawer.remove();
    act(() => root.render(<HitlPrompt event={question} onAnswer={onAnswer} busy />));
    press("1");
    act(() => root.render(<HitlPrompt event={question} onAnswer={onAnswer} readonly />));
    press("1");
    expect(onAnswer).not.toHaveBeenCalled();
    act(() => root.unmount());
    container.remove();
  });

  it("sends all grouped answers with Enter and numbers tool approval choices", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const onSendAll = vi.fn();
    const onAnswer = vi.fn();
    const first = { ...event, payload: { stage: "agent_question", free_text: true, choices, occurrence_id: "q1" } };
    const second = { ...event, payload: { stage: "agent_question", free_text: true, choices, occurrence_id: "q2" } };
    act(() =>
      root.render(
        <HitlPrompt
          event={first}
          siblingQuestions={[first, second]}
          onStageAnswer={vi.fn()}
          onSendAll={onSendAll}
          onAnswer={onAnswer}
          canSendAll
        />,
      ),
    );
    press("Enter");
    expect(onSendAll).toHaveBeenCalledOnce();
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
    press("Escape");
    expect(onAnswer).not.toHaveBeenCalled();
    press("3");
    expect(onAnswer).toHaveBeenLastCalledWith("proceed", undefined, false, true);
    act(() => root.unmount());
    container.remove();
  });
});
