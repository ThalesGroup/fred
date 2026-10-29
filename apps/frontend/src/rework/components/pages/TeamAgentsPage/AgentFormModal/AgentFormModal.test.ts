// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  buildAgentFormSubmitPayload,
  defaultCapabilitySelection,
  extractCapabilityConfigValues,
} from "./AgentFormModal";
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
  it("starts selectable templates empty and retains fixed dependencies", () => {
    expect(defaultCapabilitySelection({ ...TEMPLATE, default_capability_ids: ["unconnected"] })).toEqual([]);
    expect(
      defaultCapabilitySelection({
        ...TEMPLATE,
        supports_capabilities: false,
        default_capability_ids: ["unconnected"],
      }),
    ).toEqual(["unconnected"]);
  });
  it("retains selection and configuration even if the catalog no longer advertises them", () => {
    const payload = buildAgentFormSubmitPayload(
      { ...form(), selectedCapabilityIds: ["unknown"], capabilityConfigValues: { unknown: { retained: true } } },
      TEMPLATE,
    );
    expect(createAgentRequest(payload)).toMatchObject({
      capability_ids: ["unknown"],
      capability_config_values: { unknown: { retained: true } },
    });
  });
  it("reads saved corpus values and omits capabilities from a metadata edit", () => {
    const config = { team_documents: true, attachments: false, document_uids: [], bind_libraries: false };
    const saved = {
      ...INSTANCE,
      selected_capability_ids: ["document_access"],
      capability_config: {
        document_access: { schema_version: "0.2.0", config },
      },
    };
    const values = extractCapabilityConfigValues(saved.capability_config);
    expect(values.document_access).toEqual(config);
    const payload = buildAgentFormSubmitPayload(
      {
        ...form(),
        displayName: "Renamed",
        selectedCapabilityIds: saved.selected_capability_ids,
        capabilityConfigValues: values,
      },
      TEMPLATE,
    );
    expect(updateAgentRequest(payload, saved)).toEqual({ display_name: "Renamed" });
    expect(saved.capability_config.document_access.config).toEqual(config);
  });
  it("does not resolve organization or project spaces, unknown ids, or personal-shaped legacy ids", () => {
    for (const kind of ["organization", "project"] as const)
      expect(resolveAgentSpace([{ ...SPACES[0], kind }], SPACES[0].id)).toBeUndefined();
    expect(resolveAgentSpace(SPACES, "personal-reader")).toBeUndefined();
    expect(resolveAgentSpace(SPACES, "personal")?.id).toBe(SPACES[1].id);
  });
});

it.each([
  { bind_libraries: true, library_tag_ids: ["folder"], document_uids: ["doc"] },
  { bind_libraries: true, library_tag_ids: [], document_uids: [] },
  { bind_libraries: false, library_tag_ids: [], document_uids: null },
])("round-trips document restrictions through create, reopen and update: %j", (config) => {
  const template = { ...TEMPLATE, supports_capabilities: true };
  const payload = buildAgentFormSubmitPayload(
    {
      ...form(),
      selectedCapabilityIds: ["document_access"],
      capabilityConfigValues: { document_access: config },
    },
    template,
  );
  expect(createAgentRequest(payload).capability_config_values?.document_access).toEqual(config);
  const saved = { ...INSTANCE, capability_config: { document_access: { schema_version: "0.3.0", config } } };
  const reopened = extractCapabilityConfigValues(saved.capability_config);
  expect(reopened.document_access).toEqual(config);
  expect(
    updateAgentRequest({ ...payload, templateHasCapabilities: true, capabilityConfigValues: reopened }, saved)
      .capability_config_values?.document_access,
  ).toEqual(config);
});
