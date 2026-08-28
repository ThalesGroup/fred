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

// Focus: the window string is backend-authored ("7d", from kpi/utils.py) and
// this parser is the only thing standing between it and the chart label — a
// unit it does not recognize must drop the label entirely, never render a
// half-built sentence.

import { describe, expect, it } from "vitest";
import type { TFunction } from "i18next";

import { formatTrendWindow } from "./trendWindow";

// Echoes key + count so assertions pin both the resolved unit key and the
// interpolated count without dragging a real i18n instance into the test.
const t = ((key: string, opts?: { count?: number }) => `${key}#${opts?.count}`) as TFunction;

describe("formatTrendWindow", () => {
  it("resolves each backend unit letter to its translation key with the count", () => {
    expect(formatTrendWindow("7d", t)).toBe("rework.analytics.engagement.trendWindow.day#7");
    expect(formatTrendWindow("7h", t)).toBe("rework.analytics.engagement.trendWindow.hour#7");
    expect(formatTrendWindow("7m", t)).toBe("rework.analytics.engagement.trendWindow.minute#7");
    expect(formatTrendWindow("7s", t)).toBe("rework.analytics.engagement.trendWindow.second#7");
  });

  it("returns undefined while the response has not arrived", () => {
    expect(formatTrendWindow(undefined, t)).toBeUndefined();
    expect(formatTrendWindow(null, t)).toBeUndefined();
    expect(formatTrendWindow("", t)).toBeUndefined();
  });

  it("drops the label for a unit it does not know rather than guessing", () => {
    expect(formatTrendWindow("7w", t)).toBeUndefined();
  });

  it("drops the label when the count does not parse", () => {
    expect(formatTrendWindow("xd", t)).toBeUndefined();
  });
});
