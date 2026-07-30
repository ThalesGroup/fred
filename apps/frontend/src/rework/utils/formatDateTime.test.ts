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

import { describe, expect, it } from "vitest";
import { formatDateTime } from "./formatDateTime.ts";

describe("formatDateTime", () => {
  it("formats an ISO string as dd/mm/yy - hh:mm", () => {
    const iso = new Date(2026, 6, 27, 15, 2).toISOString(); // month is 0-indexed: 6 = July
    expect(formatDateTime(iso)).toBe("27/07/26 - 15:02");
  });

  it("returns an em dash for missing or invalid input", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime(undefined)).toBe("—");
    expect(formatDateTime("not-a-date")).toBe("—");
  });
});
