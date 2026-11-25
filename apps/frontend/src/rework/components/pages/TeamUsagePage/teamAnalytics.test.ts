// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { expect, it } from "vitest";
import {
  collectiveConsumptionQueries,
  collectiveHistoryQueries,
  collectiveInventoryQueries,
  collectiveToolQueries,
} from "./teamAnalytics";

it("applies the same explicit UTC calendar to all current and previous populations within batch limits", () => {
  const range = { since: "2026-01-01T00:00:00Z", until: "2026-01-04T00:00:00Z" };
  const calendar = { exclude_weekends: true, exclude_holidays: true };
  for (const build of [
    collectiveConsumptionQueries,
    collectiveHistoryQueries,
    collectiveInventoryQueries,
    collectiveToolQueries,
  ]) {
    const queries = build(range, "team-a", calendar);
    expect(queries.length).toBeLessThanOrEqual(8);
    for (const q of queries) {
      expect(q.scope).toEqual({ kind: "space", id: "team-a" });
      expect(q.time.calendar).toEqual(calendar);
      expect(q.time.timezone).toBe("UTC");
      expect(q.measures.length).toBeLessThanOrEqual(12);
      if (q.name.startsWith("previous_")) {
        expect(q.time.since).toBe("2025-12-29T00:00:00.000Z");
        expect(q.time.until).toBe(range.since);
      }
    }
  }
});
