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

// TEAM-09: the private/public Switch was replaced by a 4-way joining_mode
// button group. Locks in that selecting an option PATCHes the right
// joining_mode value and that the group reflects the team's current mode.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  updateTeam: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useUpdateTeamMutation: () => [h.updateTeam, { isLoading: false }],
  useUploadTeamBannerMutation: () => [vi.fn(), { isLoading: false }],
}));

vi.mock("../../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ defaultTeamBannerFile: undefined }),
}));

vi.mock("@shared/organisms/TeamSettingsPanel/TeamSettingsRetention/TeamSettingsRetention.tsx", () => ({
  default: () => <div data-testid="retention-stub" />,
}));

import TeamSettingsParameters from "./TeamSettingsParameters.tsx";

let container: HTMLDivElement;
let root: Root;

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(ui);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  h.updateTeam.mockClear();
});

function baseTeam(joining_mode: TeamWithPermissions["joining_mode"]): TeamWithPermissions {
  return {
    id: "team-1",
    name: "Team One",
    is_member: true,
    admins: [],
    permissions: [],
    joining_mode,
  } as TeamWithPermissions;
}

describe("TeamSettingsParameters joining mode", () => {
  it("marks the team's current joining_mode as selected in the button group", () => {
    render(<TeamSettingsParameters team={baseTeam("invite_only")} />);

    const radios = container.querySelectorAll('[role="radio"]');
    expect(radios).toHaveLength(4);
    // order: open, request_only, invite_only, closed
    expect(radios[2].getAttribute("aria-checked")).toBe("true");
    expect(radios[0].getAttribute("aria-checked")).toBe("false");
  });

  it("selecting a different option PATCHes the new joining_mode", () => {
    render(<TeamSettingsParameters team={baseTeam("request_only")} />);

    const radios = container.querySelectorAll('[role="radio"]');
    act(() => {
      radios[0].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(h.updateTeam).toHaveBeenCalledWith({
      teamId: "team-1",
      updateTeamRequest: { joining_mode: "open" },
    });
  });

  it("clicking the already-selected option does not PATCH", () => {
    render(<TeamSettingsParameters team={baseTeam("closed")} />);

    const radios = container.querySelectorAll('[role="radio"]');
    act(() => {
      radios[3].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(h.updateTeam).not.toHaveBeenCalled();
  });
});
