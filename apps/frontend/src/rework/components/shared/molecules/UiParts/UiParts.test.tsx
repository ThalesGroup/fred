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

// UiParts host (#1977): dispatches every part through the registry, renders
// the demo capability's card inline, and SKIPS unknown kinds without crashing.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { RawUiPart } from "@rework/types/parts";
import { UiParts } from "./UiParts";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (value: string) => value }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: () => undefined, showSuccess: () => undefined }),
}));

vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type }: { type: string }) => <span data-icon={type} />,
}));

function render(parts: RawUiPart[]): string {
  return renderToStaticMarkup(<UiParts parts={parts} />);
}

const LINK: RawUiPart = { type: "link", href: "https://example.test/report.pdf", file_name: "report.pdf" };
const GEO: RawUiPart = { type: "geo", geojson: { type: "FeatureCollection", features: [{}, {}] } };
const DEMO_CARD: RawUiPart = { type: "demo_card", title: "Demo echo", body: "HELLO" };
const UNKNOWN: RawUiPart = { type: "part_kind_from_the_future", payload: "??" };

describe("UiParts (#1977)", () => {
  it("renders a link part as a download chip", () => {
    const html = render([LINK]);
    expect(html).toContain("report.pdf");
    expect(html).toContain("chatbot.artifactLinks.downloadAria");
  });

  it("renders a geo part through the registry (summary chip)", () => {
    const html = render([GEO]);
    expect(html).toContain("chatbot.uiParts.geoSummary");
  });

  it("renders the demo capability's custom card inline", () => {
    const html = render([DEMO_CARD]);
    expect(html).toContain("Demo echo");
    expect(html).toContain("HELLO");
    expect(html).toContain("capability.demo_echo.cardAria");
  });

  it("silently skips unknown kinds — no crash, siblings still render", () => {
    const html = render([UNKNOWN, DEMO_CARD]);
    expect(html).toContain("Demo echo");
    expect(html).not.toContain("part_kind_from_the_future");
    expect(html).not.toContain("??");
  });

  it("renders nothing when no part has a registered renderer", () => {
    expect(render([UNKNOWN])).toBe("");
    expect(render([])).toBe("");
  });

  it("renders mixed known kinds side by side", () => {
    const html = render([LINK, GEO, DEMO_CARD]);
    expect(html).toContain("report.pdf");
    expect(html).toContain("chatbot.uiParts.geoSummary");
    expect(html).toContain("HELLO");
  });
});
