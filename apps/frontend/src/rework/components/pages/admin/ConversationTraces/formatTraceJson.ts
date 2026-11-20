// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { jsonLanguage } from "@codemirror/lang-json";

const parser = jsonLanguage.parser.configure({ strict: true });
const maxFormattedLength = 4 * 1024 * 1024;

/** Add indentation between tokens without interpreting any captured values. */
export function formatTraceJson(raw: string): string | undefined {
  const source = raw.replace(/^\uFEFF/, "");
  try {
    const token = parser.parse(source).cursor();
    let depth = 0;
    let previous = "";
    let formatted = "";
    while (token.next()) {
      const { name, from, to } = token;
      if (name === "Object" || name === "Array" || name === "Property") continue;

      const closes = name === "}" || name === "]";
      if (closes) depth--;
      const afterOpening = previous === "{" || previous === "[";
      if (previous === "," || (afterOpening && !closes) || (closes && !afterOpening)) {
        formatted += "\n" + "  ".repeat(Math.min(depth, 20));
      } else if (previous === ":") {
        formatted += " ";
      }
      formatted += source.slice(from, to);
      if (formatted.length > maxFormattedLength) return source;
      if (name === "{" || name === "[") depth++;
      previous = name;
    }
    return formatted;
  } catch {
    // Partial JSON and plain text are displayed as received.
    return undefined;
  }
}
