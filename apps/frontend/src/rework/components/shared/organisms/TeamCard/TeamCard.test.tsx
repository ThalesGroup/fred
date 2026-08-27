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

// TEAM-09 (narrowed to 2 states 2026-07-26): the marketplace card's join
// affordance is driven entirely by `joining_mode` (+ `is_member`) — the join
// button for OPEN, an "invite only" label otherwise, plus the self-service
// join mutation actually firing for OPEN.
//
// #2453 adds one branch on top: a public INVITE_ONLY team whose admins have a
// reachable address gets a prefilled mailto button instead of that label.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterAll, afterEach, describe, expect, it, vi } from "vitest";
import type { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  joinTeam: vi.fn(() => ({ unwrap: () => Promise.resolve({}) })),
  isJoining: false,
}));

const k = vi.hoisted(() => ({
  fullName: "Test User" as string | null,
  username: "test.user" as string | null,
}));

vi.mock("react-i18next", () => ({
  // Interpolation values are appended to the key so the mailto assertions can
  // check what the card actually fed into the subject/body templates.
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key}:${Object.values(opts).join("|")}` : key),
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useJoinTeamMutation: () => [h.joinTeam, { isLoading: h.isJoining }],
}));

vi.mock("src/hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => ({ activeTeam: undefined }),
}));

vi.mock("src/hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({
    defaultTeamAvatarFile: undefined,
    defaultPersonalAvatarFile: undefined,
    siteTitle: "Fred",
    siteSubtitle: "Platform",
  }),
}));

vi.mock("../../../../../security/KeycloakService.ts", () => ({
  KeyCloakService: { GetUserFullName: () => k.fullName, GetUserName: () => k.username },
}));

// A subpath deployment is the interesting case: the mailed link must carry the
// basename, which a router-less string concat does not get for free.
vi.mock("src/common/config", () => ({
  getConfig: () => ({ frontend_basename: "/fred/" }),
}));

import TeamCard from "./TeamCard.tsx";

// The mailto is triggered by assigning window.location.href; happy-dom would
// try to navigate on that, so intercept the assignment and record it instead.
// Restored in afterAll: the stub carries only what this file needs, so leaving
// it in place would silently break anything else that reads window.location.
const hrefSetter = vi.fn();
const realLocation = Object.getOwnPropertyDescriptor(window, "location");
Object.defineProperty(window, "location", {
  configurable: true,
  value: {
    origin: "http://localhost:3000",
    set href(value: string) {
      hrefSetter(value);
    },
  },
});

afterAll(() => {
  if (realLocation) Object.defineProperty(window, "location", realLocation);
});

const admin = { id: "u-1", first_name: "Ay", last_name: "One", email: "ay@example.com" };

function lastMailto(): string {
  const calls = hrefSetter.mock.calls;
  return calls[calls.length - 1]?.[0] ?? "";
}

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
  h.joinTeam.mockClear();
  hrefSetter.mockClear();
  h.isJoining = false;
  k.fullName = "Test User";
  k.username = "test.user";
});

function baseTeam(overrides: Partial<Team>): Team {
  return {
    id: "team-1",
    name: "Team One",
    is_member: false,
    admins: [],
    member_count: 3,
    ...overrides,
  } as Team;
}

describe("TeamCard joining_mode rendering", () => {
  it("OPEN + not a member: shows the join button and calls joinTeam on click", () => {
    const onJoined = vi.fn();
    render(<TeamCard team={baseTeam({ joining_mode: "open" })} withDescription={false} onJoined={onJoined} />);

    const button = container.querySelector("button");
    expect(button).not.toBeNull();
    expect(button?.textContent).toContain("rework.teamCard.join");

    act(() => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(h.joinTeam).toHaveBeenCalledWith({ teamId: "team-1" });
  });

  it("INVITE_ONLY with no visibility on the payload: fails closed to the label", () => {
    // A version-skew backend can omit `visibility` (#2433) - the card must not
    // hand out the admin addresses on a payload it cannot read as public.
    render(<TeamCard team={baseTeam({ joining_mode: "invite_only", admins: [admin] })} withDescription={false} />);

    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).toContain("rework.teamCard.inviteOnly");
  });

  it("INVITE_ONLY + private: no button, shows the invite-only label", () => {
    render(
      <TeamCard
        team={baseTeam({ joining_mode: "invite_only", visibility: "private", admins: [admin] })}
        withDescription={false}
      />,
    );

    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).toContain("rework.teamCard.inviteOnly");
  });

  it("INVITE_ONLY + public without a reachable admin address: falls back to the label", () => {
    render(
      <TeamCard
        team={baseTeam({ joining_mode: "invite_only", visibility: "public", admins: [{ ...admin, email: null }] })}
        withDescription={false}
      />,
    );

    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).toContain("rework.teamCard.inviteOnly");
  });

  it("already a member: no join button or label regardless of joining_mode", () => {
    render(<TeamCard team={baseTeam({ joining_mode: "open", is_member: true })} withDescription={false} />);

    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).not.toContain("rework.teamCard.join");
  });
});

describe("TeamCard invitation request (#2453)", () => {
  it("PUBLIC + INVITE_ONLY: opens a prefilled mailto addressed to every admin", () => {
    render(
      <TeamCard
        team={baseTeam({
          joining_mode: "invite_only",
          visibility: "public",
          admins: [admin, { id: "u-2", first_name: "Bee", last_name: "Two", email: "bee@example.com" }],
        })}
        withDescription={false}
      />,
    );

    const button = container.querySelector("button");
    expect(button?.textContent).toContain("rework.teamCard.join");
    expect(container.textContent).not.toContain("rework.teamCard.inviteOnly");

    act(() => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    // Recipients are comma-separated per RFC 6068 and percent-encoded.
    const raw = lastMailto();
    expect(raw.startsWith("mailto:ay%40example.com,bee%40example.com?")).toBe(true);
    // Spaces must survive as %20, never as the "+" URLSearchParams emits: mail
    // clients render that literally in the subject line.
    expect(raw).not.toContain("+");

    const href = decodeURIComponent(raw);
    expect(href).toContain("rework.teamCard.invitationMail.subject:Fred Platform|Team One");
    // The link lands on the members page (the admins add the sender by hand)
    // and carries the configured basename ("/fred/").
    expect(href).toContain(
      "rework.teamCard.invitationMail.body:Fred Platform|Team One|Test User (test.user)|http://localhost:3000/fred/team/team-1/settings/members",
    );
  });

  it("falls back to whichever identity claim Keycloak returned", () => {
    k.fullName = null;
    render(
      <TeamCard
        team={baseTeam({ joining_mode: "invite_only", visibility: "public", admins: [admin] })}
        withDescription={false}
      />,
    );

    act(() => {
      container.querySelector("button")?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    // "(test.user)" alone, never a stray "  ()" the admin cannot act on.
    expect(decodeURIComponent(lastMailto())).toContain("|(test.user)|");
  });

  it("PUBLIC + INVITE_ONLY but already a member: no mail button", () => {
    render(
      <TeamCard
        team={baseTeam({ joining_mode: "invite_only", visibility: "public", is_member: true, admins: [admin] })}
        withDescription={false}
      />,
    );

    expect(container.querySelector("button")).toBeNull();
  });
});
