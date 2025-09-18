// Copyright Thales 2025
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

import { Theme, alpha } from "@mui/material/styles";
import { formatTick, TimePrecision } from "./timeAxis";

/** Keep it string to match OpenAPI client; but delegate to TimePrecision underneath. */
export type PrecisionStr = string;

/** Back-compat wrapper: returns a tick formatter using the centralized timeAxis formatter. */
export function tsTickFormatter(precision: PrecisionStr) {
  return (ts: number) => formatTick(Number(ts), precision as TimePrecision);
}

/* -------------------------- THEME-DRIVEN STYLES --------------------------- */

export function chartSeriesPalette(theme: Theme, count?: number): string[] {
  const c = (theme.palette as any).chart || {};
  const bases: string[] = [
    c.primary,
    c.secondary,
    c.blue,
    c.green,
    c.orange,
    c.purple,
    c.red,
    c.yellow,
    c.highBlue,
    c.mediumBlue,
    c.highGreen,
    c.mediumGreen,
  ].filter(Boolean);

  if (bases.length === 0) {
    bases.push(
      theme.palette.primary.main,
      theme.palette.secondary.main,
      theme.palette.success.main,
      theme.palette.info.main,
      theme.palette.warning.main,
      theme.palette.error.main,
    );
  }

  const baseA = theme.palette.mode === "dark" ? 0.28 : 0.22;
  const soft = bases.map((hex) => alpha(hex, baseA));

  if (!count) return soft;
  const out: string[] = [];
  for (let i = 0; i < count; i++) out.push(soft[i % soft.length]);
  return out;
}

export function axisTickProps(theme: Theme) {
  return { fontSize: 11, fill: theme.palette.text.secondary };
}

export function gridStroke(theme: Theme) {
  return theme.palette.divider;
}

export function legendStyle(theme: Theme) {
  return { fontSize: 11, color: theme.palette.text.secondary as any };
}

export function tooltipStyle(theme: Theme) {
  return {
    fontSize: 12,
    backgroundColor: theme.palette.background.paper,
    border: `1px solid ${theme.palette.divider}`,
    borderRadius: 8,
    color: theme.palette.text.primary,
    boxShadow: theme.shadows[2] as any,
    padding: 8,
  };
}

export function primarySeriesColor(theme: Theme) {
  const c = (theme.palette as any).chart || {};
  const base = c.blue || c.primary || theme.palette.primary.main;
  return alpha(base, theme.palette.mode === "dark" ? 0.7 : 0.55);
}
