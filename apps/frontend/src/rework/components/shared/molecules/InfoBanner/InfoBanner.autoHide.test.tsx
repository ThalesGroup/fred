// @vitest-environment happy-dom
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

// The auto-hide contract is a *transition* — visible now, gone after the
// configured delay — which a static render cannot show, so these tests drive
// real mounts with `createRoot` + `act` and fake timers (the repo's idiom,
// see CharacterLimitNotice.test.tsx). The static rendering contract lives in
// InfoBanner.test.tsx.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { InfoBanner as InfoBannerConfig } from "src/slices/controlPlane/controlPlaneOpenApi";
import InfoBanner from "./InfoBanner";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const mockGetInfoBanner = vi.fn<() => InfoBannerConfig | null>();

vi.mock("src/common/config", () => ({
  getInfoBanner: () => mockGetInfoBanner(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.useFakeTimers();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
});

const render = () => act(() => root.render(<InfoBanner />));
const bannerElement = () => container.querySelector('[role="status"]');

describe("InfoBanner auto-hide", () => {
  it("stays visible when auto_hide_seconds is not set (persistent default)", () => {
    mockGetInfoBanner.mockReturnValue({ color: "#00BBDD", titles: { en: "Maintenance" }, messages: {}, links: [] });

    render();
    expect(bannerElement()).not.toBeNull();

    act(() => vi.advanceTimersByTime(3_600_000));
    expect(bannerElement()).not.toBeNull();
  });

  it("hides itself once the configured number of seconds has elapsed", () => {
    mockGetInfoBanner.mockReturnValue({
      color: "#00BBDD",
      auto_hide_seconds: 30,
      titles: { en: "Maintenance" },
      messages: {},
      links: [],
    });

    render();
    expect(bannerElement()).not.toBeNull();

    act(() => vi.advanceTimersByTime(29_999));
    expect(bannerElement()).not.toBeNull();

    act(() => vi.advanceTimersByTime(1));
    expect(bannerElement()).toBeNull();
  });
});
