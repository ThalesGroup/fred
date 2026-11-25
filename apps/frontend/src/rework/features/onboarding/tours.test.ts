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

// What these pin: every tour is translated in both languages, its ids are ones the
// backend accepts, and every anchor it points at is actually placed in the UI code -
// a refactor that drops an anchor fails here instead of silently shortening the tour.

import { describe, expect, it } from "vitest";
import en from "../../../locales/en/translation.json";
import fr from "../../../locales/fr/translation.json";
import { TOUR_ANCHORS } from "./tourAnchors";
import { LISTED_TOURS, REPLAY_HINT } from "./tours";

const sources = import.meta.glob(["../../**/*.tsx", "!../../**/*.test.tsx", "!./**"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const lookup = (bundle: unknown, path: string): unknown =>
  path.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], bundle);

describe("tutorial tours", () => {
  it("use unique ids the preference API accepts", () => {
    const ids = [...LISTED_TOURS, REPLAY_HINT].map((tour) => tour.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const tour of [...LISTED_TOURS, REPLAY_HINT]) {
      expect(tour.id).toMatch(/^[a-z][a-z0-9-]{0,39}$/);
      expect(tour.version).toBeGreaterThanOrEqual(1);
    }
  });

  it.each([
    ["en", en],
    ["fr", fr],
  ])("have every text in %s", (_lang, bundle) => {
    const keys = [
      "next",
      "previous",
      "done",
      "skip",
      "close",
      "learnMore",
      "gotIt",
      "pending.title",
      "copy",
      "copied",
      "copyFailed",
    ].map((key) => `rework.onboarding.${key}`);
    for (const key of [
      "title",
      "close",
      "restart",
      "tabsAria",
      "tabs.starter",
      "tabs.discover",
      "progress",
      "done",
      "todo",
    ]) {
      keys.push(`rework.onboarding.dialog.${key}`);
    }
    for (const tour of LISTED_TOURS) {
      keys.push(`rework.onboarding.${tour.id}.label`, `rework.onboarding.${tour.id}.summary`);
      if (tour.whereKey) keys.push(tour.whereKey);
      if (tour.doneKey) keys.push(tour.doneKey);
    }
    for (const tour of [...LISTED_TOURS, REPLAY_HINT]) {
      for (const step of tour.steps) {
        const texts = `rework.onboarding.${step.textFrom ?? tour.id}.${step.key}`;
        keys.push(`${texts}.title`, `${texts}.body`);
        for (const field of step.suggestions ?? []) {
          const suggest = `${texts}.suggest.${field}`;
          keys.push(`${suggest}.label`, `${suggest}.value`);
        }
      }
    }
    expect(keys.filter((key) => typeof lookup(bundle, key) !== "string")).toEqual([]);
  });

  it("point only at anchors placed in the UI", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(100);
    const code = Object.values(sources).join("\n");
    const anchorKeys = Object.entries(TOUR_ANCHORS);
    const used = new Set(
      [...LISTED_TOURS, REPLAY_HINT].flatMap((tour) =>
        tour.steps.flatMap((step) => (step.anchor ? [step.anchor] : [])),
      ),
    );
    const missing = anchorKeys
      .filter(([, anchor]) => used.has(anchor))
      .filter(([key]) => !code.includes(`TOUR_ANCHORS.${key}`))
      .map(([key]) => key);
    expect(missing).toEqual([]);
  });
});
