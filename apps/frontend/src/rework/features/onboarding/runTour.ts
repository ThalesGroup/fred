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
import { driver, type DriveStep, type Driver, type ElementMissingOpts, type PopoverDOM } from "driver.js";
import "driver.js/dist/driver.css";
import "./onboardingTour.css";
import { tourAnchorSelector, type TourAnchor } from "./tourAnchors";
import type { TourDefinition, TourStep } from "./tours";

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

/** Whether the tour can play on the current page: it has no page, or its page anchor is on screen. */
export function isTourAvailable(tour: TourDefinition, root: ParentNode = document): boolean {
  return !tour.page || findAnchor(tour.page, root) !== undefined;
}

interface Suggestion {
  label: string;
  value: string;
}

// Values the user can copy into the form the step points at (a ready-made example).
function suggestionsHtml(suggestions: Suggestion[], copyLabel: string): string {
  if (suggestions.length === 0) return "";
  const rows = suggestions.map(
    ({ label, value }, index) =>
      `<div class="fred-tour-suggestion"><span class="fred-tour-suggestion-label">${escapeHtml(label)}</span>` +
      `<span class="fred-tour-suggestion-value">${escapeHtml(value)}</span>` +
      `<button type="button" class="fred-tour-copy" data-copy-index="${index}">${escapeHtml(copyLabel)}</button></div>`,
  );
  return `<div class="fred-tour-suggestions">${rows.join("")}</div>`;
}

function wireCopyButtons(dom: PopoverDOM, suggestions: Suggestion[], copied: string, failed: string): void {
  dom.description.querySelectorAll<HTMLButtonElement>("[data-copy-index]").forEach((button) => {
    const original = button.textContent ?? "";
    button.addEventListener("click", () => {
      const value = suggestions[Number(button.dataset.copyIndex)]?.value ?? "";
      const done = (label: string) => {
        button.textContent = label;
        window.setTimeout(() => (button.textContent = original), 1500);
      };
      void navigator.clipboard?.writeText(value).then(
        () => done(copied),
        () => done(failed),
      );
    });
  });
}

// How long a step waits for what the user's action opens (a dialog, its next screen).
const WAIT_FOR_ELEMENT_MS = 10_000;

const moveOnFrom = (instance: Driver, index: number | undefined) =>
  window.setTimeout(() => {
    if (instance.isActive() && instance.getActiveIndex() === index) instance.moveNext();
  }, 0);

// What makes a step move on by itself: a click on its target, or the expected text typed in it.
function advanceOn(step: TourStep): DriveStep["advanceOn"] {
  if (step.typeToContinue) {
    const expected = step.typeToContinue;
    return {
      event: "input",
      when: (target) =>
        ((target.querySelector("textarea") as HTMLTextAreaElement | null)?.value ?? target.textContent ?? "").includes(
          expected,
        ),
    };
  }
  return step.clickToContinue ? "click" : undefined;
}

/**
 * Steps whose anchor is absent or hidden are dropped, so a tour never points at nothing.
 * `waitFor` and `lazy` steps are resolved when reached; waiting ones are dropped too when
 * the click they wait on cannot happen (that click's step was dropped).
 */
export function buildTourSteps(
  tour: TourDefinition,
  { t, values, helpHref }: TourTextOptions,
  root: ParentNode = document,
): DriveStep[] {
  let clickUnavailable = false;
  const onScreen = (anchor: TourAnchor) => findAnchor(anchor, root) !== undefined;
  const steps = tour.steps.flatMap((step): DriveStep[] => {
    if (step.when && !step.when(onScreen)) return [];
    const deferred = step.waitFor || step.lazy;
    if (!step.waitFor) clickUnavailable = false;
    if (step.waitFor && clickUnavailable) return [];
    const element = step.anchor && !deferred ? findAnchor(step.anchor, root) : undefined;
    if (step.anchor && !deferred && !element) {
      if (step.clickToContinue) clickUnavailable = true;
      return [];
    }
    const base = `rework.onboarding.${tour.id}.${step.key}`;
    let description = escapeHtml(t(`${base}.body`, values));
    if (step.helpPage && helpHref) {
      const href = escapeHtml(helpHref(step.helpPage));
      description += `<a class="fred-tour-help" href="${href}" target="_blank">${escapeHtml(t("rework.onboarding.learnMore"))}</a>`;
    }
    const suggestions = (step.suggestions ?? []).map((field) => ({
      label: t(`${base}.suggest.${field}.label`, values),
      value: t(`${base}.suggest.${field}.value`, values),
    }));
    description += suggestionsHtml(suggestions, t("rework.onboarding.copy"));
    const waitsForUser = Boolean(step.clickToContinue || step.typeToContinue);
    const popover = {
      title: escapeHtml(t(`${base}.title`, values)),
      description,
      side: step.side,
      align: "start" as const,
      // A step the user moves on by acting has nothing but the close cross; going back
      // from a waiting step would point at what the opened dialog now covers.
      ...(waitsForUser
        ? { showButtons: ["close" as const] }
        : step.waitFor
          ? { showButtons: ["next" as const, "close" as const] }
          : {}),
      ...(suggestions.length > 0
        ? {
            onPopoverRender: (dom: PopoverDOM) =>
              wireCopyButtons(dom, suggestions, t("rework.onboarding.copied"), t("rework.onboarding.copyFailed")),
          }
        : {}),
    };
    // A waiting target that never shows up is skipped once the wait is over; a clicked
    // target that goes away (dialog closed by Enter, page changed) means the action
    // happened another way. Either way, move on instead of hanging.
    const onElementMissing = (_target: Element | undefined, _step: DriveStep, opts: ElementMissingOpts) => {
      if (opts.cause === "timeout" || waitsForUser) moveOnFrom(opts.driver, opts.index);
    };
    return [
      {
        element: deferred && step.anchor ? tourAnchorSelector(step.anchor) : element,
        ...(step.waitFor ? { waitForElement: WAIT_FOR_ELEMENT_MS } : {}),
        ...(step.lazy ? { skipMissingElement: true } : {}),
        advanceOn: advanceOn(step),
        ...(step.lookOnly ? { disableActiveInteraction: true } : {}),
        onElementMissing,
        popover,
      },
    ];
  });
  // The last step's button says "Done"; every other one says "Next", whatever driver.js
  // guesses from targets that are not on screen yet.
  return steps.map((step, index) =>
    index === steps.length - 1 || !step.popover
      ? step
      : { ...step, popover: { ...step.popover, doneBtnText: t("rework.onboarding.next") } },
  );
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

export const isTourRunning = (tourId: string): boolean => active?.tourId === tourId;

/** Interrupts a running tour (page left, tour no longer due) without marking it done. */
export function stopTour(tourId: string): void {
  if (active?.tourId === tourId) active.driver.destroy();
}
