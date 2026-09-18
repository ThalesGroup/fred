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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  accept: vi.fn(() => Promise.resolve()),
  acceptance: undefined as { accepted_at: string } | undefined,
  skipped: undefined as boolean | undefined,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { date?: string }) => (options?.date ? `${key}:${options.date}` : key),
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useAcceptTeamAdminCharterMutation: () => [h.accept, { isLoading: false }],
  useGetTeamAdminCharterAcceptanceQuery: (_arg: unknown, options: { skip: boolean }) => {
    h.skipped = options.skip;
    return { data: options.skip ? undefined : h.acceptance };
  },
}));

vi.mock("@shared/molecules/TeamAdminCharterContent/TeamAdminCharterContent.tsx", () => ({
  default: () => "charter",
}));

import TeamSettingsResponsibilities from "./TeamSettingsResponsibilities.tsx";

let container: HTMLDivElement;
let root: Root;

function render(canAccept?: boolean) {
  container = document.createElement("div");
  root = createRoot(container);
  act(() => {
    root.render(<TeamSettingsResponsibilities canAccept={canAccept} />);
  });
}

afterEach(() => {
  act(() => root.unmount());
  h.accept.mockClear();
  h.acceptance = undefined;
  h.skipped = undefined;
});

describe("TeamSettingsResponsibilities", () => {
  it("shows an admin when they accepted the charter, with nothing left to accept", () => {
    h.acceptance = { accepted_at: "2026-09-15T14:10:25Z" };
    render();

    expect(container.textContent).toContain("charter");
    expect(container.textContent).toContain("rework.teamAdminCharter.acceptedOn:");
    expect(container.querySelector("button")).toBeNull();
  });

  it("lets a pending admin accept the charter without reading an acceptance", () => {
    render(true);
    const accept = container.querySelector("button") as HTMLButtonElement;

    expect(h.skipped).toBe(true);
    act(() => accept.click());
    expect(h.accept).toHaveBeenCalledTimes(1);
  });
});
