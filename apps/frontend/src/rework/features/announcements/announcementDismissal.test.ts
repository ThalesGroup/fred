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

// @vitest-environment happy-dom

// The contract this pins: a dismissal is keyed by content version, so editing
// an announcement brings it back for everyone who closed the previous wording,
// and an unusable localStorage degrades to "never dismissed" rather than
// throwing — a banner that shows again is a far better failure than a page
// that does not render.

import { afterEach, describe, expect, it, vi } from "vitest";
import { clearDismissed, isDismissed, markDismissed } from "./announcementDismissal";

afterEach(() => {
  clearDismissed();
  vi.restoreAllMocks();
});

describe("announcement dismissal", () => {
  it("reports nothing dismissed on a fresh browser", () => {
    expect(isDismissed("a1", 1)).toBe(false);
  });

  it("remembers a dismissal", () => {
    markDismissed("a1", 1);

    expect(isDismissed("a1", 1)).toBe(true);
  });

  it("keeps dismissals of different announcements apart", () => {
    markDismissed("a1", 1);

    expect(isDismissed("a2", 1)).toBe(false);
  });

  it("shows the banner again once the content version moves", () => {
    markDismissed("a1", 1);

    expect(isDismissed("a1", 2)).toBe(false);
  });

  it("keeps only the latest entry per announcement", () => {
    markDismissed("a1", 1);
    markDismissed("a1", 2);

    expect(isDismissed("a1", 1)).toBe(false);
    expect(isDismissed("a1", 2)).toBe(true);
    expect(JSON.parse(window.localStorage.getItem("fred.announcements.dismissed") ?? "[]")).toEqual(["a1@2"]);
  });

  it("treats a corrupted stored value as nothing dismissed", () => {
    window.localStorage.setItem("fred.announcements.dismissed", "{not json");

    expect(isDismissed("a1", 1)).toBe(false);
  });

  it("treats a stored non-array as nothing dismissed", () => {
    window.localStorage.setItem("fred.announcements.dismissed", '{"a1@1":true}');

    expect(isDismissed("a1", 1)).toBe(false);
  });

  it("degrades to not-dismissed when reading storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    expect(() => isDismissed("a1", 1)).not.toThrow();
    expect(isDismissed("a1", 1)).toBe(false);
  });

  it("does not throw when writing to storage fails", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });

    expect(() => markDismissed("a1", 1)).not.toThrow();
  });
});
