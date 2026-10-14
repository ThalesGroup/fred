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

import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
  TeamWithPermissions,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { agentFileCapabilities, marketplaceErrorView, publishAvailability } from "./agentMarketplace";

const t = ((key: string, opts?: Record<string, unknown>) =>
  opts && Object.keys(opts).length ? `${key} ${JSON.stringify(opts)}` : key) as unknown as TFunction;

function instance(over: Partial<ManagedAgentInstanceSummary> = {}): ManagedAgentInstanceSummary {
  return {
    agent_instance_id: "a1",
    team_id: "team-1",
    template_id: "pod:basic",
    display_name: "Helper",
    role: "Helps",
    status: "enabled",
    ...over,
  };
}

function team(over: Partial<TeamWithPermissions> = {}, published = 1, quota = 5): TeamWithPermissions {
  return {
    id: "team-1",
    name: "Team",
    visibility: "public",
    marketplace: {
      agents_publishing_enabled: true,
      agents_publish_quota: quota,
      published_count: published,
    },
    ...over,
  };
}

const templates = [{ template_id: "pod:basic" } as AgentTemplateSummary];
const published = { state: "published" as const, version: 2, published_at: "2026-10-01T10:00:00Z" };

const availability = (over: Partial<Parameters<typeof publishAvailability>[0]> = {}) =>
  publishAvailability({
    instance: instance(),
    team: team(),
    canPublish: true,
    isPersonalTeam: false,
    templates,
    ...over,
  });

describe("publishAvailability", () => {
  it("offers Publish to an editor of a public team under its quota", () => {
    expect(availability()).toEqual({ kind: "publish" });
  });

  it("offers nothing to a non-editor, in the personal space, or while the switch is off", () => {
    expect(availability({ canPublish: false })).toBeNull();
    expect(availability({ isPersonalTeam: true })).toBeNull();
    const off = team();
    off.marketplace = { ...off.marketplace!, agents_publishing_enabled: false };
    expect(availability({ team: off })).toBeNull();
  });

  it("greys Publish for an administrator-only agent type", () => {
    expect(availability({ instance: instance({ template_id: "pod:internal" }) })).toEqual({
      kind: "publish",
      blockedReason: "templateNotPublic",
    });
  });

  it("does not grey while the agent types are unknown", () => {
    expect(availability({ instance: instance({ template_id: "pod:internal" }), templates: undefined })).toEqual({
      kind: "publish",
    });
  });

  it("greys Publish in a private team", () => {
    expect(availability({ team: team({ visibility: "private" }) })?.blockedReason).toBe("teamPrivate");
  });

  it("greys Publish at the quota, including after a removal", () => {
    expect(availability({ team: team({}, 5, 5) })?.blockedReason).toBe("quotaReached");
    const removed = instance({ marketplace: { ...published, state: "removed", removed_reason: "deactivated" } });
    expect(availability({ instance: removed, team: team({}, 5, 5) })).toEqual({
      kind: "publish",
      blockedReason: "quotaReached",
    });
  });

  it("lets a published agent be republished above a lowered quota", () => {
    expect(availability({ instance: instance({ marketplace: published }), team: team({}, 6, 3) })).toEqual({
      kind: "republish",
    });
  });
});

describe("agentFileCapabilities", () => {
  it("names the selected capabilities that hold configuration files", () => {
    const withCaps = [
      {
        template_id: "pod:basic",
        available_capabilities: [
          { id: "ppt", name: "PowerPoint", assets: [{ key: "template", accepted_types: [".pptx"] }] },
          { id: "search", name: "Search", assets: [] },
          { id: "other", name: "Other", assets: [{ key: "x", accepted_types: [] }] },
        ],
      } as unknown as AgentTemplateSummary,
    ];
    const agent = instance({ selected_capability_ids: ["ppt", "search"] });
    expect(agentFileCapabilities(agent, withCaps, t)).toEqual(['PowerPoint {"defaultValue":"ppt"}']);
  });
});

describe("marketplaceErrorView", () => {
  const error = (code: string, extra: Record<string, unknown> = {}) => ({
    status: 409,
    data: { detail: { code, message: "English text", ...extra } },
  });

  it("flags a stale version so the card refreshes", () => {
    expect(marketplaceErrorView(error("marketplace_version_conflict"), t, (id) => id)).toEqual({
      stale: true,
      message: 'rework.agentMarketplace.errors.marketplace_version_conflict {"capability":""}',
    });
  });

  it("localizes a marketplace code and names the capability", () => {
    const view = marketplaceErrorView(
      error("marketplace_capability_not_exportable", { capability_id: "ppt" }),
      t,
      () => "PowerPoint",
    );
    expect(view.stale).toBe(false);
    expect(view.message).toContain("marketplace_capability_not_exportable");
    expect(view.message).toContain("PowerPoint");
  });

  it("falls back to the generic message for anything else", () => {
    expect(marketplaceErrorView({ status: 500 }, t, (id) => id).message).toBe("rework.agentCard.unexpectedError");
  });
});
