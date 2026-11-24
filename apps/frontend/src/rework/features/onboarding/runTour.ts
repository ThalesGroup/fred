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

// The only module that knows driver.js: tours stay plain data (tours.ts).
import { driver, type DriveStep, type Driver } from "driver.js";
import "driver.js/dist/driver.css";
import "./onboardingTour.css";
import { tourAnchorSelector, type TourAnchor } from "./tourAnchors";
import type { TourDefinition } from "./tours";

export type Translate = (key: string, options?: Record<string, string>) => string;

export interface TourTextOptions {
  t: Translate;
  /** Interpolation values shared by every step text (e.g. the site name). */
  values?: Record<string, string>;
  /** Resolves a Help Center page to an href; no link without it. */
  helpHref?: (page: string) => string;
}

let active: { tourId: string; driver: Driver } | null = null;

const escapeHtml = (text: string): string => text.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);

function isVisible(element: Element): boolean {
  return element.getClientRects().length > 0;
}

// The last match: with one anchor per answer (the trace), the newest answer is the one to show.
function findAnchor(anchor: TourAnchor, root: ParentNode): Element | undefined {
  const matches = root.querySelectorAll(tourAnchorSelector(anchor));
  const element = matches[matches.length - 1];
  return element && isVisible(element) ? element : undefined;
}

/** Whether the tour can play on the current page: its opening step is centred or on screen. */
export function isTourAvailable(tour: TourDefinition, root: ParentNode = document): boolean {
  const first = tour.steps[0]?.anchor;
  return !first || findAnchor(first, root) !== undefined;
}

/** Steps whose anchor is absent or hidden are dropped, so a tour never points at nothing. */
export function buildTourSteps(
  tour: TourDefinition,
  { t, values, helpHref }: TourTextOptions,
  root: ParentNode = document,
): DriveStep[] {
  return tour.steps.flatMap((step): DriveStep[] => {
    const element = step.anchor ? findAnchor(step.anchor, root) : undefined;
    if (step.anchor && !element) return [];
    const base = `rework.onboarding.${tour.id}.${step.key}`;
    let description = escapeHtml(t(`${base}.body`, values));
    if (step.helpPage && helpHref) {
      const href = escapeHtml(helpHref(step.helpPage));
      description += `<a class="fred-tour-help" href="${href}" target="_blank">${escapeHtml(t("rework.onboarding.learnMore"))}</a>`;
    }
    return [
      {
        element,
        popover: { title: escapeHtml(t(`${base}.title`, values)), description, side: step.side, align: "start" },
      },
    ];
  });
}

/**
 * Starts a tour. `onFinish` runs when the user completes (`true`) or skips (`false`) it,
 * never when it is interrupted. Only the close button or Escape skips: the dimmed page
 * ignores clicks, so a stray click cannot lose the tutorial.
 */
export function startTour(
  tour: TourDefinition,
  options: TourTextOptions & { onFinish: (completed: boolean) => void },
): boolean {
  const steps = buildTourSteps(tour, options);
  if (steps.length === 0) return false;
  active?.driver.destroy();
  const { t } = options;
  const instance = driver({
    steps,
    showProgress: steps.length > 1,
    progressText: "{{current}} / {{total}}",
    nextBtnText: t("rework.onboarding.next"),
    prevBtnText: t("rework.onboarding.previous"),
    doneBtnText: t(tour.doneKey ?? "rework.onboarding.done"),
    closeBtnLabel: t(tour.group === "starter" ? "rework.onboarding.skip" : "rework.onboarding.close"),
    popoverClass: "fred-tour",
    stagePadding: 6,
    stageRadius: 8,
    overlayClickBehavior: "none",
    onDestroyed: (_element, _step, { reason }) => {
      if (active?.driver === instance) active = null;
      if (reason !== "api" && reason !== "replaced") options.onFinish(reason === "done");
    },
  });
  active = { tourId: tour.id, driver: instance };
  instance.drive();
  return true;
}

/** A single centred popover (no spotlight), e.g. to say where a picked tour will start. */
export function showNotice(title: string, body: string, buttonLabel: string): void {
  active?.driver.destroy();
  const instance = driver({
    steps: [{ popover: { title: escapeHtml(title), description: escapeHtml(body) } }],
    popoverClass: "fred-tour",
    showButtons: ["next", "close"],
    doneBtnText: buttonLabel,
    onDestroyed: () => {
      if (active?.driver === instance) active = null;
    },
  });
  active = { tourId: "notice", driver: instance };
  instance.drive();
}

/** Interrupts a running tour (page left, tour no longer due) without marking it done. */
export function stopTour(tourId: string): void {
  if (active?.tourId === tourId) active.driver.destroy();
}
