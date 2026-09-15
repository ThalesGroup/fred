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
import { describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({ onEndReached: "unset" as unknown }));

vi.mock("@shared/molecules/TeamAdminCharterContent/TeamAdminCharterContent.tsx", () => ({
  default: ({ onEndReached }: { onEndReached?: () => void }) => {
    h.onEndReached = onEndReached;
    return "charter";
  },
}));

import TeamSettingsResponsibilities from "./TeamSettingsResponsibilities.tsx";

describe("TeamSettingsResponsibilities", () => {
  it("shows the charter read-only, with nothing left to accept", () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    act(() => {
      root.render(<TeamSettingsResponsibilities />);
    });

    expect(container.textContent).toBe("charter");
    expect(h.onEndReached).toBeUndefined();
    act(() => root.unmount());
  });
});
