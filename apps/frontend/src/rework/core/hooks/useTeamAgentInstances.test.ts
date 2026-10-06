import { describe, expect, it } from "vitest";
import type { ManagedAgentInstanceSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { isPreparing } from "./useTeamAgentInstances";

const instance = (fields: Partial<ManagedAgentInstanceSummary>) => fields as ManagedAgentInstanceSummary;

describe("isPreparing", () => {
  it("is true while a capability is still preparing", () => {
    expect(isPreparing(instance({ suspension_reason: "capability_pending", suspension_detail: null }))).toBe(true);
  });

  it("is false once the preparation failed, so polling stops", () => {
    expect(
      isPreparing(instance({ suspension_reason: "capability_pending", suspension_detail: "Analysis failed" })),
    ).toBe(false);
  });

  it("is false for available agents and other suspensions", () => {
    expect(isPreparing(instance({ suspension_reason: null }))).toBe(false);
    expect(isPreparing(instance({ suspension_reason: "capability_unavailable" }))).toBe(false);
  });
});
