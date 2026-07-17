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

// Chat-turn-control registry (CAPAB-01 #1976): descriptors resolve against the
// owning capability's plugin first, then the capability-agnostic stock kit by
// widget id; neither found is a silent skip.

import { describe, expect, it } from "vitest";
import { buildChatTurnControlRegistry, resolveChatTurnControls } from "./chatTurnControlRegistry";
import type { CapabilityChatTurnControlProps, CapabilityUiPlugin } from "./types";
import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";

function StubControl(_props: CapabilityChatTurnControlProps) {
  return <div />;
}

function StockControl(_props: CapabilityChatTurnControlProps) {
  return <div />;
}

function descriptor(capabilityId: string, widget: string, params?: object): ChatControlDescriptor {
  return { capability_id: capabilityId, widget, ...(params ? { params } : {}) };
}

describe("chatTurnControlRegistry (#1976)", () => {
  const withControl: CapabilityUiPlugin = { id: "demo_echo", chatTurnControls: { demo_toggle: StubControl } };
  const withoutControl: CapabilityUiPlugin = { id: "plain", partRenderers: {} };
  const stockKit = { attach_files: StockControl, search_policy: StockControl };

  it("resolves a plugin-declared control for its owning capability", () => {
    const registry = buildChatTurnControlRegistry([withControl, withoutControl], stockKit);
    const resolved = resolveChatTurnControls([descriptor("demo_echo", "demo_toggle")], registry);

    expect(resolved).toHaveLength(1);
    expect(resolved[0]).toMatchObject({ capabilityId: "demo_echo", widget: "demo_toggle", Component: StubControl });
  });

  it("falls back to the stock kit by widget id for a dynamic MCP capability id", () => {
    const registry = buildChatTurnControlRegistry([withControl], stockKit);
    const resolved = resolveChatTurnControls(
      [descriptor("my-server", "search_policy", { default: "hybrid" })],
      registry,
    );

    expect(resolved).toHaveLength(1);
    expect(resolved[0]).toMatchObject({
      capabilityId: "my-server",
      widget: "search_policy",
      params: { default: "hybrid" },
      Component: StockControl,
    });
  });

  it("skips a descriptor resolving to neither a plugin entry nor the stock kit", () => {
    const registry = buildChatTurnControlRegistry([withoutControl], stockKit);
    expect(resolveChatTurnControls([descriptor("plain", "not_a_widget")], registry)).toHaveLength(0);
  });

  it("defaults params to {} when the descriptor omits them", () => {
    const registry = buildChatTurnControlRegistry([], stockKit);
    const resolved = resolveChatTurnControls([descriptor("my-server", "attach_files")], registry);
    expect(resolved[0].params).toEqual({});
  });

  it("preserves descriptor order and prefers the plugin entry over a same-named stock widget", () => {
    const overridingPlugin: CapabilityUiPlugin = {
      id: "my-server",
      chatTurnControls: { attach_files: StubControl },
    };
    const registry = buildChatTurnControlRegistry([overridingPlugin], stockKit);
    const resolved = resolveChatTurnControls(
      [descriptor("my-server", "search_policy"), descriptor("my-server", "attach_files")],
      registry,
    );

    expect(resolved.map((r) => r.widget)).toEqual(["search_policy", "attach_files"]);
    expect(resolved[0].Component).toBe(StockControl);
    expect(resolved[1].Component).toBe(StubControl);
  });
});
