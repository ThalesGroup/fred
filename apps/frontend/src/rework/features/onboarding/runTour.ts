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
import { useSyncExternalStore } from "react";
import {
  driver,
  type DriveStep,
  type Driver,
  type ElementMissingOpts,
  type HookOpts,
  type PopoverDOM,
  type WaitingForElementOpts,
} from "driver.js";
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
// Whether the step on screen lets the user send a chat message (the RAG question).
let sendAllowed = false;
const activeListeners = new Set<() => void>();

function notify(): void {
  activeListeners.forEach((listener) => listener());
}

function setActive(next: { tourId: string; driver: Driver } | null): void {
  active = next;
  if (!next) sendAllowed = false;
  notify();
}

function setSendAllowed(next: boolean): void {
  if (sendAllowed === next) return;
  sendAllowed = next;
  notify();
}

/**
 * True while a tour (or its notice) is on screen and its current step does not ask the
 * user to send a message: the chat holds sending back so a turn never starts mid-tour.
 */
export function useTourBlocksSend(): boolean {
  return useSyncExternalStore(
    (listener) => {
      activeListeners.add(listener);
      return () => activeListeners.delete(listener);
    },
    () => active !== null && !sendAllowed,
    () => false,
  );
}

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

const GONE_POLL_MS = 200;

interface StepData {
  anchor?: TourAnchor;
  /** Anchor whose disappearance moves the tour on (see moveOnWhenGone). */
  watched?: TourAnchor;
  /** The chat may send while this step is on screen. */
  allowSend?: boolean;
  /** The step waits for the user to act (click, type, open something). */
  action: boolean;
}

/**
 * While a step waits for its target, the user may already be further along (they
 * clicked a dialog's own button, pressed Enter): jump to the first later step whose
 * target is on screen, looking no further than the next step that asks for an action.
 */
export function nextStepOnScreen(steps: readonly DriveStep[], from: number): number | undefined {
  for (let index = from + 1; index < steps.length; index += 1) {
    const { anchor, action } = (steps[index].data ?? {}) as Partial<StepData>;
    if (anchor && findAnchor(anchor, document)) return index;
    if (action) return undefined;
  }
  return undefined;
}

function catchUpFrom(steps: readonly DriveStep[]) {
  return (_target: Element | undefined, _step: DriveStep, opts: WaitingForElementOpts): void => {
    const timer = window.setInterval(() => {
      if (opts.signal.aborted || !opts.driver.isActive() || opts.driver.getActiveIndex() !== opts.index) {
        window.clearInterval(timer);
        return;
      }
      const ahead = opts.index === undefined ? undefined : nextStepOnScreen(steps, opts.index);
      if (ahead !== undefined) {
        window.clearInterval(timer);
        opts.driver.moveTo(ahead);
      }
    }, GONE_POLL_MS);
    opts.signal.addEventListener("abort", () => window.clearInterval(timer));
  };
}

/** A sample file shipped under `public/tutorial/`, served next to the app. */
export function tutorialAssetHref(file: string): string {
  const base = ((import.meta.env?.BASE_URL as string | undefined) ?? "/").replace(/\/$/, "");
  return `${base}/tutorial/${file}`;
}

/** Moves the tour on once the user's action makes one of `anchors` appear (e.g. a folder opened). */
function moveOnWhenShown(shown: TourAnchor | TourAnchor[]) {
  const anchors = Array.isArray(shown) ? shown : [shown];
  return (_target: Element | undefined, _step: DriveStep, { driver: instance, index }: HookOpts): void => {
    const timer = window.setInterval(() => {
      if (!instance.isActive() || instance.getActiveIndex() !== index) {
        window.clearInterval(timer);
        return;
      }
      if (anchors.some((anchor) => findAnchor(anchor, document))) {
        window.clearInterval(timer);
        instance.moveNext();
      }
    }, GONE_POLL_MS);
  };
}

/**
 * Moves the tour on as soon as nothing on screen carries `anchor` any more. Checked by
 * anchor, not by node: a re-render that swaps the node must not end the step.
 */
// A page settling (a conversation loading) hides a target for an instant: only a
// target gone for this long counts as closed by the user.
const GONE_FOR_POLLS = 3;

function moveOnWhenGone(anchor: TourAnchor, steps: readonly DriveStep[]) {
  return (_target: Element | undefined, _step: DriveStep, { driver: instance, index }: HookOpts): void => {
    let goneFor = 0;
    const timer = window.setInterval(() => {
      if (!instance.isActive() || instance.getActiveIndex() !== index) {
        window.clearInterval(timer);
        return;
      }
      goneFor = findAnchor(anchor, document) ? 0 : goneFor + 1;
      if (goneFor >= GONE_FOR_POLLS) {
        window.clearInterval(timer);
        const ahead = index === undefined ? undefined : explanationOnScreen(steps, index);
        if (ahead === undefined) instance.moveNext();
        else instance.moveTo(ahead);
      }
    }, GONE_POLL_MS);
  };
}

/**
 * After a target went away because the user acted on their own (clicked a tab, a
 * dialog's button), the first explanation already on screen, past at most one action
 * step — the one they just did. None: the tour simply moves on and catches up.
 */
export function explanationOnScreen(steps: readonly DriveStep[], from: number): number | undefined {
  let actionsPassed = 0;
  for (let index = from + 1; index < steps.length; index += 1) {
    const { anchor, action } = (steps[index].data ?? {}) as Partial<StepData>;
    if (action) {
      actionsPassed += 1;
      if (actionsPassed > 1) return undefined;
      continue;
    }
    if (anchor && findAnchor(anchor, document)) return index;
  }
  return undefined;
}

function watcherOf(step: DriveStep, steps: readonly DriveStep[]): Pick<DriveStep, "onHighlighted"> {
  const { watched } = (step.data ?? {}) as Partial<StepData>;
  return watched ? { onHighlighted: moveOnWhenGone(watched, steps) } : {};
}

/** A start-time element, a selector driver.js waits for, or the newest match looked up when reached. */
function targetOf(step: TourStep, lazy: boolean, element: Element | undefined): DriveStep["element"] {
  const anchor = step.anchor;
  if (!anchor) return undefined;
  if (step.waitFor) return tourAnchorSelector(anchor);
  if (lazy) return () => findAnchor(anchor, document) as Element;
  return element;
}

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
  // Once the user has acted, the page re-renders (a skill inserted, a dialog opened):
  // later targets are looked up when their step comes, never from the start-time page.
  let userActed = false;
  const onScreen = (anchor: TourAnchor) => findAnchor(anchor, root) !== undefined;
  const steps = tour.steps.flatMap((step): DriveStep[] => {
    if (step.when && !step.when(onScreen)) return [];
    // Present now but maybe re-rendered by then: kept (so the step count is right) and
    // looked up again when reached. An explicit `lazy` step may not exist yet at all.
    const lookUpLater = userActed && !step.waitFor && !step.lazy;
    if (lookUpLater && step.anchor && !findAnchor(step.anchor, root)) return [];
    const lazy = Boolean(step.lazy || lookUpLater);
    const deferred = step.waitFor || lazy;
    if (step.clickToContinue || step.typeToContinue) userActed = true;
    if (!step.waitFor) clickUnavailable = false;
    if (step.waitFor && clickUnavailable) return [];
    const element = step.anchor && !deferred ? findAnchor(step.anchor, root) : undefined;
    if (step.anchor && !deferred && !element) {
      if (step.clickToContinue) clickUnavailable = true;
      return [];
    }
    const base = `rework.onboarding.${step.textFrom ?? tour.id}.${step.key}`;
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
    if (step.download) {
      const href = escapeHtml(tutorialAssetHref(step.download));
      description += `<a class="fred-tour-download" href="${href}" download>${escapeHtml(t("rework.onboarding.download"))}</a>`;
    }
    const waitsForUser = Boolean(
      step.clickToContinue || step.typeToContinue || step.continueWhenShown || step.continueWhenGone,
    );
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
    // driver.js does not notice every removal (a menu closed by Enter), so the steps
    // whose target the user's action closes watch it themselves.
    // Any target that goes away moves the tour on: a dialog closed by its own button or
    // by Enter, a form submitted, a page left. The user did the step another way.
    const watchedAnchor = step.continueWhenShown ? undefined : step.anchor;
    return [
      {
        element: targetOf(step, lazy, element),
        ...(step.waitFor ? { waitForElement: WAIT_FOR_ELEMENT_MS } : {}),
        ...(lazy ? { skipMissingElement: true } : {}),
        advanceOn: advanceOn(step),
        ...(step.lookOnly ? { disableActiveInteraction: true } : {}),
        // The composer is always on screen: scrolling to it would only shift the chat.
        ...(step.keepFocus ? { focus: "none" as const, scrollIntoView: false } : {}),
        onElementMissing,
        ...(step.continueWhenShown ? { onHighlighted: moveOnWhenShown(step.continueWhenShown) } : {}),
        popover,
        data: {
          anchor: step.anchor,
          action: waitsForUser,
          watched: watchedAnchor,
          allowSend: step.allowSend,
        } satisfies StepData,
      },
    ];
  });
  return steps.map((step, index) => ({
    ...step,
    ...(step.waitForElement ? { onWaitingForElement: catchUpFrom(steps) } : {}),
    ...watcherOf(step, steps),
    // The last step's button says "Done"; every other one says "Next", whatever driver.js
    // guesses from targets that are not on screen yet.
    ...(index === steps.length - 1 || !step.popover
      ? {}
      : { popover: { ...step.popover, doneBtnText: t("rework.onboarding.next") } }),
  }));
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
    // Scroll only what is off screen: centring would also slide containers whose
    // scroll is hidden (the chat shifted sideways under its command menu).
    scrollIntoView: { block: "nearest", inline: "nearest" },
    stagePadding: 6,
    stageRadius: 8,
    overlayClickBehavior: "none",
    onHighlightStarted: (_element, step) =>
      setSendAllowed(Boolean((step.data as Partial<StepData> | undefined)?.allowSend)),
    onDestroyed: (_element, _step, { reason }) => {
      if (active?.driver === instance) setActive(null);
      if (reason !== "api" && reason !== "replaced") options.onFinish(reason === "done");
    },
  });
  setActive({ tourId: tour.id, driver: instance });
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
      if (active?.driver === instance) setActive(null);
    },
  });
  setActive({ tourId: "notice", driver: instance });
  instance.drive();
}

export const isTourRunning = (tourId: string): boolean => active?.tourId === tourId;

/** Interrupts a running tour (page left, tour no longer due) without marking it done. */
export function stopTour(tourId: string): void {
  if (active?.tourId === tourId) active.driver.destroy();
}
