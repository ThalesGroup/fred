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
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const state = vi.hoisted(() => ({
  version: "v1" as string | null,
  accepted: "v1" as string | null,
  bootstrap: false,
  admitted: true,
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@components/pages/BootstrapPage/BootstrapPage", () => ({
  default: ({ username }) => <div>Initialize {username}</div>,
}));
vi.mock("@components/pages/GcuPage/GcuPage", () => ({ default: () => <div>Accept terms</div> }));
vi.mock("@shared/layouts/MainLayout/MainLayout", () => ({ default: ({ children }) => children }));
vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useOnboardingStatusQuery: () => ({
    data: {
      username: "simon",
      admitted: state.admitted,
      root_bootstrap_required: state.bootstrap,
      gcu_version: state.version,
      acceptance: { version: state.accepted },
    },
    refetch: vi.fn(),
  }),
}));

import OnboardingGuard from "./OnboardingGuard.tsx";

beforeEach(() => {
  state.bootstrap = false;
  state.admitted = true;
  state.version = "v1";
  state.accepted = "v1";
});

describe("OnboardingGuard", () => {
  it("requires a new version and restores the shell when that version is accepted", () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const render = () =>
      act(() =>
        root.render(
          <OnboardingGuard>
            <div>Shell</div>
          </OnboardingGuard>,
        ),
      );
    render();
    expect(container.textContent).toBe("Shell");
    state.version = "v2";
    render();
    expect(container.textContent).toBe("Accept terms");
    state.accepted = "v2";
    render();
    expect(container.textContent).toBe("Shell");
    state.version = "v1";
    render();
    expect(container.textContent).toBe("Accept terms");
    state.accepted = "v1";
    render();
    expect(container.textContent).toBe("Shell");
    act(() => root.unmount());
  });

  it("shows bootstrap before consent, then consent before business content", () => {
    state.bootstrap = true;
    state.accepted = null;
    const container = document.createElement("div");
    const root = createRoot(container);
    const render = () =>
      act(() =>
        root.render(
          <OnboardingGuard>
            <div>Shell</div>
          </OnboardingGuard>,
        ),
      );
    render();
    expect(container.textContent).toBe("Initialize simon");
    state.bootstrap = false;
    render();
    expect(container.textContent).toBe("Accept terms");
    state.accepted = "v1";
    render();
    expect(container.textContent).toBe("Shell");
    act(() => root.unmount());
  });

  it("blocks an unadmitted person before consent, including previously accepted terms", () => {
    state.admitted = false;
    const container = document.createElement("div");
    const root = createRoot(container);
    const render = () => act(() => root.render(<OnboardingGuard>Shell</OnboardingGuard>));
    render();
    expect(container.textContent).toContain("rework.manager.notAdmitted");
    state.accepted = null;
    render();
    expect(container.textContent).not.toContain("Accept terms");
    state.admitted = true;
    render();
    expect(container.textContent).toBe("Accept terms");
    act(() => root.unmount());
  });

  it("allows deployments without terms gating", () => {
    state.version = null;
    state.accepted = null;
    const container = document.createElement("div");
    const root = createRoot(container);
    act(() =>
      root.render(
        <OnboardingGuard>
          <div>Shell</div>
        </OnboardingGuard>,
      ),
    );
    expect(container.textContent).toBe("Shell");
    act(() => root.unmount());
  });
});
