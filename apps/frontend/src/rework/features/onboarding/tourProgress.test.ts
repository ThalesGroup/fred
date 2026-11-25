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

import { beforeEach, describe, expect, it, vi } from "vitest";

const persistMock = vi.fn();
let preferences: Record<string, unknown> = {};

vi.mock("../../../app/userPreferences", () => ({
  getCurrentUserPreferences: () => preferences,
  persistUserPreference: (patch: unknown) => persistMock(patch),
}));

import { isTourDone, markTourDone, nextTutorialTour, restartTutorial, skipTutorial } from "./tourProgress";
import type { TourDefinition } from "./tours";

const first: TourDefinition = { id: "first", version: 2, steps: [] };
const second: TourDefinition = { id: "second", version: 1, steps: [] };

beforeEach(() => {
  persistMock.mockReset();
  preferences = {};
});

describe("tour progress", () => {
  it("counts a tour done only at its current version", () => {
    expect(isTourDone(undefined, first)).toBe(false);
    expect(isTourDone({ first: 1 }, first)).toBe(false);
    expect(isTourDone({ first: 2 }, first)).toBe(true);
  });

  it("plays tutorial tours in order, re-offering a bumped one first", () => {
    const tutorial = [first, second];
    expect(nextTutorialTour({}, tutorial)).toBe(first);
    expect(nextTutorialTour({ first: 2 }, tutorial)).toBe(second);
    expect(nextTutorialTour({ first: 1, second: 1 }, tutorial)).toBe(first);
    expect(nextTutorialTour({ first: 2, second: 1 }, tutorial)).toBeUndefined();
  });

  it("records a finished tour next to the others and restarts from scratch", () => {
    preferences = { completed_tours: { other: 3 } };

    markTourDone(first);
    restartTutorial();

    expect(persistMock).toHaveBeenNthCalledWith(1, { completed_tours: { other: 3, first: 2 } });
    expect(persistMock).toHaveBeenNthCalledWith(2, { completed_tours: {} });
  });

  it("skips every tutorial tour at once, keeping newer versions", () => {
    preferences = { completed_tours: { first: 5 } };

    skipTutorial([first, second]);

    expect(persistMock).toHaveBeenCalledWith({ completed_tours: { first: 5, second: 1 } });
  });
});
