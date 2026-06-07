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
import { relativeTime, truncate } from "./TaskCard";

const SEC = 1_000;
const MIN = 60 * SEC;
const HOUR = 60 * MIN;

// ── relativeTime ──────────────────────────────────────────────────────────────

describe("relativeTime", () => {
  it("returns 'just now' for less than 60 seconds ago", () => {
    const now = Date.now();
    expect(relativeTime(now - 30 * SEC, now)).toBe("just now");
  });

  it("returns 'just now' at exactly 0 seconds difference", () => {
    const now = Date.now();
    expect(relativeTime(now, now)).toBe("just now");
  });

  it("returns 'just now' at 59 seconds", () => {
    const now = Date.now();
    expect(relativeTime(now - 59 * SEC, now)).toBe("just now");
  });

  it("returns '1 min ago' at exactly 60 seconds", () => {
    const now = Date.now();
    expect(relativeTime(now - 60 * SEC, now)).toBe("1 min ago");
  });

  it("returns correct minute count for multi-minute gaps", () => {
    const now = Date.now();
    expect(relativeTime(now - 5 * MIN, now)).toBe("5 min ago");
  });

  it("returns '59 min ago' just before the hour boundary", () => {
    const now = Date.now();
    expect(relativeTime(now - 59 * MIN, now)).toBe("59 min ago");
  });

  it("returns '1h ago' at exactly one hour", () => {
    const now = Date.now();
    expect(relativeTime(now - HOUR, now)).toBe("1h ago");
  });

  it("returns correct hour count for multi-hour gaps", () => {
    const now = Date.now();
    expect(relativeTime(now - 3 * HOUR, now)).toBe("3h ago");
  });
});

// ── truncate ──────────────────────────────────────────────────────────────────

describe("truncate", () => {
  it("returns the name unchanged when it fits within the limit", () => {
    expect(truncate("short.pdf")).toBe("short.pdf");
  });

  it("returns the name unchanged at exactly the limit length", () => {
    const name = "a".repeat(32);
    expect(truncate(name)).toBe(name);
  });

  it("truncates and appends ellipsis when the name exceeds the limit", () => {
    const name = "a".repeat(33);
    const result = truncate(name);
    expect(result).toHaveLength(32);
    expect(result.endsWith("…")).toBe(true);
  });

  it("respects a custom max parameter", () => {
    const result = truncate("hello world", 8);
    expect(result).toHaveLength(8);
    expect(result.endsWith("…")).toBe(true);
  });
});
