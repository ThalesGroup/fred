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
import { buildTourSteps, startTour } from "./runTour";
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

describe("startTour", () => {
  it("does not start when no step can be shown", () => {
    const onlyAnchored: TourDefinition = { ...tour, steps: tour.steps.slice(1) };
    const onFinish = vi.fn();

    expect(startTour(onlyAnchored, { t, onFinish })).toBe(false);
    expect(onFinish).not.toHaveBeenCalled();
  });
});
