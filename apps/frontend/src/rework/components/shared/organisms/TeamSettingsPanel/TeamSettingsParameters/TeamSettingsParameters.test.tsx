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

// TEAM-09 (narrowed to 2 states 2026-07-26): the private/public Switch was
// replaced by a 2-way joining_mode button group (open / invite_only).
// TEAM-10 (2026-07-26): a sibling visibility (public/private) button group
// was added just above it in the same form-section — a PRIVATE team can
// never be OPEN, so the joining-mode group is entirely disabled while
// visibility is private.

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

function baseTeam(
  joining_mode: TeamWithPermissions["joining_mode"],
  visibility: TeamWithPermissions["visibility"] = "public",
): TeamWithPermissions {
  return {
    id: "team-1",
    name: "Team One",
    is_member: true,
    admins: [],
    permissions: [],
    joining_mode,
    visibility,
  } as TeamWithPermissions;
}

function radiosIn(radiogroupAriaLabel: string): HTMLElement[] {
  const group = container.querySelector(`[role="radiogroup"][aria-label="${radiogroupAriaLabel}"]`);
  return Array.from(group?.querySelectorAll('[role="radio"]') ?? []);
}

function joiningModeRadios(): HTMLElement[] {
  return radiosIn("rework.teamSettings.parameters.joiningMode.label");
}

function visibilityRadios(): HTMLElement[] {
  return radiosIn("rework.teamSettings.parameters.visibility.label");
}

describe("TeamSettingsParameters joining mode", () => {
  it("marks the team's current joining_mode as selected in the button group", () => {
    render(<TeamSettingsParameters team={baseTeam("invite_only")} />);

    const radios = joiningModeRadios();
    expect(radios).toHaveLength(2);
    // order: open, invite_only
    expect(radios[1].getAttribute("aria-checked")).toBe("true");
    expect(radios[0].getAttribute("aria-checked")).toBe("false");
  });

  it("selecting a different option PATCHes the new joining_mode", () => {
    render(<TeamSettingsParameters team={baseTeam("invite_only")} />);

    const radios = joiningModeRadios();
    act(() => {
      radios[0].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(h.updateTeam).toHaveBeenCalledWith({
      teamId: "team-1",
      updateTeamRequest: { joining_mode: "open" },
    });
  });

  it("clicking the already-selected option does not PATCH", () => {
    render(<TeamSettingsParameters team={baseTeam("invite_only")} />);

    const radios = joiningModeRadios();
    act(() => {
      radios[1].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(h.updateTeam).not.toHaveBeenCalled();
  });

  it("is entirely disabled while the team is private", () => {
    render(<TeamSettingsParameters team={baseTeam("invite_only", "private")} />);

    const radios = joiningModeRadios();
    expect(radios).toHaveLength(2);
    for (const radio of radios) {
      expect((radio as HTMLButtonElement).disabled).toBe(true);
    }
  });

  it("is enabled while the team is public", () => {
    render(<TeamSettingsParameters team={baseTeam("invite_only", "public")} />);

    for (const radio of joiningModeRadios()) {
      expect((radio as HTMLButtonElement).disabled).toBe(false);
    }
  });
});

describe("TeamSettingsParameters visibility", () => {
  it("marks the team's current visibility as selected in the button group", () => {
    render(<TeamSettingsParameters team={baseTeam("invite_only", "private")} />);

    const radios = visibilityRadios();
    expect(radios).toHaveLength(2);
    // order: public, private
    expect(radios[1].getAttribute("aria-checked")).toBe("true");
    expect(radios[0].getAttribute("aria-checked")).toBe("false");
  });

  it("selecting a different option PATCHes the new visibility", () => {
    render(<TeamSettingsParameters team={baseTeam("invite_only", "public")} />);

    const radios = visibilityRadios();
    act(() => {
      radios[1].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(h.updateTeam).toHaveBeenCalledWith({
      teamId: "team-1",
      updateTeamRequest: { visibility: "private" },
    });
  });

  it("clicking the already-selected option does not PATCH", () => {
    render(<TeamSettingsParameters team={baseTeam("invite_only", "public")} />);

    const radios = visibilityRadios();
    act(() => {
      radios[0].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(h.updateTeam).not.toHaveBeenCalled();
  });

  it("PATCHing visibility never sends joining_mode — the server owns that downgrade", () => {
    render(<TeamSettingsParameters team={baseTeam("open", "public")} />);

    const radios = visibilityRadios();
    act(() => {
      radios[1].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(h.updateTeam).toHaveBeenCalledWith({
      teamId: "team-1",
      updateTeamRequest: { visibility: "private" },
    });
  });
});

describe("TeamSettingsParameters banner preview", () => {
  it("shows an empty-state label when the team has no banner", () => {
    render(<TeamSettingsParameters team={baseTeam("invite_only")} />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("rework.teamSettings.parameters.teamBanner.noBanner");
  });

  it("renders the banner image when the team has one", () => {
    const team = { ...baseTeam("invite_only"), banner_image_url: "https://example.com/banner.png" };
    render(<TeamSettingsParameters team={team} />);

    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe("https://example.com/banner.png");
    expect(container.textContent).not.toContain("rework.teamSettings.parameters.teamBanner.noBanner");
  });
});
