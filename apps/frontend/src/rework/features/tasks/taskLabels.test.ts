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

import { describe, it, expect } from "vitest";
import type { TFunction } from "i18next";
import { relativeTime } from "./taskLabels";

const SEC = 1_000;
const MIN = 60 * SEC;
const HOUR = 60 * MIN;

// Stub mirroring the en bundle's `rework.tasks.time.*` so the assertions test the
// branching in relativeTime, not the contents of the translation file.
const t = ((key: string, opts?: { count?: number }) => {
  if (key.endsWith("justNow")) return "just now";
  if (key.endsWith("minAgo")) return `${opts?.count} min ago`;
  if (key.endsWith("hoursAgo")) return `${opts?.count}h ago`;
  return key;
}) as unknown as TFunction;

describe("relativeTime", () => {
  it("returns 'just now' for less than 60 seconds ago", () => {
    const now = Date.now();
    expect(relativeTime(now - 30 * SEC, t, now)).toBe("just now");
  });

  it("returns 'just now' at exactly 0 seconds difference", () => {
    const now = Date.now();
    expect(relativeTime(now, t, now)).toBe("just now");
  });

  it("returns 'just now' at 59 seconds", () => {
    const now = Date.now();
    expect(relativeTime(now - 59 * SEC, t, now)).toBe("just now");
  });

  it("returns '1 min ago' at exactly 60 seconds", () => {
    const now = Date.now();
    expect(relativeTime(now - 60 * SEC, t, now)).toBe("1 min ago");
  });

  it("returns correct minute count for multi-minute gaps", () => {
    const now = Date.now();
    expect(relativeTime(now - 5 * MIN, t, now)).toBe("5 min ago");
  });

  it("returns '59 min ago' just before the hour boundary", () => {
    const now = Date.now();
    expect(relativeTime(now - 59 * MIN, t, now)).toBe("59 min ago");
  });

  it("returns '1h ago' at exactly one hour", () => {
    const now = Date.now();
    expect(relativeTime(now - HOUR, t, now)).toBe("1h ago");
  });

  it("returns correct hour count for multi-hour gaps", () => {
    const now = Date.now();
    expect(relativeTime(now - 3 * HOUR, t, now)).toBe("3h ago");
  });
});
