// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import type { Prompt, PromptSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { SPACE_A } from "../TeamAgentsPage/weaverAgentFixtures";

/** Shared API payload, with deliberately different preview and full text. */
export function promptFixture(overrides: Partial<Prompt & PromptSummary> = {}): Prompt & PromptSummary {
  return {
    prompt_id: "prompt-1",
    space_id: SPACE_A,
    logical_name: "summary",
    display_name: "Real Name",
    description: "Real description",
    text_preview: "Truncated preview",
    text: "Real prompt text",
    created_at: "2026-10-31T10:00:00Z",
    updated_at: "2026-10-31T10:00:00Z",
    created_by: "reader",
    updated_by: "reader",
    ...overrides,
  };
}

export function promptSummaryFixture(overrides: Partial<PromptSummary> = {}): PromptSummary {
  const { text: _text, ...summary } = promptFixture(overrides);
  return summary;
}
