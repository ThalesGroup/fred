// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0

import { describe, expect, it } from "vitest";
import { formatSqlForDisplay } from "./formatSqlForDisplay";

describe("formatSqlForDisplay", () => {
  it("formats a DuckDB query without changing identifiers or values", () => {
    expect(
      formatSqlForDisplay(
        'SELECT "Véhicule", "Prix_Jour" FROM d_vehicles WHERE "Disponible" = \'Oui\' ORDER BY "Véhicule";',
      ),
    ).toBe(`SELECT
  "Véhicule",
  "Prix_Jour"
FROM
  d_vehicles
WHERE
  "Disponible" = 'Oui'
ORDER BY
  "Véhicule";`);
  });

  it("preserves malformed SQL when formatting fails", () => {
    const malformedSql = "SELECT 'unterminated";

    expect(formatSqlForDisplay(malformedSql)).toBe(malformedSql);
  });
});
