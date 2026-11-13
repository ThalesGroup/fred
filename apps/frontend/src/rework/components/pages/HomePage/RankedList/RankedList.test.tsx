// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import RankedList from "./RankedList";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ i18n: { language: "en" } }),
}));

describe("RankedList exact counters", () => {
  it("preserves integers beyond Number precision and scales bars without conversion", () => {
    const html = renderToStaticMarkup(
      <RankedList
        items={[
          { key: "first", label: "Same name", value: 18014398509481986n },
          { key: "second", label: "Same name", value: 9007199254740993n },
        ]}
        emptyLabel="No activity"
      />,
    );
    expect(html).toContain("18,014,398,509,481,986");
    expect(html).toContain("9,007,199,254,740,993");
    expect(html).toContain("width:100%");
    expect(html).toContain("width:50%");
    expect(html.match(/>Same name</g)).toHaveLength(2);
  });

  it("keeps a zero row distinct from an empty ranking", () => {
    const html = renderToStaticMarkup(
      <RankedList items={[{ key: "team", label: "Team", value: 0n }]} emptyLabel="No activity" />,
    );
    expect(html).toContain("width:0%");
    expect(html).not.toContain("No activity");
    expect(renderToStaticMarkup(<RankedList items={[]} emptyLabel="No activity" />)).toContain("No activity");
  });
});
