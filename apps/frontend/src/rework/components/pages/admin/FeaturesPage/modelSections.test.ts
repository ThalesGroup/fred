import { describe, expect, it } from "vitest";
import type {
  CapabilityEnablementItem,
  DiscoverySourceStatus,
} from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { partitionDiscoveredModels } from "./modelSections";

const model = (id: string, overrides: Partial<CapabilityEnablementItem> = {}) =>
  ({
    id,
    model_discovery_source_id: "mistral",
    default_on: false,
    enabled_team_ids: [],
    personal_scope: "default",
    ...overrides,
  }) as CapabilityEnablementItem;

describe("partitionDiscoveredModels", () => {
  it("hides every model absent from the latest inventory, including models with existing grants", () => {
    const removed = ["unused", "team", "personal", "default"].map((id) => model(id));
    removed[1].enabled_team_ids = ["team-a"];
    removed[2].personal_scope = "enabled";
    removed[3].default_on = true;
    const available = model("available");
    const sources = [
      {
        source_id: "mistral",
        last_success_at: "2026-10-23T09:00:00Z",
        available_models: [{ id: "available" }],
        removed_models: [],
      },
    ] as DiscoverySourceStatus[];

    const result = partitionDiscoveredModels([...removed, available], sources);

    expect(result.available.map(({ id }) => id)).toEqual(["available"]);
    expect(result.unavailableIds).toEqual(new Set(["unused", "team", "personal", "default"]));
  });

  it("does not mark a model unavailable when another source owns the removed id", () => {
    const other = model("shared", { model_discovery_source_id: "openai" });
    const sources = [{ source_id: "mistral", removed_models: [{ id: "shared" }] }] as DiscoverySourceStatus[];

    expect(partitionDiscoveredModels([other], sources).available).toEqual([other]);
  });

  it("shows a missing historical ID as a separate unavailable row when the provider publishes a new ID", () => {
    const current = model("model__openai__new", { name: "zai-glm-5-3-flash" });
    const sources = [
      {
        source_id: "mistral",
        last_success_at: "2026-10-23T09:00:00Z",
        available_models: [{ id: current.id, name: current.name, provider: "openai" }],
        removed_models: [
          {
            id: "model__openai__old",
            name: "glm-5-3-flash",
            display_name: "zai-glm-5-3-flash",
            provider: "openai",
          },
        ],
      },
    ] as DiscoverySourceStatus[];

    const result = partitionDiscoveredModels([current], sources);
    expect(result.listed.map((item) => item.name)).toEqual(["zai-glm-5-3-flash", "glm-5-3-flash"]);
    expect(result.unavailableIds).toEqual(new Set(["model__openai__old"]));
  });
});
