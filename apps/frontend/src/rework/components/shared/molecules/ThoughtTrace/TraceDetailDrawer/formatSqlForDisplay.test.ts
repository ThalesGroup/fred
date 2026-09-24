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
