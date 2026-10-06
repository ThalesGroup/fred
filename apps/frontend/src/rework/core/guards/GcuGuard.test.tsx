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

const state = vi.hoisted(() => ({ version: "v1" as string | null, accepted: "v1" as string | null }));
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn() }));
vi.mock("src/hooks/useFrontendProperties.ts", () => ({ useFrontendProperties: () => ({ gcuVersion: state.version }) }));
vi.mock("@components/pages/GcuPage/GcuPage.tsx", () => ({ default: () => <div>Accept terms</div> }));
vi.mock("../../../slices/controlPlane/controlPlaneApi.ts", () => ({
  controlPlaneApi: {
    endpoints: {
      getUserDetailsControlPlaneV1UserGet: {
        useQuery: () => ({ data: { cguValidated: state.accepted }, isLoading: false, isUninitialized: false }),
      },
    },
  },
}));

import GcuGuard from "./GcuGuard.tsx";

beforeEach(() => {
  state.version = "v1";
  state.accepted = "v1";
});

describe("GcuGuard", () => {
  it("requires a new version and restores the shell when that version is accepted", () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const render = () =>
      act(() =>
        root.render(
          <GcuGuard>
            <div>Shell</div>
          </GcuGuard>,
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
    state.accepted = "v1";
    render();
    expect(container.textContent).toBe("Shell");
    act(() => root.unmount());
  });

  it("allows deployments without terms gating", () => {
    state.version = null;
    state.accepted = null;
    const container = document.createElement("div");
    const root = createRoot(container);
    act(() =>
      root.render(
        <GcuGuard>
          <div>Shell</div>
        </GcuGuard>,
      ),
    );
    expect(container.textContent).toBe("Shell");
    act(() => root.unmount());
  });
});
