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

// The name is checked when the field is left, not on Create: a taken name
// shows under the field and keeps Create disabled until it changes.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
// Model reads are outside these form interaction tests; keep them isolated from Redux.
vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements.ts", () => ({
  useTeamRoutingPolicyQuery: () => ({ currentData: undefined, isError: false }),
  useAvailableModelProfilesQuery: () => ({ currentData: undefined, isError: false }),
}));
vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "Agent" }),
}));
vi.mock("@shared/organisms/SettingsModal/SettingsModal.tsx", () => ({
  default: ({ children, actions }: { children: React.ReactNode; actions: React.ReactNode }) => (
    <div>
      {children}
      <footer>{actions}</footer>
    </div>
  ),
}));
// These form-only tests have no Redux provider; model selection is outside their scope.
vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements.ts", () => ({
  useTeamRoutingPolicyQuery: () => ({ currentData: undefined }),
  useAvailableModelProfilesQuery: () => ({ currentData: undefined }),
}));
vi.mock("./TemplateBrowser/TemplateBrowser.tsx", () => ({
  TemplateBrowser: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <button data-testid="pick-template" onClick={() => onSelect("tpl")} />
  ),
}));
// Keep the required usage statement fillable so only name validation blocks Create.
vi.mock("./AgentFormBody.tsx", () => ({
  AgentFormBody: (props: {
    displayName: string;
    usageStatement: string;
    onUsageStatementChange: (v: string) => void;
    nameTaken?: boolean;
    onDisplayNameChange: (v: string) => void;
    onDisplayNameBlur?: () => void;
  }) => (
    <div>
      <input
        data-testid="name"
        value={props.displayName}
        onChange={(e) => props.onDisplayNameChange(e.target.value)}
        onBlur={props.onDisplayNameBlur}
      />
      <input
        data-testid="usage"
        value={props.usageStatement}
        onChange={(e) => props.onUsageStatementChange(e.target.value)}
      />
      {props.nameTaken && <p data-testid="taken">taken</p>}
    </div>
  ),
}));

import AgentFormModal from "./AgentFormModal";

const TEMPLATE = {
  template_id: "tpl",
  display_name: "Analyst",
  default_tuning_fields: [],
  available_capabilities: [],
} as unknown as AgentTemplateSummary;

const onSubmit = vi.fn(async () => undefined);
let container: HTMLDivElement;
let root: Root;

function render(props: {
  mode: "create" | "edit";
  takenNames: Set<string>;
  editInstance?: ManagedAgentInstanceSummary;
}) {
  act(() => {
    root.render(
      <AgentFormModal
        isOpen
        isSubmitting={false}
        templates={[TEMPLATE]}
        onClose={vi.fn()}
        onSubmit={onSubmit}
        {...props}
      />,
    );
  });
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  onSubmit.mockClear();
});

const nameInput = () => container.querySelector('[data-testid="name"]') as HTMLInputElement;
const submitButton = () => container.querySelector("footer button:last-of-type") as HTMLButtonElement;
const isTaken = () => container.querySelector('[data-testid="taken"]') !== null;

function type(value: string, input = nameInput()) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function chooseTemplate() {
  act(() => (container.querySelector('[data-testid="pick-template"]') as HTMLButtonElement).click());
  type("Internal team use.", container.querySelector('[data-testid="usage"]') as HTMLInputElement);
}

function leaveField() {
  act(() => {
    nameInput().dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
  });
}

describe("agent form name check", () => {
  it("warns on leaving the field, not while typing, and keeps Create disabled", () => {
    render({ mode: "create", takenNames: new Set(["writer"]) });
    chooseTemplate();

    type("  WRITER");
    expect(isTaken()).toBe(false);
    expect(submitButton().disabled).toBe(false);

    leaveField();
    expect(isTaken()).toBe(true);
    expect(submitButton().disabled).toBe(true);

    type("Writer 2");
    leaveField();
    expect(isTaken()).toBe(false);
    expect(submitButton().disabled).toBe(false);
  });

  it("flags a template name already used in the team as soon as the form opens on it", () => {
    render({ mode: "create", takenNames: new Set(["analyst"]) });
    chooseTemplate();

    expect(isTaken()).toBe(true);
    expect(submitButton().disabled).toBe(true);
  });

  it("shows a name the server refused once the page adds it to the taken names", () => {
    render({ mode: "create", takenNames: new Set() });
    chooseTemplate();
    expect(isTaken()).toBe(false);

    render({ mode: "create", takenNames: new Set(["analyst"]) });

    expect(isTaken()).toBe(true);
    expect(nameInput().value).toBe("Analyst");
  });
});
