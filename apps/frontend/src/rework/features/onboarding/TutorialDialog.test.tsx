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

// What these pin: the dialog lists each tab's tours with their progress, a tour whose
// page is elsewhere says where to go instead of starting, and a pick hands the tour
// to the runner and closes the dialog.

import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const restartMock = vi.fn();
let completed: Record<string, number> = {};

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../app/userPreferences", () => ({
  useCurrentUserPreference: () => completed,
  getCurrentUserPreferences: () => ({ completed_tours: completed }),
  persistUserPreference: vi.fn(),
}));
vi.mock("./tourProgress", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./tourProgress")>()),
  restartTutorial: () => restartMock(),
}));
vi.mock("@shared/molecules/Dialog/Dialog", () => ({
  Dialog: ({ children, footerStart }: { children: ReactNode; footerStart?: ReactNode }) => (
    <div role="dialog">
      {children}
      {footerStart}
    </div>
  ),
}));

import { TutorialDialog } from "./TutorialDialog";
import { closeTutorialDialog, clearTourRequest, openTutorialDialog, useTutorialState } from "./tutorialStore";
import { TOUR_ANCHORS } from "./tourAnchors";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;
let state: ReturnType<typeof useTutorialState>;

function StateProbe() {
  state = useTutorialState();
  return null;
}

function render() {
  act(() =>
    root.render(
      <>
        <StateProbe />
        <TutorialDialog site="Acme" />
      </>,
    ),
  );
}

const row = (label: string) =>
  [...container.querySelectorAll<HTMLButtonElement>("li button")].find((button) =>
    button.textContent?.includes(label),
  )!;

beforeEach(() => {
  completed = {};
  restartMock.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => {
    closeTutorialDialog();
    clearTourRequest();
  });
  act(() => root.unmount());
  document.body.innerHTML = "";
});

describe("TutorialDialog", () => {
  it("renders nothing while closed", () => {
    render();
    expect(container.querySelector('[role="dialog"]')).toBeNull();
  });

  it("lists the starter tours with their progress", () => {
    completed = { welcome: 1 };
    act(() => openTutorialDialog("starter"));
    render();

    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(row("rework.onboarding.welcome.label").dataset.done).toBe("true");
    expect(row("rework.onboarding.chat.label").dataset.done).toBeUndefined();
  });

  it("keeps an off-page tour clickable, with no note about where it starts", () => {
    act(() => openTutorialDialog("discover"));
    render();

    const advanced = row("rework.onboarding.advanced-chat.label");
    expect(advanced.disabled).toBe(false);
    expect(advanced.textContent).not.toContain("rework.onboarding.where.chat");
    act(() => advanced.click());
    expect(state.requestedTourId).toBe("advanced-chat");
  });

  it("hands a picked tour to the runner and closes", () => {
    const composer = document.createElement("div");
    composer.dataset.tour = TOUR_ANCHORS.chatComposer;
    composer.getClientRects = () => [new DOMRect(0, 0, 10, 10)] as unknown as DOMRectList;
    document.body.appendChild(composer);
    act(() => openTutorialDialog("discover"));
    render();

    act(() => row("rework.onboarding.advanced-chat.label").click());

    expect(state).toMatchObject({ dialogTab: null, requestedTourId: "advanced-chat" });
  });

  it("lists the wiki tour only where the team has a wiki", () => {
    act(() => openTutorialDialog("discover"));
    render();
    expect(row("rework.onboarding.wiki.label")).toBeUndefined();
    act(() => root.unmount());

    const wikiEntry = document.createElement("a");
    wikiEntry.dataset.tour = TOUR_ANCHORS.navWiki;
    document.body.appendChild(wikiEntry);
    root = createRoot(container);
    render();
    expect(row("rework.onboarding.wiki.label")).toBeDefined();
  });

  it("starts over from the first tour", () => {
    act(() => openTutorialDialog("discover"));
    render();
    const restart = [...container.querySelectorAll("button")].find((button) =>
      button.textContent?.includes("rework.onboarding.dialog.restart"),
    )!;

    act(() => restart.click());

    expect(restartMock).toHaveBeenCalledTimes(1);
    expect(state.dialogTab).toBeNull();
  });
});
