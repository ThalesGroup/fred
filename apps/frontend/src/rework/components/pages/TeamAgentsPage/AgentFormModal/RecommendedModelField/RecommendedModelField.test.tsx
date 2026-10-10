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

// "Team default model" comes first, names today's default and saves null; only team-enabled models
// are offered; a stored model no longer offered stays shown and is flagged.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  AvailableModelProfileList,
  TeamRoutingPolicy,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  policy: undefined as TeamRoutingPolicy | undefined,
  availableModels: undefined as AvailableModelProfileList | undefined,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, string>) => (params?.model ? `${key}:${params.model}` : key),
  }),
}));

vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useTeamRoutingPolicyQuery: () => ({ data: h.policy }),
  useAvailableModelProfilesQuery: () => ({ data: h.availableModels }),
}));

// The Select molecule has its own tests; here only the options and error matter.
vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({
    options,
    value,
    error,
    onChange,
  }: {
    options: { value: string; label: string; description?: string }[];
    value: string;
    error?: string;
    onChange: (value: string) => void;
  }) => (
    <div data-value={value}>
      {options.map((option) => (
        <button key={option.value} data-value={option.value} onClick={() => onChange(option.value)}>
          {option.label}
          {option.description ? ` (${option.description})` : ""}
        </button>
      ))}
      {error && <span role="alert">{error}</span>}
    </div>
  ),
}));

import { RecommendedModelField } from "./RecommendedModelField.tsx";

const GPT = "model__openai__gpt-5";
const MISTRAL = "model__mistral__mistral-small";
const CLAUDE = "model__anthropic__claude";

const MODELS: AvailableModelProfileList = {
  profiles: [
    { profile_id: "chat.gpt5", capability_id: GPT, name: "gpt-5", display_name: "GPT-5" },
    { profile_id: "chat.mistral", capability_id: MISTRAL, name: "mistral-small" },
    { profile_id: "chat.claude", capability_id: CLAUDE, name: "claude", display_name: "Claude" },
  ],
  effective_default_profile_id: "chat.mistral",
};

let container: HTMLDivElement;
let root: Root;
const onChange = vi.fn();

function render(value: string | null) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<RecommendedModelField teamId="team-1" value={value} onChange={onChange} />);
  });
}

function optionLabels(): string[] {
  return Array.from(container.querySelectorAll("button")).map((button) => button.textContent ?? "");
}

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  onChange.mockClear();
  h.policy = undefined;
  h.availableModels = undefined;
});

describe("RecommendedModelField", () => {
  it("offers the team default first, then every team-enabled model, today's default included", () => {
    h.policy = { team_id: "team-1", version: 1, disabled_model_ids: [CLAUDE] };
    h.availableModels = MODELS;
    render(null);

    expect(optionLabels()).toEqual([
      "rework.teams.formAgent.fields.recommendedModel.teamDefault (rework.teams.formAgent.fields.recommendedModel.teamDefaultCurrent:Mistral Small)",
      "GPT-5",
      "Mistral Small",
    ]);
    expect(container.querySelector("[role=alert]")).toBeNull();
  });

  it("saves null for the team default and the profile id for a specific model", () => {
    h.availableModels = MODELS;
    render("chat.gpt5");

    act(() => (container.querySelector('button[data-value=""]') as HTMLButtonElement).click());
    expect(onChange).toHaveBeenLastCalledWith(null);
    act(() => (container.querySelector('button[data-value="chat.claude"]') as HTMLButtonElement).click());
    expect(onChange).toHaveBeenLastCalledWith("chat.claude");
  });

  it("keeps a model pinned to today's default as that specific model, not the team default", () => {
    h.availableModels = MODELS;
    render("chat.mistral");

    expect(container.querySelector("div[data-value]")?.getAttribute("data-value")).toBe("chat.mistral");
    expect(container.querySelector("[role=alert]")).toBeNull();
  });

  it("lists a model with two profiles once, keyed by the stored profile, and still names the default", () => {
    h.availableModels = {
      profiles: [
        { profile_id: "chat.gpt5", capability_id: GPT, name: "gpt-5", display_name: "GPT-5" },
        { profile_id: "chat.gpt5.creative", capability_id: GPT, name: "gpt-5", display_name: "GPT-5" },
        { profile_id: "chat.mistral", capability_id: MISTRAL, name: "mistral-small" },
      ],
      effective_default_profile_id: "chat.gpt5",
    };
    render("chat.gpt5.creative");

    expect(optionLabels()).toEqual([
      "rework.teams.formAgent.fields.recommendedModel.teamDefault (rework.teams.formAgent.fields.recommendedModel.teamDefaultCurrent:GPT-5)",
      "GPT-5",
      "Mistral Small",
    ]);
    expect(container.querySelector('button[data-value="chat.gpt5.creative"]')).not.toBeNull();
    expect(container.querySelector("[role=alert]")).toBeNull();
  });

  it("flags a stored model the team no longer offers", () => {
    h.policy = { team_id: "team-1", version: 1, disabled_model_ids: [CLAUDE] };
    h.availableModels = MODELS;
    render("chat.claude");

    expect(optionLabels()).toContain("Claude (rework.teams.formAgent.fields.recommendedModel.unavailableOption)");
    expect(container.querySelector("[role=alert]")?.textContent).toBe(
      "rework.teams.formAgent.fields.recommendedModel.unavailable:Claude",
    );
  });
});
