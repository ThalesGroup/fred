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

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { InfoBanner as InfoBannerConfig } from "src/slices/controlPlane/controlPlaneOpenApi";
import InfoBanner from "./InfoBanner";

const mockGetInfoBanner = vi.fn<() => InfoBannerConfig | null>();
let mockLanguage = "en";

vi.mock("src/common/config", () => ({
  getInfoBanner: () => mockGetInfoBanner(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: mockLanguage } }),
}));

const banner: InfoBannerConfig = {
  color: "#00BBDD",
  titles: { en: "New version available", fr: "Nouvelle version disponible" },
  messages: { en: "Access the Fred documentation & blog" },
  links: [{ url: "https://fredk8.dev", labels: { en: "Go to the Fred blog" } }],
};

describe("InfoBanner", () => {
  it("renders nothing when no banner is configured", () => {
    mockGetInfoBanner.mockReturnValue(null);
    mockLanguage = "en";

    expect(renderToStaticMarkup(<InfoBanner />)).toBe("");
  });

  it("renders nothing when the banner has neither title nor message for any locale", () => {
    mockGetInfoBanner.mockReturnValue({ color: "#00BBDD", titles: {}, messages: {}, links: [] });
    mockLanguage = "en";

    expect(renderToStaticMarkup(<InfoBanner />)).toBe("");
  });

  it("renders the localized title, message, configured color and links", () => {
    mockGetInfoBanner.mockReturnValue(banner);
    mockLanguage = "en";

    const html = renderToStaticMarkup(<InfoBanner />);

    expect(html).toContain("New version available");
    expect(html).toContain("Access the Fred documentation &amp; blog");
    expect(html).toContain("--banner-bg:#00BBDD");
    expect(html).toContain('href="https://fredk8.dev"');
    expect(html).toContain("Go to the Fred blog");
  });

  it("resolves a regional i18next tag to its base locale and falls back to en", () => {
    mockGetInfoBanner.mockReturnValue(banner);
    // "fr-FR" → "fr" for the title; the message has no "fr" entry → "en" fallback.
    mockLanguage = "fr-FR";

    const html = renderToStaticMarkup(<InfoBanner />);

    expect(html).toContain("Nouvelle version disponible");
    expect(html).toContain("Access the Fred documentation &amp; blog");
  });

  it("falls back to the link URL when no label matches the locale", () => {
    mockGetInfoBanner.mockReturnValue({
      ...banner,
      links: [{ url: "https://fredk8.dev", labels: {} }],
    });
    mockLanguage = "en";

    const html = renderToStaticMarkup(<InfoBanner />);

    expect(html).toContain(">https://fredk8.dev</a>");
  });

  it("drops non-http(s) links but keeps relative ones", () => {
    mockGetInfoBanner.mockReturnValue({
      ...banner,
      // Config URLs reach an unauthenticated surface via Helm values, so a
      // javascript:/data: scheme must never become a clickable href.
      links: [
        { url: "javascript:alert(1)", labels: { en: "evil" } },
        { url: "data:text/html,x", labels: { en: "also evil" } },
        { url: "/release-notes", labels: { en: "Release notes" } },
      ],
    });
    mockLanguage = "en";

    const html = renderToStaticMarkup(<InfoBanner />);

    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("data:text/html");
    expect(html).toContain('href="/release-notes"');
  });
});
