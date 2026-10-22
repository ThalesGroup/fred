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

// Pins each type's title, body and buttons from the payload, in the viewer's
// locale; handled tiles, unknown types and the join request decisions.

import i18n, { type i18n as I18n } from "i18next";
import { beforeAll, describe, expect, it, vi } from "vitest";
import en from "../../../locales/en/translation.json";
import fr from "../../../locales/fr/translation.json";
import {
  describeNotificationType,
  isPendingDecision,
  renderNotification,
  type NotificationAction,
  type NotificationDispatch,
  type NotificationItem,
} from "./notificationTypes";

// The decision buttons dispatch the generated endpoints; each `initiate`
// returns a marker the fake dispatch answers.
const { initiate } = vi.hoisted(() => ({
  initiate: (endpoint: string) => (arg: unknown) => ({ endpoint, arg }),
}));
vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  enhancedControlPlaneApi: {
    endpoints: {
      acceptTeamJoinRequestControlPlaneV1TeamsTeamIdJoinRequestsRequestIdAcceptPost: { initiate: initiate("accept") },
      refuseTeamJoinRequestControlPlaneV1TeamsTeamIdJoinRequestsRequestIdRefusePost: { initiate: initiate("refuse") },
    },
  },
}));

const instances: Record<string, I18n> = {};
const missing: string[] = [];

beforeAll(async () => {
  for (const lng of ["en", "fr"]) {
    const instance = i18n.createInstance();
    await instance.init({
      lng,
      resources: { en: { translation: en }, fr: { translation: fr } },
      interpolation: { escapeValue: false },
      saveMissing: true,
      missingKeyHandler: (_lngs, _ns, key) => missing.push(key),
    });
    instances[lng] = instance;
  }
});

const base = {
  id: "n1",
  team_id: "team-1",
  created_at: "2026-10-20T10:00:00Z",
  expires_at: "2026-11-19T10:00:00Z",
};

const republish: NotificationItem = {
  ...base,
  type: "agent.republish_needed",
  payload: {
    team_id: "team-1",
    team_name: "Purchasing",
    agent_instance_id: "agent-1",
    agent_name: "RFP writer",
    entry_id: "entry-1",
    editor_name: "Léa D.",
  },
};

const removed: NotificationItem = {
  ...base,
  type: "agent.marketplace_removed",
  payload: {
    team_id: "team-1",
    team_name: "Legal",
    agent_instance_id: "agent-2",
    agent_name: "Contract analyst",
    entry_id: "entry-2",
    reason: "removed_by_platform_admin",
    message: "Duplicate entry",
  },
};

const joinRequested: NotificationItem = {
  ...base,
  type: "team.join_requested",
  payload: {
    team_id: "team-1",
    team_name: "Purchasing",
    request_id: "req-1",
    requester_id: "alice",
    requester_name: "Alice Martin",
    message: "I lead the RFP pipeline and would like to reuse your agents for the next three tenders.",
  },
};

const answered = (outcome: "accepted" | "refused"): NotificationItem => ({
  ...base,
  team_id: null,
  type: "team.join_request_answered",
  payload: { team_id: "team-1", team_name: "Purchasing", outcome },
});

/** A dispatch whose endpoint calls answer `results[endpoint]` (an error rejects). */
function fakeDispatch(results: Record<string, unknown> = {}) {
  const calls: { endpoint: string; arg: unknown }[] = [];
  const dispatch = vi.fn((action: { endpoint: string; arg: unknown }) => {
    calls.push(action);
    const result = results[action.endpoint];
    const settled = result instanceof Error ? Promise.reject(result) : Promise.resolve(result);
    return Object.assign(settled, { unwrap: () => settled });
  });
  return { calls, dispatch: dispatch as unknown as NotificationDispatch };
}

const callOf = (action: NotificationAction) => {
  if (action.kind !== "call") throw new Error("not a call action");
  return action.call;
};

describe("renderNotification", () => {
  it("renders a republish request as an action with a button opening that agent", () => {
    const rendered = renderNotification(republish, instances.en.t);

    expect(rendered.category).toBe("action_required");
    expect(rendered.icon).toBe("sync_problem");
    expect(rendered.title).toBe("Published agent changed");
    expect(rendered.body).toContain("Léa D.");
    expect(rendered.body).toContain("RFP writer");
    expect(rendered.body).toContain("Purchasing");
    expect(rendered.link).toBe("/team/team-1/agents?agent=agent-1");
    expect(rendered.actions).toEqual([
      expect.objectContaining({ kind: "navigate", to: "/team/team-1/agents?agent=agent-1", label: "Open the agent" }),
    ]);
    expect(rendered.handledLabel).toBeUndefined();
  });

  it("renders a removal as information with the reason and the admin's message", () => {
    const rendered = renderNotification(removed, instances.en.t);

    expect(rendered.category).toBe("information");
    expect(rendered.title).toBe("Agent removed from the marketplace");
    expect(rendered.body).toContain("Contract analyst");
    expect(rendered.body).toContain("A platform administrator removed it.");
    expect(rendered.body).toContain("Duplicate entry");
    expect(rendered.actions.map((action) => action.label)).toEqual(["Open the agent"]);
    expect(rendered.link).toBe("/team/team-1/agents?agent=agent-2");
  });

  it("falls back to the generic reason for a reason code it does not know", () => {
    const rendered = renderNotification(
      { ...removed, payload: { ...removed.payload, reason: "brand_new_reason", message: null } },
      instances.en.t,
    );

    expect(rendered.body).toContain("The agent is no longer published.");
  });

  it("follows the viewer's locale, not the one of the creation", () => {
    expect(renderNotification(republish, instances.fr.t).title).toBe("Agent publié modifié");
  });

  it("reads without a team name when the snapshot has none", () => {
    const rendered = renderNotification(
      { ...republish, payload: { ...republish.payload, team_name: null } },
      instances.en.t,
    );

    expect(rendered.body).toBe("Léa D. changed “RFP writer”. Republish it to update the marketplace version.");
  });

  it("shows who handled it instead of the buttons", () => {
    const rendered = renderNotification(
      { ...republish, handled_at: "2026-10-21T08:00:00Z", handled_by_name: "Bob" },
      instances.en.t,
    );

    expect(rendered.actions).toEqual([]);
    expect(rendered.handledLabel).toBe("Handled by Bob");
  });

  it("says the entry left the marketplace when no name was recorded", () => {
    const rendered = renderNotification(
      { ...republish, handled_at: "2026-10-21T08:00:00Z", handled_outcome: "removed" },
      instances.en.t,
    );

    expect(rendered.handledLabel).toBe("Resolved: the agent left the marketplace");
  });

  it("renders an unknown type as a generic tile without link or buttons", () => {
    const unknown = { ...base, type: "team.join_request", payload: {} } as unknown as NotificationItem;

    const rendered = renderNotification(unknown, instances.en.t);

    expect(rendered).toMatchObject({ icon: "notifications", title: "Notification", link: null, actions: [] });
  });

  it("renders a join request with the full message and Accept / Refuse calling the routes", async () => {
    const rendered = renderNotification(joinRequested, instances.en.t);

    expect(rendered.category).toBe("action_required");
    expect(rendered.title).toBe("Alice Martin asks to join Purchasing");
    expect(rendered.body).toBe(
      "I lead the RFP pipeline and would like to reuse your agents for the next three tenders.",
    );
    expect(rendered.link).toBe("/team/team-1/settings/members");
    expect(rendered.actions.map(({ label, primary, color }) => [label, primary ?? false, color])).toEqual([
      ["Refuse", false, "error"],
      ["Accept", true, "success"],
    ]);

    const { calls, dispatch } = fakeDispatch();
    await callOf(rendered.actions[0])(dispatch);
    await callOf(rendered.actions[1])(dispatch);
    expect(calls).toEqual([
      { endpoint: "refuse", arg: { teamId: "team-1", requestId: "req-1" } },
      { endpoint: "accept", arg: { teamId: "team-1", requestId: "req-1" } },
    ]);
  });

  it("marks only an open join request as a pending decision", () => {
    expect(isPendingDecision(joinRequested)).toBe(true);
    expect(renderNotification(joinRequested, instances.en.t).pendingDecision).toBe(true);
    const handled = { ...joinRequested, handled_at: "2026-10-21T09:00:00Z", handled_by_name: "Bob" };
    expect(isPendingDecision(handled as NotificationItem)).toBe(false);
    expect(isPendingDecision(republish)).toBe(false);
  });

  it("renders a join request without a message with an empty body", () => {
    const rendered = renderNotification(
      { ...joinRequested, payload: { ...joinRequested.payload, message: null } } as NotificationItem,
      instances.en.t,
    );
    expect(rendered.body).toBe("");
  });

  it("names the outcome on a join request handled by another admin", () => {
    const handled = (outcome: string) =>
      renderNotification(
        { ...joinRequested, handled_at: "2026-10-22T09:00:00Z", handled_by_name: "Bob", handled_outcome: outcome },
        instances.en.t,
      );

    expect(handled("accepted")).toMatchObject({ actions: [], handledLabel: "Accepted by Bob" });
    expect(handled("refused").handledLabel).toBe("Refused by Bob");
    expect(handled("something_else").handledLabel).toBe("Handled by Bob");
  });

  it("tells the requester they were accepted, with a button opening the team", () => {
    const rendered = renderNotification(answered("accepted"), instances.en.t);

    expect(rendered.category).toBe("information");
    expect(rendered.title).toBe("You joined Purchasing");
    expect(rendered.link).toBe("/team/team-1/agents");
    expect(rendered.actions).toEqual([
      expect.objectContaining({ kind: "navigate", to: "/team/team-1/agents", label: "Open the team" }),
    ]);
  });

  it("tells the requester they were refused, with nothing to open", () => {
    const rendered = renderNotification(answered("refused"), instances.en.t);

    expect(rendered.title).toBe("Request to join Purchasing declined");
    expect(rendered.link).toBeNull();
    expect(rendered.actions).toEqual([]);
  });

  it("uses only keys present in both languages", () => {
    missing.length = 0;
    for (const lng of ["en", "fr"]) {
      renderNotification(republish, instances[lng].t);
      renderNotification(removed, instances[lng].t);
      renderNotification({ ...republish, handled_at: "x", handled_by_name: "Bob" }, instances[lng].t);
      renderNotification({ ...republish, handled_at: "x", handled_outcome: "removed" }, instances[lng].t);
      renderNotification(joinRequested, instances[lng].t);
      for (const item of [republish, removed, joinRequested, answered("accepted")]) {
        describeNotificationType(item.type, instances[lng].t);
      }
      for (const outcome of ["accepted", "refused"] as const) {
        renderNotification(answered(outcome), instances[lng].t);
        renderNotification(
          { ...joinRequested, handled_at: "x", handled_by_name: "Bob", handled_outcome: outcome },
          instances[lng].t,
        );
      }
    }

    expect(missing).toEqual([]);
  });
});
