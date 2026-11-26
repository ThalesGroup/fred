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

// The boot script is loaded before the application, including on cached page loads.
export type ThemeClockSample = { date: string; secondsSinceMidnight: number };
export type LocalDaylight = { sunrise: string; sunset: string };

declare global {
  interface Window {
    fredThemeClock?: {
      getSnapshot(): ThemeClockSample;
      subscribe(notify: () => void): () => void;
      setPreview(sample: ThemeClockSample | null): void;
      validSchedule(value: unknown): value is LocalDaylight;
      isScheduledDark(schedule: LocalDaylight): boolean;
      setActiveSchedule(schedule: LocalDaylight | undefined): void;
    };
  }
}
