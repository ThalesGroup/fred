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

import { useSyncExternalStore } from "react";
import type { TourGroup } from "./tours";

// What the profile menu, the dialog and the tour runner share: one dialog, one requested tour.
interface TutorialState {
  /** The dialog's open tab, or null when it is closed. */
  dialogTab: TourGroup | null;
  /** A tour the user picked in the dialog, waiting for the runner. */
  requestedTourId: string | null;
  /** Bumped on every pick, so picking a pending tour again shows its notice again. */
  requestCount: number;
}

let state: TutorialState = { dialogTab: null, requestedTourId: null, requestCount: 0 };
const listeners = new Set<() => void>();

function update(patch: Partial<TutorialState>): void {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener());
}

export const openTutorialDialog = (tab: TourGroup): void => update({ dialogTab: tab });
export const closeTutorialDialog = (): void => update({ dialogTab: null });
export const requestTour = (tourId: string): void =>
  update({ dialogTab: null, requestedTourId: tourId, requestCount: state.requestCount + 1 });
export const clearTourRequest = (): void => update({ requestedTourId: null });

export function useTutorialState(): TutorialState {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => state,
    () => state,
  );
}
