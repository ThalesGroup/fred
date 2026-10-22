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

// The platform drawer mounts the capability's panel, routes it to the pod, and
// gives write actions only to capability managers (from the bootstrap roles).

import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  dispatch: vi.fn(),
  canManageFeatures: false,
  panelProps: undefined as undefined | { canManage: boolean },
}));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-redux", () => ({ useDispatch: () => h.dispatch }));
vi.mock("../../../../core/hooks/useUserCapabilities", () => ({
  useUserCapabilities: () => ({ canManageFeatures: h.canManageFeatures }),
}));
vi.mock("@shared/molecules/InlineDrawer/InlineDrawer.tsx", () => ({
  InlineDrawer: ({ open, children }: { open: boolean; children: React.ReactNode }) => (open ? children : null),
}));
vi.mock("../../../../features/capabilities/platformPanelRegistry", () => ({
  platformPanelFor: (id: string) =>
    id === "ppt_builder"
      ? (props: { canManage: boolean }) => {
          h.panelProps = props;
          return null;
        }
      : undefined,
}));

import { CapabilityPlatformDrawer } from "./CapabilityPlatformDrawer";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const capability = {
  id: "ppt_builder",
  name: "n",
  version: "1",
  icon: "x",
  team_scope: "admin_gated",
  default_on: true,
  route_base_url: "/pod/capabilities/ppt_builder",
} as CapabilityEnablementItem;

function mount(manager: boolean) {
  h.canManageFeatures = manager;
  h.panelProps = undefined;
  const root = createRoot(document.createElement("div"));
  act(() => root.render(<CapabilityPlatformDrawer capability={capability} allCapabilities={[]} onClose={() => {}} />));
  act(() => root.unmount());
}

describe("CapabilityPlatformDrawer", () => {
  it("routes the panel to the capability pod and gates its writes on the manager role", () => {
    mount(true);
    expect(h.dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ payload: { ppt_builder: "/pod/capabilities/ppt_builder" } }),
    );
    expect(h.panelProps?.canManage).toBe(true);
    mount(false);
    expect(h.panelProps?.canManage).toBe(false);
  });
});
