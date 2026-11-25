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

import { getCurrentUserPreferences, persistUserPreference } from "../../../app/userPreferences";
import { STARTER_TOURS, type TourDefinition } from "./tours";
import { openTutorialDialog } from "./tutorialStore";

export type CompletedTours = Record<string, number>;

export function isTourDone(completed: CompletedTours | null | undefined, tour: TourDefinition): boolean {
  return (completed?.[tour.id] ?? 0) >= tour.version;
}

/** The first starter tour still to show, so they play in order across pages. */
export function nextTutorialTour(
  completed: CompletedTours | null | undefined,
  tutorial: readonly TourDefinition[] = STARTER_TOURS,
): TourDefinition | undefined {
  return tutorial.find((tour) => !isTourDone(completed, tour));
}

export function markTourDone(tour: TourDefinition): void {
  const completed = getCurrentUserPreferences().completed_tours ?? {};
  persistUserPreference({ completed_tours: { ...completed, [tour.id]: tour.version } });
}

/** "Skip the tutorial": every starter tour counts as seen, until the user replays it. */
export function skipTutorial(tutorial: readonly TourDefinition[] = STARTER_TOURS): void {
  const completed = { ...(getCurrentUserPreferences().completed_tours ?? {}) };
  for (const tour of tutorial) completed[tour.id] = Math.max(completed[tour.id] ?? 0, tour.version);
  persistUserPreference({ completed_tours: completed });
}

export function restartTutorial(): void {
  persistUserPreference({ completed_tours: {} });
}

/** Profile menu "Tutorial": the starter tab while it has tours left, else what is left to discover. */
export function openTutorial(): void {
  openTutorialDialog(nextTutorialTour(getCurrentUserPreferences().completed_tours) ? "starter" : "discover");
}
