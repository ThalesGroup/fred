// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { buildAgentFormSubmitPayload, defaultCapabilitySelection } from "./AgentFormModal";
import { createAgentRequest, updateAgentRequest, resolveAgentSpace } from "../weaverAgents";
import { INSTANCE, SPACES, TEMPLATE } from "../weaverAgentFixtures";

const form = () => ({
  templateId: TEMPLATE.template_id,
  displayName: INSTANCE.display_name,
  role: INSTANCE.role,
  description: INSTANCE.description ?? "",
  usageStatement: INSTANCE.usage_statement,
  recommendedChatProfileId: INSTANCE.recommended_chat_profile_id ?? null,
  tuningValues: INSTANCE.tuning_field_values,
  selectedCapabilityIds: INSTANCE.selected_capability_ids ?? [],
  capabilityConfigValues: {},
  capabilityAssetFiles: {},
  capabilityBlockingErrors: {},
});
describe("Weaver form fidelity", () => {
  it("keeps unchanged tuning objects by reference and omits every unchanged PATCH field", () => {
    const payload = buildAgentFormSubmitPayload(form(), TEMPLATE);
    expect(payload.tuningFieldValues).toBe(INSTANCE.tuning_field_values);
    expect(updateAgentRequest(payload, INSTANCE)).toEqual({});
  });
  it("omits tuning when an edit is reverted before a metadata save", () => {
    const payload = buildAgentFormSubmitPayload(
      { ...form(), displayName: "New", tuningValues: { ...INSTANCE.tuning_field_values } },
      TEMPLATE,
    );
    expect(updateAgentRequest(payload, INSTANCE)).toEqual({ display_name: "New" });
  });
  it("does not replace a null description with an empty string in a metadata-only edit", () => {
    const saved = { ...INSTANCE, description: null };
    const payload = buildAgentFormSubmitPayload({ ...form(), description: "", displayName: "New" }, TEMPLATE);
    expect(updateAgentRequest(payload, saved)).toEqual({ display_name: "New" });
  });
  it("sends an explicit empty tuning map only when the user changed tuning", () => {
    const payload = buildAgentFormSubmitPayload({ ...form(), tuningValues: {} }, TEMPLATE);
    expect(updateAgentRequest(payload, INSTANCE)).toEqual({ tuning_field_values: {} });
  });
  it("does not drop defaults absent from the catalog to make creation succeed", () => {
    expect(defaultCapabilitySelection({ ...TEMPLATE, default_capability_ids: ["unconnected"] })).toEqual([
      "unconnected",
    ]);
  });
  it("retains selection, configuration and profile even if the catalog no longer advertises them", () => {
    const payload = buildAgentFormSubmitPayload(
      { ...form(), selectedCapabilityIds: ["unknown"], capabilityConfigValues: { unknown: { retained: true } } },
      TEMPLATE,
    );
    expect(createAgentRequest(payload)).toMatchObject({
      capability_ids: ["unknown"],
      capability_config_values: { unknown: { retained: true } },
      recommended_chat_profile_id: "saved-profile",
    });
  });
  it("does not resolve organization or project spaces, unknown ids, or personal-shaped legacy ids", () => {
    for (const kind of ["organization", "project"] as const)
      expect(resolveAgentSpace([{ ...SPACES[0], kind }], SPACES[0].id)).toBeUndefined();
    expect(resolveAgentSpace(SPACES, "personal-reader")).toBeUndefined();
    expect(resolveAgentSpace(SPACES, "personal")?.id).toBe(SPACES[1].id);
  });
});
