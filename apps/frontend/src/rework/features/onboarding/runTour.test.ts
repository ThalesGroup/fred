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

import { afterEach, describe, expect, it, vi } from "vitest";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import {
  buildTourSteps,
  explanationOnScreen,
  nextStepOnScreen,
  startTour,
  stopTour,
  useTourBlocksSend,
} from "./runTour";
import { TOUR_ANCHORS } from "./tourAnchors";
import type { TourDefinition } from "./tours";

const tour: TourDefinition = {
  id: "demo",
  version: 1,
  steps: [
    { key: "intro", helpPage: "getting-started/first-steps" },
    { key: "home", anchor: TOUR_ANCHORS.navHome },
    { key: "help", anchor: TOUR_ANCHORS.navHelp },
    { key: "profile", anchor: TOUR_ANCHORS.profileMenu },
  ],
};

const t = (key: string, values?: Record<string, string>) => (values?.site ? `${key}<${values.site}>` : key);

function place(anchor: string, visible: boolean): HTMLElement {
  const element = document.createElement("button");
  element.dataset.tour = anchor;
  // jsdom lays nothing out: a visible element is one with a client rect.
  element.getClientRects = () => (visible ? [new DOMRect(0, 0, 10, 10)] : []) as unknown as DOMRectList;
  document.body.appendChild(element);
  return element;
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("buildTourSteps", () => {
  it("skips missing and hidden anchors and keeps centred steps", () => {
    const home = place(TOUR_ANCHORS.navHome, true);
    place(TOUR_ANCHORS.navHelp, false);

    const steps = buildTourSteps(tour, { t });

    expect(steps.map((step) => step.popover?.title)).toEqual([
      "rework.onboarding.demo.intro.title",
      "rework.onboarding.demo.home.title",
    ]);
    expect(steps[0].element).toBeUndefined();
    expect(steps[1].element).toBe(home);
  });

  it("escapes texts and links the Help Center page", () => {
    const steps = buildTourSteps(tour, {
      t,
      values: { site: "<b>Acme</b>" },
      helpHref: (page) => `/app/help/en/${page}`,
    });

    expect(steps[0].popover?.title).toBe("rework.onboarding.demo.intro.title&#60;&#60;b&#62;Acme&#60;/b&#62;&#62;");
    expect(steps[0].popover?.description).toContain('href="/app/help/en/getting-started/first-steps"');
    expect(steps[0].popover?.description).toContain("rework.onboarding.learnMore");
  });
});

describe("guided steps", () => {
  const guided: TourDefinition = {
    id: "guided",
    version: 1,
    steps: [
      { key: "create", anchor: TOUR_ANCHORS.agentCreate, clickToContinue: true },
      { key: "form", anchor: TOUR_ANCHORS.agentFormBody, waitFor: true },
      { key: "submit", anchor: TOUR_ANCHORS.agentModal, waitFor: true },
      { key: "after", anchor: TOUR_ANCHORS.navHome },
    ],
  };

  it("waits for what the click opens and moves on when the user clicks", () => {
    place(TOUR_ANCHORS.agentCreate, true);
    place(TOUR_ANCHORS.navHome, true);

    const steps = buildTourSteps(guided, { t });

    expect(steps).toHaveLength(4);
    expect(steps[0].advanceOn).toBe("click");
    expect(steps[1]).toMatchObject({ element: '[data-tour="agent-form-body"]' });
    expect(steps[1].waitForElement).toBeGreaterThan(0);
  });

  it("offers copyable suggestions; action steps only offer the close cross", () => {
    const form: TourDefinition = {
      id: "form",
      version: 1,
      steps: [
        { key: "name", suggestions: ["name"] },
        { key: "type", anchor: TOUR_ANCHORS.chatComposer, typeToContinue: "/", waitFor: true, keepFocus: true },
        { key: "submit", anchor: TOUR_ANCHORS.agentModal, clickToContinue: true, waitFor: true },
        { key: "optional", anchor: TOUR_ANCHORS.chatSkills, lazy: true },
        { key: "look", anchor: TOUR_ANCHORS.agentAssistant, waitFor: true, lookOnly: true },
        { key: "end" },
      ],
    };
    const [name, type, submit, optional, look, end] = buildTourSteps(form, { t });

    expect(name.popover?.description).toContain("rework.onboarding.form.name.suggest.name.value");
    expect(name.popover?.description).toContain('data-copy-index="0"');
    expect(type.popover?.showButtons).toEqual(["close"]);
    expect(type.advanceOn).toMatchObject({ event: "input" });
    // Typing "/" opens a menu that closes if the popover takes the focus.
    expect(type.focus).toBe("none");
    expect(type.scrollIntoView).toBe(false);
    expect(submit.focus).toBeUndefined();
    expect(submit.popover?.showButtons).toEqual(["close"]);
    expect(submit.advanceOn).toBe("click");
    expect(optional.skipMissingElement).toBe(true);
    expect(look.disableActiveInteraction).toBe(true);
    expect(submit.disableActiveInteraction).toBeUndefined();
    // Only the real last step reads "Done": driver.js would guess it from targets not on screen yet.
    expect(name.popover?.doneBtnText).toBe("rework.onboarding.next");
    expect(end.popover?.doneBtnText).toBeUndefined();
  });

  it("drops the steps whose start condition is false for the current page", () => {
    place(TOUR_ANCHORS.navHome, true);
    const path: TourDefinition = {
      id: "path",
      version: 1,
      steps: [
        { key: "goHome", anchor: TOUR_ANCHORS.navHome, when: (onScreen) => !onScreen(TOUR_ANCHORS.navHome) },
        { key: "next", anchor: TOUR_ANCHORS.navHome, when: (onScreen) => onScreen(TOUR_ANCHORS.navHome) },
      ],
    };

    expect(buildTourSteps(path, { t }).map((step) => step.popover?.title)).toEqual([
      "rework.onboarding.path.next.title",
    ]);
  });

  it("drops the waiting steps when the click they wait on cannot happen", () => {
    place(TOUR_ANCHORS.navHome, true);

    const steps = buildTourSteps(guided, { t });

    expect(steps.map((step) => step.popover?.title)).toEqual(["rework.onboarding.guided.after.title"]);
  });
});

describe("action steps", () => {
  it("move on when their target goes away, e.g. a menu closed by Enter", () => {
    vi.useFakeTimers();
    const menu = place(TOUR_ANCHORS.chatSkills, true);
    const steps = buildTourSteps(
      {
        id: "pick",
        version: 1,
        steps: [{ key: "skill", anchor: TOUR_ANCHORS.chatSkills, clickToContinue: true }, { key: "end" }],
      },
      { t },
    );
    const moveNext = vi.fn();
    const instance = { isActive: () => true, getActiveIndex: () => 0, moveNext };

    steps[0].onHighlighted?.(menu, steps[0], { driver: instance, index: 0 } as never);
    vi.advanceTimersByTime(500);
    expect(moveNext).not.toHaveBeenCalled();
    // A re-render swapping the node keeps the step going.
    menu.remove();
    const rerendered = place(TOUR_ANCHORS.chatSkills, true);
    vi.advanceTimersByTime(500);
    expect(moveNext).not.toHaveBeenCalled();
    // Gone for an instant only (a page settling): the step stays.
    rerendered.remove();
    vi.advanceTimersByTime(250);
    const back = place(TOUR_ANCHORS.chatSkills, true);
    vi.advanceTimersByTime(500);
    expect(moveNext).not.toHaveBeenCalled();
    back.remove();
    vi.advanceTimersByTime(1000);

    expect(moveNext).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("look up later targets when reached: the page re-renders once the user acts", () => {
    const first = place(TOUR_ANCHORS.chatTools, true);
    const steps = buildTourSteps(
      {
        id: "acted",
        version: 1,
        steps: [
          { key: "before", anchor: TOUR_ANCHORS.chatTools },
          { key: "type", anchor: TOUR_ANCHORS.chatComposer, typeToContinue: "/", waitFor: true },
          { key: "after", anchor: TOUR_ANCHORS.chatTools },
          // Absent when the tour starts (no answer yet): not counted, never shown.
          { key: "absent", anchor: TOUR_ANCHORS.chatTrace },
        ],
      },
      { t },
    );
    expect(steps).toHaveLength(3);
    expect(steps[0].element).toBe(first);

    first.remove();
    const rerendered = place(TOUR_ANCHORS.chatTools, true);
    expect((steps[2].element as () => Element)()).toBe(rerendered);
    expect(steps[2].skipMissingElement).toBe(true);
  });

  it("offer the sample download, reuse another tour's texts, and wait for what the user opens", () => {
    vi.useFakeTimers();
    const steps = buildTourSteps(
      {
        id: "rag",
        version: 1,
        steps: [
          { key: "download", download: "aurora-station-discoveries.md" },
          { key: "create", textFrom: "create-agent" },
          { key: "open", continueWhenShown: TOUR_ANCHORS.resourcesUpload },
        ],
      },
      { t },
    );
    expect(steps[0].popover?.description).toContain('href="/tutorial/aurora-station-discoveries.md" download');
    expect(steps[1].popover?.title).toBe("rework.onboarding.create-agent.create.title");
    expect(steps[2].popover?.showButtons).toEqual(["close"]);

    const moveNext = vi.fn();
    steps[2].onHighlighted?.(undefined, steps[2], {
      driver: { isActive: () => true, getActiveIndex: () => 2, moveNext },
      index: 2,
    } as never);
    vi.advanceTimersByTime(500);
    expect(moveNext).not.toHaveBeenCalled();
    place(TOUR_ANCHORS.resourcesUpload, true);
    vi.advanceTimersByTime(500);
    expect(moveNext).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("let a step ended by the user's own validation offer only the close cross", () => {
    const [form] = buildTourSteps(
      {
        id: "form",
        version: 1,
        steps: [{ key: "form", anchor: TOUR_ANCHORS.promptModal, waitFor: true, continueWhenGone: true }],
      },
      { t },
    );
    expect(form.popover?.showButtons).toEqual(["close"]);
    expect(form.onHighlighted).toBeTypeOf("function");
  });

  it("watch every anchored target, not centred steps", () => {
    place(TOUR_ANCHORS.navHome, true);
    const [anchored, centred] = buildTourSteps(
      { id: "info", version: 1, steps: [{ key: "home", anchor: TOUR_ANCHORS.navHome }, { key: "end" }] },
      { t },
    );
    expect(anchored.onHighlighted).toBeTypeOf("function");
    expect(centred.onHighlighted).toBeUndefined();
  });

  it("land on the explanation already on screen when the user acted on their own", () => {
    const steps = buildTourSteps(
      {
        id: "form",
        version: 1,
        steps: [
          { key: "general", anchor: TOUR_ANCHORS.agentFormBody, waitFor: true },
          { key: "promptsTab", anchor: TOUR_ANCHORS.wikiEdit, waitFor: true, clickToContinue: true },
          { key: "instructions", anchor: TOUR_ANCHORS.agentInstructions, waitFor: true },
          { key: "toolsTab", anchor: TOUR_ANCHORS.wikiNewPage, waitFor: true, clickToContinue: true },
          { key: "capabilities", anchor: TOUR_ANCHORS.agentCapabilities, waitFor: true },
        ],
      },
      { t },
    );
    // The user clicked the Prompts tab during "general": its instructions are on screen.
    place(TOUR_ANCHORS.wikiEdit, true);
    place(TOUR_ANCHORS.agentInstructions, true);
    expect(explanationOnScreen(steps, 0)).toBe(2);
    // Never past two actions: capabilities would be a jump too far.
    place(TOUR_ANCHORS.agentCapabilities, true);
    document.querySelector('[data-tour="agent-instructions"]')!.remove();
    expect(explanationOnScreen(steps, 0)).toBeUndefined();
  });

  it("catch up with a user who went faster, never past the next action", () => {
    const steps = buildTourSteps(
      {
        id: "folder",
        version: 1,
        steps: [
          { key: "name", anchor: TOUR_ANCHORS.folderModal, waitFor: true },
          { key: "create", anchor: TOUR_ANCHORS.resourcesNewFolder, waitFor: true, clickToContinue: true },
          { key: "open", anchor: TOUR_ANCHORS.resourcesExplorer, waitFor: true },
          { key: "upload", anchor: TOUR_ANCHORS.resourcesUpload, waitFor: true, clickToContinue: true },
          { key: "later", anchor: TOUR_ANCHORS.agentList, waitFor: true },
        ],
      },
      { t },
    );
    // The dialog closed by its own Create button: the explorer is what is left on screen.
    place(TOUR_ANCHORS.resourcesExplorer, true);
    place(TOUR_ANCHORS.agentList, true);
    expect(nextStepOnScreen(steps, 1)).toBe(2);
    // The next action (upload) is not on screen yet: the agent list beyond it does not count.
    expect(nextStepOnScreen(steps, 2)).toBeUndefined();
    expect(steps[1].onWaitingForElement).toBeTypeOf("function");
  });
});

describe("startTour", () => {
  it("does not start when no step can be shown", () => {
    const onlyAnchored: TourDefinition = { ...tour, steps: tour.steps.slice(1) };
    const onFinish = vi.fn();

    expect(startTour(onlyAnchored, { t, onFinish })).toBe(false);
    expect(onFinish).not.toHaveBeenCalled();
  });
});

describe("useTourBlocksSend", () => {
  it("holds sending back while a tour is on screen", () => {
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    let activeNow = false;
    function Probe() {
      activeNow = useTourBlocksSend();
      return null;
    }
    const root = createRoot(document.createElement("div"));
    act(() => root.render(createElement(Probe)));
    expect(activeNow).toBe(false);

    const centred: TourDefinition = { id: "centred", version: 1, steps: [{ key: "only" }] };
    act(() => {
      startTour(centred, { t, onFinish: vi.fn() });
    });
    expect(activeNow).toBe(true);

    act(() => stopTour("centred"));
    expect(activeNow).toBe(false);

    // A step asking the user to send (the RAG question) lets the chat send.
    const ask: TourDefinition = { id: "ask", version: 1, steps: [{ key: "ask", allowSend: true }] };
    act(() => {
      startTour(ask, { t, onFinish: vi.fn() });
    });
    expect(activeNow).toBe(false);
    act(() => stopTour("ask"));
    expect(activeNow).toBe(false);
    act(() => root.unmount());
  });
});
