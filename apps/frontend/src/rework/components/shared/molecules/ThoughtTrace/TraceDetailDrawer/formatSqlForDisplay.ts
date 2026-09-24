// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0

import { format } from "sql-formatter";

/** Format a DuckDB query for display without preventing malformed SQL from being inspected. */
export function formatSqlForDisplay(sql: string): string {
  try {
    return format(sql, {
      language: "duckdb",
      keywordCase: "upper",
      tabWidth: 2,
    });
  } catch {
    return sql;
  }
}
